//! §3.2 / §3.6 chunking, and the corpus assertions D15 requires of the tests that
//! depend on their input exercising a branch.
//!
//! **The corpus is the thing that went wrong last time.** AP-3: the `typescript`
//! edit-stability test failed against a CORRECT FastCDC because its LCG's low bits
//! never satisfied the boundary mask, every chunk ran to the forced `max_size`, and
//! FastCDC silently degenerated to fixed-size chunking at 2x the target. The stream had
//! 256 distinct byte values and no short period, so every cheap "is this random" check
//! passed. So this file asserts on the corpus before asserting on the algorithm.

use entity_content::{
    cdc_boundaries, cdc_params, create_blob_cdc, create_blob_fixed, gear_table, store_blob,
    CHUNKING_FASTCDC_NC2, CHUNKING_FIXED,
};
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::Value;
use sha2::{Digest, Sha256};

/// xorshift32, not an LCG. See the module doc: an LCG's low bits are the AP-3 defect.
fn xorshift32(seed: u32, len: usize) -> Vec<u8> {
    let mut x = seed;
    let mut out = Vec::with_capacity(len);
    while out.len() < len {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        out.extend_from_slice(&x.to_le_bytes());
    }
    out.truncate(len);
    out
}

// ── §3.6.1 the gear table ────────────────────────────────────────────────────

#[test]
fn gear_table_is_little_endian_and_derived_a_second_way() {
    let table = gear_table();
    // Derived independently of the implementation, byte by byte, for three entries.
    for i in [0usize, 1, 255] {
        let mut h = Sha256::new();
        h.update(b"FastCDC");
        h.update([i as u8]);
        let d = h.finalize();
        let expected = (d[0] as u64)
            | (d[1] as u64) << 8
            | (d[2] as u64) << 16
            | (d[3] as u64) << 24
            | (d[4] as u64) << 32
            | (d[5] as u64) << 40
            | (d[6] as u64) << 48
            | (d[7] as u64) << 56;
        assert_eq!(table[i], expected, "gear_table[{i}] is not uint64_le");
    }
}

#[test]
fn little_endian_and_big_endian_actually_differ() {
    // NEGATIVE CONTROL for the test above. If the first eight digest bytes happened to
    // be a palindrome the LE/BE distinction would be untestable at that index and the
    // assertion above would pass for a big-endian implementation. This asserts the
    // discriminating condition holds before relying on it.
    let table = gear_table();
    let mut differing = 0usize;
    for i in 0..256usize {
        let mut h = Sha256::new();
        h.update(b"FastCDC");
        h.update([i as u8]);
        let d = h.finalize();
        let mut be = [0u8; 8];
        be.copy_from_slice(&d[0..8]);
        if table[i] != u64::from_be_bytes(be) {
            differing += 1;
        }
    }
    assert_eq!(
        differing, 256,
        "every entry must distinguish LE from BE; {differing}/256 did"
    );
}

// ── §3.6.2 parameters ────────────────────────────────────────────────────────

#[test]
fn params_derive_from_the_target_size() {
    let p = cdc_params(1 << 20);
    assert_eq!(p.bits, 20);
    assert_eq!(p.min_size, 1 << 18);
    assert_eq!(p.max_size, 1 << 21);
    assert_eq!(p.mask_s, (1u64 << 22) - 1);
    assert_eq!(p.mask_l, (1u64 << 18) - 1);
    // `ilog2` vs `(x as f64).log2().floor()`: at a power of two the float route is one
    // rounding decision away from `bits - 1`, and every default target size is one.
    assert_eq!(cdc_params(1 << 16).bits, 16);
}

// ── the corpus assertion, before any algorithm assertion ─────────────────────

#[test]
fn the_corpus_actually_exercises_the_boundary_mask() {
    // THE AP-3 GUARD. If this fails, no chunking result below means anything: FastCDC
    // has degenerated to fixed-size at max_size and the edit-stability test is
    // measuring a different algorithm.
    let target = 4096usize;
    let data = xorshift32(0xC0FFEE, 400 * 1024);
    let p = cdc_params(target);
    let bounds = cdc_boundaries(&data, target);
    let forced = bounds
        .windows(2)
        .filter(|w| w[1] - w[0] == p.max_size)
        .count();
    assert!(
        bounds.len() > 20,
        "corpus produced only {} boundaries; too few to say anything",
        bounds.len()
    );
    assert!(
        forced * 2 < bounds.len(),
        "{forced} of {} chunks hit the forced max_size boundary -- the mask is never \
         satisfied and this corpus cannot exercise content-defined chunking (AP-3)",
        bounds.len()
    );
}

// ── §3.6.3 the property that makes CDC worth anything ────────────────────────

#[test]
fn an_insertion_realigns_the_boundaries_after_it() {
    let target = 4096usize;
    let original = xorshift32(0x5EED, 400 * 1024);
    let mut edited = original.clone();
    // Insert 7 bytes near the front. Fixed-size chunking would shift EVERY subsequent
    // boundary by 7 and share nothing after the insertion point.
    edited.splice(9_000..9_000, *b"INSERTED");

    let a = cdc_boundaries(&original, target);
    let b = cdc_boundaries(&edited, target);

    // Boundaries in the tail, expressed as distance from the end, must coincide.
    let tail = |v: &Vec<usize>, len: usize| -> Vec<usize> {
        v.iter().rev().take(8).map(|&x| len - x).collect()
    };
    assert_eq!(
        tail(&a, original.len()),
        tail(&b, edited.len()),
        "boundaries did not realign after the insertion -- this is fixed-size chunking"
    );
}

#[test]
fn a_stream_that_never_satisfies_the_mask_is_kept_as_its_own_case() {
    // The degenerate corpus, kept deliberately. Content that never satisfies the mask
    // is REAL -- long runs of one byte are the common case -- and the resulting blob is
    // perfectly conformant while being worthless for dedup. Keeping it as a named test
    // is what stops the AP-3 guard above from being read as "this input is invalid".
    let target = 4096usize;
    let data = vec![0u8; 200 * 1024];
    let p = cdc_params(target);
    let bounds = cdc_boundaries(&data, target);
    let forced = bounds
        .windows(2)
        .filter(|w| w[1] - w[0] == p.max_size)
        .count();
    assert!(
        forced > 0,
        "a constant stream should hit the forced boundary; the corpus is not degenerate"
    );
}

// ── §3.2 / §3.3 blob construction ────────────────────────────────────────────

#[test]
fn fixed_and_cdc_declare_different_chunking_identities() {
    let data = xorshift32(1, 40_000);
    let fixed = create_blob_fixed(&data, 4096);
    let cdc = create_blob_cdc(&data, 4096);
    assert_eq!(fixed.blob.uint_field("chunking"), Some(CHUNKING_FIXED));
    assert_eq!(cdc.blob.uint_field("chunking"), Some(CHUNKING_FASTCDC_NC2));
    // §2.1: (chunking, chunk_size) IS the dedup identity, so the two blobs MUST NOT
    // hash the same even where the byte ranges coincide.
    assert_ne!(fixed.blob.hash, cdc.blob.hash);
}

#[test]
fn chunks_cover_the_input_exactly_and_in_order() {
    let data = xorshift32(42, 90_000);
    let blob = create_blob_cdc(&data, 4096);
    let mut rebuilt: Vec<u8> = Vec::new();
    for c in &blob.chunks {
        match c.field("payload") {
            Some(Value::Bytes(p)) => rebuilt.extend_from_slice(p),
            other => panic!("chunk payload is not bytes: {other:?}"),
        }
    }
    assert_eq!(rebuilt, data);
    assert_eq!(
        blob.blob.uint_field("total_size"),
        Some(data.len() as u64)
    );
}

#[test]
fn a_zero_length_blob_has_an_empty_chunk_list() {
    // C-1 in docs/SPEC-AMBIGUITIES.md. The spec says neither way; all three ports carry
    // the same reading so they cannot silently diverge on it.
    let blob = create_blob_cdc(&[], 4096);
    assert!(blob.chunks.is_empty());
    assert_eq!(blob.blob.uint_field("total_size"), Some(0));
}

#[test]
fn identical_chunks_dedup_in_the_content_store() {
    // §2.2's whole point: a chunk carries its payload and nothing else -- no sequence
    // number, no parent ref -- so identical bytes hash identically across blobs.
    //
    // ALIGNED LENGTH, deliberately. Written first with 20,000 bytes and it failed at
    // 4 of 5 -- correctly. Under FIXED-SIZE chunking the first blob's tail chunk is a
    // 3,808-byte partial, and in the doubled input those same bytes fall inside a full
    // 4,096-byte chunk. Different payload, different hash, and nothing is wrong.
    //
    // Keeping the aligned case as the dedup assertion and the partial case as its own
    // named test below is the difference between measuring dedup and measuring
    // alignment. (This is also the property §11.2 recommends FastCDC for: content-
    // defined boundaries survive a shift that fixed-size boundaries do not.)
    let store = Store::new();
    let half = xorshift32(7, 4096 * 5);
    let mut doubled = half.clone();
    doubled.extend_from_slice(&half);

    let a = create_blob_fixed(&half, 4096);
    let b = create_blob_fixed(&doubled, 4096);
    store_blob(&store, &a);
    store_blob(&store, &b);

    assert_eq!(a.chunks.len(), 5);
    assert_eq!(b.chunks.len(), 10);
    let shared = b
        .chunks
        .iter()
        .filter(|c| a.chunks.iter().any(|x| x.hash == c.hash))
        .count();
    assert_eq!(
        shared,
        b.chunks.len(),
        "every chunk of the doubled blob should already be in the store"
    );
    // NEGATIVE CONTROL: the comparison is not vacuously true. Two blobs of unrelated
    // content must share nothing, or `shared == len` is a property of the assertion
    // rather than of the store.
    let other = create_blob_fixed(&xorshift32(8, 4096 * 5), 4096);
    let crossed = other
        .chunks
        .iter()
        .filter(|c| a.chunks.iter().any(|x| x.hash == c.hash))
        .count();
    assert_eq!(crossed, 0, "unrelated content must not dedup");
}

#[test]
fn a_partial_tail_chunk_does_not_dedup_under_fixed_size_chunking() {
    // The case the test above was originally written with, kept because it is the real
    // limitation of §3.2 rather than a defect: an unaligned length produces a short
    // tail chunk whose bytes are re-chunked differently in any longer input.
    let store = Store::new();
    let short = xorshift32(7, 20_000); // 4 full chunks + a 3,808-byte tail
    let mut doubled = short.clone();
    doubled.extend_from_slice(&short);

    let a = create_blob_fixed(&short, 4096);
    let b = create_blob_fixed(&doubled, 4096);
    store_blob(&store, &a);
    store_blob(&store, &b);

    let shared = b
        .chunks
        .iter()
        .filter(|c| a.chunks.iter().any(|x| x.hash == c.hash))
        .count();
    assert_eq!(
        shared,
        a.chunks.len() - 1,
        "exactly the aligned prefix should dedup; the partial tail cannot"
    );
}
