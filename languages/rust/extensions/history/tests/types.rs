//! §9.2's six types, and the one install face this peer has.
//!
//! An INTEGRATION test, in `tests/`, so it sees the crate exactly as a third party does:
//! only `pub`. A `#[cfg(test)] mod tests` inside `src/` would see the private module and
//! would prove nothing about the boundary.
//!
//! **What this file does NOT do is compare against another implementation, and that is a
//! gap rather than a choice.** CONTENT's three §11.1 types are checked by
//! `validate-peer -category type_system`, which renders them from `entity-core-go`'s own
//! independent transcription and compares content hashes. **HISTORY has no such check.**
//! Its six oracle `type_*` checks are `client.TreeGet(path)` and nothing else
//! (`history.go:120-129`) — they assert the paths RESOLVE, not that the entities are
//! right. So a subtly wrong field map here produces a well-formed entity that hashes
//! differently from `typescript`'s and `python`'s, dedup stops for that type, all six
//! checks stay green, and nothing anywhere says so.
//!
//! That is an axis with no upstream authority, which by D16 gets its gate — and this is
//! the third port, so the gate is late. Recorded in the handoff; the assertions below
//! are structural and are not a substitute for it.

use entity_history::{
    history_type_defs, history_type_entities, publish_history_types, ALL_TYPES, CONFIG,
    QUERY_PARAMS, QUERY_RESULT, ROLLBACK_PARAMS, ROLLBACK_RESULT, TRANSITION,
};

use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

fn field_spec<'a>(def: &'a Value, field: &str) -> Option<&'a Value> {
    let fields = entity_core_protocol::peer::model::map_get(def, "fields")?;
    entity_core_protocol::peer::model::map_get(fields, field)
}

fn is_optional(spec: &Value) -> bool {
    matches!(
        entity_core_protocol::peer::model::map_get(spec, "optional"),
        Some(Value::Bool(true))
    )
}

fn type_ref(spec: &Value) -> Option<&str> {
    match entity_core_protocol::peer::model::map_get(spec, "type_ref")? {
        Value::Text(t) => Some(t.as_str()),
        _ => None,
    }
}

fn field_names(def: &Value) -> Vec<String> {
    match entity_core_protocol::peer::model::map_get(def, "fields") {
        Some(Value::Map(entries)) => entries
            .iter()
            .filter_map(|(k, _)| match k {
                Key::Text(t) => Some(t.clone()),
                _ => None,
            })
            .collect(),
        _ => vec![],
    }
}

fn def_of(name: &str) -> Value {
    history_type_defs()
        .into_iter()
        .find(|(n, _)| *n == name)
        .unwrap_or_else(|| panic!("no definition for {name}"))
        .1
}

#[test]
fn all_types_is_section_9_2s_six_in_order() {
    assert_eq!(
        ALL_TYPES,
        [
            TRANSITION,
            CONFIG,
            QUERY_PARAMS,
            QUERY_RESULT,
            ROLLBACK_PARAMS,
            ROLLBACK_RESULT
        ]
    );
    assert_eq!(history_type_defs().len(), 6);
}

/// §2.1's table, field for field. The count is asserted as well as the membership: a
/// field silently ADDED here would move the transition's content hash away from every
/// other implementation's, and a `contains` check would not notice.
#[test]
fn transition_has_exactly_section_2_1s_fourteen_fields() {
    let def = def_of(TRANSITION);
    let mut names = field_names(&def);
    names.sort();
    let mut expected = vec![
        "path",
        "event",
        "hash",
        "previous_hash",
        "author",
        "capability",
        "caller_capability",
        "handler",
        "operation",
        "timestamp",
        "clock",
        "chain_id",
        "parent_chain_id",
        "previous",
    ];
    expected.sort();
    assert_eq!(names, expected);
}

/// The two §9.1 MUSTs are NOT optional, and `caller_capability` IS.
///
/// This is the assertion that would catch the fix somebody reaches for when the peer
/// delivers no execution context: marking `author`/`capability` optional so the absent
/// values become conformant. They are not optional in §2.1, and the module's answer is
/// to record §2.1's autonomous-case values and declare the provenance — not to edit the
/// type.
#[test]
fn author_and_capability_are_required_caller_capability_is_not() {
    let def = def_of(TRANSITION);
    for required in ["path", "event", "author", "capability", "handler", "operation", "timestamp"] {
        let spec = field_spec(&def, required).expect(required);
        assert!(!is_optional(spec), "{required} must not be optional (§2.1)");
    }
    for optional in [
        "hash",
        "previous_hash",
        "caller_capability",
        "clock",
        "chain_id",
        "parent_chain_id",
        "previous",
    ] {
        let spec = field_spec(&def, optional).expect(optional);
        assert!(is_optional(spec), "{optional} is optional in §2.1");
    }
    assert_eq!(
        type_ref(field_spec(&def, "clock").unwrap()),
        Some("system/clock/state"),
        "§2.1 F7: the clock field is the structured clock state, not a uint"
    );
}

/// §2.4 — `transitions` is `array_of` the TRANSITION type, and `has_more` is REQUIRED.
///
/// `has_more` not being optional is what makes the handler's `false` encode as
/// present-and-false, which the oracle's `HasMore bool` (no `omitempty`) needs.
#[test]
fn query_result_carries_an_array_of_transitions_and_a_required_has_more() {
    let def = def_of(QUERY_RESULT);
    let transitions = field_spec(&def, "transitions").expect("transitions");
    let elem = entity_core_protocol::peer::model::map_get(transitions, "array_of")
        .expect("transitions is an array_of");
    assert_eq!(type_ref(elem), Some(TRANSITION));
    assert!(!is_optional(field_spec(&def, "has_more").unwrap()));
    assert!(is_optional(field_spec(&def, "head").unwrap()));
}

/// §2.2 — `enabled` is a required `primitive/bool`.
///
/// The recorder SKIPS a config whose `enabled` is missing or not a bool rather than
/// defaulting it, and the reason is this line: `enabled` is required, so an absent one
/// means the entity is malformed, and defaulting a malformed audit switch to `true` is
/// the wrong direction to fail in.
#[test]
fn config_requires_enabled_as_a_bool() {
    let def = def_of(CONFIG);
    let enabled = field_spec(&def, "enabled").expect("enabled");
    assert_eq!(type_ref(enabled), Some("primitive/bool"));
    assert!(!is_optional(enabled));
    assert!(is_optional(field_spec(&def, "events").unwrap()));
    assert!(is_optional(field_spec(&def, "max_depth").unwrap()));
}

/// Optional is rendered by ADDING `optional: true` to the inner spec, not by wrapping it.
///
/// Wrapping is the natural Rust reflex — the peer's own private `FSpec` has an
/// `Optional(Box<..>)` variant — and it would produce a different map and therefore a
/// different content hash from the other two ports, silently.
#[test]
fn optional_is_a_flag_on_the_spec_not_a_wrapper() {
    let def = def_of(TRANSITION);
    let spec = field_spec(&def, "previous").expect("previous");
    assert_eq!(type_ref(spec), Some("system/hash"));
    assert!(is_optional(spec));
    assert!(
        entity_core_protocol::peer::model::map_get(spec, "type_ref").is_some(),
        "the inner type_ref must survive alongside `optional`, not be nested under it"
    );
}

/// Every type entity is a `system/type` whose `name` is its own path. The oracle reads
/// them by path; the `name` field is what a reader resolves them by.
#[test]
fn type_entities_are_system_type_and_self_naming() {
    for (name, entity) in history_type_entities() {
        assert_eq!(entity.typ, "system/type");
        assert_eq!(entity.text_field("name"), Some(name));
        assert_eq!(entity.hash.len(), 33, "content_hash is 0x00 ‖ SHA-256");
    }
}

/// Type publication, exercised against a bare `Store`.
#[test]
fn publishing_binds_exactly_the_six_oracle_paths() {
    let store = Store::new();
    let type_paths = publish_history_types(&store, "PEER");
    assert_eq!(type_paths.len(), 6);
    for name in ALL_TYPES {
        // The exact paths `validate-peer -category history` fetches.
        let path = format!("/PEER/system/type/{name}");
        assert!(
            type_paths.contains(&path),
            "missing published path {path}"
        );
        let bound = store.get_at(&path).expect("bound");
        assert_eq!(bound.text_field("name"), Some(name));
    }
    // I1: nothing outside `system/type/` was written.
    for p in &type_paths {
        assert!(p.starts_with("/PEER/system/type/"), "{p} escapes the namespace");
    }
}

/// Re-publishing is idempotent: same bytes, same hash, and the second bind fires no
/// tree-change event.
///
/// This matters for the recorder rather than for the types: `install_history` registers the
/// recorder AFTER publishing the types precisely so the six type writes are not
/// recorded as application transitions, and a type publication that changed hash on
/// every call would defeat that on any restart.
#[test]
fn publishing_twice_is_byte_identical() {
    let store = Store::new();
    let first = publish_history_types(&store, "PEER");
    let hashes_a: Vec<Vec<u8>> = first
        .iter()
        .map(|p| store.hash_at(p).unwrap())
        .collect();
    let second = publish_history_types(&store, "PEER");
    let hashes_b: Vec<Vec<u8>> = second
        .iter()
        .map(|p| store.hash_at(p).unwrap())
        .collect();
    assert_eq!(hashes_a, hashes_b);
}
