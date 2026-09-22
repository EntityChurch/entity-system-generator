/**
 * CONTENT — the SDK face.
 *
 * **There is no conformance gate on this face, anywhere, and per the operator that
 * is correct rather than a defect: the SDK is a convention.** So the extension is
 * its own instrument — the handler's conformance path runs THROUGH these functions
 * rather than beside them, and `EXTENSION.toml [sdk].*.reached_by` records, per
 * operation, which check reaches it. An operation with an empty `reached_by` is
 * genuinely unmeasured; that set is meant to stay near-empty, and today it holds
 * `AtPeer` (the oracle never exercises namespace scoping) and
 * `reassembleUnderCapability`.
 */

import {
  Ecf,
  Entity,
  type ContentStore,
  type EntityTree,
  type HandlerContext,
} from "entity-core-protocol-typescript";

import { reassembleContent, type ReassembleResult } from "./internal/reassemble.js";
import { ContentTypes, CONTENT_PATTERN } from "./types.js";

/** Lowercase hex INCLUDING the leading format byte (§6.4.2 / core §3.5). */
export function hashHexWithFormat(hash: Uint8Array): string {
  return Array.from(hash, (b) => b.toString(16).padStart(2, "0")).join("");
}

// ── EnsureClosure — §3.3 verify_content ─────────────────────────────────────────

export type ClosureVerdict =
  | { readonly complete: true; readonly totalSize: number; readonly chunkCount: number }
  | { readonly complete: false; readonly code: "missing_chunk" | "empty_chunk"; readonly hash: Uint8Array }
  | { readonly complete: false; readonly code: "size_mismatch" | "blob_not_found" | "not_a_blob"; readonly hash: Uint8Array };

/**
 * §3.3 — completeness and total-size consistency over a blob already in the store.
 *
 * §3.7 classifies this **Conformance**: "implementations MUST agree on whether a
 * blob is complete ... the completeness verdict is cross-peer-uniform." So the
 * three failure modes are named exactly as §3.3 names them, and the order matters:
 * a blob whose first chunk is missing reports `missing_chunk`, not `size_mismatch`,
 * even though the totals also disagree.
 *
 * Per-chunk size is deliberately NOT validated against `chunk_size` — §3.3 says so
 * outright, because content-defined chunking produces variable-size chunks and the
 * entity hash already guarantees chunk integrity.
 */
export function ensureClosure(store: ContentStore, blobHash: Uint8Array): ClosureVerdict {
  const blob = store.get(blobHash);
  if (blob === undefined) return { complete: false, code: "blob_not_found", hash: blobHash };
  if (blob.type !== ContentTypes.Blob) return { complete: false, code: "not_a_blob", hash: blobHash };

  const chunkHashes = Ecf.asArray(Ecf.require(blob.data, "chunks")).map((h) => Ecf.asBytes(h));
  let total = 0;
  for (const chunkHash of chunkHashes) {
    const chunk = store.get(chunkHash);
    if (chunk === undefined) return { complete: false, code: "missing_chunk", hash: chunkHash };
    const payload = Ecf.asBytes(Ecf.require(chunk.data, "payload"));
    if (payload.length === 0) return { complete: false, code: "empty_chunk", hash: chunkHash };
    total += payload.length;
  }

  const declared = Number(Ecf.asUint(Ecf.require(blob.data, "total_size")));
  if (total !== declared) return { complete: false, code: "size_mismatch", hash: blobHash };
  return { complete: true, totalSize: total, chunkCount: chunkHashes.length };
}

// ── AtPeer — §6.4.2 Hash Tree Presence ──────────────────────────────────────────

/**
 * The §6.4.2 canonical namespace probe: is hash `H` bound at
 * `{namespace}/{hex(H)}` in this peer's tree?
 *
 * `hex(H)` carries the format byte (66 chars under ECFv1-SHA-256, 98 under
 * SHA-384). Dropping it — using the bare 64-char digest — is the mistake §6.4.2
 * calls out by name; it destroys the algorithm discriminator and breaks URL ⇄
 * binding parity with NETWORK §6.5.6. Its length is implied by the leading byte
 * and is never assumed, so this does no length check at all.
 *
 * **Unmeasured by any gate.** The oracle's content category has no namespace
 * check. Stated, not hidden.
 */
export function atPeer(
  tree: EntityTree,
  localPeerId: string,
  namespace: string,
  hash: Uint8Array,
): Entity | undefined {
  return tree.get("/" + localPeerId + "/" + namespace + "/" + hashHexWithFormat(hash));
}

/** The §6.4.2 ingest-side binding. Paired with {@link atPeer}; one convention, two directions. */
export function bindAtPeer(
  tree: EntityTree,
  localPeerId: string,
  namespace: string,
  entity: Entity,
): string {
  const path = "/" + localPeerId + "/" + namespace + "/" + hashHexWithFormat(entity.contentHash);
  tree.put(path, entity);
  return path;
}

// ── Descriptor construction — §2.4 presence rule ────────────────────────────────

export interface DescriptorFields {
  readonly content: Uint8Array;
  readonly mediaType?: string;
  readonly typeRef?: Uint8Array;
  readonly name?: string;
}

/**
 * §2.4 — build a descriptor, enforcing the presence rule the type system cannot
 * express: **at least one of `media_type` or `type_ref` MUST be present.** Both MAY
 * be. Throws rather than emitting an invalid entity, because a descriptor with
 * neither is a content-addressed statement that says nothing and would be
 * indistinguishable from a corrupt one once bound.
 */
export function createDescriptor(fields: DescriptorFields): Entity {
  if (fields.mediaType === undefined && fields.typeRef === undefined) {
    throw new Error("CONTENT §2.4 presence rule: a descriptor MUST carry media_type or type_ref");
  }
  return Entity.create(
    ContentTypes.Descriptor,
    Ecf.map(
      ["content", Ecf.bytes(fields.content)],
      ["media_type", fields.mediaType === undefined ? null : Ecf.text(fields.mediaType)],
      ["type_ref", fields.typeRef === undefined ? null : Ecf.bytes(fields.typeRef)],
      ["name", fields.name === undefined ? null : Ecf.text(fields.name)],
    ),
  );
}

/** §5.3 — the dual-level descriptor path. `{publisher}/system/content/descriptor/{B_hex}/{D_hex}`. */
export function descriptorPath(publisherPeerId: string, blobHash: Uint8Array, descriptor: Entity): string {
  return (
    "/" +
    publisherPeerId +
    "/" +
    ContentTypes.Descriptor +
    "/" +
    hashHexWithFormat(blobHash) +
    "/" +
    hashHexWithFormat(descriptor.contentHash)
  );
}

/**
 * §5.3 integrity check (**MUST**): a consumer fetching a descriptor at
 * `.../{B_hex}/{D_hex}` MUST verify `descriptor.data.content == B`. Mismatch ⇒
 * reject. Two-level defence — the path embeds `B_hex`, the body carries `hash(B)`,
 * and both must agree.
 */
export function descriptorMatchesAnchor(descriptor: Entity, blobHash: Uint8Array): boolean {
  if (descriptor.type !== ContentTypes.Descriptor) return false;
  const carried = Ecf.optBytes(descriptor.data, "content");
  if (carried === null || carried.length !== blobHash.length) return false;
  return carried.every((b, i) => b === blobHash[i]);
}

// ── Reassembly — the §3.4 capability-checking wrapper ────────────────────────────

/**
 * The **only** public route to materialized blob bytes in this module, and the
 * "explicit capability-checking wrapper" §3.4 requires before reassembly may be
 * reachable from outside the handler body at all.
 *
 * **The check is weaker than this comment used to claim.** It said a `HandlerContext`
 * cannot be manufactured by a consumer. It can: the class is exported with a public
 * constructor, and this repo's own `test/handler.test.ts` builds one. What the wrapper
 * demands is a context naming this pattern and carrying SOME capability — both
 * caller-supplied — and it does not check that capability against the blob or the
 * namespace. Recorded in `EXTENSION.toml [substrate.capability_wrapper]` (corrected
 * 2026-09-12 by the cross-port review); not fixed here, because the fix is the same
 * design question on all three ports.
 *
 * The two assertions below are defence-in-depth against the one way that could be
 * false — a context from a DIFFERENT handler's dispatch being passed in, which
 * would carry a capability scoped to somebody else's pattern.
 */
export function reassembleUnderCapability(ctx: HandlerContext, blobHash: Uint8Array): ReassembleResult {
  if (ctx.pattern !== CONTENT_PATTERN) {
    throw new Error(
      `CONTENT §3.4: reassembly requires a ${CONTENT_PATTERN} handler context; got '${ctx.pattern}'`,
    );
  }
  if (ctx.callerCapability === null) {
    throw new Error("CONTENT §3.4: reassembly requires a cap-checked dispatch; context carries no caller capability");
  }
  return reassembleContent(ctx.peer.contentStore, blobHash);
}
