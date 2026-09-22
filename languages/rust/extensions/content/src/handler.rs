//! CONTENT §6 — the system content handler.
//!
//! Two operations, `get` (§6.2) and `ingest` (§6.3), both hash-addressed at the params
//! level and path-addressed at the cap-scope level (§6.4).
//!
//! # Installed through `Peer::register_handler` (keystone H1)
//!
//! Until keystone landed H1/H6 on this peer this body had nowhere to go: `register_handler` was
//! private (`E0624`), `Peer` had no handler container (`E0609`) and `Outcome` did not export
//! (`E0603`), so a bound manifest answered `501 no_handler_body`. [`crate::install_content`] installs
//! it now, and the [`Handler`] impl at the bottom of this file is the whole of the change.
//!
//! # Three context facts this handler is built around
//!
//! 1. **[`HandlerRequest`] is still ours.** A third party cannot construct the peer's
//!    `HandlerContext` (its fields are `pub(crate)`), so the unit tests reach the body through
//!    this type and the dispatch path builds one from the context.
//! 2. **The store is read off the context's peer**, not captured at registration.
//! 3. **The frame budget is the connection's configured one** (H6,
//!    `HandlerContext::frame_budget`). See [`FrameBudget`].

use entity_core_protocol::peer::capability;
use entity_core_protocol::peer::handler::{Handler, HandlerContext, HandlerResult, OperationSpec};
use entity_core_protocol::peer::model::{self, entity_of_cbor, Entity};
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::peer::wire;
use entity_core_protocol::value::{Key, Value};

use entity_core_protocol::peer::Peer;

use crate::types::{CONTENT_PATTERN, CONTENT_RESPONSE, GET_REQUEST, INGEST_REQUEST, INGEST_RESULT};

/// Envelope + response overhead reserved out of the frame budget before entities are
/// packed. The response entity carries two hash arrays (33 B each plus CBOR framing)
/// and the envelope adds its own map framing; 4 KiB is comfortably above both for any
/// batch a caller can request within one frame.
pub const FRAME_RESERVE_BYTES: usize = 4096;

/// One `system/hash` in a `found` or `missing` array: 33 bytes plus a 2-byte CBOR byte-string
/// header. Private: it is this port's accounting, not a cross-port constant.
const HASH_ENTRY_BYTES: usize = 35;

/// The bound in force on the connection this request arrived over.
///
/// **CONTENT Amendment 1 §6.2 forbids a hardcoded 16 MiB literal and requires consulting the
/// connection's configured budget at response-construction time.** Before keystone's H6 this peer
/// had no configuration and no accessor, so the only honest read was `wire::MAX_FRAME` — the exact
/// literal the amendment names, satisfied degenerately because it was also the only bound enforced.
/// H6 added `PeerConfig::max_frame_bytes`, `Peer::max_frame_bytes` and
/// `HandlerContext::frame_budget`, and the transport enforces the same number, so the MUST is now
/// satisfied in the form it states: the dispatch path reads [`HandlerContext::frame_budget`].
///
/// An enum with one variant on purpose. A bare `usize` would let a caller pass a number with no
/// statement about where it came from, and that provenance is what Amendment 1 is about.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FrameBudget {
    /// The bound the transport is enforcing, read from the peer or connection that enforces it.
    Enforced(usize),
}

impl FrameBudget {
    /// The peer's configured budget — what a connection on it enforces unless configured otherwise.
    pub fn from_peer(peer: &Peer) -> FrameBudget {
        FrameBudget::Enforced(peer.max_frame_bytes())
    }

    /// The budget for this request's connection. What the dispatch path uses.
    pub fn from_context(ctx: &HandlerContext<'_>) -> FrameBudget {
        FrameBudget::Enforced(ctx.frame_budget())
    }

    fn bytes(self) -> usize {
        match self {
            FrameBudget::Enforced(n) => n,
        }
    }
}

/// What the body reads from a request. Built from the peer's [`HandlerContext`] on the dispatch
/// path, and by hand in `tests/`.
pub struct HandlerRequest<'a> {
    /// The `system/protocol/execute` entity (§3.2).
    pub exec: &'a Entity,
    pub store: &'a Store,
    pub frame_budget: FrameBudget,
    /// The caller's verified capability, for §6.4 step 2's path-scope check. `None` models an
    /// in-process call with no token, which no wire request can make.
    pub caller_capability: Option<&'a Entity>,
    pub local_peer: &'a str,
}

/// A handler outcome: status, the result entity, and protocol entities to bundle. Mapped onto the
/// peer's [`HandlerResult`] one-for-one at the dispatch boundary; kept because the tests assert on it.
#[derive(Clone, Debug)]
pub struct ContentOutcome {
    pub status: u64,
    pub result: Entity,
    pub included: Vec<Entity>,
}

impl ContentOutcome {
    fn ok(result: Entity, included: Vec<Entity>) -> ContentOutcome {
        ContentOutcome {
            status: 200,
            result,
            included,
        }
    }

    fn err(status: u64, code: &str, message: &str) -> ContentOutcome {
        ContentOutcome {
            status,
            result: wire::error_result(code, Some(message)),
            included: vec![],
        }
    }
}

/// The §6.1 handler.
pub struct ContentHandler {
    /// The namespace prefix this instance serves (§6.4). `system/content` is the
    /// default-namespace value §6.2 pins for the §6.1 manifest registration.
    ///
    /// TOPOLOGY: cycle 1 runs single-trust-domain (§6.4.1) — `get` resolves any hash in
    /// the content store and `ingest` writes the store without binding into the tree.
    /// §6.4.1 makes that OPT-IN AND RESTRICTED ("MUST NOT be enabled as the default
    /// configuration"; multi-party deployments running it are "out-of-spec and
    /// security-defective"). Declared in `EXTENSION.toml [assumptions].topology`, not
    /// assumed here.
    pub namespace: String,
}

/// §6.1 manifest operations, in the mapped §3.7 form.
pub const OPERATIONS: [&str; 2] = ["get", "ingest"];

impl ContentHandler {
    pub fn new() -> ContentHandler {
        ContentHandler {
            namespace: CONTENT_PATTERN.to_string(),
        }
    }

    pub fn with_namespace(namespace: &str) -> ContentHandler {
        ContentHandler {
            namespace: namespace.to_string(),
        }
    }

    pub fn handle_op(&self, op: &str, req: &HandlerRequest<'_>) -> ContentOutcome {
        // §6.2 / §6.3 path-as-resource MUST, checked FIRST because it applies to both
        // ops identically. `400 path_required` — the status is pinned by
        // GUIDE-EXTENSION-DEVELOPMENT §171, and the oracle checks only the CODE, so a
        // peer answering 404 passes the gate and fails the spec. We answer 400.
        let targets = match resource_targets(req.exec) {
            Some(t) => t,
            None => {
                return ContentOutcome::err(
                    400,
                    "path_required",
                    &format!(
                        "{CONTENT_PATTERN}:{op} requires a resource naming the namespace path (§6.2/§6.3)"
                    ),
                )
            }
        };

        // §6.4 step 2 — path-scope check, handler-level. Dispatch already verified the
        // resource against the grant's `resources` scope (§6.4 step 1), so this is
        // defence-in-depth: it refuses a target outside the namespace this instance
        // serves even if a grant somehow covered it.
        //
        // `capability_denied`, NOT `forbidden`. v3.7 corrected §6.4's pseudocode:
        // `forbidden` was defined in no code set — it is ENTITY-CORE-PROTOCOL §3.3's
        // *fallback* for the 403 status, not a code — and §3.3's 403 row names
        // `capability_denied` as the default.
        for target in &targets {
            // §6.4 step 2 — the PATH-SCOPE check, "using `check_path_permission`" against the caller's
            // capability with handler pattern `system/content`. The prefix compare above is the namespace
            // this instance serves; it never read the capability, and until 2026-09-12 (cross-port review)
            // it was the whole of step 2 in all three ports. The peer's own predicate now runs as well.
            // With no caller capability — an in-process call no wire request can make — there is no grant
            // to check, as for COMPUTE's eval.
            if let Some(cap) = req.caller_capability {
                if !capability::check_path_permission(
                    op,
                    target,
                    cap,
                    CONTENT_PATTERN,
                    req.local_peer,
                ) {
                    return ContentOutcome::err(
                        403,
                        "capability_denied",
                        &format!("capability does not cover {op} on '{target}' (§6.4 path scope)"),
                    );
                }
            }
            if !within_namespace(target, &self.namespace) {
                return ContentOutcome::err(
                    403,
                    "capability_denied",
                    &format!(
                        "resource target '{target}' is outside namespace '{}' (§6.4)",
                        self.namespace
                    ),
                );
            }
        }

        match op {
            "get" => self.get(req),
            "ingest" => self.ingest(req),
            // §6.6(2): "This spec does not define a `system/content:delete`." Removal is
            // local GC, never a protocol op — so an unknown verb is 501, not 404.
            other => ContentOutcome::err(501, "unsupported_operation", other),
        }
    }

    // ── §6.2 get ─────────────────────────────────────────────────────────────

    fn get(&self, req: &HandlerRequest<'_>) -> ContentOutcome {
        // The `DispatchAuthority::mint()` that stood here until 2026-09-16 is gone with the
        // type. It was minted, dropped on the next line and read by nothing: `get` does not
        // reassemble — §6.2 returns the blob and chunk ENTITIES and the consumer assembles —
        // so the token's only effect was to make this line look like a boundary. §3.4's
        // wrapper is anchored to the dispatcher's `HandlerContext` now; see `sdk.rs`.
        let hashes = match req
            .exec
            .entity_field("params")
            .as_ref()
            .and_then(|p| p.field("hashes").cloned())
        {
            Some(Value::Array(items)) => items,
            _ => {
                return ContentOutcome::err(
                    400,
                    "unexpected_params",
                    "get expects {hashes: array_of system/hash} (§6.2)",
                )
            }
        };

        // EVERY requested hash lands in exactly one of `found` / `missing`, so the two lists together cost
        // one hash-list entry per request hash — charged here, up front. Until 2026-09-12 (cross-port review)
        // only a packed entity was charged (its bytes plus its `included` key); the `found` entry beside it and
        // every `missing` entry rode on the fixed reserve, which a request of ~120 hashes outgrows, so a
        // response packed close to the budget could exceed the frame §6.2 MUSTs it fit.
        let mut remaining = req
            .frame_budget
            .bytes()
            .saturating_sub(FRAME_RESERVE_BYTES)
            .saturating_sub(hashes.len() * HASH_ENTRY_BYTES);
        let mut found: Vec<Value> = Vec::new();
        let mut missing: Vec<Value> = Vec::new();
        let mut included: Vec<Entity> = Vec::new();
        // Once the budget is exhausted every REMAINING hash goes to `missing` in
        // request order — §6.2 says "as many as fit (in request order)", so a small
        // entity after a large one does NOT get packed. Order is the contract; the
        // requester retries with `missing` and makes deterministic progress.
        let mut exhausted = false;

        for raw in &hashes {
            let h = match raw {
                Value::Bytes(b) => b.clone(),
                _ => {
                    return ContentOutcome::err(
                        400,
                        "unexpected_params",
                        "hashes entries must be byte strings (§6.2)",
                    )
                }
            };
            let entity = match req.store.get_by_hash(&h) {
                Some(e) => e,
                None => {
                    missing.push(Value::Bytes(h));
                    continue;
                }
            };
            let cost = wire_size(&entity) + h.len();
            if exhausted || cost > remaining {
                exhausted = true;
                missing.push(Value::Bytes(h));
                continue;
            }
            remaining -= cost;
            included.push(entity);
            found.push(Value::Bytes(h));
        }

        // §6.2 Amendment 2: `pending` is OPTIONAL and SHOULD be populated only by an
        // implementation with sync-state visibility — an active subscription on the
        // namespace plus an inbox feeding the content store. This composition has
        // neither, so the field is OMITTED. Emitting an empty array would advertise a
        // capability we do not have; §6.2 says a receiver that omits it is telling the
        // caller to treat all `missing` as terminal, which is the truth here.
        let response = Entity::make(
            CONTENT_RESPONSE,
            Value::Map(vec![
                (Key::Text("found".into()), Value::Array(found)),
                (Key::Text("missing".into()), Value::Array(missing)),
            ]),
        );
        ContentOutcome::ok(response, included)
    }

    // ── §6.3 ingest ──────────────────────────────────────────────────────────

    fn ingest(&self, req: &HandlerRequest<'_>) -> ContentOutcome {
        let params = match req.exec.entity_field("params") {
            Some(p) => p,
            None => return ContentOutcome::err(400, "missing_input", "Specify envelope or entity"),
        };

        let envelope = params.field("envelope").cloned();
        let entity_val = params.field("entity").cloned();
        let has_envelope = matches!(envelope, Some(Value::Map(_)));
        let has_entity = matches!(entity_val, Some(Value::Map(_)));

        if has_envelope && has_entity {
            return ContentOutcome::err(
                400,
                "ambiguous_input",
                "Specify envelope or entity, not both",
            );
        }
        if !has_envelope && !has_entity {
            return ContentOutcome::err(400, "missing_input", "Specify envelope or entity");
        }

        // ── Entity mode: store a single entity. `root` is ABSENT from the result —
        // there is no envelope wrapper to pass through (§6.3), and the §11.1 MUST is
        // scoped to envelope mode with a non-null root.
        if has_entity {
            let entity = match entity_of_cbor(&entity_val.unwrap()) {
                Ok(e) => e,
                Err(e) => {
                    return ContentOutcome::err(400, "unexpected_params", &format!("entity: {e:?}"))
                }
            };
            req.store.put_entity(&entity);
            return ContentOutcome::ok(
                Entity::make(
                    INGEST_RESULT,
                    Value::Map(vec![
                        (
                            Key::Text("root_hash".into()),
                            Value::Bytes(entity.hash.clone()),
                        ),
                        (Key::Text("ingested_count".into()), Value::UInt(1)),
                    ]),
                ),
                vec![],
            );
        }

        // ── Envelope mode: store root + all included.
        //
        // `system/envelope` extends `core/envelope`, whose `root` is a REQUIRED
        // `core/entity`, so §6.3's `if envelope.root is not null` branch is unreachable
        // for a well-formed envelope and a missing root is a malformed request rather
        // than an empty-count success.
        let env = envelope.unwrap();
        let root_val = match model::map_get(&env, "root") {
            Some(v @ Value::Map(_)) => v.clone(),
            _ => {
                return ContentOutcome::err(
                    400,
                    "unexpected_params",
                    "envelope: missing required root (§3.1)",
                )
            }
        };
        let root = match entity_of_cbor(&root_val) {
            Ok(e) => e,
            Err(e) => {
                return ContentOutcome::err(
                    400,
                    "unexpected_params",
                    &format!("envelope.root: {e:?}"),
                )
            }
        };

        req.store.put_entity(&root);
        let mut count: u64 = 1;

        if let Some(Value::Map(entries)) = model::map_get(&env, "included") {
            for (key, value) in entries {
                if !matches!(value, Value::Map(_)) {
                    return ContentOutcome::err(
                        400,
                        "unexpected_params",
                        "envelope.included values must be entities",
                    );
                }
                let inner = match entity_of_cbor(value) {
                    Ok(e) => e,
                    Err(e) => {
                        return ContentOutcome::err(
                            400,
                            "unexpected_params",
                            &format!("envelope.included: {e:?}"),
                        )
                    }
                };
                // §6.3 hash-validation MUST: each included entity's content hash is
                // verified against its key in the included map. `entity_of_cbor`
                // already re-derives the hash from {type, data} and rejects a carried
                // mismatch (§1.8 validate-before-trust); this is the §3.1 KEY check,
                // which is a different assertion and the one §6.3 names.
                //
                // A non-`Bytes` key is a malformed envelope (core §3.1 requires major
                // type 2) and produces `hash_mismatch`, which is the same answer §6.3
                // asks for and the same answer the other two ports give.
                let key_bytes: &[u8] = match key {
                    Key::Bytes(b) => b.as_slice(),
                    _ => &[],
                };
                if key_bytes != inner.hash.as_slice() {
                    return ContentOutcome::err(
                        400,
                        "hash_mismatch",
                        "included entity hash does not match key",
                    );
                }
                req.store.put_entity(&inner);
                count += 1;
            }
        }

        // §11.1 MUST: `root` is included, inlined, in envelope mode. It lets a
        // continuation navigate `data.root.data.<field>` without dereferencing the
        // content store (§6.3.1).
        ContentOutcome::ok(
            Entity::make(
                INGEST_RESULT,
                Value::Map(vec![
                    (Key::Text("root".into()), root.to_cbor()),
                    (
                        Key::Text("root_hash".into()),
                        Value::Bytes(root.hash.clone()),
                    ),
                    (Key::Text("ingested_count".into()), Value::UInt(count)),
                ]),
            ),
            vec![],
        )
    }
}

impl Default for ContentHandler {
    fn default() -> Self {
        ContentHandler::new()
    }
}

// ── helpers ──────────────────────────────────────────────────────────────────

/// The EXECUTE's resource targets, or `None` when the field is absent (§3.2).
///
/// An EMPTY targets list is treated as absent rather than as a valid empty scope: core
/// §3.2 makes `targets` MUST-contain-at-least-one, so `{targets: []}` is malformed, and
/// answering `path_required` for it is the same answer a caller needs.
///
/// **Over the wire on a live peer this branch is unreachable** — `check_permission`
/// runs before dispatch and refuses the malformed resource with `403
/// capability_denied` first. That was measured on `python` (AP-4.5) and the branch is
/// kept for the same reason it is kept there: it is still right for an in-process call,
/// which has no cap check in front of it. (Until keystone's H1 on 2026-09-12 every call on
/// this peer was in-process, so here it was the only reachable answer.)
fn resource_targets(exec: &Entity) -> Option<Vec<String>> {
    let resource = exec.field("resource")?;
    let targets = model::map_get(resource, "targets")?;
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

/// A resource target is in-namespace if it IS the prefix or sits under it.
fn within_namespace(target: &str, namespace: &str) -> bool {
    let t = target.trim_start_matches('/');
    t == namespace || t.starts_with(&format!("{namespace}/"))
}

/// Encoded size of an entity, for frame-budget accounting.
///
/// `typescript` reads `entity.wireBytes.length` — a decoded entity there retains its
/// original bytes (§1.8 forward-original). Neither `python` nor this peer's `Entity`
/// carries a wire form (`typ` / `data` / `hash` only), so the size is computed. Two of
/// three ports pay this, which is the row of §2.4 of the authoring notes that stopped
/// looking like a `python` quirk once a third substrate agreed with it.
fn wire_size(entity: &Entity) -> usize {
    entity_core_protocol::cbor::encode(&entity.to_cbor()).len()
}

/// H1 — the dispatch path. `route` calls this after §6.6 resolution and the dispatch-time
/// `check_permission` have allowed the request (§6.4 step 1).
impl Handler for ContentHandler {
    fn pattern(&self) -> &str {
        CONTENT_PATTERN
    }

    fn name(&self) -> &str {
        "content"
    }

    fn operations(&self) -> Vec<OperationSpec> {
        vec![
            OperationSpec::typed("get", GET_REQUEST, CONTENT_RESPONSE),
            OperationSpec::typed("ingest", INGEST_REQUEST, INGEST_RESULT),
        ]
    }

    fn handle(&self, ctx: &HandlerContext<'_>) -> HandlerResult {
        let req = HandlerRequest {
            exec: ctx.execute(),
            store: &ctx.peer().store,
            frame_budget: FrameBudget::from_context(ctx),
            caller_capability: ctx.caller_capability(),
            local_peer: ctx.local_peer(),
        };
        let outcome = self.handle_op(ctx.operation(), &req);
        HandlerResult {
            status: outcome.status,
            result: outcome.result,
            included: outcome.included,
        }
    }
}
