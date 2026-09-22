//! CONTENT — the SDK face.
//!
//! **There is no conformance gate on this face, anywhere, and per the operator that is
//! correct rather than a defect: the SDK is a convention.** `EXTENSION.toml
//! [sdk].*.reached_by` records, per operation, which conformance check reaches it.
//!
//! **Today no check reaches any of these functions, on any port.** The handler is installed
//! on this peer (keystone H1, 2026-09-12) and the oracle drives it, but no port's handler calls
//! `ensure_closure`, `at_peer` or `reassemble_under_capability`; this handler only mints a
//! [`DispatchAuthority`]. Until H1 the handler could not be installed here at all
//! (`501 no_handler_body` with all four §11.6.1 tree writes bound).

use entity_core_protocol::peer::model::{self, Entity};
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

use crate::internal::reassemble::{reassemble_content, Reassembled};
use crate::types::{BLOB, DESCRIPTOR};

/// Lowercase hex INCLUDING the leading format byte (§6.4.2 / core §3.5).
///
/// 66 chars under ECFv1-SHA-256, 98 under SHA-384. The length is implied by the
/// leading byte and is never assumed, so nothing here checks it. Dropping the format
/// byte — the bare 64-char digest — is the mistake §6.4.2 calls out by name: it
/// destroys the algorithm discriminator and breaks URL-to-binding parity with
/// NETWORK §6.5.6.
///
/// Delegates to the peer's own `model::hex` rather than formatting here. The peer
/// renders every hash it binds through that function, so using it removes one way for
/// a path we construct to disagree with a path it constructed.
pub fn hash_hex_with_format(h: &[u8]) -> String {
    model::hex(h)
}

// ── EnsureClosure — §3.3 verify_content ──────────────────────────────────────

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ClosureVerdict {
    Complete {
        total_size: usize,
        chunk_count: usize,
    },
    Incomplete {
        code: &'static str,
        hash: Vec<u8>,
    },
}

/// §3.3 — completeness and total-size consistency over a blob already in the store.
///
/// §3.7 classifies this **Conformance**: "implementations MUST agree on whether a blob
/// is complete ... the completeness verdict is cross-peer-uniform." So the failure
/// modes are named exactly as §3.3 names them, and **the order matters**: a blob whose
/// first chunk is missing reports `missing_chunk`, not `size_mismatch`, even though
/// the totals also disagree.
///
/// Per-chunk size is deliberately NOT validated against `chunk_size` — §3.3 says so
/// outright, because content-defined chunking produces variable-size chunks and the
/// entity hash already guarantees chunk integrity.
pub fn ensure_closure(store: &Store, blob_hash: &[u8]) -> ClosureVerdict {
    let bad = |code: &'static str, hash: &[u8]| ClosureVerdict::Incomplete {
        code,
        hash: hash.to_vec(),
    };

    let blob = match store.get_by_hash(blob_hash) {
        Some(b) => b,
        None => return bad("blob_not_found", blob_hash),
    };
    if blob.typ != BLOB {
        return bad("not_a_blob", blob_hash);
    }
    let chunk_hashes = match blob.field("chunks") {
        Some(Value::Array(items)) => items.clone(),
        _ => return bad("not_a_blob", blob_hash),
    };

    let mut total = 0usize;
    for item in &chunk_hashes {
        let h = match item {
            Value::Bytes(b) => b.as_slice(),
            _ => return bad("not_a_blob", blob_hash),
        };
        let chunk = match store.get_by_hash(h) {
            Some(c) => c,
            None => return bad("missing_chunk", h),
        };
        let payload_len = match chunk.field("payload") {
            Some(Value::Bytes(p)) => p.len(),
            _ => 0,
        };
        if payload_len == 0 {
            return bad("empty_chunk", h);
        }
        total += payload_len;
    }

    match blob.uint_field("total_size") {
        Some(declared) if declared as usize == total => ClosureVerdict::Complete {
            total_size: total,
            chunk_count: chunk_hashes.len(),
        },
        _ => bad("size_mismatch", blob_hash),
    }
}

// ── AtPeer — §6.4.2 Hash Tree Presence ───────────────────────────────────────

/// The §6.4.2 canonical namespace probe: is hash `H` bound at
/// `{namespace}/{hex(H)}` in this peer's tree?
///
/// **Unmeasured by any gate.** The oracle's content category has no namespace check.
/// Stated, not hidden.
pub fn at_peer(store: &Store, local_peer: &str, namespace: &str, h: &[u8]) -> Option<Entity> {
    store.get_at(&format!(
        "/{local_peer}/{namespace}/{}",
        hash_hex_with_format(h)
    ))
}

/// The §6.4.2 ingest-side binding. Paired with [`at_peer`]; one convention, two
/// directions.
pub fn bind_at_peer(store: &Store, local_peer: &str, namespace: &str, entity: &Entity) -> String {
    let path = format!(
        "/{local_peer}/{namespace}/{}",
        hash_hex_with_format(&entity.hash)
    );
    store.bind(&path, entity);
    path
}

// ── Descriptors — §2.4 presence rule, §5.3 path + integrity check ────────────

/// §2.4 — build a descriptor, enforcing the presence rule the type system cannot
/// express: **at least one of `media_type` or `type_ref` MUST be present.** Both MAY be.
///
/// Returns `Err` rather than emitting an invalid entity: a descriptor with neither is
/// a content-addressed statement that says nothing, and once bound it is
/// indistinguishable from a corrupt one.
///
/// The other two ports raise. Here it is a `Result`, because a panicking constructor in
/// a library crate is a different contract — the caller cannot recover from it and the
/// §2.4 violation is a caller error, not an invariant break.
pub fn create_descriptor(
    content: &[u8],
    media_type: Option<&str>,
    type_ref: Option<&[u8]>,
    name: Option<&str>,
) -> Result<Entity, &'static str> {
    if media_type.is_none() && type_ref.is_none() {
        return Err("CONTENT §2.4 presence rule: a descriptor MUST carry media_type or type_ref");
    }
    let mut pairs: Vec<(Key, Value)> = vec![(
        Key::Text("content".into()),
        Value::Bytes(content.to_vec()),
    )];
    if let Some(m) = media_type {
        pairs.push((Key::Text("media_type".into()), Value::Text(m.to_string())));
    }
    if let Some(t) = type_ref {
        pairs.push((Key::Text("type_ref".into()), Value::Bytes(t.to_vec())));
    }
    if let Some(n) = name {
        pairs.push((Key::Text("name".into()), Value::Text(n.to_string())));
    }
    Ok(Entity::make(DESCRIPTOR, Value::Map(pairs)))
}

/// §5.3 — the dual-level path `{publisher}/system/content/descriptor/{B_hex}/{D_hex}`.
pub fn descriptor_path(publisher_peer_id: &str, blob_hash: &[u8], descriptor: &Entity) -> String {
    format!(
        "/{publisher_peer_id}/{DESCRIPTOR}/{}/{}",
        hash_hex_with_format(blob_hash),
        hash_hex_with_format(&descriptor.hash)
    )
}

/// §5.3 integrity check (**MUST**): a consumer fetching a descriptor at
/// `.../{B_hex}/{D_hex}` MUST verify `descriptor.data.content == B`. Mismatch => reject.
///
/// Two-level defence — the path embeds `B_hex`, the body carries `hash(B)`, and both
/// must agree.
pub fn descriptor_matches_anchor(descriptor: &Entity, blob_hash: &[u8]) -> bool {
    descriptor.typ == DESCRIPTOR
        && descriptor.bytes_field("content") == Some(blob_hash)
}

// ── Reassembly — the §3.4 capability-checking wrapper ────────────────────────

/// A token that only this crate can mint.
///
/// **This is §3.4's "explicit capability-checking wrapper", and no port satisfies it
/// fully** (`EXTENSION.toml [substrate.capability_wrapper]`, corrected 2026-09-12).
///
/// On `typescript` and `python` the wrapper demands the peer's dispatch context, but that
/// context is constructible by any caller, and no port checks the capability against the
/// blob or namespace.
///
/// **This wrapper does not demand one.** Until keystone's H1 (2026-09-12) there was no such
/// value on this peer: the dispatch context was `(&mut Conn, &Envelope)` with `Conn` freely
/// constructible, and no handler body was reachable from dispatch. The peer's
/// `HandlerContext` now has `pub(crate)` fields and is built by the dispatcher, but this
/// type was not changed to require it. So what it proves is stated narrowly: **you got
/// here through this crate's handler** — whose `handle_op` is also callable in-process —
/// not **the dispatcher authorized you**.
///
/// It is unforgeable — a tuple struct with a private field cannot be constructed
/// outside the crate, and the constructor is `pub(crate)` — which makes it the only one
/// of the three ports' wrappers a third party cannot forge. It still checks no capability.
/// The two §3.4 clauses are recorded separately in `EXTENSION.toml` for that reason.
pub struct DispatchAuthority(());

impl DispatchAuthority {
    pub(crate) fn mint() -> DispatchAuthority {
        DispatchAuthority(())
    }
}

/// The **only** public route to materialized blob bytes.
///
/// The `_authority` parameter is load-bearing despite being unused in the body: it is
/// the type-level statement that the caller came through this crate's handler. An
/// underscore-prefixed unused parameter would silence the warning and lose the point,
/// so it is named and the `let _ = ` below consumes it explicitly.
pub fn reassemble_under_capability(
    authority: &DispatchAuthority,
    store: &Store,
    blob_hash: &[u8],
) -> Result<Vec<u8>, (&'static str, Vec<u8>)> {
    let _ = authority;
    match reassemble_content(store, blob_hash) {
        Reassembled::Ok(bytes) => Ok(bytes),
        Reassembled::Failed { code, hash } => Err((code, hash)),
    }
}
