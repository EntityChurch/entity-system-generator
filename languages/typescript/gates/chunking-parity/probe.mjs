// gates/chunking-parity/probe.mjs — the `typescript` arm of the chunking-parity gate.
//
// Reads the shared corpus, runs §3.6 FastCDC/NC2 through THE STAGED PACKAGE (resolved
// by name through its `exports` map, not by a path into the source tree), and prints one
// JSON line. `compare.py` diffs the three.
//
// Three numbers, each answering a different question:
//   boundary_count   — did the three ports cut the same NUMBER of chunks?
//   boundary_digest  — did they cut at the same OFFSETS? (a count can match by accident)
//   blob_hash        — do the resulting §2.1 entities hash identically? This is the one
//                      that matters: it is the deduplication identity, and two peers that
//                      disagree here silently fail to dedup with each other while every
//                      blob still reassembles.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const corpusPath = process.argv[2];
const targetSize = Number(process.argv[3]);
if (!corpusPath || !Number.isInteger(targetSize)) {
  console.error("usage: probe.mjs <corpus-path> <target-size>");
  process.exit(2);
}

const { cdcBoundaries, createBlobCdc } = await import("@entity-core/extension-content");

const data = new Uint8Array(readFileSync(corpusPath));
const bounds = cdcBoundaries(data, targetSize);
const blob = createBlobCdc(data, targetSize);

// `contentHash`, not `hash`. The three peers name this field three ways -- `contentHash`
// here, `hash` on both `python` and `rust` -- and the first draft of this probe reached
// for `.hash`, got `undefined`, and threw inside `Buffer.from`. It threw, which is the
// good outcome: a probe that had silently hexed `undefined` to "" would have reported
// three identical empty blob hashes and read as perfect parity.
const hex = (bytes) => {
  if (!(bytes instanceof Uint8Array)) {
    throw new TypeError(`expected a Uint8Array content hash, got ${typeof bytes}`);
  }
  return Buffer.from(bytes).toString("hex");
};

console.log(
  JSON.stringify({
    port: "typescript",
    corpus_bytes: data.length,
    target_size: targetSize,
    boundary_count: bounds.length,
    boundary_digest: createHash("sha256").update(bounds.join(",")).digest("hex"),
    blob_hash: hex(blob.blob.contentHash),
    chunk_count: blob.chunks.length,
    first_chunk_hash: hex(blob.chunks[0].contentHash),
    last_chunk_hash: hex(blob.chunks[blob.chunks.length - 1].contentHash),
  }),
);
