"""§5.1 ``emit_entity`` — the transition recorder. **MODULE-PRIVATE.**

The emit-consumer body. A caller able to reach :func:`record_transition` could append a
forged entry to an audit chain — any ``author``, any ``capability``, at any path, linked
into the real chain by ``previous``. §7.2 calls the capability field the answer to "under
what authority?", and a forgeable answer is worse than no answer because it is believed.

CONTENT §3.4 had a MUST to point at for its private surface. This has none; the boundary
is ours to set, for the same reason ``[sdk_surface]`` is (D16).
"""

from __future__ import annotations

from dataclasses import dataclass

from entity_core.peer.model import Entity

from ..patterns import (
    canonicalize_pattern,
    compare_specificity,
    pattern_matches,
    pattern_specificity,
)
from ..types import CONFIG, CONFIG_PREFIX, DEFAULT_EVENTS, HEAD_PREFIX, TRANSITION, from_core_event_type


@dataclass(frozen=True, slots=True)
class TransitionContext:
    """The §2.1 execution-context values, and where they came from.

    ``provenance`` is OURS, not §2.1's, and it never enters the transition entity: adding
    a field to a spec-declared type changes its content hash away from every other
    implementation's.
    """

    author: bytes
    capability: bytes
    caller_capability: bytes | None
    handler_pattern: str
    operation: str
    chain_id: str | None
    parent_chain_id: str | None
    provenance: str  # "context" | "autonomous-fallback"


@dataclass(frozen=True, slots=True)
class RecorderIdentity:
    """Captured at install time, because the event does not carry it."""

    local_identity_hash: bytes
    handler_grant_hash: bytes
    local_peer: str


@dataclass(frozen=True, slots=True)
class RecordedTransition:
    path: str
    event: str
    transition_hash: bytes
    head_path: str
    provenance: str


@dataclass(frozen=True, slots=True)
class HistoryConfig:
    pattern: str
    canonical_pattern: str
    enabled: bool
    #: §2.2 v1.10, ALREADY CANONICALIZED — the raw spelling is not kept, because the only
    #: consumer is `matches_pattern` and §2.2 says these use the same core §5.4 syntax as
    #: `pattern`. Canonicalizing at parse time rather than per-write also means the bare
    #: `*` rule is applied by the one function that knows it (`canonicalize_pattern`).
    canonical_pattern_exclude: tuple[str, ...]
    events: tuple[str, ...]
    max_depth: int | None
    config_path: str


def is_local_history_path(path: str, local_peer: str) -> bool:
    """§3.2 ``is_local_history_path`` — the self-guard.

    Two properties are load-bearing and both are easy to get wrong in the direction that
    still passes a naive test:

    1. It guards ``system/history/head``, NOT ``system/history/``. §3.2: config paths
       "do not create recursion risk -- they SHOULD be recorded as normal transitions for
       audit purposes." Guarding the whole namespace silently drops config auditing.
    2. It is LOCAL-ONLY. A remote peer's ``system/history/...`` arriving via sync is
       ordinary tracked content; the head pointer it produces lands in the local
       namespace and is excluded by this same check.
    """
    prefix = "/" + local_peer + "/"
    if not path.startswith(prefix):
        return False
    return path[len(prefix) :].startswith(HEAD_PREFIX)


def _parse_config(path: str, ent: Entity, local_peer: str) -> HistoryConfig | None:
    if ent.type != CONFIG:
        return None
    pattern = ent.text("pattern")
    if pattern is None:
        return None
    enabled = ent.field("enabled")
    if not isinstance(enabled, bool):
        # §2.2 types `enabled` as a required primitive/bool. A config that does not carry
        # one is malformed and is skipped rather than defaulted — defaulting to True
        # would turn an unreadable config into an ENABLED one, which is the wrong
        # direction to fail in for an audit switch.
        return None
    # §2.2 v1.10. An EMPTY list is kept as empty (no exclusions), unlike `events` below
    # where empty falls back to the default set — `events` has a spec-stated default and
    # this field's absent-value is "no exclusions", which an empty list already says.
    raw_exclude = ent.field("pattern_exclude")
    canonical_pattern_exclude = (
        tuple(canonicalize_pattern(str(p), local_peer) for p in raw_exclude)
        if isinstance(raw_exclude, list)
        else ()
    )
    raw_events = ent.field("events")
    events = (
        tuple(str(e) for e in raw_events)
        if isinstance(raw_events, list) and raw_events
        else DEFAULT_EVENTS
    )
    raw_depth = ent.field("max_depth")
    max_depth = int(raw_depth) if isinstance(raw_depth, int) and not isinstance(raw_depth, bool) else None
    return HistoryConfig(
        pattern=pattern,
        canonical_pattern=canonicalize_pattern(pattern, local_peer),
        enabled=enabled,
        canonical_pattern_exclude=canonical_pattern_exclude,
        events=events,
        max_depth=max_depth,
        config_path=path,
    )


def find_history_config(peer, path: str, local_peer: str) -> tuple[HistoryConfig | None, int, int]:
    """§6.2 ``find_history_config``, with v1.7's three-key ordering.

    Returns ``(config, considered, skipped)``. The ``enabled`` check belongs to the
    CALLER: §5.1 tests ``config is null or not config.data.enabled`` separately, and
    folding it in here would change which config wins — a specific ``enabled: false``
    must SHADOW a general ``enabled: true``, or "turn history off for this subtree"
    cannot be expressed at all.
    """
    base = "/" + local_peer + "/" + CONFIG_PREFIX + "/"
    best: HistoryConfig | None = None
    considered = 0
    skipped = 0

    for row in peer.store.listing(base):
        if not row.hash:
            continue
        config_path = base + row.segment
        ent = peer.store.get_at(config_path)
        if ent is None:
            continue
        parsed = _parse_config(config_path, ent, local_peer)
        if parsed is None:
            skipped += 1
            continue
        considered += 1
        if not pattern_matches(path, parsed.canonical_pattern):
            continue
        if best is None or compare_specificity(
            pattern_specificity(parsed.canonical_pattern),
            pattern_specificity(best.canonical_pattern),
        ) > 0:
            best = parsed
    return best, considered, skipped


def record_transition(
    peer,
    identity: RecorderIdentity,
    event_type: str,
    path: str,
    new_hash: bytes | None,
    previous_hash: bytes | None,
    ctx: TransitionContext,
    now_ms: int,
) -> RecordedTransition | None:
    """§5.1's transition build and head advance.

    ``None`` when the write is not recorded, which is a normal outcome: unconfigured
    paths, disabled configs, unlisted event types and the §3.2 self-guard all land here.
    History is opt-in (§2.2).
    """
    # §3.2 self-guard FIRST — before the config lookup, because the lookup lists the tree
    # and the guard is what stops this consumer re-entering on its own head write.
    if is_local_history_path(path, identity.local_peer):
        return None

    event = from_core_event_type(event_type)
    if event is None:
        return None

    config, _considered, _skipped = find_history_config(peer, path, identity.local_peer)
    if config is None or not config.enabled:
        return None

    # §2.2 v1.10 exclusions, and the ORDER is the MUST (HIST-R16), not the matching.
    # AFTER selection: checked against the SELECTED config only. An excluded path does
    # NOT fall through to a less specific configuration — "an exclusion is a decision,
    # not a failure to match." Folding this into `find_history_config` as a non-match
    # would be the other conformant-looking reading, and the two differ on exactly the
    # paths two configs cover, which is where an audit gap would hide.
    # BEFORE the event filter: so an excluded path is excluded for every event type.
    if any(pattern_matches(path, excl) for excl in config.canonical_pattern_exclude):
        return None

    if event not in config.events:
        return None

    head_path = "/" + identity.local_peer + "/" + HEAD_PREFIX + path
    prev_head_hex = peer.store.hash_at(head_path)
    previous_transition = bytes.fromhex(prev_head_hex) if prev_head_hex else None

    # §2.1 field order follows the spec's table so this diffs against it line by line.
    # `None` values are dropped by the encoder, which is the §1.3 absent-key rule the
    # `optional: true` specs in types.py declare.
    data: dict = {
        "path": path,
        "event": event,
        "author": ctx.author,
        "capability": ctx.capability,
        "handler": ctx.handler_pattern,
        "operation": ctx.operation,
        "timestamp": now_ms,
    }
    if new_hash is not None:
        data["hash"] = new_hash
    if previous_hash is not None:
        data["previous_hash"] = previous_hash
    # §5.1: recorded "only when it differs from capability". Compared BY VALUE — under the
    # fallback the same object arrives twice and an identity check would emit a redundant
    # field on every write.
    if ctx.caller_capability is not None and ctx.caller_capability != ctx.capability:
        data["caller_capability"] = ctx.caller_capability
    # `clock` omitted: §2.1 says "Absent when the clock extension is not installed".
    if ctx.chain_id is not None:
        data["chain_id"] = ctx.chain_id
    if ctx.parent_chain_id is not None:
        data["parent_chain_id"] = ctx.parent_chain_id
    if previous_transition is not None:
        data["previous"] = previous_transition

    transition = Entity.make(TRANSITION, data)

    # §3.1: "All transition entities are in the content store. Only the head pointer is
    # in the tree." `store.bind` does both — it puts the entity and binds the path to its
    # hash — so `hash_at(head_path)` IS "hash of latest transition entity" per §3.1.
    peer.store.bind(head_path, transition)

    if config.max_depth is not None:
        prune_history(peer, head_path, config.max_depth)

    return RecordedTransition(
        path=path,
        event=event,
        transition_hash=transition.hash,
        head_path=head_path,
        provenance=ctx.provenance,
    )


def prune_history(peer, head_path: str, max_depth: int) -> tuple[int, bytes | None]:
    """§3.3 ``prune_history``. **Walks and reports; severs nothing.**

    §3.3 says to "sever the chain — the old transition keeps its previous field
    (immutable in content store), but it's no longer reachable from the head." A
    content-addressed entity cannot be edited, so severing means writing a NEW transition
    identical to the last-kept one except without ``previous`` — which changes its hash,
    which changes what the transition before it points at, which cascades to the head.
    Rewriting the chain is the only way to truncate it, and rewriting an audit chain is
    the opposite of what an audit chain is for.

    Pruning is a SHOULD (§9.1). The honest statement is that we do not implement it.
    Routed to arch.
    """
    head_hex = peer.store.hash_at(head_path)
    if not head_hex:
        return 0, None
    current: bytes | None = bytes.fromhex(head_hex)
    count = 0
    while current is not None and count < max_depth:
        ent = peer.store.get_by_hash(current)
        if ent is None:
            break
        current = ent.bytes_("previous")
        count += 1
    return count, current
