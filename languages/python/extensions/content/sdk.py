"""CONTENT — the SDK face.

**There is no conformance gate on this face, anywhere, and per the operator that is
correct rather than a defect: the SDK is a convention.** So the extension is its own
instrument — the handler's conformance path runs THROUGH these functions rather than
beside them, and ``EXTENSION.toml [sdk].*.reached_by`` records, per operation, which
check reaches it.
"""

from __future__ import annotations

from dataclasses import dataclass

from entity_core.peer.capability import check_path_permission
from entity_core.peer.model import Entity

from ._internal.reassemble import ReassembleResult, reassemble_content
from .types import BLOB, CONTENT_PATTERN, DESCRIPTOR


def hash_hex_with_format(h: bytes) -> str:
    """Lowercase hex INCLUDING the leading format byte (§6.4.2 / core §3.5).

    66 chars under ECFv1-SHA-256, 98 under SHA-384. The length is implied by the leading
    byte and is never assumed, so nothing here checks it. Dropping the format byte — the
    bare 64-char digest — is the mistake §6.4.2 calls out by name: it destroys the
    algorithm discriminator and breaks URL-to-binding parity with NETWORK §6.5.6.
    """
    return bytes(h).hex()


# ── EnsureClosure — §3.3 verify_content ──────────────────────────────────────


@dataclass(frozen=True)
class ClosureVerdict:
    complete: bool
    total_size: int = 0
    chunk_count: int = 0
    code: str = ""
    hash: bytes = b""


def ensure_closure(store, blob_hash: bytes) -> ClosureVerdict:
    """§3.3 — completeness and total-size consistency over a blob already in the store.

    §3.7 classifies this **Conformance**: "implementations MUST agree on whether a blob
    is complete ... the completeness verdict is cross-peer-uniform." So the failure modes
    are named exactly as §3.3 names them, and **the order matters**: a blob whose first
    chunk is missing reports ``missing_chunk``, not ``size_mismatch``, even though the
    totals also disagree.

    Per-chunk size is deliberately NOT validated against ``chunk_size`` — §3.3 says so
    outright, because content-defined chunking produces variable-size chunks and the
    entity hash already guarantees chunk integrity.
    """
    blob = store.get_by_hash(blob_hash)
    if blob is None:
        return ClosureVerdict(False, code="blob_not_found", hash=blob_hash)
    if blob.type != BLOB:
        return ClosureVerdict(False, code="not_a_blob", hash=blob_hash)

    chunk_hashes = blob.field("chunks")
    if not isinstance(chunk_hashes, list):
        return ClosureVerdict(False, code="not_a_blob", hash=blob_hash)

    total = 0
    for chunk_hash in chunk_hashes:
        chunk = store.get_by_hash(bytes(chunk_hash))
        if chunk is None:
            return ClosureVerdict(False, code="missing_chunk", hash=bytes(chunk_hash))
        payload = chunk.field("payload")
        payload = bytes(payload) if isinstance(payload, (bytes, bytearray)) else b""
        if len(payload) == 0:
            return ClosureVerdict(False, code="empty_chunk", hash=bytes(chunk_hash))
        total += len(payload)

    declared = blob.uint("total_size")
    if declared is None or total != declared:
        return ClosureVerdict(False, code="size_mismatch", hash=blob_hash)
    return ClosureVerdict(True, total_size=total, chunk_count=len(chunk_hashes))


# ── AtPeer — §6.4.2 Hash Tree Presence ───────────────────────────────────────


def at_peer(peer, namespace: str, h: bytes) -> Entity | None:
    """The §6.4.2 canonical namespace probe: is hash ``H`` bound at
    ``{namespace}/{hex(H)}`` in this peer's tree?

    **Unmeasured by any gate.** The oracle's content category has no namespace check.
    Stated, not hidden.
    """
    return peer.store.get_at("/" + peer.local_peer + "/" + namespace + "/" + hash_hex_with_format(h))


def bind_at_peer(peer, namespace: str, entity: Entity) -> str:
    """The §6.4.2 ingest-side binding. Paired with :func:`at_peer`; one convention, two
    directions."""
    path = "/" + peer.local_peer + "/" + namespace + "/" + hash_hex_with_format(entity.hash)
    peer.store.bind(path, entity)
    return path


# ── Descriptors — §2.4 presence rule, §5.3 path + integrity check ────────────


def create_descriptor(
    content: bytes,
    *,
    media_type: str | None = None,
    type_ref: bytes | None = None,
    name: str | None = None,
) -> Entity:
    """§2.4 — build a descriptor, enforcing the presence rule the type system cannot
    express: **at least one of ``media_type`` or ``type_ref`` MUST be present.** Both MAY
    be.

    Raises rather than emitting an invalid entity: a descriptor with neither is a
    content-addressed statement that says nothing, and once bound it is
    indistinguishable from a corrupt one.
    """
    if media_type is None and type_ref is None:
        raise ValueError(
            "CONTENT §2.4 presence rule: a descriptor MUST carry media_type or type_ref"
        )
    data: dict = {"content": bytes(content)}
    if media_type is not None:
        data["media_type"] = media_type
    if type_ref is not None:
        data["type_ref"] = bytes(type_ref)
    if name is not None:
        data["name"] = name
    return Entity.make(DESCRIPTOR, data)


def descriptor_path(publisher_peer_id: str, blob_hash: bytes, descriptor: Entity) -> str:
    """§5.3 — the dual-level path ``{publisher}/system/content/descriptor/{B_hex}/{D_hex}``."""
    return (
        "/"
        + publisher_peer_id
        + "/"
        + DESCRIPTOR
        + "/"
        + hash_hex_with_format(blob_hash)
        + "/"
        + hash_hex_with_format(descriptor.hash)
    )


def descriptor_matches_anchor(descriptor: Entity, blob_hash: bytes) -> bool:
    """§5.3 integrity check (**MUST**): a consumer fetching a descriptor at
    ``.../{B_hex}/{D_hex}`` MUST verify ``descriptor.data.content == B``. Mismatch =>
    reject.

    Two-level defence — the path embeds ``B_hex``, the body carries ``hash(B)``, and both
    must agree.
    """
    if descriptor.type != DESCRIPTOR:
        return False
    carried = descriptor.bytes_("content")
    return carried is not None and carried == bytes(blob_hash)


# ── Reassembly — the §3.4 capability-checking wrapper ────────────────────────


def reassemble_under_capability(
    ctx, target: str, blob_hash: bytes, *, store=None, local_peer: str | None = None
) -> ReassembleResult:
    """The **only** public route to materialized blob bytes, and §3.4's "explicit
    capability-checking wrapper" — **clause 2, on this port, since 2026-09-16.**

    §3.4: *"Implementations MUST NOT expose ``reassemble_content`` as a public substrate
    primitive callable from third-party / SDK / external consumer code without an explicit
    capability-checking wrapper — direct substrate access bypasses the dispatcher cap
    discipline and creates a capability-escalation surface for consumers holding non-root
    caps."* That sentence has two halves and this port now satisfies one of them.

    **CLAUSE 2 — the capability IS checked, against a target the caller must name.** §3.4
    routes materialization through ``system/content:get`` (namespace-cap-scoped) or
    ``local/files:read`` (tree-path-cap-scoped); both are scoped to a PATH, so the wrapper
    cannot check anything without one, and the old signature had nowhere to put it.
    ``target`` is that path, and the check is the peer's own §6.3 predicate
    (``check_path_permission``, keystone ``python/src/entity_core/peer/capability.py:709``
    @ ``a8423d2b``) — the same call the handler's §6.4 step 2 makes (``handler.py``), so the
    two cannot drift into two readings of one clause. Before this, the wrapper asked only
    that the context carry SOME capability and never compared it to anything; the handler
    pattern was not checked either.

    **CLAUSE 1 IS NOT SATISFIED HERE AND THIS DOCSTRING DOES NOT CLAIM IT IS.**
    ``DispatchCtx`` is a plain dataclass, so any object with the right attributes passes and
    holding one is not the statement *the dispatcher authorized you* that it is on ``rust``
    (where ``HandlerContext``'s fields are ``pub(crate)`` and ``Peer::route`` is the only
    construction site). Routed to keystone as ``K-24``; recorded in ``EXTENSION.toml
    [substrate.capability_wrapper]`` with ``python_blocked_on = "clause 1 only"``.

    **``store`` and ``local_peer`` are parameters here and are not in the other two ports,
    and that is the substrate difference, not a design choice.** There, ``ctx.peer`` is
    reachable from the body. `python`'s ``DispatchCtx`` carries
    ``exec / conn / included / caller_cap / has_cap / handler_pattern / handler_grant`` and
    **no peer** — measured, ``gates/host-seam/probe-seam.py`` — so both arrive by
    registration-time capture and the caller passes what it captured, exactly as
    ``ContentHandler.__init__`` does. A port that quietly reached for ``ctx.peer`` here
    would raise; one that reached for a module-level singleton would work and be wrong.

    **And ``local_peer`` being free is a REAL residual weakness, stated rather than
    buried:** it is the frame the predicate canonicalizes both the target and the grant's
    scopes in, so a caller who passes a different one is asking a different question. That
    residue is bounded by clause 1 and is the same size as it — a caller who can build the
    context can already put any capability in it — so it closes with ``K-24`` and not
    before. It is not an argument against the check: §3.4's escalation surface is *a
    consumer holding a non-root cap*, and one of those now cannot read outside its grant by
    going through the SDK instead of the wire.

    Refuses by raising, which is this port's existing convention here; ``rust`` returns
    ``Err(("capability_denied", _))`` because a panicking library constructor is a
    different contract there. A procedure difference (D17), recorded where the ports are
    compared.
    """
    # The context is caller-constructible here, but it is still not necessarily OURS: a body
    # installed at another pattern holds one too, and §3.4's grant discipline is per handler.
    # On the dispatch path `handler_pattern` is set from the resolved handler, never by the
    # caller. Checked FIRST, because a context for somebody else's handler is not a question
    # about this extension's grants at all.
    if getattr(ctx, "handler_pattern", "") != CONTENT_PATTERN:
        raise PermissionError(
            f"CONTENT §3.4: reassembly requires a {CONTENT_PATTERN} handler context; "
            f"got '{getattr(ctx, 'handler_pattern', '')}'"
        )
    # FAIL CLOSED on an absent capability. On the dispatch path a request with no caller
    # capability is refused `403 capability_denied` before a context exists, so here `None`
    # is not "a call without a token" — it is a state the peer says cannot exist, and turning
    # an impossible state into an unchecked one is how the escalation surface gets built.
    cap = getattr(ctx, "caller_cap", None)
    if not getattr(ctx, "has_cap", False) or cap is None:
        raise PermissionError(
            "CONTENT §3.4: reassembly requires a cap-checked dispatch; "
            "context carries no caller capability"
        )
    if store is None or local_peer is None:
        raise ValueError(
            "CONTENT §3.4: python's DispatchCtx carries no peer, so the content store and "
            "the local peer id must be passed from registration-time capture"
        )
    operation = ctx.exec.text("operation") or ""
    if not check_path_permission(operation, target, cap, CONTENT_PATTERN, local_peer):
        raise PermissionError(
            f"CONTENT §3.4: capability does not cover {operation} on '{target}' "
            "(§6.3 path scope)"
        )
    return reassemble_content(store, blob_hash)


__all__ = [
    "ClosureVerdict",
    "at_peer",
    "bind_at_peer",
    "create_descriptor",
    "descriptor_matches_anchor",
    "descriptor_path",
    "ensure_closure",
    "hash_hex_with_format",
    "reassemble_under_capability",
]
