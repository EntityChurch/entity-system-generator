//! The public install surface, and the §4 override guard.
//!
//! The POSITIVE half of the §3.4 boundary lives here: the public routes' exact signatures, named as
//! function pointers so a change to any of them fails to compile. `src/bin/deep_import.rs` is the
//! negative half, and `languages/rust/test` requires it to fail with E0603.

mod common;

use std::sync::Arc;

use common::*;
use entity_compute::*;
use entity_core_protocol::peer::handler::RegisterError;
use entity_core_protocol::peer::Peer;

#[test]
fn the_public_routes_have_the_signatures_the_composition_calls() {
    let _: fn(&Arc<Peer>, EvaluatorLimits) -> Result<ComputeInstallation, RegisterError> = install_compute;
    let _: fn(&str) -> Result<(), String> = assert_not_builtin_override;
    let _: fn(&str) -> String = deterministic_id;
    assert!(!CAPABILITY_CHECK_IS_DISPATCH_SCOPED);
    assert_eq!(DEFAULT_LIMITS, EvaluatorLimits { max_operations: DEFAULT_MAX_OPS, max_depth: DEFAULT_MAX_DEPTH });
}

/// Every face `install_compute` claims, read back off the peer rather than off the return value:
/// the four §11.6.1 entities `register_handler` binds, the 33 types, the native body in the
/// container `route` reads, and the evaluator the H7 seam holds.
#[test]
fn install_compute_installs_every_face_and_reads_the_evaluator_back() {
    let p = peer();
    assert!(!p.has_native_handler(COMPUTE_PATTERN), "control: a fresh peer has no body at the pattern");
    assert!(p.expression_evaluator().is_none(), "control: a fresh peer has no evaluator");

    let installed = install_compute(&p, DEFAULT_LIMITS).expect("install");
    assert_eq!(installed.type_paths.len(), 33);
    for (name, entity) in compute_type_entities() {
        let path = abs(&p, &format!("system/type/{name}"));
        assert!(installed.type_paths.contains(&path));
        assert_eq!(p.store.get_at(&path), Some(entity));
    }
    assert!(p.has_native_handler(COMPUTE_PATTERN));
    assert_eq!(p.store.get_at(&abs(&p, COMPUTE_PATTERN)).map(|e| e.typ), Some("system/handler".to_string()));
    assert_eq!(installed.interface_path, abs(&p, &format!("system/handler/{COMPUTE_PATTERN}")));
    assert!(p.store.get_at(&installed.interface_path).is_some());
    assert!(p.store.get_at(&abs(&p, &format!("system/capability/grants/{COMPUTE_PATTERN}"))).is_some());
    assert_eq!(installed.evaluator_face, "installed");
    assert!(p.expression_evaluator().is_some());
}

/// H3's refusal, surfaced rather than swallowed: a second install at the same pattern is an error,
/// and it is refused BEFORE the second call writes anything — the evaluator the first install set is
/// still the one the peer holds.
#[test]
fn a_second_install_is_refused_and_leaves_the_first_in_place() {
    let p = peer();
    install_compute(&p, DEFAULT_LIMITS).expect("first install");
    let first = p.expression_evaluator().expect("evaluator after the first install");
    match install_compute(&p, DEFAULT_LIMITS) {
        Err(RegisterError::PatternCollision(pattern)) => assert_eq!(pattern, COMPUTE_PATTERN),
        Err(other) => panic!("expected PatternCollision, got {other:?}"),
        Ok(_) => panic!("a second install at {COMPUTE_PATTERN} was accepted"),
    }
    assert!(Arc::ptr_eq(&first, &p.expression_evaluator().unwrap()));
}

#[test]
fn the_override_guard_refuses_a_builtin_pattern_and_not_a_near_miss_or_our_own() {
    for bad in [BUILTINS_PREFIX.to_string(), format!("{BUILTINS_PREFIX}/map"), format!("/{PEER}/{BUILTINS_PREFIX}/add")] {
        assert!(assert_not_builtin_override(&bad).is_err(), "{bad}");
    }
    for fine in [COMPUTE_PATTERN, "system/compute/builtinsmap", "app/system/compute/builtins"] {
        assert!(assert_not_builtin_override(fine).is_ok(), "{fine}");
    }
}

/// The emit-consumer face registers on the peer's own bus. On a fresh peer §7.1's rebuild finds
/// nothing, and the NEGATIVE: a subgraph metadata entity already in the tree IS found.
#[test]
fn install_compute_registers_the_consumer_and_rebuilds_from_the_tree() {
    let p = peer();
    let fresh = install_compute(&p, DEFAULT_LIMITS).expect("install");
    assert_eq!(fresh.rebuilt, 0);

    let p2 = peer();
    p2.store.bind(&abs(&p2, "app/A1"), &entity("app/cell", vec![]));
    let root = abs(&p2, "app/B1");
    p2.store.bind(&root, &entity(LOOKUP_TREE, vec![("path", text("app/A1"))]));
    p2.store.bind(
        &format!("{}/{}", abs(&p2, PROCESSES_PREFIX), deterministic_id(&root)),
        &entity(SUBGRAPH, vec![("root_expression_path", text(&root)), ("status", text("active")), ("result_path", text(&format!("{root}/result")))]),
    );
    let restored = install_compute(&p2, DEFAULT_LIMITS).expect("install");
    assert_eq!(restored.rebuilt, 1);
    assert_eq!(restored.engine.watched_paths(), vec![abs(&p2, "app/A1")]);
}
