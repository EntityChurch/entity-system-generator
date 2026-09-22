"""§3.3 and §7 — the clauses the oracle's ``compute`` category cannot reach.

**THIS FILE EXISTS BECAUSE OF WHAT THE REACTIVE CHECKS MEASURE, NOT BECAUSE THEY FAILED.**
``validate-peer``'s reactive family is a wire client: it writes a dependency, reads a result
path and compares a number. Every check in it is an assertion about a value that APPEARED.
Several of §7's normative clauses are assertions about something that did NOT happen, or about
a value no wire read can see:

======================  ==========================================  ==============================
clause                  what it asserts                             why the wire cannot see it
======================  ==========================================  ==============================
§7.2 convergence        a re-evaluation producing the same hash      the value at ``result_path``
                        writes **nothing**                          is right either way
§7.3 cascade bound      a runaway cascade **freezes** rather than    a peer that recursed would
                        recursing                                    be down, not wrong
§7.2 grant validity     an expired grant freezes with               no vector expires a grant
                        ``installation_grant_invalid``               mid-run
§3.3 Phase 3            the caller's capability ENTITY reaches the   install answers 200 without
                        content store                                it; the FIRST re-evaluation
                                                                     is what breaks
§3.3 deterministic_id   the id is cross-peer identical               nothing reads
                                                                     ``subgraph_path`` back
======================  ==========================================  ==============================

That list is this port's honest answer to *"which rows are ours"* in
``EXTENSION.toml [conformance]``, and it is the only part of §7 where we are both the
implementer and the instrument. Where a reference vector exists it is used instead of our own
reading — see the ``deterministic_id`` test, whose expectations are `entity-core-go`'s output
and not ours (L18: a second reading of the same prose by the same team is not evidence).
"""

from __future__ import annotations

import pytest
from entity_core.peer import Entity, GrantSpec, Peer
from entity_core.peer.handlers import DispatchCtx
from entity_core.peer.wire import empty_params, make_execute, resource_target

from entity_compute import (
    ARITHMETIC,
    ERROR,
    LET,
    LITERAL,
    LOOKUP_SCOPE,
    LOOKUP_TREE,
    PROCESSES_PREFIX,
    RESULT,
    SUBGRAPH,
    ComputeHandler,
    ReactiveEngine,
    deterministic_id,
    install_compute,
)
from entity_compute.sdk import DEFAULT_LIMITS

SEED = bytes([0x22] * 32)


def peer() -> Peer:
    """A live peer with COMPUTE not yet installed. Tests that need the composition call
    :func:`install_compute` themselves, so the BEFORE state is available to assert against —
    which is what makes the negative halves below possible."""
    return Peer(SEED, open_grants=True)


def put(p: Peer, e: Entity) -> bytes:
    p.store.put_entity(e)
    return e.hash


def literal(p: Peer, value) -> bytes:
    return put(p, Entity.make(LITERAL, {"value": value}))


def abs_path(p: Peer, rel: str) -> str:
    return "/" + p.local_peer + "/" + rel


# ── §3.3 `deterministic_id` ─────────────────────────────────────────────────────


def test_deterministic_id_agrees_with_the_reference_implementation_vector_for_vector():
    """**THE EXPECTATIONS ARE `entity-core-go`'s OUTPUT, NOT OUR READING.**

    §3.3 makes this derivation normative for a reason it states plainly: *"a subgraph installed
    by Peer A at root path ``app/cell/A1`` is discoverable at the same
    ``system/compute/processes/{subgraph_id}`` on ANY peer"*. It is therefore a cross-peer
    identity, and no check in ``validate-peer`` reads ``subgraph_path`` back — so two
    implementations could disagree about it forever and every conformance run would stay green.

    These four strings were produced by running ``deterministicID`` out of
    ``entity-core-go/ext/compute/engine.go`` on 2026-09-10 — a different codebase, a different
    base32 library and a different author. They are carried in the `typescript` port's suite
    too, which makes this the one place in the corpus where three implementations of one
    encoding are pinned to the same bytes.

    **And on this port the encoding is the STDLIB's, not a hand-rolled 5-bit loop.**
    `typescript` writes the encoder out; here ``base64.b32encode`` plus ``lower()`` plus
    ``rstrip("=")`` is the same function. Two implementations of one encoding is two places for
    it to differ, so the vectors are the only thing that makes the shortcut safe.
    """
    reference = {
        "/peer/app/cell/A1": "ffb4c3uopfuogfzn35cv7wdmsgf74ubjlpntxey64wr4dh6fgqoq",
        "app/cell/A1": "mijknkgplgoibnth6mdfl3kerwp22d7w73jqfae4dtrw7xzz6gra",
        "": "4oymiquy7qobjgx36tejs35zeqt24qpemsnzgtfeswmrw6csxbkq",
        "a": "zklycewkdo64v6wcggzzui64jwtyn37ycr6e44vzqb3yll7ojc5q",
    }
    for path, expected in reference.items():
        assert deterministic_id(path) == expected, f"deterministic_id({path!r})"
    # §3.3: *"The result is a 52-character string"* — stated normatively because a padded or
    # truncated encoding still round-trips locally. `b32encode` pads to 56 with four `=`.
    for path in reference:
        assert len(deterministic_id(path)) == 52
    for path in reference:
        assert "=" not in deterministic_id(path)


def test_deterministic_id_THE_NEGATIVE_different_paths_give_different_ids():
    """A constant function passes every equality assertion above if the vectors were ours. They
    are not, but the guard costs one line and it is the assertion that would survive a future
    re-pin replacing the vectors."""
    ids = {deterministic_id(p) for p in ("a", "b", "app/x", "app/y", "")}
    assert len(ids) == 5


# ── §7.1 — the dependency walk ──────────────────────────────────────────────────


def test_every_reachable_lookup_tree_is_registered_container_or_not():
    """§7.1 ``[MUST, v3.27]`` — and A-17 is the reason this is one walker.

    §3.3's ``audit_walk`` descends only scalar ``system/hash`` fields; §7.1's descends
    containers. The three dependencies below are at three different depths: one at the top
    level, one inside a ``let`` BINDING (an array of maps), one inside an ``apply.args`` map. A
    transcription of §3.3's listing registers the first and misses the other two — and because
    the same walk builds the list Phase 2 capability-checks, it also AUTHORIZES the first and
    skips the other two, which is an authorization hole rather than a coverage one.
    """
    p = peer()
    for rel in ("app/a", "app/b", "app/c"):
        p.store.bind(abs_path(p, rel), Entity.make("app/cell", {"v": 1}))

    top = put(p, Entity.make(LOOKUP_TREE, {"path": "app/a"}))
    in_binding = put(p, Entity.make(LOOKUP_TREE, {"path": "app/b"}))
    in_args = put(p, Entity.make(LOOKUP_TREE, {"path": "app/c"}))

    # \x -> x, applied with `app/c`'s lookup as the argument.
    body = put(p, Entity.make(LOOKUP_SCOPE, {"name": "x"}))
    lam = put(p, Entity.make("compute/lambda", {"params": ["x"], "body": body}))
    call = put(p, Entity.make("compute/apply", {"fn": lam, "args": {"x": in_args}}))

    sum_node = put(p, Entity.make(ARITHMETIC, {"op": "add", "left": top, "right": call}))
    root = Entity.make(LET, {
        "bindings": [{"name": "unused", "value": in_binding}],
        "body": sum_node,
    })
    p.store.bind(abs_path(p, "app/expr"), root)

    from entity_compute._internal.subgraph import AuditContext, audit_subgraph

    audit = audit_subgraph(
        root,
        abs_path(p, "app/expr"),
        AuditContext(store=p.store, local_peer=p.local_peer, included={}, author=None),
    )
    assert set(audit.read_paths) == {
        abs_path(p, "app/a"), abs_path(p, "app/b"), abs_path(p, "app/c")
    }


def test_THE_NEGATIVE_a_lookup_scope_is_not_a_tree_dependency():
    """A walker that treated every 33-byte value as a reference, or every lookup as a tree
    lookup, would pass the test above and register paths that do not exist. Both shapes are
    here: a ``lookup/scope`` (a lookup that is not a TREE lookup) and a ``compute/literal``
    whose value happens to be 33 bytes long (§3.3's *"skip hash references that resolve to
    non-compute entities"*, and the shape CP1's adversarial vector arrives in)."""
    p = peer()
    scope_ref = put(p, Entity.make(LOOKUP_SCOPE, {"name": "x"}))
    decoy = put(p, Entity.make(LITERAL, {"value": bytes([0x00]) + bytes(32)}))
    root = Entity.make(ARITHMETIC, {"op": "add", "left": scope_ref, "right": decoy})

    from entity_compute._internal.subgraph import AuditContext, audit_subgraph

    audit = audit_subgraph(
        root,
        abs_path(p, "app/expr"),
        AuditContext(store=p.store, local_peer=p.local_peer, included={}, author=None),
    )
    assert audit.read_paths == ()


def test_the_dependency_index_is_EXACT_MATCH_not_prefix():
    """§7.1 says so twice. A write at ``app/data/sheet1/cells/A1`` does NOT wake an expression
    depending on ``app/data/sheet1``. A prefix index makes more programs appear to work and is
    wrong: §7.1 names the three compositions an application uses instead, precisely so compute
    needs no subtree primitive."""
    p = peer()
    engine = ReactiveEngine(p, DEFAULT_LIMITS)
    from entity_compute._internal.subgraph import SubgraphAudit

    engine.register("sg", abs_path(p, "app/expr"),
                    SubgraphAudit(read_paths=(abs_path(p, "app/data/sheet1"),)))
    assert engine.registered_dependencies == 1
    # The deeper path matches nothing, so nothing is woken and no error is raised.
    engine.on_tree_change(_event(abs_path(p, "app/data/sheet1/cells/A1")))
    # And the exact path DOES match — the control, without which the line above proves only
    # that the engine is inert.
    assert engine.watched_paths == (abs_path(p, "app/data/sheet1"),)


class _Event:
    __slots__ = ("path", "event_type", "new_hash", "previous_hash", "context")

    def __init__(self, path: str, context=None) -> None:
        self.path = path
        self.event_type = "modified"
        self.new_hash = ""
        self.previous_hash = ""
        self.context = context


def _event(path: str, context=None) -> _Event:
    return _Event(path, context)


# ── §7.2 — the trigger, end to end, through the real bus ────────────────────────


def _install_a_spreadsheet(p: Peer, *, result_path: str | None = None):
    """Install `A1 * 2` as a reactive subgraph and return (installation, subgraph_path).

    Goes through the HANDLER rather than through the engine directly, because the thing under
    test in the tests below is the composition — the handler's four phases, the engine's
    registration, and the peer's own emit bus wiring them together. Driving the engine directly
    would measure a unit and report it as the system.
    """
    installation = install_compute(p)
    p.store.bind(abs_path(p, "app/A1"), Entity.make("app/cell", {"value": 21}))

    cell = put(p, Entity.make(LOOKUP_TREE, {"path": "app/A1"}))
    field = put(p, Entity.make("compute/field", {"name": "value", "entity": cell}))
    expr = Entity.make(ARITHMETIC, {"op": "mul", "left": field, "right": literal(p, 2)})
    p.store.bind(abs_path(p, "app/B1"), expr)

    token, _ = p.mint_token(p.identity.identity_hash, [GrantSpec(["*"], ["*"], ["*"]).to_cbor()], None)
    params = Entity.make("system/compute/install-request", {})
    if result_path is not None:
        params = Entity.make("system/compute/install-request", {"result_path": result_path})
    exec_e = make_execute(
        "r1", abs_path(p, "system/compute"), "install", params,
        author=p.identity.identity_hash, capability=token.hash,
        resource=resource_target(abs_path(p, "app/B1")),
    )
    ctx = DispatchCtx(
        exec=exec_e, conn=None, included={token.hash.hex(): token},
        caller_cap=token, has_cap=True, handler_pattern="system/compute",
    )
    handler = p.handlers["system/compute"]
    outcome = handler.handle_op("install", ctx)
    assert outcome.status == 200, outcome.result.data
    return installation, outcome.result.text("subgraph_path"), outcome.result.text("result_path")


def test_install_registers_a_dependency_and_performs_the_initial_evaluation():
    """§3.3 Phase 4 plus its re-installation SHOULD, which this port performs on EVERY install.

    A ``result_path`` that is absent until the first dependency changes is a second state for
    every downstream reader to handle, and performing the initial evaluation is also what clears
    a ``compute/error`` left by a frozen predecessor.
    """
    p = peer()
    installation, subgraph_path, result_path = _install_a_spreadsheet(p)
    assert subgraph_path.startswith(abs_path(p, PROCESSES_PREFIX) + "/")
    assert subgraph_path.endswith(deterministic_id(abs_path(p, "app/B1")))
    assert installation.engine.registered_dependencies == 1

    result = p.store.get_at(result_path)
    assert result is not None and result.type == RESULT
    assert result.field("value") == 42


def test_a_dependency_write_re_evaluates_SYNCHRONOUSLY_before_the_put_returns():
    """§7.2's trigger, and the substrate property the whole family rests on.

    ``Store.bind`` snapshots the consumer list under its lock, releases it, then calls every
    consumer BEFORE returning. So the assertion below — read the result immediately after the
    write, with no wait — is the measurement of *"delivery is sync-inline"*. An async bus makes
    every §7.2 vector a race, and §7.2 pins no delivery mode (§9.4 leaves it impl-defined).
    """
    p = peer()
    _, _, result_path = _install_a_spreadsheet(p)
    p.store.bind(abs_path(p, "app/A1"), Entity.make("app/cell", {"value": 25}))
    result = p.store.get_at(result_path)
    assert result is not None and result.field("value") == 50


def test_a_write_from_inside_a_consumer_RE_ENTERS_the_bus_and_a_chain_cascades():
    """§7.2's *"subgraph A's result write notifies the emit pipeline, which triggers subgraph
    B"* — the property that makes a cascade a cascade, measured rather than assumed.

    B1 = A1.value * 2; C1 = B1.value + 1. Writing A1 must move C1, which can only happen if
    B1's own result write re-enters the bus.
    """
    p = peer()
    _, _, b1_result = _install_a_spreadsheet(p)

    # C1 depends on B1's RESULT path, which is where the engine writes.
    b1 = put(p, Entity.make(LOOKUP_TREE, {"path": b1_result}))
    b1_value = put(p, Entity.make("compute/field", {"name": "value", "entity": b1}))
    c1_expr = Entity.make(ARITHMETIC, {"op": "add", "left": b1_value, "right": literal(p, 1)})
    p.store.bind(abs_path(p, "app/C1"), c1_expr)

    token, _ = p.mint_token(p.identity.identity_hash, [GrantSpec(["*"], ["*"], ["*"]).to_cbor()], None)
    exec_e = make_execute(
        "r2", abs_path(p, "system/compute"), "install",
        Entity.make("system/compute/install-request", {}),
        author=p.identity.identity_hash, capability=token.hash,
        resource=resource_target(abs_path(p, "app/C1")),
    )
    ctx = DispatchCtx(exec=exec_e, conn=None, included={token.hash.hex(): token},
                      caller_cap=token, has_cap=True, handler_pattern="system/compute")
    out = p.handlers["system/compute"].handle_op("install", ctx)
    assert out.status == 200, out.result.data
    c1_result = out.result.text("result_path")
    assert p.store.get_at(c1_result).field("value") == 43

    p.store.bind(abs_path(p, "app/A1"), Entity.make("app/cell", {"value": 100}))
    assert p.store.get_at(b1_result).field("value") == 200
    assert p.store.get_at(c1_result).field("value") == 201


def test_convergence_OUR_check_decides_not_to_write_and_a_changed_result_still_writes():
    """§7.2's convergence check — **and this test is D15's sharpened clause, applied.**

    ``AP-33``: an earlier `typescript` version of this test asserted the two things a CONSUMER
    can see — the result hash did not move, no bind event fired — and PASSED with the clause's
    implementation removed, because ``Store.bind``'s own ``changed = prev != nxt`` guard
    produces the same reading. The instrument was fine; the property was not ours.

    So the assertion here is ``_re_evaluate``'s own RETURN VALUE: None on convergence, a hash
    otherwise. Nothing in the substrate can produce that on our behalf. The layer that owns the
    observable today is the peer, which is a fact about the peer and is recorded as
    ``[substrate].tree_put_suppresses_identical_bind`` — it stops being true at the next port.
    """
    p = peer()
    installation, subgraph_path, result_path = _install_a_spreadsheet(p)
    engine = installation.engine
    before = p.store.hash_at(result_path)

    # Re-evaluating an unchanged subgraph converges: the SUBJECT returns None.
    assert engine.evaluate_now(subgraph_path, None) is None
    assert p.store.hash_at(result_path) == before

    # THE CONTROL: change the dependency and the same call returns a hash.
    p.store.bind(abs_path(p, "app/A1"), Entity.make("app/cell", {"value": 5}))
    moved = p.store.hash_at(result_path)
    assert moved != before
    assert p.store.get_at(result_path).field("value") == 10


def test_a_missing_installation_grant_freezes_the_subgraph():
    """§7.2 + §3.3 Phase 3's clause an implementation drops: the caller's capability ENTITY must
    reach the content store before its hash is recorded.

    The grant is only in the envelope for the length of the EXECUTE; §7.2 fetches it by hash on
    every re-evaluation. Install answers 200 either way — the FIRST re-evaluation is what
    breaks — which is why no wire vector can see this.
    """
    p = peer()
    installation, subgraph_path, result_path = _install_a_spreadsheet(p)
    subgraph = p.store.get_at(subgraph_path)

    # Rewrite the metadata to name a grant nothing can resolve. Everything else is untouched.
    data = dict(subgraph.data)
    data["installation_grant"] = bytes([0x00]) + bytes(32)
    p.store.bind(subgraph_path, Entity.make(SUBGRAPH, data))

    p.store.bind(abs_path(p, "app/A1"), Entity.make("app/cell", {"value": 9}))

    frozen = p.store.get_at(subgraph_path)
    assert frozen.text("status") == "frozen"
    err = p.store.get_at(result_path)
    assert err.type == ERROR and err.data == {"code": "installation_grant_invalid"}


def test_THE_NEGATIVE_a_valid_grant_does_not_freeze():
    """The control for the test above. Without it, a port that froze on every re-evaluation
    passes it."""
    p = peer()
    _, subgraph_path, result_path = _install_a_spreadsheet(p)
    p.store.bind(abs_path(p, "app/A1"), Entity.make("app/cell", {"value": 9}))
    assert p.store.get_at(subgraph_path).text("status") == "active"
    assert p.store.get_at(result_path).type == RESULT


def test_an_EXPIRED_grant_freezes_with_installation_grant_invalid():
    """§7.2's ``is_expired`` — ``expires_at`` against the peer clock. No oracle vector expires a
    grant mid-run, so this clause is ours by construction."""
    p = peer()
    _, subgraph_path, result_path = _install_a_spreadsheet(p)
    subgraph = p.store.get_at(subgraph_path)
    expired, _ = p.mint_token(
        p.identity.identity_hash,
        [GrantSpec(["*"], ["*"], ["*"]).to_cbor()],
        None,
        created_at=1,
        expires_at=2,
    )
    p.store.put_entity(expired)
    data = dict(subgraph.data)
    data["installation_grant"] = expired.hash
    p.store.bind(subgraph_path, Entity.make(SUBGRAPH, data))

    p.store.bind(abs_path(p, "app/A1"), Entity.make("app/cell", {"value": 9}))
    assert p.store.get_at(subgraph_path).text("status") == "frozen"
    assert p.store.get_at(result_path).data == {"code": "installation_grant_invalid"}


def test_a_self_feeding_cascade_terminates_in_a_frozen_subgraph_not_a_stack():
    """§7.3 ``[MUST]`` — *"this cascade MUST be bounded"*.

    **On a sync-inline bus an unbounded cascade is unbounded RECURSION**, so a peer without a
    bound would raise ``RecursionError`` rather than loop — and a peer that is down is not
    wrong in a way any wire check can score. The subgraph's own result path is also one of its
    dependencies, so every evaluation triggers the next.

    Two bounds are live and this test does not try to attribute the freeze to one of them: the
    spec's ``cascade_depth`` on the execution context, and our re-entrancy counter. `typescript`
    measured all three arms (either alone holds; both disabled dies); here the assertion is the
    OUTCOME, because the attribution is already recorded and re-deriving it per port is not what
    this test is for.

    **THE EXPRESSION MUST BE STRICTLY INCREASING, AND THE FIRST DRAFT OF THIS TEST WAS NOT.**
    It read ``seed.value + own_result.value`` against a result path that did not exist yet, so
    round one produced ``not_found``, round two wrote the SAME error entity, and
    ``Store.bind``'s ``changed = prev != nxt`` guard suppressed the event — the cascade
    terminated after two steps, ACTIVE, and the test failed asserting ``frozen``. The port was
    right and the instrument was wrong.

    That is AP-33 a third time, in the same session, from the other side: the peer's
    identical-bind suppression can end a cascade that §7.3's bound was supposed to end, so a
    cascade test whose value CONVERGES is not testing the bound at all. The result path is
    pre-seeded and the expression adds 1 to its own previous value, exactly as the `typescript`
    test does, so the convergence check can never stop it. Only the bound can.
    """
    p = peer()
    installation = install_compute(p)

    root_rel = "app/loop"
    result_path = abs_path(p, "app/loop-result")
    # add(field("value", lookup(result)), 1) — strictly increasing, never converges.
    own = put(p, Entity.make(LOOKUP_TREE, {"path": result_path}))
    own_value = put(p, Entity.make("compute/field", {"name": "value", "entity": own}))
    expr = Entity.make(ARITHMETIC, {"op": "add", "left": own_value, "right": literal(p, 1)})
    p.store.bind(abs_path(p, root_rel), expr)
    # Pre-seeded so round one produces a VALUE rather than a `not_found` that then converges.
    p.store.bind(result_path, Entity.make(RESULT, {"value": 0}))

    token, _ = p.mint_token(p.identity.identity_hash, [GrantSpec(["*"], ["*"], ["*"]).to_cbor()], None)
    exec_e = make_execute(
        "r3", abs_path(p, "system/compute"), "install",
        Entity.make("system/compute/install-request", {"result_path": result_path}),
        author=p.identity.identity_hash, capability=token.hash,
        resource=resource_target(abs_path(p, root_rel)),
    )
    ctx = DispatchCtx(exec=exec_e, conn=None, included={token.hash.hex(): token},
                      caller_cap=token, has_cap=True, handler_pattern="system/compute")
    # §3.3's initial evaluation runs inside this call, and it is already the trigger: the result
    # write re-enters the bus against the subgraph's own dependency. If the bound were missing
    # this line would not return.
    out = p.handlers["system/compute"].handle_op("install", ctx)
    assert out.status == 200, out.result.data
    subgraph_path = out.result.text("subgraph_path")

    frozen = p.store.get_at(subgraph_path)
    assert frozen.text("status") == "frozen"
    assert p.store.get_at(result_path).data == {"code": "cascade_limit"}
    assert installation.engine is not None


def test_THE_NEGATIVE_a_CONVERGING_self_reference_does_not_freeze():
    """The control for the test above, and it is the assertion that first draft actually made.

    A self-referencing subgraph whose value CONVERGES terminates without the bound firing — so
    a cascade test written over a converging expression reports "bounded" for a peer with no
    bound at all. Keeping both means the freeze above is attributable to §7.3 and not to the
    substrate's identical-bind suppression.
    """
    p = peer()
    install_compute(p)
    root_rel = "app/fixed"
    result_path = abs_path(p, "app/fixed-result")
    own = put(p, Entity.make(LOOKUP_TREE, {"path": result_path}))
    own_value = put(p, Entity.make("compute/field", {"name": "value", "entity": own}))
    # add(own.value, 0) — a fixed point. Round two writes the same bytes and the bus goes quiet.
    expr = Entity.make(ARITHMETIC, {"op": "add", "left": own_value, "right": literal(p, 0)})
    p.store.bind(abs_path(p, root_rel), expr)
    p.store.bind(result_path, Entity.make(RESULT, {"value": 7}))

    token, _ = p.mint_token(p.identity.identity_hash, [GrantSpec(["*"], ["*"], ["*"]).to_cbor()], None)
    exec_e = make_execute(
        "r3b", abs_path(p, "system/compute"), "install",
        Entity.make("system/compute/install-request", {"result_path": result_path}),
        author=p.identity.identity_hash, capability=token.hash,
        resource=resource_target(abs_path(p, root_rel)),
    )
    ctx = DispatchCtx(exec=exec_e, conn=None, included={token.hash.hex(): token},
                      caller_cap=token, has_cap=True, handler_pattern="system/compute")
    out = p.handlers["system/compute"].handle_op("install", ctx)
    assert out.status == 200, out.result.data
    assert p.store.get_at(out.result.text("subgraph_path")).text("status") == "active"
    assert p.store.get_at(result_path).field("value") == 7


def test_a_frozen_subgraph_is_skipped_rather_than_re_evaluated():
    """§7.2 — recovery is re-installation (§3.3) and nothing else clears a freeze, because both
    conditions that produce one are structural and retrying changes nothing."""
    p = peer()
    _, subgraph_path, result_path = _install_a_spreadsheet(p)
    subgraph = p.store.get_at(subgraph_path)
    data = dict(subgraph.data)
    data["status"] = "frozen"
    p.store.bind(subgraph_path, Entity.make(SUBGRAPH, data))
    frozen_result = p.store.hash_at(result_path)

    p.store.bind(abs_path(p, "app/A1"), Entity.make("app/cell", {"value": 999}))
    assert p.store.hash_at(result_path) == frozen_result


# ── §7.1 rebuild ────────────────────────────────────────────────────────────────


def test_rebuild_re_registers_from_the_metadata_on_disk():
    """§7.1's ``rebuild_dependency_index``, which §7.1 MUSTs and which is the one path that
    reads the metadata back rather than trusting what install put in memory.

    Vacuous on a fresh peer and not vacuous here: the index is cleared out from under the engine
    and rebuilt from ``system/compute/processes/*``.
    """
    p = peer()
    installation, subgraph_path, _ = _install_a_spreadsheet(p)
    engine = installation.engine
    assert engine.registered_dependencies == 1

    engine.unregister(subgraph_path)
    assert engine.registered_dependencies == 0

    assert engine.rebuild() == 1
    assert engine.registered_dependencies == 1


def test_rebuild_reads_the_CURRENT_expression_not_the_hash_recorded_at_install():
    """§7.1 — ``root_expression`` is the audit RECORD; the expression at the tree path may have
    been modified since, and the per-operation checks catch an unauthorized one at evaluation
    time. A rebuild keyed on the recorded hash would register the old dependency set."""
    p = peer()
    installation, subgraph_path, _ = _install_a_spreadsheet(p)
    engine = installation.engine

    p.store.bind(abs_path(p, "app/A2"), Entity.make("app/cell", {"value": 1}))
    new_cell = put(p, Entity.make(LOOKUP_TREE, {"path": "app/A2"}))
    new_field = put(p, Entity.make("compute/field", {"name": "value", "entity": new_cell}))
    p.store.bind(
        abs_path(p, "app/B1"),
        Entity.make(ARITHMETIC, {"op": "mul", "left": new_field, "right": literal(p, 3)}),
    )

    engine.unregister(subgraph_path)
    engine.rebuild()
    assert engine.watched_paths == (abs_path(p, "app/A2"),)


# ── §3.4 uninstall ──────────────────────────────────────────────────────────────


def test_uninstall_clears_the_registrations_and_leaves_the_expression_in_the_tree():
    """§3.4 in one line: the expression entities are NOT deleted, they remain as inert data.
    Uninstall withdraws the installation grant's standing authorization; it does not withdraw
    the program."""
    p = peer()
    installation, subgraph_path, result_path = _install_a_spreadsheet(p)
    token, _ = p.mint_token(p.identity.identity_hash, [GrantSpec(["*"], ["*"], ["*"]).to_cbor()], None)
    exec_e = make_execute(
        "r4", abs_path(p, "system/compute"), "uninstall", empty_params(),
        author=p.identity.identity_hash, capability=token.hash,
        resource=resource_target(subgraph_path),
    )
    ctx = DispatchCtx(exec=exec_e, conn=None, included={token.hash.hex(): token},
                      caller_cap=token, has_cap=True, handler_pattern="system/compute")
    out = p.handlers["system/compute"].handle_op("uninstall", ctx)
    assert out.status == 200

    assert p.store.get_at(subgraph_path) is None
    assert installation.engine.registered_dependencies == 0
    assert p.store.get_at(abs_path(p, "app/B1")) is not None

    # And a dependency write now wakes nothing.
    before = p.store.hash_at(result_path)
    p.store.bind(abs_path(p, "app/A1"), Entity.make("app/cell", {"value": 77}))
    assert p.store.hash_at(result_path) == before


def test_uninstall_on_a_path_that_is_not_a_subgraph_is_404():
    p = peer()
    install_compute(p)
    token, _ = p.mint_token(p.identity.identity_hash, [GrantSpec(["*"], ["*"], ["*"]).to_cbor()], None)
    exec_e = make_execute(
        "r5", abs_path(p, "system/compute"), "uninstall", empty_params(),
        author=p.identity.identity_hash, capability=token.hash,
        resource=resource_target(abs_path(p, "app/nothing")),
    )
    ctx = DispatchCtx(exec=exec_e, conn=None, included={token.hash.hex(): token},
                      caller_cap=token, has_cap=True, handler_pattern="system/compute")
    out = p.handlers["system/compute"].handle_op("uninstall", ctx)
    assert out.status == 404


# ── §6.2 — the handler hands the CALLER's capability to the evaluator ───────────


def test_the_handler_narrows_the_tree_read_with_the_CALLERS_capability():
    """§6.2 PER TREE READ, and this is the assertion the `typescript` port's contract once
    denied was possible.

    That contract said the peer exposed no path-scope predicate an extension could call, so §6.2
    was satisfied at the dispatch boundary and a caller reaching ``system/compute:eval`` could
    read any path. The predicate is ``check_path_permission``, it is public ON THIS PEER, and
    **this repo is the seat that routed it** — keystone H9, landed, recorded CLOSED on our own
    tracker (AP-34). It exists here because we asked for it.

    The grant below covers ``app/allowed`` and not ``app/denied``, and the two halves are
    asserted together because a peer running the wide-open grant policy cannot distinguish a
    real check from ``return True``.
    """
    p = peer()
    install_compute(p)
    for rel in ("app/allowed", "app/denied"):
        p.store.bind(abs_path(p, rel), Entity.make("app/cell", {"value": 1}))

    narrow, _ = p.mint_token(
        p.identity.identity_hash,
        [GrantSpec(["*"], ["app/allowed"], ["*"]).to_cbor()],
        None,
    )

    def evaluate(rel: str):
        expr = Entity.make(LOOKUP_TREE, {"path": rel})
        p.store.bind(abs_path(p, "app/e-" + rel.replace("/", "-")), expr)
        exec_e = make_execute(
            "e1", abs_path(p, "system/compute"), "eval", empty_params(),
            author=p.identity.identity_hash, capability=narrow.hash,
            resource=resource_target(abs_path(p, "app/e-" + rel.replace("/", "-"))),
        )
        ctx = DispatchCtx(exec=exec_e, conn=None, included={narrow.hash.hex(): narrow},
                          caller_cap=narrow, has_cap=True, handler_pattern="system/compute")
        return p.handlers["system/compute"].handle_op("eval", ctx)

    allowed = evaluate("app/allowed")
    assert allowed.status == 200
    assert allowed.result.type != ERROR, allowed.result.data

    denied = evaluate("app/denied")
    # F10 / v3.19c — an evaluated `permission_denied` is a VALUE at 200, not a 4xx. 4xx is
    # reserved for authorization of the REQUEST, before evaluation.
    assert denied.status == 200
    assert denied.result.type == ERROR
    assert denied.result.text("code") == "permission_denied"


def test_install_REFUSES_when_reactive_mode_is_not_installed():
    """D13's face amendment, as a refusal rather than a comment.

    ``install`` writes subgraph metadata whose whole purpose is to be woken by §7.2. A handler
    constructed with no engine answering 200 would be a 200 for an operation that can never do
    anything — the ``501``-shaped lie one level up. So it names the face.
    """
    p = peer()
    engineless = ComputeHandler(p, None)
    token, _ = p.mint_token(p.identity.identity_hash, [GrantSpec(["*"], ["*"], ["*"]).to_cbor()], None)
    exec_e = make_execute(
        "r6", abs_path(p, "system/compute"), "install",
        Entity.make("system/compute/install-request", {}),
        author=p.identity.identity_hash, capability=token.hash,
        resource=resource_target(abs_path(p, "app/x")),
    )
    ctx = DispatchCtx(exec=exec_e, conn=None, included={token.hash.hex(): token},
                      caller_cap=token, has_cap=True, handler_pattern="system/compute")
    out = engineless.handle_op("install", ctx)
    assert out.status == 501
    assert out.result.text("code") == "not_implemented"
    assert "emit_consumer" in (out.result.text("message") or "")


def test_install_REFUSES_without_a_verified_caller_capability():
    """§3.3 Phase 2 is the ONLY moment the authorization question is asked — everything after
    installation runs under that grant and is never re-audited. So there is nothing to audit
    against without one, and "no token" is not evidence of authority."""
    p = peer()
    install_compute(p)
    p.store.bind(abs_path(p, "app/lit"), Entity.make(LITERAL, {"value": 1}))
    exec_e = make_execute(
        "r7", abs_path(p, "system/compute"), "install",
        Entity.make("system/compute/install-request", {}),
        author=p.identity.identity_hash,
        resource=resource_target(abs_path(p, "app/lit")),
    )
    ctx = DispatchCtx(exec=exec_e, conn=None, included={}, caller_cap=None,
                      handler_pattern="system/compute")
    out = p.handlers["system/compute"].handle_op("install", ctx)
    assert out.status == 403
    assert out.result.text("code") == "permission_denied"


def test_install_refuses_a_narrow_grant_that_does_not_cover_a_dependency_read():
    """§3.3 Phase 2 — the caller's capability must cover every impure operation the subgraph
    will perform, and a tree read inside the graph is one of them.

    **THE PAIR IS THE POINT.** Under the wide-open ``--debug-open-grants`` posture the suite
    runs in, every install-time capability check passes whatever the audit collected, so an
    under-authorizing audit scores identically to a correct one. This is the narrower posture,
    constructed here because it is the only place the two readings of §3.3 differ.
    """
    p = peer()
    install_compute(p)
    p.store.bind(abs_path(p, "app/secret"), Entity.make("app/cell", {"value": 1}))
    cell = put(p, Entity.make(LOOKUP_TREE, {"path": "app/secret"}))
    p.store.bind(abs_path(p, "app/reader"), Entity.make("compute/field", {
        "name": "value", "entity": cell,
    }))

    def install_with(resources: list[str]):
        token, _ = p.mint_token(
            p.identity.identity_hash, [GrantSpec(["*"], resources, ["*"]).to_cbor()], None
        )
        exec_e = make_execute(
            "r8", abs_path(p, "system/compute"), "install",
            Entity.make("system/compute/install-request", {
                "result_path": abs_path(p, "app/reader-out"),
            }),
            author=p.identity.identity_hash, capability=token.hash,
            resource=resource_target(abs_path(p, "app/reader")),
        )
        ctx = DispatchCtx(exec=exec_e, conn=None, included={token.hash.hex(): token},
                          caller_cap=token, has_cap=True, handler_pattern="system/compute")
        return p.handlers["system/compute"].handle_op("install", ctx)

    denied = install_with(["app/reader", "app/reader-out"])
    assert denied.status == 403
    assert denied.result.text("code") == "permission_denied"
    assert "app/secret" in (denied.result.text("message") or "")

    # THE CONTROL: add the dependency to the grant and the same install succeeds. Without it
    # this test passes on a port that refuses every narrow grant.
    allowed = install_with(["app/reader", "app/reader-out", "app/secret"])
    assert allowed.status == 200, allowed.result.data


# ── §7.4 the reactive budget ─────────────────────────────────────────────────────


def test_the_reactive_budget_is_bounded_by_the_grants_constraints():
    """§7.4 — and **the constraint lives on the GRANT ENTRY, not on the token** (A-21).

    §5.2/§5.5 both spell it ``capability.data.constraints["system/compute"]``;
    ``ENTITY-CORE-PROTOCOL`` §5 carries ``constraints`` on each entry of ``grants``, which is
    where both our peers parse it from and where a delegation preserves it byte-equal. A literal
    transcription of §5.5 reads nothing, falls back to the peer defaults, and produces the
    constraint escalation §5.5 exists to prevent.
    """
    from entity_compute._internal.reactive import _reactive_budget

    p = peer()
    entry = GrantSpec(["*"], ["*"], ["*"]).to_cbor()
    entry["constraints"] = {"system/compute": {"max_compute_operations": 5, "max_compute_depth": 3}}
    token, _ = p.mint_token(p.identity.identity_hash, [entry], None)
    limits = _reactive_budget(token, DEFAULT_LIMITS)
    assert limits.max_operations == 5
    assert limits.max_depth == 3

    # THE CONTROL, and it is the one that matters: a grant with NO constraints must not narrow
    # anything. A parser reading the wrong location returns the defaults for BOTH tokens, so
    # only the pair discriminates.
    plain, _ = p.mint_token(p.identity.identity_hash, [GrantSpec(["*"], ["*"], ["*"]).to_cbor()], None)
    assert _reactive_budget(plain, DEFAULT_LIMITS) == DEFAULT_LIMITS


def test_the_reactive_budget_takes_the_TIGHTEST_value_across_entries():
    """Reading the tightest value across the entries is the only choice that cannot widen a
    grant."""
    from entity_compute._internal.reactive import _reactive_budget

    p = peer()
    loose = GrantSpec(["*"], ["*"], ["*"]).to_cbor()
    loose["constraints"] = {"system/compute": {"max_compute_operations": 900}}
    tight = GrantSpec(["*"], ["*"], ["*"]).to_cbor()
    tight["constraints"] = {"system/compute": {"max_compute_operations": 7}}
    token, _ = p.mint_token(p.identity.identity_hash, [loose, tight], None)
    assert _reactive_budget(token, DEFAULT_LIMITS).max_operations == 7
