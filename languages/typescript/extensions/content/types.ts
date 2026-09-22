/**
 * CONTENT — the seven owned entity types (§2.1, §2.2, §2.4, §6.2, §6.3).
 *
 * Rendered through the PEER'S OWN `TypeDef` / `FSpec` builder rather than a
 * hand-written ECF map. That is a deliberate reuse decision, not laziness: the blob
 * and chunk entity hashes are the deduplication identity (§2.1), and §3.6.5 names
 * "two impls disagreeing on the entity hash for the same tuple" as a silent
 * dedup-breaking failure. Building the `system/type` payloads through the same
 * omit-empty encoder the peer publishes its own 53 core types with means our type
 * entities cannot drift from the peer's rendering convention in a way a review
 * would miss.
 *
 * WHY THE MODULE PUBLISHES THESE AT ALL. keystone's `registerHandler` writes the
 * §11.6.1 handler entity, interface entity, grant and signature — and no type
 * entities. Measured, not assumed: `gates/host-seam/probe-seam.mjs` reports
 * `type_blob / type_chunk / type_descriptor = NO` after registration. The oracle's
 * `content` category fails all three if nobody writes them. So the module writes
 * them, through `peer.tree.put`, which is public.
 */

import { Entity, FSpec, TypeDef, type EntityTree } from "entity-core-protocol-typescript";

const ref = FSpec.ref;
const arrayOf = FSpec.array;

/** Type-path constants. One home for every literal the module binds or emits. */
export const ContentTypes = {
  Blob: "system/content/blob",
  Chunk: "system/content/chunk",
  Descriptor: "system/content/descriptor",
  GetRequest: "system/content/get-request",
  ContentResponse: "system/content/content-response",
  IngestRequest: "system/content/ingest-request",
  IngestResult: "system/content/ingest-result",
} as const;

/** The handler pattern (§6.1). Everything the module binds derives from this. */
export const CONTENT_PATTERN = "system/content";

/**
 * §10.1 constants. Transcribed, with the v3.6 reconciliation applied: v3.5's 4 MiB
 * default is dead — §10.1, §11.2 and §2.1's convergence recommendation all say
 * 1 MiB as of v3.6, which is what `EXTENSION.toml [assumptions].chunk_size` records.
 */
export const DEFAULT_CHUNK_SIZE = 1_048_576;
export const MIN_CHUNK_SIZE = 65_536;
export const MAX_CHUNK_SIZE = 8_388_608;

/** §10.2 — the sender-side batching window, hashes per get request (§7.1). */
export const GET_BATCH_SIZE = 16;

/** §2.1 standardized `chunking` configuration identifiers. */
export const Chunking = {
  Fixed: 0,
  FastCdcNc2: 1,
} as const;

/**
 * The seven type definitions, in the order §11.1 ranks them: the two MUSTs first.
 *
 * Field order inside a definition does NOT affect the rendered bytes — the codec
 * re-sorts map keys length-then-lex — but it is kept in spec order so a reader can
 * diff this against §2.1 / §2.4 / §6.2 / §6.3 line by line.
 */
export function contentTypeDefs(): readonly TypeDef[] {
  return [
    // §2.1 — the chunk-list manifest. All four fields structural; no metadata, ever
    // (§2.3: an optional `content_type` here would split the dedup identity).
    new TypeDef(ContentTypes.Blob)
      .f("total_size", ref("primitive/uint"))
      .f("chunk_size", ref("primitive/uint"))
      .f("chunking", ref("primitive/uint"))
      .f("chunks", arrayOf(ref("system/hash"))),

    // §2.2 — one field, and the absence of the others is the point: no sequence
    // number, no parent ref, so identical bytes hash identically across blobs.
    new TypeDef(ContentTypes.Chunk).f("payload", ref("primitive/bytes")),

    // §2.4 — a consumption-format DECLARATION, not an attestation. `content` is the
    // only required field; §2.4's presence rule (at least one of media_type /
    // type_ref) is a validity constraint the type system cannot express, so it is
    // enforced in `sdk.ts` where the descriptor is built, not here.
    new TypeDef(ContentTypes.Descriptor)
      .f("content", ref("system/hash"))
      .f("media_type", ref("primitive/string").opt())
      .f("type_ref", ref("system/hash").opt())
      .f("name", ref("primitive/string").opt())
      .f("metadata", ref("primitive/any").opt()),

    // §6.2 request/response.
    new TypeDef(ContentTypes.GetRequest).f("hashes", arrayOf(ref("system/hash"))),

    // §6.2 + Amendment 2. `found` / `missing` are ARRAYS, not counters — the F4
    // cross-impl audit landing, and the one wire-shape mistake this response has
    // already made once (Go's v3.5 hybrid emitted counters). `pending` is the
    // OPTIONAL sync-state sidecar; we declare the field because the type is the
    // wire contract, and separately decline to emit it (see handler.ts).
    new TypeDef(ContentTypes.ContentResponse)
      .f("found", arrayOf(ref("system/hash")))
      .f("missing", arrayOf(ref("system/hash")))
      .f("pending", arrayOf(ref("system/hash")).opt()),

    // §6.3 — exactly one of envelope / entity. Both optional in the type; the
    // exclusivity is a handler-level 400, per the §6.3 algorithm.
    new TypeDef(ContentTypes.IngestRequest)
      .f("envelope", ref("system/envelope").opt())
      .f("entity", ref("core/entity").opt()),

    // §6.3 + §11.1 MUST: `root` is present in envelope mode and absent in entity
    // mode, which is exactly what `optional` encodes under the §1.3 absent-key rule.
    new TypeDef(ContentTypes.IngestResult)
      .f("root", ref("core/entity").opt())
      .f("root_hash", ref("system/hash"))
      .f("ingested_count", ref("primitive/uint")),
  ];
}

/**
 * Publish the type entities into the peer's tree at `system/type/{name}`.
 *
 * I1 (owned-namespace containment) is satisfied structurally: every path is
 * `system/type/` + a name from {@link ContentTypes}, and `system/type/*` is the
 * core's published type index, which every extension writes into by design
 * (`GUIDE-EXTENSION-DEVELOPMENT` §4.3 — a type name inside our owned prefix is
 * ours; the index it is filed under is shared). Nothing here writes outside
 * `system/content/` except that index entry.
 */
export function publishContentTypes(tree: EntityTree, localPeerId: string): readonly string[] {
  const written: string[] = [];
  for (const def of contentTypeDefs()) {
    const path = "/" + localPeerId + "/" + def.treePath;
    tree.put(path, def.toEntity());
    written.push(path);
  }
  return written;
}

/** A `system/protocol/error`-free way to build one of our own result entities. */
export function contentEntity(type: string, data: Parameters<typeof Entity.create>[1]): Entity {
  return Entity.create(type, data);
}
