//! `entity_history` — HISTORY v1.7 for the `rust` keystone peer.
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
//! `rust × CONTENT` established that an extension's faces do not all get the same answer
//! on one peer (D13's 2026-09-06 amendment). **This port is the sharper case**, because
//! the faces that install here are the ones that do the work, and the face that cannot
//! is the one that lets anybody see it happened.
//!
//! | face | on this peer | how we know |
//! |---|---|---|
//! | types (§9.2) | **installed** — [`install_history_types`] | `Store::bind` is `pub`; the oracle's six `type_*` checks read the paths |
//! | emit consumer (§5.1) | **installed AND RUNNING** — [`install_history_recorder`] | `gates/host-seam` arms D/E/F, plus **arm G**, which measured that a consumer may WRITE from inside the callback |
//! | SDK | library-only | no gated path reaches it here |
//! | handler body (§4.3) | **NOT installable** | `501` with all four §11.6.1 tree writes bound; `404` with none |
//!
//! So there is **no `install_history`** in this module, and its absence is deliberate —
//! the same refusal `../content` makes and for the same reason: performing the four
//! §11.6.1 writes without a body moves the peer from `404 handler_not_found`, which is
//! true, to `501 no_handler_body`, which says a handler exists and is broken. Shipping a
//! function that does that would be shipping a trap.
//!
//! **What that costs, stated plainly, and it is a bigger bill than CONTENT's.** The
//! recorder works: a composed peer accumulates a real, correct, content-addressed audit
//! chain at `system/history/head/*`. Nothing can read it over the wire, because every
//! §4.3 read path is an operation on the handler that cannot exist. `validate-peer`'s
//! `history` category reaches transitions ONLY through `system/history:query`, so 23 of
//! its 34 checks fail on a peer whose write face is working perfectly. **A category
//! score is not a statement about the extension**; the instrument that speaks to the
//! emit face on this peer is `gates/history-emit`, which is ours, and the composition's
//! conformance report says which number came from which.

pub mod handler;
pub mod patterns;
pub mod sdk;
pub mod types;

/// **NOT `pub`.** This one keyword's absence is the boundary. See `internal/mod.rs`.
mod internal;

use std::sync::{Arc, Weak};

use entity_core_protocol::peer::store::{Store, TreeChangeEvent};
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

/// What [`install_history_types`] wrote, so a caller can assert on it.
#[derive(Clone, Debug)]
pub struct HistoryTypeInstallation {
    pub type_paths: Vec<String>,
}

/// Publish HISTORY's six `system/type/*` entities into a peer's tree.
///
/// **Deliberately a different name from the other ports' `install_history`, not a
/// narrower version of it.** A caller must not be able to write one call that means
/// "installed" on two peers and "partly installed" on a third — the same rule
/// `../content`'s `install_content_types` was named under, and the reason
/// `[sdk_surface]` files both as substrate-conditional rather than as drift.
pub fn install_history_types(store: &Store, local_peer: &str) -> HistoryTypeInstallation {
    HistoryTypeInstallation {
        type_paths: publish_history_types(store, local_peer),
    }
}

/// What [`install_history_recorder`] registered, and the two facts a reader of the audit
/// trail needs before trusting it.
#[derive(Clone)]
pub struct HistoryRecorderInstallation {
    pub recorder: Arc<HistoryRecorder>,

    /// Whether §2.1's "handler grant" — the autonomous case's `capability` value — has a
    /// referent on this peer.
    ///
    /// **`false` here and `true` on the other two ports**, which is a distinction the
    /// other two did not have to make. They read back the token their own
    /// `install_history` minted; `Peer` exposes `create` and `dispatch` and there is no
    /// handler to grant for anyway, so the host passes the local identity hash and
    /// `author == capability` on every transition. The oracle's
    /// `context_capability_present` checks only for non-zero and would pass on that.
    pub handler_grant_available: bool,
}

impl HistoryRecorderInstallation {
    /// `"unknown"` | `"yes"` | `"not-observed"` — OBSERVED, never declared.
    ///
    /// A method, not a field, and that is the point: the field it replaced was a
    /// hardcoded `false` that said "measured". See `HistoryRecorder::context_observed`.
    pub fn context_available(&self) -> &'static str {
        self.recorder.context_observed()
    }
}

/// Install the §5.1 recorder as a position-4 emit consumer.
///
/// # Why this takes `&Arc<Peer>` and holds a `Weak`
///
/// `Store::register_tree_consumer` wants `Fn(&TreeChangeEvent) + Send + Sync + 'static`.
/// The store lives inside the peer, so a closure capturing `Arc<Peer>` would be owned by
/// that peer's own store — a reference cycle, and the peer would never drop. It would
/// never be *noticed* either, because a composed host lives for the process's lifetime;
/// which is exactly the kind of leak that ships. So the closure holds a `Weak` and
/// upgrades per event.
///
/// # Ordering is the composition's, and this function cannot enforce it
///
/// SYSTEM-COMPOSITION §2.2 puts history at position 4, after clock (2, 3) and before
/// compute (5) and subscription (8). The peer's consumer list is a `Vec` and
/// `register_tree_consumer` pushes — there is no position argument and nothing that
/// could check one. With HISTORY as the only consumer, position 4 is satisfied by having
/// nowhere else to be, and saying so is the point: the first composition that could
/// actually demonstrate the ordering is CONTENT + CLOCK + HISTORY.
///
/// # Call it LAST
///
/// After [`install_history_types`], not before. Otherwise the recorder observes its own
/// installation and the audit log opens with six type-entity writes nobody performed.
/// The other two ports enforce this inside a single `install_history`; here the two
/// faces install through two calls, so the ordering is the caller's to get right and the
/// composition's `host.rs` is where it is written down.
pub fn install_history_recorder(
    peer: &Arc<Peer>,
    identity: RecorderIdentity,
) -> HistoryRecorderInstallation {
    let handler_grant_available = false;
    let recorder = Arc::new(HistoryRecorder::new(identity));

    let weak: Weak<Peer> = Arc::downgrade(peer);
    let consumer = recorder.clone();
    peer.store.register_tree_consumer(move |ev: &TreeChangeEvent| {
        // A dropped peer means the process is tearing down; there is nothing to record
        // into and nothing to report. Silent by construction rather than by `unwrap`.
        let Some(peer) = weak.upgrade() else { return };
        consumer.on_tree_change(&peer.store, ev);
    });

    HistoryRecorderInstallation {
        recorder,
        handler_grant_available,
    }
}
