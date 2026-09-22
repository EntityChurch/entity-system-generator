"""COMPUTE §3.3 ``audit_subgraph`` and §7.1 ``walk_tree_lookups`` — **ONE walker.**

§3.3 permits this in as many words (*"Implementations MAY factor them into one walker with
multiple visitors"*), and here it is not an optimisation, it is the only way to get the
right answer. The two listings disagree, and the one that is wrong is the one that
authorizes:

===========================================  ====================  ====================
                                             §3.3 ``audit_walk``   §7.1 ``walk``
===========================================  ====================  ====================
descends a scalar ``system/hash`` field       yes                   yes
descends into ``apply.args``/``let.bindings`` **NO**                yes, ``[MUST, v3.27]``
===========================================  ====================  ====================

v3.27 promoted §7.1's *"all ``compute/lookup/tree`` paths reachable in the expression graph
are registered"* from a description to a ``[MUST]`` **and rewrote its walker to descend
containers** — and §3.3's walker, four sections earlier and sharing the same paragraph of
prose, was not touched. A literal transcription of §3.3 therefore capability-checks a tree
read at the top level of an expression and **skips the same read one function-argument
deep**, which is an authorization hole rather than a coverage one. Routed to arch as A-17.

Two further clauses this file implements that §3.3's listing does not carry, both MUST-ed
elsewhere in the same document:

 - **Q23** (§2.1, ``[MUST]``, and §2.1 says *"it is enforced at install time too"*): a
   builtin-path ``compute/apply`` carrying ``capability`` or ``resource`` is
   ``invalid_expression``. §3.3's listing fail-fasts F5 and installs this shape clean,
   which §2.1's own words call *"internally inconsistent"*. A-18.
 - **SA-11** (§3.3's own subgraph-boundary paragraph): the pure collection builtins
   *"require no install-time handler-target authorization grant"*. §3.3's listing appends
   **every** builtin apply to ``handler_targets``, so under a narrow grant the prose admits
   a ``map`` and the pseudocode rejects it. A-19.

Nothing here evaluates. The audit is a static walk over the expression graph; a value only
knowable at runtime (a dynamic ``store`` path, a dynamic capability) is deliberately left to
the runtime check, which is §3.3's declared conservative-static / runtime-dynamic split.

WHERE THIS PORT DIFFERS FROM ITS SIBLING, and both differences are the substrate
-------------------------------------------------------------------------------
 1. **A capability is an ``Entity``, not a ``CapabilityToken``.** `typescript` has a token
    class exposing ``.grants`` / ``.granter`` / ``.parent`` / ``.expiresAt``; here the token
    IS the entity and the fields are read with ``.bytes_()`` / ``.field()``. So
    :func:`grant_covers` cannot iterate grant records — see its docstring for what it calls
    instead, and why re-transcribing the walk was not an option (HISTORY paid for that
    lesson: 23 of 34 oracle checks denied).
 2. **A resource target is a plain map.** `typescript` parses one into a ``ResourceTarget``
    and can fail; here ``{"targets": [...], "exclude": [...]}`` is the value the peer's own
    ``_check_resource_scope`` reads, so the audit carries the dict through unchanged and
    there is no parse to fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from entity_core.peer.capability import (
    MAX_CHAIN_DEPTH,
    cap_resolve,
    check_permission,
    resolve_granter_peer_id,
)
from entity_core.peer.model import Entity
from entity_core.peer.wire import empty_params, make_execute

from ..types import (
    APPLY,
    BUILTINS_PREFIX,
    CODE_INVALID_EXPRESSION,
    LITERAL,
    LOOKUP_HASH,
    LOOKUP_TREE,
    is_compute_type,
)
from .evaluator import CONTENT_HASH_LENGTH, canonicalize_path, clean_path

_STORE_BUILTIN = BUILTINS_PREFIX + "/store"


@dataclass(frozen=True, slots=True)
class HandlerTarget:
    """§3.3 Phase 1's ``handler_targets`` entry. ``resource`` is None when dynamic or absent."""

    path: str
    operation: str | None
    resource: Any


@dataclass(frozen=True, slots=True)
class DataHashRef:
    """§3.3 Phase 2b's ``data_hashes`` entry (v3.7 D3/D6). ``path`` is the hint, or None."""

    hash: bytes
    path: str | None


@dataclass(frozen=True, slots=True)
class SubgraphAudit:
    """What one walk produced.

    **``read_paths`` serves §3.3's ``read_paths`` AND §7.1's ``deps``, and that is a
    deliberate identification rather than a shortcut.** The two listings differ by one
    canonicalization on the absolute form — §7.1 canonicalizes so the dependency matches the
    absolute-at-rest path a tree write notifies on, §3.3 does not because
    ``check_path_permission`` canonicalizes internally. Canonicalizing once, here, makes both
    correct and removes the place they could drift.
    """

    read_paths: tuple[str, ...] = ()
    handler_targets: tuple[HandlerTarget, ...] = ()
    write_paths: tuple[str, ...] = ()
    data_hashes: tuple[DataHashRef, ...] = ()


@dataclass(frozen=True, slots=True)
class AuditRefusal:
    """A refusal carrying the status/code pair §3.3 names for it. Never raised."""

    status: int
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class AuditContext:
    """What the audit reads. No budget, no scope: nothing here evaluates."""

    store: Any
    local_peer: str
    #: §4.2 step 1 — the EXECUTE envelope's ``included`` map, keyed by lowercase hex.
    included: dict
    #: ``ctx.execute.data.author`` — the installer's identity hash, for CP1.
    author: bytes | None


@dataclass(slots=True)
class _WalkState:
    root_path: str
    ctx: AuditContext
    visited: set[str] = field(default_factory=set)
    read_paths: list[str] = field(default_factory=list)
    handler_targets: list[HandlerTarget] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    data_hashes: list[DataHashRef] = field(default_factory=list)


def audit_subgraph(root: Entity, root_path: str, ctx: AuditContext) -> SubgraphAudit | AuditRefusal:
    """§3.3 Phase 1 — walk the expression graph from ``root`` and collect the four
    categories, or refuse on a static structural error.

    ``root_path`` is the resolution prefix for ``relative: true`` paths (§2.1) and MUST be the
    canonical absolute form; the caller canonicalizes once, at the EXECUTE boundary, so this
    function never has to decide.
    """
    st = _WalkState(root_path=root_path, ctx=ctx)
    refusal = _walk_node(root, st)
    if refusal is not None:
        return refusal
    return SubgraphAudit(
        read_paths=tuple(st.read_paths),
        handler_targets=tuple(st.handler_targets),
        write_paths=tuple(st.write_paths),
        data_hashes=tuple(st.data_hashes),
    )


def _walk_node(entity: Entity, st: _WalkState) -> AuditRefusal | None:
    # §3.3's cycle detection, keyed on the content hash exactly as the listing is.
    hex_ = entity.hash.hex()
    if hex_ in st.visited:
        return None
    st.visited.add(hex_)

    if entity.type == LOOKUP_TREE:
        st.read_paths.append(_lookup_path(entity, st))
        return None  # §3.3: a lookup is a leaf — its `path` is text, not a reference.

    if entity.type == LOOKUP_HASH:
        # v3.7 D3/D6. The `hash` field points at arbitrary DATA, not at an expression, so
        # this arm returning early is what keeps the generic descent below from treating a
        # data reference as a sub-expression to audit.
        hash_ = entity.bytes_("hash")
        if hash_ is None:
            return AuditRefusal(400, CODE_INVALID_EXPRESSION, "compute/lookup/hash requires a hash field")
        hint = entity.text("path")
        relative = entity.field("relative") is True
        if hint is None:
            resolved_hint = None
        elif relative:
            resolved_hint = clean_path(st.root_path + "/" + hint)
        else:
            resolved_hint = hint
        st.data_hashes.append(DataHashRef(hash=hash_, path=resolved_hint))
        return None

    if entity.type == APPLY:
        refusal = _audit_apply(entity, st)
        if refusal is not None:
            return refusal
        # and FALL THROUGH — §3.3's listing recurses into an apply's fields after collecting
        # its target, which is how a `lookup/tree` inside `args` is reached.

    # §7.1's `walk_value`, applied to §3.3's walk as well. THIS LOOP IS A-17: §3.3's own
    # listing tests `if field_value is system/hash` and descends no container.
    if not isinstance(entity.data, dict):
        return None  # data is not a map — nothing to descend into, and not an error.
    for value in entity.data.values():
        refusal = _walk_value(value, st)
        if refusal is not None:
            return refusal
    return None


def _walk_value(value: Any, st: _WalkState) -> AuditRefusal | None:
    if isinstance(value, (bytes, bytearray)):
        if len(value) != CONTENT_HASH_LENGTH:
            return None
        referenced = _lookup_entity(bytes(value), st.ctx)
        # §3.3's *"Audit scope (normative)"*: a hash that resolves to a NON-compute entity is
        # skipped. This is also what stops a `compute/literal` whose value happens to be a
        # 33-byte capability hash (CP1's shape) from being walked.
        if referenced is None or not is_compute_type(referenced.type):
            return None
        return _walk_node(referenced, st)
    if isinstance(value, list):
        for item in value:
            refusal = _walk_value(item, st)
            if refusal is not None:
                return refusal
        return None
    if isinstance(value, dict):
        for member in value.values():
            refusal = _walk_value(member, st)
            if refusal is not None:
                return refusal
        return None
    return None


def _audit_apply(entity: Entity, st: _WalkState) -> AuditRefusal | None:
    """§3.3's ``compute/apply`` arm — Q23, F5, CP1, F3, then the ``store`` write target.

    **The order is normative and each step is presence-only or static-literal-only.** Q23
    first because §2.1 makes it a SHAPE check that runs before any field is resolved; CP1
    before F3 because §3.3 says so in a comment that also says why (chain-root is cheaper and
    more fundamental than scope coverage).
    """
    path = entity.text("path")
    if path is None:
        return None  # closure mode — nothing to authorize.

    has_capability = entity.bytes_("capability") is not None
    has_resource = entity.bytes_("resource") is not None
    builtin = _builtin_name(path)

    # Q23 (§2.1) — a builtin dispatches no EXECUTE, so neither field has a referent.
    if builtin is not None and (has_capability or has_resource):
        return AuditRefusal(
            400,
            CODE_INVALID_EXPRESSION,
            "compute/apply on a builtin path MUST NOT carry capability or resource "
            "(§2.1 Q23, install-time)",
        )

    # F5 (v3.10) — a capability override with no resource cannot be dual-checked.
    if has_capability and not has_resource:
        return AuditRefusal(
            400,
            CODE_INVALID_EXPRESSION,
            "compute/apply with capability field MUST also have resource field (§2.1 F5)",
        )

    # CP1 (v3.11) — a STATIC-LITERAL embedded capability must have the installer in its
    # authority chain. A dynamic capability is deferred to the runtime dual-check.
    if has_capability:
        refusal = _check_embedded_capability(entity, st)
        if refusal is not None:
            return refusal

    # F3 (v3.10) — a static-literal resource is audited; a dynamic one is deferred.
    resource: Any = None
    if has_resource:
        literal = _resolve_literal(entity.bytes_("resource"), st.ctx)
        if literal is not None:
            value = literal.field("value")
            # A resource target is a plain `{targets: [...]}` map on this peer — the shape
            # the peer's own scope check reads. There is no struct to parse and therefore no
            # parse to fail, which is the one place `typescript` needs a try/catch here.
            if isinstance(value, dict) and isinstance(value.get("targets"), list):
                resource = value

    # SA-11, and this is A-19: **no builtin path is ever a handler target.** §3.3's listing
    # appends every apply-with-a-path unconditionally; the same section's prose says the pure
    # collection builtins *"require no install-time handler-target authorization grant"* and
    # that *"only `store` is authorization-gated at install time, VIA ITS `write_path`"*.
    # Those are the same sentence read twice: a builtin dispatches no EXECUTE (§2.1 Q23's own
    # premise), so there is no handler+operation pair for a grant to cover, and demanding one
    # would reject a legal `map` under any grant narrower than `*`.
    if builtin is None:
        st.handler_targets.append(
            HandlerTarget(path=path, operation=entity.text("operation"), resource=resource)
        )

    # §3.3's `store` special case: a LITERAL path argument becomes a static write target. A
    # computed one is not knowable here and is checked at the store site.
    if _relative_pattern(path) == _STORE_BUILTIN:
        args = entity.field("args")
        if isinstance(args, dict):
            path_arg = args.get("path")
            if isinstance(path_arg, (bytes, bytearray)) and len(path_arg) == CONTENT_HASH_LENGTH:
                literal = _resolve_literal(bytes(path_arg), st.ctx)
                if literal is not None:
                    target = literal.field("value")
                    if isinstance(target, str):
                        st.write_paths.append(target)
    return None


def _check_embedded_capability(entity: Entity, st: _WalkState) -> AuditRefusal | None:
    """CP1 / §10.1 — *"the install audit MUST verify that ``ctx.execute.data.author`` appears
    **as a granter anywhere in** the static-literal ``compute/apply.capability`` authority
    chain … in-chain, NOT rooted-at-author."*

    **In-chain and not chain-root is the whole content of this function**, and the distinction
    is not academic: a dispatch capability minted by a client is parented at the CONNECTION
    capability, whose granter is the REMOTE peer — so the chain ROOTS at the peer and the
    installer is the leaf granter. An implementation reading "rooted at author" rejects every
    legitimate embedded capability, which is the over-rejection
    ``cp1_install_static_literal_self_issued_accepted`` exists to catch.
    """
    cap_ref = _resolve_literal(entity.bytes_("capability"), st.ctx)
    if cap_ref is None:
        return None  # dynamic capability — runtime dual-check applies.

    value = cap_ref.field("value")
    if not isinstance(value, (bytes, bytearray)) or len(value) != CONTENT_HASH_LENGTH:
        # §3.3: *"else: cap entity unreachable at install — surface as chain_unreachable."*
        return AuditRefusal(
            404,
            "chain_unreachable",
            "Static compute/apply.capability does not name a capability entity",
        )
    cap_entity = _lookup_entity(bytes(value), st.ctx)
    if cap_entity is None:
        return AuditRefusal(
            404,
            "chain_unreachable",
            "Static compute/apply.capability authority chain not fully resolvable",
        )

    author = st.ctx.author
    if author is None:
        return AuditRefusal(
            403,
            "embedded_cap_unauthorized",
            "Install has no author identity to check the chain against",
        )

    # ENTITY-CORE-PROTOCOL §5.5's chain bound, taken from the peer's own constant rather than
    # restated. `typescript` has to restate it (that peer's `collectAuthorityChain` is
    # module-private); here `MAX_CHAIN_DEPTH` is public, so the number cannot drift.
    current: Entity | None = cap_entity
    for _ in range(MAX_CHAIN_DEPTH + 1):
        if current is None:
            return AuditRefusal(
                404,
                "chain_unreachable",
                "Static compute/apply.capability authority chain not fully resolvable",
            )
        if current.type != "system/capability/token":
            return AuditRefusal(
                404,
                "chain_unreachable",
                "Static compute/apply.capability chain contains a non-capability entity",
            )
        granter = current.bytes_("granter")
        if granter is not None and granter == bytes(author):
            return None  # IN-CHAIN as a granter — the installer authorized this delegation.
        parent = current.bytes_("parent")
        if parent is None:
            break  # root reached, installer never appeared.
        current = _lookup_entity(parent, st.ctx)

    return AuditRefusal(
        403,
        "embedded_cap_unauthorized",
        "Installer identity not in static compute/apply.capability chain",
    )


# ── Phase 2 — the capability checks ─────────────────────────────────────────────


def grant_covers(
    store: Any,
    included: dict,
    capability: Entity,
    handler_pattern: str,
    operation: str | None,
    resource: Any,
    local_peer: str,
) -> bool:
    """§3.3's ``check_grant_covers(path, operation, resource, capability, local_peer_id)``.

    **THIS CALLS THE PEER'S OWN §5.2 PREDICATE AND DOES NOT RE-DERIVE IT.** `typescript`'s
    sibling walks ``capability.grants`` directly, which it can because that peer exposes a
    ``CapabilityToken`` with typed grant records. Here every scope helper
    (``_grants_of_token``, ``_matches_scope``, ``_covered``, ``_canon``) is
    leading-underscore — this peer's statement about its own boundary — and HISTORY already
    paid for walking around it: a hand-rolled grant walk here denied 23 of 34 oracle checks
    and was the wrong SHAPE regardless of the bug, because a second reading of core §5.2's
    authorization logic inside an extension is exactly what D12 and L18 warn about.

    So the four dimensions are asked through ``check_permission``, which is public, by
    SYNTHESISING the EXECUTE §3.3 does not have. That is legitimate here and was not in
    HISTORY §4.2's case: §4.2 asks about a PATH, for which the peer has a path-shaped
    primitive (``check_path_permission``, our own H9); §3.3 asks about a
    (handler, operation, resource) TRIPLE, which is exactly what a dispatch authorization is
    and exactly what ``check_permission`` reads off an EXECUTE. The synthetic entity is a
    carrier for three arguments, not a request — it is never dispatched, signed or sent.

    **The granter frame IS resolved here, and that is the opposite of HISTORY's rule.**
    §PR-8: a grant's RESOURCE patterns canonicalize on the GRANTER's frame, so a bare ``*``
    on a foreign-granted capability means ``/{granter}/*`` and does not reach this peer's
    namespace. §4.2's path check deliberately has no granter frame because it is the §6.3
    defence-in-depth check on a locally-owned path; this one is the §5.2 chain-attenuation
    surface, where omitting the frame would over-admit a cross-peer grant.

    **ONE ASYMMETRY WITH THE SIBLING, DECLARED.** When ``operation`` is None — an apply with
    a ``path`` and no ``operation``, which §4.1 rejects at evaluation as
    ``invalid_expression`` — `typescript`'s hand-walk SKIPS the operations dimension while
    this one asks the peer about the empty string, so a grant whose ``operations`` is not
    ``*`` answers False here and True there. Stricter, unreachable for any well-formed graph,
    and invisible under the ``*`` posture the suite runs in. Recorded in
    ``EXTENSION.toml [assumptions].grant_covers_absent_operation`` rather than papered over,
    because a difference nobody wrote down is the one that becomes a bug report.
    """
    exec_e = make_execute(
        "audit-phase2",
        # The URI's only job here is to make `extract_peer` answer "the local peer", which is
        # the `peers` dimension §5.2 checks. A peer-relative handler pattern does that: its
        # first segment is not a peer id, so `extract_peer` falls through to `local_peer`.
        handler_pattern,
        operation or "",
        empty_params(),
        resource=resource,
    )
    granter_peer = resolve_granter_peer_id(cap_resolve(included, store), capability)
    return check_permission(local_peer, granter_peer, exec_e, capability, handler_pattern)


# ── resolution ──────────────────────────────────────────────────────────────────


def _lookup_entity(hash_: bytes, ctx: AuditContext) -> Entity | None:
    """The audit's resolver: the envelope's ``included`` map, then the content store.

    **Deliberately NOT §4.2's three-tier gate.** The tiers exist so an EVALUATION cannot use
    the content store as an oracle for entities the caller never had; the audit walks the
    installer's own expression graph before anything is authorized, and its one filter —
    *"skip hash references that resolve to non-compute entities"* — is applied by the caller
    in :func:`_walk_value`, where §3.3 puts it.
    """
    found = ctx.included.get(bytes(hash_).hex())
    if found is not None:
        return found
    return ctx.store.get_by_hash(bytes(hash_))


def _resolve_literal(hash_: bytes | None, ctx: AuditContext) -> Entity | None:
    """Resolve a reference and return it only if it is a ``compute/literal``."""
    if hash_ is None:
        return None
    found = _lookup_entity(hash_, ctx)
    return found if found is not None and found.type == LITERAL else None


def _lookup_path(entity: Entity, st: _WalkState) -> str:
    raw = entity.text("path")
    if raw is None:
        # A `lookup/tree` with no path cannot name a read. Recorded as the empty path so the
        # Phase 2 check refuses it rather than silently authorizing nothing: a grant covering
        # `""` does not exist, so an unreadable expression fails the audit instead of
        # installing with one fewer dependency than it has.
        return ""
    if entity.field("relative") is True:
        return clean_path(st.root_path + "/" + raw)
    return canonicalize_path(raw, st.ctx.local_peer)


def _relative_pattern(path: str) -> str:
    """The path with any leading ``/{peer}/`` removed — handler patterns are peer-relative."""
    if path.startswith("/"):
        i = path.find("/", 1)
        return path[i + 1:] if i >= 0 else path
    return path


def _builtin_name(path: str) -> str | None:
    """The builtin's short name, or None when ``path`` is not under the builtin prefix."""
    relative = _relative_pattern(path)
    if relative == BUILTINS_PREFIX:
        return ""
    if not relative.startswith(BUILTINS_PREFIX + "/"):
        return None
    return relative[len(BUILTINS_PREFIX) + 1:]
