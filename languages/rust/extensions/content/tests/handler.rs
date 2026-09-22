//! §6.2 / §6.3 handler behaviour, driven against a real peer `Store`.
//!
//! **These tests are ours.** They drive the body directly through [`HandlerRequest`], because a
//! third party cannot construct the peer's `HandlerContext`. The oracle's `content` category
//! reaches the same body over the wire now that `install_content` puts it behind
//! `Peer::register_handler`; what these add is the branches no vector reaches.

use entity_content::{
    create_blob_fixed, store_blob, ContentHandler, FrameBudget, HandlerRequest, CONTENT_PATTERN,
    CONTENT_RESPONSE, INGEST_RESULT,
};
use entity_core_protocol::peer::model::{self, Entity};
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

fn targets(paths: &[&str]) -> Value {
    Value::Map(vec![(
        Key::Text("targets".into()),
        Value::Array(paths.iter().map(|p| Value::Text(p.to_string())).collect()),
    )])
}

fn exec(operation: &str, params: Entity, resource: Option<Value>) -> Entity {
    let mut pairs: Vec<(Key, Value)> = vec![
        (Key::Text("request_id".into()), model::text("t1")),
        (Key::Text("uri".into()), model::text(CONTENT_PATTERN)),
        (Key::Text("operation".into()), model::text(operation)),
        (Key::Text("params".into()), params.to_cbor()),
    ];
    if let Some(r) = resource {
        pairs.push((Key::Text("resource".into()), r));
    }
    Entity::make("system/protocol/execute", Value::Map(pairs))
}

fn get_params(hashes: &[Vec<u8>]) -> Entity {
    Entity::make(
        "system/content/get-request",
        Value::Map(vec![(
            Key::Text("hashes".into()),
            Value::Array(hashes.iter().map(|h| Value::Bytes(h.clone())).collect()),
        )]),
    )
}

fn req<'a>(e: &'a Entity, store: &'a Store) -> HandlerRequest<'a> {
    HandlerRequest {
        exec: e,
        store,
        frame_budget: FrameBudget::Enforced(entity_core_protocol::peer::wire::MAX_FRAME),
        caller_capability: None,
        local_peer: "PEER",
    }
}

fn code_of(result: &Entity) -> String {
    result.text_field("code").unwrap_or("").to_string()
}

// ── §6.2 / §6.3 the path-as-resource MUST ────────────────────────────────────

#[test]
fn a_request_with_no_resource_is_400_path_required() {
    // The status is pinned at 400 by GUIDE-EXTENSION-DEVELOPMENT §171. The oracle
    // checks only the CODE, so a peer answering 404 passes the gate and fails the
    // spec -- which is why the status is asserted here and not only the code.
    let store = Store::new();
    let h = ContentHandler::new();
    let e = exec("get", get_params(&[]), None);
    let out = h.handle_op("get", &req(&e, &store));
    assert_eq!(out.status, 400);
    assert_eq!(code_of(&out.result), "path_required");
}

#[test]
fn an_empty_targets_list_is_treated_as_absent() {
    // Core §3.2 makes `targets` MUST-contain-at-least-one, so `{targets: []}` is
    // malformed. See the note on `resource_targets`: over the wire, `check_permission`
    // refuses this first with 403 (measured on `python`). This test is an in-process call, where 400 is the
    // answer -- the same branch `python` keeps for its own in-process case.
    let store = Store::new();
    let h = ContentHandler::new();
    let e = exec("get", get_params(&[]), Some(targets(&[])));
    let out = h.handle_op("get", &req(&e, &store));
    assert_eq!(out.status, 400);
    assert_eq!(code_of(&out.result), "path_required");
}

#[test]
fn a_target_outside_the_namespace_is_403() {
    let store = Store::new();
    let h = ContentHandler::new();
    let e = exec("get", get_params(&[]), Some(targets(&["system/tree/x"])));
    let out = h.handle_op("get", &req(&e, &store));
    assert_eq!(out.status, 403);
    // v3.7 §6.4: `capability_denied`, not `forbidden`. Asserted on the CODE and not on the
    // status alone, because the status was already right under v3.6 and the code was not —
    // a test that checked only `403` would have survived the re-pin without noticing.
    assert_eq!(code_of(&out.result), "capability_denied");
}

/// §6.4 step 2 — the PATH-SCOPE check against the caller's capability, through the peer's H9
/// `check_path_permission` with handler pattern `system/content`. A target INSIDE the namespace (so
/// the prefix check above passes) that the grant does not cover is `403 capability_denied`. CONTROL:
/// the same request under a grant that does cover it proceeds — without it, a handler denying every
/// capability-bearing request would pass the first assertion.
#[test]
fn a_target_the_capability_does_not_cover_is_403_even_inside_the_namespace() {
    let store = Store::new();
    let h = ContentHandler::new();
    let grant = |resources: &str| {
        let scope = |s: &str| Value::Map(vec![(Key::Text("include".into()), Value::Array(vec![Value::Text(s.into())]))]);
        Entity::make(
            "system/capability/token",
            Value::Map(vec![(
                Key::Text("grants".into()),
                Value::Array(vec![Value::Map(vec![
                    (Key::Text("handlers".into()), scope("system/content")),
                    (Key::Text("resources".into()), scope(resources)),
                    (Key::Text("operations".into()), scope("get")),
                ])]),
            )]),
        )
    };
    let e = exec("get", get_params(&[]), Some(targets(&["system/content/private/x"])));
    let narrow = grant("system/content/public/*");
    let mut r = req(&e, &store);
    r.caller_capability = Some(&narrow);
    let out = h.handle_op("get", &r);
    assert_eq!((out.status, code_of(&out.result).as_str()), (403, "capability_denied"));

    let wide = grant("system/content/*");
    r.caller_capability = Some(&wide);
    assert_eq!(h.handle_op("get", &r).status, 200, "control: a covering grant proceeds");
}

/// §6.2 — the budget pays for the `found`/`missing` entries too, one per requested hash. A budget
/// that EXACTLY fits one entity plus one entry packs it (the CONTROL: the arithmetic is right, not
/// merely stingy); the same budget with one extra, absent hash in the request does not, because that
/// hash's `missing` entry is part of the response. The pre-2026-09-12 accounting packed it anyway.
#[test]
fn the_budget_is_charged_for_every_hash_list_entry_not_only_packed_entities() {
    let store = Store::new();
    let h = ContentHandler::new();
    let e = Entity::make("test/blob", Value::Map(vec![(Key::Text("p".into()), Value::Bytes(vec![7; 200]))]));
    store.put_entity(&e);
    let wire = entity_core_protocol::cbor::encode(&e.to_cbor()).len();
    let budget = entity_content::FRAME_RESERVE_BYTES + 35 + wire + e.hash.len();
    let run = |hashes: &[Vec<u8>]| {
        let x = exec("get", get_params(hashes), Some(targets(&[CONTENT_PATTERN])));
        let mut r = req(&x, &store);
        r.frame_budget = FrameBudget::Enforced(budget);
        let out = h.handle_op("get", &r);
        assert_eq!(out.status, 200);
        out.included.len()
    };
    assert_eq!(run(&[e.hash.clone()]), 1, "control: a budget that exactly fits packs the entity");
    let absent = vec![0u8; 33];
    assert_eq!(run(&[e.hash.clone(), absent]), 0, "the absent hash's `missing` entry is part of the response");
}

#[test]
fn an_unknown_operation_is_501_not_404() {
    // §6.6(2): "This spec does not define a system/content:delete." Removal is local
    // GC, never a protocol op.
    let store = Store::new();
    let h = ContentHandler::new();
    let e = exec("delete", get_params(&[]), Some(targets(&[CONTENT_PATTERN])));
    let out = h.handle_op("delete", &req(&e, &store));
    assert_eq!(out.status, 501);
    assert_eq!(code_of(&out.result), "unsupported_operation");
}

// ── §6.2 get ─────────────────────────────────────────────────────────────────

#[test]
fn get_returns_found_and_missing_as_arrays_and_includes_the_entities() {
    // `found` / `missing` are ARRAYS, not counters -- the F4 cross-impl audit landing,
    // and the one wire-shape mistake this response has already made once.
    let store = Store::new();
    let blob = create_blob_fixed(b"the quick brown fox", 8);
    let blob_hash = store_blob(&store, &blob);
    let absent = vec![0u8; 33];

    let h = ContentHandler::new();
    let e = exec(
        "get",
        get_params(&[blob_hash.clone(), absent.clone()]),
        Some(targets(&[CONTENT_PATTERN])),
    );
    let out = h.handle_op("get", &req(&e, &store));

    assert_eq!(out.status, 200);
    assert_eq!(out.result.typ, CONTENT_RESPONSE);
    match out.result.field("found") {
        Some(Value::Array(items)) => {
            assert_eq!(items.as_slice(), [Value::Bytes(blob_hash.clone())])
        }
        other => panic!("found is not an array: {other:?}"),
    }
    match out.result.field("missing") {
        Some(Value::Array(items)) => assert_eq!(items.as_slice(), [Value::Bytes(absent)]),
        other => panic!("missing is not an array: {other:?}"),
    }
    // §6.2's wire contract: the fetched entities are delivered via the response
    // envelope's `included` map, not inline in the result.
    assert_eq!(out.included.len(), 1);
    assert_eq!(out.included[0].hash, blob_hash);
}

#[test]
fn pending_is_omitted_and_not_emitted_empty() {
    // §6.2 Amendment 2. `absent` and `empty` mean the same thing to the mapping table,
    // but a reader diffing two peers would read an empty array as "supports sync-state,
    // nothing pending" -- which would advertise a capability this composition does not
    // have. Asserting ABSENCE is the only way this distinction is defended.
    let store = Store::new();
    let h = ContentHandler::new();
    let e = exec("get", get_params(&[]), Some(targets(&[CONTENT_PATTERN])));
    let out = h.handle_op("get", &req(&e, &store));
    assert!(
        out.result.field("pending").is_none(),
        "pending must be OMITTED, not emitted empty"
    );
}

#[test]
fn the_frame_budget_bounds_the_batch_and_the_rest_go_to_missing_in_order() {
    // §6.2: "as many as fit (in request order)". Once exhausted, every REMAINING hash
    // goes to `missing` -- a small entity after a large one does NOT get packed,
    // because order is the contract and the requester retries with `missing`.
    let store = Store::new();
    let big = create_blob_fixed(&vec![7u8; 4000], 4000);
    let big_hash = store_blob(&store, &big);
    let small = create_blob_fixed(b"x", 8);
    let small_hash = store_blob(&store, &small);

    let h = ContentHandler::new();
    let e = exec(
        "get",
        get_params(&[big_hash.clone(), small_hash.clone()]),
        Some(targets(&[CONTENT_PATTERN])),
    );
    // A budget deliberately too small for the first entity. `Enforced` is constructed
    // directly here rather than via `from_peer`, which is the whole reason the variant
    // carries its number: a peer that DID configure a budget would pass it the same way.
    let tight = HandlerRequest {
        exec: &e,
        store: &store,
        frame_budget: FrameBudget::Enforced(entity_content::FRAME_RESERVE_BYTES + 64),
        caller_capability: None,
        local_peer: "PEER",
    };
    let out = h.handle_op("get", &tight);
    assert_eq!(out.status, 200);
    match out.result.field("found") {
        Some(Value::Array(items)) => assert!(items.is_empty(), "nothing should have fit"),
        other => panic!("found is not an array: {other:?}"),
    }
    match out.result.field("missing") {
        Some(Value::Array(items)) => assert_eq!(
            items.as_slice(),
            [Value::Bytes(big_hash), Value::Bytes(small_hash)],
            "the small entity must NOT be packed after the large one was skipped"
        ),
        other => panic!("missing is not an array: {other:?}"),
    }
    assert!(out.included.is_empty());
}

/// Amendment 1 BY VALUE, which this peer could not support before keystone's H6: configure a
/// non-default budget and require the body's read to return it. The NEGATIVE arm is a peer left at
/// the default, whose read must be the 16 MiB literal — so a `from_peer` that returned the constant
/// would pass the second assertion and fail the first.
#[test]
fn from_peer_reads_the_configured_budget_by_value() {
    use entity_core_protocol::peer::{CreateOptions, Peer, PeerConfig};
    let opts = || CreateOptions { seed: [0x11; 32], open_grants: true, conformance: false };
    let configured = Peer::create_with(opts(), PeerConfig::default().max_frame_bytes(3_145_749));
    assert_eq!(FrameBudget::from_peer(&configured), FrameBudget::Enforced(3_145_749));
    let default = Peer::create(opts());
    assert_eq!(
        FrameBudget::from_peer(&default),
        FrameBudget::Enforced(entity_core_protocol::peer::wire::MAX_FRAME)
    );
}

// ── §6.3 ingest ──────────────────────────────────────────────────────────────

#[test]
fn ingest_entity_mode_stores_one_and_omits_root() {
    // §11.1's `root` MUST is scoped to ENVELOPE mode. In entity mode there is no
    // envelope wrapper to pass through, so `root` is absent -- which is exactly what
    // `optional` encodes under the §1.3 absent-key rule.
    let store = Store::new();
    let h = ContentHandler::new();
    let payload = Entity::make(
        "system/content/chunk",
        Value::Map(vec![(Key::Text("payload".into()), Value::Bytes(b"hi".to_vec()))]),
    );
    let params = Entity::make(
        "system/content/ingest-request",
        Value::Map(vec![(Key::Text("entity".into()), payload.to_cbor())]),
    );
    let e = exec("ingest", params, Some(targets(&[CONTENT_PATTERN])));
    let out = h.handle_op("ingest", &req(&e, &store));

    assert_eq!(out.status, 200);
    assert_eq!(out.result.typ, INGEST_RESULT);
    assert_eq!(out.result.uint_field("ingested_count"), Some(1));
    assert_eq!(out.result.bytes_field("root_hash"), Some(payload.hash.as_slice()));
    assert!(
        out.result.field("root").is_none(),
        "root MUST be absent in entity mode"
    );
    assert!(store.get_by_hash(&payload.hash).is_some());
}

#[test]
fn ingest_envelope_mode_inlines_root_and_counts_included() {
    let store = Store::new();
    let h = ContentHandler::new();
    let inner = Entity::make(
        "system/content/chunk",
        Value::Map(vec![(Key::Text("payload".into()), Value::Bytes(b"a".to_vec()))]),
    );
    let root = Entity::make(
        "system/content/blob",
        Value::Map(vec![
            (Key::Text("total_size".into()), Value::UInt(1)),
            (Key::Text("chunk_size".into()), Value::UInt(8)),
            (Key::Text("chunking".into()), Value::UInt(0)),
            (
                Key::Text("chunks".into()),
                Value::Array(vec![Value::Bytes(inner.hash.clone())]),
            ),
        ]),
    );
    let envelope = Value::Map(vec![
        (Key::Text("root".into()), root.to_cbor()),
        (
            Key::Text("included".into()),
            Value::Map(vec![(Key::Bytes(inner.hash.clone()), inner.to_cbor())]),
        ),
    ]);
    let params = Entity::make(
        "system/content/ingest-request",
        Value::Map(vec![(Key::Text("envelope".into()), envelope)]),
    );
    let e = exec("ingest", params, Some(targets(&[CONTENT_PATTERN])));
    let out = h.handle_op("ingest", &req(&e, &store));

    assert_eq!(out.status, 200);
    assert_eq!(out.result.uint_field("ingested_count"), Some(2));
    // §11.1 MUST: `root` is inlined so a continuation can navigate
    // `data.root.data.<field>` without dereferencing the content store (§6.3.1).
    assert!(out.result.field("root").is_some(), "root MUST be inlined");
    assert!(store.get_by_hash(&root.hash).is_some());
    assert!(store.get_by_hash(&inner.hash).is_some());
}

#[test]
fn an_included_key_that_does_not_match_its_entity_is_400_hash_mismatch() {
    // The §3.1 KEY check, which is a different assertion from `entity_of_cbor`'s
    // re-derivation of the hash from {type, data}, and it is the one §6.3 names.
    let store = Store::new();
    let h = ContentHandler::new();
    let inner = Entity::make(
        "system/content/chunk",
        Value::Map(vec![(Key::Text("payload".into()), Value::Bytes(b"a".to_vec()))]),
    );
    let root = Entity::make("system/content/blob", Value::Map(vec![]));
    let envelope = Value::Map(vec![
        (Key::Text("root".into()), root.to_cbor()),
        (
            Key::Text("included".into()),
            Value::Map(vec![(Key::Bytes(vec![0u8; 33]), inner.to_cbor())]),
        ),
    ]);
    let params = Entity::make(
        "system/content/ingest-request",
        Value::Map(vec![(Key::Text("envelope".into()), envelope)]),
    );
    let e = exec("ingest", params, Some(targets(&[CONTENT_PATTERN])));
    let out = h.handle_op("ingest", &req(&e, &store));
    assert_eq!(out.status, 400);
    assert_eq!(code_of(&out.result), "hash_mismatch");
}

#[test]
fn envelope_and_entity_together_is_400_ambiguous_and_neither_is_400_missing() {
    let store = Store::new();
    let h = ContentHandler::new();

    let both = Entity::make(
        "system/content/ingest-request",
        Value::Map(vec![
            (Key::Text("envelope".into()), Value::Map(vec![])),
            (Key::Text("entity".into()), Value::Map(vec![])),
        ]),
    );
    let e = exec("ingest", both, Some(targets(&[CONTENT_PATTERN])));
    let out = h.handle_op("ingest", &req(&e, &store));
    assert_eq!(out.status, 400);
    assert_eq!(code_of(&out.result), "ambiguous_input");

    let neither = Entity::make("system/content/ingest-request", Value::Map(vec![]));
    let e = exec("ingest", neither, Some(targets(&[CONTENT_PATTERN])));
    let out = h.handle_op("ingest", &req(&e, &store));
    assert_eq!(out.status, 400);
    assert_eq!(code_of(&out.result), "missing_input");
}

#[test]
fn an_envelope_with_no_root_is_400_not_an_empty_success() {
    // §6.3's `if envelope.root is not null` branch is unreachable for a well-formed
    // envelope: `system/envelope` extends `core/envelope`, whose `root` is a REQUIRED
    // `core/entity`. So a missing root is a malformed request, not an ingested_count:0.
    let store = Store::new();
    let h = ContentHandler::new();
    let params = Entity::make(
        "system/content/ingest-request",
        Value::Map(vec![(Key::Text("envelope".into()), Value::Map(vec![]))]),
    );
    let e = exec("ingest", params, Some(targets(&[CONTENT_PATTERN])));
    let out = h.handle_op("ingest", &req(&e, &store));
    assert_eq!(out.status, 400);
    assert_eq!(code_of(&out.result), "unexpected_params");
}
