"""§3.4 ``reassemble_content`` — **MODULE-PRIVATE. Not re-exported from ``__init__``.**

  "Implementations MUST NOT expose `reassemble_content` as a public substrate primitive
   callable from third-party / SDK / external consumer code without an explicit
   capability-checking wrapper — direct substrate access bypasses the dispatcher cap
   discipline and creates a capability-escalation surface for consumers holding non-root
   caps."   — EXTENSION-CONTENT §3.4

**The boundary is not the same object it is in `typescript`, and that is the retarget
lesson this file carries.** There, `exports` in `package.json` is enforced by node: a
deep import into ``internal/`` raises ``ERR_PACKAGE_PATH_NOT_EXPORTED``, and the test
asserts on what the module resolver refuses. **Python enforces nothing.** Any consumer
can write ``from entity_content._internal.reassemble import reassemble_content`` and it
will work.

So the boundary here is convention, and the convention is stated three ways rather than
one, because no single one of them is a mechanism:

1. the package is ``_internal`` — leading underscore, PEP 8's "this is not public";
2. it is absent from ``__init__``'s ``__all__`` and from its import list;
3. ``test/test_export_surface.py`` asserts (1) and (2) hold, and asserts that the only
   public route takes a ``DispatchCtx``.

**That is weaker than the `typescript` port and the module says so rather than claiming
parity.** It is the same asymmetry D13 already records for this peer's own
``Outcome`` / ``DispatchCtx``: reachable by convention, not by declaration. A capability
claim that reads the same in both languages would be wrong in one of them.

§3.4 permits re-implementing the algorithm "for cases that operate inside the trusted
handler-context boundary", which is where this is called from:
``sdk.reassemble_under_capability``.

**This paragraph used to end "which takes a ``DispatchCtx`` the dispatcher builds only
after ``check_permission`` returned ALLOW", and that was false on this port.**
``DispatchCtx`` is a plain dataclass and any consumer can build one. The claim was
``rust``'s, written here. What the wrapper actually enforces since 2026-09-16 is §3.4's
clause 2 — the caller's capability is checked against a ``target`` path with the peer's own
``check_path_permission`` — and clause 1, the unforgeable anchor, is a keystone surface
question routed as ``K-24``. A prose claim is an undeclared assertion and it is the one
claim in a file that nothing executes (AP-47); this one is now the weaker, true version.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..types import BLOB


@dataclass(frozen=True)
class ReassembleResult:
    """Bytes or a coded failure. Never raises on a missing chunk — "missing chunk" is a
    normal incremental-sync state, not an error condition of the algorithm."""

    ok: bool
    data: bytes = b""
    code: str = ""
    hash: bytes = b""


def reassemble_content(store, blob_hash: bytes) -> ReassembleResult:
    """§3.4, transcribed.

    **``blob_pending_sync`` vs ``not_found`` is NOT decided here.** §3.4's predicate is
    sync-state visibility — a peer returns 503 IFF it has an active subscription on the
    namespace AND an inbox feeding the content store. This composition has neither, so
    the caller maps this code to a terminal 404. The code is still ``blob_pending_sync``
    at this layer so the mapping lives at the one place that knows the deployment's sync
    posture.
    """
    blob = store.get_by_hash(blob_hash)
    if blob is None:
        return ReassembleResult(False, code="blob_not_found", hash=blob_hash)
    if blob.type != BLOB:
        return ReassembleResult(False, code="not_a_blob", hash=blob_hash)

    chunk_hashes = blob.field("chunks")
    if not isinstance(chunk_hashes, list):
        return ReassembleResult(False, code="not_a_blob", hash=blob_hash)

    parts: list[bytes] = []
    for chunk_hash in chunk_hashes:
        chunk = store.get_by_hash(bytes(chunk_hash))
        if chunk is None:
            return ReassembleResult(False, code="blob_pending_sync", hash=bytes(chunk_hash))
        payload = chunk.field("payload")
        parts.append(bytes(payload) if isinstance(payload, (bytes, bytearray)) else b"")

    return ReassembleResult(True, data=b"".join(parts))
