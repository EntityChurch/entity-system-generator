//! `entity_history` — HISTORY v1.10 for the `rust` keystone peer.
//!
//! **THE PUBLIC SURFACE.** What is absent from it is as deliberate as what is present:
//! `mod internal` is declared without `pub`, so `record_transition` is invisible outside
//! this crate — `error[E0603]`, not a convention and not an underscore. A caller able to
//! reach it could append a forged entry to an audit chain: any `author`, any
//! `capability`, at any path, linked into the real chain by `previous` and
//! content-addressed exactly like a real one. `src/bin/deep_import.rs` is the fixture
//! that proves the refusal and `languages/rust/test` builds it expecting E0603
//! specifically.
//!
//! # The four faces, and the answer this port gives each of them
//!
//! | face | on this peer | how we know |
//! |---|---|---|
//! | types (§9.2) | **installed** | `Store::bind` is `pub`; the oracle's six `type_*` checks read the paths |
//! | emit consumer (§5.1) | **installed AND RUNNING** | `gates/host-seam` arms D/E/F, plus **arm G**, which measured that a consumer may WRITE from inside the callback |
//! | SDK | **installed** — the handler runs through it | the gated path is the handler |
//! | handler body (§4.3) | **installed** — `Peer::register_handler` (keystone H1) | the `history` category reads the chain through `system/history:query`; host-seam scenario 1 |
//!
//! **This port was the sharpest case of D13's face amendment**: a write face that installed and
//! recorded a real audit chain, and a read face that could not be installed, so `validate-peer`'s
//! `history` category scored 7 of 34 against a recorder working perfectly. Keystone landed H1 on
//! this peer for K-9 and the read face now installs through [`install_history`] — the other two
//! ports' call. The recorder did not change.
//!
//! **§2.1's "handler grant" has a referent now.** `register_handler` binds a self-issued grant at
//! `system/capability/grants/system/history`; [`install_history`] reads its hash back and the
//! recorder stamps it as the autonomous case's `capability`. Before H1 there was no grant to name and
//! the host passed the local identity hash, so `author == capability` on every autonomous transition.

pub mod handler;
pub mod patterns;
pub mod sdk;
pub mod types;

/// **NOT `pub`.** This one keyword's absence is the boundary. See `internal/mod.rs`.
mod internal;

use std::sync::{Arc, Weak};

use entity_core_protocol::peer::handler::{Handler, HandlerContext, HandlerSpec, RegisterError};
use entity_core_protocol::peer::store::TreeChangeEvent;
use entity_core_protocol::peer::Peer;

pub use handler::{HandlerRequest, HistoryHandler, HistoryOutcome, OPERATIONS};
pub use patterns::{
    canonicalize_pattern, compare_specificity, pattern_matches, pattern_specificity, Specificity,
};
pub use sdk::{
    build_context, config_path, history_config, resolve_config, CarriedContext, HistoryRecorder,
    RecorderStats,
};
pub use types::{
    from_core_event_type, history_entity, history_type_defs, history_type_entities,
    publish_history_types, ALL_TYPES, CONFIG, CONFIG_PREFIX, DEFAULT_EVENTS, DEFAULT_QUERY_LIMIT,
    EVENT_ACCESSED, EVENT_CREATED, EVENT_DELETED, EVENT_UPDATED, HEAD_PREFIX, HISTORY_PATTERN,
    QUERY_PARAMS, QUERY_RESULT, ROLLBACK_PARAMS, ROLLBACK_RESULT, TRANSITION,
};

/// The shapes a consumer names. Re-exported from the private module, which is what makes
/// them nameable without making `record_transition` reachable — the same façade
/// `typescript`'s `export type { ... } from "./internal/recorder.js"` builds, enforced
/// here rather than promised.
pub use internal::recorder::{
    ConfigLookup, HistoryConfig, RecordedTransition, RecorderIdentity, TransitionContext,
};

/// What [`install_history`] installed, and the two facts a reader of the audit trail needs
/// before trusting it.
#[derive(Clone)]
pub struct HistoryInstallation {
    pub pattern: String,
    pub interface_path: String,
    pub type_paths: Vec<String>,
    pub recorder: Arc<HistoryRecorder>,
    /// Whether §2.1's "handler grant" had a referent: the self-issued grant `register_handler`
    /// binds, READ BACK from the tree. `false` would mean the recorder fell back to the local
    /// identity hash, which is what this port did before keystone's H1.
    pub handler_grant_available: bool,
}

impl HistoryInstallation {
    /// `"unknown"` | `"yes"` | `"not-observed"` — OBSERVED, never declared.
    ///
    /// A method, not a field, and that is the point: the field it replaced was a
    /// hardcoded `false` that said "measured". See `HistoryRecorder::context_observed`.
    pub fn context_available(&self) -> &'static str {
        self.recorder.context_observed()
    }
}

/// Install HISTORY onto a live peer: the handler, six types, and the position-4 recorder.
///
/// # The order, and it is the other two ports'
///
/// `register_handler` binds four §11.6.1 entities and type publication six more; the recorder is
/// registered LAST, so the audit log does not open with ten writes nobody performed.
///
/// # Why this takes `&Arc<Peer>` and the recorder holds a `Weak`
///
/// `Store::register_tree_consumer` wants `Fn(&TreeChangeEvent) + Send + Sync + 'static`. The store
/// lives inside the peer, so a closure capturing `Arc<Peer>` would be owned by that peer's own
/// store — a reference cycle a process-lifetime host would never notice. So it upgrades per event.
///
/// # Position 4 is the composition's, and this function cannot enforce it
///
/// SYSTEM-COMPOSITION §2.2 puts history at position 4. `register_tree_consumer` pushes onto a `Vec`
/// with no position argument, so the order is the wiring program's call order.
pub fn install_history(
    peer: &Arc<Peer>,
    max_walk: Option<u64>,
) -> Result<HistoryInstallation, RegisterError> {
    let handler = match max_walk {
        Some(n) => HistoryHandler::with_max_walk(n),
        None => HistoryHandler::new(),
    };
    let handler: Arc<dyn Handler> = Arc::new(handler);
    // The certified surface (`install.handler`), detached: the handle unregisters on drop.
    let spec = HandlerSpec::new(handler.pattern(), handler.name()).operations(handler.operations());
    peer.register_handler(spec, move |ctx: &HandlerContext<'_>| handler.handle(ctx))?
        .detach();

    let local = peer.local_peer.clone();
    let type_paths = publish_history_types(&peer.store, &local);

    // §2.1's autonomous `capability` — the grant `register_handler` just bound, read back rather
    // than assumed. The fallback is this port's pre-H1 answer and is reported, not hidden.
    let grant = peer
        .store
        .get_at(&format!(
            "/{local}/system/capability/grants/{HISTORY_PATTERN}"
        ))
        .filter(|e| e.typ == "system/capability/token");
    let handler_grant_available = grant.is_some();
    let identity = RecorderIdentity {
        local_identity_hash: peer.identity.identity_hash.clone(),
        handler_grant_hash: grant
            .map(|g| g.hash)
            .unwrap_or_else(|| peer.identity.identity_hash.clone()),
        local_peer: local.clone(),
    };
    let recorder = Arc::new(HistoryRecorder::new(identity));

    let weak: Weak<Peer> = Arc::downgrade(peer);
    let consumer = recorder.clone();
    peer.store
        .register_tree_consumer(move |ev: &TreeChangeEvent| {
            // A dropped peer means the process is tearing down; there is nothing to record into.
            let Some(peer) = weak.upgrade() else { return };
            consumer.on_tree_change(&peer.store, ev);
        });

    Ok(HistoryInstallation {
        pattern: HISTORY_PATTERN.to_string(),
        interface_path: format!("/{local}/system/handler/{HISTORY_PATTERN}"),
        type_paths,
        recorder,
        handler_grant_available,
    })
}
