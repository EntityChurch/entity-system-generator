"""COMPUTE §3 — the ``system/compute`` handler, for the `python` peer.

§3.1 declares three operations and we declare all three, which is a DECISION and not a
transcription: §10.2 lists *"Compute handler at ``system/compute/*``"* and *"Install and
uninstall operations — required if reactive mode is implemented"* as SHOULDs, while §10.1
MUSTs three behaviours OF the install operation. Four documents, three answers
(``ROUTING-2026-09-09-d-arch-*`` §4).

**What settled it is the oracle, and that is worth stating plainly rather than dressing up as
a spec reading.** `entity-core-go`'s ``validate-peer`` declares ``handler_op_install`` and
``handler_op_uninstall`` whose body is ``FailCheck("compute handler missing operation: " + op)``
— a hard FAIL on a manifest that omits either, and 6 of the category's 128 checks are blocked
behind ``handler_op_install``. So the measurable answer is three, the spec's answer is
ambiguous, and we declare three and route the ambiguity.

**The four phases are PRE-FLIGHT then COMMIT, and §3.3 makes that atomicity normative.**
Phases 1–2b decide; Phases 3–4 write. A re-install whose audit fails leaves the previous
(possibly frozen) metadata unchanged, so a caller can retry with a different capability or a
corrected expression without losing the frozen state. Nothing below writes anything before the
last check has passed. That matters more than tidiness here: Phase 2b SEALS
``authorized_data_hashes``, a §4.2 Tier 2 authorization surface, and a half-built audit
produces a subgraph admitting hashes nobody validated.

**THE DISPATCH IDIOM IS THIS PEER'S, NOT THE SIBLING'S.** ``handle_op(op, ctx) -> Outcome``,
duck-typed, no base class, with the operation ladder as an ``if`` chain — the shape every
handler on this peer has. There is no ``async``: this peer serves thread-per-connection and
nothing in §3 is I/O-bound, where `typescript`'s ``handle`` is a ``Promise`` because that
peer's dispatcher is. The §7.2 consequence is the interesting half — a re-evaluation triggered
from inside ``Store.bind`` runs to completion before the ``put`` returns on BOTH ports, one
because the bus is synchronous and one because the runtime is single-threaded per request.
"""

from __future__ import annotations

from typing import Any

from entity_core.peer.capability import check_path_permission
from entity_core.peer.handlers import DispatchCtx, Outcome
from entity_core.peer.model import Entity
from entity_core.peer.wire import error_result

from ._internal.evaluator import canonicalize_path
from ._internal.reactive import ReactiveEngine, deterministic_id
from ._internal.subgraph import (
    AuditContext,
    AuditRefusal,
    SubgraphAudit,
    audit_subgraph,
    grant_covers,
)
from .sdk import ComputeEvaluator, EvaluatorLimits
from .types import (
    CODE_AMBIGUOUS_RESOURCE,
    CODE_INVALID_EXPRESSION,
    CODE_NOT_FOUND,
    CODE_PERMISSION_DENIED,
    COMPUTE_PATTERN,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_OPS,
    INSTALL_REQUEST,
    INSTALL_RESULT,
    PROCESSES_PREFIX,
    RESULT,
    is_compute_expression,
)

#: §3.1's manifest, verbatim, in the mapped §3.7 form this peer publishes.
#:
#: ``eval`` declares ``primitive/any`` on BOTH sides and that is the spec's shape, not a
#: placeholder: the input is any compute expression entity and the output is a value, a
#: ``compute/result`` or a ``compute/error``. A narrower declaration here would be a claim §3.2
#: does not make.
#:
#: ``uninstall`` takes ``primitive/any`` because §3.1 says *"empty-params per V7 §3.2"* — there
#: is no ``system/compute/uninstall-request``; the type was eliminated in v3.12. The
#: declaration header still names one, which is the §9.2 drift already filed.
OPERATION_SPECS: dict[str, dict[str, str]] = {
    "eval": {"input_type": "primitive/any", "output_type": "primitive/any"},
    "install": {"input_type": INSTALL_REQUEST, "output_type": INSTALL_RESULT},
    "uninstall": {"input_type": "primitive/any", "output_type": "system/protocol/status"},
}


def _err(status: int, code: str, message: str = "") -> Outcome:
    return Outcome(status, error_result(code, message))


def _resource_targets(exec_e: Entity) -> list[str] | None:
    resource = exec_e.field("resource")
    if not isinstance(resource, dict):
        return None
    targets = resource.get("targets")
    if not isinstance(targets, list) or not targets:
        return None
    return [str(t) for t in targets]


class ComputeHandler:
    """The §3.1 handler. Installed by :func:`~entity_compute.install_compute`."""

    #: §3.1 / §9.2, in this peer's ladder order.
    OPERATIONS = ("eval", "install", "uninstall")

    __slots__ = ("peer", "_limits", "_engine")

    def __init__(
        self,
        peer: Any,
        engine: ReactiveEngine | None = None,
        *,
        max_operations: int | None = None,
        max_depth: int | None = None,
    ) -> None:
        #: Registration-time capture — this peer's ``DispatchCtx`` carries no peer (measured,
        #: ``languages/python/gates/host-seam/probe-seam.py``; ``profile.toml``
        #: ``[extension_host].ctx_carries_peer = false``).
        self.peer = peer
        self._limits = EvaluatorLimits(
            max_operations=DEFAULT_MAX_OPS if max_operations is None else max_operations,
            max_depth=DEFAULT_MAX_DEPTH if max_depth is None else max_depth,
        )
        #: §7's engine, or None when reactive mode is not installed.
        #:
        #: **Nullable rather than always-present, and that is a face distinction rather than
        #: defensive coding** (D13's face amendment). ``install`` writes subgraph metadata whose
        #: whole purpose is to be woken by §7.2, and §3.3's *"Expressions without
        #: installation"* clause is explicit that reactive mode requires an installation grant.
        #: A handler that accepted an install with no engine behind it would answer 200 for an
        #: operation that can never do anything — the ``501``-shaped lie one level up. So the
        #: handler refuses, naming the face.
        self._engine = engine

    # ── dispatch ─────────────────────────────────────────────────────────────

    def handle_op(self, op: str, ctx: DispatchCtx) -> Outcome:
        if op == "eval":
            return self._eval(ctx)
        if op == "install":
            return self._install(ctx)
        if op == "uninstall":
            return self._uninstall(ctx)
        return _err(
            400,
            "unknown_operation",
            f"{COMPUTE_PATTERN} has no operation '{op}' (§3.1)",
        )

    # ── §3.2 handle_eval ─────────────────────────────────────────────────────

    def _eval(self, ctx: DispatchCtx) -> Outcome:
        """§3.2 ``handle_eval``.

        **The three refusals below are in §3.2's order and each has its own code.** The
        ordering matters for the same reason §4.1's builtin-path shape check does: a resolution
        failure and a not-an-expression failure are different codes, and deciding them in the
        other order would make the answer depend on which fault a malformed request hits first.

        **And the last line is the one that surprises people.** An evaluated ``compute/error``
        comes back at **status 200** with the error as the result entity (F10, and v3.19c's
        normative clarification for ``permission_denied``). 4xx is reserved for authorization
        of the REQUEST, before evaluation. A caller detects a computed error by
        ``result.type == "compute/error"``, never by the status — and a port that mapped it to
        4xx would look more correct and be less interoperable.
        """
        # §3.2: "eval requires exactly one resource target (the expression path)".
        targets = _resource_targets(ctx.exec)
        if targets is None or len(targets) != 1:
            return _err(
                400,
                "ambiguous_resource",
                "eval requires exactly one resource target (the expression path)",
            )
        absolute = canonicalize_path(targets[0], self.peer.local_peer)

        expression = self.peer.store.get_at(absolute)
        if expression is None:
            return _err(404, "not_found", "No entity at path")
        if not is_compute_expression(expression.type):
            return _err(400, "invalid_expression", "Entity at path is not a compute expression")

        evaluator = ComputeEvaluator(self.peer, self._limits)
        read, write = self._path_authority(ctx.caller_cap)
        # §3.2: for an explicit eval the subgraph root IS the expression URI. For an installed
        # subgraph it comes from `root_expression_path` — "same value, different source", which
        # is why it is a parameter and not a constant.
        outcome = evaluator.evaluate_at(
            expression,
            absolute,
            budget=_read_budget_override(ctx),
            included=ctx.included,
            can_read_path=read,
            can_write_path=write,
        )

        if outcome.error is not None:
            # F10 — an evaluated error is a VALUE at 200.
            return Outcome.ok(outcome.error.to_entity())

        # §2.4 — a primitive result is wrapped in a `compute/result` carrying the source
        # expression's hash; an entity result travels as itself. §3.2's entity-native
        # unwrapping table is the same split read from the other side.
        value = outcome.value
        if isinstance(value, Entity):
            return Outcome.ok(value)
        return Outcome.ok(
            Entity.make(RESULT, {"value": value, "expression": expression.hash})
        )

    # ── §3.3 handle_install ──────────────────────────────────────────────────

    def _install(self, ctx: DispatchCtx) -> Outcome:
        """§3.3 ``handle_install`` — the four phases, in order, pre-flight before commit.

        **Read the phase boundary as the security boundary.** Phase 2 asks whether the
        CALLER's capability covers every impure operation the subgraph will perform; everything
        after installation runs under that same grant (§7.2's *"Authorization source"*) and is
        never re-audited. So Phase 2 is the only moment at which the question is asked, and
        Phase 2b's ``authorized_data_hashes`` is the only record of the answer.
        """
        engine = self._engine
        if engine is None:
            return _err(
                501,
                "not_implemented",
                "system/compute:install requires §7 reactive mode, which is not installed in "
                "this composition (the emit_consumer face). An install with no engine behind "
                "it would record a subgraph nothing can ever wake.",
            )

        # §3.3: "install requires exactly one resource target (the root expression path)".
        targets = _resource_targets(ctx.exec)
        if targets is None or len(targets) != 1:
            return _err(
                400,
                CODE_AMBIGUOUS_RESOURCE,
                "install requires exactly one resource target (the root expression path)",
            )
        local = self.peer.local_peer
        root_path = canonicalize_path(targets[0], local)

        expression = self.peer.store.get_at(root_path)
        if expression is None:
            return _err(404, CODE_NOT_FOUND, "No expression at path")
        if not is_compute_expression(expression.type):
            return _err(400, CODE_INVALID_EXPRESSION, "Entity at path is not a compute expression")

        # ── Phase 1 — audit the subgraph ──────────────────────────────────────
        audit_ctx = AuditContext(
            store=self.peer.store,
            local_peer=local,
            # §4.2 step 1 — the envelope's `included` map, ALREADY keyed by lowercase hex
            # (`Included`). The audit resolves through it before the content store, which is
            # what lets an installer carry an embedded capability's chain in the EXECUTE rather
            # than having to publish it first; CP1's adversarial vector arrives exactly that way.
            included=ctx.included,
            author=ctx.exec.bytes_("author"),
        )
        audit = audit_subgraph(expression, root_path, audit_ctx)
        if isinstance(audit, AuditRefusal):
            return _err(audit.status, audit.code, audit.message)

        # ── Phase 2 — the caller's capability covers every impure operation ───
        capability = ctx.caller_cap
        if capability is None:
            return _err(
                403,
                CODE_PERMISSION_DENIED,
                "install requires a verified caller capability to audit against",
            )

        for path in audit.read_paths:
            if not check_path_permission("get", path, capability, "system/tree", local):
                return _err(
                    403, CODE_PERMISSION_DENIED, "Caller capability does not cover read: " + path
                )
        for target in audit.handler_targets:
            if not grant_covers(
                self.peer.store,
                ctx.included,
                capability,
                target.path,
                target.operation,
                target.resource,
                local,
            ):
                return _err(
                    403,
                    CODE_PERMISSION_DENIED,
                    "Caller capability does not cover handler: "
                    + target.path + "." + (target.operation or ""),
                )

        requested = _read_result_path_override(ctx)
        result_path = (
            root_path + "/result" if requested is None else canonicalize_path(requested, local)
        )
        if not check_path_permission("put", result_path, capability, "system/tree", local):
            return _err(
                403,
                CODE_PERMISSION_DENIED,
                "Caller capability does not cover result write: " + result_path,
            )
        for path in audit.write_paths:
            canonical = canonicalize_path(path, local)
            if not check_path_permission("put", canonical, capability, "system/tree", local):
                return _err(
                    403,
                    CODE_PERMISSION_DENIED,
                    "Caller capability does not cover write: " + canonical,
                )

        # ── Phase 2b — validate `compute/lookup/hash` data references (v3.7 D5/D6) ──
        #
        # THE SET THIS LOOP BUILDS IS THE ONE §4.2 TIER 2 TRUSTS WITHOUT RE-CHECKING. Each
        # entry is validated three ways — the hint path resolves, the entity there hashes to
        # the referenced value, and the caller may read that path — and only then is the hash
        # admitted. A `compute/lookup/hash` with no hint is refused outright: resolving it
        # would need a reverse index this port does not have, and §3.3 makes "or reject" one of
        # the three permitted dispositions.
        authorized_data_hashes: list[bytes] = []
        for entry in audit.data_hashes:
            if entry.path is None:
                return _err(
                    400,
                    "no_authorization_path",
                    "compute/lookup/hash without path hint requires reverse index or "
                    "content_store_access",
                )
            hint_path = canonicalize_path(entry.path, local)
            bound = self.peer.store.get_at(hint_path)
            if bound is None:
                return _err(404, CODE_NOT_FOUND, "No entity at hint path: " + hint_path)
            if bound.hash != entry.hash:
                return _err(
                    400,
                    "hash_mismatch",
                    f"Entity at {hint_path} has hash {bound.hash.hex()}, "
                    f"expression references {entry.hash.hex()}",
                )
            if not check_path_permission("get", hint_path, capability, "system/tree", local):
                return _err(
                    403,
                    CODE_PERMISSION_DENIED,
                    "Caller grant does not cover tree GET at: " + hint_path,
                )
            authorized_data_hashes.append(entry.hash)

        # ── Phase 3 — commit the subgraph metadata ────────────────────────────
        subgraph_path = (
            canonicalize_path(PROCESSES_PREFIX, local) + "/" + deterministic_id(root_path)
        )

        # §3.3, and this clause is the one an implementation drops: the caller's capability
        # entity MUST reach the content store before its hash is recorded. The grant is only in
        # the envelope for the length of this EXECUTE; §7.2 fetches it by hash on every
        # re-evaluation, and a subgraph whose grant cannot be resolved freezes with
        # `installation_grant_invalid` the first time it fires.
        self.peer.store.put_entity(capability)

        author = ctx.exec.bytes_("author")
        data: dict[str, Any] = {
            "root_expression_path": root_path,
            "root_expression": expression.hash,
            "installation_grant": capability.hash,
            "result_path": result_path,
            "status": "active",
        }
        if author is not None:
            data["installed_by"] = author
        # The SEVENTH field. §2.5's type block declares six; §3.3 Phase 3 writes this one, §4.2
        # reads it, §10.1 MUSTs it by name, and `entity-core-go`'s `ComputeSubgraphData` carries
        # it `omitempty`. Omitted when empty so the bytes agree with the reference for the
        # common case.
        if authorized_data_hashes:
            data["authorized_data_hashes"] = authorized_data_hashes
        subgraph = Entity.make("system/compute/subgraph", data)
        self.peer.store.bind(subgraph_path, subgraph, ctx.exec_context())

        # ── Phase 4 — register dependencies, then evaluate once ───────────────
        engine.register(subgraph_path, root_path, audit)
        # §3.3's re-installation clause SHOULDs an initial evaluation, and doing it on every
        # install rather than only on re-install is what makes the two paths one path: a
        # `result_path` that is absent until the first dependency changes is a second state for
        # every downstream reader to handle. It also clears a `compute/error` left by a frozen
        # predecessor, which is the other half of that SHOULD.
        engine.evaluate_now(subgraph_path, ctx.exec_context())

        return Outcome.ok(
            Entity.make(
                INSTALL_RESULT,
                {
                    "subgraph_path": subgraph_path,
                    "impure_operations": _impure_operations(audit),
                    "result_path": result_path,
                },
            )
        )

    # ── §3.4 handle_uninstall ────────────────────────────────────────────────

    def _uninstall(self, ctx: DispatchCtx) -> Outcome:
        """§3.4 ``handle_uninstall`` — clear the registrations, delete the metadata.

        **The expression entities are NOT deleted**, and §3.4 says so in one line: they remain
        in the tree as inert data. Uninstall withdraws the installation grant's standing
        authorization; it does not withdraw the program.
        """
        engine = self._engine
        if engine is None:
            return _err(
                501,
                "not_implemented",
                "system/compute:uninstall requires §7 reactive mode, which is not installed "
                "in this composition",
            )
        targets = _resource_targets(ctx.exec)
        if targets is None or len(targets) != 1:
            return _err(
                400,
                CODE_AMBIGUOUS_RESOURCE,
                "uninstall requires exactly one resource target (the subgraph path)",
            )
        subgraph_path = canonicalize_path(targets[0], self.peer.local_peer)
        subgraph = self.peer.store.get_at(subgraph_path)
        if subgraph is None or subgraph.type != "system/compute/subgraph":
            return _err(404, CODE_NOT_FOUND, "No installed subgraph at path")

        engine.unregister(subgraph_path)
        self.peer.store.unbind(subgraph_path, ctx.exec_context())

        # §3.4 returns `{status: 200}` and nothing else. The STATUS is the answer and it rides
        # the EXECUTE_RESPONSE, so the result entity is this peer's empty-ack shape rather than
        # a body — §3.1's manifest names `system/protocol/status` as the output type and core
        # defines no such entity type, which is the §9.2 drift already filed. Minting one here
        # would put a type on the wire no registry knows.
        return Outcome.ok(Entity.make("primitive/any", {}))

    # ── §6.2 / §6.3's two path predicates ────────────────────────────────────

    def _path_authority(self, capability: Entity | None):
        """Build the two predicates from the caller's own capability.

        **Two predicates and not one**, because §6.3's table gives the two operations different
        authorities: a tree READ rides ``ctx.capability``, and a ``store`` WRITE rides the
        caller's capability with the handler explicitly forbidden from substituting its own
        grant (no silent escalation). They happen to be the same token here and they are not
        the same question, so collapsing them would hide that a future port with a handler
        grant has a decision to make.

        ``(None, None)`` when there is no token, which leaves the evaluator's permissive
        defaults in place — the honest answer for an in-process dispatch that arrived with
        nothing to narrow.

        **This calls ``check_path_permission``, which this repo routed as keystone H9 after
        hand-walking the grants here and watching it deny 23 of 34 oracle checks.** The
        `typescript` port's equivalent contract entry once claimed the predicate did not exist
        on a peer — while our own ``TRACKER-entity-core-keystone.md`` carried it as H9, CLOSED,
        routed by this seat (AP-34). It exists on this peer because we asked for it.
        """
        if capability is None:
            return None, None
        local = self.peer.local_peer

        def can_read(path: str) -> bool:
            return check_path_permission("get", path, capability, "system/tree", local)

        def can_write(path: str) -> bool:
            return check_path_permission("put", path, capability, "system/tree", local)

        return can_read, can_write


def _impure_operations(audit: SubgraphAudit) -> dict[str, Any]:
    """§3.3's ``impure_operations`` — the audit's four categories, as the install result's
    ``primitive/any`` payload.

    Reported verbatim rather than summarized. The caller asked the handler to audit a graph on
    its behalf and this is the audit; a count would tell it that N things were checked without
    telling it which, and the reason the field is ``primitive/any`` in §2.6 is that its shape is
    the audit's shape.
    """
    return {
        "read_paths": list(audit.read_paths),
        "handler_targets": [
            {"path": t.path, **({"operation": t.operation} if t.operation is not None else {})}
            for t in audit.handler_targets
        ],
        "write_paths": list(audit.write_paths),
        "data_hashes": [d.hash for d in audit.data_hashes],
    }


def _read_result_path_override(ctx: DispatchCtx) -> str | None:
    """§2.6 — ``install-request.result_path``, optional. None means "use the default".

    Reads through ``sub_entity``, which returns None rather than raising on a malformed params
    map (§4.9 no-crash), so there is no ``try`` here. `typescript` needs one: its
    ``HandlerContext.params`` is a GETTER that decodes, and the decode throws one frame outside
    any ``try`` placed around the field read — a real bug that port had and fixed.
    """
    params = ctx.exec.sub_entity("params")
    return None if params is None else params.text("result_path")


def _read_budget_override(ctx: DispatchCtx) -> int | None:
    """§3.2 — ``params`` optionally carries operation knobs (``{budget: ...}``).

    Returns None when absent, which is different from returning the default: the default lives
    in one place (this handler's constructor, from §9.3) and a None here means *"the caller did
    not ask"*, so the two cannot drift apart. §5.2's minimum rule then applies between this and
    any capability constraint.
    """
    params = ctx.exec.sub_entity("params")
    return None if params is None else params.uint("budget")
