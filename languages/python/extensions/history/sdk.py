"""HISTORY — the SDK face, and the **emit-consumer face**.

The emit consumer is why this extension was built second. `DESIGN-THE-SDK-LAYER` §1 named
four faces and CONTENT exercised three; this is the fourth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from entity_core.peer.model import Entity

from ._internal.recorder import (
    RecordedTransition,
    RecorderIdentity,
    TransitionContext,
    find_history_config,
    is_local_history_path,
    record_transition,
)
from .types import CONFIG, CONFIG_PREFIX, HISTORY_PATTERN

#: What the recorder does when the tree-change event carries no execution context.
#:
#: **On all three peers, it never carries one.** `typescript` declares an ``EmitContext``
#: carrying almost exactly SYSTEM-COMPOSITION §1.4's inventory and constructs it at zero
#: sites; `python` and `rust` have no context field on the event at all — ``TreeEvent`` is
#: ``(event_type, path, new_hash, previous_hash)`` and the dataclass is frozen+slots, so
#: there is not even a slot to fill. This is not an occasional fallback; today it fires on
#: every write, and the constant is named for that rather than something reassuring.
AUTONOMOUS_FALLBACK = "autonomous-fallback"


def build_context(
    identity: RecorderIdentity,
    operation: str,
    handler_pattern: str,
    carried: dict | None,
) -> TransitionContext:
    """Map an event's carried context onto §2.1's fields.

    §2.1 defines the autonomous case exactly — author is "the local peer's identity hash",
    capability is "the handler grant" — and a tree-change event with no execution context
    is, from the recorder's vantage, indistinguishable from an autonomous write. So those
    are the values recorded.

    **That is a reading of the spec and it is also wrong about the world**: a
    ``system/tree:put`` that arrived over the wire from a remote caller is not autonomous,
    and the transition will say it was. Which is why ``provenance`` exists and why the
    composition prints it. Routed to keystone as H8.
    """
    if not carried or carried.get("author") is None:
        return TransitionContext(
            author=identity.local_identity_hash,
            capability=identity.handler_grant_hash,
            caller_capability=None,
            handler_pattern=handler_pattern,
            operation=operation,
            chain_id=None,
            parent_chain_id=None,
            provenance=AUTONOMOUS_FALLBACK,
        )
    # §2.1 `capability`: the caller's for caller-authorized writes, the handler's own
    # grant for handler-authorized ones.
    capability = (
        carried.get("handler_grant")
        or carried.get("caller_capability")
        or identity.handler_grant_hash
    )
    return TransitionContext(
        author=carried["author"],
        capability=capability,
        caller_capability=carried.get("caller_capability"),
        handler_pattern=carried.get("handler_pattern") or handler_pattern,
        operation=carried.get("operation") or operation,
        chain_id=carried.get("chain_id"),
        parent_chain_id=carried.get("parent_chain_id"),
        provenance="context",
    )


@dataclass
class RecorderStats:
    """Counters the composition and the tests read. Not part of §2.1."""

    observed: int = 0
    recorded: int = 0
    skipped_self_guard: int = 0
    skipped_unconfigured: int = 0
    fallback_contexts: int = 0


class HistoryRecorder:
    """The §5.1 recorder, as a peer tree-event consumer.

    **Registration order is the composition's job, not this class's.** SYSTEM-COMPOSITION
    §2.2 puts history at position 4; this peer's ``register_tree_consumer`` APPENDS to a
    list and takes no position argument, so ordering is achieved only by the order the
    wiring program calls it in, and nothing here can enforce or check it.
    """

    name = "history"

    def __init__(self, peer, identity: RecorderIdentity) -> None:
        self.peer = peer
        self.identity = identity
        self.stats = RecorderStats()
        self.recorded_transitions: list[RecordedTransition] = []

    def on_tree_change(self, ev) -> None:
        self.stats.observed += 1

        if is_local_history_path(ev.path, self.identity.local_peer):
            self.stats.skipped_self_guard += 1
            return

        ctx = build_context(self.identity, "put", "system/tree", None)
        if ctx.provenance == AUTONOMOUS_FALLBACK:
            self.stats.fallback_contexts += 1

        # `python`'s TreeEvent carries hashes as HEX STRINGS ("" for absent), where
        # `typescript` carries `Uint8Array | null`. Converted at the boundary rather than
        # threaded through the recorder, so the recorder speaks one representation.
        recorded = record_transition(
            self.peer,
            self.identity,
            ev.event_type,
            ev.path,
            bytes.fromhex(ev.new_hash) if ev.new_hash else None,
            bytes.fromhex(ev.previous_hash) if ev.previous_hash else None,
            ctx,
            _now_ms(),
        )
        if recorded is None:
            self.stats.skipped_unconfigured += 1
            return
        self.stats.recorded += 1
        self.recorded_transitions.append(recorded)


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


# ── configuration (§6.1) ────────────────────────────────────────────────────────


def history_config(
    pattern: str,
    enabled: bool = True,
    events: list[str] | None = None,
    max_depth: int | None = None,
) -> Entity:
    """Build a ``system/history/config`` entity (§2.2).

    §6.1 is explicit that no handler operation is needed — "configuration uses the
    standard tree ``put``" — so which paths a deployment audits is composition policy and
    this only builds the entity.

    ``enabled`` is always written, including ``False``: §2.2 types it as a required
    ``primitive/bool``, and a disabled config that decoded as malformed would be SKIPPED
    by ``_parse_config`` and would silently RE-ENABLE history for the path it was written
    to turn off.
    """
    data: dict = {"pattern": pattern, "enabled": enabled}
    if events:
        data["events"] = list(events)
    if max_depth is not None:
        data["max_depth"] = max_depth
    return Entity.make(CONFIG, data)


def config_path(local_peer: str, name: str) -> str:
    """The tree path a named config binds at (§6.1)."""
    return "/" + local_peer + "/" + CONFIG_PREFIX + "/" + name


def resolve_config(peer, path: str, local_peer: str):
    """Which config governs a path (§6.2).

    The public form of the recorder's own lookup, exposed because it is the only way an
    operator can answer "is this path audited, and by which rule" without writing to it
    and looking.
    """
    return find_history_config(peer, path, local_peer)
