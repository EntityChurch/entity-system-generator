"""``entity_compute`` — COMPUTE v3.29 for the `python` peer.

THE PUBLIC ENTRY POINT. ``_internal`` is not re-exported and is not in ``__all__``; see
``_internal/__init__.py`` for why that boundary is weaker here than on `typescript` and why it
matters more for this extension than for either of the first two.

**THE FIFTH FACE IS NOT INSTALLABLE ON THIS PEER, AND THAT IS THE HEADLINE OF THIS PORT.**
`typescript`'s ``installCompute`` installs five: ``types``, ``handler``, ``emit_consumer``,
``sdk`` and — uniquely in this corpus — the **expression evaluator**, through
``Peer.setExpressionEvaluator`` (keystone's H7, which this repo routed on 2026-09-03 and which
landed the same day). This peer has no such seam. Measured, not assumed:

    $ grep -rniE "expression_evaluator|set_evaluator|unsupported_expression|entity_native_dispatch" \\
          protocol-generator/{python,rust,typescript}/src        # entity-core-keystone
    24 hits in 5 files; the python and rust hits are `_entity_native_dispatch` and its
    `501 unsupported_expression`, with no seam of any spelling.

``Peer._entity_native_dispatch`` (``src/entity_core/peer/peer.py``) evaluates the built-in
``compute/literal`` shape in-process and then answers ``501 unsupported_expression``. There is
no consultation step between the two, at any visibility, so the face is **not-installable**
rather than not-installed — D13's face amendment vocabulary, and the distinction is the whole
point: ``not-installed`` is a thing we have not built and ``not-installable`` is a thing the
substrate does not host.

**IT COSTS THIS PORT NOTHING MEASURABLE, WHICH IS ALSO WORTH STATING.** Exactly one of the
oracle's 128 ``compute`` checks reaches the entity-native path
(``v314_compute_apply_to_entity_native``), and it already fails on `typescript` — where the
seam IS installed — for a different reason: ``compute/apply`` handler mode needs a re-entrant
LOCAL dispatch the peer does not expose (keystone K-5). So the face is absent here and the
score is not a statement about it. **A category score is a statement about the oracle's access
path** — the `rust` × HISTORY lesson, arriving from the opposite direction: there a working
face was unmeasurable, here an absent face is unmeasured.

:func:`install_compute` keeps the detection anyway, three-valued and OBSERVED, so the day
keystone lands H7 on this peer the port reports ``installed`` without an edit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from entity_core.peer.model import Entity

from .handler import OPERATION_SPECS, ComputeHandler
from ._internal.reactive import ReactiveEngine, deterministic_id
from .sdk import (
    CAPABILITY_CHECK_IS_DISPATCH_SCOPED,
    DEFAULT_LIMITS,
    ComputeEvaluator,
    EvalOutcome,
    EvaluatorLimits,
    assert_not_builtin_override,
)
from .types import (
    ALL_TYPES,
    APPLY,
    ARITHMETIC,
    ASSOC_ARGS,
    BUILTINS_PREFIX,
    CLOSURE,
    CODE_AMBIGUOUS_RESOURCE,
    CODE_BUDGET_EXHAUSTED,
    CODE_CASCADE_LIMIT,
    CODE_CAST_OUT_OF_RANGE,
    CODE_COUNT_OUT_OF_RANGE,
    CODE_DEPTH_EXCEEDED,
    CODE_DIVISION_BY_ZERO,
    CODE_INDEX_OUT_OF_RANGE,
    CODE_INSTALLATION_GRANT_INVALID,
    CODE_INVALID_EXPRESSION,
    CODE_MISSING_ARGUMENT,
    CODE_NOT_FOUND,
    CODE_PERMISSION_DENIED,
    CODE_SCOPE_UNREACHABLE,
    CODE_TYPE_MISMATCH,
    CODE_UNKNOWN_TYPE,
    COMPARE,
    COMPUTE_PATTERN,
    CONCAT_ARGS,
    CONSTRUCT,
    CORE_EXPRESSION_TYPES,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_OPS,
    ERROR,
    FIELD,
    FILTER_ARGS,
    FOLD_ARGS,
    GROUP,
    GROUP_BY_ARGS,
    IF,
    INDEX,
    INLINE_EXPRESSION_TYPES,
    INSTALL_REQUEST,
    INSTALL_RESULT,
    LAMBDA,
    LENGTH,
    LET,
    LITERAL,
    LOGIC,
    LOOKUP_HASH,
    LOOKUP_SCOPE,
    LOOKUP_TREE,
    MAP_ARGS,
    NUMERIC_CAST,
    PROCESSES_PREFIX,
    RANGE_ARGS,
    RECOMMENDED_MAX_CASCADE_DEPTH,
    RESULT,
    SCOPE,
    SCOPE_BINDING,
    STORE_ARGS,
    SUBGRAPH,
    compute_entity,
    compute_type_defs,
    compute_type_entities,
    is_compute_expression,
    is_compute_type,
    publish_compute_types,
)


@dataclass(frozen=True, slots=True)
class ComputeInstallation:
    """What :func:`install_compute` installed. Reported, never assumed."""

    pattern: str
    interface_path: str
    type_paths: tuple[str, ...]
    handler_paths: tuple[str, ...]
    #: §7's engine — the ``emit_consumer`` face, and the owner of the dependency index.
    engine: ReactiveEngine
    #: §7.1's rebuild count: subgraphs re-registered from ``system/compute/processes/*``.
    rebuilt: int
    #: Whether the peer accepted an expression evaluator through the H7 seam.
    #:
    #: **Three-valued and OBSERVED, never declared.** HISTORY shipped a hardcoded
    #: ``context_available = False`` commented "measured" — a claim about another team's peer,
    #: frozen in our source, asserted by our own tests; when the substrate moved nothing could
    #: notice. This is read off the peer: ``installed`` when the read-back returns the object we
    #: handed it, ``not-installable`` when the seam is absent, ``not-observed`` when the seam
    #: exists and the read-back does not agree.
    #:
    #: On this peer it is ``not-installable`` today. The value is produced by
    #: :func:`_install_evaluator` rather than written here, so it stops being a claim about
    #: another team's tree the moment that tree changes.
    evaluator_face: str


def install_compute(
    peer: Any, *, max_operations: int | None = None, max_depth: int | None = None
) -> ComputeInstallation:
    """Install COMPUTE onto a live peer: the four §11.6.1 writes, 33 types, the handler, §7's
    consumer, and the H7 evaluator where the peer has one.

    **This peer has no registration surface** (measured —
    ``languages/python/gates/host-seam/probe-seam.py``; ``profile.toml``
    ``[extension_host].registration_surface = "none"``), so all four §11.6.1 writes are ours,
    through public names only. Same seven-step shape ``install_history`` has, plus the
    evaluator step.

    **The order matters and is not arbitrary.** The consumer is registered LAST, after the
    §11.6.1 writes and the type publication. Otherwise it observes its own installation: four
    tree writes plus thirty-three type entities. For HISTORY that produced an audit log
    starting with ten entries nobody performed; here it is stronger than hygiene, because
    **COMPUTE's consumer WRITES BACK** — a §11.6.1 registration write arriving before the
    handler exists would re-enter an evaluator with a half-built peer behind it.
    """
    # §4's override prohibition, enforced before anything is written. As of v3.29 this rule
    # stands on its own — the core `system/*` reservation it used to delegate to was withdrawn
    # (0.8.2.13), so nothing upstream would refuse this on our behalf. Checking our OWN pattern
    # looks redundant and is not: it is the one call site a future change to `COMPUTE_PATTERN`
    # would run through.
    assert_not_builtin_override(COMPUTE_PATTERN)

    limits = EvaluatorLimits(
        max_operations=DEFAULT_MAX_OPS if max_operations is None else max_operations,
        max_depth=DEFAULT_MAX_DEPTH if max_depth is None else max_depth,
    )
    # ONE engine, TWO halves: §3.3's Phase 4 runs through the handler and §7.2's trigger runs
    # through the emit bus, and they are the same object's two entry points rather than two
    # structures that have to agree about what is installed.
    engine = ReactiveEngine(peer, limits)

    local = peer.local_peer

    def absolute(rel: str) -> str:
        return "/" + local + "/" + rel

    interface_rel = "system/handler/" + COMPUTE_PATTERN
    handler_paths: list[str] = []

    # (1) §11.6.1 manifest at the pattern path — what `_resolve_handler` walks for.
    path = absolute(COMPUTE_PATTERN)
    peer.store.bind(path, Entity.make("system/handler", {"interface": interface_rel}))
    handler_paths.append(path)

    # (2) The handler interface entity (discovery index) — §3.1's manifest, complete. The
    #     oracle's `handler_manifest_decode` and three `handler_op_*` checks read this.
    interface_path = absolute(interface_rel)
    peer.store.bind(
        interface_path,
        Entity.make(
            "system/handler/interface",
            {"pattern": COMPUTE_PATTERN, "name": "compute", "operations": OPERATION_SPECS},
        ),
    )
    handler_paths.append(interface_path)

    # (3)+(4) Self-issued signed handler grant + its signature at the §3.5 invariant pointer,
    #         so dispatch-time grant validation can find and verify it.
    token, signature = peer.mint_token(peer.identity.identity_hash, [], None)
    grant_path = absolute("system/capability/grants/" + COMPUTE_PATTERN)
    peer.store.bind(grant_path, token)
    handler_paths.append(grant_path)
    sig_path = absolute("system/signature/" + token.hash.hex())
    peer.store.bind(sig_path, signature)
    handler_paths.append(sig_path)

    # (5) The 33 type entities. 63 of this composition's core improvements are the oracle's
    #     `type_compute_*_match` checks over these bytes.
    type_paths = publish_compute_types(peer)

    # (6) The executable body, into the container dispatch consults.
    peer.handlers[COMPUTE_PATTERN] = ComputeHandler(
        peer, engine, max_operations=max_operations, max_depth=max_depth
    )

    evaluator_face = _install_evaluator(peer, limits)

    # (7) LAST: the emit consumer. See the docstring for why "last" is load-bearing here in a
    #     way it was not for HISTORY.
    peer.store.register_tree_consumer(engine.on_tree_change)

    # (8) §7.1's `rebuild_dependency_index`. Vacuous on a fresh peer and not vacuous in
    #     general: a composition installed onto a peer whose tree was restored from elsewhere
    #     has subgraphs in `system/compute/processes/` and an empty index, which is precisely
    #     the state §7.1 MUSTs a rebuild for.
    rebuilt = engine.rebuild()

    return ComputeInstallation(
        pattern=COMPUTE_PATTERN,
        interface_path=interface_path,
        type_paths=tuple(type_paths),
        handler_paths=tuple(handler_paths),
        engine=engine,
        rebuilt=rebuilt,
        evaluator_face=evaluator_face,
    )


def _install_evaluator(peer: Any, limits: EvaluatorLimits) -> str:
    """The H7 seam: hand the peer an evaluator for entity-native handler bodies.

    ``ENTITY-CORE-PROTOCOL`` §6.6's dispatch evaluates the built-in ``compute/literal`` shape
    in-process, then — on a peer that has the seam — consults an installed evaluator, then
    answers ``501 unsupported_expression``. **That ordering is the whole safety argument**:
    ``core_register_body_binding`` drives the literal path on every peer in the cohort, so the
    literal floor is out of an evaluator's reach and installing one cannot move a conformance
    result.

    **THE SEAM IS DETECTED, NOT ASSUMED, AND ON THIS PEER IT IS ABSENT.**
    ``set_expression_evaluator`` is keystone's addition to ONE of the 46 peers and 45 read
    ``unknown``. A peer without the method gets ``not-installable`` and everything else still
    installs — the D13 face amendment applied to our own installer rather than only to our
    reports.

    **The branches below the detection are unexercised against the real peer today, and that is
    the AP-3 shape unless something drives them** — a check that cannot reach its assertion.
    ``test/test_install.py`` drives all three verdicts against stand-in peers (no seam / a seam
    that stores / a seam that swallows), so the detector is known to be able to answer
    something other than ``not-installable`` before the day it has to.
    """
    setter = getattr(peer, "set_expression_evaluator", None)
    if not callable(setter):
        return "not-installable"

    def evaluate_expression(request: Any) -> Any:
        # DECLINE anything that is not a compute expression. The peer's own
        # `501 unsupported_expression` then stands — a better answer than one we invented about
        # a body we do not understand, and what makes two installed evaluators compose.
        expression = getattr(request, "expression", None)
        if expression is None or not is_compute_expression(expression.type):
            return None
        # A fresh evaluator per dispatch: §4.2 scopes the encountered set to one evaluation, so
        # a shared instance would widen `resolve()`'s reach across unrelated requests.
        outcome = ComputeEvaluator(peer, limits).evaluate_at(
            expression, getattr(request, "expression_path", "")
        )
        # F10 — an evaluated `compute/error` is a VALUE at 200, not a transport failure, and the
        # dispatch boundary unwraps it as the result entity (§3.2). Declining here instead would
        # answer 501 for a program that RAN and produced an error.
        if outcome.error is not None:
            return outcome.error.to_entity()
        if isinstance(outcome.value, Entity):
            return outcome.value
        return Entity.make(RESULT, {"value": outcome.value, "expression": expression.hash})

    setter(evaluate_expression)
    # READ BACK, never assume. The one thing a setter cannot tell you is whether it set
    # anything — keystone planted exactly that defect against their own H7 work (a setter that
    # writes nothing, shaped like `julia`'s dead register map), and D13's Read layer exists
    # because a call site is not a capability.
    return (
        "installed"
        if getattr(peer, "expression_evaluator", None) is evaluate_expression
        else "not-observed"
    )


__all__ = [
    # install
    "ComputeInstallation",
    "install_compute",
    "ComputeHandler",
    # types — the 33 type-path constants, flat. HISTORY settled this (D16,
    # `[sdk_surface]`): flat names are the contract in every port and a grouped object is an
    # alias, never the other way round. CONTENT paid 18 drift entries for learning it the
    # other way.
    "LITERAL",
    "LOOKUP_SCOPE",
    "LOOKUP_TREE",
    "LOOKUP_HASH",
    "APPLY",
    "IF",
    "LET",
    "LAMBDA",
    "ARITHMETIC",
    "COMPARE",
    "LOGIC",
    "FIELD",
    "CONSTRUCT",
    "INDEX",
    "LENGTH",
    "NUMERIC_CAST",
    "CLOSURE",
    "SCOPE",
    "SCOPE_BINDING",
    "RESULT",
    "ERROR",
    "SUBGRAPH",
    "INSTALL_REQUEST",
    "INSTALL_RESULT",
    "MAP_ARGS",
    "FILTER_ARGS",
    "FOLD_ARGS",
    "RANGE_ARGS",
    "GROUP_BY_ARGS",
    "GROUP",
    "CONCAT_ARGS",
    "ASSOC_ARGS",
    "STORE_ARGS",
    # the three collections
    "CORE_EXPRESSION_TYPES",
    "INLINE_EXPRESSION_TYPES",
    "ALL_TYPES",
    # paths and limits
    "COMPUTE_PATTERN",
    "BUILTINS_PREFIX",
    "PROCESSES_PREFIX",
    "DEFAULT_MAX_OPS",
    "DEFAULT_MAX_DEPTH",
    "RECOMMENDED_MAX_CASCADE_DEPTH",
    # §9.1's sixteen codes
    "CODE_BUDGET_EXHAUSTED",
    "CODE_DEPTH_EXCEEDED",
    "CODE_TYPE_MISMATCH",
    "CODE_DIVISION_BY_ZERO",
    "CODE_NOT_FOUND",
    "CODE_UNKNOWN_TYPE",
    "CODE_MISSING_ARGUMENT",
    "CODE_INVALID_EXPRESSION",
    "CODE_CASCADE_LIMIT",
    "CODE_PERMISSION_DENIED",
    "CODE_INSTALLATION_GRANT_INVALID",
    "CODE_INDEX_OUT_OF_RANGE",
    "CODE_CAST_OUT_OF_RANGE",
    "CODE_COUNT_OUT_OF_RANGE",
    "CODE_SCOPE_UNREACHABLE",
    "CODE_AMBIGUOUS_RESOURCE",
    # operations
    "is_compute_expression",
    "is_compute_type",
    "compute_type_defs",
    "compute_type_entities",
    "publish_compute_types",
    "compute_entity",
    # sdk
    "ComputeEvaluator",
    "EvalOutcome",
    "EvaluatorLimits",
    "DEFAULT_LIMITS",
    "assert_not_builtin_override",
    "CAPABILITY_CHECK_IS_DISPATCH_SCOPED",
    # §7
    "ReactiveEngine",
    "deterministic_id",
]
