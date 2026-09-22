/**
 * `@entity-core/extension-content` — CONTENT v3.6 for the `typescript` peer.
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

import { Ecf, Entity, TypeNames, type Peer } from "entity-core-protocol-typescript";

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
 * Three steps, and the second and third exist because `registerHandler` does not
 * do them. Both were **measured** on the peer's build artifact
 * (`gates/host-seam/probe-seam.mjs`), not read off the source:
 *
 *  1. `registerHandler` — writes the §11.6.1 handler entity, the interface entity,
 *     the self-issued grant and its signature. This is the peer's job and it does it.
 *
 *  2. **Re-write the interface entity with the §6.1 operation specs.** keystone's
 *     `Handler` interface carries operation NAMES only (`readonly operations:
 *     readonly string[]`), so `registerHandler` renders `{get: {}, ingest: {}}` —
 *     an operations map with no `input_type` / `output_type`. CONTENT §6.1 declares
 *     both for both ops. The oracle checks key presence only, so this step changes
 *     no conformance number today and is done anyway: the manifest is the peer's
 *     published contract, and publishing a contract with the types missing because
 *     the registration API could not express them is a defect that happens to be
 *     ungated. **Routed to keystone as one line.**
 *
 *  3. **Publish the type entities.** `registerHandler` writes none; the probe
 *     reports `type_blob / type_chunk / type_descriptor = NO` immediately after
 *     registration. The oracle's `type_*` checks fail all three unless the module
 *     writes them. §11.1 makes blob and chunk MUSTs.
 */
export function installContent(peer: Peer, options: ContentHandlerOptions = {}): ContentInstallation {
  peer.registerHandler(new ContentHandler(options));

  const interfacePath = "/" + peer.localPeerId + "/system/handler/" + CONTENT_PATTERN;
  peer.tree.put(interfacePath, contentInterfaceEntity());

  const typePaths = publishContentTypes(peer.tree, peer.localPeerId);

  return { pattern: CONTENT_PATTERN, interfacePath, typePaths };
}

/**
 * The §6.1 manifest, complete. `pattern` is published peer-relative, matching what
 * `registerHandler` writes and what a remote resolves.
 *
 * §6.1's manifest block writes `pattern: "system/content/*"`, with the prose
 * immediately below it saying "Manifest at pattern path `system/content`. Index
 * entry at `system/handler/system/content`." The `/*` is the CAPABILITY-scope
 * spelling used in §6.4's grant examples (`handlers: {include:
 * ["system/content/*"]}`), not the binding path — binding at a literal `.../*` would
 * put a `*` segment in the tree. We publish `system/content`, which is what the
 * prose, the index path and the oracle all agree on.
 */
function contentInterfaceEntity(): Entity {
  const opSpec = (inputType: string, outputType: string) =>
    Ecf.map(["input_type", Ecf.text(inputType)], ["output_type", Ecf.text(outputType)]);

  return Entity.create(
    TypeNames.HandlerInterface,
    Ecf.map(
      ["pattern", Ecf.text(CONTENT_PATTERN)],
      ["name", Ecf.text("content")],
      [
        "operations",
        Ecf.map(
          ["get", opSpec("system/content/get-request", "system/content/content-response")],
          ["ingest", opSpec("system/content/ingest-request", "system/content/ingest-result")],
        ),
      ],
    ),
  );
}
