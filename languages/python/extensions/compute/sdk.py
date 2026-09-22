"""COMPUTE — the in-process SDK surface, for the `python` peer.

Same rule as CONTENT and HISTORY: there is no conformance gate on this face and per the
operator that is correct, so **the extension is the instrument** — the handler's own
wire-gated path runs THROUGH this class rather than beside it. Two consumers, one
implementation; if this surface were wrong the `compute` category would say so.

**This is also the file that owns §4's override prohibition**, which as of v3.29 is ours to
enforce and was not before. See :func:`assert_not_builtin_override`.

**THERE IS NO H7 EVALUATOR SEAM ON THIS PEER, so this port has one consumer where
`typescript` has two** — see ``__init__.py``'s ``install_compute``. That removes the one
entry point §6.2 could not narrow per tree read, which is why
:data:`CAPABILITY_CHECK_IS_DISPATCH_SCOPED`'s reasoning is different here even though its
value is the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from entity_core.peer.model import Entity

from ._internal.evaluator import (
    Budget,
    ComputeError,
    EvalContext,
    as_compute_error,
    empty_scope,
    evaluate,
    is_error,
    materialize,
)
from .types import BUILTINS_PREFIX, DEFAULT_MAX_DEPTH, DEFAULT_MAX_OPS


@dataclass(frozen=True, slots=True)
class EvaluatorLimits:
    """§9.3's two peer-wide defaults, as a value rather than as two arguments."""

    max_operations: int
    max_depth: int


#: §9.3's recommended pair, as the default every entry point falls back to.
DEFAULT_LIMITS = EvaluatorLimits(max_operations=DEFAULT_MAX_OPS, max_depth=DEFAULT_MAX_DEPTH)


@dataclass(frozen=True, slots=True)
class EvalOutcome:
    """What an evaluation produced. Exactly one of the first two fields is non-None.

    **:attr:`value` is the MATERIALIZED form and never an in-flight one** (§2.3, v3.19c
    option α). This is the compute -> non-compute crossing for both of this port's consumers
    — the handler's ``eval`` and §7.2's reactive re-evaluation — so it is the one place the
    boundary has to be enforced, and enforcing it here is why neither consumer had to learn
    what an in-flight value is.

    ``value`` is ``None`` both when the outcome is an error AND when the expression genuinely
    evaluated to null (§4.1's ``if`` with no ``else`` returns one, and §4.5 makes it falsy).
    **Read :attr:`error` to tell the two apart, never :attr:`value`.** `typescript` has the
    same ambiguity for the same reason; on this substrate it is sharper because there is no
    tagged null to distinguish.
    """

    value: Any
    error: ComputeError | None
    #: Steps actually charged — ``max_operations`` minus what is left. §4.2's counter.
    operations_used: int


def _always_true(_path: str) -> bool:
    return True


def _no_dependency(_path: str) -> None:
    return None


class ComputeEvaluator:
    """The evaluator, as an in-process object.

    One instance per evaluation is the intended use — it carries the encountered-hash set,
    which §4.2 scopes to a single evaluation. Reusing one across evaluations would widen
    ``resolve()``'s reach past what the section allows, which is the kind of change that makes
    more programs work and is still wrong.

    Takes the PEER rather than a four-member interface. `typescript` declares a
    ``ComputePeerServices`` structural type because its two callers reach the same services
    from two different objects (a ``Peer`` and a ``PeerServices``); here both callers hold the
    peer itself, and the two members this class reads — ``.store`` and ``.local_peer`` — are
    the same two on every path. Declared in ``[sdk_surface].substrate``.
    """

    __slots__ = ("_peer", "_limits", "_encountered", "_dependencies")

    def __init__(self, peer: Any, limits: EvaluatorLimits = DEFAULT_LIMITS) -> None:
        self._peer = peer
        self._limits = limits
        self._encountered: set[str] = set()
        self._dependencies: list[str] = []

    @property
    def dependencies(self) -> tuple[str, ...]:
        """Paths §7.1 would register as reactive dependencies. Read after an evaluation."""
        return tuple(self._dependencies)

    def evaluate_at(
        self,
        expression: Entity,
        subgraph_root: str,
        *,
        budget: int | None = None,
        content_store_access: bool = False,
        included: dict | None = None,
        authorized_data_hashes: frozenset[str] | None = None,
        can_read_path: Callable[[str], bool] | None = None,
        can_write_path: Callable[[str], bool] | None = None,
    ) -> EvalOutcome:
        """Evaluate ``expression``, with ``subgraph_root`` as the base for ``relative: true``
        paths.

        **``subgraph_root`` is a required positional and not a default**, because §2.1 gives
        it two different sources — the expression URI for an explicit eval, the subgraph
        metadata's ``root_expression_path`` for a reactive one — and "same value, different
        source" is exactly the kind of sentence that becomes a bug when one caller is allowed
        to omit it.

        The keyword arguments are `typescript`'s ``EvaluateOptions`` object, in this language's
        idiom (``[sdk_surface].substrate``). Their meanings, in spec terms:

        ``budget``
            §3.2's ``params.budget`` knob. ``None`` means the caller did not ask, which is
            different from passing the default — §5.2's minimum rule is applied below and a
            caller cannot raise its own ceiling.
        ``content_store_access``
            §4.2 Tier 0. Default False, and it is the door
            ``_internal`` exists to keep shut.
        ``included``
            §4.2 step 1 — the envelope's pre-authorized ``included`` map, keyed by hex.
        ``authorized_data_hashes``
            §4.2 Tier 2, an installed subgraph's SEALED set. Empty unless the caller is
            §7.2's reactive path, which is the only caller that has one: the set is sealed by
            §3.3 Phase 2b and lives on the subgraph metadata. **NOT the encountered set** — an
            earlier `typescript` draft passed that, which would have made every hash the
            program itself produced Tier-2 authorized.
        ``can_read_path`` / ``can_write_path``
            §4.1 / §6.3's two path predicates, when the caller HOLDS a capability. Default
            permissive, which is the declared substrate gap on the explicit-eval path rather
            than an oversight — see :data:`CAPABILITY_CHECK_IS_DISPATCH_SCOPED`. §7.2's
            reactive path supplies both, because it evaluates under the INSTALLATION GRANT,
            which is an entity it fetched from the content store.
        """
        # §5.2's minimum rule, in the one place it can be applied: the caller's ask and the
        # peer default, whichever is smaller.
        operations = (
            self._limits.max_operations if budget is None
            else min(budget, self._limits.max_operations)
        )

        counters = Budget(operations=operations, depth=self._limits.max_depth)
        ctx = self._context(subgraph_root, content_store_access, included, authorized_data_hashes,
                            can_read_path, can_write_path)

        out = evaluate(expression, empty_scope(), counters, ctx)
        used = operations - counters.operations

        if is_error(out):
            # `is_error` is kind-based (§4.1), so this catches BOTH an in-flight ComputeError
            # and a compute/error entity that evaluated successfully. The second is why this
            # converts rather than casts.
            return EvalOutcome(value=None, error=as_compute_error(out), operations_used=used)
        # §2.3 / v3.19c option α — THE BOUNDARY. Everything above this line may be an
        # in-flight typed value; nothing below it is. `materialize` also stores what the bare
        # form references, which is the half of the rule that is easy to drop: a returned
        # entity whose `system/hash` field points at nothing the store has is a reference the
        # caller cannot follow, and no vector for that failure exists.
        return EvalOutcome(value=materialize(out, ctx), error=None, operations_used=used)

    def _context(
        self,
        subgraph_root: str,
        content_store_access: bool,
        included: dict | None,
        authorized_data_hashes: frozenset[str] | None,
        can_read_path: Callable[[str], bool] | None,
        can_write_path: Callable[[str], bool] | None,
    ) -> EvalContext:
        dependencies = self._dependencies
        encountered = self._encountered

        def register_dependency(path: str) -> None:
            if path not in dependencies:
                dependencies.append(path)

        def mark_encountered(hex_: str) -> None:
            encountered.add(hex_)

        return EvalContext(
            store=self._peer.store,
            local_peer=self._peer.local_peer,
            subgraph_root=subgraph_root,
            included=included if included is not None else {},
            has_content_store_access=content_store_access is True,
            # §4.2 TIER 2 — empty on the explicit-eval path and the SEALED set on the reactive
            # one. `mark_encountered` deliberately feeds nothing here: §10.1's
            # encountered-during-read guarantee is scoped to compute-typed entities, which
            # Tier 1 already admits. The set is kept so the call sites match §4.4/§4.3 N6.
            authorized_data_hashes=(
                authorized_data_hashes if authorized_data_hashes is not None else frozenset()
            ),
            can_read_path=can_read_path if can_read_path is not None else _always_true,
            # §6.3's `store` write. A distinct member rather than an alias of `can_read_path`
            # because §6.3 gives the two different authorities — a tree READ rides
            # `ctx.capability` and a `store` WRITE rides the caller's with the handler
            # forbidden from substituting its own grant — and §7.2 supplies two different
            # answers.
            can_write_path=can_write_path if can_write_path is not None else _always_true,
            register_dependency=register_dependency,
            mark_encountered=mark_encountered,
        )


#: §6.2's capability check — **which of this extension's entry points narrows per tree read,
#: and which cannot.**
#:
#: §4.1 guards ``compute/lookup/tree`` with
#: ``check_path_permission("get", path, ctx.capability, "system/tree", ...)``. On `typescript`
#: there are THREE ways into the evaluator and they do not get the same answer; **on this peer
#: there are two, and both narrow per tree read**:
#:
#: ===================================  =============================  ==================
#: entry point                          capability                      §6.2
#: ===================================  =============================  ==================
#: ``system/compute:eval`` (handler)    ``DispatchCtx.caller_cap``      **per tree read**
#: §7.2 reactive re-evaluation          the installation grant          **per tree read**
#: the H7 evaluator seam                *does not exist on this peer*   n/a
#: ===================================  =============================  ==================
#:
#: **So the constant is False here for a DIFFERENT reason than it is False on `typescript`,
#: and stating that is the point of keeping it exported.** There it is False because the third
#: row is real and cannot narrow (``ExpressionRequest`` carries the ``Execute`` and no
#: verified token). Here the third row is absent — this peer has no
#: ``set_expression_evaluator`` — so nothing in this port is dispatch-scoped at all, and the
#: constant reads False because *no entry point takes that shortcut*.
#:
#: One name, two ports, same value, two meanings. That is D13's face amendment one level down
#: — **a claim about a seam names the face it is about** — and it is why the name stays in
#: ``[sdk_surface].substrate`` rather than being read as agreement.
CAPABILITY_CHECK_IS_DISPATCH_SCOPED = False


def assert_not_builtin_override(pattern: str) -> None:
    """§4's override prohibition — **ours to enforce as of v3.29, and it was not before.**

    Through v3.28 §3.5 described this rule as *"a subset of"* core's ``system/*`` reservation
    and told implementers that enforcing that reservation needed *"no separate
    compute-specific guard."* ``ENTITY-CORE-PROTOCOL`` 0.8.2.13 **withdrew the reservation**,
    so v3.29 restates the prohibition on its own basis: it binds **every installation path**
    because it is a cross-peer determinism requirement, not a namespace policy. Two peers
    disagreeing about what ``"add"`` means is an interop failure.

    There is now nothing upstream that refuses a registration at
    ``system/compute/builtins/*`` on our behalf, so this function is the enforcement point,
    and it is called from :func:`~entity_compute.install_compute`'s path rather than left as
    documentation.

    Raises :class:`ValueError`. **Not a ``compute/error``**: this is an INSTALLATION fault in
    the host program, discovered before the peer serves anything, and answering it with a
    value a caller could store would be the §2.4 error type doing a job it is not for.
    """
    relative = pattern
    if pattern.startswith("/"):
        i = pattern.find("/", 1)
        relative = pattern[i + 1:] if i >= 0 else pattern
    if relative == BUILTINS_PREFIX or relative.startswith(BUILTINS_PREFIX + "/"):
        raise ValueError(
            f"EXTENSION-COMPUTE §4: a handler MUST NOT be registered at {pattern}. "
            "The builtin handlers are the cross-peer determinism floor; overriding one makes "
            "two peers disagree about what an operation means. (v3.29 — this rule no longer "
            "delegates to the withdrawn core system/* reservation.)"
        )
