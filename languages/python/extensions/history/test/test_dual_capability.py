"""§4.2's dual capability model — check 2, and the arm nothing upstream drives.

**Why this file exists.** ``_token_covers`` is §4.2's second check: the caller must hold
authority over the TARGET path as a tree path, not merely over ``system/history``. Before
this file, nothing in this port exercised it at any level:

- the three sibling test modules cover patterns, the export surface and the recorder;
- the oracle's ``history`` category drives ``query`` and ``rollback`` with a grant that
  satisfies BOTH halves, so it only ever walks the ALLOW arm. That is recorded upstream
  as ``[conformance]`` ``HIST-R9`` — *"nothing measures this, and it is a MUST"* — and
  routed.

So a change to this predicate could pass 34 unit tests and a 32-improvement conformance
run while getting the deny arm wrong, which is the only arm §7.5 is about. **The deny
cases here are the negative control (D15); the allow case exists to prove they are not
denying for an unrelated reason.**

**These are five POSITIONAL arguments** — ``check_path_permission(operation, path, token,
handler_pattern, local_peer)`` — and three of the four tests below fail on a transposition
rather than on a logic error. That is deliberate: the predicate is one line, so the
realistic defect is in the call, not the body.

**L18 applies and is not evaded.** This is our code checking our call into the peer's
function. It is not evidence about any other port, and it does not close ``HIST-R9`` — that
needs a wire check driving a caller authorized for the history op and not for the path.
It bounds THIS port against THIS change.
"""

from __future__ import annotations

import pytest
from entity_core.peer import Peer
from entity_core.peer.model import Entity

from entity_history.handler import _token_covers

TARGET = "docs/report"
OTHER = "secrets/payroll"


@pytest.fixture
def peer():
    # `open_grants` is irrelevant here and deliberately left at its default: this
    # predicate reads the TOKEN, never the peer's grant posture. A rig that turned it on
    # would pass whether or not the token was consulted.
    return Peer(bytes([0x33] * 32))


def token(*, handlers: list[str], operations: list[str], resources: list[str]) -> Entity:
    """A minimal grant token.

    Unsigned and never dispatched: ``check_path_permission`` reads ``grants`` and nothing
    else, so signing it would test the peer's crypto rather than our call.
    """
    return Entity.make(
        "system/capability/grant",
        {
            "grants": [
                {
                    "handlers": {"include": handlers},
                    "operations": {"include": operations},
                    "resources": {"include": resources},
                }
            ]
        },
    )


def test_allows_when_the_token_covers_the_target_as_a_tree_path(peer):
    """The positive control. Without it the three denies below prove nothing."""
    t = token(handlers=["system/tree"], operations=["get"], resources=[TARGET])
    assert _token_covers(peer, t, "get", TARGET, "system/tree") is True


def test_denies_when_the_grant_covers_a_DIFFERENT_path(peer):
    """§7.5's exfiltration case, and the reason the dual check exists at all.

    The caller holds a perfectly good ``system/tree``/``get`` grant — just not for the
    path whose history they are asking for. The oracle never constructs this.
    """
    t = token(handlers=["system/tree"], operations=["get"], resources=[OTHER])
    assert _token_covers(peer, t, "get", TARGET, "system/tree") is False


def test_denies_when_the_grant_is_for_the_history_handler_only(peer):
    """The crux of the dual model: authority over ``system/history`` is NOT authority
    over the target. A caller granted the history op alone must not read the history of
    a path they cannot read — and this is the case that fails if ``handler_pattern`` is
    passed as ``system/history`` at the call site."""
    t = token(handlers=["system/history"], operations=["get"], resources=[TARGET])
    assert _token_covers(peer, t, "get", TARGET, "system/tree") is False


def test_denies_when_the_operation_is_not_covered(peer):
    """``rollback`` asks for ``put`` on the target, not ``get`` — a read grant must not
    authorize the write. Catches an operation/path transposition in the call."""
    t = token(handlers=["system/tree"], operations=["get"], resources=[TARGET])
    assert _token_covers(peer, t, "put", TARGET, "system/tree") is False


def test_resource_scope_is_matched_against_the_LOCAL_peer(peer):
    """The frame, pinned — this is what the 2026-09-09 change altered.

    The previous implementation resolved a GRANTER peer id and matched resources against
    it. §6.3 is the defence-in-depth check on a path the local peer owns, so the frame is
    ``local_peer``; the peer's own docstring says *"do not add a granter frame to it"*.
    A grant written in absolute local form and one written relative must therefore agree,
    and a grant naming a different peer's path must not match.
    """
    absolute = "/" + peer.local_peer + "/" + TARGET
    t_rel = token(handlers=["system/tree"], operations=["get"], resources=[TARGET])
    t_abs = token(handlers=["system/tree"], operations=["get"], resources=[absolute])
    assert _token_covers(peer, t_rel, "get", TARGET, "system/tree") is True
    assert _token_covers(peer, t_abs, "get", TARGET, "system/tree") is True

    foreign = token(
        handlers=["system/tree"],
        operations=["get"],
        resources=["/someotherpeerid/" + TARGET],
    )
    assert _token_covers(peer, foreign, "get", TARGET, "system/tree") is False
