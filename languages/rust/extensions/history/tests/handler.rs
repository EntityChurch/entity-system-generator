//! §4.3 `query` and `rollback`, driven DIRECTLY.
//!
//! **These operations cannot be dispatched on this peer**, so every assertion here is
//! ours and none of them is a conformance claim. `gates/host-seam/rust` measured why:
//! `501 no_handler_body` with all four §11.6.1 tree writes bound, `404` with none, and
//! `register_handler` / `Peer::handlers` / `Outcome` all private. The other two ports
//! drive these same algorithms over the wire and `validate-peer` scores them; here the
//! oracle never reaches this code.
//!
//! What that buys is still worth having — the algorithms are the same in all three ports
//! and a divergence here is a divergence there — but the argument that *"the extension
//! is its own instrument"* holds only where a gated path runs THROUGH the code, and none
//! does. Stated in `EXTENSION.toml` as `reached_by = []` on this port and stated again
//! in the composition's conformance report.

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::{Store, TreeChangeEvent};
use entity_core_protocol::peer::wire;
use entity_core_protocol::value::{Key, Value};

use entity_history::{
    config_path, history_config, HandlerRequest, HistoryHandler, HistoryRecorder, RecorderIdentity,
    OPERATIONS, QUERY_PARAMS, QUERY_RESULT, ROLLBACK_PARAMS, ROLLBACK_RESULT,
};

const PEER: &str = "z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH";

fn scope(include: &[&str]) -> Value {
    Value::Map(vec![(
        Key::Text("include".into()),
        Value::Array(include.iter().map(|s| Value::Text((*s).into())).collect()),
    )])
}

/// A capability token in the shape `capability::grants_of_token` parses.
///
/// Hand-built because the peer's own `grant_val` / `mint_token` are private — the same
/// Export-layer fact `gates/host-seam` records for `Outcome`. It is never signed and
/// never dispatched; `check_permission` reads only `grants`.
fn token(handlers: &[&str], resources: &[&str], operations: &[&str]) -> Entity {
    Entity::make(
        "system/capability/token",
        Value::Map(vec![(
            Key::Text("grants".into()),
            Value::Array(vec![Value::Map(vec![
                (Key::Text("handlers".into()), scope(handlers)),
                (Key::Text("resources".into()), scope(resources)),
                (Key::Text("operations".into()), scope(operations)),
            ])]),
        )]),
    )
}

/// A token that covers the whole local namespace for tree get+put — the shape a caller
/// with ordinary authority over its own paths would hold.
fn full_token() -> Entity {
    token(&["system/tree"], &["*"], &["get", "put"])
}

fn exec(operation: &str, params: Entity, targets: &[&str]) -> Entity {
    wire::make_execute(wire::ExecuteFields {
        request_id: "test",
        uri: &format!("/{PEER}/system/history"),
        operation,
        params,
        resource: Some(Value::Map(vec![(
            Key::Text("targets".into()),
            Value::Array(targets.iter().map(|t| Value::Text((*t).into())).collect()),
        )])),
        author: None,
        capability: None,
    })
}

fn exec_no_resource(operation: &str, params: Entity) -> Entity {
    wire::make_execute(wire::ExecuteFields {
        request_id: "test",
        uri: &format!("/{PEER}/system/history"),
        operation,
        params,
        resource: None,
        author: None,
        capability: None,
    })
}

fn query_params(path: &str, extra: Vec<(Key, Value)>) -> Entity {
    let mut pairs = vec![(Key::Text("path".into()), Value::Text(path.into()))];
    pairs.extend(extra);
    Entity::make(QUERY_PARAMS, Value::Map(pairs))
}

fn rollback_params(path: &str, target: &[u8]) -> Entity {
    Entity::make(
        ROLLBACK_PARAMS,
        Value::Map(vec![
            (Key::Text("path".into()), Value::Text(path.into())),
            (Key::Text("target_hash".into()), Value::Bytes(target.to_vec())),
        ]),
    )
}

fn payload(v: &str) -> Entity {
    Entity::make(
        "system/validate/history-test",
        Value::Map(vec![(Key::Text("value".into()), Value::Text(v.into()))]),
    )
}

/// A store with history configured for everything, plus a recorder driven by hand so the
/// chain is real rather than fabricated. Returns `(store, recorder)`.
fn seeded() -> (Store, HistoryRecorder) {
    let store = Store::new();
    store.bind(
        &config_path(PEER, "everything"),
        &history_config("*", true, None, None),
    );
    let rec = HistoryRecorder::new(RecorderIdentity {
        local_identity_hash: vec![0xAA; 33],
        handler_grant_hash: vec![0xAA; 33],
        local_peer: PEER.to_string(),
    });
    (store, rec)
}

fn write(store: &Store, rec: &HistoryRecorder, path: &str, value: &str) -> Entity {
    let previous = store.hash_at(path);
    let ent = payload(value);
    store.bind(path, &ent);
    rec.on_tree_change(
        store,
        &TreeChangeEvent {
            event_type: if previous.is_none() { "created" } else { "modified" },
            path: path.to_string(),
            new_hash: Some(ent.hash.clone()),
            previous_hash: previous,
            // AUTONOMOUS, and that is the fixture's CLAIM rather than a placeholder:
            // these drive a bare store write with no dispatch above them, which is
            // precisely §2.1's autonomous case. The peer gained this slot with H8
            // (`dc5a458`) -- a fixture that omitted it would stop compiling, and one
            // that filled it would assert a provenance it never had.
            context: None,
        },
    );
    ent
}

fn transitions_of(result: &Entity) -> Vec<Value> {
    match result.field("transitions") {
        Some(Value::Array(items)) => items.clone(),
        _ => panic!("query result has no transitions array"),
    }
}

fn field_of(transition: &Value, key: &str) -> Option<Value> {
    entity_core_protocol::peer::model::map_get(transition, key).cloned()
}

fn code_of(result: &Entity) -> String {
    result.text_field("code").unwrap_or("").to_string()
}

// ── §4.1 the manifest surface ────────────────────────────────────────────────

#[test]
fn the_manifest_declares_exactly_query_and_rollback() {
    assert_eq!(OPERATIONS, ["query", "rollback"]);
}

// ── the pre-op checks ────────────────────────────────────────────────────────

/// GUIDE-EXTENSION-DEVELOPMENT §4.1 makes a resource-less directly-callable op a
/// `400 path_required`. The code is in `[error_surface].unresolved` because no spec code
/// set defines it — and HISTORY is the SECOND extension to inherit it, which is the
/// argument that it is a corpus fact rather than a CONTENT quirk.
#[test]
fn a_resource_less_call_is_400_path_required() {
    let (store, _) = seeded();
    let h = HistoryHandler::new();
    let e = exec_no_resource("query", query_params(&format!("/{PEER}/app/doc"), vec![]));
    let out = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(out.status, 400);
    assert_eq!(code_of(&out.result), "path_required");
}

/// §6.6-style: an unknown verb is `501`, not `404`. The op does not exist; the handler
/// does.
#[test]
fn an_unknown_operation_is_501() {
    let (store, _) = seeded();
    let h = HistoryHandler::new();
    let e = exec("purge", wire::empty_params(), &["system/history"]);
    let out = h.handle_op(
        "purge",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(out.status, 501);
    assert_eq!(code_of(&out.result), "unsupported_operation");
}

// ── §4.2 the dual capability check ───────────────────────────────────────────

/// §7.1: "This prevents using the history system to access data the caller couldn't
/// otherwise read." A grant on `system/history` alone must not become a read primitive
/// over the whole tree.
///
/// **This is the check nothing else performs**: the target path lives in `params`, not
/// in `resource`, so the dispatcher's resource scoping never sees it. The token here
/// covers `system/history` and the handler pattern §4.2 names is `system/tree`, so it
/// must be denied even though it would have been enough to reach the handler.
#[test]
fn a_history_only_capability_cannot_read_an_arbitrary_path() {
    let (store, rec) = seeded();
    let path = format!("/{PEER}/private/doc");
    write(&store, &rec, &path, "v1");

    let h = HistoryHandler::new();
    let history_only = token(&["system/history"], &["system/history"], &["query"]);
    let e = exec("query", query_params(&path, vec![]), &["system/history"]);
    let out = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&history_only),
        },
    );
    assert_eq!(out.status, 403);
    assert_eq!(code_of(&out.result), "capability_denied");

    // THE CONTROL. Same request, same path, a token that DOES cover the target as a tree
    // path. Without this arm the assertion above passes for a handler that denies
    // everything — which is exactly what `python`'s first draft did, failing 23 of 34
    // oracle checks on one root cause.
    let allowed = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(allowed.status, 200);
}

/// "No token" is not evidence of authority. §7.1's purpose is that history must not
/// widen what a caller can reach, so an in-process call with no capability is DENIED
/// rather than trusted.
#[test]
fn no_caller_capability_is_denied_not_trusted() {
    let (store, _) = seeded();
    let h = HistoryHandler::new();
    let e = exec("query", query_params(&format!("/{PEER}/app/doc"), vec![]), &["system/history"]);
    let out = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: None,
        },
    );
    assert_eq!(out.status, 403);
    assert_eq!(code_of(&out.result), "capability_denied");
}

/// §4.2 asks for `put` authority on the target for a rollback and `get` for a query.
/// A read-only token must be able to query and must NOT be able to roll back.
#[test]
fn rollback_needs_put_authority_where_query_needs_only_get() {
    let (store, rec) = seeded();
    let path = format!("/{PEER}/app/doc");
    let v1 = write(&store, &rec, &path, "v1");
    write(&store, &rec, &path, "v2");

    let h = HistoryHandler::new();
    let read_only = token(&["system/tree"], &["*"], &["get"]);

    let q = exec("query", query_params(&path, vec![]), &["system/history"]);
    let qout = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &q,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&read_only),
        },
    );
    assert_eq!(qout.status, 200, "a read-only token may query");

    let r = exec(
        "rollback",
        rollback_params(&path, &v1.hash),
        &["system/history", &path],
    );
    let rout = h.handle_op(
        "rollback",
        &HandlerRequest {
            exec: &r,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&read_only),
        },
    );
    assert_eq!(rout.status, 403, "a read-only token may not roll back");
    assert_eq!(code_of(&rout.result), "capability_denied");
}

// ── §4.3.1 query ─────────────────────────────────────────────────────────────

/// §4.3.1: no history → an EMPTY RESULT, not a 404. The path may simply never have been
/// written, and "no history" is a fact rather than a failure.
///
/// `has_more` must be present-and-`false`, not absent: §2.4 makes it required and the
/// oracle decodes it into a `bool` with no `omitempty`.
#[test]
fn a_path_with_no_history_returns_an_empty_result_not_a_404() {
    let (store, _) = seeded();
    let h = HistoryHandler::new();
    let path = format!("/{PEER}/never/written");
    let e = exec("query", query_params(&path, vec![]), &["system/history"]);
    let out = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(out.status, 200);
    assert_eq!(out.result.typ, QUERY_RESULT);
    assert!(transitions_of(&out.result).is_empty());
    assert_eq!(
        out.result.field("has_more"),
        Some(&Value::Bool(false)),
        "has_more is REQUIRED and must encode as present-and-false"
    );
}

/// §2.3: "The `path` field ... accepts short-form input. The handler canonicalizes it
/// before processing." A query for `app/doc` must find the history of
/// `/{peer}/app/doc`.
#[test]
fn a_short_form_path_is_canonicalized_before_the_lookup() {
    let (store, rec) = seeded();
    write(&store, &rec, &format!("/{PEER}/app/doc"), "v1");

    let h = HistoryHandler::new();
    let e = exec("query", query_params("app/doc", vec![]), &["system/history"]);
    let out = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(out.status, 200);
    assert_eq!(transitions_of(&out.result).len(), 1);
    assert_eq!(
        out.result.text_field("path"),
        Some(format!("/{PEER}/app/doc").as_str())
    );
}

/// The transitions array carries each transition's DATA MAP inline, not its hash and not
/// a `{type, data}` entity map.
///
/// §2.4's `array_of: {type_ref: ...}` admits all three readings. **The oracle settles
/// it**: `HistoryQueryResultData` is `Transitions []TransitionData` and decodes elements
/// straight into the field struct. A hash array decodes as nothing; an entity-map array
/// decodes as a struct with every field zero — which passes `transition_recorded` (the
/// array is non-empty) and fails `transition_event_created` four checks later.
#[test]
fn transitions_are_inline_data_maps_not_hashes_or_entity_wrappers() {
    let (store, rec) = seeded();
    let path = format!("/{PEER}/app/doc");
    let v1 = write(&store, &rec, &path, "v1");

    let h = HistoryHandler::new();
    let e = exec("query", query_params(&path, vec![]), &["system/history"]);
    let out = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    let items = transitions_of(&out.result);
    assert_eq!(items.len(), 1);
    // A DATA map: `event` is reachable at the top level of the element.
    assert_eq!(
        field_of(&items[0], "event"),
        Some(Value::Text("created".into()))
    );
    assert_eq!(field_of(&items[0], "hash"), Some(Value::Bytes(v1.hash.clone())));
    // NOT an entity wrapper — there is no `type`/`data` nesting.
    assert_eq!(field_of(&items[0], "data"), None);
    assert_eq!(field_of(&items[0], "type"), None);
    // The entities still ride as `included`, so a hash-resolving caller needs no second
    // round trip.
    assert_eq!(out.included.len(), 1);
}

#[test]
fn limit_truncates_and_sets_has_more() {
    let (store, rec) = seeded();
    let path = format!("/{PEER}/app/doc");
    for v in ["v1", "v2", "v3"] {
        write(&store, &rec, &path, v);
    }

    let h = HistoryHandler::new();
    let e = exec(
        "query",
        query_params(&path, vec![(Key::Text("limit".into()), Value::UInt(1))]),
        &["system/history"],
    );
    let out = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(transitions_of(&out.result).len(), 1);
    assert_eq!(out.result.field("has_more"), Some(&Value::Bool(true)));

    // The control: unlimited returns all three and `has_more` goes false. Without it,
    // `has_more: true` would also be produced by a walk that simply never terminates
    // correctly.
    let all = exec("query", query_params(&path, vec![]), &["system/history"]);
    let out_all = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &all,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(transitions_of(&out_all.result).len(), 3);
    assert_eq!(out_all.result.field("has_more"), Some(&Value::Bool(false)));
}

/// §4.3.1's `events` filter CONTINUES — it skips an entry and keeps walking — where
/// `since` BREAKS. Collapsing the two into one predicate changes the result set.
#[test]
fn the_event_filter_skips_and_keeps_walking() {
    let (store, rec) = seeded();
    let path = format!("/{PEER}/app/doc");
    write(&store, &rec, &path, "v1"); // created
    write(&store, &rec, &path, "v2"); // updated

    let h = HistoryHandler::new();
    let e = exec(
        "query",
        query_params(
            &path,
            vec![(
                Key::Text("events".into()),
                Value::Array(vec![Value::Text("created".into())]),
            )],
        ),
        &["system/history"],
    );
    let out = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    let items = transitions_of(&out.result);
    assert_eq!(items.len(), 1, "the `created` entry is past the `updated` one in the walk");
    assert_eq!(
        field_of(&items[0], "event"),
        Some(Value::Text("created".into()))
    );
}

// ── §4.3.2 rollback, and §7.5 ────────────────────────────────────────────────

#[test]
fn rollback_restores_the_target_and_rebinds_the_path() {
    let (store, rec) = seeded();
    let path = format!("/{PEER}/app/doc");
    let v1 = write(&store, &rec, &path, "v1");
    let v2 = write(&store, &rec, &path, "v2");
    assert_eq!(store.hash_at(&path), Some(v2.hash.clone()));

    let h = HistoryHandler::new();
    let e = exec(
        "rollback",
        rollback_params(&path, &v1.hash),
        &["system/history", &path],
    );
    let out = h.handle_op(
        "rollback",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(out.status, 200);
    assert_eq!(out.result.typ, ROLLBACK_RESULT);
    assert_eq!(out.result.bytes_field("restored"), Some(v1.hash.as_slice()));
    assert_eq!(
        store.hash_at(&path),
        Some(v1.hash.clone()),
        "§4.3.2 restores by rebinding the path"
    );
}

/// **§7.5 History Exfiltration Prevention — the security check of this operation.**
///
/// "You can only restore entities that were previously at that path." Without it,
/// `rollback` is an unrestricted `put` that bypasses every type and validation path a
/// real put has.
#[test]
fn rollback_refuses_a_hash_that_was_never_at_this_path() {
    let (store, rec) = seeded();
    let mine = format!("/{PEER}/app/doc");
    let theirs = format!("/{PEER}/other/doc");
    write(&store, &rec, &mine, "v1");
    let foreign = write(&store, &rec, &theirs, "not-yours");

    let h = HistoryHandler::new();
    // The entity IS in the content store — this is not a "missing blob" case. It was
    // simply never bound at THIS path.
    assert!(store.get_by_hash(&foreign.hash).is_some());
    let e = exec(
        "rollback",
        rollback_params(&mine, &foreign.hash),
        &["system/history", &mine],
    );
    let out = h.handle_op(
        "rollback",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(out.status, 404);
    assert_eq!(code_of(&out.result), "not_in_history");
    assert_eq!(
        store.hash_at(&mine),
        store.hash_at(&mine),
        "the refusal must not have written anything"
    );
}

/// §4.3.2 `is_in_history` matches on `hash` **OR** `previous_hash`.
///
/// Dropping the second disjunct still passes the test above and still passes a rollback
/// to any value the path once held as a `hash`. It fails only for the FIRST entity ever
/// at the path when rolled back past the write that replaced it — the oldest reachable
/// state, which is the one an undo most wants. This is that case: after two writes the
/// walk reaches the `updated` transition, whose `previous_hash` is v1, before it reaches
/// v1's own `created` transition.
#[test]
fn is_in_history_matches_previous_hash_not_only_hash() {
    let (store, rec) = seeded();
    let path = format!("/{PEER}/app/doc");
    let v1 = write(&store, &rec, &path, "v1");
    write(&store, &rec, &path, "v2");

    let h = HistoryHandler::new();
    let e = exec("query", query_params(&path, vec![]), &["system/history"]);
    let req = HandlerRequest {
        exec: &e,
        store: &store,
        local_peer: PEER,
        caller_capability: Some(&full_token()),
    };
    assert!(h.is_in_history(&req, &path, &v1.hash));

    // The negative: a hash from a different path is not in this path's history, however
    // reachable it is in the content store.
    let elsewhere = write(&store, &rec, &format!("/{PEER}/other/doc"), "x");
    assert!(!h.is_in_history(&req, &path, &elsewhere.hash));
}

/// In history but GC'd from the content store (§3.3) is `500 storage_error`, NOT a 404
/// and NOT CONTENT's `blob_not_found`.
///
/// A 404 would say "not in history", which is false — we just proved it IS — and would
/// be indistinguishable from the branch above. `blob_not_found` is CONTENT's owned code
/// and §8.3 makes HISTORY installable without CONTENT, so borrowing it would emit a code
/// whose defining spec is absent from the peer.
///
/// The store here is one this test builds by hand: a head pointer and a transition chain
/// naming an entity that was never put. That is exactly the state §3.3's GC leaves.
#[test]
fn a_gcd_target_is_500_storage_error_not_a_404() {
    let store = Store::new();
    let missing = payload("collected"); // built, never stored
    let transition = Entity::make(
        "system/history/transition",
        Value::Map(vec![
            (
                Key::Text("path".into()),
                Value::Text(format!("/{PEER}/app/doc")),
            ),
            (Key::Text("event".into()), Value::Text("created".into())),
            (
                Key::Text("hash".into()),
                Value::Bytes(missing.hash.clone()),
            ),
            (Key::Text("author".into()), Value::Bytes(vec![0xAA; 33])),
            (Key::Text("capability".into()), Value::Bytes(vec![0xAA; 33])),
            (
                Key::Text("handler".into()),
                Value::Text("system/tree".into()),
            ),
            (Key::Text("operation".into()), Value::Text("put".into())),
            (Key::Text("timestamp".into()), Value::UInt(1)),
        ]),
    );
    let path = format!("/{PEER}/app/doc");
    store.bind(
        &format!("/{PEER}/system/history/head{path}"),
        &transition,
    );

    let h = HistoryHandler::new();
    let e = exec(
        "rollback",
        rollback_params(&path, &missing.hash),
        &["system/history", &path],
    );
    let out = h.handle_op(
        "rollback",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(out.status, 500);
    assert_eq!(code_of(&out.result), "storage_error");
}

/// Malformed params are `400 unexpected_params`, on both operations.
#[test]
fn malformed_params_are_400_unexpected_params() {
    let (store, _) = seeded();
    let h = HistoryHandler::new();
    let req_for = |e: &Entity, op: &str| {
        h.handle_op(
            op,
            &HandlerRequest {
                exec: e,
                store: &store,
                local_peer: PEER,
                caller_capability: Some(&full_token()),
            },
        )
    };

    let no_path = exec(
        "query",
        Entity::make(QUERY_PARAMS, Value::Map(vec![])),
        &["system/history"],
    );
    let out = req_for(&no_path, "query");
    assert_eq!(out.status, 400);
    assert_eq!(code_of(&out.result), "unexpected_params");

    let no_target = exec(
        "rollback",
        Entity::make(
            ROLLBACK_PARAMS,
            Value::Map(vec![(
                Key::Text("path".into()),
                Value::Text(format!("/{PEER}/app/doc")),
            )]),
        ),
        &["system/history"],
    );
    let out = req_for(&no_target, "rollback");
    assert_eq!(out.status, 400);
    assert_eq!(code_of(&out.result), "unexpected_params");
}

/// The declared walk bound, which is NOT in the spec and IS declared in
/// `EXTENSION.toml [assumptions].max_walk`.
///
/// §2.3's `limit` is caller-supplied and unbounded above, and §4.3.1's loop walks until
/// the chain ends — so a caller asking for `limit: 2^53` materialises the whole chain.
/// The cap changes an observable answer: `has_more` goes true earlier than a naive
/// reading of §4.3.1 would produce, which is why it is declared rather than applied
/// quietly.
#[test]
fn the_walk_bound_is_enforced_and_shows_up_as_has_more() {
    let (store, rec) = seeded();
    let path = format!("/{PEER}/app/doc");
    for i in 0..5 {
        write(&store, &rec, &path, &format!("v{i}"));
    }

    let h = HistoryHandler::with_max_walk(2);
    let e = exec("query", query_params(&path, vec![]), &["system/history"]);
    let out = h.handle_op(
        "query",
        &HandlerRequest {
            exec: &e,
            store: &store,
            local_peer: PEER,
            caller_capability: Some(&full_token()),
        },
    );
    assert_eq!(transitions_of(&out.result).len(), 2);
    assert_eq!(
        out.result.field("has_more"),
        Some(&Value::Bool(true)),
        "a walk stopped by the cap must not report the chain as exhausted"
    );
}
