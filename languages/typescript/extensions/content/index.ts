/**
 * `@entity-core/extension-content` — CONTENT v3.7 for the `typescript` peer.
 *
 * **The public entry point. What is not exported here is not reachable by a
 * consumer**, and one omission is a MUST rather than a taste: `reassembleContent`
 * lives at `internal/reassemble.ts` and is absent from this file on purpose (§3.4).
 * `test/export-surface.test.ts` asserts the omission, because a MUST with no check
 * is a sentence.
 *
 * Install model: **`sdk-native`** — in-process, against a live `Peer`. That is
 * forced, not chosen. The peer's `system/handler:register` wire op refuses
 * `system/*` patterns (core §6.2: "user-installed handlers MUST NOT register at
 * system/* paths") and CONTENT's pattern IS `system/content`. Every extension that
 * owns a system-namespace pattern inherits this constraint; it is measured on both
 * tier-A peers, not inferred.
 */

import { type Peer } from "entity-core-protocol-typescript";

import { ContentHandler, type ContentHandlerOptions } from "./handler.js";
import { CONTENT_PATTERN, publishContentTypes } from "./types.js";

export { ContentHandler, type ContentHandlerOptions } from "./handler.js";
export {
  ContentTypes,
  CONTENT_PATTERN,
  Chunking,
  DEFAULT_CHUNK_SIZE,
  MIN_CHUNK_SIZE,
  MAX_CHUNK_SIZE,
  GET_BATCH_SIZE,
  contentTypeDefs,
  contentTypeEntities,
  publishContentTypes,
} from "./types.js";
export {
  cdcBoundaries,
  cdcParams,
  createBlobCdc,
  createBlobFixed,
  gearTable,
  storeBlob,
  type Blob,
  type CdcParams,
} from "./chunking.js";
export {
  atPeer,
  bindAtPeer,
  createDescriptor,
  descriptorMatchesAnchor,
  descriptorPath,
  ensureClosure,
  hashHexWithFormat,
  reassembleUnderCapability,
  type ClosureVerdict,
  type DescriptorFields,
} from "./sdk.js";

/** What {@link installContent} actually wrote, so a caller can assert on it. */
export interface ContentInstallation {
  readonly pattern: string;
  readonly interfacePath: string;
  readonly typePaths: readonly string[];
}

/**
 * Install CONTENT onto a live peer.
 *
 * Two steps. It was three for one day, and losing the third is the interesting part:
 *
 *  1. `registerHandler` — writes the §11.6.1 handler entity, the interface entity, the
 *     self-issued grant and its signature, **and now the §3.7 operation specs**, because
 *     `Handler.operations` accepts the mapped form as of keystone 2026-09-06. The
 *     post-install `tree.put` that re-wrote the interface entity to say what the
 *     operations take and return is **deleted**, not commented out. Routed as K-2, closed
 *     upstream, workaround removed the same day it stopped being needed — a workaround
 *     that outlives its cause becomes the reason nobody notices the fix landed.
 *
 *  2. **Publish the type entities.** `registerHandler` still writes none, and that is
 *     arguably right: the types are the extension's, not the peer's. Measured, not
 *     assumed — `gates/host-seam/probe-seam.mjs` reports `type_blob / type_chunk /
 *     type_descriptor = NO` immediately after registration, and the oracle's `type_*`
 *     checks fail all three unless the module writes them. §11.1 makes blob and chunk
 *     MUSTs.
 */
export function installContent(peer: Peer, options: ContentHandlerOptions = {}): ContentInstallation {
  peer.registerHandler(new ContentHandler(options));

  const interfacePath = "/" + peer.localPeerId + "/system/handler/" + CONTENT_PATTERN;
  const typePaths = publishContentTypes(peer.tree, peer.localPeerId);

  return { pattern: CONTENT_PATTERN, interfacePath, typePaths };
}
