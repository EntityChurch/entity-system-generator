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
  Permissions,
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
 * The **only** public route to materialized blob bytes in this module, and §3.4's
 * *"explicit capability-checking wrapper"* — **clause 2, on this port, since 2026-09-16.**
 *
 * §3.4: *"Implementations MUST NOT expose `reassemble_content` as a public substrate
 * primitive callable from third-party / SDK / external consumer code without an explicit
 * capability-checking wrapper — direct substrate access bypasses the dispatcher cap
 * discipline and creates a capability-escalation surface for consumers holding non-root
 * caps."* That sentence has two halves and this port now satisfies one of them.
 *
 * **CLAUSE 2 — the capability IS checked, against a target the caller must name.** §3.4
 * routes materialization through `system/content:get` (namespace-cap-scoped) or
 * `local/files:read` (tree-path-cap-scoped); both are scoped to a PATH, so the wrapper
 * cannot check anything without one, and the old signature had nowhere to put it.
 * `target` is that path, and the check is the peer's own §6.3 predicate
 * (`Permissions.checkPathPermission`, keystone `typescript/src/capability/permissions.ts:180`
 * @ `a8423d2b`) — the same call the handler's §6.4 step 2 makes (`handler.ts`), so the two
 * cannot drift into two readings of one clause. Before this, the wrapper asked only for a
 * context naming this pattern and carrying SOME capability, both caller-supplied, and never
 * compared that capability to anything.
 *
 * **CLAUSE 1 IS NOT SATISFIED HERE AND THIS COMMENT DOES NOT CLAIM IT IS.** `HandlerContext`
 * is exported with a public constructor and this repo's own `test/handler.test.ts` builds
 * one, so holding a context is not the statement *the dispatcher authorized you* that it is
 * on `rust` (where the fields are `pub(crate)` and `Peer::route` is the only construction
 * site). Routed to keystone as `K-24`; recorded in `EXTENSION.toml
 * [substrate.capability_wrapper]` with `typescript_blocked_on = "clause 1 only"`.
 *
 * **What that residue costs, stated rather than implied:** a consumer who builds a context
 * can put any capability in it, so this check binds an HONEST caller to its grant and does
 * not bind a forging one. That is a real difference from `rust` and it is clause 1's, not
 * this function's — but the check is still worth having, because the escalation surface
 * §3.4 names is *a consumer holding a non-root cap*, and one of those now cannot read
 * outside its grant by going through the SDK instead of the wire.
 *
 * Refuses by throwing, which is this port's existing convention here and for
 * `createDescriptor`; `rust` returns `Err(("capability_denied", _))` because a panicking
 * library constructor is a different contract there. A procedure difference (D17), recorded
 * where the two ports' shapes are compared.
 */
export function reassembleUnderCapability(
  ctx: HandlerContext,
  target: string,
  blobHash: Uint8Array,
): ReassembleResult {
  // The context is caller-constructible here, but it is still not necessarily OURS: a body
  // installed at another pattern holds one too, and §3.4's grant discipline is per handler.
  // On the dispatch path the pattern is set from the resolved handler, never by the caller.
  if (ctx.pattern !== CONTENT_PATTERN) {
    throw new Error(
      `CONTENT §3.4: reassembly requires a ${CONTENT_PATTERN} handler context; got '${ctx.pattern}'`,
    );
  }
  // FAIL CLOSED on an absent capability. On the dispatch path a request with no caller
  // capability is refused `403 capability_denied` before a context exists, so here `null`
  // is not "a call without a token" — it is a state the peer says cannot exist, and turning
  // an impossible state into an unchecked one is how the escalation surface gets built.
  const capability = ctx.callerCapability;
  if (capability === null) {
    throw new Error("CONTENT §3.4: reassembly requires a cap-checked dispatch; context carries no caller capability");
  }
  if (
    !Permissions.checkPathPermission(
      ctx.operation,
      target,
      capability,
      CONTENT_PATTERN,
      ctx.peer.localPeerId,
    )
  ) {
    throw new Error(
      `CONTENT §3.4: capability does not cover ${ctx.operation} on '${target}' (§6.3 path scope)`,
    );
  }
  return reassembleContent(ctx.peer.contentStore, blobHash);
}
