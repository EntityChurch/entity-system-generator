/**
 * §3.4 `reassemble_content` — **MODULE-PRIVATE. NOT re-exported from `index.ts`.**
 *
 * This file exists at `internal/` and is absent from the package's public entry
 * point on purpose, and the purpose is a MUST:
 *
 *   "Implementations MUST NOT expose `reassemble_content` as a public substrate
 *    primitive callable from third-party / SDK / external consumer code without an
 *    explicit capability-checking wrapper — direct substrate access bypasses the
 *    dispatcher cap discipline and creates a capability-escalation surface for
 *    consumers holding non-root caps."   — EXTENSION-CONTENT §3.4
 *
 * §3.4 permits re-implementing the algorithm "for cases that operate inside the
 * trusted handler-context boundary", which is exactly and only where this is
 * called from: `sdk.ts`'s `reassembleUnderCapability`.
 *
 * **This paragraph used to end "which takes a `HandlerContext` it cannot
 * manufacture — a check the caller cannot have skipped", and that was false on this
 * port.** `HandlerContext` is exported with a public constructor and this package's
 * own `test/handler.test.ts` builds one. The claim was `rust`'s, written here. What
 * the wrapper actually enforces since 2026-09-16 is §3.4's clause 2 — the caller's
 * capability is checked against a `target` path with the peer's own
 * `checkPathPermission` — and clause 1, the unforgeable anchor, is a keystone surface
 * question routed as `K-24`. A prose claim is an undeclared assertion and it is the
 * one claim in a file that nothing executes (AP-47); this one is now the weaker,
 * true version.
 *
 * The enforcement point is not this comment. It is
 * `test/export-surface.test.ts`, which imports the package's public entry and
 * asserts no export reassembles, and exercises the wrapper's refusals in both
 * directions. A MUST with no check is a sentence.
 */

import { Ecf, type ContentStore, type Entity } from "entity-core-protocol-typescript";

import { ContentTypes } from "../types.js";

export type ReassembleError =
  | { readonly ok: false; readonly code: "blob_not_found"; readonly hash: Uint8Array }
  | { readonly ok: false; readonly code: "blob_pending_sync"; readonly hash: Uint8Array }
  | { readonly ok: false; readonly code: "not_a_blob"; readonly hash: Uint8Array };

export type ReassembleResult = { readonly ok: true; readonly bytes: Uint8Array } | ReassembleError;

/**
 * §3.4, transcribed. Returns bytes or a coded failure; never throws on a missing
 * chunk, because "missing chunk" is a normal incremental-sync state and not an
 * error condition of the algorithm.
 *
 * **`blob_pending_sync` vs `not_found` is NOT decided here.** §3.4's predicate is
 * sync-state visibility — a peer returns 503 IFF it has an active subscription on
 * the namespace AND an inbox feeding the content store. This composition has
 * neither (no SUBSCRIPTION, no INBOX installed), so the caller maps this code to a
 * terminal 404. The code is still `blob_pending_sync` at this layer so the mapping
 * lives at the one place that knows the deployment's sync posture.
 */
export function reassembleContent(store: ContentStore, blobHash: Uint8Array): ReassembleResult {
  const blob = store.get(blobHash);
  if (blob === undefined) {
    return { ok: false, code: "blob_not_found", hash: blobHash };
  }
  if (blob.type !== ContentTypes.Blob) {
    return { ok: false, code: "not_a_blob", hash: blobHash };
  }

  const chunkHashes = Ecf.asArray(Ecf.require(blob.data, "chunks")).map((h) => Ecf.asBytes(h));
  const parts: Uint8Array[] = [];
  let total = 0;
  for (const chunkHash of chunkHashes) {
    const chunk: Entity | undefined = store.get(chunkHash);
    if (chunk === undefined) {
      return { ok: false, code: "blob_pending_sync", hash: chunkHash };
    }
    const payload = Ecf.asBytes(Ecf.require(chunk.data, "payload"));
    parts.push(payload);
    total += payload.length;
  }

  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return { ok: true, bytes: out };
}
