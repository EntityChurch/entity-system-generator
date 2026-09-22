//! CONTENT — the SDK face.
//!
//! **There is no conformance gate on this face, anywhere, and per the operator that is
//! correct rather than a defect: the SDK is a convention.** `EXTENSION.toml
//! [sdk].*.reached_by` records, per operation, which conformance check reaches it.
//!
//! **Today no check reaches any of these functions, on any port.** The handler is installed
//! on this peer (keystone H1, 2026-09-12) and the oracle drives it, but no port's handler calls
//! `ensure_closure`, `at_peer` or `reassemble_under_capability`. Until H1 the handler could not
//! be installed here at all (`501 no_handler_body` with all four §11.6.1 tree writes bound).
//!
//! **That is why the §3.4 re-anchoring of 2026-09-16 moved no conformance number and was never
//! going to.** `reassemble_under_capability` has no caller in this tree and no wire route: the
//! oracle is a wire client and cannot reach an in-process SDK function. The measurement is at
//! the type and unit level — see `tests/sdk.rs`, where the capability check is exercised in both
//! directions — and the conformance figures are re-run to show they did NOT move, which is a
//! different claim from showing that they did.

use entity_core_protocol::peer::capability;
use entity_core_protocol::peer::handler::HandlerContext;
use entity_core_protocol::peer::model::{self, Entity};
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

use crate::internal::reassemble::{reassemble_content, Reassembled};
use crate::types::{BLOB, CONTENT_PATTERN, DESCRIPTOR};

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
    let mut pairs: Vec<(Key, Value)> =
        vec![(Key::Text("content".into()), Value::Bytes(content.to_vec()))];
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
    descriptor.typ == DESCRIPTOR && descriptor.bytes_field("content") == Some(blob_hash)
}

// ── Reassembly — the §3.4 capability-checking wrapper ────────────────────────

/// The **only** public route to materialized blob bytes, and §3.4's *"explicit
/// capability-checking wrapper"* — **both of its clauses, on this port, since 2026-09-16.**
///
/// §3.4: *"Implementations MUST NOT expose `reassemble_content` as a public substrate
/// primitive callable from third-party / SDK / external consumer code without an explicit
/// capability-checking wrapper — direct substrate access bypasses the dispatcher cap
/// discipline and creates a capability-escalation surface for consumers holding non-root
/// caps."* That sentence has two halves, and until this change this port satisfied neither
/// of them in the form it states.
///
/// **1 — the anchor is DISPATCHER-BUILT, not crate-local.** `HandlerContext` cannot be
/// constructed outside the peer crate: its fields are `pub(crate)`
/// (`HandlerContext`, `protocol-generator/rust/src/peer/handler.rs:470`), and `Peer::route`
/// is the only site in the peer that builds one (`core.rs:911`) — both at keystone
/// `a8423d2b`, one construction site in the whole tree, verified by grep. It is reached only
/// after §5.2's `check_permission` ALLOWs (`core.rs:884-888`), and a request with no caller
/// capability is refused `403 capability_denied` BEFORE the context exists (`core.rs:879-882`).
/// So holding a `&HandlerContext` is the statement *the dispatcher authorized you*, which
/// is the thing §3.4 is about.
///
/// This replaces `DispatchAuthority`, a crate-private token that was unforgeable and proved
/// the wrong proposition — *you came through this crate's handler*, whose `handle_op` is also
/// callable in-process. It was minted in one place, dropped immediately, and read by nothing.
///
/// **2 — the CAPABILITY IS CHECKED, against a target the caller must name.** §3.4 routes
/// materialization through `system/content:get` (namespace-cap-scoped) or `local/files:read`
/// (tree-path-cap-scoped); both are scoped to a PATH, so the wrapper cannot check anything
/// without one, and the old signature had nowhere to put it. `target` is that path, and the
/// check is the peer's own §6.3 predicate (`check_path_permission`,
/// `protocol-generator/rust/src/peer/capability.rs:431`) — the same one the handler's §6.4
/// step 2 runs, so the two cannot drift into two readings of one clause.
///
/// **And the store is no longer an argument.** It is read from the context. A caller who
/// could pass any `&Store` could hand this function a store the dispatcher never authorized
/// anything against, which made the capability check — had one existed — a check about the
/// wrong subject.
///
/// Returns `Err(("capability_denied", vec![]))` on refusal: the hash slot carries the
/// *pending* chunk for `blob_pending_sync` and there is no hash to report for a denial.
pub fn reassemble_under_capability(
    ctx: &HandlerContext<'_>,
    target: &str,
    blob_hash: &[u8],
) -> Result<Vec<u8>, (&'static str, Vec<u8>)> {
    if !authorizes(
        ctx.pattern(),
        ctx.operation(),
        target,
        ctx.caller_capability(),
        ctx.local_peer(),
    ) {
        return Err(("capability_denied", Vec::new()));
    }
    match reassemble_content(&ctx.peer().store, blob_hash) {
        Reassembled::Ok(bytes) => Ok(bytes),
        Reassembled::Failed { code, hash } => Err((code, hash)),
    }
}

/// The §3.4 decision, as a pure function of the five values the context carries.
///
/// **Split out so it can be MEASURED, and that is the whole reason.** The wrapper above
/// cannot be called from a test: `HandlerContext` is the dispatcher's and a consumer cannot
/// construct one — which is exactly the property `src/bin/deep_import.rs` claims as `E0451`.
/// Left inline, the capability check would be a branch nothing could ever execute in either
/// direction, in a function with no caller in this tree: a face nobody can reach is a face
/// whose contents are unmeasured (D23), and a security check that has never been observed
/// refusing is not a check.
///
/// `pub(crate)`, not `pub`: it takes five loose arguments with no context to bind them, so
/// exporting it would put a route to the decision beside the route to the bytes and invite a
/// caller to answer the question itself. The unit tests below are inside this module and see
/// it; `tests/sdk.rs` is a third party and does not.
pub(crate) fn authorizes(
    pattern: &str,
    operation: &str,
    target: &str,
    caller_capability: Option<&Entity>,
    local_peer: &str,
) -> bool {
    // The context is unforgeable, but it is not necessarily OURS: a body installed at
    // another pattern holds one too, and §3.4's grant discipline is per handler. The
    // pattern is set by the dispatcher from the resolved handler, never by the caller.
    if pattern != CONTENT_PATTERN {
        return false;
    }
    // FAIL CLOSED on an absent capability, and the asymmetry with the handler's §6.4
    // step 2 is deliberate. There, `None` models an in-process call with no token and is
    // reachable from our own unit tests. HERE the context is the dispatcher's, and
    // `Peer::route` refuses `None` with `403 capability_denied` before building one
    // (`protocol-generator/rust/src/peer/core.rs:879-882` @ keystone `a8423d2b`) — so on
    // this path `None` is not "a call without a token", it is a state the peer says
    // cannot exist. Turning an impossible state into an unchecked one is how the
    // escalation surface §3.4 names gets built.
    let cap = match caller_capability {
        Some(c) => c,
        None => return false,
    };
    // The peer's own §6.3 predicate — the same one the handler's §6.4 step 2 runs, so the
    // two cannot drift into two readings of one clause.
    capability::check_path_permission(operation, target, cap, CONTENT_PATTERN, local_peer)
}

#[cfg(test)]
mod authorization_tests {
    //! §3.4 clause 2, in both directions, against a real grant rather than a stub.
    //!
    //! These are unit tests inside `src/` on purpose, which is the opposite of the choice
    //! `tests/sdk.rs` documents for the export-surface assertion — and for the opposite
    //! reason. That one must see the crate as a third party does. This one must see a
    //! `pub(crate)` function, and what it measures is a DECISION rather than a boundary.
    //!
    //! **CONTROL, executed 2026-09-16 with the SUBJECT REMOVED** — `authorizes` stubbed to
    //! `return true`, which is what "no capability check" means here and is the state this
    //! port was in the day before:
    //!
    //! ```text
    //! test result: FAILED. 1 passed; 5 failed
    //! ```
    //!
    //! Five refusals red, `a_covering_capability_authorizes` still green. That split is the
    //! reading worth keeping: had the positive gone red too, the fixture would be broken
    //! rather than the subject, and five reds would prove nothing (D15 sharpened — the
    //! control is the absence of the subject, and a control that does not move is a
    //! finding about who owns the property).

    use super::*;
    use entity_core_protocol::peer::model::Entity;
    use entity_core_protocol::value::{Key, Value};

    const PEER: &str = "peer1";

    fn scope(include: &[&str]) -> Value {
        Value::Map(vec![(
            Key::Text("include".into()),
            Value::Array(include.iter().map(|s| Value::Text((*s).into())).collect()),
        )])
    }

    /// A capability token in the shape `capability::grants_of_token` parses.
    ///
    /// Hand-built because the peer's own `mint_token` is private. It is never signed and
    /// never dispatched; `check_path_permission` reads only `grants`, and the signature,
    /// chain, temporal bounds and revocation are `verify_request`'s — which on the real
    /// path has already run before any context exists.
    fn cap_with(operations: &[&str], handlers: &[&str], resources: &[&str]) -> Entity {
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

    fn covering() -> Entity {
        cap_with(
            &["get"],
            &["system/content"],
            &["/peer1/system/content/docs"],
        )
    }

    #[test]
    fn a_covering_capability_authorizes() {
        // THE POSITIVE CONTROL. Without it every refusal below is satisfied by a
        // predicate that answers `false` unconditionally, which is the cheapest way to
        // pass a suite of denial tests (D15).
        assert!(authorizes(
            CONTENT_PATTERN,
            "get",
            "/peer1/system/content/docs",
            Some(&covering()),
            PEER
        ));
    }

    #[test]
    fn a_capability_covering_another_path_is_refused() {
        // The §3.4 escalation surface in one line: a consumer holding a real, verified,
        // non-root capability, reaching for bytes its grant does not cover.
        assert!(!authorizes(
            CONTENT_PATTERN,
            "get",
            "/peer1/system/content/secrets",
            Some(&covering()),
            PEER
        ));
    }

    #[test]
    fn a_capability_for_another_operation_is_refused() {
        assert!(!authorizes(
            CONTENT_PATTERN,
            "ingest",
            "/peer1/system/content/docs",
            Some(&covering()),
            PEER
        ));
    }

    #[test]
    fn a_capability_scoped_to_another_handler_is_refused() {
        let other = cap_with(&["get"], &["system/tree"], &["/peer1/system/content/docs"]);
        assert!(!authorizes(
            CONTENT_PATTERN,
            "get",
            "/peer1/system/content/docs",
            Some(&other),
            PEER
        ));
    }

    #[test]
    fn no_capability_fails_closed() {
        assert!(!authorizes(
            CONTENT_PATTERN,
            "get",
            "/peer1/system/content/docs",
            None,
            PEER
        ));
    }

    #[test]
    fn a_context_belonging_to_another_handler_is_refused() {
        // Clause 1's residue. The context is unforgeable, so this cannot be reached by a
        // consumer — but a body at another pattern holds one, and the grant discipline is
        // per handler. The capability here COVERS everything asked; only the pattern is
        // wrong, so nothing but the first check can produce this refusal.
        let broad = cap_with(&["get"], &["*"], &["/peer1/*"]);
        assert!(!authorizes(
            "system/files",
            "get",
            "/peer1/system/content/docs",
            Some(&broad),
            PEER
        ));
        assert!(authorizes(
            CONTENT_PATTERN,
            "get",
            "/peer1/system/content/docs",
            Some(&broad),
            PEER
        ));
    }
}
