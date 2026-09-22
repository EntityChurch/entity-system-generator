"""COMPUTE §7 — reactive mode: the dependency index (§7.1), the re-evaluation trigger (§7.2)
and the cascade bound (§7.3).

**THE EMIT CONSUMER THAT WRITES BACK, and this port had to re-measure both peer properties it
rests on rather than inherit them.** COMPUTE's ``emit_consumer`` face is not a recorder like
HISTORY's — it is the seam by which a tree write RE-ENTERS the evaluator and writes back. Two
properties of the substrate become load-bearing, §7.2 pins neither (§9.4 leaves emit delivery
implementation-defined), and on this peer they are decided by
:class:`entity_core.peer.store.Store`:

 1. **Delivery is sync-inline.** ``Store.bind`` snapshots the consumer list under its lock,
    releases the lock, then calls every consumer before returning. So by the time the oracle's
    ``tree:put`` of ``A1 = 25`` has answered, ``B1/result`` already holds ``50``. An async bus
    would make every §7.2 vector a race. Same verdict as `typescript`, reached through a
    different mechanism: **that peer has no lock to release and this one deliberately fires
    outside it**, which is the same sentence that makes property 2 safe here.
 2. **A write from inside a consumer re-enters the bus.** That is what makes a cascade a
    cascade (§7.2's *"subgraph A's result write notifies the emit pipeline, which triggers
    subgraph B"*) — and it is why §7.3's bound is not decoration: on a sync-inline bus an
    unbounded cascade is unbounded RECURSION. **On this peer it does not deadlock**, and that
    is a real difference from the naive reading: ``Store``'s docstring states the rule it was
    built to — *"emit consumers are invoked OUTSIDE the lock … so a consumer never re-enters
    the store while it is held"* — so re-entrancy costs stack, not liveness. A peer that fired
    consumers under its lock would hang here instead of overflowing, and a hang after the
    measurement is indistinguishable from a hang before it (AP-21).

**What is deliberately NOT here: a second evaluator.** Re-evaluation runs the same
:class:`~entity_compute.sdk.ComputeEvaluator` the handler's ``eval`` runs, with a different
authority and a different budget. §7.2's only semantic additions are the grant check, the
convergence check and the freeze; every one of those is in this file and none of them is in
the evaluator.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from entity_core.peer.capability import check_path_permission
from entity_core.peer.model import Entity
from entity_core.peer.store import ExecContext

from ..sdk import ComputeEvaluator, EvaluatorLimits
from ..types import (
    CODE_CASCADE_LIMIT,
    CODE_INSTALLATION_GRANT_INVALID,
    COMPUTE_PATTERN,
    ERROR,
    PROCESSES_PREFIX,
    RECOMMENDED_MAX_CASCADE_DEPTH,
    RESULT,
    SUBGRAPH,
    is_compute_expression,
)
from .evaluator import canonicalize_path
from .subgraph import AuditContext, AuditRefusal, SubgraphAudit, audit_subgraph

#: The re-entrancy backstop's bound. Twice the cascade limit, so it can only fire where the
#: spec's own counter has already failed to move — which is the error-write path (§7.2 passes
#: the context unchanged there) and nothing else.
_REENTRY_LIMIT = RECOMMENDED_MAX_CASCADE_DEPTH * 2

_CAPABILITY_TOKEN = "system/capability/token"


class _DependencyIndex:
    """§7.1's dependency index — ``path -> (expression_uri, subgraph_path)``.

    **EXACT-MATCH, and the section says so twice.** :meth:`match` returns entries whose
    registered path EQUALS the written one; a write at ``app/data/sheet1/cells/A1`` does NOT
    wake an expression depending on ``app/data/sheet1``. A prefix index here would make more
    programs appear to work and would be wrong — §7.1 names the three compositions
    (content-addressed parent, subscription + aggregation, history query) an application uses
    instead, precisely so compute needs no subtree primitive.

    Comparison is on canonical absolute-at-rest paths. Registration canonicalizes through the
    same function the evaluator's ``compute/lookup/tree`` arm uses, and the peer's tree writes
    on canonical paths, so the two sides cannot drift.
    """

    __slots__ = ("_by_path", "_by_subgraph")

    def __init__(self) -> None:
        self._by_path: dict[str, list[tuple[str, str]]] = {}
        self._by_subgraph: dict[str, list[str]] = {}

    def add(self, path: str, expression_uri: str, subgraph_path: str) -> None:
        entries = self._by_path.setdefault(path, [])
        if not any(sp == subgraph_path for _, sp in entries):
            entries.append((expression_uri, subgraph_path))
        paths = self._by_subgraph.setdefault(subgraph_path, [])
        if path not in paths:
            paths.append(path)

    def match(self, path: str) -> list[tuple[str, str]]:
        return list(self._by_path.get(path, ()))

    def remove_subgraph(self, subgraph_path: str) -> None:
        paths = self._by_subgraph.pop(subgraph_path, None)
        if paths is None:
            return
        for path in paths:
            entries = self._by_path.get(path)
            if entries is None:
                continue
            kept = [e for e in entries if e[1] != subgraph_path]
            if kept:
                self._by_path[path] = kept
            else:
                del self._by_path[path]

    @property
    def size(self) -> int:
        """Diagnostics only — the count of registered (path, subgraph) pairs."""
        return sum(len(entries) for entries in self._by_path.values())

    @property
    def watched_paths(self) -> tuple[str, ...]:
        return tuple(self._by_path.keys())


class ReactiveEngine:
    """The §7 engine: a tree-change consumer that owns the dependency index.

    One instance per peer, created by :func:`~entity_compute.install_compute` and handed to the
    handler, so §3.3's Phase 4 (``register_subgraph_dependencies``) and §7.2's trigger are the
    same object's two halves rather than two structures that have to agree.

    **Registered as a BOUND METHOD, not as an object.** This peer's emit bus takes
    ``Callable[[TreeEvent], None]`` (``Store.register_tree_consumer``) where `typescript`'s
    takes an ``EmitConsumer`` with ``onTreeChange`` and ``onContentStore``. So there is no
    ``on_content_store`` here — and its absence is the same decision that file makes
    explicitly with an empty method: §7.1 registers TREE paths, a content-store put has no
    path and therefore no index key, and an implementation that reacted there would fire on
    every entity the evaluator itself materializes. D19's shape — an instrument does not read
    a quantity its own execution writes; here, does not TRIGGER on one.
    """

    name = "compute"

    __slots__ = ("_peer", "_limits", "_index", "_reentry")

    def __init__(self, peer: Any, limits: EvaluatorLimits) -> None:
        self._peer = peer
        self._limits = limits
        self._index = _DependencyIndex()
        #: §7.3's bound, as a RE-ENTRANCY counter, beside the context-carried one.
        #:
        #: **Two bounds, because they fail in different places.** ``cascade_depth`` travels on
        #: the execution context and is the spec's mechanism — it survives a hop through
        #: another handler and across peers (SYSTEM-COMPOSITION §3.4). This counter does not
        #: travel and measures something else: how deep inside ``Store.bind`` we currently
        #: are. It exists because §7.2's ERROR write passes the context **unchanged** — the
        #: pseudocode increments only on the converged-result path — so a subgraph whose error
        #: result feeds its own dependency would recurse with a cascade depth that never
        #: moves. On a sync-inline bus that is a ``RecursionError`` rather than a runaway
        #: loop, and a peer that dies is a worse answer than a frozen subgraph.
        self._reentry = 0

    # ── §7.2 `on_tree_change` ────────────────────────────────────────────────────

    def on_tree_change(self, ev: Any) -> None:
        """§7.2 ``on_tree_change``. The signature this peer's bus calls."""
        entries = self._index.match(ev.path)
        if not entries:
            return

        context = getattr(ev, "context", None)

        if self._reentry >= _REENTRY_LIMIT:
            for _, subgraph_path in entries:
                self._freeze(subgraph_path, CODE_CASCADE_LIMIT, context)
            return

        depth = _cascade_depth(context)
        self._reentry += 1
        try:
            for expression_uri, subgraph_path in entries:
                subgraph = self._peer.store.get_at(subgraph_path)
                if subgraph is None or subgraph.type != SUBGRAPH:
                    # §7.2: uninstalled out from under us — clean the stale registration.
                    self._index.remove_subgraph(subgraph_path)
                    continue
                if subgraph.text("status") == "frozen":
                    continue
                if depth >= RECOMMENDED_MAX_CASCADE_DEPTH:
                    self._freeze(subgraph_path, CODE_CASCADE_LIMIT, context)
                    continue
                self._re_evaluate(expression_uri, subgraph_path, subgraph, context, depth)
        finally:
            self._reentry -= 1

    # ── §3.3 Phase 4 / §7.1 `register_subgraph_dependencies` ─────────────────────

    def register(self, subgraph_path: str, expression_uri: str, audit: SubgraphAudit) -> None:
        """Register every tree dependency of the expression against ``subgraph_path``.

        ``audit.read_paths`` comes from the SAME walk §3.3 Phase 1 ran — see ``subgraph.py``.
        That is §7.1's *"Implementations MAY factor them into one walker"*, taken up because
        the alternative is two walkers with one ``[MUST]`` between them and no instrument able
        to say they disagree.
        """
        self._index.remove_subgraph(subgraph_path)  # re-install replaces, never accumulates.
        for path in audit.read_paths:
            self._index.add(path, expression_uri, subgraph_path)

    def unregister(self, subgraph_path: str) -> None:
        self._index.remove_subgraph(subgraph_path)

    def rebuild(self) -> int:
        """§7.1's ``rebuild_dependency_index`` — scan ``system/compute/processes/*`` and
        re-register from the CURRENT expression at each root path.

        Called at install time rather than only at restart, because this port holds the index
        in memory and an in-process composition never restarts. It is here because §7.1 MUSTs
        it and because it is the one path that reads the metadata back rather than trusting
        what install put in memory.
        """
        prefix = canonicalize_path(PROCESSES_PREFIX, self._peer.local_peer)
        n = 0
        # `Store.listing` yields one level of SEGMENTS, not paths — the full path is rebuilt
        # here. Reading the segment as a path is the kind of near-miss that produces an index
        # of zero entries and a clean-looking verdict.
        for row in self._peer.store.listing(prefix):
            path = prefix + "/" + row.segment
            subgraph = self._peer.store.get_at(path)
            if subgraph is None or subgraph.type != SUBGRAPH:
                continue
            # §7.1: read the CURRENT expression at the tree path, not the hash recorded at
            # installation. `root_expression` is the audit record; the expression may have been
            # modified since, and the per-operation checks catch an unauthorized one at
            # evaluation time.
            root_path = subgraph.text("root_expression_path")
            if root_path is None:
                continue
            expression = self._peer.store.get_at(root_path)
            if expression is None or not is_compute_expression(expression.type):
                continue
            audit = audit_subgraph(expression, root_path, self._audit_context())
            if isinstance(audit, AuditRefusal):
                continue
            self.register(path, root_path, audit)
            n += 1
        return n

    @property
    def registered_dependencies(self) -> int:
        """Diagnostics for the composition's startup line and for our own tests."""
        return self._index.size

    @property
    def watched_paths(self) -> tuple[str, ...]:
        return self._index.watched_paths

    def evaluate_now(self, subgraph_path: str, context: Any) -> bytes | None:
        """§3.3's *"Implementations SHOULD … perform an initial evaluation after
        installation"*, reachable from the handler so install and re-install take the same
        path. Returns the result hash written, or None when nothing was written.
        """
        subgraph = self._peer.store.get_at(subgraph_path)
        if subgraph is None or subgraph.type != SUBGRAPH:
            return None
        expression_uri = subgraph.text("root_expression_path")
        if expression_uri is None:
            return None
        return self._re_evaluate(
            expression_uri, subgraph_path, subgraph, context, _cascade_depth(context)
        )

    # ── §7.2 `re_evaluate` ───────────────────────────────────────────────────────

    def _re_evaluate(
        self,
        expression_uri: str,
        subgraph_path: str,
        subgraph: Entity,
        context: Any,
        depth: int,
    ) -> bytes | None:
        result_path = subgraph.text("result_path")
        if result_path is None:
            return None

        # §7.2 — the installation grant must still be available and unexpired. Revocation is
        # NOT checked here and that is the spec's own ruling: `verify_request`
        # (ENTITY-CORE-PROTOCOL §5.2 step 4) catches it on the first dispatched impure op, and
        # the resulting error freezes the subgraph through the ordinary path. Calling
        # `_is_revoked` here would be a permitted fail-fast optimization and nothing more —
        # and on this peer it is private anyway.
        grant_hash = subgraph.bytes_("installation_grant")
        grant = None if grant_hash is None else self._peer.store.get_by_hash(grant_hash)
        if grant is not None and not _is_capability(grant):
            grant = None
        if grant is None or _is_expired(grant, self._peer.now_millis()):
            self._freeze(subgraph_path, CODE_INSTALLATION_GRANT_INVALID, context)
            return None

        expression = self._peer.store.get_at(expression_uri)
        if expression is None:
            # §7.2: the expression is gone. The subgraph metadata survives; the registrations
            # do not, because there is nothing left to wake.
            self._index.remove_subgraph(subgraph_path)
            return None

        local_peer = self._peer.local_peer
        limits = _reactive_budget(grant, self._limits)
        evaluator = ComputeEvaluator(self._peer, limits)
        outcome = evaluator.evaluate_at(
            expression,
            expression_uri,
            # §7.2's *"Authorization source"*: the installation grant authorizes every impure
            # operation, and it was verified at install to cover all of them. **BOTH of this
            # port's entry points narrow per path** — the handler's `eval` from the caller's
            # token, this one from the grant — because this peer publishes
            # `check_path_permission` (our own H9, closed). See
            # `sdk.CAPABILITY_CHECK_IS_DISPATCH_SCOPED` for why the constant is still False.
            can_read_path=lambda path: check_path_permission(
                "get", path, grant, "system/tree", local_peer
            ),
            can_write_path=lambda path: check_path_permission(
                "put", path, grant, "system/tree", local_peer
            ),
            # §4.2 Tier 2 — the set §3.3 Phase 2b SEALED. This is the first composition on this
            # port in which it is non-empty, and it is why `authorized_data_hashes` is a field
            # on the metadata rather than a local of the install call.
            authorized_data_hashes=_authorized_hashes(subgraph),
        )

        if outcome.error is not None:
            # §7.2's reactive error handling: the error entity IS the result. It is written
            # with the incoming context — the pseudocode increments only on the converged path
            # — and the subgraph stays ACTIVE. A budget exhaustion may be transient (§7.3), and
            # freezing on every evaluation error would make an error a permanent state that
            # only re-installation clears.
            result = outcome.error.to_entity()
            self._write(result_path, result, context)
            return result.hash

        result = _result_entity(outcome.value, expression)

        # §7.2's convergence check. Same hash -> no write -> no event -> no cascade.
        #
        # **THE TREE WOULD ALSO SUPPRESS AN IDENTICAL BIND, AND THAT IS WHY THIS ASSERTION IS
        # NOT THE ONE OUR TESTS REST ON** (AP-33 / D15's sharpened clause): `Store.bind`
        # computes `changed = prev != nxt` and fires nothing when the hash is unmoved, so a
        # test observing "no bind event" passes with this check DELETED. The layer that owns
        # the property here is the peer, not us, and §7.2 addresses us — §9.4 leaves delivery
        # impl-defined, so a peer whose `bind` emits unconditionally cascades forever on a
        # converged subgraph. Doing it here is what makes the NON-write observable to this
        # function, which is the only assertion the subject alone can satisfy: `_re_evaluate`
        # returns None on convergence and a hash otherwise, and nothing in the substrate can
        # produce that return value on our behalf.
        previous = self._peer.store.hash_at(result_path)
        if previous and previous == result.hash.hex():
            return None
        self._write(result_path, result, context, cascade_depth=depth + 1)
        return result.hash

    def _freeze(self, subgraph_path: str, code: str, context: Any) -> None:
        """§7.2's freeze: a code-only ``compute/error`` at the result path, ``status:
        "frozen"`` on the metadata. Recovery is re-installation (§3.3), which is the only
        thing that clears it — deliberately, because both conditions that reach here
        (``cascade_limit`` and ``installation_grant_invalid``) are structural and retrying
        changes nothing.
        """
        subgraph = self._peer.store.get_at(subgraph_path)
        if subgraph is None or subgraph.type != SUBGRAPH:
            return
        result_path = subgraph.text("result_path")
        if result_path is not None:
            # §2.4 — the materialized form is CODE-ONLY. `message` and `at` are in-flight
            # diagnostics; putting one in a tree-written entity forks the content hash across
            # two conformant peers.
            self._write(result_path, Entity.make(ERROR, {"code": code}), context)
        self._write(subgraph_path, _with_status(subgraph, "frozen"), context)

    def _write(self, path: str, entity: Entity, context: Any, cascade_depth: int | None = None) -> None:
        self._peer.store.bind(path, entity, self._exec_context(context, cascade_depth))

    def _exec_context(self, context: Any, cascade_depth: int | None = None) -> ExecContext:
        """The execution context our writes carry.

        ``chain_id`` is INHERITED and never regenerated — SYSTEM-COMPOSITION §3.4 makes that a
        composition-level invariant, and it is the field a cross-peer cascade is traced by.
        ``author`` is the local peer, because §7.2 evaluates as ``local_peer_identity``;
        ``caller_capability`` is deliberately dropped rather than inherited, because the
        authority for this write is the installation grant and not whoever happened to touch
        the dependency.

        ``handler_grant`` is left None rather than set to the installation grant, and the
        reason is cross-port rather than semantic: the grant IS the authority §7.2 names, so
        recording it would be defensible — but `typescript`'s ``EmitContext`` has no such slot
        (its §6.8a shape carries ``callerCapability`` and not a handler grant), so setting it
        here would make one HISTORY recorder in a two-extension composition attribute the same
        reactive write two ways depending on the port. Declared in
        ``EXTENSION.toml [substrate].exec_context_handler_grant``.
        """
        inherited_depth = cascade_depth if cascade_depth is not None else _cascade_depth_or_none(context)
        return ExecContext(
            request_id=getattr(context, "request_id", "") or "",
            handler_pattern=COMPUTE_PATTERN,
            operation="eval",
            author=self._peer.identity.identity_hash,
            caller_capability=None,
            handler_grant=None,
            chain_id=getattr(context, "chain_id", None),
            parent_chain_id=getattr(context, "parent_chain_id", None),
            cascade_depth=inherited_depth,
        )

    def _audit_context(self) -> AuditContext:
        return AuditContext(
            store=self._peer.store,
            local_peer=self._peer.local_peer,
            included={},
            author=None,
        )


def _cascade_depth(context: Any) -> int:
    """SYSTEM-COMPOSITION §3.1 — an absent counter is depth 0, never "unknown"."""
    depth = getattr(context, "cascade_depth", None)
    return depth if isinstance(depth, int) and not isinstance(depth, bool) else 0


def _cascade_depth_or_none(context: Any) -> int | None:
    depth = getattr(context, "cascade_depth", None)
    return depth if isinstance(depth, int) and not isinstance(depth, bool) else None


def _is_capability(entity: Entity) -> bool:
    """The `python` stand-in for `typescript`'s ``new CapabilityToken(entity)`` throwing.

    That peer validates on construction; here a token is a bare ``Entity``, so the same
    question is the type plus the one field §5.2's scope match reads. Anything else — chain
    verification, signature, temporal representability — is the DISPATCHER's job and was done
    at install; re-doing a subset of it here would be a second reading of core §5.2 inside an
    extension (D12 / L18).
    """
    return entity.type == _CAPABILITY_TOKEN and isinstance(entity.field("grants"), list)


def _is_expired(grant: Entity, now_ms: int) -> bool:
    """§7.2's ``is_expired`` — ``expires_at`` against the peer clock."""
    expires_at = grant.uint("expires_at")
    return expires_at is not None and expires_at < now_ms


def _reactive_budget(grant: Entity, limits: EvaluatorLimits) -> EvaluatorLimits:
    """§7.4 ``reactive_budget`` — fresh and independent, bounded by the installation grant's
    ``constraints["system/compute"]``, falling back to the peer defaults (§9.3).

    **The constraint lives on the GRANT ENTRY, not on the token**, and §5.2/§5.5 both spell it
    ``capability.data.constraints["system/compute"]``. ``ENTITY-CORE-PROTOCOL`` §5 carries
    ``constraints`` on each entry of ``grants``, which is where both our peers parse it from
    and where a delegation preserves it byte-equal. Reading the tightest value across the
    entries is the only choice that cannot widen a grant. Routed as A-21.
    """
    operations = limits.max_operations
    depth = limits.max_depth
    grants = grant.field("grants")
    if not isinstance(grants, list):
        return limits
    for entry in grants:
        if not isinstance(entry, dict):
            continue
        constraints = entry.get("constraints")
        if not isinstance(constraints, dict):
            continue
        compute = constraints.get(COMPUTE_PATTERN)
        if not isinstance(compute, dict):
            continue
        ops = _opt_uint(compute, "max_compute_operations")
        if ops is not None:
            operations = min(operations, ops)
        d = _opt_uint(compute, "max_compute_depth")
        if d is not None:
            depth = min(depth, d)
    return EvaluatorLimits(max_operations=operations, max_depth=depth)


def _opt_uint(value: dict, key: str) -> int | None:
    found = value.get(key)
    if isinstance(found, bool) or not isinstance(found, int) or found < 0:
        return None
    return found


def _authorized_hashes(subgraph: Entity) -> frozenset[str]:
    """§4.2 Tier 2 — the sealed set, as hex, from the metadata's seventh field."""
    field = subgraph.field("authorized_data_hashes")
    if not isinstance(field, list):
        return frozenset()
    return frozenset(
        bytes(item).hex() for item in field if isinstance(item, (bytes, bytearray))
    )


def _result_entity(value: Any, expression: Entity) -> Entity:
    """§2.4 — a primitive result is wrapped in a ``compute/result`` carrying the SOURCE
    EXPRESSION's hash; an entity result travels as itself.

    Identical to the handler's ``eval`` return, and that identity is the point: a caller
    reading ``{root}/result`` after a reactive update and a caller reading the response of an
    explicit ``eval`` are looking at the same bytes for the same expression.
    """
    if isinstance(value, Entity):
        return value
    return Entity.make(RESULT, {"value": value, "expression": expression.hash})


def _with_status(subgraph: Entity, status: str) -> Entity:
    data = dict(subgraph.data) if isinstance(subgraph.data, dict) else {}
    data["status"] = status
    return Entity.make(SUBGRAPH, data)


_BASE32_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"


def deterministic_id(root_path: str) -> str:
    """§3.3's ``deterministic_id`` — ``base32_lower_no_padding(sha256(utf8_bytes(root_path)))``.

    **The SHA-256 here is NOT a ``content_hash_format`` dispatch site**, and v7.68 pins that
    explicitly: the ``subgraph_id`` is a deterministic path-segment identifier, not part of the
    content-address space, so every implementation uses SHA-256 regardless of its configured
    hash format — precisely so cross-peer subgraph inspection works in a mixed-format cohort.
    Using the peer's configured hash function here would look more consistent and would break
    the property the clause exists to protect.

    **The alphabet is RFC 4648 base32, lowercased, and that identity is load-bearing rather
    than a convenience.** `typescript` hand-rolls the 5-bit encoder over the same alphabet;
    this uses the stdlib and lowercases. Two implementations of one encoding is two places for
    it to differ, and §3.3's cross-peer discoverability clause means a difference is a subgraph
    nobody can find — so ``test/test_reactive.py`` pins a fixed vector rather than asserting
    the shape.
    """
    digest = hashlib.sha256(root_path.encode("utf-8")).digest()
    return base64.b32encode(digest).decode("ascii").lower().rstrip("=")
