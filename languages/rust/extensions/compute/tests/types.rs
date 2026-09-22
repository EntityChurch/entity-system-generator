//! The 33 type definitions. The cross-PORT defence is `make type-parity`, which compares every
//! port's type entities by content hash and field map; the cross-IMPLEMENTATION defence is the 63
//! core `type_compute_*_match` checks against `entity-core-go`'s own transcription. These tests hold
//! the local invariants those two depend on.

mod common;

use std::collections::HashSet;

use common::*;
use entity_compute::*;
use entity_core_protocol::value::{Key, Value};

#[test]
fn thirty_three_types_are_defined_once_each_in_all_types_order() {
    let defs = compute_type_defs();
    assert_eq!(defs.len(), 33);
    assert_eq!(
        defs.iter().map(|(n, _)| *n).collect::<Vec<_>>(),
        ALL_TYPES.to_vec()
    );
    let hashes: HashSet<_> = compute_type_entities()
        .into_iter()
        .map(|(_, e)| e.hash)
        .collect();
    assert_eq!(
        hashes.len(),
        33,
        "no two definitions render the same entity"
    );
    for (name, e) in compute_type_entities() {
        assert_eq!(e.typ, "system/type");
        assert_eq!(e.text_field("name"), Some(name));
    }
}

fn fields_of(name: &str) -> Vec<String> {
    let (_, data) = compute_type_defs()
        .into_iter()
        .find(|(n, _)| *n == name)
        .unwrap();
    let Value::Map(entries) = data else { panic!() };
    let fields = entries.into_iter().find_map(|(k, v)| match k {
        Key::Text(t) if t == "fields" => Some(v),
        _ => None,
    });
    match fields {
        Some(Value::Map(f)) => f
            .into_iter()
            .map(|(k, _)| match k {
                Key::Text(t) => t,
                _ => panic!(),
            })
            .collect(),
        _ => vec![],
    }
}

/// A-11: SEVEN fields — §3.3's shape, not §2.5's six. `authorized_data_hashes` is the one §10.1 MUSTs.
#[test]
fn the_subgraph_type_carries_the_seventh_field_the_spec_musts() {
    let f = fields_of(SUBGRAPH);
    assert_eq!(f.len(), 7);
    assert!(f.contains(&"authorized_data_hashes".to_string()));
}

/// The eighth core expression type, which §2.1's prose count omits and the oracle's
/// `types_expression` does not ask for.
#[test]
fn the_eighth_core_expression_type_is_registered() {
    assert!(CORE_EXPRESSION_TYPES.contains(&LOOKUP_HASH));
    assert_eq!(fields_of(LOOKUP_HASH), vec!["hash", "path", "relative"]);
}

/// A-10: sixteen expression types, twenty-three compute types — and the value types are compute
/// types but not expressions, which is what stops a stored closure evaluating on lookup.
#[test]
fn the_membership_predicates_carry_the_three_types_sections_4_2_and_4_7_omit() {
    let expressions: Vec<_> = ALL_TYPES
        .iter()
        .filter(|t| is_compute_expression(t))
        .collect();
    assert_eq!(expressions.len(), 16);
    let compute: Vec<_> = ALL_TYPES.iter().filter(|t| is_compute_type(t)).collect();
    assert_eq!(compute.len(), 23);
    for value_type in [CLOSURE, SCOPE, RESULT, ERROR] {
        assert!(
            is_compute_type(value_type) && !is_compute_expression(value_type),
            "{value_type}"
        );
    }
    assert!(
        !is_compute_type(SCOPE_BINDING) && !is_compute_type(GROUP),
        "record types are neither"
    );
}

/// Optional is ADDED to the inner spec, never wrapped — the one rendering mistake that is natural in
/// Rust and moves every optional field's hash.
#[test]
fn an_optional_field_spec_is_the_inner_spec_plus_optional_true() {
    let (_, data) = compute_type_defs()
        .into_iter()
        .find(|(n, _)| *n == LOGIC)
        .unwrap();
    let expected = map(vec![
        ("name", text(LOGIC)),
        (
            "fields",
            map(vec![
                ("op", map(vec![("type_ref", text("primitive/string"))])),
                ("left", map(vec![("type_ref", text("system/hash"))])),
                (
                    "right",
                    map(vec![
                        ("type_ref", text("system/hash")),
                        ("optional", Value::Bool(true)),
                    ]),
                ),
            ]),
        ),
    ]);
    assert_eq!(
        entity_core_protocol::cbor::encode(&data),
        entity_core_protocol::cbor::encode(&expected)
    );
}
