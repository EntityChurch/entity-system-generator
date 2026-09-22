"""CONTENT §3.2 fixed-size and §3.6 FastCDC/NC2 chunking.

§3.7 classifies BOTH as **Conformance** algorithms: two implementations that follow them
produce byte-identical chunk boundaries for the same input, and divergence does not fail
loudly — it silently drops the peer out of cross-peer deduplication while every blob
still reassembles.

**Transcribed from the pseudocode, not ported from `../typescript/chunking.ts`.** That
is deliberate and it is the only honest way to get any signal out of a second port: two
transcriptions of one spec can disagree and tell us something, whereas a translation of
our own TypeScript would agree with it by construction and tell us nothing. The
cross-language hash comparison in ``test/test_cross_port.py`` is only worth running
because of this.

Even so — **N of our ports agreeing is N of our ports agreeing** (L18). §3.6.5's
cross-impl vectors are a Stage-4 byproduct that does not exist yet; when they land they
replace these expectations, and if they disagree with us we are wrong.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from entity_core.peer.model import Entity

from .types import BLOB, CHUNK, CHUNKING_FASTCDC_NC2, CHUNKING_FIXED, DEFAULT_CHUNK_SIZE

_U64 = (1 << 64) - 1

_GEAR_TABLE: tuple[int, ...] | None = None


def gear_table() -> tuple[int, ...]:
    """§3.6.1 — ``gear_table[i] = uint64_le(SHA-256("FastCDC" || byte(i))[0:8])``.

    "FastCDC" is the 7-byte ASCII string, ``byte(i)`` a single byte, ``uint64_le`` the
    first 8 digest bytes read little-endian. Computed once and memoized: the spec says
    "the table is computed once at initialization", and 256 SHA-256s per chunking call
    would be an easy accidental hot loop.

    ``int.from_bytes(..., "little")`` is the whole derivation. Reading big-endian here is
    the single most likely way to produce a table that looks right and dedups with
    nobody, which is why ``test_chunking.py`` derives the expected values a second way
    and also asserts the two byte orders differ.
    """
    global _GEAR_TABLE
    if _GEAR_TABLE is None:
        _GEAR_TABLE = tuple(
            int.from_bytes(hashlib.sha256(b"FastCDC" + bytes([i])).digest()[:8], "little")
            for i in range(256)
        )
    return _GEAR_TABLE


@dataclass(frozen=True)
class CdcParams:
    """§3.6.2 — every parameter derives from the target size."""

    target_size: int
    min_size: int
    max_size: int
    bits: int
    mask_s: int
    mask_l: int


def cdc_params(target_size: int = DEFAULT_CHUNK_SIZE) -> CdcParams:
    bits = int(math.floor(math.log2(target_size)))
    nc = 2
    return CdcParams(
        target_size=target_size,
        min_size=target_size // 4,
        max_size=target_size * 2,
        bits=bits,
        mask_s=(1 << (bits + nc)) - 1,
        mask_l=(1 << (bits - nc)) - 1,
    )


def _find_boundary(data: bytes, offset: int, p: CdcParams) -> int:
    """§3.6.3 ``find_boundary``. Two phases: the harder mask below the target pushes
    chunks toward it, the easier mask above pulls them back.

    ``& _U64`` after every step is load-bearing and is NOT in the pseudocode, because the
    pseudocode assumes a 64-bit register. Python ints are unbounded: without the mask the
    fingerprint grows without limit and keeps high bits a 64-bit implementation
    discards. The ``fp & mask`` test itself only reads low bits, so the divergence
    appears only once the accumulated value exceeds 64 bits — i.e. never in a small test
    and always in a real file. `python` and `rust` fail this differently and `typescript`
    fails it the same way, which is why it is called out in both ports rather than in one.
    """
    gear = gear_table()
    fp = 0
    i = offset + p.min_size

    limit1 = min(offset + p.target_size, len(data))
    while i < limit1:
        fp = ((fp << 1) + gear[data[i]]) & _U64
        if (fp & p.mask_s) == 0:
            return i + 1
        i += 1

    limit2 = min(offset + p.max_size, len(data))
    while i < limit2:
        fp = ((fp << 1) + gear[data[i]]) & _U64
        if (fp & p.mask_l) == 0:
            return i + 1
        i += 1

    return i


def cdc_boundaries(data: bytes, target_size: int = DEFAULT_CHUNK_SIZE) -> list[int]:
    """The boundary offsets a FastCDC pass produces. Exposed for the §3.6.5 vectors."""
    p = cdc_params(target_size)
    out: list[int] = []
    offset = 0
    while offset < len(data):
        remaining = len(data) - offset
        end = offset + remaining if remaining <= p.min_size else _find_boundary(data, offset, p)
        out.append(end)
        offset = end
    return out


@dataclass(frozen=True)
class Blob:
    """A chunked blob: the manifest entity plus the chunk entities it names."""

    blob: Entity
    chunks: tuple[Entity, ...]


def _chunk_entity(payload: bytes) -> Entity:
    return Entity.make(CHUNK, {"payload": payload})


def _blob_entity(total_size: int, chunk_size: int, chunking: int, chunks: list[Entity]) -> Entity:
    return Entity.make(
        BLOB,
        {
            "total_size": total_size,
            "chunk_size": chunk_size,
            "chunking": chunking,
            "chunks": [bytes(c.hash) for c in chunks],
        },
    )


def create_blob_fixed(data: bytes, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Blob:
    """§3.2 — fixed-size. ``chunking: 0``."""
    chunks: list[Entity] = []
    offset = 0
    while offset < len(data):
        end = min(offset + chunk_size, len(data))
        chunks.append(_chunk_entity(data[offset:end]))
        offset = end
    return Blob(_blob_entity(len(data), chunk_size, CHUNKING_FIXED, chunks), tuple(chunks))


def create_blob_cdc(data: bytes, target_size: int = DEFAULT_CHUNK_SIZE) -> Blob:
    """§3.6.3 — FastCDC/NC2. ``chunking: 1``. The §11.2 SHOULD and the default we emit.

    Zero-length input produces a blob with an EMPTY chunk list: the loop never runs.
    Consistent with §3.3 (the total of no chunks is 0), and §3.3's ``empty_chunk`` guard
    is about a chunk whose payload is empty, which is a different object. The spec says
    neither way — logged as C-1 in ``docs/SPEC-AMBIGUITIES.md``, carried identically here
    and in the `typescript` port so the two cannot silently diverge on it.
    """
    p = cdc_params(target_size)
    chunks: list[Entity] = []
    offset = 0
    while offset < len(data):
        remaining = len(data) - offset
        end = offset + remaining if remaining <= p.min_size else _find_boundary(data, offset, p)
        chunks.append(_chunk_entity(data[offset:end]))
        offset = end
    return Blob(_blob_entity(len(data), target_size, CHUNKING_FASTCDC_NC2, chunks), tuple(chunks))


def store_blob(store, blob: Blob) -> bytes:
    """Write a blob and its chunks into the content store.

    §3.1: content entities live in the content store, NOT the entity tree — a 1 TiB file
    is ~262K chunks and the tree is listable. `python`'s ``Store`` is one object for both,
    so the distinction is which METHOD is called: ``put_entity`` (content store) and
    never ``bind`` (tree). A port that reached for ``bind`` here would pass every unit
    test and put a quarter-million entries in the peer's listing.
    """
    for chunk in blob.chunks:
        store.put_entity(chunk)
    store.put_entity(blob.blob)
    return bytes(blob.blob.hash)
