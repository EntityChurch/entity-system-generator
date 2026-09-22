# Content Extension — Normative Specification

**Version**: 3.6
**Latest change:** §10 constants reconciled with the amendment prose they had drifted from — `DEFAULT_CHUNK_SIZE` is **1 MiB** (§3.5, A2) at every site, and `GET_BATCH_SIZE` is **16** (§7.1, A4). A2 and A4 landed in prose and in the §3.6.2 parameter table and never reached §10.1, §10.2, §11.2 or §2.1's convergence recommendation, so the document stated two defaults for the value §2.1 makes the deduplication identity. Also: §10.3 gains the `ingest` row it omitted, and §6.1's `get` gains its `output_type`. Behaviour is unchanged for the value that matters — `entity-core-{go,rust,py}` already emit 1 MiB. Prior: Amendment 4 naming normalization — the frame-limit check label / type-path renamed snake → kebab, now `system/content/frame-limit-respected`, per `STYLE-NAMING-CONVENTIONS.md`; Go renames the check label in lockstep, Rust/Py doc-comment-only for this one. (Version lineage: v3.6 + Amendments 1–3, then v3.6, v3.5, v3.4, v3.3 baselines — see the changelog table for per-version detail.)
**Status**: Active
**Conformance grade:** Draft (per `GUIDE-EXTENSION-DEVELOPMENT.md` §9). No cross-impl validation pass yet. Reference impls pending.

**Depends**: ENTITY-CORE-PROTOCOL.md (v7.51+); ENTITY-CBOR-ENCODING.md (v1.4+) — per-dependency detail below.

- `ENTITY-CORE-PROTOCOL.md` (v7.51+) — request-side and result-side envelope-`included` preservation across dispatch boundaries (v7.49 result-side equivalence, v7.51 request-side preservation) underpins the v3.4 ingest-result pass-through and the §4 handler-mediated `included` map.
- `ENTITY-CBOR-ENCODING.md` (v1.4+) — canonical ECF for entity-hash stability of blob and chunk entities.

**Used by (informative):**
- `EXTENSION-REVISION` — chain composition through `system/content:ingest` (e.g., `revision/fetch → content:ingest → revision/merge`).
- `EXTENSION-SUBSCRIPTION` — content-referencing entity notifications carry blob refs; content transfer is a separate operation (§8.1).
- `EXTENSION-INBOX` — large payload delivery via content reference rather than inline params (§8.2).
- Any domain handler that owns binary content (`local/files`, media handlers, dataset handlers) — via the §4 handler-mediated access pattern.

**Owned namespaces (per GUIDE-EXTENSION-DEVELOPMENT §4.3 — closed):**
- `system/content/` — handler URI + entity-type prefix for `blob`, `chunk`, and ingest/get request/result types.
- The optional system content handler binds at `system/content/` and `system/content/{namespace}/` (§6.4).

**Owned handler ops:**
- `system/content:get` — hash-addressed retrieval (§6.2).
- `system/content:ingest` — hash-addressed content-store write (§6.3).

**Owned entity types:**
- `system/content/blob` (§2.1) — the chunk-list manifest.
- `system/content/chunk` (§2.2) — a chunk payload.
- `system/content/descriptor` (§2.4) — consumption-format declaration for hash-addressable content (v3.5).
- `system/content/get-request` / `system/content/content-response` (§6.2) — system content handler operation types.
- `system/content/ingest-request` / `system/content/ingest-result` (§6.3) — ingest operation types.

**Extension points exposed:** None.
**Extension points consumed:** None.

---

> **Path notation.** Paths in this document use peer-relative notation (without leading `/{peer_id}/`). All peer-relative paths resolve to the local peer's namespace: `system/tree` means `/{local_peer_id}/system/tree`. Every path in the entity tree is absolute at rest — rooted at a peer identity. See ENTITY-CORE-PROTOCOL.md §1.4 for the path model. Cross-peer examples use absolute paths with explicit peer identities.

## 1. Overview

The content extension defines a universal pattern for storing and transferring binary content within the entity system. It provides:

1. **Content types**: `system/content/blob` and `system/content/chunk` — entity types for representing binary content as chunked, content-addressed data. Always installed.
2. **Algorithm specifications**: Chunking, verification, and reassembly — defining correct behavior for implementations that handle binary content.
3. **Handler guidance**: Patterns for serving chunked content through domain handlers, including the `get-request` operation pattern.
4. **System content handler** (optional): `system/content/*` — capability-gated, hash-addressed access to the content store. Type-agnostic — serves any entity by hash, not just blobs and chunks.

### 1.1 Extension Structure

The content extension installs system types that any handler can use. The types (§2) and algorithms (§3) define the interoperability contract — two implementations that follow the same algorithm specifications with the same chunk size produce the same entity hashes and can exchange content.

The extension does NOT provide a shared code library. Each implementation writes its own chunking, verification, and serving code in its own language. The algorithm specifications (§3) define what correct behavior is. The handler integration guidance (§4) describes recommended patterns. Implementations follow these specifications to be interoperable.

```
Content Extension
├── Types (always installed)         → system/content/blob, system/content/chunk
├── Algorithm specs (§3)             → chunking, verification, reassembly
├── Handler guidance (§4)            → get-request pattern, hash validation
└── System content handler (§6)      → optional, general-purpose content access
```

Handlers that deal with binary content implement the chunking and serving logic directly — the algorithm is straightforward and the dispatch overhead of delegating to a service handler would exceed the cost of the work itself. For computationally expensive operations (image processing, transcoding), service handler dispatch makes sense. For chunking, direct implementation is the practical choice.

**Key properties of this architecture:**

- **Deduplication across handlers**. The content store is shared. Identical chunks produce identical entity hashes regardless of which handler created them. A local files handler and a media handler storing the same bytes share chunks automatically.
- **Capability scoping stays with the handler**. A grant on `local/files/*` is sufficient to access file content. No separate content namespace permissions are needed.
- **Clients interact with the handler, not content internals**. A client asks a handler for a file; the handler serves it. The chunking mechanism is transparent to clients that don't need to understand it.
- **The system content handler is independent**. It provides capability-gated, hash-addressed access to the content store — useful for entity sync, public content sharing, or any hash-based entity retrieval. It serves any entity type, not just blobs and chunks. It is not a dependency for handler-mediated content access.

### 1.2 The Content Pattern

Any entity type that carries binary content references it through a `system/content/blob` entity rather than inlining the bytes. The blob describes the content (size, chunk list) and references chunk entities containing the actual bytes. This indirection provides:

- **Deduplication**: Identical content produces identical chunks and identical blob entities regardless of the referencing entity type or handler. The content store is shared — any handler can participate in deduplication by using these types.
- **Entity-native verification**: Each chunk is verified by its entity hash on receipt. The blob's entity hash covers the ordered chunk list. No separate content hash is needed.
- **Resumable transfer**: A receiver tracks which chunks it has and only fetches missing ones. Transfer can be interrupted and resumed at any point.
- **Content networking**: The blob manifest is a content-addressed chunk list — analogous to a torrent file. Any peer with the chunks can serve them. Standard types enable multi-peer content distribution.

For public / hash-addressable content where no domain-specific referencing entity is the natural fit, the standard mechanism for declaring consumption formats over a blob is the `system/content/descriptor` (§2.4 + §5.3). Handler-mediated content continues to use the handler's typed entity as the referencing entity.

### 1.3 Uniform Chunking

All content uses the blob+chunk pattern, regardless of size. Content smaller than the chunk size produces a blob with a single chunk. This uniformity means:

- One code path for all content handling
- Consistent references (always ref a blob, never inline raw bytes)
- No special-case logic for small vs. large content

This extension specifies two chunking algorithms: fixed-size (§3.2) and content-defined (§3.6). **Content-defined chunking (FastCDC) is RECOMMENDED** — it produces edit-stable boundaries, so modifying content in one region does not invalidate chunks in other regions. Fixed-size chunking is simpler but produces different chunks after any insertion or deletion.

**Convergence is load-bearing (v3.6).** Cross-peer deduplication is the primary value the content extension provides; convergent chunking is the mechanism. Implementations that diverge from the canonical FastCDC parameters (gear table, target/min/max size, mask derivation per §3.6.2) lose cross-peer dedup for the divergent content. Interoperability is preserved (receivers reassemble any conformant blob), but the storage-savings and bandwidth-savings properties degrade. Deployments operating outside the canonical chunking are effectively running their own content-store topology layered on top of the entity-core content system; this is permitted but explicitly named.

---

## 2. Type Definitions

### 2.1 Content Blob

The blob entity describes a piece of binary content. It serves as the manifest — listing the chunk hashes that comprise the content.

```
system/content/blob := {
  fields: {
    total_size:  {type_ref: "primitive/uint"}                ; Total content size in bytes
    chunk_size:  {type_ref: "primitive/uint"}                ; Nominal chunk size in bytes
    chunking:    {type_ref: "primitive/uint"}                ; Chunking algorithm identifier
    chunks:      {array_of: {type_ref: "system/hash"}}       ; Ordered entity hashes of chunks
  }
}
```

- `total_size`: Byte count of the raw content.
- `chunk_size`: The nominal chunk size in bytes. For fixed-size chunking, this is the exact size of all non-final chunks. For FastCDC, this is the target size from which all parameters are derived (§3.6.2).
- `chunking`: Identifies the exact chunking configuration used to create this blob. Each value specifies a complete, deterministic configuration — algorithm, parameters, and any lookup tables.

  **Value ranges:**

  | Range | Purpose |
  |-------|---------|
  | 0–255 | Reserved — standardized configurations defined by the entity protocol |
  | 256+ | Custom — implementation-defined configurations for private or experimental use |

  **Standardized values:**

  | Value | Configuration | Specification |
  |-------|---------------|---------------|
  | 0 | Fixed-size | §3.2. Chunks at every `chunk_size` bytes. |
  | 1 | FastCDC/NC2 | §3.6. Gear table from §3.6.1, NC=2, min=`chunk_size/4`, max=`chunk_size*2`. |
  | 2–255 | Reserved | For future standardized configurations. |

  The value identifies the complete configuration, not just the algorithm family. A FastCDC implementation using a different gear table or different normalization level is a different configuration — it produces different chunk boundaries and different blob hashes. Such configurations **SHOULD** use a custom value (256+) rather than reusing a standardized value.

  **Deduplication identity**: The pair (`chunking`, `chunk_size`) fully determines all chunking parameters. For FastCDC/NC2, `chunk_size` derives min, max, masks, and scan phases. Changing either value produces different chunk boundaries — and therefore different chunk hashes, a different blob hash, and no deduplication with blobs using different settings.

  | `chunking` | `chunk_size` | Deduplicates? |
  |------------|-------------|---------------|
  | 1 (FastCDC/NC2) | 1 MiB | Yes — same chunks |
  | 1 (FastCDC/NC2) | 4 MiB | No — different boundaries, different chunks |
  | 0 (Fixed-size) | 1 MiB | No — different algorithm, different chunks |

  Convergence on both values (recommended: `chunking: 1`, `chunk_size: 1 MiB` — the §3.5 default, §10.1 `DEFAULT_CHUNK_SIZE`) maximizes cross-peer deduplication. Peers using custom configurations accept that their chunks will not deduplicate with peers using standardized settings.

- `chunks`: Ordered list of entity hashes (`system/hash`) identifying the chunk entities. The order determines reassembly order. This field is in `data`, so it is covered by the blob's own entity hash.

All four fields are structural and deterministic for given content and chunking parameters. The blob carries no semantic metadata — content type, filename, purpose, etc. belong on the referencing entity (§5.1). Same content + same `chunking` + same `chunk_size` → same blob entity hash, regardless of which handler or peer created it.

The blob entity's hash is `ecfv1-sha256(ecf_encode({type: "system/content/blob", data: {...}}))`. Two blobs with identical content, chunking algorithm, and chunk size produce the same entity hash — content deduplication uses the entity system's native content addressing, not a separate hash.

**No separate content hash**: The blob does not carry an independent hash of the raw content bytes. Each chunk entity is verified by its entity hash on receipt (ENTITY-CORE-PROTOCOL.md §1.8). The blob's entity hash covers the ordered chunk list. If every chunk entity hash validates and the blob entity hash validates, the reassembled content is correct by construction. A separate raw-bytes hash would be a second content-addressing system layered on the entity system's native one — redundant, and a source of architectural complexity (see §2.3).

**No content-level compression**: Chunk payloads are always raw bytes. Compression is handled at other layers — wire compression (ENTITY-CORE-PROTOCOL.md §4.5) for bandwidth, storage-layer compression for disk. This ensures chunk entity hashes are stable across peers regardless of compression preferences, preserving cross-peer deduplication and chunk-level interoperability. See §2.3.

### 2.2 Content Chunk

A chunk entity contains a portion of the content payload. Chunks carry no sequence information — ordering is determined by the chunk's position in the blob's `chunks` list.

```
system/content/chunk := {
  fields: {
    payload: {type_ref: "primitive/bytes"}   ; Chunk data
  }
}
```

- `payload`: Raw binary bytes. In the CBOR wire encoding (ECF), this is native binary data (major type 2) — no encoding overhead. Always uncompressed.

The chunk entity has no sequence number, no parent reference, and no metadata. This is deliberate: two chunks with identical payload bytes produce the same entity hash, enabling deduplication across blobs and across peers. If the same 1 MiB block appears at different offsets in different files, or on different peers, it is stored once and identified by the same hash.

### 2.3 Design Rationale

Three decisions about what the content extension does NOT do, and why.

**No separate content hash**: The blob does not carry an independent hash of the raw content bytes (e.g., `sha256:` of the concatenated payloads). The entity system is already a content-addressing system — every entity is identified by its entity hash (`ecfv1-sha256:`). Each chunk is verified by its entity hash. The blob's entity hash covers the ordered chunk list. A separate raw-bytes hash would be a second content-addressing mechanism layered on the first, adding:

- A new hash format (`sha256:` vs `ecfv1-sha256:`) with its own algorithm negotiation
- O(content_size) additional computation on both creation and verification
- A `resolve` operation to map between the two hash systems
- Conceptual complexity that invites errors (thinking in terms of "raw bytes" instead of entities)

The entity system's native hashing provides content identity: same content + same chunking algorithm + same chunk_size → same chunk payloads → same chunk entity hashes → same blob data → same blob entity hash. Deduplication works through the same mechanism as every other entity. If an application needs a raw-bytes hash for external interop (e.g., verifying against a published SHA-256 checksum), it can compute one — but it is not part of the manifest.

**No metadata on the blob**: The blob carries no semantic metadata — no content type, no filename, no description. All metadata belongs on the referencing entity (§5.1). This is critical for deduplication: if the blob had an optional `content_type` field, two applications storing the same content with different MIME types (or one setting it, one omitting it) would produce different blob entity hashes. The same bytes would be stored twice. The blob is purely structural — it says how to reassemble the content, not what the content means.

Entity types that reference blobs carry their own metadata. A file entity has a filename and MIME type. An image entity has dimensions and format. A dataset entity has schema information. The blob doesn't need to duplicate any of this. Bridge protocols (HTTP, etc.) derive Content-Type from the referencing entity, not the blob.

Semantic interpretation over a blob travels through the `system/content/descriptor` layer (§2.4 + §5.3) without placing metadata on the blob, preserving the no-metadata invariant. Any peer may publish one or more descriptors per blob; consumer policy decides which to honor (§5.3 trust model). This pattern serves the public / hash-addressable case where no domain-specific referencing entity carries the semantic anchor.

**No content-level compression**: Chunk payloads are always raw bytes. If chunks stored compressed data, the chunk entity hash would cover the compressed bytes. Two peers storing the same content with different compression algorithms would produce different chunk entity hashes. A receiver with one peer's blob manifest could not get chunks from the other peer — the hashes wouldn't match. This breaks the content-addressing property that enables cross-peer deduplication.

**Compression layers**: The entity system provides compression at two other layers:

| Layer | Scope | Lifecycle | Declaration |
|-------|-------|-----------|-------------|
| **Wire compression** | Per-frame | Ephemeral (decompress on receipt) | Hello negotiation (ENTITY-CORE-PROTOCOL.md §4.5) |
| **Storage compression** | Per-entity in content store | Implementation-internal | Implementation-defined |

Wire compression handles bandwidth — all frames (including chunk transfers) benefit from negotiated compression. Storage compression handles disk — the content store can compress entities internally (like git's zlib compression of objects). Neither affects entity hashes, so chunk-level interoperability is preserved.

This follows the git model: hash the canonical raw form, compress below the content-addressing layer.

### 2.4 Content Descriptor

A descriptor is a **consumption-format declaration**: a statement that says "this blob can be consumed as *X*." It is not an authoritative claim about what the blob *is*; it is one publisher's assertion about one way to read it. The same blob typically has multiple valid consumption formats (a PDF blob may be consumed as `application/pdf`, as `text/plain` for its extracted text, or as `image/png` for a first-page render), and the descriptor pattern supports that natively.

The descriptor sits **over** the blob — semantic interpretation flows through the descriptor layer without placing metadata on the blob itself, preserving the no-metadata invariant (§2.3). Multiple publishers may publish multiple descriptors per blob; consumer policy decides which to honor (§5.3 trust model).

```
system/content/descriptor := {
  fields: {
    content:     {type_ref: "system/hash"}
                 ; REQUIRED. The blob being interpreted.

    media_type:  {type_ref: "primitive/string", optional: true}
                 ; IANA media type for opaque content
                 ; (e.g., "image/png", "application/pdf", "audio/flac").

    type_ref:    {type_ref: "system/hash", optional: true}
                 ; Reference to a `system/type` for structured content.
                 ; Composes with EXTENSION-TYPE when installed; ignored when absent.

    name:        {type_ref: "primitive/string", optional: true}
                 ; Suggested presentation handle; not authoritative.

    metadata:    {type_ref: "primitive/any", optional: true}
                 ; Publisher-defined extension surface.
  }
}
```

**Presence rule.** At least one of `media_type` or `type_ref` MUST be present. Both MAY be present (e.g., `media_type: "application/json"` plus a `type_ref` to the schema the JSON should match).

**Hashing.** The descriptor itself is content-addressed like any other entity; two descriptors are equal iff their bodies are byte-equivalent under ECF.

**What the descriptor does NOT do:**

- Does not put metadata onto the blob. The dedup invariants on `system/content/blob` are unchanged (§2.3 design rationale stands).
- Does not replace handler-specific referencing entities. A `local/files/file` continues to carry filesystem-specific metadata and reference its blob directly; descriptors are for cases where no domain-specific referencing entity is the natural fit (primarily public/hash-addressable content).
- Does not introduce a new content-addressing system or a parallel hash format.
- Does not require EXTENSION-TYPE to install. When TYPE is present, `descriptor.type_ref` composes with it. When TYPE is absent, `media_type` carries the interpretation hint alone.
- Does not claim authority. Descriptors are declarations, not attestations. A peer wanting to *attest* a descriptor as authoritative layers a `system/attestation` over the descriptor entity using existing mechanisms (§6.5 deployment guidance).

The descriptor's discovery convention — the invariant-pointer path at which descriptors are bound — is specified in §5.3.

---

## 3. Algorithm Specifications

This section defines the algorithms for creating, verifying, and reassembling chunked content. Implementations that handle binary content follow these specifications to produce interoperable content entities.

### 3.1 Content Storage

Content entities (blobs and chunks) are stored in the **content store** (hash→entity), not the entity tree (URI→hash). This is a deliberate separation:

- **Entity tree**: Path-addressed, hierarchical, listable, mutable. For structured entities that have natural paths and benefit from tree traversal.
- **Content store**: Hash-addressed, flat, not listable through the protocol, immutable. For content entities identified by hash.

Content entities don't have natural paths. A chunk has no meaningful location — it's identified by the hash of its payload. Storing content in the entity tree would create a flat namespace with potentially hundreds of thousands of entries, breaking tree listing at scale (a 1 TiB file produces ~262K chunk entries).

The content store is shared across all handlers. A chunk stored by the local files handler is the same entity (same hash) as an identical chunk stored by the media handler. Deduplication is automatic.

### 3.2 Fixed-Size Chunking

```
create_blob(raw_bytes, chunk_size):
  total_size = length(raw_bytes)

  ; Split into chunks
  chunks = []
  offset = 0
  while offset < total_size:
    end = min(offset + chunk_size, total_size)
    chunk_bytes = raw_bytes[offset:end]

    ; Create chunk entity and store
    chunk_entity = {
      type: "system/content/chunk"
      data: {payload: chunk_bytes}
    }
    chunk_hash = ecf_hash(chunk_entity)
    content_store.put(chunk_hash, chunk_entity)
    chunks.append(chunk_hash)
    offset = end

  ; Create blob entity
  blob_entity = {
    type: "system/content/blob"
    data: {
      total_size: total_size
      chunk_size: chunk_size
      chunking:   0               ; fixed-size
      chunks:     chunks
    }
  }
  blob_hash = ecf_hash(blob_entity)
  content_store.put(blob_hash, blob_entity)

  return blob_hash
```

### 3.3 Content Verification

```
verify_content(blob):
  ; Each chunk was already verified on receipt (entity fidelity)
  ; The blob's entity hash covers the chunks list (§2.1)
  ; Verification here confirms completeness and total size consistency

  total = 0
  for chunk_hash in blob.data.chunks:
    chunk = content_store.get(chunk_hash)
    if chunk is null:
      return error("missing_chunk", chunk_hash)

    payload_size = length(chunk.data.payload)
    if payload_size == 0:
      return error("empty_chunk", chunk_hash)

    total = total + payload_size

  ; Verify total size
  if total != blob.data.total_size:
    return error("size_mismatch")

  return ok
```

Verification is entity-native — the same mechanism used for every other entity:

1. **Chunk entity hash** — verified on receipt per entity fidelity (ENTITY-CORE-PROTOCOL.md §1.8). Confirms each chunk was not tampered with in transit.
2. **Blob entity hash** — verified on receipt. Covers the ordered chunk list, chunk_size, and total_size. If the blob hash validates, the chunk list is authoritative.
3. **Completeness** — all chunks present, non-empty, and total size matches the blob's declaration.

There is no separate content hash. If every chunk entity hash is valid and the blob entity hash is valid, the reassembled content is correct by construction. Per-chunk size validation against `chunk_size` is not performed — the entity hash already guarantees chunk integrity, and content-defined chunking (§3.6) produces variable-size chunks.

### 3.4 Content Reassembly

```
reassemble_content(blob_hash):
  blob = content_store.get(blob_hash)
  if blob is null:
    return error("blob_not_found")

  raw_bytes = []
  for chunk_hash in blob.data.chunks:
    chunk = content_store.get(chunk_hash)
    if chunk is null:
      return error("blob_pending_sync", chunk_hash)
    raw_bytes.append(chunk.data.payload)

  return concatenate(raw_bytes)
```

**This pseudocode is a published algorithm reference, NOT a substrate primitive.** Like the FastCDC algorithm in §3.6, `reassemble_content` defines the canonical computation; it is not a callable public API on the content store. Capability-checked access to materialized blob bytes is provided by handler-mediated operations:

- **`system/content:get`** (§6.2) — namespace-cap-scoped access (broad); caller's cap covers a namespace path.
- **`local/files:read`** (or equivalent domain-handler ops) — tree-path-cap-scoped access (narrow); caller's cap covers the file's tree path.

Consumers needing to materialize blob bytes route through one of these capability-checked surfaces. Implementations MAY re-implement the algorithm in their own code for cases that operate inside the trusted handler-context boundary (the handler holds the ContentStore reference, operates under its `internal_scope` grant, and the cap discipline is enforced at the dispatch boundary upstream — ENTITY-CORE-PROTOCOL.md §6.8 handler-authorized reads/writes). Implementations MUST NOT expose `reassemble_content` as a public substrate primitive callable from third-party / SDK / external consumer code without an explicit capability-checking wrapper — direct substrate access bypasses the dispatcher cap discipline and creates a capability-escalation surface for consumers holding non-root caps.

**Partial-sync condition.** When a referenced chunk (or the blob entity itself) has not yet arrived in the local content store — a normal occurrence during incremental cross-peer sync — the algorithm surfaces **`503 blob_pending_sync`**. Semantic: *retry on next sync event*; consumers receiving this code MUST treat the operation as eligible for retry without operator intervention.

**`503` vs `404` predicate (sync-state visibility).** The choice between `503 blob_pending_sync` (transient — will arrive) and `404 not_found` (terminal — will not arrive) depends on the peer's **sync-state visibility**: implementations return `503` IFF the peer has an active subscription on the blob's namespace AND an inbox / delivery path feeding the content store (i.e., the missing chunks are expected to arrive via the normal sync mechanism). Peers without sync-state visibility — e.g., a standalone peer with no upstream sync, or a chunk referenced from a namespace the peer doesn't subscribe to — return `404`. Sync-state determination is implementation-defined; deployments SHOULD document their default behavior.

**Architectural note (v3.6 update).** The broader content-store cap-discipline question — how content-store access is capability-scoped at the substrate level — is answered in v3.6 by §6.4's two-topology framing: **namespace-scoped (Hash Tree Presence, §6.4.2) is the production default for multi-party deployments**; single-trust-domain is the opt-in restricted-use mode (§6.4.1). The algorithm-reference framing in this §3.4 (`reassemble_content` is a published algorithm, NOT a substrate primitive callable from SDK / third-party consumers) composes with §6.4: capability-checked access to materialized bytes routes through `system/content:get` (namespace-cap-scoped per the cap-matrix §6.4.3) or `local/files:read` (tree-path-cap-scoped). The unification question — fully merging the substrate cap-discipline across all content-bearing handlers into a single mechanism — remains for a future cycle; v3.6 settles the substrate-side answer for `system/content` access.

### 3.5 Recommended Chunk Sizes

| Content Size | Recommended Chunk Size | Resulting Chunks |
|-------------|----------------------|------------------|
| < 1 MiB | 1 MiB (single chunk) | 1 |
| 1 MiB — 1 GiB | 1 MiB | 1 — 1024 |
| 1 GiB — 16 GiB | 4 MiB | 256 — 4096 |
| > 16 GiB | Implementation-defined | ~1000–4000 target |

The default chunk size is **1 MiB (1,048,576 bytes)** (v3.6 — was 4 MiB in v3.5). This matches the centroid of production CDC systems (Borg, restic, casync) and balances:
- ~1024 chunks per GiB — manageable manifest size
- Effective deduplication granularity for typical edit workloads
- Per-chunk overhead (entity hash, envelope framing) remains negligible

Implementations **MAY** use any chunk size. The chunk size is recorded in the blob entity, so receivers handle any chunk size transparently. Implementations **SHOULD** ensure chunks fit within the transport's frame limit when one exists.

**Migration note (v3.5 → v3.6 cutover).** Existing deployments running the v3.5 4 MiB default remain conformant — chunks are self-describing per blob entity. New deployments SHOULD use 1 MiB. Migration does NOT require rechunking existing content (existing 4 MiB chunks stay valid); new content chunked at 1 MiB co-exists with old content chunked at 4 MiB in the same store. **Cross-peer dedup is preserved for any content chunked with the same parameters on both peers.** **Cutover coordination required:** implementations adopting the 1 MiB default SHOULD coordinate the cutover with sibling implementations to preserve cross-peer dedup during the transition window; un-coordinated cutovers lose dedup for content ingested mid-flight. **Prerequisite:** DOMAIN-LOCAL-FILES v1.3 Amendment 3 (§5.5 circuit-breaker recompute uses incoming blob's `chunk_size`, not consumer's local default) MUST land across all three impls before A2 cutover is safe — without it, mixed-size peers spuriously fire the circuit-breaker rewrite even when content is identical.

### 3.6 Content-Defined Chunking (Recommended)

The fixed-size algorithm (§3.2) splits at every N bytes regardless of content. Inserting a single byte at the start shifts every chunk boundary — all subsequent chunks get new hashes, and the entire content must be re-transferred. For content that is modified (working files, projects, datasets), this defeats deduplication.

Content-defined chunking (CDC) derives chunk boundaries from the content itself, so boundaries are stable across edits. Modifying content in one region only invalidates chunks in that region — chunks before and after retain their boundaries and hashes.

This extension specifies **FastCDC** as the recommended CDC algorithm. FastCDC uses a gear hash (one shift, one table lookup, one addition per byte — no sliding window) with normalized boundary selection. It is well-proven in production (Google cdc-file-transfer, Plakar), significantly faster than alternatives (Rabin fingerprint, Buzhash), and fully deterministic — two implementations with the same parameters produce identical chunks.

**Convergence is the mechanism (v3.6 strengthened).** The spec defines a specific gear table, specific parameters, and a specific boundary condition. Two implementations following this specification exactly produce identical chunks for the same content and target size. **Diverging from any of these parameters — different table, different mask derivation, different algorithm — drops the implementation out of the cross-peer dedup system for any content chunked with the divergent parameters.** Receivers still reassemble (chunk-list is self-describing), but the storage/bandwidth value of the substrate degrades to per-impl. Deployments that diverge SHOULD document the divergence in their conformance reporting per `GUIDE-EXTENSION-DEVELOPMENT.md` §9.

#### 3.6.1 Gear Table

The gear table is 256 entries of 64-bit unsigned integers, derived deterministically:

```
for i in 0..255:
  gear_table[i] = uint64_le(SHA-256("FastCDC" || byte(i))[0:8])
```

`SHA-256("FastCDC" || byte(i))` computes the SHA-256 hash of the 7-byte string "FastCDC" concatenated with a single byte of value `i`. `uint64_le` reads the first 8 bytes of the hash digest as a little-endian 64-bit unsigned integer.

All conforming implementations **MUST** use this derivation. The table is computed once at initialization.

#### 3.6.2 Parameters

| Parameter | Derivation | Default (1 MiB target — v3.6) |
|-----------|------------|----------------------|
| `target_size` | Configured (§3.5) | 1,048,576 |
| `min_size` | `target_size / 4` | 262,144 (256 KiB) |
| `max_size` | `target_size * 2` | 2,097,152 (2 MiB) |
| `bits` | `floor(log2(target_size))` | 20 |
| `NC` | 2 (normalization level) | 2 |
| `mask_s` | `(1 << (bits + NC)) - 1` | `0x003FFFFF` (22 bits) |
| `mask_l` | `(1 << (bits - NC)) - 1` | `0x0003FFFF` (18 bits) |

The normalization level `NC = 2` is the recommended value from the FastCDC paper. It controls the spread between the small-phase and large-phase masks — higher values produce tighter normalization around the target size.

#### 3.6.3 Algorithm

```
create_blob_cdc(raw_bytes, target_size):
  min_size = target_size / 4
  max_size = target_size * 2
  bits = floor(log2(target_size))
  mask_s = (1 << (bits + 2)) - 1
  mask_l = (1 << (bits - 2)) - 1

  chunks = []
  offset = 0
  while offset < length(raw_bytes):
    remaining = length(raw_bytes) - offset
    if remaining <= min_size:
      ; Final piece: too small to split further
      end = offset + remaining
    else:
      end = find_boundary(raw_bytes, offset, min_size, target_size,
                          max_size, mask_s, mask_l)

    chunk_bytes = raw_bytes[offset:end]
    chunk_entity = {type: "system/content/chunk", data: {payload: chunk_bytes}}
    chunk_hash = ecf_hash(chunk_entity)
    content_store.put(chunk_hash, chunk_entity)
    chunks.append(chunk_hash)
    offset = end

  blob_entity = {
    type: "system/content/blob"
    data: {
      total_size: length(raw_bytes)
      chunk_size: target_size
      chunking:   1               ; fastcdc
      chunks:     chunks
    }
  }
  blob_hash = ecf_hash(blob_entity)
  content_store.put(blob_hash, blob_entity)
  return blob_hash


find_boundary(data, offset, min_size, target_size, max_size, mask_s, mask_l):
  fp = 0
  i = offset + min_size

  ; Phase 1: harder mask (below target — fewer boundaries, push toward target)
  limit1 = min(offset + target_size, length(data))
  while i < limit1:
    fp = (fp << 1) + gear_table[data[i]]
    if (fp & mask_s) == 0:
      return i + 1
    i = i + 1

  ; Phase 2: easier mask (above target — more boundaries, pull back toward target)
  limit2 = min(offset + max_size, length(data))
  while i < limit2:
    fp = (fp << 1) + gear_table[data[i]]
    if (fp & mask_l) == 0:
      return i + 1
    i = i + 1

  ; Reached max_size — forced boundary
  return i
```

The two-phase mask (normalized chunking) concentrates chunk sizes around the target: the harder mask below the target makes boundaries less likely (pushing chunks toward the target size), while the easier mask above the target makes boundaries more likely (preventing oversized chunks). The `min_size` skip avoids scanning bytes that would produce undersized chunks.

#### 3.6.4 Why FastCDC

| Algorithm | Performance | Sliding window | Normalization | Adoption |
|-----------|------------|----------------|---------------|----------|
| **Rabin fingerprint** | ~500 MB/s | Yes | No | restic, LBFS, Tarsnap |
| **Buzhash** | ~1 GB/s | Yes | No | Borg, casync |
| **FastCDC** | 2–10 GB/s | No | Yes (built-in) | Google, Plakar |

FastCDC's gear hash requires one shift + one table lookup + one addition per byte — no sliding window, no polynomial arithmetic. The normalized boundary selection (dual masks) is unique to FastCDC and controls chunk size variance, which other algorithms lack. Performance scales with modern hardware (the v2020 variant processes two bytes per iteration for an additional 20–40% speedup with identical boundary decisions).

Implementations **SHOULD** use the FastCDC algorithm specified above. Implementations **MAY** use fixed-size chunking (§3.2) as a simpler alternative, with the understanding that edit-stability and cross-peer deduplication of modified content will be reduced.

#### 3.6.5 Conformance vectors (surfaces)

Cross-impl convergence for FastCDC (and fixed-size, for completeness) will produce conformance vectors at the surfaces below. These vectors are a Stage-4 byproduct per `GUIDE-EXTENSION-DEVELOPMENT.md` §7 — the architecture team does NOT pre-author them. The surfaces are named here so impl teams know what shape the vectors will take when they emerge.

- **Gear table surface.** First 16 entries of the gear table (§3.6.1), as 64-bit unsigned integers. Mechanically derivable from the formula; the role of a vector here is sanity-check, not novelty.
- **Fixed-size chunking surface.** For each of a small canonical input set (e.g., zeros, repeating patterns, pseudo-random with documented seed), the produced chunk boundaries and chunk hashes at each standardized chunk size.
- **FastCDC boundary surface.** Same canonical input set, with target sizes from the §3.5 recommended table, the produced chunk boundaries (byte offsets), chunk count, and chunk hashes. Edit-stability vectors — same input with a 1-byte insertion at a known offset, and the expected boundary delta — are the most interop-critical.
- **ECF byte-equality surface** (cross-references `EXTENSION-TYPE.md` §5.5). Vectors that exercise the canonical-encoding boundary for blob and chunk entities. Two impls disagreeing on the entity hash for the same `(chunks, chunk_size, chunking, total_size)` tuple breaks cross-peer dedup silently — the same class of risk that drove `ENTITY-CBOR-ENCODING.md` Appendix E.

Vectors land in the cross-impl validation matrix (compare `reviews/VALIDATION-MATRIX-IDENTITY-FOUNDATIONS.md`) once the first multi-impl pass surfaces them. The spec absorbs the canonical set at conformance lock.

### 3.7 Algorithm Classification

Per `ENTITY-CORE-PROTOCOL.md` §7 and `GUIDE-EXTENSION-DEVELOPMENT.md` §4.5, algorithms in this extension are classified:

| Algorithm | Classification | Requirement |
|-----------|---------------|-------------|
| Fixed-size chunking (§3.2) | **Conformance** | Implementations producing fixed-size blobs MUST produce byte-identical chunks for the same input + `chunk_size`. Cross-peer deduplication depends on this. |
| FastCDC chunking — gear table (§3.6.1) | **Conformance** | All conforming implementations MUST derive the gear table per `gear_table[i] = uint64_le(SHA-256("FastCDC" \|\| byte(i))[0:8])`. Table values are byte-identical across impls. |
| FastCDC chunking — boundary algorithm (§3.6.3) | **Conformance** | Implementations producing `chunking: 1` blobs MUST produce byte-identical chunk boundaries for the same input + `target_size`, given the gear table from §3.6.1. |
| Content verification (§3.3) | **Conformance** | Implementations MUST agree on whether a blob is complete (all chunks present, non-empty, total size matches). The completeness verdict is cross-peer-uniform. |
| Content reassembly (§3.4) | **Reference** | The pseudocode shows expected behavior. Implementations MAY stream, parallelize, or pre-allocate. The reassembled bytes MUST be identical. |
| Hash validation (§4.4) | **Conformance** | The membership check (chunk hashes in blob's `chunks` list; blob managed by this handler) MUST agree across implementations. The mechanism for step 1 (`handler.manages_blob`) is implementation-defined. |
| Descriptor lookup (§5.3) | **Reference** | The pseudocode in §5.3 shows expected behavior. Implementations MAY index, batch, or order publishers differently. The set of valid (publisher, descriptor) pairs returned MUST be equivalent for the same `(blob_hash, publisher_set, tree_state)`. |
| Handler blob ownership check (§4.4 step 1) | **Implementation-defined** | Each handler chooses its own mechanism (entity-tree walk, managed-blob set, etc.). The check's verdict is local. |
| Namespace-to-content mapping (§6.4) | **Implementation-defined** | Tagging, partitioning, default-everything, or hash-presence-in-tree — all valid. |
| Transfer parallelism (§7.4) | **Implementation-defined** | Concurrent request count is a local performance decision. |

---

## 4. Handler Integration

Handlers that deal with binary content implement the algorithms from §3 and serve content through their own paths and capability scopes. The content chunking mechanism is transparent to clients — they interact with the handler's operations, not with content entities directly.

### 4.1 The Handler-Centric Access Model

Each handler manages its own content access. A client that has a capability for a handler's path can access the content that handler manages — no additional content-specific capabilities are needed.

```
Client                                      Handler (e.g., local files)
  │                                           │
  ├─ EXECUTE {                                │
  │    uri: "local/files/report.pdf"          │
  │    operation: "read"                      │
  │  } ─────────────────────────────────────>│
  │                                           ├─ Validates capability for local/files/*
  │                                           ├─ Reads file metadata from entity tree
  │                                           ├─ Reads blob manifest from content store
  │                                           │
  │<── Envelope {                             │
  │      root: EXECUTE_RESPONSE {             │
  │        result: file_entity                │  File entity as result
  │      }                                    │  (includes data.content: blob_hash)
  │      included: {                          │
  │        blob_hash: blob_entity             │  Blob manifest included
  │      }                                    │
  │    } ────────────────────────────────────│
  │                                           │
  │  Client reads file entity from result,    │
  │  looks up data.content hash in included,  │
  │  extracts chunk hashes from blob manifest │
  │                                           │
  ├─ EXECUTE {                                │
  │    uri: "local/files/report.pdf"          │
  │    operation: "get"             │
  │    params: {                              │
  │      blob_hash: "ecfv1-sha256:abc..."       │
  │      hashes: [chunk1, chunk2, ...]        │
  │    }                                      │
  │  } ─────────────────────────────────────>│
  │                                           ├─ Validates capability for local/files/*
  │                                           ├─ Validates blob belongs to this handler
  │                                           ├─ Validates chunk hashes are in blob
  │                                           ├─ Reads chunks from content store
  │                                           │
  │<── Envelope {                             │
  │      root: EXECUTE_RESPONSE {             │
  │        result: {found, missing}           │
  │      }                                    │
  │      included: {                          │
  │        chunk1: chunk_entity, ...          │  Chunks in included map
  │      }                                    │
  │    } ────────────────────────────────────│
```

The handler:
1. Validates the client's capability against its own path pattern
2. Returns content-referencing entities with the blob included in the envelope
3. On get-request, validates the blob belongs to this handler and chunk hashes are in the blob
4. Reads from the shared content store and returns chunks in the envelope's included map

The client:
1. Requests metadata through the handler's domain operation (e.g., `read`)
2. Reads the result entity's content ref, resolves it to the blob in the envelope's included map
3. Fetches chunks through the handler's `get-request` operation, specifying the blob hash
4. Reassembles using the reassembly algorithm (§3.4)

### 4.2 Content Operations for Handlers

Handlers that serve chunked content **SHOULD** implement a content get operation. `get-request` is a **recommended op-name convention** for any domain handler serving content (e.g., `local/files:get-request`, `media:get-request`, `dataset:get-request`); it is not a system-level op. Per `GUIDE-EXTENSION-DEVELOPMENT.md` §4.2, normative prose uses the full handler path (`<handler-uri>:get-request`); the bare name names the convention.

```
; Handler-specific content get operation (the convention)
get-request := {
  input_type: {
    fields: {
      blob_hash: {type_ref: "system/hash"}                   ; Blob manifest hash
      hashes:    {array_of: {type_ref: "system/hash"}}       ; Chunk hashes to get
    }
  }
  output_type: "system/content/content-response"               ; Reuses system content type
}
```

The `blob_hash` field serves two purposes: it identifies which content the client is requesting chunks for, and it enables the handler to validate chunk ownership efficiently (§4.4). The response reuses `system/content/content-response` (§6.2) — the `found`/`missing` pattern is the same regardless of whether the handler or the system content handler serves the chunks.

This operates under the handler's own capability scope. The handler **MUST** verify that the blob belongs to content it manages and that the requested chunk hashes are in that blob's manifest — a handler **MUST NOT** serve arbitrary hashes from the content store, as that would bypass the handler-centric access model (§4.4).

Implementations **MUST** respect **the transport's configured frame budget** (per V7 §1.6; consult the connection's configured budget at response-construction time, NOT a hardcoded 16 MiB literal) when constructing the response. If including all resolved entities would exceed the limit, the implementation **SHOULD** include as many as fit (in request order) and move the remainder to `missing`. The requester retries with the missing hashes.

**Behavioral conformance — frame-budget response chunking (v3.6+).** The frame-budget MUST is exercised by the `system/content/frame-limit-respected` validate-peer behavioral check. The check verifies behavior by issuing a request whose ideal response would exceed the connection's frame budget and confirming the response carries the partial set in `found` plus the rest in `missing`. Implementations failing this check are non-conformant. Companion: §7.4 transport-aware batching responsibility split (senders SHOULD implement `GET_BATCH_SIZE`-windowed batching per §7.1; receivers MUST respect frame-budget per this paragraph).

### 4.3 Small Content Optimization

Handlers **SHOULD** inline-include chunk entities in the metadata response's `included` map when the blob's `total_size` is **≤ 65,536 bytes (64 KiB)**. Above 64 KiB, handlers SHOULD require the client to follow up with the handler's `<handler-uri>:get-request` operation (§4.2) or, where the system content handler is installed, `system/content:get` (§6.2).

The 64 KiB threshold balances three concerns: (a) small files (thumbnails, config snippets, short text documents) round-trip in one envelope, eliminating the second EXECUTE for the dominant case; (b) the threshold sits below the typical transport frame limit (~1 MiB) by a wide margin, leaving headroom for the envelope framing and the metadata entity itself; (c) the threshold is small enough that even on a peer storing millions of small entities, the per-call envelope cost stays bounded. Handlers MAY use a larger inline threshold when their deployment knows the transport headroom; the 64 KiB pin is the cross-impl-uniform default.

**Alignment with `MIN_CHUNK_SIZE` (§10.1).** The 64 KiB threshold equals the protocol's `MIN_CHUNK_SIZE`: a blob with `total_size ≤ 64 KiB` is exactly one chunk at the minimum chunk size (the final-chunk exception in §10.1 covers this). The inline-include optimization therefore activates precisely when the blob's chunk graph collapses to a single sub-`MIN_CHUNK_SIZE` chunk — the simplest possible content shape. The alignment is intentional, not coincidental: above 64 KiB a blob has either two minimum-size chunks or one chunk above the minimum, and the round-trip cost of the second EXECUTE becomes comparable to the per-chunk envelope overhead.

```
; Handler returns metadata + blob + all chunks in one response
; When total content fits the 64 KiB inline threshold
handle_read(params, ctx):
  metadata = entity_tree.get(file_path)
  blob = content_store.get(metadata.data.content)   ; Look up by system/hash
  ctx.include(blob.content_hash, blob)
  if blob.data.total_size <= 65536:
    for chunk_hash in blob.data.chunks:
      chunk = content_store.get(chunk_hash)
      ctx.include(chunk_hash, chunk)
  return metadata
```

### 4.4 Hash Validation

A handler serving content **MUST** validate that requested chunk hashes are in the specified blob, and that the blob belongs to content this handler manages. This prevents the handler from becoming an open proxy to the content store.

The `blob_hash` in the get-request request (§4.2) makes validation straightforward:

```
validate_get_content(handler, blob_hash, requested_hashes):
  ; Step 1: Verify this handler manages content referencing this blob
  if not handler.manages_blob(blob_hash):
    DENY

  ; Step 2: Load the blob manifest and verify chunk membership
  blob = content_store.get(blob_hash)
  if blob is null:
    DENY

  valid_chunks = set(blob.data.chunks)
  for hash in requested_hashes:
    if hash not in valid_chunks:
      DENY

  ALLOW
```

Step 1 checks that the blob is reachable from an entity this handler manages (e.g., a file entity in the handler's entity tree path with a content ref pointing to this blob). The mechanism is implementation-defined — handlers may check the entity tree directly, maintain a set of managed blob hashes, or use other strategies.

Step 2 is a set membership check against the blob's chunk list. The blob manifest is typically already in the content store from the preceding metadata request, so this is a local lookup.

---

## 5. Content Referencing

### 5.1 Referencing Content from Entities

Entity types reference content through a ref to the blob entity:

```
; Example: file entity referencing content
{
  type: "local/files/file"
  data: {
    name: "report.pdf"
    size: 52428800
    modified_at: 1706832000000
    content: h'00...'                                       ; system/hash reference to blob (33 B under SHA-256; length per format byte)
  }
}
```

Any entity type following this pattern gets automatic content deduplication. The blob entity is shared when the same content (same raw bytes) is referenced by different typed entities, provided they use the same chunk size. Content type, filename, and other semantic metadata belong on the referencing entity — the blob is purely structural.

### 5.2 Entity Inclusion in Envelopes

When a handler returns a result entity that references a content blob, the handler **MUST** include the blob entity in the response envelope's `included` map. Without the blob manifest, the client has no way to discover the chunk list — the blob is in the content store (not the entity tree), and the client has no separate operation to request it by hash through the handler.

The sender **SHOULD NOT** include chunk entities in the same envelope — they are fetched separately via the handler's `<handler-uri>:get-request` operation (§4.2). For small content that fits the 64 KiB inline threshold, the handler **SHOULD** also include chunk entities (§4.3).

### 5.3 Descriptor Path Convention

A descriptor entity (§2.4) is bound at a tree path keyed by the blob it describes, scoped to the publishing peer:

```
/{publisher_peer_id}/system/content/descriptor/{B_hex}/{D_hex}
```

Where:

- `B_hex` = hex encoding of the blob's entity hash (the **anchor**).
- `D_hex` = hex encoding of the descriptor's own entity hash (the **leaf**).

**The dual-level keying is normative.** This parallels V7's existing capability-signature convention at one level deeper:

| | Capability-signature pattern (V7) | Descriptor pattern (§2.4) |
|---|---|---|
| Path | `/{signer_peer}/system/signature/{target_hex}` | `/{publisher_peer}/system/content/descriptor/{B_hex}/{D_hex}` |
| Cardinality | One per (signer, target) | N per (publisher, blob) — one per consumption format |
| Anchor | `target_hex` (the thing signed) | `B_hex` (the blob being interpreted) |
| Discovery from anchor | Read the invariant path on candidate signers | List the `{B_hex}/` subtree on candidate publishers; enumerate descriptor leaves |
| Authority | The signer attests the target | Anyone publishes; no authority claim implied |
| Integrity | Signature over `target_hex` | Descriptor body's `content` field carries `hash(B)`; tampering changes `D_hex` |

**Integrity check (MUST).** A consumer fetching a descriptor at `/{publisher}/system/content/descriptor/{B_hex}/{D_hex}` **MUST** verify that `descriptor.data.content == B`. Mismatch ⇒ reject. This is the two-level defense against path corruption or accidental misbinding (the path embeds `B_hex`, the body carries `hash(B)`; both must agree).

**Lookup workflow (Reference algorithm per §3.7):**

```
descriptors_for(blob_hash B, candidate_publishers P_set, ctx):
  results = []
  for P in P_set:
    leaves = ctx.tree.list("/{P}/system/content/descriptor/{B_hex}/")
    for D_hex in leaves:
      descriptor = ctx.tree.get("/{P}/system/content/descriptor/{B_hex}/{D_hex}")
      if descriptor.data.content != B:
        continue  ; integrity check — MUST
      results.append((P, descriptor))
  return results
```

Cross-peer discovery uses the standard sync paths the system content handler exposes (§6). No new transport mechanism; the descriptor is just another entity, fetched the same way as any other.

**Trust model.** Anyone may publish descriptors. The architecture takes no stance on whose descriptor a consumer should honor. Common deployment policies:

- **Strict publisher allowlist.** Honor descriptors only from pre-trusted peers (originating publisher, curated catalogue peer).
- **Format-driven.** Honor any descriptor whose declared format the consumer can render; cross-verify by attempting consumption.
- **Quorum / curation.** Treat a blob as having interpretation X if K-of-N curators publish matching descriptors.
- **Open / TOFU.** Accept any descriptor; let the rendering layer reject bad ones.

These are deployment policies, not protocol mandates. The protocol guarantees: bytes are unchanged (content-addressing); the integrity check filters path-corruption; a wrong format hint produces a failed render that the consumer can ignore.

**Layer 1 vs Layer 2** (`GUIDE-EXTENSION-DEVELOPMENT.md` §4.8). Descriptor consumption is **Layer 2 only.** It modulates local consumer behavior (which descriptor to honor, which format to render) over a content-addressed blob. It does not consult or modify the capability chain verdict. No cross-peer-determinism concern.

See `GUIDE-EXTENSION-DEVELOPMENT.md` §3.5 for the general "paths are convention; the entity graph is coherence" pattern this convention exemplifies.

---

## 6. System Content Handler (Optional)

The system content handler provides capability-gated, hash-addressed access to the content store. It is a specialized component for specific use cases — most peers do not need it. Handler-mediated content access (§4) is sufficient for normal content delivery and provides stronger security properties (blob ownership validation, view tree scoping).

**What it provides**: The core protocol provides path-based access to the entity tree via the system tree handler's `get`/`put` operations (ENTITY-CORE-PROTOCOL.md §6.3), but there is no protocol-level access to the content store — the second storage layer (`Hash → Entity`). The system content handler fills this gap. It takes hashes, looks them up in the content store, and returns whatever entities it finds. The operations are type-agnostic.

**When to install it**:

- **Content store synchronization** — keeping content stores in sync across peers you own. Back up all content to a central peer, or replicate across machines for redundancy.
- **Public content networks** — participating in shared content distribution. The blob manifest maps naturally to a torrent-like model: share the manifest (chunk list), and any peer with the content handler installed can serve the chunks. Combined with the descriptor pattern (§5.3), the system content handler supports public-content distribution with portable interpretation: peers fetch a blob by hash, discover descriptors via the invariant-path convention, choose a consumption format they support, and render. Descriptors carry the semantic anchor; the system content handler carries the bytes.
- **Entity graph traversal** — following refs to entities not available locally, when the source handler is unknown or unavailable.

**When NOT to install it**: For normal client access to handler-managed content, use the handler's own content operations (§4). The handler-mediated model provides blob ownership validation (§4.4) and integrates with view tree scoping (EXTENSION-TREE.md §8). The system content handler bypasses both.

**Security implications**: Without namespace scoping (§6.4), this handler exposes the entire content store to any peer with a valid capability. It does not provide listing or enumeration — peers must already know the hashes — but any known hash is retrievable. See §6.5 for deployment guidance.

### 6.1 Handler Manifest

```
system/handler := {
  pattern:    "system/content/*"
  name:       "content"
  operations: {
    get: {
      input_type:  "system/content/get-request"
      output_type: "system/content/content-response"
    }
    ingest: {
      input_type:  "system/content/ingest-request"
      output_type: "system/content/ingest-result"
    }
  }
}
```

Manifest at pattern path `system/content`. Index entry at `system/handler/system/content`.

The handler declares `get` and `ingest` operations. Domain handlers MAY also declare `get` (ENTITY-CORE-PROTOCOL.md §6.4) — the handler scope distinguishes them. A `get` on `system/content` is hash-addressed (content store lookup). A `get` on `system/tree` is path-addressed (entity tree lookup). Same verb, different handler, different addressing.

### 6.2 Get

Hash-addressed entity retrieval. Returns any entity type — blobs, chunks, capabilities, type definitions, or any other entity in the content store.

```
system/content/get-request := {
  fields: {
    hashes: {array_of: {type_ref: "system/hash"}}        ; Entity hashes to retrieve
  }
}

system/content/content-response := {
  fields: {
    found:   {array_of: {type_ref: "system/hash"}}       ; Hashes successfully resolved
    missing: {array_of: {type_ref: "system/hash"}}       ; Hashes not found
  }
}
```

The response envelope's `included` map contains the resolved entities. The `found` list confirms which hashes were resolved. The `missing` list identifies hashes not present in the content store.

**Wire shape contract (v3.6 — F4 cross-impl audit landing).** `content-response.data.found` and `content-response.data.missing` are `array_of system/hash` — arrays of hashes, not counters. The fetched entities themselves are delivered via the response envelope's `included` map (per ENTITY-CORE-PROTOCOL.md §3.3 v7.51 envelope-`included` preservation across dispatch boundaries), not embedded in the response data body. Consumers iterate `envelope.included` to obtain the fetched entities; the `found` array is the index that confirms which hashes are present in `included` and the `missing` array names hashes the receiver did not have. **Implementations MUST emit arrays (not counters)**; deriving a count from an array is trivial, deriving an array from a count is not. The three-way cross-impl audit (Rust + Python emit arrays; Go's v3.5 hybrid emits counters) confirmed the spec-literal arrays shape; Go's amendment to arrays is in flight.

```
handle_get(params, ctx):
  found = []
  missing = []
  for hash in params.hashes:
    entity = content_store.get(hash)
    if entity is not null:
      ctx.include(hash, entity)
      found.append(hash)
    else:
      missing.append(hash)
  return {found, missing}
```

Implementations **MUST** respect **the transport's configured frame budget** (per V7 §1.6; consult the connection's configured budget at response-construction time, NOT a hardcoded 16 MiB literal) when constructing the response. If including all resolved entities would exceed the limit, the implementation **SHOULD** include as many as fit (in request order) and move the remainder to `missing`. The requester retries with the missing hashes.

**Behavioral conformance — frame-budget response chunking (v3.6+).** The frame-budget MUST is exercised by the `system/content/frame-limit-respected` validate-peer behavioral check. The check verifies behavior by issuing a request whose ideal response would exceed the connection's frame budget and confirming the response carries the partial set in `found` plus the rest in `missing`. Implementations failing this check are non-conformant. Companion: §7.4 transport-aware batching responsibility split (senders SHOULD implement `GET_BATCH_SIZE`-windowed batching per §7.1; receivers MUST respect frame-budget per this paragraph).

Single-entity retrieval is `hashes: [one_hash]`. The response is always `{found, missing}` — no separate single-entity operation.

**Partial-sync sidecar (canonical; v3.6 Amendment 2 — resolves three-impl convergence on bare-hash `missing`).** The `missing` field is `array_of system/hash` — bare hashes, no per-entry dicts (per the v3.6 §6.2 spec-literal-arrays contract; three impls converged on this wire shape empirically). The sync-state-visibility predicate (per §3.4) is exposed as a separate optional sidecar field on the response:

```
content-response.data := {
  found:   array_of system/hash      ; hashes successfully resolved (in envelope.included)
  missing: array_of system/hash      ; hashes not found (caller may retry)
  pending: array_of system/hash      ; OPTIONAL; subset of missing; the hashes the
                                     ; receiver expects to arrive via the normal sync
                                     ; mechanism (active subscription + inbox feeding
                                     ; the content store — sync-state-visibility per §3.4).
                                     ; Implementations supporting sync-state visibility
                                     ; SHOULD populate. Receivers without sync-state
                                     ; awareness MAY omit (empty or absent).
}
```

Semantic mapping:
- A hash in `missing` AND in `pending` → canonical `503 blob_pending_sync` — caller SHOULD retry on next sync event (per §3.4).
- A hash in `missing` but NOT in `pending` → terminal `404 not_found` — caller treats as won't-arrive via the normal mechanism.
- `pending` absent or empty → receiver does not advertise sync-state visibility; caller treats all `missing` as terminal (404) unless overridden by deployment policy.

Sync-state determination is implementation-defined; deployments SHOULD document their default predicate. **The annotation is informational — it does not change the `missing` list shape; callers without sync-state awareness MAY ignore `pending` entirely.** Earlier text (v3.6 baseline) suggested per-entry `{hash, pending}` dict entries; this was retracted as internally contradictory (the spec text "does not change the missing list shape" cannot coexist with per-entry dict objects). The sidecar form is the canonical shape; per-entry dict form is non-conformant.

**Path-as-resource (ENTITY-CORE-PROTOCOL.md §3.2 MUST).** The `system/content:get` EXECUTE carries a `resource` field naming the namespace path (e.g., `system/content` for the default namespace, `system/content/public` for the `public` namespace; see §6.4). The namespace path is the cap-scope resource; the `hashes` array in `params` is the operation payload. Calling `system/content:get` without a `resource` **MUST** return **`400 path_required`** (`GUIDE-EXTENSION-DEVELOPMENT.md` §171 is the authority for this code). This is consistent with the ENTITY-CORE-PROTOCOL.md §3.2 pattern: every directly-callable op identifies its resource, even when the op's semantic target is hash-shaped.

**Default namespace path (v3.6 — F5 SDK-author clarity).** All `system/content:get` and `system/content:ingest` dispatches MUST carry a `Resource.Targets` value matching the configured namespace prefix. The default namespace prefix for the system content handler when no namespace sub-path is configured is `system/content` (per §6.1 manifest registration); dispatches targeting the default handler use `Resource.Targets = ["system/content"]`. Dispatches targeting a sub-namespace (e.g., `system/content/public`) use `Resource.Targets = ["system/content/public"]`. See §6.4 for the namespace-scoping mechanism and §6.4.3 cap-matrix that scopes which namespaces a given grant covers.

### 6.3 Ingest

Writes entities into the content store from an envelope or a standalone entity. Complements `get` — `get` reads from the content store by hash, `ingest` writes to it.

```
system/content/ingest-request := {
  fields: {
    envelope: {type_ref: "system/envelope", optional: true}
              ; An envelope — root + included entities. All are stored.
    entity:   {type_ref: "core/entity", optional: true}
              ; A standalone entity. Stored as-is.
              ; Exactly one of envelope or entity MUST be present.
  }
}

system/content/ingest-result := {
  fields: {
    root:           {type_ref: "core/entity", optional: true}
                    ; In envelope mode with non-null envelope.root, this is
                    ; envelope.root, inlined. Enables downstream chain steps
                    ; to navigate into the wrapper's fields (e.g., via
                    ; transform extract "data.root.data.<field>") without
                    ; dereferencing the content store.
                    ; Absent in entity mode (no envelope wrapper to pass).
    root_hash:      {type_ref: "system/hash"}
    ingested_count: {type_ref: "primitive/uint"}
  }
}
```

**Algorithm:**

```
handle_ingest(ctx, params):
  if params.data.envelope is not null and params.data.entity is not null:
    return error(400, "ambiguous_input", "Specify envelope or entity, not both")
  if params.data.envelope is null and params.data.entity is null:
    return error(400, "missing_input", "Specify envelope or entity")

  ; --- Envelope mode: store root + all included ---
  if params.data.envelope is not null:
    envelope = params.data.envelope
    count = 0

    if envelope.root is not null:
      ctx.content_store.put(envelope.root)
      count += 1

    for (hash, entity) in envelope.included:
      if content_hash(entity) != hash:
        return error(400, "hash_mismatch", "included entity hash does not match key")
      ctx.content_store.put(entity)
      count += 1

    root_hash = content_hash(envelope.root)
    return {status: 200, result: {
      root:           envelope.root,            ; pass-through; absent when envelope.root is null
      root_hash:      root_hash,
      ingested_count: count
    }}

  ; --- Entity mode: store single entity ---
  entity = params.data.entity
  ctx.content_store.put(entity)
  entity_hash = content_hash(entity)
  return {status: 200, result: {root_hash: entity_hash, ingested_count: 1}}
```

**Properties:**

- **Content store only.** No tree writes, no subscriptions fire, no cascades. The operation writes to the content store, which is append-only, immutable, and has no reactive behavior.
- **Idempotent.** Storing an entity that already exists is a no-op — content-addressed storage is inherently idempotent.
- **Type-agnostic.** Like `get`, `ingest` handles any entity type — blobs, chunks, trie nodes, file entities, or any other entity. The content handler is type-agnostic by design (§6).
- **Hash validation.** Each included entity's content hash is verified against its key in the included map. A mismatch indicates a malformed envelope and is rejected.
- **Two input modes.** Envelope mode stores root + all included entities (bulk). Entity mode stores a single entity. Exactly one of `envelope` or `entity` must be present.
- **Post-ingest availability.** After ingest, all entities from the envelope are available via `content_store.get(hash)`. The returned `root_hash` can be passed to subsequent operations (e.g., `merge` expects a snapshot hash in the content store).
- **Result root pass-through.** In envelope mode with non-null `envelope.root`, the result includes `root` — the original `envelope.root` entity inlined as a value. This enables downstream continuation chain steps to navigate into the wrapper's fields (e.g., `extract: "data.root.data.head"`) without dereferencing the content store. In entity mode, `root` is absent — there is no envelope wrapper to pass through. Existing callers that read only `root_hash` and `ingested_count` are unaffected.

**Cross-implementation transition.** Implementations adopting the `root` field SHOULD coordinate rollout with sibling-implementation peers. During the transition, mixed peers will produce non-byte-identical `ingest-result` entities for the same input — the `root_hash` and `ingested_count` fields remain semantically correct in both shapes; only the entity-level content hash differs. Chains do not reference the ingest-result entity's hash directly, so chain composition is unaffected.

**§6.3.1 Chain composition pattern (informative).**

A common chain shape produces a wrapped-envelope response and feeds it to a downstream operation that needs a semantic field from inside the wrapper. Example: `revision/fetch → content:ingest → revision/merge`.

```
Step 1: revision/fetch  →  envelope {
    root: { type: "system/revision/fetch-result",
            data: { head: V_hash, versions: [...], has_more: false } },
    included: { version entries, trie roots }
  }

Step 2 (continuation): target system/content, operation ingest
    params.envelope = <result of step 1>
    → ingest-result {
        root:           { type: "system/revision/fetch-result", data: {...} },
        root_hash:      hash(fetch-result wrapper),
        ingested_count: N
      }

Step 3 (continuation): target system/revision, operation merge
    transform.extract = "data.root.data.head"
    params            = { prefix: "...", strategy: "three-way" }
    result_field      = "remote_version"
    → merge runs with params = { prefix, strategy, remote_version: V_hash }
```

The path `data.root.data.head` crosses two entity boundaries: `data.` into the ingest-result entity's payload, then `.root.` to the inlined wrapper entity, then `.data.` into the wrapper's payload, then `.head` for the field. Each `.data.` step crosses one entity boundary.

The `extract → result_field` pattern is the inject mode of `execute_dispatch` (EXTENSION-CONTINUATION.md §3.6): `extract` produces a single value from the previous result; `result_field` names the params slot the value is injected into; the continuation's static `params` provides the remaining fields the operation needs.

For the snapshot-IS-root case (e.g., `tree/extract → content:ingest → tree/merge`), the wrapper IS the snapshot, and `data.root_hash` is directly usable as `source`. Both navigation paths coexist correctly against the same ingest-result shape.

**Capability and path-as-resource (ENTITY-CORE-PROTOCOL.md §3.2 MUST).** Requires a grant for `system/content` with operation `"ingest"`. The EXECUTE carries a `resource` field naming the namespace path (the same path the corresponding `get` would target); the grant's `resources` scope covers the namespace. Calling `system/content:ingest` without a `resource` **MUST** return **`400 path_required`** (`GUIDE-EXTENSION-DEVELOPMENT.md` §171 is the authority for this code). The hashes embedded in `params.envelope` / `params.entity` are operation payload; the namespace path is the resource the cap scope sees. (Pre-v3.5 wording read "No resource scope is needed — content store writes are hash-addressed, not path-addressed." That posture is reversed in v3.5: the hashes are payload; the namespace is the resource that scopes which writers can land bytes in which namespace partition.)

**Behavior-change callout (v3.4 → v3.5).** Peers that previously called `system/content:get` / `system/content:ingest` without a `resource` field will now receive `path_required`. v3.4 has no shipped impls, so no migration path is needed in practice — the change lands as a v3.4 → v3.5 normative tightening, not as a deprecation. Impl teams reading the diff should not miss this single line of behavior reversal.

Deployment considerations from §6.5 apply: `ingest` allows any peer with a valid capability + namespace scope to write arbitrary entities into the namespace partition. This is safe (content store is append-only, content-addressed, no reactive behavior) but increases storage usage; peers SHOULD scope `ingest` capabilities to trusted peers.

### 6.4 Namespace Scoping

The handler path provides natural namespace support. The URI path after `system/content/` is the namespace:

```
entity://peer/system/content             ; Default namespace (single-trust-domain topology only)
entity://peer/system/content/public      ; "public" namespace
entity://peer/system/content/shared      ; "shared" namespace
```

Namespace scoping requires a two-level capability check, following the same pattern as the tree handler (ENTITY-CORE-PROTOCOL.md §6.3):

1. **Handler scope** (system-level): The capability **MUST** include a grant with `handlers: {include: ["system/content/*"]}` (or a covering pattern) and `operations: {include: ["get"]}`. When the EXECUTE includes a `resource` field (`system/protocol/resource-target`), `check_permission` also verifies the resource targets against the grant's `resources` scope. Checked by `check_permission` (ENTITY-CORE-PROTOCOL.md §5.2) before the handler is called.
2. **Path scope** (handler-level, defense-in-depth): The handler checks whether the capability grants `get` on the specific namespace path via the `resources` scope using `check_path_permission`. When `resource` is present on the EXECUTE, this is defense-in-depth (dispatch already verified resource scope). When `resource` is absent, this is the sole path-level enforcement.

```
; Trusted peer: full content store access (single-trust-domain topology only)
grants: [
  {handlers: {include: ["system/content/*"]}, resources: {include: ["system/content/*"]}, operations: {include: ["get"]}}
]

; Scoped peer: public namespace only (namespace-scoped topology — production default)
grants: [
  {handlers: {include: ["system/content/*"]}, resources: {include: ["system/content/public/*"]}, operations: {include: ["get"]}}
]
```

The handler extracts the namespace from the request URI and performs the path-scope check:

```
handle_get(params, ctx, request_uri, capability):
  ; Handler scope already verified by check_permission (§5.2)

  ; Path-scope check (handler-level)
  if not check_path_permission("get", request_uri_path, capability, "system/content", local_peer_id):
    return error(403, "forbidden")

  ; Proceed with hash lookups scoped to this namespace
  namespace = extract_namespace(request_uri)
  ...
```

The two-level check applies uniformly to both `get` and `ingest` — both ops are hash-addressed at the params level and path-addressed at the cap-scope level.

#### 6.4.1 Deployment topologies — namespace-scoped (production default) vs. single-trust-domain (opt-in)

The system content handler supports two deployment topologies; their applicability is asymmetric. **Namespace-scoped is the production default for any multi-party deployment.** Single-trust-domain is an opt-in mode for narrowly-scoped use cases and MUST NOT be enabled as the production default configuration.

**Namespace-scoped topology (production default; canonical).** Multiple distinct namespaces (e.g., `system/content/public`, `system/content/shared/team-alpha`, `system/content/orgs/foo/projects/bar`); each namespace cap-scoped separately; namespace-membership is a meaningful access boundary. `system/content:ingest` into namespace P writes to the content store **AND** binds at the canonical path in the tree (§6.4.2); `system/content:get` consults the tree binding and serves only when the hash is bound under the requested namespace. **All multi-party production deployments MUST use namespace-scoped topology. Production-grade implementations MUST support namespace-scoped topology and SHOULD wire §6.4.2 as the canonical convention.**

**Single-trust-domain topology (opt-in, restricted use).** One logical namespace; broad cap grants; the content store is a flat hash-keyed KV. `system/content:ingest` writes to the content store only (no tree binding); `system/content:get` resolves any hash for any cap-holding caller. Security floor is hash secrecy + cap-checked dispatch on a single broad namespace. **This topology is for single-trust-domain deployments only:** dev/test environments, single-machine deployments, deployments where every cap-holding caller is at the same trust level by construction (e.g., all callers are first-party services under one operator). **Implementations supporting this topology MUST document it as explicitly opt-in and MUST NOT enable it as the default configuration.** Multi-party deployments operating under single-trust-domain topology are out-of-spec and security-defective.

Mixed-mode (a handler instance per namespace, each in its own topology) is conformant; this is left to deployment configuration. The "multi-party" trigger for the namespace-scoped MUST is whether the handler instance serves callers under non-equivalent trust levels, not whether the deployment as a whole has multiple peers.

#### 6.4.2 Canonical namespacing convention — Hash Tree Presence (namespace-scoped topology)

For deployments using the namespace-scoped topology (§6.4.1), the canonical convention binds each content hash directly into the tree at a path under the namespace prefix:

```
{namespace}/{hex(H)}
```

where `{namespace}` is the namespace prefix (e.g., `system/content/public`, `system/content/shared/team-alpha`) and `{hex(H)}` is the lowercase hex encoding of the content hash. **`{hex(H)}` follows the ENTITY-CORE-PROTOCOL.md §3.5 invariant-path hex convention — lowercase, *format-code byte included*, NOT the 64-char digest-only form. Its length is implied by the leading format byte and is never assumed** (66 chars beginning `00` under ECFv1-SHA-256, 98 beginning `01` under ECFv1-SHA-384 — `SPECIFICATION-FORMAT.md` §8.4.5). This preserves the algorithm discriminator for crypto-agility and gives URL ⇄ binding parity for the NETWORK §6.5.6 serving route. The bound entity at that path is the `system/content/blob` or `system/content/chunk` entity itself.

Namespace depth is a deployment choice: flat (`system/content/public/{hex(H)}`), categorized (`system/content/shared/team-alpha/{hex(H)}`), or arbitrarily nested (`system/content/orgs/foo/projects/bar/{hex(H)}`) all conform. The leaf component is always `{hex(H)}`.

**Lookup is a single `tree:get` probe:**

```
tree:get({namespace}/{hex(H)}) → blob_entity | null
```

A null return means the hash is not bound under the namespace (so `system/content:get` under that namespace returns 404 even if the hash exists in the content store under a different namespace); a non-null return means it is. No reverse-index or scan operation is required.

**Ingest binds at the canonical path:**

```
system/content:ingest into namespace {namespace} writes:
  content_store.put(H, blob_entity)
  tree.put({namespace}/{hex(H)}, blob_entity)        ; the §6.4.2 namespace binding
```

Receivers of `system/content:get` under `{namespace}` resolve via `tree:get({namespace}/{hex(H)})` first and serve the bound entity. Implementations operating in single-trust-domain topology (§6.4.1) skip the `tree.put` step and resolve via `content_store.get(H)` directly; this is only valid under the §6.4.1 opt-in restrictions.

#### 6.4.3 Capability matrix for namespace access (namespace-scoped topology)

*This matrix applies to deployments using the namespace-scoped topology (§6.4.1) — i.e., all production multi-party deployments. For single-trust-domain deployments (opt-in, restricted use per §6.4.1), cap-checked dispatch on the single broad namespace prefix is the only access control; the matrix does not subdivide.*

Under the canonical Hash Tree Presence convention, the operational meaning of "namespace-scoped access" is a function of which ops the cap grant covers:

| Grant covers... | Holder can... | Operational shape |
|---|---|---|
| `tree:get` on `{namespace}/*` only | Enumerate all bound hashes by listing; retrieve any bound entity by exact-path tree:get | **Public listable index** — namespace is fully discoverable |
| `system/content:get` on `{namespace}/*` only | Probe by hash; retrieve content for known hashes; cannot enumerate | **Probe-only namespace** — holder must already know hashes (out-of-band, from a manifest, etc.) |
| Both `tree:get` and `system/content:get` on `{namespace}/*` | Both enumerate and retrieve | **Full read access** — standard "trusted peer" shape |
| `system/content:ingest` on `{namespace}/*` | Publish hashes into the namespace | **Publish access** — separate from read; composes with read grants |
| Neither read op | No access | **Default deny** |

Deployments select the access shape per-namespace by issuing grants that cover the appropriate ops. The matrix is the substrate's expression of the privacy/discoverability spectrum:

- **Public catalogues** (e.g., a shared media library): grant `tree:get` + `system/content:get` broadly.
- **Private namespaces with known-hash access** (e.g., capability-token-style sharing where the hash IS the share link): grant `system/content:get` only; recipients must obtain the hash through the sharing channel.
- **Tiered access** (e.g., browse vs. download): split grants by namespace sub-prefix; coarse-grained `system/content:get` everywhere, narrow `tree:get` only for the discoverable subset.

#### 6.4.4 Alternative namespacing shapes (informative — for namespace-scoped topology only)

The Hash Tree Presence convention (§6.4.2) is canonical; impls SHOULD use it as the default for namespace-scoped topology. Deployments with specific constraints MAY use alternative shapes:

- **Tagging:** content-store entries carry namespace labels; the handler filters by tag. Trade-off: avoids per-namespace tree-binding storage cost; sacrifices tree-visibility of namespace contents.
- **Separate stores:** each namespace backed by a distinct content store partition. Trade-off: clean isolation; loses cross-namespace dedup.

These shapes are conformant to §6.4 namespace-scoping but do NOT compose with the §6.4.2 lookup convention; consumers built against a non-canonical namespace shape lose the `tree:get` probe affordance and must use handler-specific lookup. Deployments choosing alternative shapes SHOULD document their lookup convention for downstream consumers.

#### 6.4.5 Index size — sizing considerations (namespace-scoped topology)

Hash Tree Presence binds one tree entry per content hash per namespace. For deployments where a single hash is published into many namespaces, this is N entries pointing at the same content-store entity (no content duplication; the content store dedups). For deployments with large publication volumes (millions of hashes), the namespace index grows linearly with publication count.

Deployments concerned with index size MAY:

- **Sub-namespace by deployment-specific categorization** to keep any individual prefix probeable in bounded time (`{namespace}/{category}/{hex(H)}`; categorization rule is deployment-defined).
- **Use a non-canonical namespacing shape** per §6.4.4 (Tagging or Separate stores) where the per-entry tree cost is not paid.

The 4 MiB→1 MiB chunk default shift in v3.6 (§3.5) makes typical content land at ~4× chunks per blob, which increases per-blob index entries proportionally if chunks are also bound by namespace presence. Deployments storing chunks under namespaces SHOULD account for this.

---

**Legacy four-options framing (v3.5 reference).** The v3.5 spec listed four impl-defined options (Tagging, Separate stores, Default-everything, Hash Tree Presence). v3.6 promotes Hash Tree Presence to canonical for namespace-scoped topology and reframes Default-everything as the single-trust-domain topology with explicit MUST NOT for multi-party production defaults. The other two options (Tagging, Separate stores) remain informative alternative shapes per §6.4.4.

### 6.5 Security Considerations

The system content handler has a fundamentally different security model from handler-mediated content access (§4):

| | Handler-mediated (§4) | System content handler (§6) |
|--|--|--|
| **Addressing** | Path (via handler URI) | Hash (content store lookup) |
| **Ownership check** | Handler validates blob belongs to its content (§4.4) | None — serves any hash in scope |
| **View tree scoping** | Yes — handler receives capability-scoped tree | No — accesses content store directly |
| **Security model** | Capability + ownership validation | Capability + hash secrecy |

**Hash as access key**: Knowing a content hash does not grant access — a peer must have both the hash AND a valid capability. However, unlike handler-mediated access, there is no ownership validation. A peer with `system/content/*` access can retrieve any entity from the content store, including content managed by other handlers.

**No discovery**: The handler provides no mechanism to enumerate or list hashes. Peers must already know the hashes they want to retrieve. Discovery happens through other channels — blob manifests, handler responses, or out-of-band communication.

**Deployment guidance**:

- **Peers you own**: Grant `system/content/*` for full content store sync between your own machines.
- **Trusted peers**: Grant namespace-scoped access (e.g., `system/content/shared/*`) for selective content sharing.
- **Public/anonymous peers**: Grant only specific namespaces (e.g., `system/content/public/*`) with curated content mappings.
- **Default**: Do not install unless you have a specific use case. Handler-mediated access (§4) is sufficient for normal content delivery.
- **Descriptor publication** (v3.5). Any peer with write access to its own `system/content/descriptor/{B_hex}/...` subtree may publish descriptors for any blob hash. This is by design — the trust model is consumer-side (§5.3 trust model). Deployments that want "verified publisher" semantics layer a `system/attestation` over the descriptor entity using the standard attestation mechanism (EXTENSION-ATTESTATION); a quorum-of-curators policy composes with EXTENSION-QUORUM.
- **Descriptor publication quota** (v3.5). Peers SHOULD apply local quota / rate-limit policies to descriptor publication when storage is bounded; the system content handler's `ingest` capability scoping covers blob ingest but does not cover tree-bound descriptor entities. Storage-bounded deployments hosting public-content catalogues SHOULD set a per-publisher descriptor budget and either rate-limit or hard-cap at the tree-write layer.
- **Drift between handler-aware `media_type` and descriptor `media_type`** (v3.5). Domain handler-mediated entities (`local/files/file`, image-handler entities, dataset-handler entities, etc.) carry their own `media_type` directly on the entity as the handler-aware fast path; the descriptor is for handler-unaware consumers that fetch through the system content handler. When both exist for the same underlying blob (the domain entity carries `media_type: "image/png"` and a separately published descriptor carries `media_type: "image/jpeg"`), the handler-aware consumer SHOULD treat the domain entity's value as authoritative for its own consumption. Handler-unaware consumers see only the descriptor. Cross-checking — when a consumer has access to both — is a consumer-policy decision; the architecture takes no stance. Drift is a deployment concern, not a protocol failure.

### 6.6 Blob and Chunk Lifecycle

Blob and chunk entities live in the content store. Their lifecycle on revision (the referencing entity changes) and deletion (the referencing entity is removed) is governed by the content store's garbage-collection policy. **GC is not a normative protocol extension** — by resolution, GC is locally-implemented operational hygiene rather than a dedicated extension, with cross-extension obligations consolidated in `GUIDE-GC.md`. This spec pins the following retention contract for blob/chunk entities:

1. **Persistence by default.** Implementations SHOULD treat blob and chunk entities as content-store-persistent across referencing-entity revisions. A `local/files/file` entity that is revised to point at a new blob ref MUST NOT cause the old blob's entity to be removed from the content store as a side effect of the revision.
2. **No protocol-level deletion op for content entities.** This spec does not define a `system/content:delete`. Removal of blob or chunk entities is a content-store operation performed by the implementation's local GC mechanism (per `GUIDE-GC.md`) or by an out-of-band administrative tool. Deployments may either (a) accept storage cost (infinite-storage assumption is a valid peer posture per `GUIDE-GC.md §1`), (b) deploy a local cleanup mechanism aligned with the live-set definition in `GUIDE-GC.md §2`, or (c) configure per-extension retention windows (REVISION's `version_retention_window`, HISTORY's `max_depth`, etc.) to bound what stays live.
3. **Reachability roots (informative).** A blob is reachable from this spec's contribution to the live set when: it is referenced by an entity at any path under the peer's tree; it is referenced from any revision-history entry per EXTENSION-REVISION within the configured `version_retention_window`; it is referenced from any in-flight continuation per EXTENSION-CONTINUATION; it is referenced from any in-flight subscription notification payload (§8.1). The full reachability contract (seven live-root categories + transitive ref closure) is in `GUIDE-GC.md §2`; this list is the CONTENT-specific contribution.

Implementations MAY layer their own deletion mechanism for content-store-internal purposes (cache eviction, capacity bounds), provided the mechanism does not surface as a protocol op and does not violate the persistence-by-default rule from (1) above without explicit deployment opt-in.

---

## 7. Content Transfer

### 7.1 Handler-Mediated Transfer

The standard transfer pattern for content owned by a domain handler:

```
transfer_handler_content(remote_peer, handler_uri, metadata_operation, blob_hash):
  ; Step 1: Get the blob manifest (check local content store first)
  blob = content_store.get(blob_hash)
  if blob is null:
    ; Handler MUST include blob in response envelope (§5.2)
    metadata_response = EXECUTE {
      uri: handler_uri
      operation: metadata_operation
    }
    blob = metadata_response.included[blob_hash]

  ; Step 2: Determine which chunks we need
  needed = []
  for chunk_hash in blob.data.chunks:
    if not content_store.has(chunk_hash):
      needed.append(chunk_hash)

  if needed is empty:
    content_store.put(blob_hash, blob)
    return

  ; Step 3: get chunks through the handler
  while needed is not empty:
    batch = needed[0:GET_BATCH_SIZE]
    response = EXECUTE {
      uri: handler_uri
      operation: "get-request"
      params: {blob_hash: blob_hash, hashes: batch}
    }
    for hash in response.result.found:
      chunk = response.included[hash]
      content_store.put(hash, chunk)
      needed.remove(hash)

  ; Step 4: Store the blob locally
  content_store.put(blob_hash, blob)
```

The key difference from a direct content store transfer: all operations go through the domain handler's URI, using the client's existing capability for that handler. No separate content capabilities are needed.

**Streaming chunk fetch (v3.6 — SHOULD when content size ≥ 64 MiB).** For blobs whose `total_size` exceeds 64 MiB, receivers SHOULD batch chunk fetch in bounded windows (`GET_BATCH_SIZE` chunks at a time; recommended initial value 16) and incrementally consume each batch before requesting the next. Streaming chunk fetch keeps receiver-side memory bounded to one batch + the reassembly window; total memory consumption is independent of blob size. This SHOULD be paired with streaming reassembly per DOMAIN-LOCAL-FILES.md v1.3 §5.3 (or equivalent domain-handler-side streaming write) so end-to-end memory bounds hold. SHA-256 supports incremental update at chunk granularity; integrity validation per §3.3 SHOULD use the streaming hash interface.

### 7.2 System Content Transfer

When using the system content handler (§6), transfer uses the handler's `get` operation:

```
transfer_system_content(remote_peer, blob_hash, namespace):
  content_uri = "entity://" + remote_peer + "/system/content"
  if namespace is not null:
    content_uri = content_uri + "/" + namespace

  ; Step 1: Get the blob manifest
  blob = content_store.get(blob_hash)
  if blob is null:
    response = EXECUTE {
      uri: content_uri
      operation: "get"
      params: {hashes: [blob_hash]}
    }
    if blob_hash in response.result.missing:
      return error("blob_not_found")
    blob = response.included[blob_hash]

  ; Step 2: Determine which chunks we need
  needed = []
  for chunk_hash in blob.data.chunks:
    if not content_store.has(chunk_hash):
      needed.append(chunk_hash)

  if needed is empty:
    content_store.put(blob_hash, blob)
    return

  ; Step 3: get missing chunks in batches
  while needed is not empty:
    batch = needed[0:GET_BATCH_SIZE]
    response = EXECUTE {
      uri: content_uri
      operation: "get"
      params: {hashes: batch}
    }
    for hash in response.result.found:
      chunk = response.included[hash]
      content_store.put(hash, chunk)
      needed.remove(hash)

  ; Step 4: Store the blob locally
  content_store.put(blob_hash, blob)
```

**Streaming reassembly (v3.6 — SHOULD when content size ≥ 64 MiB).** Implementations consuming `system/content:get` responses for large blobs SHOULD reassemble via streaming write to the destination (filesystem, downstream handler, etc.) rather than materializing the full byte buffer. The streaming consumer pattern composes naturally with §7.1 streaming chunk fetch: chunk-fetch batches feed a streaming reassembler whose output goes directly to the destination. This closes the "10 GB OOMs the receiver" cliff that DOMAIN-LOCAL-FILES v1.3 Amendment 1 L4 called out.

### 7.3 Resumable Transfer

Transfer is inherently resumable. The receiver checks which chunk hashes it already has in its content store and only getting missing chunks. If transfer is interrupted, the receiver resumes by re-running the transfer algorithm — already-fetched chunks are skipped.

### 7.4 Transfer Rate Control

Content transfer uses a pull-based model — the receiver requests chunks at its own pace. This provides natural back-pressure: a slow receiver simply issues fewer get requests. No explicit flow control protocol is needed.

For batch `get`, the server controls the response size (it respects transport limits and returns what fits). A server under load **MAY** return fewer entities than requested by moving excess to the `missing` list with status 200. The receiver interprets `missing` as "retry later" — there is no distinction between "not found" and "temporarily unavailable" in the batch response. If the server needs to reject outright, it returns status 429 (rate limited) or 503 (service unavailable) as the EXECUTE_RESPONSE status.

Concurrent get requests are an implementation decision. Receivers **MAY** issue multiple get requests in parallel for throughput, but **SHOULD** limit concurrency to avoid overwhelming the server. A recommended starting point is 4 concurrent requests, adjustable based on response latency.

**Transport-aware batching responsibility split (v3.6+).** Sender-side (the requesting peer's `system/content:get` caller — typically driven by `content.EnsureClosure` per the SDK-EXTENSION-OPERATIONS content extension §X) **SHOULD** implement `GET_BATCH_SIZE`-windowed batching per §7.1 (recommended initial value 16; tunable per deployment). Receiver-side (the handler serving `system/content:get`) **MUST** respect the connection's configured frame budget per §6.2. **The two responsibilities are independent:** a receiver that respects frame limits does not relieve senders of streaming-window discipline (memory-bounded fetch on the requesting side); a sender that batches does not relieve receivers of frame-budget discipline (the receiver's response chunking is per-request and budget-aware regardless of how the request was batched). Implementations conform when both surfaces respect their respective discipline.

---

## 8. Integration with Other Extensions

### 8.1 Subscription Notifications

When a subscription notification fires for an entity that references content (via blob ref), the notification carries the entity's metadata — not the content. The subscriber receiving the notification can:

1. Check the `included` map for the referenced entity
2. Extract the blob hash from the entity's refs
3. Transfer the content using the appropriate transfer pattern (§7.1 or §7.2)

The subscription extension's entity inclusion strategy (EXTENSION-SUBSCRIPTION.md §4.4) applies to the metadata entity, not to the blob or chunks. Content transfer is always a separate operation.

### 8.2 Inbox Delivery

Inbox deliveries (EXTENSION-INBOX.md) that produce large results **SHOULD** store the result as content and deliver a reference rather than inlining large payloads in the delivery params. The delivery carries the content ref (a `system/hash` pointing at a `system/content/blob`); the recipient resolves the ref through the handler-mediated transfer pattern (§7.1) or the system content handler (§7.2) as appropriate.

(EXTENSION-CALLBACK was retired in favor of EXTENSION-INBOX; the spec lives in `specs/deprecated/` for historical reference only.)

### 8.3 Large Structured Entities

Content chunking is designed for binary payloads — files, media, datasets — things that are inherently large and opaque. A structured entity with a large `data` field is a different problem: it typically indicates a design issue rather than a transfer issue.

**Primary guidance**: Entity types **SHOULD** be designed so that `data` stays small and large payloads are referenced via content blobs (§5.1). A file entity carries metadata in `data` (name, size, timestamps — small) and references the content via a blob ref (large). This decomposition is the standard pattern and should be applied to any entity type that might grow large.

**Edge cases**: In rare situations (migration, bulk replication, legacy compatibility), a large structured entity may need to be transferred intact. The content extension's chunking mechanism can be used for this — serialize the entity to bytes, create a content blob, transfer, reconstruct:

```
transfer_large_entity(entity):
  entity_bytes = ecf_encode(entity)
  blob_hash = create_blob(entity_bytes, DEFAULT_CHUNK_SIZE)
  ; Transfer via content chunking (§7)
  ; Receiver: raw_bytes → ecf_decode → entity → validate entity hash
```

This is an escape hatch. If an entity type regularly produces large entities, the type **SHOULD** be redesigned to use content refs rather than relying on serialization-based transfer.

---

## 9. Wire Efficiency

Each chunk is transferred as a full entity in an envelope. The per-chunk wire overhead includes:

| Component | Approximate Size |
|-----------|-----------------|
| Envelope framing (4-byte length prefix) | 4 bytes |
| CBOR envelope structure | ~50 bytes |
| Entity type and structure | ~80 bytes |
| Entity hash (ecfv1-sha256) | ~80 bytes |
| CBOR binary payload overhead | ~10 bytes |
| **Total per-chunk overhead** | **~224 bytes** |

For a 1 MiB chunk: ~1 MiB + ~224 bytes → ~1.0 MiB on wire. Per-chunk overhead is ~0.02%.

At this size, multiple chunks fit within a typical batch `get` response. Individual chunk requests are one chunk per response, which is the expected baseline. CBOR binary encoding (major type 2) carries raw bytes directly — no base64 expansion or encoding overhead.

**Hashing cost per chunk**: The receiver validates the chunk entity hash — one SHA-256 over the ECF-encoded chunk (~1 MiB). Per the envelope transport optimization (ENTITY-CORE-PROTOCOL.md §3.1), the envelope's own content_hash is not validated on the wire, avoiding a redundant O(message_size) hash per frame. Total hashing for a 1 GiB transfer: ~2 GiB of SHA-256 (1 GiB for per-chunk entity hashes on create, ~1 GiB for per-chunk validation on receipt). There is no separate content hash — entity hashing is the only hashing layer.

---

## 10. Constants

### 10.1 Chunk Size

| Constant | Value | Description |
|----------|-------|-------------|
| `DEFAULT_CHUNK_SIZE` | 1,048,576 (1 MiB) | Recommended default target chunk size (§3.5) |
| `MIN_CHUNK_SIZE` | 65,536 (64 KiB) | Protocol minimum — no chunk may be smaller (except the final chunk of a blob) |
| `MAX_CHUNK_SIZE` | 8,388,608 (8 MiB) | Recommended maximum chunk size |

These are protocol-level constraints, independent of the chunking algorithm's internal parameters. For example, FastCDC's `min_size` (§3.6.2) is `target_size / 4` = 256 KiB at the default target — well above `MIN_CHUNK_SIZE`.

### 10.2 Transfer

| Constant | Value | Description |
|----------|-------|-------------|
| `GET_BATCH_SIZE` | 16 | Recommended sender-side batching window — hashes per get request (§7.1) |

### 10.3 Handler Operations

| Operation | Handler | Description |
|-----------|---------|-------------|
| `get` | `system/content/*` (optional) | Retrieve entities by hash from content store (§6.2) |
| `ingest` | `system/content/*` (optional) | Chunk and store bytes, returning the blob hash (§6.3) |

This table enumerates the operations the `system/content` handler declares in its §6.1 manifest. Both are optional in the sense that the whole handler is optional (§11.3); when the handler **is** installed, both are declared and `ingest` carries the §11.1 `root` MUST.

---

## 11. Conformance

### 11.1 MUST Implement

- Content blob type (`system/content/blob`) — creation and parsing (§2.1)
- Content chunk type (`system/content/chunk`) — creation and parsing (§2.2)
- Content creation algorithm — fixed-size (§3.2) or FastCDC (§3.6)
- Content entities stored in content store, not entity tree (§3.1)
- Content verification — completeness and size consistency (§3.3)
- Handlers returning content refs **MUST** include the blob entity in the response envelope (§5.2)
- Handlers serving content **MUST** validate blob ownership and chunk membership on get-request (§4.4)
- `content:ingest` result **MUST** include `root` when called in envelope mode with non-null `envelope.root` (§6.3)

### 11.2 SHOULD Implement

- FastCDC content-defined chunking with the specified gear table and parameters (§3.6)
- Chunk sizes that fit within the transport's frame limit when one exists (§10.1)
- Handler content get operation for handlers that serve binary content (§4.2)
- Small content optimization — include chunks in metadata response when they fit (§4.3)
- Resumable transfer (§7.3)
- Default target chunk size of 1 MiB (§3.5, §10.1)
- CBOR binary encoding for chunk payloads (§2.2)

### 11.3 MAY Implement

- System content handler at `system/content/*` (§6)
- System content `ingest` operation (§6.3) — SHOULD be supported when system content handler is installed
- System content namespace scoping (§6.4)
- Fixed-size chunking as alternative to FastCDC (§3.2)
- Alternative target chunk sizes based on content size (§3.5)
- Local re-chunking after transfer (receiver re-chunks to preferred chunk size)

### 11.4 Implementation-Defined

- Chunk size selection strategy
- Transfer parallelism (concurrent chunk gets)
- Handler blob ownership check mechanism (§4.4 Step 1)
- Namespace-to-content mapping strategy when using system content handler (§6.4)
- Storage backend for chunks and blobs
- Cache eviction policy for chunk entities
- Re-chunking policy after transfer

---

## 12. Document history

| Version | Date | Change |
|---|---|---|
| 3.6 Amendment 3 | — | **§6.6 GC reframe — wording only, no impl change.** EXTENSION-GC was retired (no extension; see `proposals/deferred/PROPOSAL-EXTENSION-GC.md` for the structural argument and `GUIDE-GC.md` for the resolution). §6.6 narrative updated: the persistence-by-default + no-delete-op + reachability-roots contract is unchanged in semantics; only the deferral pointer "pending EXTENSION-GC" replaced by a reference to GUIDE-GC. Proposal-first proportionality — wording-only spec hygiene, no impl-impact, version-bump with changelog row. |
| 3.6 Amendment 2 | — | **§6.2 partial-sync sidecar resolution** (Go post-landing audit Finding 2; Python flagged; three-impl convergence on bare-hash `missing` wire shape ratified). The earlier §6.2 partial-sync paragraph was internally contradictory: said entries MAY carry per-entry `pending` annotation but also said "does not change the `missing` list shape" — incompatible. Amendment 2 retracts the per-entry dict form (non-conformant) and lands the **sidecar form**: response gains a separate optional `pending: array_of system/hash` field that's a subset of `missing` exposing the sync-state-visibility predicate; `missing` stays `array_of system/hash` per v3.6 §6.2 spec-literal-arrays contract. Zero impl changes (all three already emit bare-hash `missing`); ratifies the convergent reality + adds a clean sidecar surface for sync-state-visibility consumers. From the Go post-landing materialization audit, Finding 2 (Direction A — Go's lean). |
| 3.6 Amendment 1 | — | **F8 spec touch landed** (paired with the content-materialization-first-class change, Amendment D). §6.2 + §4.2 frame-budget MUST clarified — implementations consult the connection's **configured** frame budget per V7 §1.6, not a hardcoded 16 MiB literal (per Rust's pin). New `system/content/frame-limit-respected` validate-peer behavioral check pinned at both surfaces (handler-mediated §4.2 + system content handler §6.2). §7.4 new "Transport-aware batching responsibility split" paragraph naming sender-side `GET_BATCH_SIZE`-windowed batching SHOULD (per §7.1; recommended 16) + receiver-side frame-budget MUST as independent responsibilities. Cross-impl audit: Go non-conformant at `ext/content/handler.go:115-168`; Rust non-conformant at `extensions/content/src/handler.rs:73-85`; Python non-conformant (same shape). Impl fix ~30–80 LOC per impl bundled with §7.1 sender-side batching addition (~30 LOC). F5 already landed in v3.6 A6; workbench's fold-in note captured (no additional spec text needed). |
| 3.6 | — | **Six amendments landed** + two paired amendments in companion specs per `proposals/PROPOSAL-EXTENSION-CONTENT-V3.6.md`. **A1**: §6.4 restructured — two deployment topologies named (namespace-scoped = production default, MUST for multi-party; single-trust-domain = opt-in restricted-use, MUST NOT be production multi-party default); §6.4.2 Hash Tree Presence canonical for namespace-scoped (bind `{namespace}/{hex(H)}` in tree; `tree:get` is the O(1) lookup primitive); §6.4.3 cap-matrix (tree:get grant = listable index; system/content:get grant = probe-only; combination = full read; cross-product = privacy/discoverability spectrum); §6.4.4 alternative shapes (Tagging, Separate stores) demoted to informative; §6.4.5 index-sizing considerations. **A2**: §3.5 chunk default 4 MiB → 1 MiB per industry CDC centroid (Borg/restic/casync). §3.6.2 FastCDC parameter table updated for 1 MiB target. Existing 4 MiB deployments remain conformant per migration note; **paired DOMAIN-LOCAL-FILES v1.3 Amendment 3 (§5.5 circuit-breaker chunk_size fix) is hard prerequisite for cutover safety**; sibling lock-step coordination SHOULD per §3.5 migration note. **A3**: §1.3 + §3.6 strengthened normative convergence language — diverging from canonical FastCDC parameters drops the implementation out of the cross-peer dedup system explicitly. **A4**: §7.1 + §7.2 streaming wire ingest + streaming reassembly SHOULD ≥64 MiB (companion to DOMAIN-LOCAL-FILES v1.3 L4 promotion; `GET_BATCH_SIZE=16` initial; bounded receiver memory). **A5**: §6.2 spec-literal arrays for `found`/`missing` reaffirmed + envelope-`Included` entity-delivery contract pinned (per V7 §3.3 v7.51 envelope-`included` preservation; F4 three-way cross-impl audit: 2-of-3 spec-literal-arrays + Python pushback on Go hybrid; Go fixes ~10–15 LOC). **A6**: §6.2 default-namespace cross-reference (`system/content` for default-handler dispatches; F5 SDK-author clarity). §3.4 architectural-note updated to point at §6.4 as the substrate-side answer for `system/content` cap discipline. **PAIRED:** DOMAIN-LOCAL-FILES v1.3 Amendment 3 (§5.5 circuit-breaker recompute MUST use incoming blob's `chunk_size`); GUIDE-EXTENSION-DEVELOPMENT §9.1 convergence-angle-diversity meta-note. v3 reframe per user direction: default-permissions-to-everything-as-default is a security defect, not a topology option. |
| 3.5 | — | **Nine amendments landed.** **A1**: new `system/content/descriptor` entity type (§2.4) + dual-level invariant-pointer path convention (§5.3) with MUST integrity check. **A2**: §1.2 / §2.3 / §6 / §6.5 updated naming the descriptor as the public-content interpretation surface; §6.5 also gains descriptor-publication-quota and `media_type`-drift deployment guidance (Go O4/Q2). **A3**: new §3.7 algorithm classification table per V7 §7. **A4**: new §3.6.5 conformance vector surfaces — high-level naming only; vectors a Stage-4 byproduct. **A5**: path-as-resource for hash-addressed ops `get` / `ingest` (§6.2 / §6.3 normative; namespace path is the cap-scope resource; missing resource MUST return `path_required`); §6.3 carries the explicit v3.4 → v3.5 behavior-change callout. **A6**: op-naming discipline pass on `get-request` (§4.2) — full handler URI in normative prose. **A7**: §4.3 small-content inline-included threshold pinned at 64 KiB (= `MIN_CHUNK_SIZE`); pseudocode predicate updated. **A8**: new §6.6 blob/chunk lifecycle on revision/deletion — deferred to EXTENSION-GC; persistence-by-default interim guidance. **A9** (companion): `GUIDE-EXTENSION-DEVELOPMENT.md` new §3.5 "Paths are convention; the entity graph is coherence" — landed in the same round; CONTENT v3.5 §5.3 and TYPE v1.1 §1.4/§1.5 are the worked examples. Paper-team feedback on the content descriptor and the Go review of the CONTENT/TYPE proposals were both absorbed. |
| 3.4 | — | `system/content/ingest-result` carries the original `envelope.root` entity inline in envelope mode (new optional `root` field; MUST when `system/content:ingest` is supported). Enables continuation chains over wrapped-envelope responses (e.g., `revision/fetch → content:ingest → revision/merge`) without per-handler `source_envelope` proliferation. Additive on the wire — existing callers reading only `root_hash`/`ingested_count` are unaffected. Per `proposals/implemented/PROPOSAL-CONTENT-INGEST-PASS-THROUGH.md` (C1). |
| 3.3 | — | Baseline at draft. Blob+chunk types, FastCDC §3.6, handler-mediated access pattern §4, optional system content handler §6, transfer patterns §7. |

**Hygiene pass:** Header reformatted to `GUIDE-EXTENSION-DEVELOPMENT.md` §3.3 shape (added Used-by, Owned namespaces, Owned ops, Owned entity types, Extension points exposed/consumed); conformance grade added per GUIDE §9 (Draft); V7 dependency floor bumped v7.3+ → v7.51+ (the floor v3.4 actually requires); §8.2 stale reference to retired `EXTENSION-CALLBACK` replaced with `EXTENSION-INBOX`. No normative change. Source: review against the GUIDE-EXTENSION-DEVELOPMENT initial draft.
