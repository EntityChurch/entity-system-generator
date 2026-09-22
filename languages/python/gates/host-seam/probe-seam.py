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
    -v <generator>:/gen:ro -v <keystone>:/keystone:ro -w /gen/languages/python/gates/host-seam \
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

#: A frame budget that is NOT the default and not a round number, so the value a body
#: reads back can only have come from this configuration. See `find_frame_budget`.
CONFIGURED_FRAME_BUDGET = 3_145_749  # 3 MiB + 21


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
                    "frame_budget_site": budget[0] if budget else "-",
                    "frame_budget_value": budget[1] if budget else -1,
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


def find_frame_budget(ctx: DispatchCtx, peer) -> tuple[str, int] | None:
    """Can the body consult the CONNECTION's configured frame budget, and is the number
    it gets back the CONFIGURED one? CONTENT v3.6 Amendment 1 §6.2/§4.2 makes this a
    MUST — "the connection's configured budget at response-construction time, NOT a
    hardcoded 16 MiB literal".

    **This returns the VALUE, not just the site, and that is the D15 correction.**
    The first version of this function searched for an attribute whose name matched
    `frame` and `max|limit|budget|bytes` and reported the site. It went green the day
    keystone landed the fix — correctly, as it happens — but it *could not have gone
    red* for a peer that stamped the 16 MiB constant onto every connection and named
    the field `max_frame_bytes`. The name is not the property. The property is that a
    peer configured to enforce N reports N.

    ``wire.MAX_FRAME`` is still never accepted as an answer: it is the literal the
    amendment names as the wrong one, and a probe that counted it would report the MUST
    satisfied by the exact construct it forbids.
    """
    # Prefer the peer's own accessor when it has one — that is the surface an extension
    # is told to use, and reading around it would measure a different thing.
    budget = None
    site = None
    accessor = getattr(ctx, "frame_budget", None)
    if callable(accessor):
        try:
            value = accessor()
            if isinstance(value, int):
                budget, site = value, "ctx.frame_budget()"
        except Exception:  # noqa: BLE001 - an accessor that raises is an answer too
            budget, site = None, None

    if budget is None:
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
                    value = getattr(obj, key, None)
                    if isinstance(value, int):
                        budget, site = value, f"{label}.{key}"
                        break
            if budget is not None:
                break

    return None if budget is None or site is None else (site, budget)


def negative_control() -> int:
    """**The control for the frame-budget check itself** (D15).

    A check that cannot go RED measures nothing, and the *name*-matching version of
    `find_frame_budget` could not: it reported the site and never the value, so a peer
    stamping the 16 MiB constant onto every connection and calling the field
    `max_frame_bytes` would have passed it.

    This arm builds the host with **no** budget configuration, drives the same EXECUTE,
    and asserts the body reads back `wire.MAX_FRAME` — the literal the amendment names
    as the wrong answer — and that the scoring rejects it. If this arm ever goes green,
    the positive arm is not measuring what it says.
    """
    global _FORCE_DEFAULT_BUDGET
    _FORCE_DEFAULT_BUDGET = True
    try:
        out, _ = run_once(bind_tree=True, set_handler=True)
    finally:
        _FORCE_DEFAULT_BUDGET = False

    data = out.get("data") or {}
    value = data.get("frame_budget_value", -1)
    site = data.get("frame_budget_site", "-")
    print("NEGATIVE CONTROL — peer built with no frame-budget configuration:")
    print(f"  {site} reports {value}   (wire.MAX_FRAME = {_wire.MAX_FRAME})")
    reads_default = value == _wire.MAX_FRAME
    rejected = value != CONFIGURED_FRAME_BUDGET
    print(f"  reads the peer default rather than a stale/absent value: {'yes' if reads_default else 'NO'}")
    print(f"  scoring REJECTS it as the Amendment 1 answer:            {'yes' if rejected else 'NO — the check is vacuous'}")
    return 0 if reads_default and rejected else 1


#: Set by `negative_control` only. Never a flag a normal run can reach.
_FORCE_DEFAULT_BUDGET = False


def make_host():
    """The peer under test, configured with a NON-DEFAULT frame budget where the peer
    supports one. A peer that does not take the keyword is not a failure of the peer —
    it is the honest reason the value half of the frame-budget check cannot run, and it
    is reported as `unknown` rather than skipped silently."""
    if _FORCE_DEFAULT_BUDGET:
        return Peer(SEED_HOST, open_grants=True), True
    try:
        return Peer(SEED_HOST, open_grants=True, max_frame_bytes=CONFIGURED_FRAME_BUDGET), True
    except TypeError:
        return Peer(SEED_HOST, open_grants=True), False


def run_once(*, bind_tree: bool, set_handler: bool):
    """One control. Returns (result-dict, the handler instance or None)."""
    host, _ = make_host()
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
    peer, _ = make_host()
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
    _, configurable = make_host()
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
    # Amendment 1 §6.2, scored on the VALUE. Reachability is not the property: a peer
    # that stamped `MAX_FRAME` onto every connection and named the field
    # `max_frame_bytes` would satisfy a name check while enforcing the literal the
    # amendment forbids. This asks a peer configured to enforce N what it reports.
    budget_site = data.get("frame_budget_site")
    budget_value = data.get("frame_budget_value", -1)
    if not configurable:
        budget_verdict = "unknown — this peer takes no frame-budget configuration, so the value cannot be varied"
    elif not data.get("frame_budget_reachable"):
        budget_verdict = "NO — Amendment 1 MUST unimplementable, nothing carries a budget"
    elif budget_value == CONFIGURED_FRAME_BUDGET:
        budget_verdict = f"MEASURED PASS — {budget_site} = {budget_value} (the configured value)"
    elif budget_value == _wire.MAX_FRAME:
        budget_verdict = (
            f"FAIL — {budget_site} reports {budget_value}, which is wire.MAX_FRAME. "
            f"The peer was configured for {CONFIGURED_FRAME_BUDGET}; the accessor is "
            "reporting the literal the amendment names as the wrong answer."
        )
    else:
        budget_verdict = (
            f"FAIL — {budget_site} reports {budget_value}, expected {CONFIGURED_FRAME_BUDGET}"
        )
    print(f"  CONTENT §6.2 frame budget (value, not name):  {budget_verdict}")
    print(f"     (peer configured max_frame_bytes={CONFIGURED_FRAME_BUDGET}; "
          f"wire.MAX_FRAME={_wire.MAX_FRAME} is never accepted as an answer)")

    budget_ok = (not configurable) or budget_value == CONFIGURED_FRAME_BUDGET
    print()
    control_rc = negative_control()

    ok = (
        witness_ok and negative_ok and dict_is_consulted and never_asked_ok
        and budget_ok and control_rc == 0
    )
    print(f"\n  python tier: {'A (full loop)' if ok else 'B (generate + test only)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
