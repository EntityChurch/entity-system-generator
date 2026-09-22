//! §3.3 closure, §2.4 / §5.3 descriptors, §6.4.2 namespace binding — and the positive
//! half of the §3.4 export-surface check.
//!
//! An integration test in `tests/` sees the crate exactly as a third party does: only
//! the public surface. That is why the §3.4 assertion lives here rather than in a unit
//! test beside the code — a `#[cfg(test)] mod tests` inside `src/` would see the
//! private module and prove nothing about the boundary.

use entity_content::{
    create_blob_fixed, create_descriptor, descriptor_matches_anchor, descriptor_path,
    ensure_closure, hash_hex_with_format, store_blob, ClosureVerdict, DESCRIPTOR,
};
use entity_core_protocol::peer::handler::HandlerContext;
use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

// ── §3.3 verify_content ──────────────────────────────────────────────────────

#[test]
fn a_complete_blob_is_complete() {
    let store = Store::new();
    let blob = create_blob_fixed(b"abcdefghijklmnop", 4);
    let h = store_blob(&store, &blob);
    match ensure_closure(&store, &h) {
        ClosureVerdict::Complete {
            total_size,
            chunk_count,
        } => {
            assert_eq!(total_size, 16);
            assert_eq!(chunk_count, 4);
        }
        other => panic!("expected Complete, got {other:?}"),
    }
}

#[test]
fn a_missing_chunk_reports_missing_chunk_and_not_size_mismatch() {
    // §3.3's ORDER is normative: a blob whose first chunk is missing reports
    // `missing_chunk`, even though the totals also disagree. §3.7 classifies the
    // completeness verdict as cross-peer-uniform, so the code a peer returns is part
    // of the contract and not a diagnostic detail.
    let store = Store::new();
    let blob = create_blob_fixed(b"abcdefghijklmnop", 4);
    // Store the manifest but NOT the chunks.
    store.put_entity(&blob.blob);
    match ensure_closure(&store, &blob.blob.hash) {
        ClosureVerdict::Incomplete { code, hash } => {
            assert_eq!(code, "missing_chunk");
            assert_eq!(hash, blob.chunks[0].hash);
        }
        other => panic!("expected Incomplete, got {other:?}"),
    }
}

#[test]
fn a_declared_total_that_disagrees_is_size_mismatch() {
    // NEGATIVE CONTROL for the test above: with every chunk present, the SAME function
    // must reach the size check and report the other code. Without this, "it said
    // missing_chunk" is consistent with a function that always says missing_chunk.
    let store = Store::new();
    let real = create_blob_fixed(b"abcdefghijklmnop", 4);
    for c in &real.chunks {
        store.put_entity(c);
    }
    // A manifest naming the same chunks but lying about the total.
    let lying = Entity::make(
        "system/content/blob",
        Value::Map(vec![
            (Key::Text("total_size".into()), Value::UInt(99)),
            (Key::Text("chunk_size".into()), Value::UInt(4)),
            (Key::Text("chunking".into()), Value::UInt(0)),
            (
                Key::Text("chunks".into()),
                Value::Array(
                    real.chunks
                        .iter()
                        .map(|c| Value::Bytes(c.hash.clone()))
                        .collect(),
                ),
            ),
        ]),
    );
    store.put_entity(&lying);
    match ensure_closure(&store, &lying.hash) {
        ClosureVerdict::Incomplete { code, .. } => assert_eq!(code, "size_mismatch"),
        other => panic!("expected size_mismatch, got {other:?}"),
    }
}

#[test]
fn a_non_blob_entity_is_not_a_blob() {
    let store = Store::new();
    let e = Entity::make("system/type", Value::Map(vec![]));
    store.put_entity(&e);
    match ensure_closure(&store, &e.hash) {
        ClosureVerdict::Incomplete { code, .. } => assert_eq!(code, "not_a_blob"),
        other => panic!("expected not_a_blob, got {other:?}"),
    }
}

// ── §6.4.2 / core §3.5 the format byte ───────────────────────────────────────

#[test]
fn hash_hex_includes_the_leading_format_byte() {
    // 66 chars under ECFv1-SHA-256. Dropping the format byte -- the bare 64-char digest
    // -- is the mistake §6.4.2 calls out by name: it destroys the algorithm
    // discriminator and breaks URL-to-binding parity with NETWORK §6.5.6.
    let e = Entity::make("system/type", Value::Map(vec![]));
    let hex = hash_hex_with_format(&e.hash);
    assert_eq!(hex.len(), 66, "expected 33 bytes of hex, got {}", hex.len());
    assert!(
        hex.starts_with("00"),
        "format byte 0 (ecfv1-sha256) must lead"
    );
}

// ── §2.4 / §5.3 descriptors ──────────────────────────────────────────────────

#[test]
fn a_descriptor_with_neither_media_type_nor_type_ref_is_refused() {
    // The §2.4 presence rule the type system cannot express. A descriptor with neither
    // is a content-addressed statement that says nothing, and once bound it is
    // indistinguishable from a corrupt one.
    assert!(create_descriptor(&[0u8; 33], None, None, Some("x")).is_err());
    assert!(create_descriptor(&[0u8; 33], Some("text/plain"), None, None).is_ok());
    assert!(create_descriptor(&[0u8; 33], None, Some(&[0u8; 33]), None).is_ok());
}

#[test]
fn the_five_three_integrity_check_rejects_a_mismatched_anchor() {
    let blob = create_blob_fixed(b"payload", 4);
    let d = create_descriptor(
        &blob.blob.hash,
        Some("application/octet-stream"),
        None,
        None,
    )
    .unwrap();
    assert!(descriptor_matches_anchor(&d, &blob.blob.hash));
    // NEGATIVE CONTROL: the same function must reject a different anchor, or "it
    // matched" says nothing.
    assert!(!descriptor_matches_anchor(&d, &[9u8; 33]));
    // And a non-descriptor entity is rejected on type before content.
    let not_a_descriptor = Entity::make("system/type", Value::Map(vec![]));
    assert!(!descriptor_matches_anchor(
        &not_a_descriptor,
        &blob.blob.hash
    ));
}

#[test]
fn the_descriptor_path_is_dual_level_and_both_levels_carry_the_format_byte() {
    let blob = create_blob_fixed(b"payload", 4);
    let d = create_descriptor(&blob.blob.hash, Some("text/plain"), None, None).unwrap();
    let path = descriptor_path("PEERID", &blob.blob.hash, &d);
    assert_eq!(
        path,
        format!(
            "/PEERID/{DESCRIPTOR}/{}/{}",
            hash_hex_with_format(&blob.blob.hash),
            hash_hex_with_format(&d.hash)
        )
    );
}

// ── §3.4 — the positive half of the export-surface check ─────────────────────

#[test]
fn the_only_public_route_to_bytes_demands_the_dispatchers_context_and_a_target() {
    // POSITIVE CONTROL for `src/bin/deep_import.rs`, which must FAIL to compile. If
    // this file did not compile, that failure would be indistinguishable from the
    // fixture's and the §3.4 claim would rest on a broken build (D15).
    //
    // RE-ANCHORED 2026-09-16. This assertion used to name `&DispatchAuthority` — a
    // crate-private token that was unforgeable and proved the wrong proposition: *you
    // came through this crate's handler*, whose `handle_op` is also callable in-process.
    // It now names `&HandlerContext`, which only the peer's dispatcher can construct
    // (`Peer::route`, the one construction site in the peer tree) and only after §5.2's
    // `check_permission` ALLOWs.
    //
    // **The `&str` in the middle is the half that was missing entirely.** §3.4 routes
    // materialization through cap-scoped surfaces — namespace-scoped `system/content:get`
    // or tree-path-scoped `local/files:read` — and both are scoped to a PATH. The old
    // signature had nowhere to put one, so the wrapper could not have checked a
    // capability against anything even if it had tried to.
    //
    // **And `&Store` is GONE from the signature, which is a strengthening rather than a
    // tidy-up.** A caller who could pass any store could hand this function one the
    // dispatcher never authorized anything against, making the check — had one existed —
    // a check about the wrong subject. The store now comes from the context.
    //
    // The assertion is on the SIGNATURE, which is what the boundary is made of. Naming
    // the function without calling it is the whole test: it compiles only if the public
    // surface is what we claim. The DECISION behind it is measured in both directions in
    // `src/sdk.rs`'s `authorization_tests`, which is a unit module because this file —
    // being a third party, correctly — cannot construct a context to drive it with.
    let f: fn(&HandlerContext<'_>, &str, &[u8]) -> Result<Vec<u8>, (&'static str, Vec<u8>)> =
        entity_content::reassemble_under_capability;
    let _ = f;
}
