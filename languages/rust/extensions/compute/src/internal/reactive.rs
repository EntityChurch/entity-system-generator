//! COMPUTE §7 — reactive mode: the dependency index (§7.1), the re-evaluation trigger (§7.2) and
//! the cascade bound (§7.3), for the `rust` peer.
//!
//! **THE EMIT CONSUMER THAT WRITES BACK.** A tree write re-enters the evaluator and writes back,
//! and two substrate properties become load-bearing that §7.2 pins neither of (§9.4 leaves delivery
//! implementation-defined). On this peer both are decided by `Store`:
//!
//!  1. **Delivery is sync-inline.** `Store::bind_with_context` updates the tree under its write
//!     lock, RELEASES it, then calls every consumer before returning.
//!  2. **A write from inside a consumer re-enters the bus** — which is what makes a cascade a
//!     cascade, and why §7.3's bound is not decoration. **The re-entry takes the consumer list's
//!     `RwLock` for READ a second time on the same thread.** `std::sync::RwLock` documents that a
//!     recursive read may deadlock if a writer is queued; the only writer is
//!     `register_tree_consumer`, which runs before the peer serves. HISTORY's `host-seam` arm G
//!     measured ONE level of this; a cascade is sixteen. `tests/reactive.rs` drives a cascade to
//!     the bound behind a timeout, because the failure being looked for is a hang.
//!
//! **Held across nothing.** The dependency index is behind a `Mutex`, and every method copies what
//! it needs and drops the guard BEFORE evaluating or writing. A re-entrant `on_tree_change` on the
//! same thread would otherwise deadlock on our own lock, which no amount of peer correctness could
//! fix.
//!
//! **What is deliberately NOT here: a second evaluator.** Re-evaluation runs the same
//! [`ComputeEvaluator`] an explicit eval does, with a different authority and budget.
//!
//! # Where this port differs from `python`'s
//!
//!  - **No peer clock accessor.** `now_ms` is private to the peer's modules, so §7.2's expiry test
//!    reads `SystemTime` here. Same clock the peer uses; not the same function.
//!  - **No `check_path_permission`** (H9, normative, absent). The grant's per-path authority goes
//!    through `subgraph::path_permitted`.
//!  - **The engine holds a `Weak<Peer>`**, because the consumer closure lives in the peer's own
//!    store: a strong reference would be a cycle and the peer would never drop — the same reasoning
//!    as `../../../history/src/lib.rs`'s recorder.

use std::cell::Cell;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex, Weak};
use std::time::{SystemTime, UNIX_EPOCH};

use sha2::{Digest, Sha256};

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::{ExecContext, TreeChangeEvent};
use entity_core_protocol::peer::Peer;
use entity_core_protocol::value::{Key, Value};

use super::evaluator::canonicalize_path;
use super::subgraph::{audit_subgraph, path_permitted, AuditContext, SubgraphAudit};
use crate::sdk::{ComputeEvaluator, EvaluateOptions, EvaluatorLimits};
use crate::types::{
    CODE_CASCADE_LIMIT, CODE_INSTALLATION_GRANT_INVALID, COMPUTE_PATTERN, ERROR, PROCESSES_PREFIX,
    RECOMMENDED_MAX_CASCADE_DEPTH, RESULT, SUBGRAPH, is_compute_expression,
};

/// The re-entrancy backstop. Twice the cascade limit, so it can only fire where the spec's own
/// counter has failed to move — §7.2's error write passes the context UNCHANGED.
const REENTRY_LIMIT: u32 = (RECOMMENDED_MAX_CASCADE_DEPTH * 2) as u32;

const CAPABILITY_TOKEN: &str = "system/capability/token";

thread_local! {
    /// How deep inside `Store::bind` this THREAD currently is. Per thread and not per engine,
    /// because the quantity is the call stack, and a peer serves each connection on its own thread.
    static REENTRY: Cell<u32> = const { Cell::new(0) };
}

/// §7.1's dependency index — `path -> [(expression_uri, subgraph_path)]`. **EXACT-MATCH**: a write
/// at `.../cells/A1` does NOT wake a dependency on `.../cells`.
#[derive(Default)]
struct DependencyIndex {
    by_path: HashMap<String, Vec<(String, String)>>,
    by_subgraph: HashMap<String, Vec<String>>,
}

impl DependencyIndex {
    fn add(&mut self, path: &str, expression_uri: &str, subgraph_path: &str) {
        let entries = self.by_path.entry(path.to_string()).or_default();
        if !entries.iter().any(|(_, sp)| sp == subgraph_path) {
            entries.push((expression_uri.to_string(), subgraph_path.to_string()));
        }
        let paths = self.by_subgraph.entry(subgraph_path.to_string()).or_default();
        if !paths.iter().any(|p| p == path) {
            paths.push(path.to_string());
        }
    }

    fn remove_subgraph(&mut self, subgraph_path: &str) {
        let Some(paths) = self.by_subgraph.remove(subgraph_path) else {
            return;
        };
        for path in paths {
            if let Some(entries) = self.by_path.get_mut(&path) {
                entries.retain(|(_, sp)| sp != subgraph_path);
                if entries.is_empty() {
                    self.by_path.remove(&path);
                }
            }
        }
    }
}

/// The §7 engine: a tree-change consumer that owns the dependency index. One per peer; §3.3's
/// Phase 4 and §7.2's trigger are its two halves.
pub struct ReactiveEngine {
    peer: Weak<Peer>,
    limits: EvaluatorLimits,
    index: Mutex<DependencyIndex>,
}

impl ReactiveEngine {
    pub fn new(peer: &Arc<Peer>, limits: EvaluatorLimits) -> ReactiveEngine {
        ReactiveEngine {
            peer: Arc::downgrade(peer),
            limits,
            index: Mutex::new(DependencyIndex::default()),
        }
    }

    fn with_index<R>(&self, f: impl FnOnce(&mut DependencyIndex) -> R) -> R {
        let mut guard = self.index.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        f(&mut guard)
    }

    // ── §7.2 `on_tree_change` ────────────────────────────────────────────────────────

    /// §7.2 `on_tree_change`. The signature `Store::register_tree_consumer` calls.
    pub fn on_tree_change(&self, ev: &TreeChangeEvent) {
        let entries = self.with_index(|ix| ix.by_path.get(&ev.path).cloned().unwrap_or_default());
        if entries.is_empty() {
            return;
        }
        let Some(peer) = self.peer.upgrade() else {
            return; // the peer is tearing down; nothing to write into.
        };
        let context = ev.context.as_ref();

        if REENTRY.with(Cell::get) >= REENTRY_LIMIT {
            for (_, subgraph_path) in &entries {
                self.freeze(&peer, subgraph_path, CODE_CASCADE_LIMIT, context);
            }
            return;
        }

        let depth = cascade_depth(context);
        REENTRY.with(|r| r.set(r.get() + 1));
        for (expression_uri, subgraph_path) in &entries {
            let subgraph = match peer.store.get_at(subgraph_path) {
                Some(s) if s.typ == SUBGRAPH => s,
                // Uninstalled out from under us — clean the stale registration.
                _ => {
                    self.unregister(subgraph_path);
                    continue;
                }
            };
            if subgraph.text_field("status") == Some("frozen") {
                continue;
            }
            if depth >= RECOMMENDED_MAX_CASCADE_DEPTH {
                self.freeze(&peer, subgraph_path, CODE_CASCADE_LIMIT, context);
                continue;
            }
            self.re_evaluate(&peer, expression_uri, subgraph_path, &subgraph, context, depth);
        }
        REENTRY.with(|r| r.set(r.get() - 1));
    }

    // ── §3.3 Phase 4 / §7.1 ──────────────────────────────────────────────────────────

    /// Register every tree dependency of the expression. `audit.read_paths` comes from the SAME
    /// walk §3.3 Phase 1 ran. A re-install replaces, never accumulates.
    pub fn register(&self, subgraph_path: &str, expression_uri: &str, audit: &SubgraphAudit) {
        self.with_index(|ix| {
            ix.remove_subgraph(subgraph_path);
            for path in &audit.read_paths {
                ix.add(path, expression_uri, subgraph_path);
            }
        });
    }

    pub fn unregister(&self, subgraph_path: &str) {
        self.with_index(|ix| ix.remove_subgraph(subgraph_path));
    }

    /// §7.1's `rebuild_dependency_index` — scan `system/compute/processes/*` and re-register from
    /// the CURRENT expression at each root path.
    pub fn rebuild(&self) -> usize {
        let Some(peer) = self.peer.upgrade() else {
            return 0;
        };
        let prefix = canonicalize_path(PROCESSES_PREFIX, &peer.local_peer);
        let empty = Default::default();
        let audit_ctx = AuditContext {
            store: &peer.store,
            local_peer: &peer.local_peer,
            included: &empty,
            author: None,
        };
        let mut n = 0;
        // `listing` yields one level of SEGMENTS, not paths — the full path is rebuilt here.
        for row in peer.store.listing(&prefix) {
            let path = format!("{prefix}/{}", row.seg);
            let Some(subgraph) = peer.store.get_at(&path).filter(|s| s.typ == SUBGRAPH) else {
                continue;
            };
            let Some(root_path) = subgraph.text_field("root_expression_path") else {
                continue;
            };
            let Some(expression) = peer.store.get_at(root_path).filter(|e| is_compute_expression(&e.typ)) else {
                continue;
            };
            let Ok(audit) = audit_subgraph(&expression, root_path, &audit_ctx) else {
                continue;
            };
            self.register(&path, root_path, &audit);
            n += 1;
        }
        n
    }

    /// Diagnostics — the count of registered (path, subgraph) pairs.
    pub fn registered_dependencies(&self) -> usize {
        self.with_index(|ix| ix.by_path.values().map(Vec::len).sum())
    }

    pub fn watched_paths(&self) -> Vec<String> {
        self.with_index(|ix| {
            let mut v: Vec<String> = ix.by_path.keys().cloned().collect();
            v.sort();
            v
        })
    }

    /// §3.3's initial evaluation after installation, reachable from the handler so install and
    /// re-install are one path. Returns the result hash written, or `None` when nothing was.
    pub fn evaluate_now(&self, subgraph_path: &str, context: Option<&ExecContext>) -> Option<Vec<u8>> {
        let peer = self.peer.upgrade()?;
        let subgraph = peer.store.get_at(subgraph_path).filter(|s| s.typ == SUBGRAPH)?;
        let expression_uri = subgraph.text_field("root_expression_path")?.to_string();
        self.re_evaluate(&peer, &expression_uri, subgraph_path, &subgraph, context, cascade_depth(context))
    }

    // ── §7.2 `re_evaluate` ───────────────────────────────────────────────────────────

    /// Returns `None` on convergence and a hash otherwise — **the one assertion only the subject can
    /// satisfy** (AP-33): the store's own `changed` guard also suppresses an identical bind, so "no
    /// event fired" is not evidence that THIS check ran.
    fn re_evaluate(
        &self,
        peer: &Arc<Peer>,
        expression_uri: &str,
        subgraph_path: &str,
        subgraph: &Entity,
        context: Option<&ExecContext>,
        depth: u64,
    ) -> Option<Vec<u8>> {
        let result_path = subgraph.text_field("result_path")?.to_string();

        // §7.2 — the installation grant must still be available and unexpired. Revocation is the
        // dispatcher's (§5.2 step 4), not re-checked here.
        let grant = subgraph
            .bytes_field("installation_grant")
            .and_then(|h| peer.store.get_by_hash(h))
            .filter(is_capability);
        let grant = match grant {
            Some(g) if !is_expired(&g, now_ms()) => g,
            _ => {
                self.freeze(peer, subgraph_path, CODE_INSTALLATION_GRANT_INVALID, context);
                return None;
            }
        };

        let Some(expression) = peer.store.get_at(expression_uri) else {
            // The expression is gone: nothing left to wake.
            self.unregister(subgraph_path);
            return None;
        };

        let local_peer = peer.local_peer.clone();
        let limits = reactive_budget(&grant, self.limits);
        let sealed = authorized_hashes(subgraph);
        // §7.2's authorization source: the INSTALLATION GRANT, per path.
        let can_read = |path: &str| path_permitted("get", path, &grant, &local_peer);
        let can_write = |path: &str| path_permitted("put", path, &grant, &local_peer);

        let mut evaluator = ComputeEvaluator::new(&peer.store, &peer.local_peer, limits);
        let outcome = evaluator.evaluate_at(
            &expression,
            expression_uri,
            EvaluateOptions {
                authorized_data_hashes: Some(&sealed),
                can_read_path: Some(&can_read),
                can_write_path: Some(&can_write),
                ..Default::default()
            },
        );

        if let Some(error) = outcome.error {
            // §7.2's reactive error handling: the error entity IS the result, written with the
            // INCOMING context, and the subgraph stays ACTIVE.
            let result = error.to_entity();
            self.write(peer, &result_path, &result, context, None);
            return Some(result.hash);
        }

        let result = match (outcome.entity, outcome.value) {
            (Some(entity), _) => entity,
            (None, Some(value)) => result_entity(value, &expression),
            (None, None) => unreachable!("EvalOutcome carries exactly one of value/entity/error"),
        };

        // §7.2's convergence check. Same hash -> no write -> no event -> no cascade.
        if peer.store.hash_at(&result_path).as_deref() == Some(result.hash.as_slice()) {
            return None;
        }
        self.write(peer, &result_path, &result, context, Some(depth + 1));
        Some(result.hash)
    }

    /// §7.2's freeze: a code-only `compute/error` at the result path, `status: "frozen"` on the
    /// metadata. Recovery is re-installation.
    fn freeze(&self, peer: &Arc<Peer>, subgraph_path: &str, code: &str, context: Option<&ExecContext>) {
        let Some(subgraph) = peer.store.get_at(subgraph_path).filter(|s| s.typ == SUBGRAPH) else {
            return;
        };
        if let Some(result_path) = subgraph.text_field("result_path") {
            let error = Entity::make(
                ERROR,
                Value::Map(vec![(Key::Text("code".into()), Value::Text(code.to_string()))]),
            );
            self.write(peer, result_path, &error, context, None);
        }
        self.write(peer, subgraph_path, &with_status(&subgraph, "frozen"), context, None);
    }

    fn write(
        &self,
        peer: &Arc<Peer>,
        path: &str,
        entity: &Entity,
        context: Option<&ExecContext>,
        cascade_depth: Option<u64>,
    ) {
        peer.store.bind_with_context(path, entity, Some(exec_context(peer, context, cascade_depth)));
    }
}

/// The execution context our writes carry. `chain_id` INHERITED, never regenerated
/// (SYSTEM-COMPOSITION §3.4). `author` is the local peer (§7.2 evaluates as the local identity);
/// `caller_capability` is dropped; `handler_grant` is left empty for the cross-port reason
/// `[substrate.exec_context_handler_grant]` records.
fn exec_context(peer: &Peer, context: Option<&ExecContext>, cascade_depth: Option<u64>) -> ExecContext {
    ExecContext {
        request_id: context.map(|c| c.request_id.clone()).unwrap_or_default(),
        handler_pattern: COMPUTE_PATTERN.to_string(),
        operation: "eval".to_string(),
        author: Some(peer.identity.identity_hash.clone()),
        caller_capability: None,
        handler_grant: None,
        chain_id: context.and_then(|c| c.chain_id.clone()),
        parent_chain_id: context.and_then(|c| c.parent_chain_id.clone()),
        cascade_depth: cascade_depth.or_else(|| context.and_then(|c| c.cascade_depth)),
    }
}

/// SYSTEM-COMPOSITION §3.1 — an absent counter is depth 0, never "unknown".
fn cascade_depth(context: Option<&ExecContext>) -> u64 {
    context.and_then(|c| c.cascade_depth).unwrap_or(0)
}

fn is_capability(entity: &Entity) -> bool {
    entity.typ == CAPABILITY_TOKEN && matches!(entity.field("grants"), Some(Value::Array(_)))
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// §7.2's `is_expired` — `expires_at` against the clock.
fn is_expired(grant: &Entity, now: u64) -> bool {
    matches!(grant.uint_field("expires_at"), Some(expires_at) if expires_at < now)
}

/// §7.4 `reactive_budget` — bounded by the grant's `constraints["system/compute"]`, read from each
/// GRANT ENTRY (where core §5 carries it) and taking the tightest. Routed as A-21.
fn reactive_budget(grant: &Entity, limits: EvaluatorLimits) -> EvaluatorLimits {
    let mut out = limits;
    let Some(Value::Array(grants)) = grant.field("grants") else {
        return out;
    };
    for entry in grants {
        let Some(compute) = map_get(entry, "constraints").and_then(|c| map_get(c, COMPUTE_PATTERN)) else {
            continue;
        };
        if let Some(Value::UInt(ops)) = map_get(compute, "max_compute_operations") {
            out.max_operations = out.max_operations.min(*ops);
        }
        if let Some(Value::UInt(d)) = map_get(compute, "max_compute_depth") {
            out.max_depth = out.max_depth.min(*d);
        }
    }
    out
}

/// §4.2 Tier 2 — the sealed set, from the metadata's seventh field.
fn authorized_hashes(subgraph: &Entity) -> HashSet<Vec<u8>> {
    match subgraph.field("authorized_data_hashes") {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(|i| match i {
                Value::Bytes(b) => Some(b.clone()),
                _ => None,
            })
            .collect(),
        _ => HashSet::new(),
    }
}

/// §2.4 — a primitive result wrapped in a `compute/result` carrying the source expression's hash.
fn result_entity(value: Value, expression: &Entity) -> Entity {
    Entity::make(
        RESULT,
        Value::Map(vec![
            (Key::Text("value".into()), value),
            (Key::Text("expression".into()), Value::Bytes(expression.hash.clone())),
        ]),
    )
}

fn with_status(subgraph: &Entity, status: &str) -> Entity {
    let mut entries = match &subgraph.data {
        Value::Map(e) => e.clone(),
        _ => Vec::new(),
    };
    entries.retain(|(k, _)| !matches!(k, Key::Text(t) if t == "status"));
    entries.push((Key::Text("status".into()), Value::Text(status.to_string())));
    Entity::make(SUBGRAPH, Value::Map(entries))
}

fn map_get<'v>(map: &'v Value, key: &str) -> Option<&'v Value> {
    match map {
        Value::Map(entries) => entries.iter().find_map(|(k, v)| match k {
            Key::Text(t) if t == key => Some(v),
            _ => None,
        }),
        _ => None,
    }
}

const BASE32_ALPHABET: &[u8; 32] = b"abcdefghijklmnopqrstuvwxyz234567";

/// §3.3's `deterministic_id` — `base32_lower_no_padding(sha256(utf8_bytes(root_path)))`.
///
/// **SHA-256 regardless of the peer's hash format** (v7.68): a path-segment identifier, not a
/// content address. The encoder is hand-rolled because this target adds no crates; `typescript`
/// hand-rolls the same 5-bit walk and `python` uses its stdlib, and all three are pinned to
/// `entity-core-go`'s output vectors in their own suites.
pub fn deterministic_id(root_path: &str) -> String {
    let digest = Sha256::digest(root_path.as_bytes());
    let mut out = String::with_capacity(52);
    let mut buffer: u32 = 0;
    let mut bits = 0;
    for byte in digest.iter() {
        buffer = (buffer << 8) | u32::from(*byte);
        bits += 8;
        while bits >= 5 {
            bits -= 5;
            out.push(BASE32_ALPHABET[((buffer >> bits) & 0x1f) as usize] as char);
        }
    }
    if bits > 0 {
        out.push(BASE32_ALPHABET[((buffer << (5 - bits)) & 0x1f) as usize] as char);
    }
    out
}
