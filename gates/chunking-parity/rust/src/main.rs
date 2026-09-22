//! The `rust` arm of the chunking-parity gate.
//!
//! The `typescript` / `python` twins, same shape: read the shared corpus, run §3.6
//! FastCDC/NC2 through the cell across the crate boundary, print one JSON line.
//!
//! Three numbers, each answering a different question:
//!   `boundary_count`   — did the three ports cut the same NUMBER of chunks?
//!   `boundary_digest`  — did they cut at the same OFFSETS? (a count can match by accident)
//!   `blob_hash`        — do the resulting §2.1 entities hash identically? This is the one
//!                        that matters: it is the deduplication identity, and two peers
//!                        that disagree here silently fail to dedup with each other while
//!                        every blob still reassembles.

use entity_content::{cdc_boundaries, create_blob_cdc};
use sha2::{Digest, Sha256};

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: probe <corpus-path> <target-size>");
        std::process::exit(2);
    }
    let data = std::fs::read(&args[1]).expect("read corpus");
    let target_size: usize = args[2].parse().expect("target size");

    let bounds = cdc_boundaries(&data, target_size);
    let blob = create_blob_cdc(&data, target_size);

    let joined = bounds
        .iter()
        .map(|b| b.to_string())
        .collect::<Vec<_>>()
        .join(",");
    let mut h = Sha256::new();
    h.update(joined.as_bytes());

    println!(
        r#"{{"port":"rust","corpus_bytes":{},"target_size":{},"boundary_count":{},"boundary_digest":"{}","blob_hash":"{}","chunk_count":{},"first_chunk_hash":"{}","last_chunk_hash":"{}"}}"#,
        data.len(),
        target_size,
        bounds.len(),
        hex(&h.finalize()),
        hex(&blob.blob.hash),
        blob.chunks.len(),
        hex(&blob.chunks[0].hash),
        hex(&blob.chunks[blob.chunks.len() - 1].hash),
    );
}
