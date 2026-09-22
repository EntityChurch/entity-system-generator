//! HISTORY — the six owned entity types (§9.2, defined at §2.1–§2.4 and §4.3.2).
//!
//! **This is the face that installs on this peer**, and it is the only one the oracle
//! can see. `Store::bind` is public; the handler container is not. So the six
//! `type_*` checks in `validate-peer -category history` are the whole of what a
//! third party measures about this port, and everything else this crate does is
//! measured by instruments that are ours.
//!
//! The field maps are hand-built, exactly as `../content/src/types.rs`'s are and for
//! the same compile-enforced reason: `FSpec`, `fref`, `opt`, `farray` and `TypeDef` in
//! `peer::type_defs` carry no `pub`, so the peer's own builder is invisible across the
//! crate boundary. `typescript` renders these through the peer's `TypeDef`; `python`
//! and this port cannot.
//!
//! That lands on the one surface where a mistake is silent. A subtly wrong field map
//! produces a well-formed entity that hashes differently from every other
//! implementation's, and nothing raises an error anywhere — the entity is simply not
//! the same entity. **Unlike CONTENT, there is no `type_system` category check that
//! compares a HISTORY type against the oracle's own transcription**: `validate-peer`'s
//! `history` category asserts only that the six paths RESOLVE (`history.go:120-129`,
//! `client.TreeGet` and nothing more). So the cross-port defence here is
//! `tests/types.rs`, which asserts the three ports render the same bytes — ours, not
//! an oracle's, and recorded as such.

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

// ── type-path constants, FLAT. One home for every literal the module binds. ──
//
// FLAT IS THE CONTRACT, in every port, and that was decided rather than inherited.
// CONTENT shipped these bundled into a `ContentTypes` object in `typescript` and flat
// in `python`/`rust`, and `tools/sdk-parity.py`'s first run reported eight names of
// drift from that one choice made once and never made again. HISTORY started down the
// identical path and the gate caught it at the second port (D16).

/// §2.1 — the transition entity. The audit record itself.
pub const TRANSITION: &str = "system/history/transition";
/// §2.2 — per-path-pattern configuration.
pub const CONFIG: &str = "system/history/config";
/// §2.3
pub const QUERY_PARAMS: &str = "system/history/query-params";
/// §2.4
pub const QUERY_RESULT: &str = "system/history/query-result";
/// §4.3.2
pub const ROLLBACK_PARAMS: &str = "system/history/rollback-params";
/// §4.3.2
pub const ROLLBACK_RESULT: &str = "system/history/rollback-result";

/// §9.2's six, in the spec's listed order.
pub const ALL_TYPES: [&str; 6] = [
    TRANSITION,
    CONFIG,
    QUERY_PARAMS,
    QUERY_RESULT,
    ROLLBACK_PARAMS,
    ROLLBACK_RESULT,
];

/// The handler pattern (§4.1). Everything the module would bind derives from this.
///
/// It is a constant on this port even though nothing can be bound at it, because
/// `tests/handler.rs` drives the body directly and the §4.2 dual check names it.
pub const HISTORY_PATTERN: &str = "system/history";

/// §3.1 — the head-pointer prefix, and §3.2's self-guard subject.
///
/// These are the SAME STRING and that is load-bearing: §3.2's guard targets
/// `system/history/head`, which is exactly the prefix this module writes to, and it is
/// deliberately NARROWER than `system/history/`. §3.2 says config paths "are
/// handler-written via explicit EXECUTE and do not create recursion risk — they SHOULD
/// be recorded as normal transitions for audit purposes." A constant named
/// `HISTORY_NAMESPACE` would be the wrong thing to guard on, so there is not one.
pub const HEAD_PREFIX: &str = "system/history/head";

/// §6.1 — where configurations live. NOT self-guarded; see above.
pub const CONFIG_PREFIX: &str = "system/history/config";

// ── §2.1's event vocabulary. Four values; `accessed` is the MAY (§9.1). ──────
//
// THESE ARE NOT THE CORE'S STRINGS. The peer's emit pathway derives
// `created | modified | deleted` (`store.rs:35`); §2.1's table says
// `created | updated | deleted | accessed`. See [`from_core_event_type`].

pub const EVENT_CREATED: &str = "created";
pub const EVENT_UPDATED: &str = "updated";
pub const EVENT_DELETED: &str = "deleted";
pub const EVENT_ACCESSED: &str = "accessed";

/// §2.2 "Default events". `accessed` is opt-in and no composition records it — see
/// `EXTENSION.toml [substrate.accessed_event]` for why it is not reachable at all.
pub const DEFAULT_EVENTS: [&str; 3] = [EVENT_CREATED, EVENT_UPDATED, EVENT_DELETED];

/// §2.3 — "Maximum transitions to return. Default: 50".
pub const DEFAULT_QUERY_LIMIT: u64 = 50;

/// Map a core tree-change `event_type` onto §2.1's vocabulary.
///
/// The ONLY difference is `modified` → `updated`. Returning `None` for anything else
/// is deliberate: an unrecognised core event is never silently recorded as some nearest
/// neighbour, because the event string is a field of a content-addressed entity and a
/// wrong value there is a wrong hash forever.
pub fn from_core_event_type(core_event_type: &str) -> Option<&'static str> {
    match core_event_type {
        "created" => Some(EVENT_CREATED),
        "modified" => Some(EVENT_UPDATED),
        "deleted" => Some(EVENT_DELETED),
        _ => None,
    }
}

// ── field-spec builders (omit-empty; the ECF §1.3 absent-key convention) ─────
//
// Deliberately the same four shapes as `../content/src/types.rs`, `../../python/
// extensions/history/types.py` and the peer's own private `FSpec::to_data`, so the set
// can be diffed line by line. The codec re-sorts map keys length-then-lex, so
// declaration order here is irrelevant to the bytes — only the key/value set matters.

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
/// it. Wrapping would be the natural Rust reflex and would produce a different map and
/// therefore a different hash.
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

/// The six definitions, in §9.2's listed order.
///
/// Field order inside a definition does NOT affect the rendered bytes, but it follows
/// the spec's tables so a reader can diff this against §2.1 line by line — and against
/// `../../typescript/extensions/history/types.ts` and
/// `../../python/extensions/history/types.py`, which are the same list in the other two
/// languages.
pub fn history_type_defs() -> Vec<(&'static str, Value)> {
    vec![
        // §2.1 — the transition. Fourteen fields, and the two that carry §9.1's MUST
        // are `author` and `capability`.
        //
        // `provenance` IS NOT HERE. It is ours, not the spec's, and adding a field to a
        // spec-declared type would move this entity's content hash away from every
        // other implementation's — the silent cross-impl break the CONTENT work was
        // about. It is carried out of band; see `internal/recorder.rs`.
        (
            TRANSITION,
            type_def(
                TRANSITION,
                vec![
                    ("path", fref("system/tree/path")),
                    ("event", fref("primitive/string")),
                    ("hash", opt(fref("system/hash"))),
                    ("previous_hash", opt(fref("system/hash"))),
                    ("author", fref("system/hash")),
                    ("capability", fref("system/hash")),
                    ("caller_capability", opt(fref("system/hash"))),
                    ("handler", fref("system/tree/path")),
                    ("operation", fref("primitive/string")),
                    ("timestamp", fref("primitive/uint")),
                    ("clock", opt(fref("system/clock/state"))),
                    ("chain_id", opt(fref("primitive/string"))),
                    ("parent_chain_id", opt(fref("primitive/string"))),
                    ("previous", opt(fref("system/hash"))),
                ],
            ),
        ),
        // §2.2 — per-path-pattern configuration.
        (
            CONFIG,
            type_def(
                CONFIG,
                vec![
                    ("pattern", fref("system/tree/path")),
                    ("enabled", fref("primitive/bool")),
                    ("events", opt(farray(fref("primitive/string")))),
                    ("max_depth", opt(fref("primitive/uint"))),
                ],
            ),
        ),
        // §2.3
        (
            QUERY_PARAMS,
            type_def(
                QUERY_PARAMS,
                vec![
                    ("path", fref("system/tree/path")),
                    ("limit", opt(fref("primitive/uint"))),
                    ("since", opt(fref("system/hash"))),
                    ("before", opt(fref("primitive/uint"))),
                    ("events", opt(farray(fref("primitive/string")))),
                ],
            ),
        ),
        // §2.4 — `transitions` is an array of the TRANSITIONS, not of hashes. Which
        // form goes on the wire is settled by the oracle rather than by §2.4; see
        // `handler.rs`.
        (
            QUERY_RESULT,
            type_def(
                QUERY_RESULT,
                vec![
                    ("path", fref("system/tree/path")),
                    ("head", opt(fref("system/hash"))),
                    ("transitions", farray(fref(TRANSITION))),
                    ("has_more", fref("primitive/bool")),
                ],
            ),
        ),
        // §4.3.2
        (
            ROLLBACK_PARAMS,
            type_def(
                ROLLBACK_PARAMS,
                vec![
                    ("path", fref("system/tree/path")),
                    ("target_hash", fref("system/hash")),
                ],
            ),
        ),
        (
            ROLLBACK_RESULT,
            type_def(
                ROLLBACK_RESULT,
                vec![
                    ("path", fref("system/tree/path")),
                    ("restored", fref("system/hash")),
                ],
            ),
        ),
    ]
}

/// Materialize each definition as a `system/type` entity.
pub fn history_type_entities() -> Vec<(&'static str, Entity)> {
    history_type_defs()
        .into_iter()
        .map(|(name, data)| (name, Entity::make("system/type", data)))
        .collect()
}

/// Bind the six type entities into a peer's tree at `system/type/{name}`.
///
/// I1 (owned-namespace containment) holds structurally: every path is `system/type/`
/// plus a name from [`ALL_TYPES`], and `system/type/*` is the core's shared type index
/// every extension writes into by design.
///
/// Takes a `&Store` rather than a peer, matching `../content`: the caller already holds
/// `peer.store`, and passing the peer would imply this function might use more of it.
pub fn publish_history_types(store: &Store, local_peer: &str) -> Vec<String> {
    let mut written = Vec::new();
    for (name, entity) in history_type_entities() {
        let path = format!("/{local_peer}/system/type/{name}");
        store.bind(&path, &entity);
        written.push(path);
    }
    written
}

/// Build one of our own entities without reaching for `Entity::make` at each site.
///
/// Present in all three ports (`historyEntity` / `history_entity`) and `required` in
/// `[sdk_surface]`, so it is here even though this port has two call sites for it.
pub fn history_entity(typ: &str, data: Value) -> Entity {
    Entity::make(typ, data)
}
