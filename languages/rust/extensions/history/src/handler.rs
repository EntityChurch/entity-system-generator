//! HISTORY §4 — the system history handler. `query` (§4.3.1) and `rollback` (§4.3.2).
//!
//! # Installed through `Peer::register_handler` (keystone H1)
//!
//! This body was written and tested for a peer with nowhere to install it (`register_handler`
//! private, `E0624`), which made HISTORY on `rust` the sharpest case of D13's face amendment: the
//! recorder installed and ran, and the only route by which anything could READ what it wrote was
//! this handler. Keystone landed H1 for K-9; [`crate::install_history`] installs it, and the
//! [`Handler`] impl at the bottom of this file is the whole of the change. The body did not change.
//!
//! [`HandlerRequest`] stays ours: a third party cannot construct the peer's `HandlerContext`, so the
//! unit tests reach the body through this type.
//!
//! §4.2's dual check calls keystone's H9 `check_path_permission` — see
//! [`HistoryHandler::check_target_access`].

use entity_core_protocol::peer::capability;
use entity_core_protocol::peer::handler::{Handler, HandlerContext, HandlerResult, OperationSpec};
use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::{ExecContext, Store};
use entity_core_protocol::peer::wire;
use entity_core_protocol::value::{Key, Value};

use crate::types::{
    DEFAULT_QUERY_LIMIT, HEAD_PREFIX, HISTORY_PATTERN, QUERY_PARAMS, QUERY_RESULT, ROLLBACK_PARAMS,
    ROLLBACK_RESULT,
};

/// §4.1 / §9.3 manifest operations, in the mapped §3.7 form.
pub const OPERATIONS: [&str; 2] = ["query", "rollback"];

/// A walk bound that is NOT in the spec, and is here because its absence is a denial of
/// service on an audited path.
///
/// §2.3's `limit` defaults to 50 but is caller-supplied and unbounded above; a chain is
/// as long as the path has been written. §4.3.1's algorithm walks `while current_hash is
/// not null and len(transitions) < limit`, so a caller asking for `limit: 2^53` walks
/// the entire chain and materialises it.
///
/// Declared in `EXTENSION.toml [assumptions].max_walk` rather than silently applied: it
/// changes an observable answer — `has_more` goes true earlier than a naive reading —
/// and a cap nobody declared is exactly the kind of local decision this repo does not
/// get to make quietly.
pub const DEFAULT_MAX_WALK: u64 = 1000;

/// What the body reads from a request. Built from the peer's `HandlerContext` on the dispatch
/// path, and by hand in `tests/`.
pub struct HandlerRequest<'a> {
    /// The `system/protocol/execute` entity (§3.2).
    pub exec: &'a Entity,
    /// Registration-time capture. Nothing in `exec` routes back to the peer.
    pub store: &'a Store,
    /// The peer this handler is installed on, for path canonicalization (§2.3) and for
    /// the §4.2 permission frame.
    pub local_peer: &'a str,
    /// The caller's capability token, as the dispatcher would have resolved it.
    ///
    /// `None` models an in-process call with no token. §4.2 check 2 DENIES on it — see
    /// [`HistoryHandler::check_target_access`].
    pub caller_capability: Option<&'a Entity>,
    /// The §6.8a execution context of this dispatch, stamped on the rollback write so the recorder
    /// attributes it to the caller. `None` in a test models an autonomous write.
    pub context: Option<&'a ExecContext>,
}

/// A handler outcome: status, the result entity, and protocol entities to bundle. Mapped onto
/// the peer's [`HandlerResult`] one-for-one at the dispatch boundary; kept because the tests
/// assert on it.
#[derive(Clone, Debug)]
pub struct HistoryOutcome {
    pub status: u64,
    pub result: Entity,
    pub included: Vec<Entity>,
}

impl HistoryOutcome {
    fn ok(result: Entity) -> HistoryOutcome {
        HistoryOutcome {
            status: 200,
            result,
            included: vec![],
        }
    }

    fn ok_with(result: Entity, included: Vec<Entity>) -> HistoryOutcome {
        HistoryOutcome {
            status: 200,
            result,
            included,
        }
    }

    fn err(status: u64, code: &str, message: &str) -> HistoryOutcome {
        HistoryOutcome {
            status,
            result: wire::error_result(code, Some(message)),
            included: vec![],
        }
    }
}

/// The §4.1 handler.
pub struct HistoryHandler {
    max_walk: u64,
}

impl HistoryHandler {
    pub fn new() -> HistoryHandler {
        HistoryHandler {
            max_walk: DEFAULT_MAX_WALK,
        }
    }

    /// **A method, not a `HistoryHandlerOptions` struct.** `typescript` takes an
    /// options object and `[sdk_surface]` files `type:history_handler_options` as
    /// substrate-conditional to that port; `python` takes a keyword argument. This is
    /// the same configuration with no type to name, which is what that classification
    /// says.
    pub fn with_max_walk(max_walk: u64) -> HistoryHandler {
        HistoryHandler { max_walk }
    }

    pub fn handle_op(&self, op: &str, req: &HandlerRequest<'_>) -> HistoryOutcome {
        // §4.3.1/§4.3.2's EXECUTE examples both carry `resource: {targets: [...]}`, and
        // GUIDE-EXTENSION-DEVELOPMENT §4.1 makes a resource-less directly-callable op a
        // `400 path_required`. Same code, same authority and same caveat as CONTENT's:
        // `[error_surface].unresolved`, because no spec code set defines it. The second
        // extension inheriting it is the argument that it is a corpus fact.
        if resource_targets(req.exec).is_none() {
            return HistoryOutcome::err(
                400,
                "path_required",
                &format!(
                    "{HISTORY_PATTERN}:{op} requires a resource naming the handler path (§4.3)"
                ),
            );
        }

        match op {
            "query" => self.query(req),
            "rollback" => self.rollback(req),
            other => HistoryOutcome::err(501, "unsupported_operation", other),
        }
    }

    // ── §4.2 the dual check ──────────────────────────────────────────────────

    /// §4.2 `check_history_access` — the dual check. `None` on ALLOW, else the error.
    ///
    /// **Check 1 is already done and re-doing it would be wrong.** §4.2's first check is
    /// "can caller use the history handler?", which the dispatcher performs before it
    /// builds a context — a body runs only because `check_permission` returned ALLOW for
    /// this pattern and operation. Re-running it here would re-derive an answer we have
    /// and would deny an in-process caller that legitimately has no token.
    ///
    /// **Check 2 is the one that is ours**, and nothing else performs it: the target
    /// path lives in `params`, not in `resource`, so the dispatcher's resource scoping
    /// never sees it. §7.1 is explicit about why it matters — "This prevents using the
    /// history system to access data the caller couldn't otherwise read." A handler
    /// grant on `system/history` alone must not become a read primitive over the tree.
    ///
    /// # `check_path_permission` — keystone's H9, called
    ///
    /// §4.2 names core's `check_path_permission` (§6.3) for the second check. Until keystone
    /// landed H9 on this peer there was none, and this function synthesised an EXECUTE for
    /// `check_permission` — which also resolved no granter frame, a limit recorded in
    /// `[substrate.path_permission]`. The predicate is now the peer's own and the call is the one
    /// the other two ports make.
    pub fn check_target_access(
        &self,
        req: &HandlerRequest<'_>,
        op: &str,
        target_path: &str,
    ) -> Option<HistoryOutcome> {
        let target_operation = if op == "rollback" { "put" } else { "get" };

        let Some(token) = req.caller_capability else {
            // In-process dispatch with no caller capability. We DENY rather than allow:
            // §7.1's whole purpose is that history must not widen what a caller can
            // reach, and "no token" is not evidence of authority.
            return Some(HistoryOutcome::err(
                403,
                "capability_denied",
                &format!(
                    "{op} requires a capability covering {target_operation} on {target_path} (§4.2)"
                ),
            ));
        };

        // §4.2 passes `"system/tree"` as the handler pattern, NOT `"system/history"`. That is
        // the crux of the dual model: the caller must hold authority over the target path as a
        // TREE path, exactly as if they were reading or writing it directly.
        let allowed = capability::check_path_permission(
            target_operation,
            target_path,
            token,
            "system/tree",
            req.local_peer,
        );
        match allowed {
            true => None,
            false => Some(HistoryOutcome::err(
                403,
                "capability_denied",
                &format!(
                    "capability does not cover {target_operation} on {target_path} (§4.2 dual check)"
                ),
            )),
        }
    }

    /// The head-pointer path for a tracked path (§3.1).
    fn head_path(&self, local_peer: &str, canonical_target: &str) -> String {
        format!("/{local_peer}/{HEAD_PREFIX}{canonical_target}")
    }

    // ── §4.3.1 query ─────────────────────────────────────────────────────────

    fn query(&self, req: &HandlerRequest<'_>) -> HistoryOutcome {
        let Some(params) = req.exec.entity_field("params") else {
            return HistoryOutcome::err(
                400,
                "unexpected_params",
                "query expects a system/history/query-params entity",
            );
        };
        let Some(raw_path) = params.text_field("path") else {
            return HistoryOutcome::err(
                400,
                "unexpected_params",
                "query expects {path: system/tree/path} (§2.3)",
            );
        };

        // §2.3: "The `path` field ... accepts short-form input. The handler
        // canonicalizes it before processing."
        let path = capability::canonicalize(req.local_peer, raw_path);

        if let Some(denied) = self.check_target_access(req, "query", &path) {
            return denied;
        }

        let limit = params.uint_field("limit").unwrap_or(DEFAULT_QUERY_LIMIT);
        let before = params.uint_field("before");
        let since = params.bytes_field("since").map(|b| b.to_vec());
        let events: Option<Vec<String>> = match params.field("events") {
            Some(Value::Array(items)) => Some(
                items
                    .iter()
                    .filter_map(|v| match v {
                        Value::Text(t) => Some(t.clone()),
                        _ => None,
                    })
                    .collect(),
            ),
            _ => None,
        };

        let head_hash = req.store.hash_at(&self.head_path(req.local_peer, &path));
        let Some(head_hash) = head_hash else {
            // §4.3.1: no history → empty result, NOT a 404. The path may simply never
            // have been written, and "no history" is a fact rather than a failure.
            //
            // `has_more` is REQUIRED (§2.4, not optional) and is written as
            // present-and-false, which is what the oracle's `HasMore bool
            // \`cbor:"has_more"\`` (no `omitempty`) requires.
            return HistoryOutcome::ok(Entity::make(
                QUERY_RESULT,
                Value::Map(vec![
                    (Key::Text("path".into()), Value::Text(path.clone())),
                    (Key::Text("transitions".into()), Value::Array(vec![])),
                    (Key::Text("has_more".into()), Value::Bool(false)),
                ]),
            ));
        };

        let mut collected: Vec<Entity> = Vec::new();
        let mut current: Option<Vec<u8>> = Some(head_hash.clone());
        let mut walked = 0u64;

        while (collected.len() as u64) < limit && walked < self.max_walk {
            let Some(h) = current.clone() else { break };
            let Some(transition) = req.store.get_by_hash(&h) else {
                break; // §4.3.1: "if transition is null: break"
            };
            walked += 1;

            // §4.3.1's filter ORDER, transcribed. `since` BREAKS — it is an exclusive
            // lower bound on the walk. `before` and `events` CONTINUE — they skip an
            // entry and keep walking. Collapsing the three into one predicate changes
            // the result set.
            if since.as_deref() == Some(h.as_slice()) {
                break;
            }

            let previous = transition.bytes_field("previous").map(|b| b.to_vec());
            let ts = transition.uint_field("timestamp");

            if let (Some(b), Some(t)) = (before, ts) {
                if t >= b {
                    current = previous;
                    continue;
                }
            }
            if let Some(filter) = &events {
                let ev = transition.text_field("event").unwrap_or("");
                if !filter.iter().any(|e| e == ev) {
                    current = previous;
                    continue;
                }
            }

            collected.push(transition);
            current = previous;
        }

        let has_more = current.is_some();

        // `transitions` carries each transition's DATA MAP INLINE, not its hash.
        //
        // §2.4 types the field `array_of: {type_ref: "system/history/transition"}`,
        // which on its own admits both readings — a `system/hash` field elsewhere in the
        // same type is also a reference to an entity. **The oracle settles it**:
        // `HistoryQueryResultData` is `Transitions []TransitionData` and it decodes the
        // array elements straight into the field struct (`core/types/history.go`). A
        // hash array decodes as nothing there, and an array of `{type, data}` entity
        // maps decodes as a struct with every field zero — which would pass
        // `transition_recorded` (the array is non-empty) and fail
        // `transition_event_created` with an empty event string. The wrong reading fails
        // four checks down, not here.
        //
        // §4.3.1's `system/envelope` form is a SHOULD "for efficiency"; the plain result
        // is conformant. We send the plain form and still pass the entities as
        // `included`, so a caller resolving transitions by hash gets them without a
        // second round trip.
        let result = Entity::make(
            QUERY_RESULT,
            Value::Map(vec![
                (Key::Text("path".into()), Value::Text(path)),
                (Key::Text("head".into()), Value::Bytes(head_hash)),
                (
                    Key::Text("transitions".into()),
                    Value::Array(collected.iter().map(|t| t.data.clone()).collect()),
                ),
                (Key::Text("has_more".into()), Value::Bool(has_more)),
            ]),
        );
        HistoryOutcome::ok_with(result, collected)
    }

    // ── §4.3.2 rollback ──────────────────────────────────────────────────────

    fn rollback(&self, req: &HandlerRequest<'_>) -> HistoryOutcome {
        let Some(params) = req.exec.entity_field("params") else {
            return HistoryOutcome::err(
                400,
                "unexpected_params",
                "rollback expects a system/history/rollback-params entity",
            );
        };
        let (Some(raw_path), Some(target_hash)) = (
            params.text_field("path"),
            params.bytes_field("target_hash").map(|b| b.to_vec()),
        ) else {
            return HistoryOutcome::err(
                400,
                "unexpected_params",
                "rollback expects {path, target_hash} (§4.3.2)",
            );
        };

        let path = capability::canonicalize(req.local_peer, raw_path);

        if let Some(denied) = self.check_target_access(req, "rollback", &path) {
            return denied;
        }

        // §7.5 History Exfiltration Prevention — THE security check of this operation.
        // "This prevents using rollback to write arbitrary content to a path — you can
        // only restore entities that were previously at that path." Without it,
        // `rollback` is an unrestricted `put` that bypasses every type and validation
        // path a real put has.
        if !self.is_in_history(req, &path, &target_hash) {
            return HistoryOutcome::err(
                404,
                "not_in_history",
                "Target hash not found in history for this path",
            );
        }

        let Some(entity) = req.store.get_by_hash(&target_hash) else {
            // In history but no longer in the content store — GC'd per §3.3.
            // Distinguished from `not_in_history` on purpose: one says "you may not",
            // the other says "it is gone", and the caller's remedy differs.
            //
            // `500 storage_error`, NOT a 404 and NOT CONTENT's `blob_not_found`. A 404
            // says "not in history", which is false — we just proved it IS — and would
            // be indistinguishable from the branch above. `blob_not_found` is CONTENT's
            // owned code, and §8.3 makes HISTORY installable without CONTENT, so
            // borrowing it would emit a code whose defining spec is absent from the
            // peer. Core §3.3's 500 row enumerates `storage_error` as "a content-store
            // or tree bind/read failed", which is exactly this.
            return HistoryOutcome::err(
                500,
                "storage_error",
                "Target hash is in this path's history but the entity is no longer in the content store (§3.3 GC)",
            );
        };

        // §4.3.2: "Restore by rebinding the path to the old entity's content hash...
        // This goes through normal put, which will itself be recorded in history." So
        // this write fires the emit pathway and our own recorder observes it — the
        // rollback appears in the chain as an ordinary `updated`.
        //
        // §4.3.2: "the transition's `operation` field will reflect the rollback operation", and §2.1
        // records the remote caller as `author`. So the write carries THIS dispatch's execution context.
        // It did not in any of our three ports until 2026-09-12 (cross-port review): every rollback was
        // recorded as the peer's own `system/tree:put`, and the oracle's `rollback_new_transition`
        // checks only `event` and `hash`, so nothing could see it.
        req.store.bind_with_context(&path, &entity, req.context.cloned());

        HistoryOutcome::ok(Entity::make(
            ROLLBACK_RESULT,
            Value::Map(vec![
                (Key::Text("path".into()), Value::Text(path)),
                (Key::Text("restored".into()), Value::Bytes(target_hash)),
            ]),
        ))
    }

    /// §4.3.2 `is_in_history`, transcribed — including the part that is easy to drop.
    ///
    /// It matches on `hash` **OR** `previous_hash`. Dropping the second disjunct still
    /// passes a test that rolls back to a value the path once held, because that value
    /// is some transition's `hash`. It fails only for the FIRST entity ever at the path
    /// when you roll back past the write that replaced it — the oldest reachable state,
    /// which is the one an undo most wants.
    ///
    /// **UNCAPPED, deliberately** — unlike `query`. `max_walk` bounds a READ whose caller has
    /// `has_more` to continue with; applied here it turned a real rollback target deeper than
    /// `max_walk` transitions into a false `404 not_in_history`, which breaks §4.3.2's MUST. The chain
    /// is content-addressed and cannot cycle. (`[assumptions].max_walk`; 2026-09-12 cross-port review.)
    pub fn is_in_history(
        &self,
        req: &HandlerRequest<'_>,
        path: &str,
        target_hash: &[u8],
    ) -> bool {
        let mut current = req.store.hash_at(&self.head_path(req.local_peer, path));
        loop {
            let Some(h) = current.clone() else { return false };
            let Some(transition) = req.store.get_by_hash(&h) else {
                return false;
            };
            if transition.bytes_field("hash") == Some(target_hash)
                || transition.bytes_field("previous_hash") == Some(target_hash)
            {
                return true;
            }
            current = transition.bytes_field("previous").map(|b| b.to_vec());
        }
    }
}

/// H1 — the dispatch path. `route` calls this after §6.6 resolution and the dispatch-time
/// `check_permission` have allowed the request (§4.2's first check).
impl Handler for HistoryHandler {
    fn pattern(&self) -> &str {
        HISTORY_PATTERN
    }

    fn name(&self) -> &str {
        "history"
    }

    fn operations(&self) -> Vec<OperationSpec> {
        vec![
            OperationSpec::typed("query", QUERY_PARAMS, QUERY_RESULT),
            OperationSpec::typed("rollback", ROLLBACK_PARAMS, ROLLBACK_RESULT),
        ]
    }

    fn handle(&self, ctx: &HandlerContext<'_>) -> HandlerResult {
        let peer = ctx.peer();
        let context = ctx.exec_context();
        let req = HandlerRequest {
            exec: ctx.execute(),
            store: &peer.store,
            local_peer: &peer.local_peer,
            caller_capability: ctx.caller_capability(),
            context: Some(&context),
        };
        let outcome = self.handle_op(ctx.operation(), &req);
        HandlerResult {
            status: outcome.status,
            result: outcome.result,
            included: outcome.included,
        }
    }
}

impl Default for HistoryHandler {
    fn default() -> Self {
        HistoryHandler::new()
    }
}

// ── helpers ──────────────────────────────────────────────────────────────────

/// The EXECUTE's resource targets, or `None` when the field is absent (§3.2).
///
/// An EMPTY targets list is treated as absent rather than as a valid empty scope: core
/// §3.2 makes `targets` MUST-contain-at-least-one, so `{targets: []}` is malformed, and
/// `path_required` is the same answer a caller needs.
fn resource_targets(exec: &Entity) -> Option<Vec<String>> {
    let resource = exec.field("resource")?;
    let targets = entity_core_protocol::peer::model::map_get(resource, "targets")?;
    let items = match targets {
        Value::Array(items) if !items.is_empty() => items,
        _ => return None,
    };
    Some(
        items
            .iter()
            .filter_map(|v| match v {
                Value::Text(t) => Some(t.clone()),
                _ => None,
            })
            .collect(),
    )
}
