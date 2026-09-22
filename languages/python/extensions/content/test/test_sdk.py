"""§3.4 clause 2, in both directions, against a real grant rather than a stub.

**The `rust` port cannot have this file and that asymmetry is the point.** There
`reassemble_under_capability` takes a `&HandlerContext` whose fields are `pub(crate)`, so
no test can call the wrapper at all and the DECISION had to be split out as a `pub(crate)`
predicate to be measured (`src/sdk.rs`'s `authorization_tests`). Here `DispatchCtx` is a
plain dataclass — which is exactly clause 1's failure on this port, routed as `K-24` — so
the wrapper itself is directly reachable and the check is measured where it lives. **The
port that is weaker on clause 1 is the port on which clause 2 is testable end to end**, and
neither fact is a choice either port made.

The contexts below are REAL `DispatchCtx`es over a real `Peer`, not duck-typed stand-ins:
the operation is read off the EXECUTE and `peer.local_peer` is the canonicalization frame
the predicate matches grants in, so a stub would be asserting on a shape rather than on the
decision. `test_export_surface.py` keeps the duck-typed cases, deliberately — they measure
the gates that fire BEFORE any capability is read, and must keep working for a caller
holding nothing that resembles a dispatch.

**CONTROL, executed 2026-09-16 with the SUBJECT REMOVED** — the `check_path_permission`
branch deleted from `sdk.py`, which is the state this port was in the day before:

    3 failed, 2 passed

Three refusals red, `a_covering_capability_authorizes` still green. That split is the
reading worth keeping: had the positive gone red too, the fixture would be broken rather
than the subject, and three reds would prove nothing (D15 sharpened — the control is the
absence of the subject).
"""

from __future__ import annotations

import pytest
from entity_core.peer import Peer
from entity_core.peer.handlers import DispatchCtx
from entity_core.peer.model import Entity
from entity_core.peer.wire import make_execute

from entity_content import CONTENT_PATTERN, GET_REQUEST, reassemble_under_capability

HOST_SEED = bytes([0x61] * 32)


@pytest.fixture
def peer():
    # No listener and no connection: nothing here goes over the wire, so there is nothing
    # to close. `Peer` itself holds no socket until `listen`.
    return Peer(HOST_SEED)


def cap_with(operations, handlers, resources) -> Entity:
    """A capability token in the shape ``_grants_of_token`` parses.

    Hand-built because the peer's own minting path is not public here. It is never signed
    and never dispatched; ``check_path_permission`` reads only ``grants``, and the
    signature, chain, temporal bounds and revocation are ``verify_request``'s — which on
    the real path has already run before any context exists.
    """
    return Entity.make(
        "system/capability/token",
        {
            "grants": [
                {
                    "handlers": {"include": list(handlers)},
                    "resources": {"include": list(resources)},
                    "operations": {"include": list(operations)},
                }
            ]
        },
    )


def docs(p: Peer) -> str:
    """The target path, written against the peer's OWN id and resolved at call time.

    The predicate canonicalizes both the path and the grant's resource patterns in the
    local peer's frame, so a literal `/peer1/...` would be a different path from the
    grant's on every run and every refusal would pass for the wrong reason.
    """
    return "/" + p.local_peer + "/system/content/docs"


def context(p: Peer, token, *, pattern: str = CONTENT_PATTERN, operation: str = "get") -> DispatchCtx:
    exec_e = make_execute(
        "sdk-1",
        "/" + p.local_peer + "/" + CONTENT_PATTERN,
        operation,
        Entity.make(GET_REQUEST, {"hashes": []}),
    )
    return DispatchCtx(
        exec=exec_e,
        conn=None,
        included={},
        caller_cap=token,
        has_cap=token is not None,
        handler_pattern=pattern,
    )


def call(p: Peer, ctx: DispatchCtx, target: str):
    return reassemble_under_capability(
        ctx, target, bytes(33), store=p.store, local_peer=p.local_peer
    )


def test_a_covering_capability_authorizes(peer):
    """THE POSITIVE CONTROL.

    Without it every refusal below is satisfied by a wrapper that raises unconditionally,
    which is the cheapest way to pass a suite of denial tests (D15). The blob is absent, so
    the expected ANSWER is a coded reassembly failure — which is the authorization having
    been passed, not skipped.
    """
    token = cap_with(["get"], [CONTENT_PATTERN], [docs(peer)])
    result = call(peer, context(peer, token), docs(peer))
    assert not result.ok
    assert result.code == "blob_not_found"


def test_a_capability_covering_another_path_is_refused(peer):
    """The §3.4 escalation surface in one line: a consumer holding a real, verified,
    non-root capability, reaching for bytes its grant does not cover."""
    token = cap_with(["get"], [CONTENT_PATTERN], [docs(peer)])
    with pytest.raises(PermissionError, match="does not cover get on"):
        call(peer, context(peer, token), "/" + peer.local_peer + "/system/content/secrets")


def test_a_capability_for_another_operation_is_refused(peer):
    token = cap_with(["get"], [CONTENT_PATTERN], [docs(peer)])
    with pytest.raises(PermissionError, match="does not cover ingest on"):
        call(peer, context(peer, token, operation="ingest"), docs(peer))


def test_a_capability_scoped_to_another_handler_is_refused(peer):
    token = cap_with(["get"], ["system/tree"], [docs(peer)])
    with pytest.raises(PermissionError, match="does not cover get on"):
        call(peer, context(peer, token), docs(peer))


def test_a_context_belonging_to_another_handler_is_refused(peer):
    """Clause 1's residue, and the one case the pattern gate alone can produce.

    The capability here COVERS everything asked — operation, handler scope and path all
    match — so nothing but the `handler_pattern` check can refuse it. The second half is
    the discriminating one: the same capability under the right pattern is allowed through
    to reassembly.
    """
    broad = cap_with(["get"], ["*"], ["/" + peer.local_peer + "/*"])
    with pytest.raises(PermissionError, match="requires a system/content handler context"):
        call(peer, context(peer, broad, pattern="system/files"), docs(peer))
    allowed = call(peer, context(peer, broad), docs(peer))
    assert not allowed.ok and allowed.code == "blob_not_found", "control: only the pattern was wrong"
