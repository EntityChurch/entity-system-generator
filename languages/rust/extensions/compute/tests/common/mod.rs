//! Shared fixtures for the integration tests. Everything here goes through the crate's PUBLIC
//! surface: an integration test in `tests/` sees only `pub`, which is the §3.4 boundary measured
//! from the inside.

#![allow(dead_code)]

use std::sync::Arc;

use entity_compute::{ComputeEvaluator, EvalOutcome, EvaluateOptions, EvaluatorLimits, DEFAULT_LIMITS, LITERAL};
use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::peer::{CreateOptions, Peer};
use entity_core_protocol::value::{Key, Value};

pub const PEER: &str = "z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH";

pub fn root() -> String {
    format!("/{PEER}/app/expr")
}

/// A map value from `(&str, Value)` pairs.
pub fn map(pairs: Vec<(&str, Value)>) -> Value {
    Value::Map(pairs.into_iter().map(|(k, v)| (Key::Text(k.to_string()), v)).collect())
}

pub fn text(s: &str) -> Value {
    Value::Text(s.to_string())
}

pub fn int(i: i128) -> Value {
    if i >= 0 {
        Value::UInt(i as u64)
    } else {
        Value::NInt((-1 - i) as u64)
    }
}

pub fn bytes(h: &[u8]) -> Value {
    Value::Bytes(h.to_vec())
}

pub fn entity(typ: &str, pairs: Vec<(&str, Value)>) -> Entity {
    Entity::make(typ, map(pairs))
}

/// Store an entity and return the hash a parent expression references it by.
pub fn put(store: &Store, e: Entity) -> Vec<u8> {
    store.put_entity(&e);
    e.hash
}

pub fn literal(store: &Store, value: Value) -> Vec<u8> {
    put(store, entity(LITERAL, vec![("value", value)]))
}

pub fn run(store: &Store, expr: &Entity) -> EvalOutcome {
    run_with(store, expr, DEFAULT_LIMITS, EvaluateOptions::default())
}

pub fn run_with(store: &Store, expr: &Entity, limits: EvaluatorLimits, options: EvaluateOptions) -> EvalOutcome {
    ComputeEvaluator::new(store, PEER, limits).evaluate_at(expr, &root(), options)
}

/// Assert success with a data value, reporting the CODE on failure.
pub fn value_of(outcome: &EvalOutcome) -> Value {
    if let Some(e) = &outcome.error {
        panic!("expected a value, got compute/error {} ({})", e.code, e.detail);
    }
    outcome
        .value
        .clone()
        .unwrap_or_else(|| panic!("expected a data value, got entity {:?}", outcome.entity.as_ref().map(|e| &e.typ)))
}

pub fn entity_of(outcome: &EvalOutcome) -> Entity {
    if let Some(e) = &outcome.error {
        panic!("expected an entity, got compute/error {} ({})", e.code, e.detail);
    }
    outcome.entity.clone().expect("expected an entity result")
}

pub fn code_of(outcome: &EvalOutcome) -> String {
    match &outcome.error {
        Some(e) => e.code.clone(),
        None => panic!("expected an error, got {:?} / {:?}", outcome.value, outcome.entity.as_ref().map(|e| &e.typ)),
    }
}

/// A live peer. `open_grants: true` is the posture the conformance harness launches in.
pub fn peer() -> Arc<Peer> {
    Arc::new(Peer::create(CreateOptions {
        seed: [0x11; 32],
        open_grants: true,
        conformance: false,
    }))
}

pub fn abs(p: &Peer, rel: &str) -> String {
    format!("/{}/{rel}", p.local_peer)
}

/// A `system/capability/token` built by hand. **This peer exposes no mint** (keystone K-2), and
/// `check_permission` reads only the `grants` array, so for the handler's per-path checks a token
/// with the right grant shape is the thing under test and a signature would add nothing.
pub fn token(granter: &[u8], handlers: &[&str], resources: &[&str], operations: &[&str]) -> Entity {
    let scope = |items: &[&str]| map(vec![("include", Value::Array(items.iter().map(|s| text(s)).collect()))]);
    entity(
        "system/capability/token",
        vec![
            (
                "grants",
                Value::Array(vec![map(vec![
                    ("handlers", scope(handlers)),
                    ("resources", scope(resources)),
                    ("operations", scope(operations)),
                ])]),
            ),
            ("granter", bytes(granter)),
        ],
    )
}
