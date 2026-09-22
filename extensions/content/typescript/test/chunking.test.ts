/**
 * §3.6 FastCDC and §3.2 fixed-size — the Conformance algorithms.
 *
 * **These tests are not evidence about the spec.** §3.6.5 says the cross-impl vectors
 * are a Stage-4 byproduct the architecture team does not pre-author, and they do not
 * exist yet. When they land they replace these expectations, and if they disagree with
 * us we are wrong (L18: N of our ports agreeing is N of our ports agreeing).
 *
 * What they CAN do meanwhile is catch the failure mode §3.6 names: divergence that is
 * silent. A wrong gear table, a big-endian read, or an unbounded fingerprint still
 * produces blobs that reassemble perfectly and deduplicate with nobody. So the gear
 * table is checked against an INDEPENDENT derivation — `node:crypto` + a little-endian
 * `DataView` read — rather than against a constant this module produced.
 */

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";

import { Ecf } from "entity-core-protocol-typescript";
import {
  cdcBoundaries,
  cdcParams,
  createBlobCdc,
  createBlobFixed,
  gearTable,
  Chunking,
  DEFAULT_CHUNK_SIZE,
} from "@entity-core/extension-content";

/** §3.6.1, derived a second way: node's SHA-256 and a real little-endian read. */
function independentGearEntry(i: number): bigint {
  const digest = createHash("sha256").update(Buffer.concat([Buffer.from("FastCDC", "ascii"), Buffer.from([i])])).digest();
  return new DataView(digest.buffer, digest.byteOffset, 8).getBigUint64(0, true);
}

test("§3.6.1 gear table matches an independent derivation for all 256 entries", () => {
  const table = gearTable();
  assert.equal(table.length, 256);
  for (let i = 0; i < 256; i++) {
    assert.equal(table[i], independentGearEntry(i), `gear_table[${i}]`);
  }
});

test("§3.6.1 the table is not accidentally big-endian", () => {
  // A big-endian read of the same digest is the single most likely wrong table, and it
  // would pass every "is it deterministic" test. Assert the two differ so a future
  // refactor cannot quietly swap them.
  const digest = createHash("sha256").update(Buffer.concat([Buffer.from("FastCDC", "ascii"), Buffer.from([0])])).digest();
  const bigEndian = new DataView(digest.buffer, digest.byteOffset, 8).getBigUint64(0, false);
  assert.notEqual(gearTable()[0], bigEndian);
});

test("§3.6.2 parameters derive from the target size", () => {
  const p = cdcParams(DEFAULT_CHUNK_SIZE);
  assert.equal(p.targetSize, 1_048_576);
  assert.equal(p.minSize, 262_144);
  assert.equal(p.maxSize, 2_097_152);
  assert.equal(p.bits, 20);
  assert.equal(p.maskS, 0x003fffffn);
  assert.equal(p.maskL, 0x0003ffffn);
});

/**
 * Deterministic pseudo-random bytes with a documented seed (§3.6.5's canonical input
 * shape).
 *
 * **xorshift32, and the first attempt was an LCG that quietly broke the test.**
 * `x = (x * 1103515245 + 12345) >>> 0` is a textbook LCG and wrong in JS: the product
 * exceeds 2^53, so the float multiply loses the low bits before `>>> 0` truncates.
 * The resulting stream has 256 distinct byte values and no short period — it looks
 * random by every cheap check — but its low bits are structured enough that
 * `fp & mask_s` never hits zero. Every chunk then ran to the forced `max_size`
 * boundary, FastCDC degenerated into fixed-size chunking at 2x the target, and the
 * edit-stability test failed against a CORRECT implementation. Kept in the record
 * because a chunker test is only as good as its corpus, and "the test data was the
 * defect" is a failure mode a passing suite never reports. The degenerate shape is
 * real content, so it now has its own test below rather than being deleted.
 */
function seeded(length: number, seed = 0x9e3779b9): Uint8Array {
  const out = new Uint8Array(length);
  let x = seed >>> 0;
  for (let i = 0; i < length; i++) {
    x ^= x << 13;
    x >>>= 0;
    x ^= x >>> 17;
    x ^= x << 5;
    x >>>= 0;
    out[i] = x & 0xff;
  }
  return out;
}

/** Bytes whose low bits never satisfy the boundary mask — see {@link seeded}. */
function maskEvading(length: number): Uint8Array {
  const out = new Uint8Array(length);
  let x = 0x9e37 >>> 0;
  for (let i = 0; i < length; i++) {
    x = (x * 1103515245 + 12345) >>> 0;
    out[i] = (x >>> 16) & 0xff;
  }
  return out;
}

const TARGET = 65_536; // small target keeps the tests fast; every derivation still applies

test("§3.6.3 boundaries are deterministic", () => {
  const data = seeded(400_000);
  assert.deepEqual(cdcBoundaries(data, TARGET), cdcBoundaries(data, TARGET));
});

test("§3.6.3 boundaries respect min_size and max_size", () => {
  const p = cdcParams(TARGET);
  const data = seeded(400_000);
  const bounds = cdcBoundaries(data, TARGET);
  let prev = 0;
  for (const [idx, end] of bounds.entries()) {
    const size = end - prev;
    const isFinal = idx === bounds.length - 1;
    if (!isFinal) {
      assert.ok(size >= p.minSize, `chunk ${idx} is ${size} B, below min_size ${p.minSize}`);
    }
    assert.ok(size <= p.maxSize, `chunk ${idx} is ${size} B, above max_size ${p.maxSize}`);
    prev = end;
  }
  assert.equal(prev, data.length, "boundaries must cover the input exactly");
});

test("§3.6 edit-stability: a 1-byte insertion does not reshuffle later boundaries", () => {
  // §3.6.5 calls this "the most interop-critical" vector, and it is the property fixed-size
  // chunking does NOT have — which is the next test.
  const data = seeded(600_000);
  const edited = new Uint8Array(data.length + 1);
  edited.set(data.subarray(0, 10), 0);
  edited[10] = 0xff;
  edited.set(data.subarray(10), 11);

  const before = cdcBoundaries(data, TARGET);
  const after = cdcBoundaries(edited, TARGET);

  // Later boundaries realign to (original + 1). Count how many survive; FastCDC's whole
  // claim is that this is most of them, not all of them.
  const shifted = new Set(after.map((b) => b - 1));
  const survivors = before.filter((b) => shifted.has(b)).length;
  assert.ok(
    survivors >= Math.floor(before.length / 2),
    `only ${survivors}/${before.length} boundaries survived a 1-byte insertion — ` +
      "edit-stability is the reason §3.6 recommends FastCDC at all",
  );
});

test("§3.6.3 content that never satisfies the mask degenerates to max_size", () => {
  // Not a defect — the forced-boundary arm of `find_boundary` is spec'd and this is
  // what reaching it looks like. Worth pinning because the degenerate shape is
  // indistinguishable from healthy chunking unless you look at the offsets: every
  // boundary lands on an exact multiple of max_size, edit-stability is gone, and the
  // blob is still perfectly conformant. A deployment whose content looks like this is
  // paying FastCDC's cost for fixed-size chunking's behaviour.
  const p = cdcParams(TARGET);
  const data = maskEvading(TARGET * 6);
  const bounds = cdcBoundaries(data, TARGET);
  assert.deepEqual(
    bounds.slice(0, 3),
    [p.maxSize, p.maxSize * 2, p.maxSize * 3],
    "every boundary is the forced max_size one",
  );
});

test("§3.2 fixed-size chunking has no edit-stability, and that is expected", () => {
  const data = seeded(400_000);
  const edited = new Uint8Array(data.length + 1);
  edited[0] = 0xff;
  edited.set(data, 1);
  const a = createBlobFixed(data, TARGET);
  const b = createBlobFixed(edited, TARGET);
  const aHashes = a.chunks.map((c) => c.contentHashHex);
  const bHashes = new Set(b.chunks.map((c) => c.contentHashHex));
  const shared = aHashes.filter((h) => bHashes.has(h)).length;
  assert.equal(shared, 0, "an insertion at offset 0 shifts every fixed-size boundary (§3.6 opener)");
});

test("§2.1 the blob records the dedup identity (chunking, chunk_size) and the ordered list", () => {
  const data = seeded(200_000);
  const { blob, chunks } = createBlobCdc(data, TARGET);
  assert.equal(blob.type, "system/content/blob");
  assert.equal(Ecf.asUint(Ecf.require(blob.data, "total_size")), BigInt(data.length));
  assert.equal(Ecf.asUint(Ecf.require(blob.data, "chunk_size")), BigInt(TARGET));
  assert.equal(Ecf.asUint(Ecf.require(blob.data, "chunking")), BigInt(Chunking.FastCdcNc2));
  const listed = Ecf.asArray(Ecf.require(blob.data, "chunks")).map((h) => Buffer.from(Ecf.asBytes(h)).toString("hex"));
  assert.deepEqual(listed, chunks.map((c) => c.contentHashHex), "order determines reassembly order");
});

test("§2.2 identical payloads dedup to one chunk entity", () => {
  const repeated = new Uint8Array(TARGET * 3).fill(0x41);
  const { chunks } = createBlobFixed(repeated, TARGET);
  const unique = new Set(chunks.map((c) => c.contentHashHex));
  assert.equal(chunks.length, 3);
  assert.equal(unique.size, 1, "three identical 64 KiB blocks are ONE entity — §2.2's whole point");
});

test("same content + same parameters -> same blob hash (the dedup identity)", () => {
  const data = seeded(150_000);
  assert.equal(createBlobCdc(data, TARGET).blob.contentHashHex, createBlobCdc(data, TARGET).blob.contentHashHex);
  assert.notEqual(
    createBlobCdc(data, TARGET).blob.contentHashHex,
    createBlobCdc(data, TARGET * 2).blob.contentHashHex,
    "§2.1: changing chunk_size produces different boundaries and no dedup",
  );
  assert.notEqual(
    createBlobCdc(data, TARGET).blob.contentHashHex,
    createBlobFixed(data, TARGET).blob.contentHashHex,
    "§2.1: chunking 0 vs 1 is a different configuration",
  );
});
