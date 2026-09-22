"""CONTENT §6 — the system content handler.

Two operations, ``get`` (§6.2) and ``ingest`` (§6.3), both hash-addressed at the params
level and path-addressed at the cap-scope level (§6.4).

**The dispatch idiom is `python`'s, not a translation of the `typescript` one.** A handler
here is any object with ``handle_op(op, ctx) -> Outcome`` — duck-typed, so no
peer-internal base class is inherited. The per-operation ``if`` ladder is what every
bootstrap handler in this peer does; a ``dict`` of methods would be more like the Go
reference and less like the substrate we are installing into.

**Three context facts this handler is built around, all measured** by
`gates/host-seam/probe-seam.py` rather than read:

1. ``DispatchCtx`` carries **no peer**. The store arrives by registration-time capture,
   which is why ``__init__`` takes one.
2. ``DispatchCtx`` carries **no suffix**. ``_resolve_handler`` matches the pattern and
   drops the remainder, so a body that needs it re-derives it from ``ctx.exec``'s URI.
3. ``ctx.frame_budget()`` returns the budget the transport is enforcing on THIS
   connection — as of keystone 2026-09-06, and measured by value rather than by
   attribute name: a peer configured to enforce 3,145,749 reports 3,145,749, and an
   unconfigured one reports the 16 MiB default that the §6.2 amendment names as the
   wrong answer.
"""

from __future__ import annotations

from typing import Any

from entity_core.peer.handlers import DispatchCtx, Outcome
from entity_core.peer.model import Entity, entity_of_cbor
from entity_core.peer.wire import error_result

from .types import (
    CONTENT_PATTERN,
    CONTENT_RESPONSE,
    GET_REQUEST,
    INGEST_RESULT,
)

#: Envelope + response overhead reserved out of the frame budget before entities are
#: packed. The response entity carries two hash arrays (33 B each plus CBOR framing) and
#: the envelope adds its own map framing; 4 KiB is comfortably above both for any batch a
#: caller can request within one frame.
FRAME_RESERVE_BYTES = 4096


def _err(status: int, code: str, message: str = "") -> Outcome:
    return Outcome(status, error_result(code, message))


class ContentHandler:
    """The §6.1 handler. Installed by :func:`entity_content.install_content`."""

    def __init__(self, peer, namespace: str = CONTENT_PATTERN) -> None:
        #: Registration-time capture. `python`'s DispatchCtx carries no peer (measured),
        #: so this is the only route from a body to the store, the tree and the emit bus.
        self.peer = peer
        #: The namespace prefix this instance serves (§6.4). `system/content` is the
        #: default-namespace value §6.2 pins for the §6.1 manifest registration.
        #:
        #: TOPOLOGY: cycle 1 runs single-trust-domain (§6.4.1) — `get` resolves any hash
        #: in the content store and `ingest` writes the store without binding into the
        #: tree. §6.4.1 makes that OPT-IN AND RESTRICTED ("MUST NOT be enabled as the
        #: default configuration"; multi-party deployments running it are "out-of-spec
        #: and security-defective"). Declared in `EXTENSION.toml [assumptions].topology`,
        #: not assumed here.
        self.namespace = namespace

    #: §6.1 manifest operations, in the mapped §3.7 form.
    OPERATIONS = ("get", "ingest")

    # ── dispatch ─────────────────────────────────────────────────────────────

    def handle_op(self, op: str, ctx: DispatchCtx) -> Outcome:
        # §6.2 / §6.3 path-as-resource MUST, checked FIRST because it applies to both ops
        # identically. `400 path_required` — the status is pinned by
        # GUIDE-EXTENSION-DEVELOPMENT §171, and the oracle checks only the CODE, so a peer
        # answering 404 passes the gate and fails the spec. We answer 400.
        targets = _resource_targets(ctx.exec)
        if targets is None:
            return _err(
                400,
                "path_required",
                f"{CONTENT_PATTERN}:{op} requires a resource naming the namespace path (§6.2/§6.3)",
            )

        # §6.4 step 2 — path-scope check, handler-level. Dispatch already verified the
        # resource against the grant's `resources` scope (§6.4 step 1), so this is
        # defence-in-depth: it refuses a target outside the namespace this instance
        # serves even if a grant somehow covered it.
        for target in targets:
            if not _within_namespace(target, self.namespace):
                return _err(
                    403,
                    "forbidden",
                    f"resource target '{target}' is outside namespace '{self.namespace}' (§6.4)",
                )

        if op == "get":
            return self._get(ctx)
        if op == "ingest":
            return self._ingest(ctx)
        # §6.6(2): "This spec does not define a `system/content:delete`." Removal is
        # local GC, never a protocol op — so an unknown verb is 501, not 404.
        return _err(501, "unsupported_operation", op)

    # ── §6.2 get ─────────────────────────────────────────────────────────────

    def _get(self, ctx: DispatchCtx) -> Outcome:
        params = ctx.exec.sub_entity("params")
        hashes = params.field("hashes") if params is not None else None
        if not isinstance(hashes, list):
            return _err(
                400, "unexpected_params", "get expects {hashes: array_of system/hash} (§6.2)"
            )

        # Amendment 1 §6.2 MUST: consult THE CONNECTION'S configured budget at
        # response-construction time, not a hardcoded 16 MiB literal. `frame_budget()`
        # prefers the connection's value and falls back to the peer's configured default
        # only for an in-process dispatch, which has no frame at all.
        remaining = _frame_budget(ctx) - FRAME_RESERVE_BYTES

        found: list[bytes] = []
        missing: list[bytes] = []
        included: list[Entity] = []
        # Once the budget is exhausted every REMAINING hash goes to `missing` in request
        # order — §6.2 says "as many as fit (in request order)", so a small entity after a
        # large one does NOT get packed. Order is the contract; the requester retries with
        # `missing` and makes deterministic progress.
        exhausted = False

        for raw in hashes:
            if not isinstance(raw, (bytes, bytearray)):
                return _err(400, "unexpected_params", "hashes entries must be byte strings (§6.2)")
            h = bytes(raw)
            entity = self.peer.store.get_by_hash(h)
            if entity is None:
                missing.append(h)
                continue
            cost = _wire_size(entity) + len(h)
            if exhausted or cost > remaining:
                exhausted = True
                missing.append(h)
                continue
            remaining -= cost
            included.append(entity)
            found.append(h)

        # §6.2 Amendment 2: `pending` is OPTIONAL and SHOULD be populated only by an
        # implementation with sync-state visibility — an active subscription on the
        # namespace plus an inbox feeding the content store. This composition has neither,
        # so the field is OMITTED. Emitting an empty array would advertise a capability we
        # do not have; §6.2 says a receiver that omits it is telling the caller to treat
        # all `missing` as terminal, which is the truth here.
        response = Entity.make(CONTENT_RESPONSE, {"found": found, "missing": missing})
        return Outcome.ok(response, *included)

    # ── §6.3 ingest ──────────────────────────────────────────────────────────

    def _ingest(self, ctx: DispatchCtx) -> Outcome:
        params = ctx.exec.sub_entity("params")
        if params is None:
            return _err(400, "missing_input", "Specify envelope or entity")

        envelope = params.field("envelope")
        entity_val = params.field("entity")
        has_envelope = isinstance(envelope, dict)
        has_entity = isinstance(entity_val, dict)

        if has_envelope and has_entity:
            return _err(400, "ambiguous_input", "Specify envelope or entity, not both")
        if not has_envelope and not has_entity:
            return _err(400, "missing_input", "Specify envelope or entity")

        # ── Entity mode: store a single entity. `root` is ABSENT from the result —
        # there is no envelope wrapper to pass through (§6.3), and the §11.1 MUST is
        # scoped to envelope mode with a non-null root.
        if has_entity:
            try:
                entity = entity_of_cbor(entity_val)
            except Exception as exc:  # noqa: BLE001 - a malformed entity is a 400, not a crash
                return _err(400, "unexpected_params", f"entity: {exc}")
            self.peer.store.put_entity(entity)
            return Outcome.ok(
                Entity.make(
                    INGEST_RESULT,
                    {"root_hash": bytes(entity.hash), "ingested_count": 1},
                )
            )

        # ── Envelope mode: store root + all included.
        #
        # `system/envelope` extends `core/envelope`, whose `root` is a REQUIRED
        # `core/entity`, so §6.3's `if envelope.root is not null` branch is unreachable
        # for a well-formed envelope and a missing root is a malformed request rather
        # than an empty-count success.
        root_val = envelope.get("root")
        if not isinstance(root_val, dict):
            return _err(400, "unexpected_params", "envelope: missing required root (§3.1)")
        try:
            root = entity_of_cbor(root_val)
        except Exception as exc:  # noqa: BLE001
            return _err(400, "unexpected_params", f"envelope.root: {exc}")

        self.peer.store.put_entity(root)
        count = 1

        included_val = envelope.get("included")
        if isinstance(included_val, dict):
            for key, value in included_val.items():
                if not isinstance(value, dict):
                    return _err(400, "unexpected_params", "envelope.included values must be entities")
                try:
                    inner = entity_of_cbor(value)
                except Exception as exc:  # noqa: BLE001
                    return _err(400, "unexpected_params", f"envelope.included: {exc}")
                # §6.3 hash-validation MUST: each included entity's content hash is
                # verified against its key in the included map. `entity_of_cbor` already
                # re-derives the hash from {type, data} and rejects a carried mismatch
                # (§1.8 validate-before-trust); this is the §3.1 KEY check, which is a
                # different assertion and the one §6.3 names.
                if bytes(_key_bytes(key)) != bytes(inner.hash):
                    return _err(400, "hash_mismatch", "included entity hash does not match key")
                self.peer.store.put_entity(inner)
                count += 1

        # §11.1 MUST: `root` is included, inlined, in envelope mode. It lets a
        # continuation navigate `data.root.data.<field>` without dereferencing the
        # content store (§6.3.1).
        return Outcome.ok(
            Entity.make(
                INGEST_RESULT,
                {
                    "root": root.to_cbor(),
                    "root_hash": bytes(root.hash),
                    "ingested_count": count,
                },
            )
        )


# ── helpers ──────────────────────────────────────────────────────────────────


def _resource_targets(exec_e: Entity) -> list[str] | None:
    """The EXECUTE's resource targets, or None when the field is absent (§3.2).

    An EMPTY targets list is treated as absent rather than as a valid empty scope: core
    §3.2 makes `targets` MUST-contain-at-least-one, so `{targets: []}` is malformed, and
    answering `path_required` for it is the same answer a caller needs.
    """
    resource = exec_e.field("resource")
    if not isinstance(resource, dict):
        return None
    targets = resource.get("targets")
    if not isinstance(targets, list) or not targets:
        return None
    return [t for t in targets if isinstance(t, str)]


def _within_namespace(target: str, namespace: str) -> bool:
    """A resource target is in-namespace if it IS the prefix or sits under it."""
    t = target.lstrip("/")
    return t == namespace or t.startswith(namespace + "/")


def _frame_budget(ctx: DispatchCtx) -> int:
    """The budget in force for THIS request.

    Calls the peer's own accessor when it has one — that is the surface an extension is
    told to use, and reading around it into `conn.max_frame_bytes` would measure a
    different thing and would drift the day the fallback rule changes. The
    ``getattr`` guard is not defensive padding: this module is generated for a cohort,
    and a peer without the accessor must degrade to a defined number rather than raise.
    """
    accessor = getattr(ctx, "frame_budget", None)
    if callable(accessor):
        value = accessor()
        if isinstance(value, int):
            return value
    conn_budget = getattr(ctx.conn, "max_frame_bytes", None)
    if isinstance(conn_budget, int):
        return conn_budget
    return getattr(ctx, "peer_max_frame", 16 * 1024 * 1024)


def _wire_size(entity: Entity) -> int:
    """Encoded size of an entity, for frame-budget accounting.

    `typescript` reads ``entity.wireBytes.length`` — a decoded entity there retains its
    original bytes (§1.8 forward-original). `python`'s ``Entity`` carries ``type / data /
    hash`` and no wire form, so the size is computed. Re-encoding per candidate is real
    work on a large batch and is the honest cost of the substrate difference; a port that
    guessed from ``total_size`` would be wrong for every entity that is not a blob.
    """
    from entity_core import encode

    return len(encode(entity.to_cbor()))


def _key_bytes(key: Any) -> bytes:
    """The §3.1 included-map key, normalized to plain ``bytes``.

    The codec marks byte-string map keys with ``entity_core.ByteKey``, which IS a
    ``bytes`` subclass — so the first branch already covers it and the normalization is
    only so the comparison in ``_ingest`` is against a plain value. A ``str`` key here is
    a malformed envelope (core §3.1 requires major type 2) and falls through to ``b""``,
    which fails the hash comparison and produces the ``hash_mismatch`` §6.3 asks for.
    """
    if isinstance(key, (bytes, bytearray)):
        return bytes(key)
    return b""
