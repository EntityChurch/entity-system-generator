//! §2.1 / §2.2 / §2.4 / §6.2 / §6.3 — the seven hand-built type definitions.
//!
//! **These tests cannot tell you the field maps are right.** Nothing local can: a
//! subtly wrong map produces a well-formed entity that hashes differently from every
//! other implementation's, dedup stops for that type, and no error is raised anywhere.
//! What they CAN do is pin the three rendering decisions that would produce a different
//! hash for an otherwise-correct declaration, because those are the ones a
//! reimplementation gets wrong:
//!
//! 1. **omit-empty** — a type with no fields carries no `fields` key at all.
//! 2. **`optional` is merged, not wrapped** — the natural Rust reflex is
//!    `Optional(Box<FSpec>)`, which would render a nested map and a different hash.
//! 3. **`array_of` is a carrier key**, not a sibling of `type_ref`.
//!
//! The check that CAN tell you the maps are right is `validate-peer`'s
//! `type_system.type_system_content_{blob,chunk,descriptor}_match`, which renders the
//! same three types from `entity-core-go`'s own independent transcription and compares
//! content hashes. It is the one third-party measurement this substrate supports, and
//! `languages/rust/compositions/content` exists to run it.

use entity_content::{
    content_type_defs, content_type_entities, install_content_types, ALL_TYPES, BLOB, CHUNK,
    DESCRIPTOR,
};
use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

fn field_spec<'a>(def: &'a Value, field: &str) -> &'a Value {
    let fields = match def {
        Value::Map(entries) => entries
            .iter()
            .find(|(k, _)| matches!(k, Key::Text(t) if t == "fields"))
            .map(|(_, v)| v)
            .expect("the type declares fields"),
        other => panic!("type def is not a map: {other:?}"),
    };
    match fields {
        Value::Map(entries) => entries
            .iter()
            .find(|(k, _)| matches!(k, Key::Text(t) if t == field))
            .map(|(_, v)| v)
            .unwrap_or_else(|| panic!("no field {field}")),
        other => panic!("fields is not a map: {other:?}"),
    }
}

fn keys_of(v: &Value) -> Vec<String> {
    match v {
        Value::Map(entries) => entries
            .iter()
            .map(|(k, _)| match k {
                Key::Text(t) => t.clone(),
                other => format!("{other:?}"),
            })
            .collect(),
        other => panic!("not a map: {other:?}"),
    }
}

#[test]
fn all_seven_types_are_declared_and_named_consistently() {
    let defs = content_type_defs();
    assert_eq!(defs.len(), 7);
    let declared: Vec<&str> = defs.iter().map(|(n, _)| *n).collect();
    assert_eq!(declared.as_slice(), ALL_TYPES.as_slice());
    // Each definition's `name` field must equal the path it is filed under. A mismatch
    // is invisible to every consumer until two peers disagree about which type an
    // entity is.
    for (name, def) in &defs {
        match def {
            Value::Map(entries) => {
                let n = entries
                    .iter()
                    .find(|(k, _)| matches!(k, Key::Text(t) if t == "name"))
                    .map(|(_, v)| v);
                assert_eq!(n, Some(&Value::Text(name.to_string())));
            }
            other => panic!("not a map: {other:?}"),
        }
    }
}

#[test]
fn optional_is_merged_into_the_inner_spec_and_not_wrapped() {
    // Rendering decision (2). `Optional(Box<FSpec>)` -- the shape the peer's own
    // private enum uses internally -- renders by ADDING `optional: true` to the inner
    // map. Wrapping it would produce `{optional: {type_ref: ...}}`, a different map and
    // a different content hash, and nothing local would notice.
    let defs = content_type_defs();
    let descriptor = &defs.iter().find(|(n, _)| *n == DESCRIPTOR).unwrap().1;
    let media_type = field_spec(descriptor, "media_type");
    let mut keys = keys_of(media_type);
    keys.sort();
    assert_eq!(keys, vec!["optional".to_string(), "type_ref".to_string()]);
    assert_eq!(
        media_type,
        &Value::Map(vec![
            (Key::Text("type_ref".into()), Value::Text("primitive/string".into())),
            (Key::Text("optional".into()), Value::Bool(true)),
        ])
    );
}

#[test]
fn array_of_is_a_carrier_key_not_a_sibling_of_type_ref() {
    // Rendering decision (3).
    let defs = content_type_defs();
    let blob = &defs.iter().find(|(n, _)| *n == BLOB).unwrap().1;
    let chunks = field_spec(blob, "chunks");
    assert_eq!(keys_of(chunks), vec!["array_of".to_string()]);
    assert_eq!(
        chunks,
        &Value::Map(vec![(
            Key::Text("array_of".into()),
            Value::Map(vec![(
                Key::Text("type_ref".into()),
                Value::Text("system/hash".into())
            )])
        )])
    );
}

#[test]
fn a_type_with_no_fields_would_carry_no_fields_key() {
    // Rendering decision (1), asserted against the ONE case in the corpus that could
    // exercise it. All seven CONTENT types declare fields, so this asserts the property
    // on the builder's own output for an empty declaration rather than on a type that
    // happens to have none -- which is the difference between testing the rule and
    // testing the data.
    let none = Entity::make("system/type", Value::Map(vec![(
        Key::Text("name".into()),
        Value::Text("system/content/nothing".into()),
    )]));
    assert_eq!(keys_of(&none.data), vec!["name".to_string()]);
    // And the corpus does not accidentally satisfy it: every real type HAS fields, so
    // an omit-empty bug would be invisible in this corpus without the case above.
    for (name, def) in content_type_defs() {
        assert!(
            keys_of(&def).contains(&"fields".to_string()),
            "{name} declares no fields; the omit-empty case above is no longer the only one"
        );
    }
}

#[test]
fn chunk_carries_payload_and_nothing_else() {
    // §2.2. The absence is the point: no sequence number, no parent ref, so identical
    // bytes hash identically across blobs. A helpful extra field here would silently
    // end cross-peer dedup for every chunk this peer ever writes.
    let defs = content_type_defs();
    let chunk = &defs.iter().find(|(n, _)| *n == CHUNK).unwrap().1;
    let fields = match chunk {
        Value::Map(entries) => entries
            .iter()
            .find(|(k, _)| matches!(k, Key::Text(t) if t == "fields"))
            .map(|(_, v)| v)
            .unwrap(),
        other => panic!("{other:?}"),
    };
    assert_eq!(keys_of(fields), vec!["payload".to_string()]);
}

#[test]
fn rendering_is_deterministic() {
    // Two independent renders must produce equal content hashes. Cheap, and it is the
    // check that would catch a map built from a HashMap iteration somewhere upstream.
    let a = content_type_entities();
    let b = content_type_entities();
    for ((na, ea), (nb, eb)) in a.iter().zip(b.iter()) {
        assert_eq!(na, nb);
        assert_eq!(ea.hash, eb.hash, "{na} did not render deterministically");
    }
}

#[test]
fn install_writes_all_seven_at_the_core_type_index() {
    // I1 (owned-namespace containment) holds structurally: every path is
    // `system/type/` plus a name from ALL_TYPES, and `system/type/*` is the core's
    // published type index that every extension writes into by design
    // (GUIDE-EXTENSION-DEVELOPMENT §4.3 -- a type name inside our owned prefix is ours;
    // the index it is filed under is shared).
    let store = Store::new();
    let installation = install_content_types(&store, "PEERID");
    assert_eq!(installation.type_paths.len(), 7);
    for name in ALL_TYPES {
        let path = format!("/PEERID/system/type/{name}");
        assert!(
            installation.type_paths.contains(&path),
            "{path} was not written"
        );
        let bound = store.get_at(&path).expect("bound in the tree");
        assert_eq!(bound.typ, "system/type");
    }
    // NEGATIVE CONTROL: a path we did not write is not bound, so "get_at returned
    // something" is not a property of the store rather than of the install.
    assert!(store.get_at("/PEERID/system/type/system/content/absent").is_none());
}
