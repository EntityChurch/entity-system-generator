#!/usr/bin/env python3
"""POC — does the `python` keystone peer's public surface actually dispatch to a
language-native handler body installed after construction?

The `typescript` sibling of this probe (``probe-seam.mjs``) settled H1 for that peer.
This one settles `python`'s tier, and it exists because the cycle-1 plan put python at
**tier A on a source read** — `peer.handlers` is a plain public dict consulted on the
dispatch path — which is exactly the claim D13 says is not a claim. Three source reads
by two seats passed `julia` and `csharp`; both fail this probe's class.

WHAT IS INSTALLED, AND THROUGH WHAT. Nothing here calls an underscore-prefixed name on
the peer. `python` has **no registration method at all** — no `registerHandler`, no
`register_handler`. Installation is a hand-assembled sequence of writes through
`peer.store.bind` / `peer.mint_token` / `peer.handlers`, all public. That asymmetry with
`typescript` is a result of this probe, not a workaround inside it: see §11.6.1 below,
where the "writes performed by the registration surface" table has no surface to name.

THE WITNESS. The body returns a string derived from a REQUEST field concatenated with
REGISTRATION-TIME captured state. No entity-native body can produce it: `python`'s
``_entity_native_dispatch`` evaluates ``compute/literal`` and 501s everything else, so a
literal cannot depend on a request field. If the response carries the value, the
installed callable ran.

FOUR CONTROLS, because "installed and never asked" is a distinct failure from "not
installed" and D13 requires the negative control to tell them apart:

  A. tree entities bound + `handlers[pattern]` set   -> 200 + the derived witness
  B. nothing installed at the pattern                -> non-200 (the check can go RED)
  C. tree entities bound, `handlers` NOT set         -> 501 (proves the DICT is the
                                                       consulted container, not the tree)
  D. `handlers` set, tree entities NOT bound         -> 404, and then the body is invoked
                                                       DIRECTLY in-process with its call
                                                       counter snapshotted first. Live and
                                                       reachable, and dispatch never asked
                                                       it: the Reach-layer distinction.

Read-only against keystone: nothing here writes into another team's tree.

Run (container, offline):
  podman run --rm --network=none \
    -v <generator>:/gen:ro -v <keystone>:/keystone:ro -w /gen/gates/host-seam \
    localhost/entity-core-keystone/python-toolchain:latest \
    python probe-seam.py --peer-root /keystone/protocol-generator/python
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from peer_under_test import load_peer_under_test  # noqa: E402

_STAGING = Path(tempfile.mkdtemp(prefix="probe-seam-py-"))
RESOLVED = load_peer_under_test(_STAGING)

from entity_core.peer import (  # noqa: E402
    Entity,
    Identity,
    Peer,
    dial,
    listen,
    resource_target,
    response_result,
    response_status,
)

# `Outcome` / `DispatchCtx` are what a handler body must RETURN and CONSUME. They live in
# `entity_core.peer.handlers` — a module with no leading underscore, so a third party can
# import them — but they are absent from `entity_core.peer.__all__`. Python enforces
# nothing either way; the D13 Export-layer answer for this peer is "reachable by
# convention, not declared", and the probe records which of the two it used.
from entity_core.peer.handlers import DispatchCtx, Outcome  # noqa: E402
from entity_core.peer import wire as _wire  # noqa: E402
from entity_core.peer import __all__ as PEER_ALL  # noqa: E402

PATTERN = "system/content"
REGISTRATION_NONCE = "seam-witness-7f3a"
SEED_HOST = bytes([0x51] * 32)
SEED_CLIENT = bytes([0x52] * 32)


class ReferenceHandler:
    """The reference body. A plain class with ``handle_op(op, ctx)`` — `python`'s
    dispatch idiom is duck-typed, so no peer-internal base class is inherited and no
    peer-internal type is named to declare it.

    It captures `peer` and `nonce` at CONSTRUCTION time on purpose. `python`'s
    ``DispatchCtx`` carries ``exec / conn / included / caller_cap / has_cap`` and **no
    reference to the peer** — unlike `typescript`, where ``ctx.peer.tree`` and
    ``ctx.peer.contentStore`` are reachable from the body. Store access here is
    registration-time capture, which is a fact the generator's context adapter has to
    model per language rather than assume.
    """

    def __init__(self, peer, nonce: str) -> None:
        self.peer = peer
        self.nonce = nonce
        self.calls = 0
        self.last_source = "-"

    def handle_op(self, op: str, ctx: DispatchCtx) -> Outcome:
        self.calls += 1
        self.last_source = "dispatch"
        params = ctx.exec.sub_entity("params")
        probe = (params.text("probe") if params is not None else None) or "<absent>"
        budget = find_frame_budget(ctx, self.peer)
        return Outcome.ok(
            Entity.make(
                "system/content/content-response",
                {
                    "found": [],
                    "missing": [],
                    "witness": f"{probe}:{self.nonce}",
                    "operation": op,
                    "suffix": suffix_of(ctx),
                    "resource_present": ctx.exec.field("resource") is not None,
                    "has_store": hasattr(self.peer, "store")
                    and callable(getattr(self.peer.store, "bind", None)),
                    "has_content_store": content_store_of(self.peer) is not None,
                    "has_emit": callable(
                        getattr(self.peer.store, "register_tree_consumer", None)
                    ),
                    "connection_present": ctx.conn is not None,
                    "caller_cap_present": ctx.caller_cap is not None,
                    "frame_budget_reachable": budget is not None,
                    "frame_budget_site": budget or "-",
                },
            )
        )


def suffix_of(ctx: DispatchCtx) -> str:
    """`python` does not compute a handler suffix for the body — the pattern is matched
    in ``_resolve_handler`` and the remainder is dropped. The body derives it from the
    URI itself, which is a per-language context gap worth recording rather than hiding.
    """
    uri = ctx.exec.text("uri") or ""
    marker = "/" + PATTERN
    i = uri.find(marker)
    return uri[i + len(marker) :] if i >= 0 else ""


def content_store_of(peer) -> object | None:
    """CONTENT needs a content store. `python`'s ``Store`` is one object for tree bindings
    AND content; probe for the content half by name rather than assuming a separate field.
    """
    store = getattr(peer, "store", None)
    if store is None:
        return None
    for name in ("put_content", "put_blob", "content_put", "register_content_consumer"):
        if callable(getattr(store, name, None)):
            return store
    return None


def find_frame_budget(ctx: DispatchCtx, peer) -> str | None:
    """Can the body consult the CONNECTION's configured frame budget? CONTENT v3.6
    Amendment 1 §6.2/§4.2 makes this a MUST — "the connection's configured budget at
    response-construction time, NOT a hardcoded 16 MiB literal".

    ``wire.MAX_FRAME`` is deliberately NOT accepted here. It is a module-level constant
    equal to 16 MiB, which is the literal the amendment names as the wrong answer; a
    probe that counted it would report the MUST satisfied by the exact construct it
    forbids.
    """
    for label, obj in (("ctx.conn", ctx.conn), ("ctx", ctx), ("peer", peer),
                       ("peer.store", getattr(peer, "store", None))):
        if obj is None:
            continue
        for key in dir(obj):
            if key.startswith("_"):
                continue
            if re.search(r"frame", key, re.I) and re.search(
                r"max|limit|budget|bytes", key, re.I
            ):
                return f"{label}.{key}"
    return None


def run_once(*, bind_tree: bool, set_handler: bool):
    """One control. Returns (result-dict, the handler instance or None)."""
    host = Peer(SEED_HOST, open_grants=True)
    body = ReferenceHandler(host, REGISTRATION_NONCE) if set_handler else None

    if bind_tree:
        bind_handler_entities(host, PATTERN)
    if set_handler:
        host.handlers[PATTERN] = body

    ln = listen(host, 0)
    try:
        client = Identity.of_seed(SEED_CLIENT)
        cc = dial("127.0.0.1", ln.port)
        try:
            cc.handshake(client)
            params = Entity.make("system/content/get-request", {"probe": "cycle-1"})
            env = cc.execute(
                client,
                "/" + host.local_peer + "/" + PATTERN,
                "get",
                params,
                resource_target(PATTERN),
            )
        finally:
            cc.close()
    finally:
        ln.close()

    out: dict = {"status": 0, "type": "-", "error": None, "data": None}
    if env is None:
        out["error"] = "no response envelope"
        return out, body
    out["status"] = response_status(env)
    res = response_result(env)
    if res is None:
        out["error"] = "response carried no result"
        return out, body
    out["type"] = res.type
    if res.type == "system/protocol/error":
        out["error"] = res.text("code")
    elif isinstance(res.data, dict):
        out["data"] = {
            k: (v if isinstance(v, (str, bool, int)) else type(v).__name__)
            for k, v in res.data.items()
        }
    return out, body


def bind_handler_entities(peer, pattern: str) -> None:
    """The §11.6.1 install writes — performed HERE, by the caller, because the peer
    exposes no surface that performs them. Public names only: ``peer.store.bind``,
    ``peer.mint_token``, ``peer.identity.identity_hash``, ``peer.local_peer``.

    Compare `typescript`, where ``registerHandler`` does steps 1-3 and skips the type
    entities. On `python` every step is ours, which means the generator ships an install
    adapter for this peer rather than calling one.
    """
    local = peer.local_peer

    def absp(rel: str) -> str:
        return "/" + local + "/" + rel

    # (1) handler manifest at the pattern path — this is what `_resolve_handler` finds.
    peer.store.bind(
        absp(pattern),
        Entity.make("system/handler", {"interface": "system/handler/" + pattern}),
    )
    # (2) handler interface entity (discovery index).
    peer.store.bind(
        absp("system/handler/" + pattern),
        Entity.make(
            "system/handler/interface",
            {
                "pattern": pattern,
                "name": "content",
                "operations": {
                    "get": {
                        "input_type": "system/content/get-request",
                        "output_type": "system/content/content-response",
                    },
                    "ingest": {"input_type": "system/content/ingest-request"},
                },
            },
        ),
    )
    # (3) self-issued signed handler grant.
    token, sig = peer.mint_token(peer.identity.identity_hash, [], None)
    peer.store.bind(absp("system/capability/grants/" + pattern), token)
    peer.store.bind(absp("system/signature/" + token.hash.hex()), sig)


def inspect_install_writes() -> dict:
    """What did the install actually put in the tree? In-process, so the probe reports
    WHAT the seam did rather than only that it worked.
    """
    peer = Peer(SEED_HOST, open_grants=True)
    local = peer.local_peer

    def bound(rel: str) -> bool:
        return peer.store.get_at("/" + local + "/" + rel) is not None

    before = bound(PATTERN)
    bind_handler_entities(peer, PATTERN)
    peer.handlers[PATTERN] = ReferenceHandler(peer, REGISTRATION_NONCE)
    return {
        "_before_handler_entity": before,
        "handler_entity": bound(PATTERN),
        "interface_entity": bound("system/handler/" + PATTERN),
        "grant": bound("system/capability/grants/" + PATTERN),
        "type_blob": bound("system/type/system/content/blob"),
        "type_chunk": bound("system/type/system/content/chunk"),
        "type_descriptor": bound("system/type/system/content/descriptor"),
        "handlers_dict_entry": PATTERN in peer.handlers,
    }


def main() -> int:
    print(f"peer package: {RESOLVED.dist_name} {RESOLVED.version}")
    print(f"peer root:    {RESOLVED.peer_root}")
    print(f"resolved via: {RESOLVED.how_resolved}")
    import entity_core

    staged_ok = str(Path(entity_core.__file__).resolve()).startswith(
        str(RESOLVED.staged_root)
    )
    print(f"imported from staged copy: {'yes' if staged_ok else 'NO — path leak'}")
    print(f"python: {sys.version.split()[0]}\n")

    print("Export layer — can a third party name what the body must return/consume?")
    for name in ("Outcome", "DispatchCtx"):
        declared = name in PEER_ALL
        print(
            f"  {name:<12} importable from entity_core.peer.handlers: yes   "
            f"declared in entity_core.peer.__all__: {'yes' if declared else 'NO'}"
        )
    print(
        "  -> reachable by convention, not by declaration. Python enforces neither;\n"
        "     recorded as the Export-layer answer rather than scored pass/fail."
    )

    print("\n§11.6.1 writes — performed by the CALLER (this peer exposes no "
          "registration surface):")
    writes = inspect_install_writes()
    for k, v in writes.items():
        if k.startswith("_"):
            continue
        print(f"  {'yes' if v else 'NO '}  {k}")

    print("\nControl A — tree bound + handlers dict set (the full install):")
    a, _ = run_once(bind_tree=True, set_handler=True)
    print(f"  status={a['status']} type={a['type']} error={a['error'] or '-'}")
    if a["data"]:
        for k, v in a["data"].items():
            print(f"    {k} = {v}")

    print("\nControl B — nothing installed at the pattern (must go RED):")
    b, _ = run_once(bind_tree=False, set_handler=False)
    print(f"  status={b['status']} type={b['type']} error={b['error'] or '-'}")

    print("\nControl C — tree bound, handlers dict NOT set:")
    c, _ = run_once(bind_tree=True, set_handler=False)
    print(f"  status={c['status']} type={c['type']} error={c['error'] or '-'}")

    print("\nControl D — handlers dict set, tree NOT bound:")
    d, d_body = run_once(bind_tree=False, set_handler=True)
    calls_after_dispatch = d_body.calls
    # Snapshot BEFORE the direct call — the counter is the whole discrimination.
    direct = d_body.handle_op(
        "get",
        DispatchCtx(
            exec=Entity.make(
                "system/protocol/execute",
                {
                    "request_id": "direct-1",
                    "uri": "/local/" + PATTERN,
                    "operation": "get",
                    "params": Entity.make(
                        "system/content/get-request", {"probe": "direct"}
                    ).to_cbor(),
                },
            ),
            conn=None,
            included={},
        ),
    )
    d_body.last_source = "direct"
    direct_ok = direct.status == 200 and direct.result.field("witness") == (
        f"direct:{REGISTRATION_NONCE}"
    )
    print(f"  status={d['status']} type={d['type']} error={d['error'] or '-'}")
    print(f"  body invocations attributable to dispatch: {calls_after_dispatch}")
    print(
        f"  same body invoked directly in-process:      "
        f"{'200 + witness' if direct_ok else 'FAILED — body is not live'}"
    )

    witness_ok = a["status"] == 200 and (a["data"] or {}).get("witness") == (
        f"cycle-1:{REGISTRATION_NONCE}"
    )
    negative_ok = b["status"] != 200
    dict_is_consulted = c["status"] != 200
    never_asked_ok = calls_after_dispatch == 0 and direct_ok and d["status"] != 200

    print("\nVERDICT")
    print(f"  H1 (installed body reached by dispatch):       "
          f"{'MEASURED PASS' if witness_ok else 'FAIL'}")
    print(f"  negative control discriminates:                "
          f"{'yes' if negative_ok else 'NO — check is vacuous'}")
    print(f"  handlers dict is the consulted container:      "
          f"{'yes (C fell through)' if dict_is_consulted else 'NO — C answered 200'}")
    print(f"  'installed and never asked' distinguished:     "
          f"{'yes' if never_asked_ok else 'NO — Reach layer unproven'}")
    data = a["data"] or {}
    print(f"  emit hook reachable from the body:             "
          f"{'yes' if data.get('has_emit') else 'no'}")
    print(f"  store + content store reachable from the body: "
          f"{'yes' if data.get('has_store') and data.get('has_content_store') else 'no'}"
          f"  (via registration-time capture; ctx carries no peer)")
    print(f"  CONTENT §6.2 frame budget reachable:           "
          f"{data.get('frame_budget_site') if data.get('frame_budget_reachable') else 'NO — Amendment 1 MUST unimplementable'}")
    print(f"     (wire.MAX_FRAME = {_wire.MAX_FRAME} is a module constant — the literal "
          f"the amendment names as the wrong answer, so it is not counted)")

    ok = witness_ok and negative_ok and dict_is_consulted and never_asked_ok
    print(f"\n  python tier: {'A (full loop)' if ok else 'B (generate + test only)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
