//! COMPUTE — the 33 owned entity types (§2.1–§2.6 and §3.5), for the `rust` peer.
//!
//! **This is one of the two faces that install on this peer**, and it is the one with a real
//! cross-implementation oracle. 63 `type_system.type_compute_*_match` checks in
//! `entity-core-go` compare each published type entity's content hash against that
//! codebase's OWN transcription of the same §2.x block, and `make type-parity` compares all
//! three ports by hash and by field map. So a wrong field map here does not hide: it fails a
//! named check.
//!
//! The field maps are hand-built for the same compile-enforced reason as `../content` and
//! `../history`: `FSpec`, `fref`, `opt`, `farray` and `TypeDef` in `peer::type_defs` carry no
//! `pub`, so the peer's own builder is invisible across the crate boundary.
//!
//! THE THREE DECLARED DEVIATIONS are the other two ports', re-derived from the spec rather
//! than copied (L18):
//!
//!  1. **§2.1 says "Seven primitive expression types" and defines EIGHT.** All eight are here.
//!  2. **`system/compute/subgraph` gets SEVEN fields, not §2.5's six.** §3.3 Phase 3 writes
//!     `authorized_data_hashes`, §4.2 reads it, §1.1 names it load-bearing, §10.1 MUSTs it.
//!  3. **Both membership predicates carry all sixteen expression types.** §4.7's list has
//!     thirteen and §4.2's has twenty; both omit `compute/index`, `compute/length` and
//!     `compute/numeric-cast`. See [`is_compute_type`].
//!
//! All three are routed (`ROUTING-2026-09-09-d-arch-*`, `ROUTING-2026-09-10-arch-*`).

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

// ── §2.1 core expression types — EIGHT, not the seven §2.1's prose says ────────────
pub const LITERAL: &str = "compute/literal";
pub const LOOKUP_SCOPE: &str = "compute/lookup/scope";
pub const LOOKUP_TREE: &str = "compute/lookup/tree";
pub const LOOKUP_HASH: &str = "compute/lookup/hash";
pub const APPLY: &str = "compute/apply";
pub const IF: &str = "compute/if";
pub const LET: &str = "compute/let";
pub const LAMBDA: &str = "compute/lambda";

// ── §2.2 inline expression types — eight ──────────────────────────────────────────
pub const ARITHMETIC: &str = "compute/arithmetic";
pub const COMPARE: &str = "compute/compare";
pub const LOGIC: &str = "compute/logic";
pub const FIELD: &str = "compute/field";
pub const CONSTRUCT: &str = "compute/construct";
pub const INDEX: &str = "compute/index";
pub const LENGTH: &str = "compute/length";
pub const NUMERIC_CAST: &str = "compute/numeric-cast";

// ── §2.3 value types ──────────────────────────────────────────────────────────────
pub const CLOSURE: &str = "compute/closure";
pub const SCOPE: &str = "compute/scope";
pub const SCOPE_BINDING: &str = "system/compute/scope-binding";

// ── §2.4 result and error ─────────────────────────────────────────────────────────
pub const RESULT: &str = "compute/result";
pub const ERROR: &str = "compute/error";

// ── §2.5 / §2.6 subgraph and install ──────────────────────────────────────────────
pub const SUBGRAPH: &str = "system/compute/subgraph";
pub const INSTALL_REQUEST: &str = "system/compute/install-request";
pub const INSTALL_RESULT: &str = "system/compute/install-result";

// ── §3.5 builtin argument types ───────────────────────────────────────────────────
pub const MAP_ARGS: &str = "system/compute/map-args";
pub const FILTER_ARGS: &str = "system/compute/filter-args";
pub const FOLD_ARGS: &str = "system/compute/fold-args";
pub const RANGE_ARGS: &str = "system/compute/range-args";
pub const GROUP_BY_ARGS: &str = "system/compute/group-by-args";
pub const GROUP: &str = "system/compute/group";
pub const CONCAT_ARGS: &str = "system/compute/concat-args";
pub const ASSOC_ARGS: &str = "system/compute/assoc-args";
pub const STORE_ARGS: &str = "system/compute/store-args";

/// §10.1's eight core expression types, in the order §10.1 lists them.
pub const CORE_EXPRESSION_TYPES: [&str; 8] = [
    LITERAL,
    LOOKUP_SCOPE,
    LOOKUP_TREE,
    LOOKUP_HASH,
    APPLY,
    IF,
    LET,
    LAMBDA,
];

/// §2.2's eight inline expression types, in §2.2's declaration order.
pub const INLINE_EXPRESSION_TYPES: [&str; 8] = [
    ARITHMETIC,
    COMPARE,
    LOGIC,
    FIELD,
    CONSTRUCT,
    INDEX,
    LENGTH,
    NUMERIC_CAST,
];

/// Every type this extension owns and publishes, in spec-section order.
pub const ALL_TYPES: [&str; 33] = [
    LITERAL,
    LOOKUP_SCOPE,
    LOOKUP_TREE,
    LOOKUP_HASH,
    APPLY,
    IF,
    LET,
    LAMBDA,
    ARITHMETIC,
    COMPARE,
    LOGIC,
    FIELD,
    CONSTRUCT,
    INDEX,
    LENGTH,
    NUMERIC_CAST,
    CLOSURE,
    SCOPE,
    SCOPE_BINDING,
    RESULT,
    ERROR,
    SUBGRAPH,
    INSTALL_REQUEST,
    INSTALL_RESULT,
    MAP_ARGS,
    FILTER_ARGS,
    FOLD_ARGS,
    RANGE_ARGS,
    GROUP_BY_ARGS,
    GROUP,
    CONCAT_ARGS,
    ASSOC_ARGS,
    STORE_ARGS,
];

/// The handler pattern. §3.1's PROSE, not §3.1's code block, which spells it
/// `system/compute/*` (the capability-scope form; 2 of 18 manifests across the corpus).
pub const COMPUTE_PATTERN: &str = "system/compute";

/// §3.5 — the builtin handler prefix, and §4's override prohibition subject. Ours to guard as
/// of v3.29: `ENTITY-CORE-PROTOCOL` 0.8.2.13 withdrew the core `system/*` reservation it used
/// to delegate to. See `sdk::assert_not_builtin_override`.
pub const BUILTINS_PREFIX: &str = "system/compute/builtins";

/// §7 reactive mode — where subgraph metadata lives (§3.3 Phase 3).
pub const PROCESSES_PREFIX: &str = "system/compute/processes";

// ── §9.1's sixteen error codes ────────────────────────────────────────────────────
//
// Three carry a property §9.1's table does not record (v3.27): `depth_exceeded` CONTAINS (its
// counter is restored on unwind, §5.1) while `budget_exhausted` and `cascade_limit`
// SHORT-CIRCUIT everywhere. See `internal::evaluator::is_halting`.
pub const CODE_BUDGET_EXHAUSTED: &str = "budget_exhausted";
pub const CODE_DEPTH_EXCEEDED: &str = "depth_exceeded";
pub const CODE_TYPE_MISMATCH: &str = "type_mismatch";
pub const CODE_DIVISION_BY_ZERO: &str = "division_by_zero";
pub const CODE_NOT_FOUND: &str = "not_found";
pub const CODE_UNKNOWN_TYPE: &str = "unknown_type";
pub const CODE_MISSING_ARGUMENT: &str = "missing_argument";
pub const CODE_INVALID_EXPRESSION: &str = "invalid_expression";
pub const CODE_CASCADE_LIMIT: &str = "cascade_limit";
pub const CODE_PERMISSION_DENIED: &str = "permission_denied";
pub const CODE_INSTALLATION_GRANT_INVALID: &str = "installation_grant_invalid";
pub const CODE_INDEX_OUT_OF_RANGE: &str = "index_out_of_range";
pub const CODE_CAST_OUT_OF_RANGE: &str = "cast_out_of_range";
pub const CODE_COUNT_OUT_OF_RANGE: &str = "count_out_of_range";
pub const CODE_SCOPE_UNREACHABLE: &str = "scope_unreachable";
pub const CODE_AMBIGUOUS_RESOURCE: &str = "ambiguous_resource";

/// §9.3 — `peer_default_max_ops`.
pub const DEFAULT_MAX_OPS: u64 = 100_000;
/// §9.3 — `peer_default_max_depth` / `RECOMMENDED_MAX_DEPTH`.
pub const DEFAULT_MAX_DEPTH: u64 = 1_024;
/// §9.3 — `RECOMMENDED_MAX_CASCADE_DEPTH`. §10.3's one MAY is its configurability.
pub const RECOMMENDED_MAX_CASCADE_DEPTH: u64 = 16;

/// §4.7 `is_compute_expression` — the sixteen expression types and nothing else.
///
/// `compute/closure` and `compute/scope` are deliberately absent: §2.1's `lookup/tree` note says
/// *"closures are values, not expressions, and are not re-evaluated"*. `compute/result` and
/// `compute/error` are §2.4 values, not programs.
///
/// **SIXTEEN, AND §4.7's OWN LIST IS THIRTEEN.** A declared deviation, routed (A-10).
pub fn is_compute_expression(type_name: &str) -> bool {
    CORE_EXPRESSION_TYPES.contains(&type_name) || INLINE_EXPRESSION_TYPES.contains(&type_name)
}

/// §4.2 `is_compute_type` — Tier 1 of `validate_compute_resolvable`.
///
/// **TWENTY-THREE, AND §4.2's OWN LIST IS TWENTY, AND HERE THE OMISSION IS FUNCTIONAL.** Every
/// sub-expression is referenced by hash and resolved through Tier 1 when there is no
/// content-store access and no sealed set, so a literal transcription answers `not_found` on any
/// valid program containing an `index`, `length` or `numeric-cast` node.
pub fn is_compute_type(type_name: &str) -> bool {
    is_compute_expression(type_name)
        || [
            CLOSURE,
            SCOPE,
            RESULT,
            ERROR,
            SUBGRAPH,
            INSTALL_REQUEST,
            INSTALL_RESULT,
        ]
        .contains(&type_name)
}

// ── field-spec builders (omit-empty; the ECF §1.3 absent-key convention) ─────────────
//
// The same four shapes as `../history/src/types.rs`, `../../python/extensions/compute/types.py`
// and `typescript`'s `FSpec`. The codec re-sorts map keys length-then-lex, so declaration order
// here does not reach the bytes.

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

/// Optional is ADDED to the inner spec, never wrapped around it. Wrapping is the natural Rust
/// reflex and produces a different map, therefore a different hash.
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

/// No `key_type`: `typescript`'s `FSpec.map(value)` is called with none at every position below,
/// and a key present on one port and absent on another is a different hash for one type.
fn fmap(value: Value) -> Value {
    map_of(vec![("map_of", value)])
}

fn type_def(name: &str, fields: Vec<(&str, Value)>) -> Value {
    let mut pairs: Vec<(Key, Value)> =
        vec![(Key::Text("name".into()), Value::Text(name.to_string()))];
    if !fields.is_empty() {
        pairs.push((Key::Text("fields".into()), map_of(fields)));
    }
    Value::Map(pairs)
}

/// The 33 definitions, in §2.1 → §2.2 → §2.3 → §2.4 → §2.5/§2.6 → §3.5 order.
///
/// Kept in spec order so a reader can diff this block by block against the spec and line by
/// line against `types.py` / `types.ts`.
pub fn compute_type_defs() -> Vec<(&'static str, Value)> {
    let h = || fref("system/hash");
    let path = || fref("system/tree/path");
    let text = || fref("primitive/string");
    let any = || fref("primitive/any");
    let boolean = || fref("primitive/bool");
    let type_name = || fref("system/type/name");

    vec![
        // ── §2.1 ──────────────────────────────────────────────────────────────────
        (LITERAL, type_def(LITERAL, vec![("value", any())])),
        (LOOKUP_SCOPE, type_def(LOOKUP_SCOPE, vec![("name", text())])),
        (
            LOOKUP_TREE,
            type_def(
                LOOKUP_TREE,
                vec![("path", path()), ("relative", opt(boolean()))],
            ),
        ),
        // The eighth core type, and the one the oracle's `types_expression` does not ask for.
        (
            LOOKUP_HASH,
            type_def(
                LOOKUP_HASH,
                vec![
                    ("hash", h()),
                    ("path", opt(path())),
                    ("relative", opt(boolean())),
                ],
            ),
        ),
        // Dual-mode apply: every field optional, which is why §4.1 decides the mode from which
        // fields are PRESENT.
        (
            APPLY,
            type_def(
                APPLY,
                vec![
                    ("path", opt(path())),
                    ("operation", opt(text())),
                    ("resource", opt(h())),
                    ("fn", opt(h())),
                    ("args", opt(fmap(h()))),
                    ("capability", opt(h())),
                ],
            ),
        ),
        (
            IF,
            type_def(
                IF,
                vec![("condition", h()), ("then", h()), ("else", opt(h()))],
            ),
        ),
        // §2.1's comment calls `bindings` `[{name, value}, ...]` and DECLARES `primitive/any`.
        // We render what is declared.
        (
            LET,
            type_def(LET, vec![("bindings", farray(any())), ("body", h())]),
        ),
        (
            LAMBDA,
            type_def(LAMBDA, vec![("params", farray(text())), ("body", h())]),
        ),
        // ── §2.2 ──────────────────────────────────────────────────────────────────
        //
        // The spec's `constraints: {op: {one_of: [...]}}` has no carrier in a `system/type` or a
        // `field-spec`, on any of the three peers; the `one_of` is enforced in the evaluator.
        // `[substrate.type_constraints_unrenderable]`.
        (
            ARITHMETIC,
            type_def(
                ARITHMETIC,
                vec![("op", text()), ("left", h()), ("right", h())],
            ),
        ),
        (
            COMPARE,
            type_def(COMPARE, vec![("op", text()), ("left", h()), ("right", h())]),
        ),
        // `right` optional — absent for "not".
        (
            LOGIC,
            type_def(
                LOGIC,
                vec![("op", text()), ("left", h()), ("right", opt(h()))],
            ),
        ),
        (
            FIELD,
            type_def(FIELD, vec![("name", text()), ("entity", h())]),
        ),
        (
            CONSTRUCT,
            type_def(
                CONSTRUCT,
                vec![("entity_type", type_name()), ("fields", fmap(h()))],
            ),
        ),
        (INDEX, type_def(INDEX, vec![("array", h()), ("index", h())])),
        (LENGTH, type_def(LENGTH, vec![("array", h())])),
        (
            NUMERIC_CAST,
            type_def(NUMERIC_CAST, vec![("value", h()), ("to_type", type_name())]),
        ),
        // ── §2.3 ──────────────────────────────────────────────────────────────────
        (
            CLOSURE,
            type_def(
                CLOSURE,
                vec![("params", farray(text())), ("body", h()), ("env", opt(h()))],
            ),
        ),
        (
            SCOPE,
            type_def(SCOPE, vec![("bindings", fmap(fref(SCOPE_BINDING)))]),
        ),
        // §2.3's kind-tagged union, v3.19b.
        (
            SCOPE_BINDING,
            type_def(
                SCOPE_BINDING,
                vec![
                    ("kind", text()),
                    ("entity_hash", opt(h())),
                    ("value", opt(any())),
                ],
            ),
        ),
        // ── §2.4 ──────────────────────────────────────────────────────────────────
        (
            RESULT,
            type_def(RESULT, vec![("value", any()), ("expression", h())]),
        ),
        // `code` is the ONLY materialized field; the other three are declared because the TYPE
        // has them and are never materialized by the evaluator (v3.26).
        (
            ERROR,
            type_def(
                ERROR,
                vec![
                    ("code", text()),
                    ("message", opt(text())),
                    ("at", opt(text())),
                    ("expression", opt(h())),
                ],
            ),
        ),
        // ── §2.5 / §2.6 ───────────────────────────────────────────────────────────
        //
        // SEVEN FIELDS — §3.3's shape, not §2.5's six. A declared deviation (A-11).
        (
            SUBGRAPH,
            type_def(
                SUBGRAPH,
                vec![
                    ("root_expression_path", path()),
                    ("root_expression", h()),
                    ("installation_grant", h()),
                    ("installed_by", h()),
                    ("result_path", path()),
                    ("status", text()),
                    ("authorized_data_hashes", opt(farray(h()))),
                ],
            ),
        ),
        (
            INSTALL_REQUEST,
            type_def(INSTALL_REQUEST, vec![("result_path", opt(path()))]),
        ),
        (
            INSTALL_RESULT,
            type_def(
                INSTALL_RESULT,
                vec![
                    ("subgraph_path", path()),
                    ("impure_operations", any()),
                    ("result_path", path()),
                ],
            ),
        ),
        // No `system/compute/uninstall-request`: eliminated in v3.12; the header still names it.
        // ── §3.5 ──────────────────────────────────────────────────────────────────
        (
            MAP_ARGS,
            type_def(MAP_ARGS, vec![("collection", h()), ("fn", h())]),
        ),
        // `fn`, not `predicate` — renamed at F11 (v3.19).
        (
            FILTER_ARGS,
            type_def(FILTER_ARGS, vec![("collection", h()), ("fn", h())]),
        ),
        (
            FOLD_ARGS,
            type_def(
                FOLD_ARGS,
                vec![("collection", h()), ("fn", h()), ("initial", h())],
            ),
        ),
        (RANGE_ARGS, type_def(RANGE_ARGS, vec![("n", h())])),
        (
            GROUP_BY_ARGS,
            type_def(GROUP_BY_ARGS, vec![("collection", h()), ("fn", h())]),
        ),
        (
            GROUP,
            type_def(GROUP, vec![("key", any()), ("members", farray(any()))]),
        ),
        // v3.27: ONE hash of an expression, not an array of hashes.
        (
            CONCAT_ARGS,
            type_def(CONCAT_ARGS, vec![("collections", h())]),
        ),
        (
            ASSOC_ARGS,
            type_def(
                ASSOC_ARGS,
                vec![("collection", h()), ("index", h()), ("value", h())],
            ),
        ),
        (
            STORE_ARGS,
            type_def(STORE_ARGS, vec![("path", path()), ("value", h())]),
        ),
    ]
}

/// `(type_name, system/type entity)` for each of the 33 — the materialised form.
pub fn compute_type_entities() -> Vec<(&'static str, Entity)> {
    compute_type_defs()
        .into_iter()
        .map(|(name, data)| (name, Entity::make("system/type", data)))
        .collect()
}

/// Bind the 33 type entities at `system/type/{name}` and return the absolute paths written.
///
/// Takes `&Store` rather than a peer, matching `../content` and `../history`.
pub fn publish_compute_types(store: &Store, local_peer: &str) -> Vec<String> {
    let mut written = Vec::new();
    for (name, entity) in compute_type_entities() {
        let path = format!("/{local_peer}/system/type/{name}");
        store.bind(&path, &entity);
        written.push(path);
    }
    written
}

/// Build one of our own entities without reaching for `Entity::make` at each site. Present in
/// all three ports and `required` in `[sdk_surface]`.
pub fn compute_entity(entity_type: &str, data: Value) -> Entity {
    Entity::make(entity_type, data)
}
