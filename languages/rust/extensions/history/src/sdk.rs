//! HISTORY — the SDK face, and the **emit-consumer face**.
//!
//! The emit consumer is why this extension was built second, and on this peer it is the
//! only face that both installs *and* does work. `DESIGN-THE-SDK-LAYER` §1 named four
//! faces; CONTENT exercised three and none of them ran here. This one runs.
//!
//! Everything interesting about it is about the two things the peer does not give us:
//! the execution context (see [`build_context`]) and read events (see `EXTENSION.toml
//! [substrate.accessed_event]`).

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::{ExecContext, Store, TreeChangeEvent};
use entity_core_protocol::value::{Key, Value};

use crate::internal::recorder::{
    find_history_config, is_local_history_path, record_transition, ConfigLookup, RecordedTransition,
    RecorderIdentity, TransitionContext, TreeChange, PROVENANCE_AUTONOMOUS_FALLBACK,
    PROVENANCE_CONTEXT,
};
use crate::types::{CONFIG, CONFIG_PREFIX};

/// Build the §2.1 context from whatever the tree-change event carried.
///
/// # On this peer it carried nothing, and it cannot
///
/// `TreeChangeEvent` is `{event_type, path, new_hash, previous_hash}` — four fields,
/// `store.rs:34-39`, no context field to be absent. `python`'s event is the same four.
/// `typescript` declares an `EmitContext` with almost exactly SYSTEM-COMPOSITION §1.4's
/// inventory and **constructs it at zero sites**. So across three peers the fallback is
/// not a fallback: it is the only path, and the constant is named
/// `PROVENANCE_AUTONOMOUS_FALLBACK` rather than something reassuring for that reason.
///
/// §2.1 defines the autonomous-case values exactly:
///
/// - `author` — "For autonomous operations (no external request), the local peer's
///   identity hash."
/// - `capability` — "For autonomous operations, the handler grant."
///
/// A tree-change event with no execution context is, from the recorder's vantage,
/// indistinguishable from an autonomous write, so those are the values recorded. **That
/// is a reading of the spec and it is also wrong about the world**: a `system/tree:put`
/// that arrived over the wire from a remote caller is not autonomous, and the transition
/// will say it was. §7.2 calls `capability` the answer to "under what authority?" — and
/// on these peers the answer is always "its own".
///
/// **And on THIS peer it is one step weaker still.** The second bullet has no referent:
/// there is no handler grant, because `Peer` exposes no mint and there is no handler to
/// grant for. The host passes the local identity hash for both, so `author` and
/// `capability` are the same bytes on every transition. The oracle's
/// `context_capability_present` only checks non-zero and passes on that — which is the
/// D13 distinction one level up, and is why the composition report says so out loud.
///
/// The signature takes the already-extracted pieces rather than the event, because the
/// per-target difference is *which of them can ever be non-`None`*, and that belongs at
/// the boundary rather than threaded through the recorder. On this port `carried` is
/// always `None` and the parameter exists so the day it is not, this function is where
/// the change lands.
pub fn build_context(
    identity: &RecorderIdentity,
    operation: &str,
    handler_pattern: &str,
    carried: Option<&CarriedContext>,
) -> TransitionContext {
    match carried {
        None => TransitionContext {
            author: identity.local_identity_hash.clone(),
            capability: identity.handler_grant_hash.clone(),
            caller_capability: None,
            handler_pattern: handler_pattern.to_string(),
            operation: operation.to_string(),
            chain_id: None,
            parent_chain_id: None,
            provenance: PROVENANCE_AUTONOMOUS_FALLBACK,
        },
        Some(c) => TransitionContext {
            author: c.author.clone(),
            // §2.1 `capability`: "For caller-authorized writes, the external caller's
            // capability... For handler-authorized writes, the handler's own grant."
            capability: c
                .handler_grant
                .clone()
                .or_else(|| c.caller_capability.clone())
                .unwrap_or_else(|| identity.handler_grant_hash.clone()),
            caller_capability: c.caller_capability.clone(),
            handler_pattern: c
                .handler_pattern
                .clone()
                .unwrap_or_else(|| handler_pattern.to_string()),
            operation: c.operation.clone().unwrap_or_else(|| operation.to_string()),
            chain_id: c.chain_id.clone(),
            parent_chain_id: c.parent_chain_id.clone(),
            provenance: PROVENANCE_CONTEXT,
        },
    }
}
/// The peer's `ExecContext` -> this extension's `CarriedContext`.
///
/// A BOUNDARY FUNCTION, and the same split the other two ports use: the recorder speaks
/// one vocabulary and each port converts into it exactly once. The peer's slot names are
/// SYSTEM-COMPOSITION §1.4's RESERVED names and are identical across all three peers;
/// what differs is the container, which is what a boundary is for.
///
/// **Returns `None` when the context carries no `author`, and that is not a shortcut.**
/// §6.8a: every slot is read from the wire rather than synthesized, so a slot the request
/// did not carry stays `None`. A context present but authorless cannot satisfy §2.1's
/// `author`, and defaulting it to the local identity here would silently produce the exact
/// forgery §9.1 exists to prevent -- while looking like provenance `"context"`. Falling
/// back explicitly keeps the honest label.
pub fn carried_from_exec(ctx: &ExecContext) -> Option<CarriedContext> {
    Some(CarriedContext {
        author: ctx.author.clone()?,
        caller_capability: ctx.caller_capability.clone(),
        handler_grant: ctx.handler_grant.clone(),
        handler_pattern: Some(ctx.handler_pattern.clone()),
        operation: Some(ctx.operation.clone()),
        chain_id: ctx.chain_id.clone(),
        parent_chain_id: ctx.parent_chain_id.clone(),
    })
}


/// SYSTEM-COMPOSITION §1.4's inventory, as the recorder would consume it.
///
/// **Nothing on this peer produces one.** It is declared so that [`build_context`] has a
/// non-degenerate branch to test — `tests/recorder.rs` constructs one by hand and
/// asserts the `context` provenance path — and so that the shape a peer would have to
/// deliver is written down in the routing packet's own vocabulary rather than in prose.
#[derive(Clone, Debug, Default)]
pub struct CarriedContext {
    pub author: Vec<u8>,
    pub caller_capability: Option<Vec<u8>>,
    pub handler_grant: Option<Vec<u8>>,
    pub handler_pattern: Option<String>,
    pub operation: Option<String>,
    pub chain_id: Option<String>,
    pub parent_chain_id: Option<String>,
}

/// Counters the composition and the tests read. Not part of §2.1.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RecorderStats {
    pub observed: u64,
    pub recorded: u64,
    pub skipped_self_guard: u64,
    pub skipped_unconfigured: u64,
    pub fallback_contexts: u64,
    /// Events whose carried context supplied an author. The counterpart of
    /// `fallback_contexts`; together they are the evidence behind `context_observed()`,
    /// counted rather than inferred so the composition can print the quantity beside the
    /// verdict.
    pub context_contexts: u64,
}

/// The §5.1 recorder, as a peer emit consumer.
///
/// # Why it takes the store per call instead of holding one
///
/// `register_tree_consumer` wants `Fn(&TreeChangeEvent) + Send + Sync + 'static`. The
/// store lives inside the `Peer`, and a closure that captured `Arc<Peer>` would be owned
/// by that peer's own store — a reference cycle, and the peer would never drop. So the
/// registration in [`install_history_recorder`] captures a `Weak<Peer>` and upgrades per
/// event, and this type stays store-agnostic: `tests/recorder.rs` drives it against a
/// bare `Store` with no peer at all.
///
/// **Registration ORDER is the composition's job, not this type's**, and that is
/// SYSTEM-COMPOSITION §2.2: history is position 4, after clock (2, 3) and before compute
/// (5) and subscription (8). This peer's consumer list is a `Vec` with no position
/// argument — `register_tree_consumer` pushes — so ordering is achieved by the order the
/// wiring program calls in, and there is nothing here that could enforce it.
pub struct HistoryRecorder {
    identity: RecorderIdentity,
    observed: AtomicU64,
    recorded: AtomicU64,
    skipped_self_guard: AtomicU64,
    skipped_unconfigured: AtomicU64,
    fallback_contexts: AtomicU64,
    context_contexts: AtomicU64,
    last: Mutex<Vec<RecordedTransition>>,
}

impl HistoryRecorder {
    pub fn new(identity: RecorderIdentity) -> HistoryRecorder {
        HistoryRecorder {
            identity,
            observed: AtomicU64::new(0),
            recorded: AtomicU64::new(0),
            skipped_self_guard: AtomicU64::new(0),
            skipped_unconfigured: AtomicU64::new(0),
            fallback_contexts: AtomicU64::new(0),
            context_contexts: AtomicU64::new(0),
            last: Mutex::new(Vec::new()),
        }
    }

    /// The consumer body. Called from inside `Store::fire`, which holds the consumer
    /// lock — see `internal/recorder.rs` for the arm that measured that re-entering it
    /// is safe on this peer.
    pub fn on_tree_change(&self, store: &Store, ev: &TreeChangeEvent) {
        self.observed.fetch_add(1, Ordering::SeqCst);

        if is_local_history_path(&ev.path, &self.identity.local_peer) {
            self.skipped_self_guard.fetch_add(1, Ordering::SeqCst);
            return;
        }

        // H8 LANDED 2026-09-07 (`dc5a458`). This was `None` UNCONDITIONALLY, with the
        // comment "`None` on this peer, always" -- because `TreeChangeEvent` had no
        // context slot, so every transition this recorder wrote took §2.1's autonomous
        // reading and attributed a remote caller's write to the local peer. Routed as H8;
        // the peer now carries it and §9.1's MUST on `author`/`capability` becomes
        // satisfiable here for the first time.
        let carried = ev.context.as_ref().and_then(carried_from_exec);
        let ctx = build_context(&self.identity, "put", "system/tree", carried.as_ref());
        if ctx.provenance == PROVENANCE_AUTONOMOUS_FALLBACK {
            self.fallback_contexts.fetch_add(1, Ordering::SeqCst);
        } else {
            self.context_contexts.fetch_add(1, Ordering::SeqCst);
        }

        let change = TreeChange {
            event_type: ev.event_type,
            path: &ev.path,
            new_hash: ev.new_hash.as_deref(),
            previous_hash: ev.previous_hash.as_deref(),
        };
        match record_transition(store, &self.identity, &change, &ctx, now_ms()) {
            None => {
                self.skipped_unconfigured.fetch_add(1, Ordering::SeqCst);
            }
            Some(rec) => {
                self.recorded.fetch_add(1, Ordering::SeqCst);
                if let Ok(mut last) = self.last.lock() {
                    last.push(rec);
                }
            }
        }
    }

    pub fn stats(&self) -> RecorderStats {
        RecorderStats {
            observed: self.observed.load(Ordering::SeqCst),
            recorded: self.recorded.load(Ordering::SeqCst),
            skipped_self_guard: self.skipped_self_guard.load(Ordering::SeqCst),
            skipped_unconfigured: self.skipped_unconfigured.load(Ordering::SeqCst),
            fallback_contexts: self.fallback_contexts.load(Ordering::SeqCst),
            context_contexts: self.context_contexts.load(Ordering::SeqCst),
        }
    }

    /// `"unknown"` | `"yes"` | `"not-observed"` — what this recorder has SEEN.
    ///
    /// **`"not-observed"`, never `"no"`, and the name is the whole correction.** "No" is
    /// a claim about the PEER; what this counter knows is a fact about THESE EVENTS. A
    /// composition driven only by autonomous writes — a bare `Store::bind`, the peer's own
    /// bootstrap — legitimately sees zero contexts on a peer that delivers them perfectly.
    ///
    /// This replaced a hardcoded `context_available: false` carrying the comment
    /// "measured": a claim about ANOTHER TEAM'S PEER, frozen in our source and asserted by
    /// our own tests. When keystone landed H8 the peers began delivering a context and all
    /// three ports went on reporting `false`. Nothing could have noticed — we wrote the
    /// value and we wrote the check. D13 already forbids the shape; it had been applied to
    /// every claim about a peer except the one we stored in our own struct.
    pub fn context_observed(&self) -> &'static str {
        if self.context_contexts.load(Ordering::SeqCst) > 0 {
            "yes"
        } else if self.observed.load(Ordering::SeqCst) > 0 {
            "not-observed"
        } else {
            "unknown"
        }
    }

    /// The transitions recorded so far, oldest first. Test and composition surface.
    pub fn recorded_transitions(&self) -> Vec<RecordedTransition> {
        self.last.lock().map(|v| v.clone()).unwrap_or_default()
    }
}

/// Wall-clock milliseconds since the epoch (§2.1 `timestamp`, §5.1 `system_clock_ms()`).
///
/// The other two ports read the peer's own clock (`peer.nowMs` / `peer.now_ms()`); this
/// one has none to read, so it reads the host's. That is a difference with no observable
/// consequence today — §2.1's `clock` field, which is the one that would carry a
/// *logical* time, is absent because CLOCK is not installed — and it is stated rather
/// than smoothed over, because the day CLOCK is composed the two are not the same source.
fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

// ── configuration (§6.1) ─────────────────────────────────────────────────────

/// Build a `system/history/config` entity (§2.2).
///
/// §6.1 is explicit that no handler operation is needed — "configuration uses the
/// standard tree `put`" — so this builds the entity and the caller binds it. Exposed
/// because a composition and a test both need to configure history, and hand-building
/// the map at each site is how two call sites end up with different `events` defaults.
///
/// `enabled` is written unconditionally, including when it is `false`. §2.2 types it as
/// a required `primitive/bool`, and a config that decoded as malformed would be SKIPPED
/// by the recorder's parser and would silently RE-ENABLE history for the path it was
/// written to turn off.
pub fn history_config(
    pattern: &str,
    enabled: bool,
    events: Option<&[&str]>,
    max_depth: Option<u64>,
) -> Entity {
    let mut pairs: Vec<(Key, Value)> = vec![
        (Key::Text("pattern".into()), Value::Text(pattern.to_string())),
        (Key::Text("enabled".into()), Value::Bool(enabled)),
    ];
    if let Some(evs) = events {
        pairs.push((
            Key::Text("events".into()),
            Value::Array(evs.iter().map(|e| Value::Text((*e).to_string())).collect()),
        ));
    }
    if let Some(d) = max_depth {
        pairs.push((Key::Text("max_depth".into()), Value::UInt(d)));
    }
    Entity::make(CONFIG, Value::Map(pairs))
}

/// The tree path a named config binds at (§6.1).
pub fn config_path(local_peer: &str, name: &str) -> String {
    format!("/{local_peer}/{CONFIG_PREFIX}/{name}")
}

/// Resolve which config governs a path (§6.2) — the public form of the recorder's own
/// lookup.
///
/// Exposed because it is the only way an operator can answer "is this path audited, and
/// by which rule" without writing to it and looking. On this peer it is also the only
/// route to that answer at all: the other two ports can ask over the wire through
/// `system/history:query`, and here there is no handler to ask.
pub fn resolve_config(store: &Store, path: &str, local_peer: &str) -> ConfigLookup {
    find_history_config(store, path, local_peer)
}
