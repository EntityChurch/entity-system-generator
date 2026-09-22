"""§4.3.2 + §2.1 — a rollback's tree write carries the dispatch's execution context.

§4.3.2: *"the transition's `operation` field will reflect the rollback operation"*, and §2.1
records the remote caller as ``author``. Until 2026-09-12 all three ports bound the restored entity
with no context, so every rollback was recorded as the peer's own write; the oracle's
``rollback_new_transition`` checks only ``event`` and ``hash`` and could not see it.

The witness is attributable: ``author`` comes from the EXECUTE this test builds, and ``operation``
from the dispatch, so a recorder or a store that invented a context could not match both. The
CONTROL is an ordinary bind at the same path, which must reach the same consumer context-less —
otherwise "the consumer saw a context" would be a fact about the consumer, not about the rollback.
"""

from __future__ import annotations

from entity_core.peer import Peer
from entity_core.peer.handlers import DispatchCtx
from entity_core.peer.model import Entity
from entity_core.peer.wire import make_execute, resource_target

from entity_history import HISTORY_PATTERN, ROLLBACK_PARAMS, config_path, history_config, install_history

AUTHOR = bytes([0xCA] * 33)


def test_a_rollback_write_carries_the_dispatch_context():
    peer = Peer(bytes([0x61] * 32), open_grants=True)
    install_history(peer)
    local = peer.local_peer
    peer.store.bind(config_path(local, "everything"), history_config("*", True))
    path = f"/{local}/app/doc"
    v1 = Entity.make("app/doc", {"v": 1})
    peer.store.bind(path, v1)
    peer.store.bind(path, Entity.make("app/doc", {"v": 2}))

    seen = []
    peer.store.register_tree_consumer(lambda ev: seen.append(ev.context) if ev.path == path else None)

    token, _ = peer.mint_token(peer.identity.identity_hash, [{
        "handlers": {"include": ["*"]}, "operations": {"include": ["*"]}, "resources": {"include": ["*"]},
    }], None)
    exec_e = make_execute(
        "r-rb", f"/{local}/{HISTORY_PATTERN}", "rollback",
        Entity.make(ROLLBACK_PARAMS, {"path": path, "target_hash": v1.hash}),
        author=AUTHOR, capability=token.hash, resource=resource_target(path),
    )
    ctx = DispatchCtx(exec=exec_e, conn=None, included={}, caller_cap=token, has_cap=True,
                      handler_pattern=HISTORY_PATTERN)
    outcome = peer.handlers[HISTORY_PATTERN].handle_op("rollback", ctx)
    assert outcome.status == 200, outcome.result.data

    assert len(seen) == 1 and seen[0] is not None, "the rollback write reached the bus with no context"
    assert seen[0].operation == "rollback"
    assert seen[0].author == AUTHOR

    # CONTROL — an ordinary bind at the same path reaches the same consumer with no context.
    peer.store.bind(path, Entity.make("app/doc", {"v": 3}))
    assert len(seen) == 2 and seen[1] is None
