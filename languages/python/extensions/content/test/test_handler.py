"""§6 — the system content handler, driven OVER THE WIRE from a second peer.

In-process handler calls would be faster and would measure less. The failure this repo has
already shipped once is a call site read as a capability — a symbol present, reachable,
consulted, and answering `501` behind the call.

**What stays in-process is only what a wire client cannot construct**: a pinned frame
budget. On this peer that is a shorter list than on `typescript`, because the host CLI
takes `--max-frame-bytes` and `Peer(seed, max_frame_bytes=N)` exists — so the budget test
here configures a real peer and drives a real connection, where the `typescript` one has
to hand-build a `ConnectionState`. Same assertion, one substrate more honest.
"""

from __future__ import annotations

import threading

import pytest
from entity_core.peer import Identity, Peer, dial, listen, resource_target
from entity_core.peer.model import Entity, Envelope
from entity_core.peer.wire import response_result, response_status

from entity_content import (
    CONTENT_PATTERN,
    CONTENT_RESPONSE,
    GET_REQUEST,
    INGEST_REQUEST,
    INGEST_RESULT,
    ALL_TYPES,
    create_blob_fixed,
    ensure_closure,
    install_content,
    store_blob,
)

HOST_SEED = bytes([0x61] * 32)
CLIENT_SEED = bytes([0x62] * 32)


class Rig:
    """Host peer + an authenticated session from a second identity."""

    def __init__(self, **peer_kwargs):
        self.peer = Peer(HOST_SEED, open_grants=True, **peer_kwargs)
        self.installation = install_content(self.peer)
        self._listener = listen(self.peer, 0)
        self.client = Identity.of_seed(CLIENT_SEED)
        self._conn = dial("127.0.0.1", self._listener.port)
        self._conn.handshake(self.client)
        self.uri = "/" + self.peer.local_peer + "/" + CONTENT_PATTERN

    def execute(self, op, params, resource=resource_target(CONTENT_PATTERN)):
        env = self._conn.execute(self.client, self.uri, op, params, resource)
        assert env is not None, "no response envelope"
        return env

    def close(self):
        self._conn.close()
        self._listener.close()


@pytest.fixture
def rig():
    r = Rig()
    try:
        yield r
    finally:
        r.close()


def error_code(env) -> str | None:
    result = response_result(env)
    if result is None or result.type != "system/protocol/error":
        return None
    return result.text("code")


def hash_list(env, field: str) -> list[bytes]:
    result = response_result(env)
    assert result is not None
    return [bytes(h) for h in result.field(field)]


# ── §6.2 / §6.3 path-as-resource MUST ────────────────────────────────────────


def test_get_without_a_resource_is_400_path_required(rig):
    env = rig.execute("get", Entity.make(GET_REQUEST, {"hashes": []}), resource=None)
    assert error_code(env) == "path_required"
    # The oracle checks the CODE only, so a peer answering 404 passes the gate and fails
    # the spec. GUIDE-EXTENSION-DEVELOPMENT §171 pins 400; assert the status too.
    assert response_status(env) == 400


def test_ingest_without_a_resource_is_400_path_required(rig):
    target = Entity.make("test/marker", {})
    env = rig.execute("ingest", Entity.make(INGEST_REQUEST, {"entity": target.to_cbor()}), resource=None)
    assert error_code(env) == "path_required"
    assert response_status(env) == 400


def test_an_empty_targets_list_never_reaches_the_handler(rig):
    """**Measured, and it corrects an assumption in this module's own code.**

    `handler._resource_targets` treats `{targets: []}` as absent, so the handler would
    answer `path_required` — core §3.2 makes `targets` MUST-contain-at-least-one, so an
    empty list is malformed rather than a valid empty scope. Over the wire that branch is
    **unreachable**: `check_permission` runs before dispatch and refuses the malformed
    resource with `403 capability_denied` first.

    Asserted as it actually behaves rather than as the handler intends, because the
    difference is the finding. The handler's own branch is kept — it is still the right
    answer for an in-process dispatch, which has no cap check in front of it — but this
    test stops it from being mistaken for the wire contract.
    """
    env = rig.execute("get", Entity.make(GET_REQUEST, {"hashes": []}), resource={"targets": []})
    assert response_status(env) == 403
    assert error_code(env) == "capability_denied"


def test_a_resource_target_outside_the_namespace_is_403(rig):
    env = rig.execute(
        "get", Entity.make(GET_REQUEST, {"hashes": []}), resource=resource_target("local/files")
    )
    assert response_status(env) == 403
    # v3.7 §6.4: `capability_denied`, not `forbidden`. Asserted on the CODE and not on the
    # status alone, because the status was already right under v3.6 and the code was not —
    # a test that checked only `403` would have survived the re-pin without noticing.
    assert error_code(env) == "capability_denied"


# ── §6.2 get ─────────────────────────────────────────────────────────────────


def test_get_names_a_resolved_hash_in_found_and_an_unknown_one_in_missing(rig):
    blob = create_blob_fixed(b"\x07" * 3000, 1024)
    blob_hash = store_blob(rig.peer.store, blob)
    unknown = bytes([0x00, 0xAB] + [0] * 31)

    env = rig.execute("get", Entity.make(GET_REQUEST, {"hashes": [blob_hash, unknown]}))
    result = response_result(env)

    assert response_status(env) == 200, "a miss is not an error — §6.2 always answers {found, missing}"
    assert result.type == CONTENT_RESPONSE
    # §6.2 wire-shape contract (F4 audit landing): ARRAYS, not counters. Deriving a count
    # from an array is trivial; deriving an array from a count is not.
    assert hash_list(env, "found") == [bytes(blob.blob.hash)]
    assert len(hash_list(env, "missing")) == 1
    # THE contract: `found` is an index INTO `included`. A response naming a hash it did
    # not deliver is a reference without a referent.
    assert env.included.get_by_hash(blob_hash) is not None
    # Amendment 2: `pending` is OPTIONAL and advertises sync-state visibility. No
    # subscription, no inbox — emitting it even empty would claim a capability we lack.
    assert result.field("pending") is None


def test_the_handler_is_type_agnostic(rig):
    arbitrary = Entity.make("test/whatever", {"k": "v"})
    rig.peer.store.put_entity(arbitrary)
    env = rig.execute("get", Entity.make(GET_REQUEST, {"hashes": [bytes(arbitrary.hash)]}))
    assert response_status(env) == 200
    assert env.included.get_by_hash(bytes(arbitrary.hash)) is not None, (
        "§6: 'It serves any entity type, not just blobs and chunks.'"
    )


def test_malformed_params_are_400_unexpected_params_not_a_crash(rig):
    env = rig.execute("get", Entity.make(GET_REQUEST, {"hashes": "not an array"}))
    assert response_status(env) == 400
    assert error_code(env) == "unexpected_params"


def test_an_unadvertised_operation_is_501(rig):
    env = rig.execute("delete", Entity.make("primitive/any", {}))
    assert response_status(env) == 501
    assert error_code(env) == "unsupported_operation"


def test_amendment_1_the_budget_consulted_is_the_configured_one():
    """§6.2 Amendment 1: consult the CONNECTION's configured budget, never a hardcoded
    16 MiB literal.

    Two peers, identical but for the budget, driven over real connections. The wide arm
    packs both entities; the squeezed arm packs neither. **A handler reading
    `wire.MAX_FRAME` would answer identically twice**, which is what makes this a
    measurement rather than a smoke test — and it is only constructible because keystone
    landed `Peer(seed, max_frame_bytes=N)` on 2026-09-06 (our K-1).
    """
    big = Entity.make("test/big", {"p": b"\x01" * 64_000})
    small = Entity.make("test/small", {"p": "x"})
    request = Entity.make(GET_REQUEST, {"hashes": [bytes(big.hash), bytes(small.hash)]})

    wide = Rig()
    try:
        wide.peer.store.put_entity(big)
        wide.peer.store.put_entity(small)
        env = wide.execute("get", request)
        assert len(hash_list(env, "found")) == 2
    finally:
        wide.close()

    squeezed = Rig(max_frame_bytes=8192)
    try:
        squeezed.peer.store.put_entity(big)
        squeezed.peer.store.put_entity(small)
        env = squeezed.execute("get", request)
        # §6.2: "include as many as fit (IN REQUEST ORDER) and move the remainder to
        # `missing`". Once the budget is exhausted the small entity does NOT get packed —
        # order is the contract, so the requester's retry makes deterministic progress.
        assert hash_list(env, "missing") == [bytes(big.hash), bytes(small.hash)]
        assert hash_list(env, "found") == []
    finally:
        squeezed.close()


# ── §6.3 ingest ──────────────────────────────────────────────────────────────


def test_entity_mode_stores_one_entity_and_omits_root(rig):
    target = Entity.make("test/marker", {"n": 1})
    env = rig.execute("ingest", Entity.make(INGEST_REQUEST, {"entity": target.to_cbor()}))
    result = response_result(env)

    assert response_status(env) == 200
    assert result.type == INGEST_RESULT
    assert result.uint("ingested_count") == 1
    assert result.bytes_("root_hash") == bytes(target.hash)
    # §6.3: "In entity mode, `root` is absent — there is no envelope wrapper to pass through."
    assert result.field("root") is None
    assert rig.peer.store.get_by_hash(bytes(target.hash)) is not None


def test_envelope_mode_inlines_root_and_counts_root_plus_included(rig):
    """§6.3 + §11.1 MUST."""
    inner = Entity.make("test/inner", {"v": "leaf"})
    root = Entity.make("test/wrapper", {"head": bytes(inner.hash)})
    envelope = Envelope.of(root, inner)

    env = rig.execute("ingest", Entity.make(INGEST_REQUEST, {"envelope": envelope.to_cbor()}))
    result = response_result(env)

    assert response_status(env) == 200
    assert result.uint("ingested_count") == 2
    # The §11.1 MUST: it lets a continuation navigate `data.root.data.head` without
    # dereferencing the content store (§6.3.1).
    inlined = result.field("root")
    assert isinstance(inlined, dict) and inlined["type"] == "test/wrapper"
    assert rig.peer.store.get_by_hash(bytes(inner.hash)) is not None
    assert rig.peer.store.get_by_hash(bytes(root.hash)) is not None


def test_both_inputs_is_ambiguous_and_neither_is_missing(rig):
    e = Entity.make("test/marker", {})
    envelope = Envelope.of(e)

    both = Entity.make(INGEST_REQUEST, {"envelope": envelope.to_cbor(), "entity": e.to_cbor()})
    assert error_code(rig.execute("ingest", both)) == "ambiguous_input"

    neither = Entity.make(INGEST_REQUEST, {})
    assert error_code(rig.execute("ingest", neither)) == "missing_input"


def test_ingest_is_idempotent(rig):
    payload = Entity.make("test/round", {"p": "trip"})
    params = Entity.make(INGEST_REQUEST, {"entity": payload.to_cbor()})
    assert response_status(rig.execute("ingest", params)) == 200
    env = rig.execute("ingest", params)
    assert response_status(env) == 200
    assert response_result(env).bytes_("root_hash") == bytes(payload.hash)

    got = rig.execute("get", Entity.make(GET_REQUEST, {"hashes": [bytes(payload.hash)]}))
    assert hash_list(got, "found") == [bytes(payload.hash)]


# ── §6.1 manifest + §2 types, as the oracle reads them ───────────────────────


def test_the_published_manifest_carries_the_operation_input_output_types(rig):
    iface = rig.peer.store.get_at("/" + rig.peer.local_peer + "/system/handler/" + CONTENT_PATTERN)
    assert iface is not None, "index entry at system/handler/system/content"
    assert iface.text("pattern") == CONTENT_PATTERN
    ops = iface.field("operations")
    assert ops["get"]["input_type"] == GET_REQUEST
    assert ops["get"]["output_type"] == CONTENT_RESPONSE
    assert ops["ingest"]["input_type"] == INGEST_REQUEST
    assert ops["ingest"]["output_type"] == INGEST_RESULT


def test_every_type_entity_the_oracle_reads_is_published(rig):
    for name in ALL_TYPES:
        path = "/" + rig.peer.local_peer + "/system/type/" + name
        assert rig.peer.store.get_at(path) is not None, f"{name} must be registered"


def test_the_handler_body_is_installed_last(rig):
    """Order is not cosmetic: dispatch resolves the pattern by walking the TREE, then
    consults the dict. Both must be present, and the tree write must not lag the dict."""
    assert CONTENT_PATTERN in rig.peer.handlers
    assert rig.peer.store.get_at("/" + rig.peer.local_peer + "/" + CONTENT_PATTERN) is not None


# ── §3.3 EnsureClosure ───────────────────────────────────────────────────────


def test_closure_distinguishes_complete_missing_chunk_and_blob_not_found():
    peer = Peer(HOST_SEED)
    blob = create_blob_fixed(b"\x09" * 2500, 1024)
    blob_hash = store_blob(peer.store, blob)

    ok = ensure_closure(peer.store, blob_hash)
    assert ok.complete and ok.total_size == 2500 and ok.chunk_count == 3

    # §3.3 orders the checks: the first missing chunk reports `missing_chunk`, NOT
    # `size_mismatch`, even though the totals also disagree.
    orphan = create_blob_fixed(b"\x03" * 4096, 1024)
    peer.store.put_entity(orphan.blob)
    verdict = ensure_closure(peer.store, bytes(orphan.blob.hash))
    assert not verdict.complete and verdict.code == "missing_chunk"

    absent = ensure_closure(peer.store, bytes(33))
    assert not absent.complete and absent.code == "blob_not_found"


# ── §6.4 step 2 — in-process, because the wire cannot isolate it ────────────────────


def test_a_target_the_capability_does_not_cover_is_403_even_inside_the_namespace():
    """§6.4 step 2 — the PATH-SCOPE check, ``check_path_permission`` with handler pattern
    ``system/content``. In-process on purpose: over the wire the dispatcher's step-1 resource
    check refuses the same request first, so a wire test passes with our clause deleted (D15's
    sharpened clause — the control must remove the SUBJECT). CONTROL: a covering grant proceeds.
    """
    from entity_core.peer.handlers import DispatchCtx
    from entity_core.peer.wire import make_execute

    peer = Peer(HOST_SEED, open_grants=True)
    install_content(peer)
    handler = peer.handlers[CONTENT_PATTERN]

    def grant(resource: str) -> Entity:
        return Entity.make("system/capability/token", {"grants": [{
            "handlers": {"include": [CONTENT_PATTERN]},
            "resources": {"include": [resource]},
            "operations": {"include": ["get"]},
        }]})

    exec_e = make_execute("r-64", "/" + peer.local_peer + "/" + CONTENT_PATTERN, "get",
                          Entity.make(GET_REQUEST, {"hashes": []}),
                          resource=resource_target(CONTENT_PATTERN + "/private/x"))

    def call(token: Entity):
        ctx = DispatchCtx(exec=exec_e, conn=None, included={}, caller_cap=token, has_cap=True,
                          handler_pattern=CONTENT_PATTERN)
        return handler.handle_op("get", ctx)

    denied = call(grant(CONTENT_PATTERN + "/public/*"))
    assert denied.status == 403
    assert denied.result.text("code") == "capability_denied"
    assert call(grant(CONTENT_PATTERN + "/*")).status == 200, "control: a covering grant proceeds"
