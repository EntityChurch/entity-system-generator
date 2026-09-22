"""CONTENT — the SDK face.

**There is no conformance gate on this face, anywhere, and per the operator that is
correct rather than a defect: the SDK is a convention.** So the extension is its own
instrument — the handler's conformance path runs THROUGH these functions rather than
beside them, and ``EXTENSION.toml [sdk].*.reached_by`` records, per operation, which
check reaches it.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def reassemble_under_capability(ctx, blob_hash: bytes, store=None) -> ReassembleResult:
    """The **only** public route to materialized blob bytes, and the "explicit
    capability-checking wrapper" §3.4 requires before reassembly may be reachable from
    outside the handler body at all.

    A ``DispatchCtx`` cannot be manufactured by a consumer in the sense that matters: the
    dispatcher builds one, and only after ``check_permission`` (core §5.2) returned ALLOW
    for this caller, this operation and this resource. Requiring one as the first argument
    means the capability discipline has already run by the time this function has
    anything to do.

    **`store` is a parameter here and is not in the `typescript` port, and that is the
    substrate difference, not a design choice.** There, ``ctx.peer.contentStore`` is
    reachable from the body. `python`'s ``DispatchCtx`` carries ``exec / conn / included /
    caller_cap / has_cap`` and **no peer** — measured, `gates/host-seam/probe-seam.py` —
    so the store arrives by registration-time capture and the caller passes what it
    captured. A port that quietly reached for ``ctx.peer`` here would not compile; one
    that reached for a module-level singleton would work and be wrong.
    """
    if not getattr(ctx, "has_cap", False) or getattr(ctx, "caller_cap", None) is None:
        raise PermissionError(
            "CONTENT §3.4: reassembly requires a cap-checked dispatch; "
            "context carries no caller capability"
        )
    if store is None:
        raise ValueError(
            "CONTENT §3.4: python's DispatchCtx carries no peer, so the content store "
            "must be passed from registration-time capture"
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
