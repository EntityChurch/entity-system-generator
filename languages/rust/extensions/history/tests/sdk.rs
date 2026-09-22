//! **THE POSITIVE CONTROL for the compile-fail arm, plus the SDK surface itself.**
//!
//! `src/bin/deep_import.rs` must fail to compile, and on its own that check reports its
//! strongest result when nothing works at all — a missing vendor mirror, the wrong
//! rustc, a broken peer. So `languages/rust/test` interprets the failure only after this
//! suite has passed, and this suite is written to name the PUBLIC route to everything
//! the fixture names privately. If `mod internal` gained a `pub`, the fixture would
//! compile and the driver would say so; if the crate stopped building, this file would
//! fail first and the driver would refuse to score the fixture at all.
//!
//! The second half asserts the SDK surface `[sdk_surface]` declares, in this port's
//! spelling. `tools/sdk-parity.py` compares the NAMES across ports off `src/lib.rs`; it
//! cannot check that a name resolves to something with the right shape, and that is what
//! these signatures do.

use std::sync::Arc;

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::peer::{CreateOptions, Peer};

use entity_history::{
    build_context, canonicalize_pattern, compare_specificity, config_path, from_core_event_type,
    history_config, history_entity, history_type_defs, history_type_entities,
    install_history_recorder, install_history_types, pattern_matches, pattern_specificity,
    publish_history_types, resolve_config, CarriedContext, ConfigLookup, HistoryConfig,
    HistoryRecorder, HistoryRecorderInstallation, HistoryTypeInstallation, RecordedTransition,
    RecorderIdentity, RecorderStats, Specificity, TransitionContext, ALL_TYPES, CONFIG,
    CONFIG_PREFIX, DEFAULT_EVENTS, DEFAULT_QUERY_LIMIT, EVENT_ACCESSED, EVENT_CREATED,
    EVENT_DELETED, EVENT_UPDATED, HEAD_PREFIX, HISTORY_PATTERN, QUERY_PARAMS, QUERY_RESULT,
    ROLLBACK_PARAMS, ROLLBACK_RESULT, TRANSITION,
};

const PEER: &str = "z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH";

/// **The control.** Every one of these names is the PUBLIC counterpart of something
/// `deep_import.rs` reaches for privately, bound at its exact type. If this compiles and
/// the fixture does not, the difference is the boundary and nothing else.
#[test]
fn the_public_route_exists_at_the_signatures_the_boundary_claims() {
    // The recorder is reachable; `record_transition` behind it is not.
    let _: fn(RecorderIdentity) -> HistoryRecorder = HistoryRecorder::new;
    let _: fn(&Store, &str, &str) -> ConfigLookup = resolve_config;

    // The shapes the private module defines, nameable through the façade.
    let _: fn(&RecorderIdentity, &str, &str, Option<&CarriedContext>) -> TransitionContext =
        build_context;

    // The two install faces this peer HAS, at the names that say which face they are.
    let _: fn(&Store, &str) -> HistoryTypeInstallation = install_history_types;
    let _: fn(&Arc<Peer>, RecorderIdentity) -> HistoryRecorderInstallation =
        install_history_recorder;

    // Types, patterns, config.
    let _: fn(&str, &str) -> String = canonicalize_pattern;
    let _: fn(&str) -> Specificity = pattern_specificity;
    let _: fn(&Specificity, &Specificity) -> i32 = compare_specificity;
    let _: fn(&str, &str) -> bool = pattern_matches;
    let _: fn(&str) -> Option<&'static str> = from_core_event_type;
    let _: fn(&Store, &str) -> Vec<String> = publish_history_types;
    let _: fn(&str, &str) -> String = config_path;
    let _: fn(&str, bool, Option<&[&str]>, Option<u64>) -> Entity = history_config;
    let _ = history_type_defs();
    let _ = history_type_entities();
    let _ = history_entity(TRANSITION, entity_core_protocol::value::Value::Map(vec![]));
}

/// **There is no `install_history` on this port, and its absence is the deliberate
/// half of the surface.**
///
/// The other two ports export one; it registers the handler face, and here the handler
/// face has no install path. A narrower `install_history` would let a caller write one
/// call that means "installed" on two peers and "partly installed" on a third, so the
/// two faces that DO install are named individually and `[sdk_surface]` files all three
/// names as substrate-conditional.
///
/// This test cannot assert the absence of a name — a missing symbol is a compile error,
/// not a test failure — so what it asserts is the shape that makes the absence safe:
/// installing types does not register a consumer, and installing the recorder does not
/// publish types. Either one silently doing the other's job is how a "partly installed"
/// call gets reinvented.
#[test]
fn the_two_install_faces_are_independent() {
    let store = Store::new();
    let types = install_history_types(&store, PEER);
    assert_eq!(types.type_paths.len(), 6);
    // No consumer was registered: a bind fires nothing that writes a head pointer.
    let path = format!("/{PEER}/app/doc");
    store.bind(&path, &history_entity("x", entity_core_protocol::value::Value::Map(vec![])));
    assert!(store.hash_at(&format!("/{PEER}/{HEAD_PREFIX}{path}")).is_none());

    let peer = Arc::new(Peer::create(CreateOptions {
        seed: [0x55; 32],
        open_grants: false,
        conformance: false,
    }));
    let install = install_history_recorder(
        &peer,
        RecorderIdentity {
            local_identity_hash: peer.identity.identity_hash.clone(),
            handler_grant_hash: peer.identity.identity_hash.clone(),
            local_peer: peer.local_peer.clone(),
        },
    );
    // No types were published by the recorder install.
    for name in ALL_TYPES {
        assert!(
            peer.store
                .get_at(&format!("/{}/system/type/{name}", peer.local_peer))
                .is_none(),
            "install_history_recorder must not publish types"
        );
    }
    assert_eq!(install.recorder.stats().recorded, 0);
}

/// The two honest fields on the installation result, and why they are on the result
/// rather than in the stats: a system recording fabricated provenance and one recording
/// real provenance are different systems, and the difference has to be visible where
/// someone decides to trust the audit trail.
#[test]
fn the_installation_reports_both_things_this_peer_cannot_supply() {
    let peer = Arc::new(Peer::create(CreateOptions {
        seed: [0x56; 32],
        open_grants: false,
        conformance: false,
    }));
    let install = install_history_recorder(
        &peer,
        RecorderIdentity {
            local_identity_hash: peer.identity.identity_hash.clone(),
            handler_grant_hash: peer.identity.identity_hash.clone(),
            local_peer: peer.local_peer.clone(),
        },
    );
    assert!(
        !install.context_available,
        "the peer's TreeChangeEvent has four fields and none is a context"
    );
    assert!(
        !install.handler_grant_available,
        "there is no handler to grant for, and Peer exposes no mint"
    );
}

/// The constants a consumer must agree with us on, at the values the spec fixes.
#[test]
fn the_constant_surface_is_the_specs_values() {
    assert_eq!(HISTORY_PATTERN, "system/history");
    assert_eq!(HEAD_PREFIX, "system/history/head");
    assert_eq!(CONFIG_PREFIX, "system/history/config");
    assert_eq!(TRANSITION, "system/history/transition");
    assert_eq!(CONFIG, "system/history/config");
    assert_eq!(QUERY_PARAMS, "system/history/query-params");
    assert_eq!(QUERY_RESULT, "system/history/query-result");
    assert_eq!(ROLLBACK_PARAMS, "system/history/rollback-params");
    assert_eq!(ROLLBACK_RESULT, "system/history/rollback-result");
    assert_eq!(DEFAULT_QUERY_LIMIT, 50, "§2.3 'Default: 50'");
    assert_eq!(DEFAULT_EVENTS, [EVENT_CREATED, EVENT_UPDATED, EVENT_DELETED]);
    assert_eq!(EVENT_ACCESSED, "accessed");
    assert_eq!(ALL_TYPES.len(), 6);

    // §3.2's guard subject and §6.1's config prefix are DIFFERENT strings, and the guard
    // is the narrower one. A guard on the whole namespace would silently drop
    // config-change auditing, which §3.2 explicitly says SHOULD be recorded.
    assert_ne!(HEAD_PREFIX, CONFIG_PREFIX);
    assert!(CONFIG_PREFIX.starts_with("system/history/"));
    assert!(!CONFIG_PREFIX.starts_with(HEAD_PREFIX));
}

/// `accessed` is accepted in a config and never matches, because §5.2 puts read audit
/// inside the TREE HANDLER's `handle_get` and the emit pathway fires on Bind. No
/// consumer on any of the three peers observes a read at all.
///
/// It is a MAY (§9.1), so not implementing it is conformant. Asserted rather than left
/// as a silent hole: the difference between "we chose not to" and "the substrate cannot"
/// is exactly what the `[substrate]` blocks are for.
#[test]
fn the_accessed_event_is_configurable_and_unreachable() {
    assert!(!DEFAULT_EVENTS.contains(&EVENT_ACCESSED));
    let cfg = history_config("*", true, Some(&[EVENT_ACCESSED]), None);
    assert_eq!(cfg.typ, CONFIG);
    // It parses and stores; there is simply no event that can ever match it.
    assert!(from_core_event_type("accessed").is_none());
    assert!(from_core_event_type("read").is_none());
}

/// `HistoryConfig`, `RecordedTransition` and `RecorderStats` are named by
/// `[sdk_surface].required` in all three ports, so a consumer can hold them. This binds
/// each to a value so a rename or a field change is a compile error here rather than a
/// silent surface change caught only by the parity gate's name list.
#[test]
fn the_named_shapes_are_constructible_and_readable() {
    let store = Store::new();
    store.bind(
        &config_path(PEER, "everything"),
        &history_config("*", true, None, None),
    );
    let lookup: ConfigLookup = resolve_config(&store, &format!("/{PEER}/app/doc"), PEER);
    let cfg: HistoryConfig = lookup.config.expect("configured");
    assert_eq!(cfg.pattern, "*");
    assert_eq!(cfg.canonical_pattern, format!("/{PEER}/*"));
    assert!(cfg.enabled);
    assert_eq!(cfg.max_depth, None);
    assert_eq!(cfg.config_path, config_path(PEER, "everything"));

    let rec = HistoryRecorder::new(RecorderIdentity {
        local_identity_hash: vec![0xAA; 33],
        handler_grant_hash: vec![0xAA; 33],
        local_peer: PEER.to_string(),
    });
    let stats: RecorderStats = rec.stats();
    assert_eq!(stats.observed, 0);
    let recorded: Vec<RecordedTransition> = rec.recorded_transitions();
    assert!(recorded.is_empty());
}
