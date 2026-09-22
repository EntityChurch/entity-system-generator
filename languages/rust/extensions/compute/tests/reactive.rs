//! §3 and §7 — the handler body and the reactive engine, against a REAL peer's store and emit bus.
//!
//! These tests drive `ComputeHandler::handle` directly with a [`HandlerRequest`], because a third
//! party cannot construct the peer's `HandlerContext`. What they measure is the body and the engine;
//! dispatch through `Peer::register_handler` is measured by the composed run and by
//! `languages/rust/gates/host-seam`. The emit consumer IS real: `install_compute` registers it on the
//! peer's own `Store::register_tree_consumer`, and every write below goes through the peer's own bus.

mod common;

use std::collections::BTreeMap;
use std::sync::mpsc;
use std::sync::Arc;
use std::time::Duration;

use common::*;
use entity_compute::*;
use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::ExecContext;
use entity_core_protocol::peer::wire::{self, ExecuteFields};
use entity_core_protocol::peer::Peer;
use entity_core_protocol::value::Value;

// ── §3.3 `deterministic_id` ─────────────────────────────────────────────────────────

/// **THE EXPECTATIONS ARE `entity-core-go`'s OUTPUT**, produced by `deterministicID` in
/// `ext/compute/engine.go` and carried unchanged in the `typescript` and `python` suites. No
/// `validate-peer` check reads `subgraph_path` back, so this is the only thing that keeps three
/// implementations of one cross-peer identity from drifting apart silently.
#[test]
fn deterministic_id_agrees_with_the_reference_vector_for_vector() {
    let reference = [
        (
            "/peer/app/cell/A1",
            "ffb4c3uopfuogfzn35cv7wdmsgf74ubjlpntxey64wr4dh6fgqoq",
        ),
        (
            "app/cell/A1",
            "mijknkgplgoibnth6mdfl3kerwp22d7w73jqfae4dtrw7xzz6gra",
        ),
        ("", "4oymiquy7qobjgx36tejs35zeqt24qpemsnzgtfeswmrw6csxbkq"),
        ("a", "zklycewkdo64v6wcggzzui64jwtyn37ycr6e44vzqb3yll7ojc5q"),
    ];
    for (path, expected) in reference {
        assert_eq!(
            deterministic_id(path),
            expected,
            "deterministic_id({path:?})"
        );
        assert_eq!(deterministic_id(path).len(), 52);
    }
    // THE NEGATIVE: a constant function would pass nothing above, but the guard is the one that
    // survives a re-pin replacing the vectors.
    let ids: std::collections::HashSet<_> = ["a", "b", "app/x", "app/y", ""]
        .iter()
        .map(|p| deterministic_id(p))
        .collect();
    assert_eq!(ids.len(), 5);
}

// ── fixtures ────────────────────────────────────────────────────────────────────────

struct Installed {
    peer: Arc<Peer>,
    handler: ComputeHandler,
    engine: Arc<ReactiveEngine>,
    cap: Entity,
}

fn installed() -> Installed {
    let peer = peer();
    let reactive = install_compute(&peer, DEFAULT_LIMITS).expect("install COMPUTE on a fresh peer");
    let cap = token(&peer.identity.identity_hash, &["*"], &["*"], &["*"]);
    Installed {
        handler: ComputeHandler::new(Some(reactive.engine.clone()), DEFAULT_LIMITS),
        engine: reactive.engine,
        peer,
        cap,
    }
}

fn resource(path: &str) -> Value {
    map(vec![("targets", Value::Array(vec![text(path)]))])
}

fn exec(p: &Peer, operation: &str, target: &str, params: Entity) -> Entity {
    wire::make_execute(ExecuteFields {
        request_id: "r1",
        uri: &abs(p, COMPUTE_PATTERN),
        operation,
        params,
        resource: Some(resource(target)),
        author: Some(&p.identity.identity_hash),
        capability: None,
    })
}

fn call(
    inst: &Installed,
    operation: &str,
    target: &str,
    params: Entity,
    cap: Option<&Entity>,
) -> ComputeOutcome {
    let e = exec(&inst.peer, operation, target, params);
    let included = BTreeMap::new();
    inst.handler.handle(
        operation,
        &HandlerRequest {
            exec: &e,
            store: &inst.peer.store,
            local_peer: &inst.peer.local_peer,
            caller_capability: cap,
            included: &included,
            context: None,
        },
    )
}

fn empty_install_request() -> Entity {
    entity(INSTALL_REQUEST, vec![])
}

/// `B1 = A1.value * 2`, installed through the HANDLER, so the handler's four phases, the engine's
/// registration and the peer's emit bus are measured together.
fn install_spreadsheet(inst: &Installed) -> (String, String) {
    let p = &inst.peer;
    p.store.bind(
        &abs(p, "app/A1"),
        &entity("app/cell", vec![("value", int(21))]),
    );
    let cell = put(
        &p.store,
        entity(LOOKUP_TREE, vec![("path", text("app/A1"))]),
    );
    let field = put(
        &p.store,
        entity(
            FIELD,
            vec![("name", text("value")), ("entity", bytes(&cell))],
        ),
    );
    let two = literal(&p.store, int(2));
    p.store.bind(
        &abs(p, "app/B1"),
        &entity(
            ARITHMETIC,
            vec![
                ("op", text("mul")),
                ("left", bytes(&field)),
                ("right", bytes(&two)),
            ],
        ),
    );
    let out = call(
        inst,
        "install",
        &abs(p, "app/B1"),
        empty_install_request(),
        Some(&inst.cap),
    );
    assert_eq!(out.status, 200, "{:?}", out.result);
    (
        out.result.text_field("subgraph_path").unwrap().to_string(),
        out.result.text_field("result_path").unwrap().to_string(),
    )
}

fn result_value(p: &Peer, path: &str) -> Option<Value> {
    p.store.get_at(path).and_then(|e| e.field("value").cloned())
}

// ── §3.2 eval ───────────────────────────────────────────────────────────────────────

#[test]
fn eval_returns_a_result_and_an_evaluated_error_at_status_200() {
    let inst = installed();
    let p = &inst.peer;
    let one = literal(&p.store, int(1));
    p.store.bind(
        &abs(p, "app/e"),
        &entity(
            ARITHMETIC,
            vec![
                ("op", text("add")),
                ("left", bytes(&one)),
                ("right", bytes(&one)),
            ],
        ),
    );
    let out = call(
        &inst,
        "eval",
        &abs(p, "app/e"),
        wire::empty_params(),
        Some(&inst.cap),
    );
    assert_eq!((out.status, out.result.typ.as_str()), (200, RESULT));
    assert_eq!(out.result.field("value"), Some(&int(2)));

    let zero = literal(&p.store, int(0));
    p.store.bind(
        &abs(p, "app/bad"),
        &entity(
            ARITHMETIC,
            vec![
                ("op", text("div")),
                ("left", bytes(&one)),
                ("right", bytes(&zero)),
            ],
        ),
    );
    let out = call(
        &inst,
        "eval",
        &abs(p, "app/bad"),
        wire::empty_params(),
        Some(&inst.cap),
    );
    assert_eq!(
        (out.status, out.result.typ.as_str()),
        (200, ERROR),
        "F10: a computed error is a VALUE at 200"
    );
}

#[test]
fn eval_refusals_are_in_section_3_2_order_with_their_own_codes() {
    let inst = installed();
    let p = &inst.peer;
    assert_eq!(
        call(
            &inst,
            "eval",
            &abs(p, "app/missing"),
            wire::empty_params(),
            None
        )
        .status,
        404
    );
    p.store.bind(&abs(p, "app/data"), &entity("app/v", vec![]));
    let out = call(
        &inst,
        "eval",
        &abs(p, "app/data"),
        wire::empty_params(),
        None,
    );
    assert_eq!(
        (out.status, out.result.text_field("code")),
        (400, Some(CODE_INVALID_EXPRESSION))
    );
    assert_eq!(
        call(
            &inst,
            "teleport",
            &abs(p, "app/data"),
            wire::empty_params(),
            None
        )
        .status,
        400
    );
}

#[test]
fn eval_narrows_the_tree_read_with_the_callers_capability() {
    let inst = installed();
    let p = &inst.peer;
    p.store.bind(
        &abs(p, "app/secret/x"),
        &entity("app/v", vec![("n", int(1))]),
    );
    p.store.bind(
        &abs(p, "app/e"),
        &entity(LOOKUP_TREE, vec![("path", text("app/secret/x"))]),
    );

    let narrow = token(
        &p.identity.identity_hash,
        &["*"],
        &[&format!("/{}/app/allowed/*", p.local_peer)],
        &["*"],
    );
    let out = call(
        &inst,
        "eval",
        &abs(p, "app/e"),
        wire::empty_params(),
        Some(&narrow),
    );
    assert_eq!(out.result.text_field("code"), Some(CODE_PERMISSION_DENIED));
    // THE CONTROL: the wide grant reads the same path.
    let out = call(
        &inst,
        "eval",
        &abs(p, "app/e"),
        wire::empty_params(),
        Some(&inst.cap),
    );
    assert_eq!(out.result.typ, "app/v");
}

// ── §3.3 install ────────────────────────────────────────────────────────────────────

#[test]
fn install_registers_a_dependency_and_performs_the_initial_evaluation() {
    let inst = installed();
    let (subgraph_path, result_path) = install_spreadsheet(&inst);
    let p = &inst.peer;
    assert_eq!(
        subgraph_path,
        format!(
            "{}/{}",
            abs(p, PROCESSES_PREFIX),
            deterministic_id(&abs(p, "app/B1"))
        )
    );
    assert_eq!(inst.engine.registered_dependencies(), 1);
    assert_eq!(result_value(p, &result_path), Some(int(42)));
    let meta = p.store.get_at(&subgraph_path).unwrap();
    assert_eq!(meta.text_field("status"), Some("active"));
    assert_eq!(
        meta.bytes_field("installation_grant"),
        Some(inst.cap.hash.as_slice())
    );
    assert!(
        p.store.get_by_hash(&inst.cap.hash).is_some(),
        "the grant reaches the content store before its hash is recorded"
    );
}

#[test]
fn install_refuses_without_an_engine_without_a_capability_and_under_a_narrow_grant() {
    let inst = installed();
    let p = &inst.peer;
    p.store.bind(
        &abs(p, "app/A1"),
        &entity("app/cell", vec![("value", int(1))]),
    );
    p.store.bind(
        &abs(p, "app/B1"),
        &entity(LOOKUP_TREE, vec![("path", text("app/A1"))]),
    );

    let no_engine = ComputeHandler::new(None, DEFAULT_LIMITS);
    let e = exec(p, "install", &abs(p, "app/B1"), empty_install_request());
    let included = BTreeMap::new();
    let req = HandlerRequest {
        exec: &e,
        store: &p.store,
        local_peer: &p.local_peer,
        caller_capability: Some(&inst.cap),
        included: &included,
        context: None,
    };
    assert_eq!(no_engine.handle("install", &req).status, 501);

    assert_eq!(
        call(
            &inst,
            "install",
            &abs(p, "app/B1"),
            empty_install_request(),
            None
        )
        .status,
        403
    );

    let narrow = token(
        &p.identity.identity_hash,
        &["*"],
        &[&format!("/{}/app/B1/*", p.local_peer)],
        &["*"],
    );
    let out = call(
        &inst,
        "install",
        &abs(p, "app/B1"),
        empty_install_request(),
        Some(&narrow),
    );
    assert_eq!(
        out.status, 403,
        "the dependency read on app/A1 is not covered"
    );
    assert!(out
        .result
        .text_field("message")
        .unwrap_or("")
        .contains("app/A1"));
    // Pre-flight before commit: the refused install wrote nothing.
    assert!(p
        .store
        .get_at(&format!(
            "{}/{}",
            abs(p, PROCESSES_PREFIX),
            deterministic_id(&abs(p, "app/B1"))
        ))
        .is_none());
}

/// A-17: §3.3's listing descends no container; the walker here does, so a read one argument deep is
/// audited. The NEGATIVE half is the narrow grant that covers only the top-level read.
#[test]
fn install_audits_a_tree_read_nested_inside_apply_args() {
    let inst = installed();
    let p = &inst.peer;
    p.store
        .bind(&abs(p, "app/deep"), &entity("app/cell", vec![]));
    let deep = put(
        &p.store,
        entity(LOOKUP_TREE, vec![("path", text("app/deep"))]),
    );
    let x = put(&p.store, entity(LOOKUP_SCOPE, vec![("name", text("x"))]));
    let lam = put(
        &p.store,
        entity(
            LAMBDA,
            vec![
                ("params", Value::Array(vec![text("x")])),
                ("body", bytes(&x)),
            ],
        ),
    );
    p.store.bind(
        &abs(p, "app/root"),
        &entity(
            APPLY,
            vec![
                ("fn", bytes(&lam)),
                ("args", map(vec![("x", bytes(&deep))])),
            ],
        ),
    );

    let only_root = token(
        &p.identity.identity_hash,
        &["*"],
        &[&format!("/{}/app/root/*", p.local_peer)],
        &["*"],
    );
    assert_eq!(
        call(
            &inst,
            "install",
            &abs(p, "app/root"),
            empty_install_request(),
            Some(&only_root)
        )
        .status,
        403
    );
    assert_eq!(
        call(
            &inst,
            "install",
            &abs(p, "app/root"),
            empty_install_request(),
            Some(&inst.cap)
        )
        .status,
        200
    );
    assert!(inst.engine.watched_paths().contains(&abs(p, "app/deep")));
}

#[test]
fn a_lookup_scope_is_not_a_tree_dependency_and_the_index_is_exact_match() {
    let inst = installed();
    let (_, result_path) = install_spreadsheet(&inst);
    let p = &inst.peer;
    assert_eq!(inst.engine.watched_paths(), vec![abs(p, "app/A1")]);
    // A write BELOW the dependency does not wake it.
    p.store.bind(
        &abs(p, "app/A1/child"),
        &entity("app/cell", vec![("value", int(1000))]),
    );
    assert_eq!(result_value(p, &result_path), Some(int(42)));
}

// ── §7.2 — the trigger, through the peer's own bus ──────────────────────────────────

#[test]
fn a_dependency_write_re_evaluates_synchronously_before_the_bind_returns() {
    let inst = installed();
    let (_, result_path) = install_spreadsheet(&inst);
    let p = &inst.peer;
    p.store.bind(
        &abs(p, "app/A1"),
        &entity("app/cell", vec![("value", int(25))]),
    );
    assert_eq!(
        result_value(p, &result_path),
        Some(int(50)),
        "no wait: delivery is sync-inline"
    );
}

/// Subgraph B depends on A's RESULT path, so A's result write re-enters the bus and wakes B. On
/// this peer that re-entry takes the consumer list's read lock a second time on one thread.
#[test]
fn a_write_from_inside_a_consumer_re_enters_the_bus_and_a_chain_cascades() {
    let inst = installed();
    let (_, a_result) = install_spreadsheet(&inst);
    let p = &inst.peer;
    let a = put(
        &p.store,
        entity(LOOKUP_TREE, vec![("path", text(&a_result))]),
    );
    let v = put(
        &p.store,
        entity(FIELD, vec![("name", text("value")), ("entity", bytes(&a))]),
    );
    let one = literal(&p.store, int(1));
    p.store.bind(
        &abs(p, "app/C1"),
        &entity(
            ARITHMETIC,
            vec![
                ("op", text("add")),
                ("left", bytes(&v)),
                ("right", bytes(&one)),
            ],
        ),
    );
    let out = call(
        &inst,
        "install",
        &abs(p, "app/C1"),
        empty_install_request(),
        Some(&inst.cap),
    );
    assert_eq!(out.status, 200);
    let c_result = out.result.text_field("result_path").unwrap().to_string();
    assert_eq!(result_value(p, &c_result), Some(int(43)));

    p.store.bind(
        &abs(p, "app/A1"),
        &entity("app/cell", vec![("value", int(100))]),
    );
    assert_eq!(result_value(p, &a_result), Some(int(200)));
    assert_eq!(
        result_value(p, &c_result),
        Some(int(201)),
        "A's result write woke C"
    );
}

/// **AP-33 / D15's sharpened clause.** The peer's `bind` suppresses an identical rebind by itself,
/// so "no event fired" passes with our convergence check deleted. `evaluate_now`'s RETURN is what
/// only the subject can produce: `None` on convergence, a hash when the result moved.
#[test]
fn convergence_is_decided_by_our_check_not_by_the_stores_suppression() {
    let inst = installed();
    let (subgraph_path, result_path) = install_spreadsheet(&inst);
    let p = &inst.peer;
    assert_eq!(
        inst.engine.evaluate_now(&subgraph_path, None),
        None,
        "unchanged inputs: no write"
    );

    // THE CONTROL: perturb the stored result (not a dependency, so nothing re-evaluates), and the
    // next evaluation must write and report the hash it wrote.
    p.store.bind(
        &result_path,
        &entity(
            RESULT,
            vec![("value", int(0)), ("expression", bytes(&[0; 33]))],
        ),
    );
    let written = inst
        .engine
        .evaluate_now(&subgraph_path, None)
        .expect("a moved result is written");
    assert_eq!(p.store.hash_at(&result_path), Some(written));
    assert_eq!(result_value(p, &result_path), Some(int(42)));
}

#[test]
fn a_missing_or_expired_installation_grant_freezes_the_subgraph() {
    let inst = installed();
    let (subgraph_path, result_path) = install_spreadsheet(&inst);
    let p = &inst.peer;

    // Expired: rewrite the metadata to point at a grant whose expires_at is in the past.
    let mut expired = token(&p.identity.identity_hash, &["*"], &["*"], &["*"]);
    if let Value::Map(entries) = &mut expired.data {
        entries.push((
            entity_core_protocol::value::Key::Text("expires_at".into()),
            Value::UInt(1),
        ));
    }
    let expired = Entity::make(&expired.typ, expired.data);
    p.store.put_entity(&expired);
    let meta = p.store.get_at(&subgraph_path).unwrap();
    let mut data = match meta.data.clone() {
        Value::Map(e) => e,
        _ => unreachable!(),
    };
    for (k, v) in data.iter_mut() {
        if matches!(k, entity_core_protocol::value::Key::Text(t) if t == "installation_grant") {
            *v = Value::Bytes(expired.hash.clone());
        }
    }
    p.store
        .bind(&subgraph_path, &Entity::make(SUBGRAPH, Value::Map(data)));

    p.store.bind(
        &abs(p, "app/A1"),
        &entity("app/cell", vec![("value", int(5))]),
    );
    let result = p.store.get_at(&result_path).unwrap();
    assert_eq!(
        (result.typ.as_str(), result.text_field("code")),
        (ERROR, Some(CODE_INSTALLATION_GRANT_INVALID))
    );
    assert_eq!(
        p.store.get_at(&subgraph_path).unwrap().text_field("status"),
        Some("frozen")
    );

    // A frozen subgraph is skipped: a further write changes nothing.
    p.store.bind(
        &abs(p, "app/A1"),
        &entity("app/cell", vec![("value", int(6))]),
    );
    assert_eq!(
        p.store.get_at(&result_path).unwrap().text_field("code"),
        Some(CODE_INSTALLATION_GRANT_INVALID)
    );
}

#[test]
fn a_valid_grant_does_not_freeze() {
    let inst = installed();
    let (subgraph_path, _) = install_spreadsheet(&inst);
    let p = &inst.peer;
    p.store.bind(
        &abs(p, "app/A1"),
        &entity("app/cell", vec![("value", int(7))]),
    );
    assert_eq!(
        p.store.get_at(&subgraph_path).unwrap().text_field("status"),
        Some("active")
    );
}

/// §7.3 — a subgraph whose result feeds its own dependency, with a STRICTLY INCREASING expression so
/// it can never converge. It must end frozen with `cascade_limit`, not recurse until the stack dies.
///
/// **Behind a timeout, on its own thread**, because on this substrate the two failures being looked
/// for are a HANG (a recursive `RwLock` read that deadlocks) and an ABORT (stack overflow), and a
/// test that hangs reports nothing.
#[test]
fn a_self_feeding_cascade_terminates_frozen_not_as_a_hang_or_an_abort() {
    let (tx, rx) = mpsc::channel();
    std::thread::Builder::new()
        .stack_size(64 * 1024 * 1024)
        .spawn(move || {
            let inst = installed();
            let p = &inst.peer;
            let result_path = abs(p, "app/loop/result");
            p.store.bind(
                &result_path,
                &entity(
                    RESULT,
                    vec![("value", int(0)), ("expression", bytes(&[0; 33]))],
                ),
            );
            let prev = put(
                &p.store,
                entity(LOOKUP_TREE, vec![("path", text(&result_path))]),
            );
            let v = put(
                &p.store,
                entity(
                    FIELD,
                    vec![("name", text("value")), ("entity", bytes(&prev))],
                ),
            );
            let one = literal(&p.store, int(1));
            p.store.bind(
                &abs(p, "app/loop"),
                &entity(
                    ARITHMETIC,
                    vec![
                        ("op", text("add")),
                        ("left", bytes(&v)),
                        ("right", bytes(&one)),
                    ],
                ),
            );
            let out = call(
                &inst,
                "install",
                &abs(p, "app/loop"),
                empty_install_request(),
                Some(&inst.cap),
            );
            let subgraph = out.result.text_field("subgraph_path").map(str::to_string);
            let status = subgraph
                .and_then(|s| p.store.get_at(&s))
                .and_then(|m| m.text_field("status").map(str::to_string));
            let code = p
                .store
                .get_at(&result_path)
                .and_then(|r| r.text_field("code").map(str::to_string));
            tx.send((out.status, status, code)).ok();
        })
        .unwrap();
    let (status, meta_status, code) = rx
        .recv_timeout(Duration::from_secs(30))
        .expect("the cascade HUNG");
    assert_eq!(status, 200);
    assert_eq!(meta_status.as_deref(), Some("frozen"));
    assert_eq!(code.as_deref(), Some(CODE_CASCADE_LIMIT));
}

/// THE NEGATIVE for the test above: a self-reference that CONVERGES never freezes. Without it, a
/// freeze on every self-dependency would pass the cascade test.
#[test]
fn a_converging_self_reference_does_not_freeze() {
    let inst = installed();
    let p = &inst.peer;
    let result_path = abs(p, "app/fix/result");
    let prev = put(
        &p.store,
        entity(LOOKUP_TREE, vec![("path", text(&result_path))]),
    );
    let _ = prev;
    // `fix = 5`, with a dependency on its own result path that it never changes.
    let dep = put(
        &p.store,
        entity(LOOKUP_TREE, vec![("path", text("app/fix/seed"))]),
    );
    let five = literal(&p.store, int(5));
    let body = put(
        &p.store,
        entity(
            IF,
            vec![
                ("condition", bytes(&five)),
                ("then", bytes(&five)),
                ("else", bytes(&dep)),
            ],
        ),
    );
    p.store
        .bind(&abs(p, "app/fix/seed"), &entity("app/v", vec![]));
    p.store
        .bind(&abs(p, "app/fix"), &p.store.get_by_hash(&body).unwrap());
    let out = call(
        &inst,
        "install",
        &abs(p, "app/fix"),
        empty_install_request(),
        Some(&inst.cap),
    );
    assert_eq!(out.status, 200);
    let subgraph = out.result.text_field("subgraph_path").unwrap().to_string();
    p.store.bind(
        &abs(p, "app/fix/seed"),
        &entity("app/v", vec![("n", int(1))]),
    );
    assert_eq!(
        p.store.get_at(&subgraph).unwrap().text_field("status"),
        Some("active")
    );
}

// ── §7.1 rebuild, §3.4 uninstall, §7.4 budget ───────────────────────────────────────

#[test]
fn rebuild_re_registers_from_the_metadata_on_disk_reading_the_current_expression() {
    let inst = installed();
    let (subgraph_path, _) = install_spreadsheet(&inst);
    let p = &inst.peer;
    inst.engine.unregister(&subgraph_path);
    assert_eq!(inst.engine.registered_dependencies(), 0);
    // Change the expression at the root path: rebuild must read THIS, not the installed hash.
    p.store.bind(
        &abs(p, "app/B1"),
        &entity(LOOKUP_TREE, vec![("path", text("app/Z9"))]),
    );
    assert_eq!(inst.engine.rebuild(), 1);
    assert_eq!(inst.engine.watched_paths(), vec![abs(p, "app/Z9")]);
}

#[test]
fn uninstall_clears_registrations_leaves_the_expression_and_404s_a_non_subgraph() {
    let inst = installed();
    let (subgraph_path, _) = install_spreadsheet(&inst);
    let p = &inst.peer;
    assert_eq!(
        call(
            &inst,
            "uninstall",
            &subgraph_path,
            wire::empty_params(),
            None
        )
        .status,
        200
    );
    assert_eq!(inst.engine.registered_dependencies(), 0);
    assert!(p.store.get_at(&subgraph_path).is_none());
    assert!(
        p.store.get_at(&abs(p, "app/B1")).is_some(),
        "§3.4: the expression stays in the tree"
    );
    assert_eq!(
        call(
            &inst,
            "uninstall",
            &abs(p, "app/B1"),
            wire::empty_params(),
            None
        )
        .status,
        404
    );
}

#[test]
fn the_reactive_budget_takes_the_tightest_constraint_across_grant_entries() {
    let inst = installed();
    let p = &inst.peer;
    // A chain that needs ~7 steps; a grant entry capping max_compute_operations at 3 must starve it.
    p.store.bind(
        &abs(p, "app/A1"),
        &entity("app/cell", vec![("value", int(1))]),
    );
    let cell = put(
        &p.store,
        entity(LOOKUP_TREE, vec![("path", text("app/A1"))]),
    );
    let field = put(
        &p.store,
        entity(
            FIELD,
            vec![("name", text("value")), ("entity", bytes(&cell))],
        ),
    );
    let two = literal(&p.store, int(2));
    p.store.bind(
        &abs(p, "app/B1"),
        &entity(
            ARITHMETIC,
            vec![
                ("op", text("mul")),
                ("left", bytes(&field)),
                ("right", bytes(&two)),
            ],
        ),
    );

    let scope = |items: &[&str]| {
        map(vec![(
            "include",
            Value::Array(items.iter().map(|s| text(s)).collect()),
        )])
    };
    let grant_entry = |ops: u64| {
        map(vec![
            ("handlers", scope(&["*"])),
            ("resources", scope(&["*"])),
            ("operations", scope(&["*"])),
            (
                "constraints",
                map(vec![(
                    COMPUTE_PATTERN,
                    map(vec![("max_compute_operations", Value::UInt(ops))]),
                )]),
            ),
        ])
    };
    let constrained = entity(
        "system/capability/token",
        vec![
            (
                "grants",
                Value::Array(vec![grant_entry(1000), grant_entry(3)]),
            ),
            ("granter", bytes(&p.identity.identity_hash)),
        ],
    );
    let out = call(
        &inst,
        "install",
        &abs(p, "app/B1"),
        empty_install_request(),
        Some(&constrained),
    );
    assert_eq!(out.status, 200);
    let result = p
        .store
        .get_at(out.result.text_field("result_path").unwrap())
        .unwrap();
    assert_eq!(
        result.text_field("code"),
        Some(CODE_BUDGET_EXHAUSTED),
        "the tighter of 1000 and 3"
    );
}

/// The writes our engine makes carry an execution context: inherited `chain_id`, the local peer as
/// `author`, no caller capability, and a cascade depth one past the incoming one.
#[test]
fn reactive_writes_carry_an_inherited_execution_context() {
    let inst = installed();
    let (_, result_path) = install_spreadsheet(&inst);
    let p = &inst.peer;
    let seen = Arc::new(std::sync::Mutex::new(
        Vec::<(String, Option<ExecContext>)>::new(),
    ));
    let sink = seen.clone();
    p.store.register_tree_consumer(move |ev| {
        sink.lock()
            .unwrap()
            .push((ev.path.clone(), ev.context.clone()))
    });
    let ctx = ExecContext {
        chain_id: Some("chain-7".into()),
        cascade_depth: Some(2),
        ..Default::default()
    };
    p.store.bind_with_context(
        &abs(p, "app/A1"),
        &entity("app/cell", vec![("value", int(9))]),
        Some(ctx),
    );
    let seen = seen.lock().unwrap();
    let (_, written) = seen
        .iter()
        .find(|(path, _)| path == &result_path)
        .expect("the result write was observed");
    let written = written.as_ref().expect("our write carries a context");
    assert_eq!(written.chain_id.as_deref(), Some("chain-7"));
    assert_eq!(written.cascade_depth, Some(3));
    assert_eq!(
        written.author.as_deref(),
        Some(p.identity.identity_hash.as_slice())
    );
    assert_eq!(written.caller_capability, None);
    assert_eq!(written.handler_pattern, COMPUTE_PATTERN);
}
