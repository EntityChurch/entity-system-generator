"""``entity_history`` — HISTORY v1.7 for the `python` peer.

THE PUBLIC ENTRY POINT. ``_internal`` is not re-exported and is not in ``__all__``.

**Python enforces nothing, and this port says so rather than claiming the `typescript`
port's guarantee.** There, node's ``exports`` map refuses a deep import at resolve time
and the test asserts on the resolver's refusal. Here a determined consumer can
``import entity_history._internal.recorder`` and it works. ``test/test_export_surface.py``
asserts BOTH that the convention holds AND that it can be walked around, so the two ports'
boundary claims are not read as equal — the same split CONTENT's §3.4 clause 1 has.
"""

from __future__ import annotations

from dataclasses import dataclass

from entity_core.peer.model import Entity

from ._internal.recorder import (
    HistoryConfig,
    RecordedTransition,
    RecorderIdentity,
    TransitionContext,
)
from .handler import HistoryHandler
from .patterns import (
    Specificity,
    canonicalize_pattern,
    compare_specificity,
    pattern_matches,
    pattern_specificity,
)
from .sdk import (
    HistoryRecorder,
    RecorderStats,
    build_context,
    config_path,
    history_config,
    resolve_config,
)
from .types import (
    ALL_TYPES,
    CONFIG,
    CONFIG_PREFIX,
    DEFAULT_EVENTS,
    DEFAULT_QUERY_LIMIT,
    EVENT_ACCESSED,
    EVENT_CREATED,
    EVENT_DELETED,
    EVENT_UPDATED,
    HEAD_PREFIX,
    HISTORY_PATTERN,
    QUERY_PARAMS,
    QUERY_RESULT,
    ROLLBACK_PARAMS,
    ROLLBACK_RESULT,
    TRANSITION,
    from_core_event_type,
    history_type_defs,
    history_entity,
    history_type_entities,
    publish_history_types,
)

#: §4.1's manifest operations, in the mapped §3.7 form.
_OPERATION_SPECS = {
    "query": {"input_type": QUERY_PARAMS, "output_type": QUERY_RESULT},
    "rollback": {"input_type": ROLLBACK_PARAMS, "output_type": ROLLBACK_RESULT},
}


@dataclass(frozen=True, slots=True)
class HistoryInstallation:
    pattern: str
    interface_path: str
    type_paths: tuple[str, ...]
    handler_paths: tuple[str, ...]
    recorder: HistoryRecorder
    #: Whether the peer's tree-change events can carry an execution context AT ALL.
    #: ``False`` on every peer measured. On the installation result rather than buried in
    #: stats, because a system recording fabricated provenance and one recording real
    #: provenance are different systems, and the difference has to be visible where
    #: someone decides to trust the audit trail.
    context_available: bool


def install_history(peer, max_walk: int | None = None) -> HistoryInstallation:
    """Install HISTORY onto a live peer: handler, types, and the position-4 consumer.

    **This peer has no registration surface** (measured — `gates/host-seam/probe-seam.py`),
    so all four §11.6.1 writes are ours, through public names only. Same six-step shape as
    ``install_content``, plus a seventh step CONTENT never had.

    **The order matters and is not arbitrary.** The consumer is registered LAST, after the
    §11.6.1 writes and the type publication. Otherwise the recorder observes its own
    installation: four tree writes plus six type entities recorded as application
    transitions before the peer ever listens. That is the "installing a handler emits
    tree-change events" finding cycle 1 routed, and here it is not theoretical — it is the
    difference between an audit log that starts empty and one that starts with ten entries
    nobody performed.
    """
    local = peer.local_peer

    def absolute(rel: str) -> str:
        return "/" + local + "/" + rel

    interface_rel = "system/handler/" + HISTORY_PATTERN
    handler_paths: list[str] = []

    # (1) §11.6.1 manifest at the pattern path — what `_resolve_handler` walks for.
    path = absolute(HISTORY_PATTERN)
    peer.store.bind(path, Entity.make("system/handler", {"interface": interface_rel}))
    handler_paths.append(path)

    # (2) The handler interface entity (discovery index) — §4.1's manifest, complete.
    interface_path = absolute(interface_rel)
    peer.store.bind(
        interface_path,
        Entity.make(
            "system/handler/interface",
            {"pattern": HISTORY_PATTERN, "name": "history", "operations": _OPERATION_SPECS},
        ),
    )
    handler_paths.append(interface_path)

    # (3)+(4) Self-issued signed handler grant + its signature at the §3.5 invariant
    #         pointer, so dispatch-time grant validation can find and verify it.
    token, signature = peer.mint_token(peer.identity.identity_hash, [], None)
    grant_path = absolute("system/capability/grants/" + HISTORY_PATTERN)
    peer.store.bind(grant_path, token)
    handler_paths.append(grant_path)
    sig_path = absolute("system/signature/" + token.hash.hex())
    peer.store.bind(sig_path, signature)
    handler_paths.append(sig_path)

    # (5) The six type entities — the oracle's six `type_*` checks fail unless we write them.
    type_paths = publish_history_types(peer)

    # (6) The executable body, into the container dispatch consults.
    peer.handlers[HISTORY_PATTERN] = (
        HistoryHandler(peer) if max_walk is None else HistoryHandler(peer, max_walk=max_walk)
    )

    # (7) LAST: the emit consumer. THE FACE CONTENT NEVER HAD.
    identity = RecorderIdentity(
        local_identity_hash=peer.identity.identity_hash,
        # §2.1's "handler grant" for the autonomous case. Taken from the token we just
        # minted rather than re-read, so it is the same bytes the peer published.
        handler_grant_hash=token.hash,
        local_peer=local,
    )
    recorder = HistoryRecorder(peer, identity)
    peer.store.register_tree_consumer(recorder.on_tree_change)

    return HistoryInstallation(
        pattern=HISTORY_PATTERN,
        interface_path=interface_path,
        type_paths=tuple(type_paths),
        handler_paths=tuple(handler_paths),
        recorder=recorder,
        context_available=False,  # measured; EXTENSION.toml [substrate.execution_context]
    )


__all__ = [
    # install
    "HistoryInstallation",
    "install_history",
    "HistoryHandler",
    # types
    "ALL_TYPES",
    "TRANSITION",
    "CONFIG",
    "QUERY_PARAMS",
    "QUERY_RESULT",
    "ROLLBACK_PARAMS",
    "ROLLBACK_RESULT",
    "HISTORY_PATTERN",
    "HEAD_PREFIX",
    "CONFIG_PREFIX",
    "EVENT_CREATED",
    "EVENT_UPDATED",
    "EVENT_DELETED",
    "EVENT_ACCESSED",
    "DEFAULT_EVENTS",
    "DEFAULT_QUERY_LIMIT",
    "from_core_event_type",
    "history_type_defs",
    "history_entity",
    "history_type_entities",
    "publish_history_types",
    # patterns
    "Specificity",
    "canonicalize_pattern",
    "pattern_specificity",
    "compare_specificity",
    "pattern_matches",
    # sdk
    "HistoryRecorder",
    "RecorderStats",
    "RecorderIdentity",
    "RecordedTransition",
    "TransitionContext",
    "HistoryConfig",
    "build_context",
    "history_config",
    "config_path",
    "resolve_config",
]
