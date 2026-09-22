//! CONTENT — the seven owned entity types (§2.1, §2.2, §2.4, §6.2, §6.3).
//!
//! **Third port, third answer on the same axis, and this one is enforced.**
//!
//! The `typescript` port renders its type entities through the peer's own `TypeDef` /
//! `FSpec` builder, because the blob and chunk hashes ARE the deduplication identity
//! (§2.1) and reusing the peer's encoder removes one way to disagree. `python` could
//! not: its equivalents are leading-underscore, and we declined to import them because
//! an underscore is that peer's statement about its own boundary.
//!
//! **Here it is not a statement, it is a compile error.** `FSpec`, `fref`, `opt`,
//! `farray` and `TypeDef` in `peer::type_defs` carry no `pub`, so they are invisible
//! across the crate boundary. Only `core_type_count()` and `publish()` are public, and
//! `publish()` writes the 53-type core floor — extension vocabularies are explicitly
//! out of its scope (its own module doc says so). The field maps below are therefore
//! hand-built, exactly as `python`'s are, and for a materially stronger reason.
//!
//! That lands on the one surface where a mistake is silent: nothing in this module
//! fails if a field map is subtly wrong. The entity simply hashes differently from
//! every other implementation's, dedup stops for that type, and no error is raised
//! anywhere.
//!
//! **What catches it is not in this file and is not ours.** It is `validate-peer`'s
//! `type_system.type_system_content_{blob,chunk,descriptor}_match`, which renders the
//! same three types from `entity-core-go`'s own independent transcription and compares
//! content hashes. That check is the reason this port can be hand-built at all — and
//! it is the one conformance claim this substrate CAN make, because publishing a type
//! entity is `store.bind`, which is public, while installing a handler body is not.

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

// ── type-path constants. One home for every literal the module binds or emits. ──

pub const BLOB: &str = "system/content/blob";
pub const CHUNK: &str = "system/content/chunk";
pub const DESCRIPTOR: &str = "system/content/descriptor";
pub const GET_REQUEST: &str = "system/content/get-request";
pub const CONTENT_RESPONSE: &str = "system/content/content-response";
pub const INGEST_REQUEST: &str = "system/content/ingest-request";
pub const INGEST_RESULT: &str = "system/content/ingest-result";

pub const ALL_TYPES: [&str; 7] = [
    BLOB,
    CHUNK,
    DESCRIPTOR,
    GET_REQUEST,
    CONTENT_RESPONSE,
    INGEST_REQUEST,
    INGEST_RESULT,
];

/// The handler pattern (§6.1). Everything the module binds derives from this.
pub const CONTENT_PATTERN: &str = "system/content";

/// §10.1. v3.6 reconciled every site to 1 MiB; the v3.5 4 MiB reading is dead.
pub const DEFAULT_CHUNK_SIZE: usize = 1_048_576;
pub const MIN_CHUNK_SIZE: usize = 65_536;
pub const MAX_CHUNK_SIZE: usize = 8_388_608;

/// §10.2 — the sender-side batching window, hashes per get request (§7.1).
pub const GET_BATCH_SIZE: usize = 16;

/// §2.1 standardized `chunking` configuration identifiers.
pub const CHUNKING_FIXED: u64 = 0;
pub const CHUNKING_FASTCDC_NC2: u64 = 1;

// ── field-spec builders (omit-empty; the ECF §1.3 absent-key convention) ──────
//
// Deliberately the same four shapes as `../python/types.py` and the peer's own
// private `FSpec::to_data`, so the three can be diffed line by line. The codec
// re-sorts map keys length-then-lex, so declaration order here is irrelevant to the
// bytes -- only the present key/value set matters.

fn map_of(pairs: Vec<(&str, Value)>) -> Value {
    Value::Map(
        pairs
            .into_iter()
            .map(|(k, v)| (Key::Text(k.to_string()), v))
            .collect(),
    )
}

fn fref(t: &str) -> Value {
    map_of(vec![("type_ref", Value::Text(t.to_string()))])
}

/// Optional is rendered by ADDING `optional: true` to the inner spec, not by wrapping
/// it. Wrapping would be the natural Rust reflex (`Optional(Box<FSpec>)` in the peer's
/// own enum) and would produce a different map and therefore a different hash.
fn opt(inner: Value) -> Value {
    match inner {
        Value::Map(mut entries) => {
            entries.push((Key::Text("optional".into()), Value::Bool(true)));
            Value::Map(entries)
        }
        other => other,
    }
}

fn farray(elem: Value) -> Value {
    map_of(vec![("array_of", elem)])
}

/// Render a `system/type` data map. Omit-empty: a type with no fields carries no
/// `fields` key at all.
fn type_def(name: &str, fields: Vec<(&str, Value)>) -> Value {
    let mut pairs: Vec<(Key, Value)> =
        vec![(Key::Text("name".into()), Value::Text(name.to_string()))];
    if !fields.is_empty() {
        pairs.push((
            Key::Text("fields".into()),
            Value::Map(
                fields
                    .into_iter()
                    .map(|(k, v)| (Key::Text(k.to_string()), v))
                    .collect(),
            ),
        ));
    }
    Value::Map(pairs)
}

/// The seven definitions, in the order §11.1 ranks them: the two MUSTs first.
///
/// Field order inside a definition does NOT affect the rendered bytes, but it is kept
/// in spec order so a reader can diff this against §2.1 / §2.4 / §6.2 / §6.3 line by
/// line — and against `../python/types.py` and `../typescript/types.ts`, which are the
/// same list in the other two languages.
pub fn content_type_defs() -> Vec<(&'static str, Value)> {
    vec![
        // §2.1 — the chunk-list manifest. All four fields structural; no metadata,
        // ever (§2.3: an optional `content_type` here would split the dedup identity).
        (
            BLOB,
            type_def(
                BLOB,
                vec![
                    ("total_size", fref("primitive/uint")),
                    ("chunk_size", fref("primitive/uint")),
                    ("chunking", fref("primitive/uint")),
                    ("chunks", farray(fref("system/hash"))),
                ],
            ),
        ),
        // §2.2 — one field, and the absence of the others is the point: no sequence
        // number, no parent ref, so identical bytes hash identically across blobs.
        (
            CHUNK,
            type_def(CHUNK, vec![("payload", fref("primitive/bytes"))]),
        ),
        // §2.4 — a consumption-format DECLARATION, not an attestation. §2.4's presence
        // rule (at least one of media_type / type_ref) is a validity constraint the
        // type system cannot express, so it is enforced in `sdk.rs` where the
        // descriptor is built, not here.
        (
            DESCRIPTOR,
            type_def(
                DESCRIPTOR,
                vec![
                    ("content", fref("system/hash")),
                    ("media_type", opt(fref("primitive/string"))),
                    ("type_ref", opt(fref("system/hash"))),
                    ("name", opt(fref("primitive/string"))),
                    ("metadata", opt(fref("primitive/any"))),
                ],
            ),
        ),
        // §6.2 request/response.
        (
            GET_REQUEST,
            type_def(GET_REQUEST, vec![("hashes", farray(fref("system/hash")))]),
        ),
        // §6.2 + Amendment 2. `found` / `missing` are ARRAYS, not counters — the F4
        // cross-impl audit landing, and the one wire-shape mistake this response has
        // already made once. `pending` is the OPTIONAL sync-state sidecar; the field
        // is declared because the type is the wire contract, and separately not
        // emitted (see `handler.rs`).
        (
            CONTENT_RESPONSE,
            type_def(
                CONTENT_RESPONSE,
                vec![
                    ("found", farray(fref("system/hash"))),
                    ("missing", farray(fref("system/hash"))),
                    ("pending", opt(farray(fref("system/hash")))),
                ],
            ),
        ),
        // §6.3 — exactly one of envelope / entity. Both optional in the type; the
        // exclusivity is a handler-level 400, per the §6.3 algorithm.
        (
            INGEST_REQUEST,
            type_def(
                INGEST_REQUEST,
                vec![
                    ("envelope", opt(fref("system/envelope"))),
                    ("entity", opt(fref("core/entity"))),
                ],
            ),
        ),
        // §6.3 + §11.1 MUST: `root` is present in envelope mode and absent in entity
        // mode, which is exactly what `optional` encodes under the §1.3 absent-key rule.
        (
            INGEST_RESULT,
            type_def(
                INGEST_RESULT,
                vec![
                    ("root", opt(fref("core/entity"))),
                    ("root_hash", fref("system/hash")),
                    ("ingested_count", fref("primitive/uint")),
                ],
            ),
        ),
    ]
}

/// Materialize each definition as a `system/type` entity.
pub fn content_type_entities() -> Vec<(&'static str, Entity)> {
    content_type_defs()
        .into_iter()
        .map(|(name, data)| (name, Entity::make("system/type", data)))
        .collect()
}

/// Bind the type entities into a peer's tree at `system/type/{name}`.
///
/// **This is the one install face that works on this substrate**, and it is worth
/// stating why rather than leaving it as an accident of what happened to compile:
/// publishing a type is a tree write, `Store::bind` is public, and nothing about it
/// needs a dispatch-path hook. Installing a handler BODY needs one and there is none
/// (`gates/host-seam/rust`, scenario 1). The two faces of one extension get two
/// different answers on one peer.
///
/// Takes a `&Store` rather than a peer, because unlike the other two ports there is no
/// second thing to reach for: the caller already holds `peer.store` and passing the
/// peer would imply this function might use more of it.
pub fn publish_content_types(store: &Store, local_peer: &str) -> Vec<String> {
    let mut written = Vec::new();
    for (name, entity) in content_type_entities() {
        let path = format!("/{local_peer}/system/type/{name}");
        store.bind(&path, &entity);
        written.push(path);
    }
    written
}
