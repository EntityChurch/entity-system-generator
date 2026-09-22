//! §5.1 `emit_entity` — the transition recorder. **MODULE-PRIVATE** (see `mod.rs`).
//!
//! This is the emit-consumer body, and on this peer it is the half of the extension
//! that actually runs in production. The handler face cannot be installed; this one
//! can, and `languages/rust/gates/host-seam` arm G measured the property it needs:
//! **the peer's consumer seam is re-entrant.** `Store::fire` holds `consumers.read()`
//! across the callback, a `bind` from inside takes `inner.write()` and then re-enters
//! `fire`, and the arm ran that shape behind a 5-second timeout because the failure it
//! was looking for is a deadlock rather than a wrong answer. It returned, the head
//! pointer landed, and the head write's own event came back to the guard exactly once.
//!
//! That measurement is why the recorder is a plain consumer here instead of a queue
//! drained by a second thread. Reading `store.rs` would have suggested the same answer
//! and would not have been evidence for it (D13: source reads decide what to build,
//! never what is true).

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::value::{Key, Value};

use crate::patterns::{
    canonicalize_pattern, compare_specificity, pattern_matches, pattern_specificity,
};
use crate::types::{
    from_core_event_type, CONFIG, CONFIG_PREFIX, DEFAULT_EVENTS, HEAD_PREFIX, TRANSITION,
};

/// Where a transition's execution-context values came from.
///
/// **`provenance` is OURS, not §2.1's**, and it never enters the transition entity:
/// adding a field to a spec-declared type would move its content hash away from every
/// other implementation's, which is the silent cross-impl break this ecosystem keeps
/// paying for. It rides on [`RecordedTransition`] instead.
///
/// **A `&'static str` and not an enum, and the rejected enum is worth recording.** The
/// Rust reflex is `enum Provenance { Context, AutonomousFallback }` — two values, wrong
/// ones unrepresentable, exhaustive `match`. It is better Rust and it was not written,
/// because it is a public name in one port and not in the other two, which is precisely
/// the class `tools/sdk-parity.py` exists to refuse (D16). The gate would have caught it
/// as an undeclared name; the point of the gate is that the decision gets made instead
/// of arriving. `substrate` would have been a lie — nothing about this substrate forces
/// an enum — so the honest options were `drift` or parity, and parity is cheap here.
pub const PROVENANCE_CONTEXT: &str = "context";

/// The value on every write on every peer measured so far. Named for what it is rather
/// than for something reassuring: see `EXTENSION.toml [substrate.execution_context]`.
pub const PROVENANCE_AUTONOMOUS_FALLBACK: &str = "autonomous-fallback";

/// The §2.1 execution-context values a transition needs, and where they came from.
#[derive(Clone, Debug)]
pub struct TransitionContext {
    pub author: Vec<u8>,
    pub capability: Vec<u8>,
    pub caller_capability: Option<Vec<u8>>,
    pub handler_pattern: String,
    pub operation: String,
    pub chain_id: Option<String>,
    pub parent_chain_id: Option<String>,
    pub provenance: &'static str,
}

/// What the recorder captures at registration time, because the event does not carry it.
#[derive(Clone, Debug)]
pub struct RecorderIdentity {
    /// §2.1: "For autonomous operations (no external request), the local peer's
    /// identity hash."
    pub local_identity_hash: Vec<u8>,
    /// §2.1: "For autonomous operations, the handler grant."
    ///
    /// **On this peer there is no handler grant, because there is no handler.** The
    /// other two ports read back the token their own `install_history` minted at
    /// `system/capability/grants/system/history`; here `Peer` exposes `create` and
    /// `dispatch` and nothing else, so there is no mint and nothing to read. The host
    /// supplies the local identity hash and the composition declares that it did — see
    /// `EXTENSION.toml [substrate.handler_grant]`. It is a weaker fabrication than the
    /// other two ports', not the same one.
    pub handler_grant_hash: Vec<u8>,
    pub local_peer: String,
}

/// One recorded transition, as reported back to the caller. Not a spec entity.
#[derive(Clone, Debug)]
pub struct RecordedTransition {
    pub path: String,
    pub event: &'static str,
    pub transition_hash: Vec<u8>,
    pub head_path: String,
    pub provenance: &'static str,
}

/// A parsed `system/history/config` entity plus the pattern it was stored with.
#[derive(Clone, Debug)]
pub struct HistoryConfig {
    pub pattern: String,
    pub canonical_pattern: String,
    pub enabled: bool,
    /// §2.2 v1.10, ALREADY CANONICALIZED — the raw spelling is not kept, because the only
    /// consumer is `pattern_matches` and §2.2 says these use the same core §5.4 syntax as
    /// `pattern`. Canonicalizing at parse time also means the bare-`*` rule is applied by
    /// the one function that knows it (`canonicalize_pattern`).
    pub canonical_pattern_exclude: Vec<String>,
    pub events: Vec<String>,
    pub max_depth: Option<u64>,
    pub config_path: String,
}

/// What a config lookup considered, so a caller can tell "no config matched" from
/// "every config was unreadable".
#[derive(Clone, Debug)]
pub struct ConfigLookup {
    pub config: Option<HistoryConfig>,
    pub considered: usize,
    pub skipped: usize,
}

/// §3.2 `is_local_history_path` — the self-guard, transcribed.
///
/// Two properties are load-bearing and both are easy to get wrong in the direction that
/// still passes a naive test:
///
/// 1. **It guards `system/history/head`, NOT `system/history/`.** §3.2: config paths
///    "are handler-written via explicit EXECUTE and do not create recursion risk — they
///    SHOULD be recorded as normal transitions for audit purposes." Guarding the whole
///    namespace would silently drop config-change auditing and nothing would fail.
/// 2. **It is LOCAL-ONLY.** A remote peer's `system/history/...` arriving via sync is
///    ordinary tracked content; the head pointer it produces lands at
///    `/{local}/system/history/head/{remote}/...` and is excluded by this same check.
pub fn is_local_history_path(path: &str, local_peer: &str) -> bool {
    let prefix = format!("/{local_peer}/");
    match path.strip_prefix(&prefix) {
        None => false, // remote namespace — no recursion risk (§3.2)
        Some(rest) => rest.starts_with(HEAD_PREFIX),
    }
}

fn parse_config(path: &str, ent: &Entity, local_peer: &str) -> Option<HistoryConfig> {
    if ent.typ != CONFIG {
        return None;
    }
    let pattern = ent.text_field("pattern")?.to_string();
    // §2.2 types `enabled` as a required `primitive/bool`. A config that does not carry
    // one is malformed and is SKIPPED rather than defaulted — defaulting to `true` would
    // turn an unreadable config into an enabled one, which is the wrong direction to
    // fail in for an audit switch.
    let enabled = match ent.field("enabled") {
        Some(Value::Bool(b)) => *b,
        _ => return None,
    };
    // §2.2 v1.10. An EMPTY list stays empty (no exclusions), unlike `events` below where
    // empty falls back to the default set — `events` has a spec-stated default, and this
    // field's absent-value is "no exclusions", which an empty list already says.
    let canonical_pattern_exclude = match ent.field("pattern_exclude") {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(|v| match v {
                Value::Text(t) => Some(canonicalize_pattern(t, local_peer)),
                _ => None,
            })
            .collect(),
        _ => Vec::new(),
    };
    let events = match ent.field("events") {
        Some(Value::Array(items)) if !items.is_empty() => items
            .iter()
            .filter_map(|v| match v {
                Value::Text(t) => Some(t.clone()),
                _ => None,
            })
            .collect(),
        _ => DEFAULT_EVENTS.iter().map(|s| s.to_string()).collect(),
    };
    Some(HistoryConfig {
        canonical_pattern: canonicalize_pattern(&pattern, local_peer),
        pattern,
        enabled,
        canonical_pattern_exclude,
        events,
        max_depth: ent.uint_field("max_depth"),
        config_path: path.to_string(),
    })
}

/// §6.2 `find_history_config`, with v1.7's three-key ordering.
///
/// Returns the most specific MATCHING config, enabled or not. **The `enabled` check
/// belongs to the caller** — §5.1 tests `config is null or not config.data.enabled`
/// separately, and folding it in here would change which config wins: a specific
/// `enabled: false` must SHADOW a general `enabled: true`, or "turn history off for this
/// subtree" cannot be expressed at all. That is not stated in §6.2 and it is the only
/// reading under which the `enabled` field is useful, so it is recorded in
/// `EXTENSION.toml [assumptions]`.
pub fn find_history_config(store: &Store, path: &str, local_peer: &str) -> ConfigLookup {
    let base = format!("/{local_peer}/{CONFIG_PREFIX}/");
    let mut best: Option<HistoryConfig> = None;
    let mut considered = 0usize;
    let mut skipped = 0usize;

    for row in store.listing(&base) {
        if row.hash.is_none() {
            continue;
        }
        let config_path = format!("{base}{}", row.seg);
        let Some(ent) = store.get_at(&config_path) else {
            continue;
        };
        let Some(parsed) = parse_config(&config_path, &ent, local_peer) else {
            // A malformed config is skipped, not fatal: §6.2 iterates configs to find a
            // match and one unreadable entity must not leave every path un-audited. It
            // is also not silent — the caller gets the count.
            skipped += 1;
            continue;
        };
        considered += 1;
        if !pattern_matches(path, &parsed.canonical_pattern) {
            continue;
        }
        let wins = match &best {
            None => true,
            Some(b) => {
                compare_specificity(
                    &pattern_specificity(&parsed.canonical_pattern),
                    &pattern_specificity(&b.canonical_pattern),
                ) > 0
            }
        };
        if wins {
            best = Some(parsed);
        }
    }
    ConfigLookup {
        config: best,
        considered,
        skipped,
    }
}

/// The four fields a core tree-change event carries on this peer.
///
/// Taken apart rather than passed as the peer's `TreeChangeEvent`, for the reason
/// `sdk.rs`'s `build_context` is shaped the way it is: the per-target difference is
/// which pieces can ever be non-null, and that belongs at the boundary rather than
/// threaded through the recorder. It also lets `tests/recorder.rs` drive this without
/// constructing a peer event.
#[derive(Clone, Debug)]
pub struct TreeChange<'a> {
    pub event_type: &'a str,
    pub path: &'a str,
    pub new_hash: Option<&'a [u8]>,
    pub previous_hash: Option<&'a [u8]>,
}

/// §5.1's transition build and head advance, plus §3.3's prune.
///
/// `None` when the write is not recorded, which is a normal outcome and not an error:
/// unconfigured paths, disabled configs, unlisted event types and the §3.2 self-guard
/// all land there. History is opt-in (§2.2).
pub fn record_transition(
    store: &Store,
    identity: &RecorderIdentity,
    ev: &TreeChange<'_>,
    ctx: &TransitionContext,
    now_ms: u64,
) -> Option<RecordedTransition> {
    // §3.2 self-guard FIRST — before the config lookup, because the lookup LISTS the
    // tree and the guard is what stops this consumer re-entering on its own head write.
    // On this peer that re-entry is real and was measured (host-seam arm G), so the
    // ordering here is not defensive style.
    if is_local_history_path(ev.path, &identity.local_peer) {
        return None;
    }

    // An event vocabulary we do not recognise is never guessed at (`types.rs`).
    let event = from_core_event_type(ev.event_type)?;

    let config = find_history_config(store, ev.path, &identity.local_peer).config?;
    if !config.enabled {
        // §2.2: "If history is not configured for a path, no transitions are recorded."
        return None;
    }
    // §2.2 v1.10 exclusions, and the ORDER is the MUST (HIST-R16), not the matching.
    // AFTER selection: checked against the SELECTED config only. An excluded path does
    // NOT fall through to a less specific configuration — "an exclusion is a decision,
    // not a failure to match." Folding this into `find_history_config` as a non-match is
    // the other conformant-looking reading, and the two differ on exactly the paths two
    // configs cover. BEFORE the event filter: excluded for every event type.
    if config
        .canonical_pattern_exclude
        .iter()
        .any(|excl| pattern_matches(ev.path, excl))
    {
        return None;
    }

    if !config.events.iter().any(|e| e == event) {
        return None; // §5.1: "event type not configured"
    }

    let head_path = format!("/{}/{}{}", identity.local_peer, HEAD_PREFIX, ev.path);
    let previous_transition = store.hash_at(&head_path);

    // §2.1 field order follows the spec's table so this diffs against it line by line.
    // Absent optional fields are simply not pushed — the §1.3 absent-key rule the
    // `optional: true` specs in `types.rs` declare.
    let mut pairs: Vec<(Key, Value)> = Vec::with_capacity(14);
    let mut put = |k: &str, v: Value| pairs.push((Key::Text(k.to_string()), v));

    put("path", Value::Text(ev.path.to_string()));
    put("event", Value::Text(event.to_string()));
    if let Some(h) = ev.new_hash {
        put("hash", Value::Bytes(h.to_vec()));
    }
    if let Some(h) = ev.previous_hash {
        put("previous_hash", Value::Bytes(h.to_vec()));
    }
    put("author", Value::Bytes(ctx.author.clone()));
    put("capability", Value::Bytes(ctx.capability.clone()));
    // §5.1: recorded "only when it differs from capability". Compared BY VALUE — under
    // the fallback the same bytes arrive twice, and a comparison that was not by value
    // would emit a redundant field on every write.
    if let Some(cc) = &ctx.caller_capability {
        if cc != &ctx.capability {
            put("caller_capability", Value::Bytes(cc.clone()));
        }
    }
    put("handler", Value::Text(ctx.handler_pattern.clone()));
    put("operation", Value::Text(ctx.operation.clone()));
    put("timestamp", Value::UInt(now_ms));
    // `clock` is omitted: §2.1 says "Absent when the clock extension is not installed",
    // and CLOCK is not in any composition this repo has built.
    if let Some(c) = &ctx.chain_id {
        put("chain_id", Value::Text(c.clone()));
    }
    if let Some(c) = &ctx.parent_chain_id {
        put("parent_chain_id", Value::Text(c.clone()));
    }
    if let Some(p) = &previous_transition {
        put("previous", Value::Bytes(p.clone()));
    }

    let transition = Entity::make(TRANSITION, Value::Map(pairs));

    // §3.1: "All transition entities are in the content store. Only the head pointer is
    // in the tree." `Store::bind` does both — it inserts the entity into `content` and
    // binds the path to its hash — so `hash_at(head_path)` IS "hash of latest transition
    // entity" per §3.1, in one call.
    store.bind(&head_path, &transition);

    if let Some(depth) = config.max_depth {
        prune_history(store, &head_path, depth);
    }

    Some(RecordedTransition {
        path: ev.path.to_string(),
        event,
        transition_hash: transition.hash.clone(),
        head_path,
        provenance: ctx.provenance,
    })
}

/// §3.3 `prune_history`. **This severs nothing, and the comment is the deliverable.**
///
/// §3.3's algorithm walks to the `max_depth`-th transition and then says: "sever the
/// chain — the old transition keeps its previous field (immutable in content store),
/// but it's no longer reachable from the head."
///
/// A content-addressed entity cannot be edited, so "severing" means writing a NEW
/// transition identical to the last-kept one except with `previous` absent — which
/// changes its content hash, which changes the hash the transition before it points at,
/// which cascades all the way to the head. Rewriting the chain is the only way to
/// truncate it, and rewriting an audit chain is the opposite of what an audit chain is
/// for.
///
/// So this walks and reports. Pruning is a SHOULD (§9.1), the transitions beyond the
/// depth remain reachable, and the honest statement is that we do not implement it
/// rather than that we do. Routed to arch.
pub fn prune_history(store: &Store, head_path: &str, max_depth: u64) -> (u64, Option<Vec<u8>>) {
    let Some(head) = store.hash_at(head_path) else {
        return (0, None);
    };
    let mut current = Some(head);
    let mut count = 0u64;
    while count < max_depth {
        let Some(h) = current.clone() else { break };
        let Some(ent) = store.get_by_hash(&h) else {
            break;
        };
        current = ent.bytes_field("previous").map(|b| b.to_vec());
        count += 1;
    }
    (count, current)
}
