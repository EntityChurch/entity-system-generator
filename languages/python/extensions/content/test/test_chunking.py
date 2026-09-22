"""§3.6 FastCDC and §3.2 fixed-size — the Conformance algorithms.

**Not evidence about the spec.** §3.6.5's cross-impl vectors are a Stage-4 byproduct that
does not exist yet; when they land they replace these expectations, and if they disagree
with us we are wrong (L18).

What they CAN do is catch the failure §3.6 names: divergence that is silent. A wrong gear
table, a big-endian read, or an unbounded fingerprint still produces blobs that reassemble
perfectly and deduplicate with nobody. So the gear table is checked against an INDEPENDENT
derivation rather than against a constant this module produced.

**The corpus is checked before the algorithm is.** The `typescript` port's first version
of the edit-stability test failed against a CORRECT implementation because its byte
generator's low bits never satisfied the boundary mask — FastCDC degenerated to fixed-size
and nothing said so. That is AP-3 and D15's second enforcement clause, and it is why
`test_the_corpus_actually_exercises_content_defined_boundaries` runs first.
"""

from __future__ import annotations

import hashlib

from entity_content import (
    CHUNKING_FASTCDC_NC2,
    DEFAULT_CHUNK_SIZE,
    cdc_boundaries,
    cdc_params,
    create_blob_cdc,
    create_blob_fixed,
    gear_table,
)

#: A small target keeps the tests fast; every derivation still applies.
TARGET = 65_536


def seeded(length: int, seed: int = 0x9E3779B9) -> bytes:
    """xorshift32. Deterministic, documented seed (§3.6.5's canonical input shape)."""
    out = bytearray(length)
    x = seed & 0xFFFFFFFF
    for i in range(length):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        x &= 0xFFFFFFFF
        out[i] = x & 0xFF
    return bytes(out)


def mask_evading(length: int) -> bytes:
    """The LCG that broke the `typescript` port's edit-stability test.

    In JS the product exceeds 2^53 and the float multiply eats the low bits. Python's ints
    are exact, so this is NOT the same stream — the mask-evasion there was a float
    artefact. Reproduced here as a plain low-entropy structured stream so the degenerate
    shape still has a test; what is being pinned is the forced-`max_size` arm of
    `find_boundary`, not the JS defect.
    """
    return bytes((i * 7) & 0xF0 for i in range(length))


# ── §3.6.1 gear table ────────────────────────────────────────────────────────


def _independent_gear_entry(i: int) -> int:
    """A second derivation of §3.6.1, written from the spec sentence rather than from
    `chunking.py` — `int.from_bytes(..., "little")` over the first 8 digest bytes."""
    digest = hashlib.sha256(b"FastCDC" + bytes([i])).digest()
    return int.from_bytes(digest[0:8], "little")


def test_gear_table_matches_an_independent_derivation_for_all_256_entries():
    table = gear_table()
    assert len(table) == 256
    for i in range(256):
        assert table[i] == _independent_gear_entry(i), f"gear_table[{i}]"


def test_gear_table_is_not_accidentally_big_endian():
    """A big-endian read would pass every determinism test and dedup with nobody."""
    digest = hashlib.sha256(b"FastCDC" + bytes([0])).digest()
    assert gear_table()[0] != int.from_bytes(digest[0:8], "big")


def test_gear_table_entries_are_64_bit():
    assert all(0 <= v <= (1 << 64) - 1 for v in gear_table())


# ── §3.6.2 parameters ────────────────────────────────────────────────────────


def test_parameters_derive_from_the_target_size():
    p = cdc_params(DEFAULT_CHUNK_SIZE)
    assert p.target_size == 1_048_576
    assert p.min_size == 262_144
    assert p.max_size == 2_097_152
    assert p.bits == 20
    assert p.mask_s == 0x003FFFFF
    assert p.mask_l == 0x0003FFFF


# ── the corpus, before the algorithm ─────────────────────────────────────────


def test_the_corpus_actually_exercises_content_defined_boundaries():
    """**D15's corpus clause.** If every boundary lands on a multiple of `max_size`, the
    content-defined arm never ran and every test below is measuring fixed-size chunking
    under another name — which is exactly how a correct FastCDC failed its edit-stability
    test in the `typescript` port."""
    p = cdc_params(TARGET)
    bounds = cdc_boundaries(seeded(600_000), TARGET)
    forced = [b for b in bounds if b % p.max_size == 0]
    assert len(forced) < len(bounds), (
        "every boundary is a forced max_size boundary — the corpus never satisfies the "
        "mask, so nothing below is testing content-defined chunking"
    )


# ── §3.6.3 boundaries ────────────────────────────────────────────────────────


def test_boundaries_are_deterministic():
    data = seeded(400_000)
    assert cdc_boundaries(data, TARGET) == cdc_boundaries(data, TARGET)


def test_boundaries_respect_min_and_max_size_and_cover_the_input():
    p = cdc_params(TARGET)
    data = seeded(400_000)
    bounds = cdc_boundaries(data, TARGET)
    prev = 0
    for index, end in enumerate(bounds):
        size = end - prev
        if index != len(bounds) - 1:
            assert size >= p.min_size, f"chunk {index} is {size} B, below min_size {p.min_size}"
        assert size <= p.max_size, f"chunk {index} is {size} B, above max_size {p.max_size}"
        prev = end
    assert prev == len(data), "boundaries must cover the input exactly"


def test_edit_stability_a_one_byte_insertion_does_not_reshuffle_later_boundaries():
    """§3.6.5 calls this "the most interop-critical" vector."""
    data = seeded(600_000)
    edited = data[:10] + b"\xff" + data[10:]

    before = cdc_boundaries(data, TARGET)
    after = cdc_boundaries(edited, TARGET)

    shifted = {b - 1 for b in after}
    survivors = sum(1 for b in before if b in shifted)
    assert survivors >= len(before) // 2, (
        f"only {survivors}/{len(before)} boundaries survived a 1-byte insertion — "
        "edit-stability is the reason §3.6 recommends FastCDC at all"
    )


def test_content_that_never_satisfies_the_mask_degenerates_to_max_size():
    """Not a defect — the forced-boundary arm of `find_boundary` is spec'd, and this is
    what reaching it looks like: every boundary on an exact multiple of `max_size`,
    edit-stability gone, and the blob still perfectly conformant."""
    p = cdc_params(TARGET)
    bounds = cdc_boundaries(mask_evading(TARGET * 6), TARGET)
    assert bounds[:3] == [p.max_size, p.max_size * 2, p.max_size * 3]


def test_the_fingerprint_is_bounded_to_64_bits():
    """Python ints are unbounded, so `& _U64` after every step is load-bearing and is NOT
    in the pseudocode. Without it the fingerprint keeps high bits a 64-bit implementation
    discards — and since the mask test reads only low bits, the divergence appears only on
    inputs long enough to overflow. Never in a small test; always in a real file.

    Asserted by running an input long enough that an unbounded accumulator would have
    exceeded 64 bits many times over, and confirming the boundaries still match a
    deliberately re-derived bounded computation."""
    data = seeded(300_000, seed=0x1234_5678)
    bounds = cdc_boundaries(data, TARGET)

    gear = gear_table()
    p = cdc_params(TARGET)
    u64 = (1 << 64) - 1
    expected: list[int] = []
    offset = 0
    while offset < len(data):
        remaining = len(data) - offset
        if remaining <= p.min_size:
            end = offset + remaining
        else:
            fp = 0
            i = offset + p.min_size
            end = min(offset + p.max_size, len(data))
            limit1 = min(offset + p.target_size, len(data))
            hit = False
            while i < limit1:
                fp = ((fp << 1) + gear[data[i]]) & u64
                if (fp & p.mask_s) == 0:
                    end, hit = i + 1, True
                    break
                i += 1
            if not hit:
                limit2 = min(offset + p.max_size, len(data))
                while i < limit2:
                    fp = ((fp << 1) + gear[data[i]]) & u64
                    if (fp & p.mask_l) == 0:
                        end, hit = i + 1, True
                        break
                    i += 1
                if not hit:
                    end = i
        expected.append(end)
        offset = end

    assert bounds == expected


# ── §3.2 fixed-size, and §2.1's dedup identity ───────────────────────────────


def test_fixed_size_has_no_edit_stability_and_that_is_expected():
    data = seeded(400_000)
    edited = b"\xff" + data
    a = create_blob_fixed(data, TARGET)
    b = create_blob_fixed(edited, TARGET)
    b_hashes = {bytes(c.hash) for c in b.chunks}
    shared = sum(1 for c in a.chunks if bytes(c.hash) in b_hashes)
    assert shared == 0, "an insertion at offset 0 shifts every fixed-size boundary"


def test_the_blob_records_the_dedup_identity_and_the_ordered_list():
    data = seeded(200_000)
    blob = create_blob_cdc(data, TARGET)
    assert blob.blob.type == "system/content/blob"
    assert blob.blob.uint("total_size") == len(data)
    assert blob.blob.uint("chunk_size") == TARGET
    assert blob.blob.uint("chunking") == CHUNKING_FASTCDC_NC2
    listed = [bytes(h) for h in blob.blob.field("chunks")]
    assert listed == [bytes(c.hash) for c in blob.chunks], "order determines reassembly order"


def test_identical_payloads_dedup_to_one_chunk_entity():
    repeated = b"A" * (TARGET * 3)
    blob = create_blob_fixed(repeated, TARGET)
    assert len(blob.chunks) == 3
    assert len({bytes(c.hash) for c in blob.chunks}) == 1, "§2.2's whole point"


def test_same_content_and_parameters_give_the_same_blob_hash():
    data = seeded(150_000)
    assert create_blob_cdc(data, TARGET).blob.hash == create_blob_cdc(data, TARGET).blob.hash
    assert create_blob_cdc(data, TARGET).blob.hash != create_blob_cdc(data, TARGET * 2).blob.hash
    assert create_blob_cdc(data, TARGET).blob.hash != create_blob_fixed(data, TARGET).blob.hash


def test_zero_length_input_produces_an_empty_chunk_list():
    """C-1 in `docs/SPEC-AMBIGUITIES.md`, carried identically here and in the `typescript`
    port so the two cannot silently diverge on an open question."""
    blob = create_blob_cdc(b"", TARGET)
    assert blob.chunks == ()
    assert blob.blob.uint("total_size") == 0
    assert blob.blob.field("chunks") == []
