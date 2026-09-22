//! §4.1 `compute/apply` HANDLER mode, against a recording dispatcher.
//!
//! Crate-internal, because the dispatcher seam is: a third party cannot construct the peer's
//! `HandlerContext`, and `evaluate_in_request` is `pub(crate)` so that nothing outside the crate can
//! dispatch under a capability it names. The wire half — keystone's `dispatch_execute` actually
//! routing — is measured by the composed run (`v38_apply_handler_mode`,
//! `v310_apply_resource_field_accepted`, `v314_compute_apply_to_entity_native`).
//!
//! **What the oracle does not reach, and why these exist:** the F2 dual check's two denials, the
//! `>= 400` mapping, SA-4's re-wrap, and SA-2's `system/hash` encoding. Every test that asserts a
//! refusal also asserts the dispatcher was NOT called, because a refusal that dispatched anyway is
//! the escalation the dual check exists to prevent.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

use super::evaluator::DispatchCall;
use crate::sdk::{ComputeEvaluator, EvalOutcome, EvaluateOptions, RequestContext, DEFAULT_LIMITS};
use crate::types::{
    APPLY, CODE_INVALID_EXPRESSION, CODE_NOT_FOUND, CODE_PERMISSION_DENIED, CODE_TYPE_MISMATCH,
    ERROR, LITERAL, LOOKUP_HASH, RESULT,
};

const PEER: &str = "z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH";

fn map(pairs: Vec<(&str, Value)>) -> Value {
    Value::Map(pairs.into_iter().map(|(k, v)| (Key::Text(k.to_string()), v)).collect())
}

fn text(s: &str) -> Value {
    Value::Text(s.to_string())
}

fn put(store: &Store, e: Entity) -> Vec<u8> {
    store.put_entity(&e);
    e.hash
}

fn literal(store: &Store, value: Value) -> Vec<u8> {
    put(store, Entity::make(LITERAL, map(vec![("value", value)])))
}

fn token(handlers: &[&str]) -> Entity {
    let scope = |items: &[&str]| map(vec![("include", Value::Array(items.iter().map(|s| text(s)).collect()))]);
    Entity::make(
        "system/capability/token",
        map(vec![(
            "grants",
            Value::Array(vec![map(vec![
                ("handlers", scope(handlers)),
                ("resources", scope(&["*"])),
                ("operations", scope(&["*"])),
            ])]),
        )]),
    )
}

/// A handler at `app/h` (manifest + interface) whose `run` operation declares `app/in` and whose
/// `bare` operation declares no input type, and the type `app/in` with one `system/hash` field and
/// one `primitive/any` field.
fn store_with_handler() -> Store {
    let store = Store::new();
    store.bind(
        &format!("/{PEER}/app/h"),
        &Entity::make("system/handler", map(vec![("interface", text("system/handler/app/h"))])),
    );
    store.bind(
        &format!("/{PEER}/system/handler/app/h"),
        &Entity::make(
            "system/handler/interface",
            map(vec![
                ("pattern", text("app/h")),
                (
                    "operations",
                    map(vec![("run", map(vec![("input_type", text("app/in"))])), ("bare", map(vec![]))]),
                ),
            ]),
        ),
    );
    store.bind(
        &format!("/{PEER}/system/type/app/in"),
        &Entity::make(
            "system/type",
            map(vec![
                ("name", text("app/in")),
                (
                    "fields",
                    map(vec![
                        ("ref", map(vec![("type_ref", text("system/hash"))])),
                        ("n", map(vec![("type_ref", text("primitive/any"))])),
                    ]),
                ),
            ]),
        ),
    );
    store
}

struct Recorder {
    calls: AtomicUsize,
    last: Mutex<Option<(String, String, Option<Value>, Entity, Option<Entity>)>>,
    reply: (u64, Entity),
}

impl Recorder {
    fn replying(status: u64, result: Entity) -> Recorder {
        Recorder { calls: AtomicUsize::new(0), last: Mutex::new(None), reply: (status, result) }
    }

    fn dispatch(&self, call: DispatchCall) -> (u64, Entity) {
        self.calls.fetch_add(1, Ordering::SeqCst);
        *self.last.lock().unwrap() = Some((call.path, call.operation, call.resource, call.params, call.capability));
        self.reply.clone()
    }
}

fn run(store: &Store, apply: &Entity, capability: Option<&Entity>, rec: Option<&Recorder>) -> EvalOutcome {
    let closure = |call: DispatchCall| rec.expect("dispatcher present").dispatch(call);
    let mut ev = ComputeEvaluator::new(store, PEER, DEFAULT_LIMITS);
    ev.evaluate_in_request(
        apply,
        &format!("/{PEER}/app/expr"),
        EvaluateOptions { content_store_access: true, ..Default::default() },
        RequestContext {
            capability,
            dispatch: if rec.is_some() { Some(&closure) } else { None },
            bindings: Vec::new(),
        },
    )
}

fn code(o: &EvalOutcome) -> String {
    match (&o.error, &o.entity) {
        (Some(e), _) => e.code.clone(),
        (None, Some(e)) if e.typ == ERROR => e.text_field("code").unwrap_or("").to_string(),
        _ => panic!("expected an error, got value={:?} entity={:?}", o.value, o.entity.as_ref().map(|e| &e.typ)),
    }
}

fn apply(store: &Store, pairs: Vec<(&str, Value)>) -> Entity {
    let e = Entity::make(APPLY, map(pairs));
    store.put_entity(&e);
    e
}

#[test]
fn params_are_built_from_the_declared_input_type_and_encoded_per_field() {
    let store = store_with_handler();
    let target = Entity::make("app/thing", map(vec![("x", text("y"))]));
    let target_hash = put(&store, target.clone());
    let by_hash = put(&store, Entity::make(LOOKUP_HASH, map(vec![("hash", Value::Bytes(target_hash.clone()))])));
    let n = literal(&store, Value::UInt(7));
    let expr = apply(
        &store,
        vec![
            ("path", text("app/h")),
            ("operation", text("run")),
            ("args", Value::Map(vec![(Key::Text("ref".into()), Value::Bytes(by_hash)), (Key::Text("n".into()), Value::Bytes(n))])),
        ],
    );
    let rec = Recorder::replying(200, Entity::make("app/out", map(vec![])));
    let out = run(&store, &expr, None, Some(&rec));
    assert_eq!(out.entity.as_ref().map(|e| e.typ.as_str()), Some("app/out"), "an entity return passes through");

    let (path, op, resource, params, cap) = rec.last.lock().unwrap().take().expect("dispatched");
    assert_eq!((path.as_str(), op.as_str()), ("app/h", "run"));
    assert!(resource.is_none() && cap.is_none());
    assert_eq!(params.typ, "app/in");
    assert_eq!(params.bytes_field("ref"), Some(target_hash.as_slice()), "a system/hash field carries the hash");
    assert_eq!(params.uint_field("n"), Some(7), "a primitive/any field is inlined");
}

/// The NEGATIVE of the test above: a primitive at a `system/hash` position is `type_mismatch`,
/// and nothing is dispatched.
#[test]
fn a_primitive_at_a_hash_field_is_type_mismatch_and_not_dispatched() {
    let store = store_with_handler();
    let n = literal(&store, Value::UInt(7));
    let expr = apply(
        &store,
        vec![("path", text("app/h")), ("operation", text("run")), ("args", Value::Map(vec![(Key::Text("ref".into()), Value::Bytes(n))]))],
    );
    let rec = Recorder::replying(200, Entity::make("app/out", map(vec![])));
    assert_eq!(code(&run(&store, &expr, None, Some(&rec))), CODE_TYPE_MISMATCH);
    assert_eq!(rec.calls.load(Ordering::SeqCst), 0);
}

/// §2.1 SA-4 — a bare primitive (`primitive/any`) comes back as `compute/result` naming the apply;
/// a `compute/result` already is not wrapped twice.
#[test]
fn a_bare_primitive_return_is_rewrapped_and_a_result_is_not() {
    let store = store_with_handler();
    let expr = apply(&store, vec![("path", text("app/h")), ("operation", text("run"))]);

    let rec = Recorder::replying(200, Entity::make("primitive/any", Value::UInt(42)));
    let out = run(&store, &expr, None, Some(&rec));
    let result = out.entity.expect("an entity");
    assert_eq!(result.typ, RESULT);
    assert_eq!(result.uint_field("value"), Some(42));
    assert_eq!(result.bytes_field("expression"), Some(expr.hash.as_slice()));

    let inner = Entity::make(RESULT, map(vec![("value", Value::UInt(1))]));
    let rec = Recorder::replying(200, inner.clone());
    assert_eq!(run(&store, &expr, None, Some(&rec)).entity, Some(inner));
}

/// `>= 400`: a dispatched `compute/error` is that error; a `403` is `permission_denied` as a value
/// (§3.2 v3.19c); anything else is `not_found`. An operation declaring no input type dispatches a
/// `primitive/any` params entity.
#[test]
fn a_failed_dispatch_maps_to_its_compute_error_permission_denied_or_not_found() {
    let store = store_with_handler();
    let expr = apply(&store, vec![("path", text("app/h")), ("operation", text("bare"))]);

    let rec = Recorder::replying(403, Entity::make("system/protocol/error", map(vec![("code", text("capability_denied"))])));
    assert_eq!(code(&run(&store, &expr, None, Some(&rec))), CODE_PERMISSION_DENIED);
    assert_eq!(rec.last.lock().unwrap().as_ref().unwrap().3.typ, "primitive/any");

    let rec = Recorder::replying(500, Entity::make("system/protocol/error", map(vec![("code", text("internal_error"))])));
    assert_eq!(code(&run(&store, &expr, None, Some(&rec))), CODE_NOT_FOUND);

    let rec = Recorder::replying(400, Entity::make(ERROR, map(vec![("code", text("division_by_zero"))])));
    assert_eq!(code(&run(&store, &expr, None, Some(&rec))), "division_by_zero");
}

/// §4.1 — `resolve_handler` and the operation lookup come BEFORE the args: an unresolvable arg does
/// not mask either code, and nothing is dispatched. Resolution is longest-prefix, so a sub-path
/// reads the enclosing handler's declared input type.
#[test]
fn the_handler_and_operation_are_resolved_before_any_arg_and_by_longest_prefix() {
    let store = store_with_handler();
    let broken_arg = Value::Map(vec![(Key::Text("n".into()), Value::Bytes(vec![0; 33]))]);
    let rec = Recorder::replying(200, Entity::make("app/out", map(vec![])));

    let nowhere = apply(&store, vec![("path", text("app/nowhere")), ("operation", text("run")), ("args", broken_arg.clone())]);
    assert_eq!(code(&run(&store, &nowhere, None, Some(&rec))), CODE_NOT_FOUND);
    let undeclared = apply(&store, vec![("path", text("app/h")), ("operation", text("nope")), ("args", broken_arg)]);
    assert_eq!(code(&run(&store, &undeclared, None, Some(&rec))), CODE_INVALID_EXPRESSION);
    assert_eq!(rec.calls.load(Ordering::SeqCst), 0);

    let sub = apply(&store, vec![("path", text("app/h/deeper")), ("operation", text("run"))]);
    run(&store, &sub, None, Some(&rec));
    assert_eq!(rec.last.lock().unwrap().as_ref().expect("dispatched").3.typ, "app/in");
}

/// §2.1 [MUST] — `path` and `fn` together is invalid, and handler mode is not entered.
#[test]
fn path_and_fn_together_is_invalid_and_not_dispatched() {
    let store = store_with_handler();
    let expr = apply(&store, vec![("path", text("app/h")), ("operation", text("run")), ("fn", Value::Bytes(vec![0; 33]))]);
    let rec = Recorder::replying(200, Entity::make("app/out", map(vec![])));
    assert_eq!(code(&run(&store, &expr, None, Some(&rec))), CODE_INVALID_EXPRESSION);
    assert_eq!(rec.calls.load(Ordering::SeqCst), 0);
}

/// §7.2's reactive path has no request context: handler mode names that instead of guessing.
#[test]
fn with_no_dispatcher_handler_mode_is_invalid_expression_naming_why() {
    let store = store_with_handler();
    let expr = apply(&store, vec![("path", text("app/h")), ("operation", text("run"))]);
    let out = run(&store, &expr, None, None);
    assert_eq!(code(&out), CODE_INVALID_EXPRESSION);
    assert!(out.error.unwrap().detail.contains("handler dispatch not available"));
}

/// F2 — the dual check. The provided capability must cover the target, AND so must `ctx.capability`.
/// Each denial is `permission_denied` with the dispatcher never called; the ALLOW arm dispatches
/// under the PROVIDED capability and carries the resource through (F4).
#[test]
fn the_dual_check_denies_on_either_capability_and_dispatches_under_the_provided_one() {
    let store = store_with_handler();
    let resource = literal(&store, map(vec![("targets", Value::Array(vec![text("app/h/x")]))]));
    let wide = token(&["*"]);
    let narrow = token(&["app/elsewhere"]);
    let with_cap = |cap: &Entity| {
        let cap_lit = put(&store, Entity::make(LOOKUP_HASH, map(vec![("hash", Value::Bytes(put(&store, cap.clone())))])));
        apply(
            &store,
            vec![
                ("path", text("app/h")),
                ("operation", text("run")),
                ("resource", Value::Bytes(resource.clone())),
                ("capability", Value::Bytes(cap_lit)),
            ],
        )
    };

    // provided does not cover
    let rec = Recorder::replying(200, Entity::make("app/out", map(vec![])));
    assert_eq!(code(&run(&store, &with_cap(&narrow), Some(&wide), Some(&rec))), CODE_PERMISSION_DENIED);
    assert_eq!(rec.calls.load(Ordering::SeqCst), 0);

    // the ceiling does not cover
    let rec = Recorder::replying(200, Entity::make("app/out", map(vec![])));
    assert_eq!(code(&run(&store, &with_cap(&wide), Some(&narrow), Some(&rec))), CODE_PERMISSION_DENIED);
    assert_eq!(rec.calls.load(Ordering::SeqCst), 0);

    // no ceiling at all — FAIL CLOSED rather than skip the half of the check it cannot make
    let rec = Recorder::replying(200, Entity::make("app/out", map(vec![])));
    assert_eq!(code(&run(&store, &with_cap(&wide), None, Some(&rec))), CODE_PERMISSION_DENIED);
    assert_eq!(rec.calls.load(Ordering::SeqCst), 0);

    // both cover
    let rec = Recorder::replying(200, Entity::make("app/out", map(vec![])));
    let out = run(&store, &with_cap(&wide), Some(&wide), Some(&rec));
    assert_eq!(out.entity.map(|e| e.typ), Some("app/out".to_string()));
    let (_, _, res, _, cap) = rec.last.lock().unwrap().take().unwrap();
    assert_eq!(cap.map(|c| c.hash), Some(wide.hash.clone()));
    assert_eq!(res, Some(map(vec![("targets", Value::Array(vec![text("app/h/x")]))])));
}
