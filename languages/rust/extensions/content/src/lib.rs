//! `entity_content` — CONTENT v3.7 for the `rust` keystone peer.
//!
//! **The public surface. What is not re-exported here is not part of it — and one
//! omission is a MUST rather than a taste:** `reassemble_content` lives in a `mod
//! internal` declared without `pub`, so it is invisible outside this crate. Not by
//! convention, not by an underscore: `error[E0603]`. `src/bin/deep_import.rs` is the
//! fixture that proves it, and `languages/rust/test` builds that fixture expecting the
//! failure — with a positive control, because a compile-fail check without one reports
//! its strongest result when the toolchain is broken.
//!
//! # What this port installs
//!
//! An extension has four faces (`docs/DESIGN-THE-SDK-LAYER.md`). **On this peer they now all get the
//! same answer**, which they did not for the first four compositions on `rust`:
//!
//! | face | on this peer | how we know |
//! |---|---|---|
//! | types (§11.1) | **installed** | `Store::bind` is `pub`; oracle-checked by content hash |
//! | emit consumer (§6.13(c)) | **installable** — unused by CONTENT | probe scenario 2, two negatives |
//! | SDK (§3.3/§5.3/§3.4) | **installed** — the handler runs through it | [`sdk`] |
//! | handler body (§11.6.1 step 4) | **installed** — `Peer::register_handler` (keystone H1) | the `content` category; probe scenario 1 |
//!
//! Until keystone landed H1 for K-9 the handler row read **NOT installable** (`501 no_handler_body`
//! with all four tree writes bound, `register_handler` private), and this crate deliberately had no
//! `install_content`: performing the four writes without a body moves a peer from
//! `404 handler_not_found`, which was true, to `501 no_handler_body`, which says a handler exists
//! and is broken. `register_handler` binds the entities and the body together, so the trap is gone
//! and the name is the other two ports' name.

pub mod chunking;
pub mod handler;
pub mod sdk;
pub mod types;

/// **NOT `pub`.** This one keyword's absence is the §3.4 boundary. See
/// `internal/mod.rs` for the three-language comparison.
mod internal;

pub use chunking::{
    cdc_boundaries, cdc_params, create_blob, create_blob_cdc, create_blob_fixed, gear_table, store_blob,
    Blob, CdcParams,
};
pub use handler::{
    ContentHandler, ContentOutcome, FrameBudget, HandlerRequest, FRAME_RESERVE_BYTES, OPERATIONS,
};

use std::sync::Arc;

use entity_core_protocol::peer::handler::{Handler, HandlerContext, HandlerSpec, RegisterError};
use entity_core_protocol::peer::Peer;
pub use sdk::{
    at_peer, bind_at_peer, create_descriptor, descriptor_matches_anchor, descriptor_path,
    ensure_closure, hash_hex_with_format, reassemble_under_capability, ClosureVerdict,
};
pub use types::{
    content_type_defs, content_type_entities, publish_content_types, ALL_TYPES, BLOB, CHUNK,
    CHUNKING_FASTCDC_NC2, CHUNKING_FIXED, CONTENT_PATTERN, CONTENT_RESPONSE, DEFAULT_CHUNK_SIZE,
    DESCRIPTOR, GET_BATCH_SIZE, GET_REQUEST, INGEST_REQUEST, INGEST_RESULT, MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
};

/// What [`install_content`] installed, so a caller can assert on it.
#[derive(Clone, Debug)]
pub struct ContentInstallation {
    pub pattern: String,
    pub interface_path: String,
    pub type_paths: Vec<String>,
}

/// Install CONTENT onto a live peer: the §6.1 handler through `Peer::register_handler`, then the
/// seven `system/type/*` entities.
///
/// `namespace` is §6.4's served prefix and defaults to [`CONTENT_PATTERN`]; the handler is always
/// installed AT [`CONTENT_PATTERN`], as on the other two ports. Refused (keystone H3) when a handler
/// is already bound there, before anything is written.
///
/// Takes `&Arc<Peer>` (it took `&Peer`): the certified surface, `Peer::register_handler`, installs
/// through the `Arc` so its handle can unregister. The handle is detached — installed for the peer's
/// life, as before.
pub fn install_content(peer: &Arc<Peer>, namespace: Option<&str>) -> Result<ContentInstallation, RegisterError> {
    let handler = match namespace {
        Some(ns) => ContentHandler::with_namespace(ns),
        None => ContentHandler::new(),
    };
    let handler: Arc<dyn Handler> = Arc::new(handler);
    let spec = HandlerSpec::new(handler.pattern(), handler.name()).operations(handler.operations());
    peer.register_handler(spec, move |ctx: &HandlerContext<'_>| handler.handle(ctx))?.detach();
    let local = &peer.local_peer;
    Ok(ContentInstallation {
        pattern: CONTENT_PATTERN.to_string(),
        interface_path: format!("/{local}/system/handler/{CONTENT_PATTERN}"),
        type_paths: publish_content_types(&peer.store, local),
    })
}
