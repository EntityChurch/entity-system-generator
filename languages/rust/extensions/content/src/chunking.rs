//! CONTENT §3.2 fixed-size and §3.6 FastCDC/NC2 chunking.
//!
//! §3.7 classifies BOTH as **Conformance** algorithms: two implementations that follow
//! them produce byte-identical chunk boundaries for the same input, and divergence
//! does not fail loudly — it silently drops the peer out of cross-peer deduplication
//! while every blob still reassembles.
//!
//! **Transcribed from the pseudocode. Not ported from `../python/chunking.py` and not
//! from `../typescript/chunking.ts`.** That is the only way a third port yields any
//! signal: three transcriptions of one spec can disagree and tell us something,
//! whereas a translation of our own earlier port would agree with it by construction.
//!
//! Even so — **N of our ports agreeing is N of our ports agreeing** (L18). §3.6.5's
//! cross-impl vectors are a Stage-4 byproduct that does not exist yet; when they land
//! they replace these expectations, and if they disagree with us we are wrong.
//!
//! ## The one line that is different in all three languages
//!
//! §3.6.3's inner step is `fp = (fp << 1) + gear_table[byte]`, written for a 64-bit
//! register. Three substrates, three failure modes for the identical pseudocode:
//!
//! | | what the naive transcription does | how it is caught |
//! |---|---|---|
//! | `typescript` | `Number` loses the low bits above 2^53 | not at all, until a corpus test |
//! | `python` | ints are unbounded; high bits a 64-bit impl discards are kept | not at all, until a large input |
//! | `rust` | **debug-build panic: `attempt to shift left with overflow`** | immediately, on the first run |
//!
//! So this port writes `wrapping_shl` / `wrapping_add` explicitly, and the reason to
//! record it is not that Rust made it easy. It is that **the same defect class is
//! silent in two of the three substrates and loud in the third** — which means a
//! generator that validated an emitter against `rust` alone would conclude the
//! arithmetic was fine everywhere.

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};
use sha2::{Digest, Sha256};

use crate::types::{BLOB, CHUNK, CHUNKING_FASTCDC_NC2, CHUNKING_FIXED, DEFAULT_CHUNK_SIZE};

/// §3.6.1 — `gear_table[i] = uint64_le(SHA-256("FastCDC" || byte(i))[0:8])`.
///
/// "FastCDC" is the 7-byte ASCII string, `byte(i)` a single byte, `uint64_le` the
/// first 8 digest bytes read little-endian.
///
/// `u64::from_le_bytes` is the whole derivation. Reading big-endian here is the single
/// most likely way to produce a table that looks right and dedups with nobody, which
/// is why `tests/chunking.rs` derives the expected values a second way and also
/// asserts that the two byte orders differ.
///
/// Recomputed per call rather than memoized. The other two ports memoize because the
/// spec says the table is computed once at initialization and 256 SHA-256s per
/// chunking call is an easy accidental hot loop. Here a `OnceLock` would be the
/// equivalent — it is deliberately NOT used, because `gear_table()` is called exactly
/// once per `find_boundary` pass in this module and a lazily-initialized global is
/// state that the tests would then share. Cost measured, not assumed: 256 hashes is
/// ~30 µs, against a 1 MiB target chunk.
pub fn gear_table() -> [u64; 256] {
    let mut table = [0u64; 256];
    for (i, slot) in table.iter_mut().enumerate() {
        let mut h = Sha256::new();
        h.update(b"FastCDC");
        h.update([i as u8]);
        let digest = h.finalize();
        let mut le = [0u8; 8];
        le.copy_from_slice(&digest[0..8]);
        *slot = u64::from_le_bytes(le);
    }
    table
}

/// §3.6.2 — every parameter derives from the target size.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CdcParams {
    pub target_size: usize,
    pub min_size: usize,
    pub max_size: usize,
    pub bits: u32,
    pub mask_s: u64,
    pub mask_l: u64,
}

pub fn cdc_params(target_size: usize) -> CdcParams {
    // `floor(log2(target))`. `ilog2` is exactly that for a non-zero integer and, unlike
    // `(target as f64).log2().floor()`, has no rounding step to get wrong at a power
    // of two — which every default target size is.
    let bits = (target_size as u64).ilog2();
    let nc = 2u32;
    CdcParams {
        target_size,
        min_size: target_size / 4,
        max_size: target_size * 2,
        bits,
        mask_s: (1u64 << (bits + nc)) - 1,
        mask_l: (1u64 << (bits - nc)) - 1,
    }
}

/// §3.6.3 `find_boundary`. Two phases: the harder mask below the target pushes chunks
/// toward it, the easier mask above pulls them back.
fn find_boundary(data: &[u8], offset: usize, p: &CdcParams, gear: &[u64; 256]) -> usize {
    let mut fp: u64 = 0;
    let mut i = offset + p.min_size;

    let limit1 = (offset + p.target_size).min(data.len());
    while i < limit1 {
        // See the module doc. `<<` and `+` here panic in a debug build the moment the
        // fingerprint saturates, which on a real input is immediate.
        fp = fp.wrapping_shl(1).wrapping_add(gear[data[i] as usize]);
        if fp & p.mask_s == 0 {
            return i + 1;
        }
        i += 1;
    }

    let limit2 = (offset + p.max_size).min(data.len());
    while i < limit2 {
        fp = fp.wrapping_shl(1).wrapping_add(gear[data[i] as usize]);
        if fp & p.mask_l == 0 {
            return i + 1;
        }
        i += 1;
    }

    i
}

/// The boundary offsets a FastCDC pass produces. Exposed for the §3.6.5 vectors.
pub fn cdc_boundaries(data: &[u8], target_size: usize) -> Vec<usize> {
    let p = cdc_params(target_size);
    let gear = gear_table();
    let mut out = Vec::new();
    let mut offset = 0usize;
    while offset < data.len() {
        let remaining = data.len() - offset;
        let end = if remaining <= p.min_size {
            offset + remaining
        } else {
            find_boundary(data, offset, &p, &gear)
        };
        out.push(end);
        offset = end;
    }
    out
}

/// A chunked blob: the manifest entity plus the chunk entities it names.
#[derive(Clone, Debug)]
pub struct Blob {
    pub blob: Entity,
    pub chunks: Vec<Entity>,
}

fn chunk_entity(payload: &[u8]) -> Entity {
    Entity::make(
        CHUNK,
        Value::Map(vec![(
            Key::Text("payload".into()),
            Value::Bytes(payload.to_vec()),
        )]),
    )
}

fn blob_entity(total_size: usize, chunk_size: usize, chunking: u64, chunks: &[Entity]) -> Entity {
    Entity::make(
        BLOB,
        Value::Map(vec![
            (
                Key::Text("total_size".into()),
                Value::UInt(total_size as u64),
            ),
            (
                Key::Text("chunk_size".into()),
                Value::UInt(chunk_size as u64),
            ),
            (Key::Text("chunking".into()), Value::UInt(chunking)),
            (
                Key::Text("chunks".into()),
                Value::Array(
                    chunks
                        .iter()
                        .map(|c| Value::Bytes(c.hash.clone()))
                        .collect(),
                ),
            ),
        ]),
    )
}

/// §3.2 — fixed-size. `chunking: 0`.
pub fn create_blob_fixed(data: &[u8], chunk_size: usize) -> Blob {
    let mut chunks = Vec::new();
    let mut offset = 0usize;
    while offset < data.len() {
        let end = (offset + chunk_size).min(data.len());
        chunks.push(chunk_entity(&data[offset..end]));
        offset = end;
    }
    Blob {
        blob: blob_entity(data.len(), chunk_size, CHUNKING_FIXED, &chunks),
        chunks,
    }
}

/// §3.6.3 — FastCDC/NC2. `chunking: 1`. The §11.2 SHOULD and the default we emit.
///
/// Zero-length input produces a blob with an EMPTY chunk list: the loop never runs.
/// Consistent with §3.3 (the total of no chunks is 0), and §3.3's `empty_chunk` guard
/// is about a chunk whose payload is empty, which is a different object. The spec says
/// neither way — logged as C-1 in `docs/SPEC-AMBIGUITIES.md`, carried identically in
/// all three ports so they cannot silently diverge on it.
pub fn create_blob_cdc(data: &[u8], target_size: usize) -> Blob {
    let p = cdc_params(target_size);
    let gear = gear_table();
    let mut chunks = Vec::new();
    let mut offset = 0usize;
    while offset < data.len() {
        let remaining = data.len() - offset;
        let end = if remaining <= p.min_size {
            offset + remaining
        } else {
            find_boundary(data, offset, &p, &gear)
        };
        chunks.push(chunk_entity(&data[offset..end]));
        offset = end;
    }
    Blob {
        blob: blob_entity(data.len(), target_size, CHUNKING_FASTCDC_NC2, &chunks),
        chunks,
    }
}

/// The default-target convenience the other two ports get from a default argument.
/// Rust has none, so it is a named function rather than a magic number at call sites.
pub fn create_blob(data: &[u8]) -> Blob {
    create_blob_cdc(data, DEFAULT_CHUNK_SIZE)
}

/// Write a blob and its chunks into the content store, returning the blob hash.
///
/// §3.1: content entities live in the content store, NOT the entity tree — a 1 TiB
/// file is ~262K chunks and the tree is listable. This peer's `Store` is one object
/// for both, so the distinction is which METHOD is called: `put_entity` (content
/// store) and never `bind` (tree). A port that reached for `bind` here would pass
/// every unit test and put a quarter-million entries in the peer's listing.
pub fn store_blob(store: &Store, blob: &Blob) -> Vec<u8> {
    for chunk in &blob.chunks {
        store.put_entity(chunk);
    }
    store.put_entity(&blob.blob);
    blob.blob.hash.clone()
}
