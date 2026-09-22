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
//! # What this port installs, and what it cannot
//!
//! An extension has four faces (`docs/DESIGN-THE-SDK-LAYER.md`). **On this peer they
//! do not get the same answer, and that is the result of the third port.**
//!
//! | face | on this peer | how we know |
//! |---|---|---|
//! | types (§11.1) | **installable** — [`install_content_types`] | `Store::bind` is `pub`; oracle-checked |
//! | emit consumer (§6.13(c)) | **installable** — unused by CONTENT | probe scenario 2, two negatives |
//! | SDK (§3.3/§5.3/§3.4) | **usable** — it is a library, it needs no peer hook | [`sdk`] |
//! | handler body (§11.6.1 step 4) | **NOT installable** | probe scenario 1: `501` with all four tree writes bound |
//!
//! So there is **no `install_content`** in this module, and its absence is deliberate.
//! The four §11.6.1 tree writes *are* individually performable — they are ordinary
//! `store.bind` calls — and performing them without a body is worse than doing
//! nothing: it moves the peer from `404 handler_not_found` to `501 no_handler_body`,
//! which reads as *installed and broken* rather than *absent*. Measured, not reasoned:
//! `gates/host-seam/rust`, scenario 1 arms A and B.
//!
//! Shipping a function that does that would be shipping a trap, so this crate does not
//! have one. [`ContentHandler`] is written, tested and correct; it has nowhere to go.
//!
//! # What that costs, stated plainly
//!
//! No wire-driven conformance check reaches [`handler`] or [`sdk`] on this peer.
//! `EXTENSION.toml` records `reached_by = []` for every SDK entry on this port. The
//! argument that "the extension is its own instrument" holds only where a gated path
//! runs THROUGH the SDK face, and here none does. The one third-party measurement this
//! substrate supports is `validate-peer`'s `type_system.type_system_content_*_match`,
//! which reads the entities [`install_content_types`] binds and compares content hashes
//! against `entity-core-go`'s independent transcription.

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
pub use sdk::{
    at_peer, bind_at_peer, create_descriptor, descriptor_matches_anchor, descriptor_path,
    ensure_closure, hash_hex_with_format, reassemble_under_capability, ClosureVerdict,
    DispatchAuthority,
};
pub use types::{
    content_type_defs, content_type_entities, publish_content_types, ALL_TYPES, BLOB, CHUNK,
    CHUNKING_FASTCDC_NC2, CHUNKING_FIXED, CONTENT_PATTERN, CONTENT_RESPONSE, DEFAULT_CHUNK_SIZE,
    DESCRIPTOR, GET_BATCH_SIZE, GET_REQUEST, INGEST_REQUEST, INGEST_RESULT, MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
};

use entity_core_protocol::peer::store::Store;

/// What [`install_content_types`] actually wrote, so a caller can assert on it.
#[derive(Clone, Debug)]
pub struct ContentTypeInstallation {
    pub type_paths: Vec<String>,
}

/// Publish CONTENT's seven `system/type/*` entities into a peer's tree.
///
/// **This is the whole install surface on this substrate**, and it is a real one: the
/// oracle's `type_system` category reads exactly these paths, and the three §11.1 types
/// among them are compared by content hash against `entity-core-go`'s own transcription.
/// A hand-built field map that is subtly wrong fails there and nowhere else.
///
/// Neither `typescript`'s nor `python`'s registration path writes type entities either
/// (measured, `gates/host-seam/probe-seam.mjs`: `type_blob/chunk/descriptor = NO`), so
/// this is the one §11.6.1-adjacent write that is the module's job in all three ports.
pub fn install_content_types(store: &Store, local_peer: &str) -> ContentTypeInstallation {
    ContentTypeInstallation {
        type_paths: publish_content_types(store, local_peer),
    }
}
