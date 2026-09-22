/**
 * CONTENT §3.2 fixed-size and §3.6 FastCDC/NC2 chunking.
 *
 * §3.7 classifies BOTH as **Conformance** algorithms: two implementations that
 * follow them produce byte-identical chunk boundaries for the same input, and
 * divergence does not fail loudly — it silently drops the peer out of cross-peer
 * deduplication while every blob still reassembles. That is why this file is
 * transcribed line-by-line from the pseudocode rather than "written to be
 * equivalent", and why the unit tests pin the gear table and the boundary offsets.
 *
 * **This module's output is not evidence about the spec.** Three of our ports
 * agreeing is three of our ports agreeing (L18). The cross-impl vectors §3.6.5
 * names are a Stage-4 byproduct that does not exist yet; when they land they
 * replace these tests' expectations, and if they disagree with us we are wrong.
 */

import { Entity, Ecf, crypto as peerCrypto, type ContentStore } from "entity-core-protocol-typescript";

import { Chunking, ContentTypes, DEFAULT_CHUNK_SIZE } from "./types.js";

/**
 * §3.6.1 — `gear_table[i] = uint64_le(SHA-256("FastCDC" || byte(i))[0:8])`.
 *
 * "FastCDC" is the 7-byte ASCII string, `byte(i)` a single byte, `uint64_le` the
 * first 8 digest bytes read little-endian. Computed once, memoized: the spec says
 * "the table is computed once at initialization" and 256 SHA-256s per chunking
 * call would be an easy accidental hot loop.
 */
let GEAR_TABLE: BigUint64Array | null = null;

export function gearTable(): BigUint64Array {
  if (GEAR_TABLE !== null) return GEAR_TABLE;
  const table = new BigUint64Array(256);
  const prefix = new TextEncoder().encode("FastCDC");
  const buf = new Uint8Array(prefix.length + 1);
  buf.set(prefix, 0);
  for (let i = 0; i < 256; i++) {
    buf[prefix.length] = i;
    const digest = peerCrypto.defaultProvider.sha256.digest(buf);
    let value = 0n;
    // Little-endian over the FIRST 8 bytes. Reading big-endian here is the single
    // most likely way to produce a table that looks right and dedups with nobody.
    for (let b = 7; b >= 0; b--) {
      value = (value << 8n) | BigInt(digest[b] ?? 0);
    }
    table[i] = value;
  }
  GEAR_TABLE = table;
  return table;
}

/** §3.6.2 — every parameter derives from the target size. */
export interface CdcParams {
  readonly targetSize: number;
  readonly minSize: number;
  readonly maxSize: number;
  readonly bits: number;
  readonly maskS: bigint;
  readonly maskL: bigint;
}

export function cdcParams(targetSize: number = DEFAULT_CHUNK_SIZE): CdcParams {
  const bits = Math.floor(Math.log2(targetSize));
  const NC = 2n;
  return {
    targetSize,
    minSize: Math.floor(targetSize / 4),
    maxSize: targetSize * 2,
    bits,
    maskS: (1n << (BigInt(bits) + NC)) - 1n,
    maskL: (1n << (BigInt(bits) - NC)) - 1n,
  };
}

const U64 = (1n << 64n) - 1n;

/**
 * §3.6.3 `find_boundary`. Two phases: the harder mask below the target pushes
 * chunks toward it, the easier mask above pulls them back.
 *
 * The `fp << 1` is a 64-bit shift. JS `bigint` is unbounded, so the mask must be
 * applied explicitly — an unbounded `fp` grows without limit and, worse, keeps
 * high bits that a 64-bit implementation discards, so the `& mask` test diverges
 * only for inputs long enough to overflow. That is a divergence no small test
 * would find and every real file would.
 */
function findBoundary(data: Uint8Array, offset: number, p: CdcParams): number {
  const gear = gearTable();
  let fp = 0n;
  let i = offset + p.minSize;

  const limit1 = Math.min(offset + p.targetSize, data.length);
  while (i < limit1) {
    fp = ((fp << 1n) + (gear[data[i] ?? 0] ?? 0n)) & U64;
    if ((fp & p.maskS) === 0n) return i + 1;
    i++;
  }

  const limit2 = Math.min(offset + p.maxSize, data.length);
  while (i < limit2) {
    fp = ((fp << 1n) + (gear[data[i] ?? 0] ?? 0n)) & U64;
    if ((fp & p.maskL) === 0n) return i + 1;
    i++;
  }

  return i;
}

/** The boundary offsets a FastCDC pass produces. Exposed for the §3.6.5 vectors. */
export function cdcBoundaries(data: Uint8Array, targetSize: number = DEFAULT_CHUNK_SIZE): readonly number[] {
  const p = cdcParams(targetSize);
  const out: number[] = [];
  let offset = 0;
  while (offset < data.length) {
    const remaining = data.length - offset;
    const end = remaining <= p.minSize ? offset + remaining : findBoundary(data, offset, p);
    out.push(end);
    offset = end;
  }
  return out;
}

/** A chunked blob: the manifest entity plus the chunk entities it names. */
export interface Blob {
  readonly blob: Entity;
  readonly chunks: readonly Entity[];
}

function chunkEntity(payload: Uint8Array): Entity {
  return Entity.create(ContentTypes.Chunk, Ecf.map(["payload", Ecf.bytes(payload)]));
}

function blobEntity(totalSize: number, chunkSize: number, chunking: number, chunks: readonly Entity[]): Entity {
  return Entity.create(
    ContentTypes.Blob,
    Ecf.map(
      ["total_size", Ecf.uint(BigInt(totalSize))],
      ["chunk_size", Ecf.uint(BigInt(chunkSize))],
      ["chunking", Ecf.uint(BigInt(chunking))],
      ["chunks", Ecf.array(chunks.map((c) => Ecf.bytes(c.contentHash)))],
    ),
  );
}

/** §3.2 — fixed-size. `chunking: 0`. */
export function createBlobFixed(data: Uint8Array, chunkSize: number = DEFAULT_CHUNK_SIZE): Blob {
  const chunks: Entity[] = [];
  let offset = 0;
  while (offset < data.length) {
    const end = Math.min(offset + chunkSize, data.length);
    chunks.push(chunkEntity(data.subarray(offset, end)));
    offset = end;
  }
  return { blob: blobEntity(data.length, chunkSize, Chunking.Fixed, chunks), chunks };
}

/**
 * §3.6.3 — FastCDC/NC2. `chunking: 1`. The §11.2 SHOULD and the default we emit.
 *
 * Zero-length input produces a blob with an EMPTY chunk list: the `while` never
 * runs. `total_size: 0` and `chunks: []` is internally consistent under §3.3
 * (total of no chunks is 0), and §3.3's `empty_chunk` guard is about a chunk whose
 * payload is empty, which is a different thing. Logged in the authoring notes
 * because the spec does not say it either way.
 */
export function createBlobCdc(data: Uint8Array, targetSize: number = DEFAULT_CHUNK_SIZE): Blob {
  const p = cdcParams(targetSize);
  const chunks: Entity[] = [];
  let offset = 0;
  while (offset < data.length) {
    const remaining = data.length - offset;
    const end = remaining <= p.minSize ? offset + remaining : findBoundary(data, offset, p);
    chunks.push(chunkEntity(data.subarray(offset, end)));
    offset = end;
  }
  return { blob: blobEntity(data.length, targetSize, Chunking.FastCdcNc2, chunks), chunks };
}

/**
 * Write a blob and its chunks into the content store (§3.1: content entities live
 * in the content store, NOT the entity tree — a 1 TiB file is ~262K chunks and the
 * tree is listable).
 */
export function storeBlob(store: ContentStore, blob: Blob): Uint8Array {
  for (const chunk of blob.chunks) store.put(chunk);
  store.put(blob.blob);
  return blob.blob.contentHash;
}
