//! §3.4 `reassemble_content` — **CRATE-PRIVATE. Not reachable from outside.**
//!
//! > "Implementations MUST NOT expose `reassemble_content` as a public substrate
//! > primitive callable from third-party / SDK / external consumer code without an
//! > explicit capability-checking wrapper — direct substrate access bypasses the
//! > dispatcher cap discipline and creates a capability-escalation surface for
//! > consumers holding non-root caps."   — EXTENSION-CONTENT §3.4
//!
//! §3.4 permits re-implementing the algorithm "for cases that operate inside the
//! trusted handler-context boundary", which is where this is called from:
//! `sdk::reassemble_under_capability`, which demands a `DispatchAuthority` that
//! nothing outside this crate can construct.

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::Value;

use crate::types::BLOB;

/// Bytes or a coded failure. Never an `Err` on a missing chunk — "missing chunk" is a
/// normal incremental-sync state, not an error condition of the algorithm.
///
/// A `Result<Vec<u8>, Code>` would have been the Rust reflex and would have been
/// wrong: it invites `?` at call sites, and a missing chunk propagating as an error
/// through `_get` would turn a 200-with-`missing` into a 500.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Reassembled {
    Ok(Vec<u8>),
    Failed { code: &'static str, hash: Vec<u8> },
}

pub(crate) fn reassemble_content(store: &Store, blob_hash: &[u8]) -> Reassembled {
    let failed = |code: &'static str, hash: &[u8]| Reassembled::Failed {
        code,
        hash: hash.to_vec(),
    };

    let blob = match store.get_by_hash(blob_hash) {
        Some(b) => b,
        None => return failed("blob_not_found", blob_hash),
    };
    if blob.typ != BLOB {
        return failed("not_a_blob", blob_hash);
    }

    let chunk_hashes = match blob.field("chunks") {
        Some(Value::Array(items)) => items.clone(),
        _ => return failed("not_a_blob", blob_hash),
    };

    let mut out: Vec<u8> = Vec::new();
    for item in &chunk_hashes {
        let h = match item {
            Value::Bytes(b) => b.as_slice(),
            _ => return failed("not_a_blob", blob_hash),
        };
        // **`blob_pending_sync` vs `not_found` is NOT decided here.** §3.4's predicate
        // is sync-state visibility — a peer returns 503 IFF it has an active
        // subscription on the namespace AND an inbox feeding the content store. This
        // composition has neither, so the caller maps this code to a terminal 404. The
        // code stays `blob_pending_sync` at this layer so the mapping lives at the one
        // place that knows the deployment's sync posture.
        let chunk: Entity = match store.get_by_hash(h) {
            Some(c) => c,
            None => return failed("blob_pending_sync", h),
        };
        match chunk.field("payload") {
            Some(Value::Bytes(p)) => out.extend_from_slice(p),
            _ => {}
        }
    }

    Reassembled::Ok(out)
}
