//! CONTENT §6 — the system content handler.
//!
//! Two operations, `get` (§6.2) and `ingest` (§6.3), both hash-addressed at the params
//! level and path-addressed at the cap-scope level (§6.4).
//!
//! # This handler is written and tested. It cannot be installed. Both facts are real.
//!
//! `gates/host-seam/rust/` measures the seam by execution and by rustc:
//!
//! ```text
//! A. nothing bound                    404  handler_not_found
//! B. all four §11.6.1 tree writes     501  no_handler_body
//! C. the same body called DIRECTLY    200  witness=...   invocations 0 -> 1
//! error[E0624]: method `register_handler` is private
//! error[E0609]: no field `handlers` on type `Peer`
//! error[E0603]: struct `Outcome` is private
//! ```
//!
//! So the module cannot spell its result as the peer's `Outcome`, cannot receive the
//! peer's dispatch context, and has nowhere to be bound. **What it can still be is
//! correct**, and correct is testable: every branch below is exercised by
//! `tests/handler.rs` against a real peer `Store`, driving the same §6.2/§6.3
//! algorithms the other two ports drive over the wire.
//!
//! What that does NOT buy is a conformance claim. `tests/handler.rs` is ours; the
//! oracle never reaches this code on this peer; and **the extension being its own
//! instrument is an argument that only works when a wire check runs THROUGH it.**
//! Here none does. Stated in `EXTENSION.toml` as `reached_by = []` for every entry on
//! this port, and stated again in the composition's conformance report.
//!
//! # Three context facts this handler is built around
//!
//! 1. **There is no dispatch context type.** `typescript` has `ctx`, `python` has
//!    `DispatchCtx`; here the dispatcher passes `(&mut Conn, &Envelope)` to private
//!    code. So [`HandlerRequest`] is OURS, and its shape is a claim about what a body
//!    would need rather than a mirror of what a body is given.
//! 2. **The store arrives by registration-time capture**, exactly as on `python`, and
//!    for the same reason: nothing in a request carries a route back to the peer.
//! 3. **The frame budget is the peer's transport constant.** See [`FrameBudget`].

use entity_core_protocol::peer::model::{self, entity_of_cbor, Entity};
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::peer::wire;
use entity_core_protocol::value::{Key, Value};

use crate::sdk::DispatchAuthority;
use crate::types::{CONTENT_PATTERN, CONTENT_RESPONSE, INGEST_RESULT};

/// Envelope + response overhead reserved out of the frame budget before entities are
/// packed. The response entity carries two hash arrays (33 B each plus CBOR framing)
/// and the envelope adds its own map framing; 4 KiB is comfortably above both for any
/// batch a caller can request within one frame.
pub const FRAME_RESERVE_BYTES: usize = 4096;

/// The bound in force on the connection this request arrived over.
///
/// **CONTENT Amendment 1 §6.2 forbids a hardcoded 16 MiB literal and requires
/// consulting the connection's configured budget at response-construction time. On
/// this peer those two are the same number, and that is a finding rather than a
/// loophole.**
///
/// `wire::MAX_FRAME` is `16 * 1024 * 1024` — the exact literal the amendment names as
/// the wrong answer — and it is what `read_frame` enforces. But it is not *hardcoded
/// by us*: it is the peer's own transport constant, read from the peer, and it is the
/// only bound the peer ever enforces because `CreateOptions` has no frame field and
/// `Conn` carries none (measured: `gates/host-seam/rust`, scenario 3).
///
/// So the MUST is satisfied **degenerately**: the value read is the value enforced.
/// The routed finding is *"make it configurable"*, not *"this is unimplementable"* —
/// which is a materially different packet from the one that became K-1 on `python`,
/// where nothing on the connection carried a budget at all AND the constant was
/// consulted by a body that could not see it.
///
/// This is an enum with one variant on purpose. A bare `usize` would let a caller pass
/// a number with no statement about where it came from, and that is precisely the
/// provenance Amendment 1 is about.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FrameBudget {
    /// The bound the transport is enforcing, read from the peer that enforces it.
    Enforced(usize),
}

impl FrameBudget {
    /// Read the bound from the peer's own transport module.
    pub fn from_peer() -> FrameBudget {
        FrameBudget::Enforced(wire::MAX_FRAME)
    }

    fn bytes(self) -> usize {
        match self {
            FrameBudget::Enforced(n) => n,
        }
    }
}

/// What a §11.6.1 body would receive, if there were a way to be one.
pub struct HandlerRequest<'a> {
    /// The `system/protocol/execute` entity (§3.2).
    pub exec: &'a Entity,
    /// Registration-time capture. Nothing in `exec` routes back to the peer.
    pub store: &'a Store,
    pub frame_budget: FrameBudget,
}

/// A handler outcome: status, the result entity, and protocol entities to bundle.
///
/// **This type exists because the peer's does not export.** `peer::core::Outcome` is a
/// bare `struct` with no `pub` (`error[E0603]`, measured), so a third party cannot name
/// it, construct it, or return it. That is D13's Export layer, and on this substrate it
/// is not a review finding — it is a compile error.
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
        for target in &targets {
            if !within_namespace(target, &self.namespace) {
                return ContentOutcome::err(
                    403,
                    "forbidden",
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
        // Minted here and nowhere else. Everything past this line is inside the
        // "trusted handler-context boundary" §3.4 names.
        let _authority = DispatchAuthority::mint();

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

        let mut remaining = req.frame_budget.bytes().saturating_sub(FRAME_RESERVE_BYTES);
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
            return ContentOutcome::err(400, "ambiguous_input", "Specify envelope or entity, not both");
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
                        (Key::Text("root_hash".into()), Value::Bytes(entity.hash.clone())),
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
                    (Key::Text("root_hash".into()), Value::Bytes(root.hash.clone())),
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
/// which has no cap check in front of it. On THIS peer every call is in-process, so
/// here it is the only reachable answer rather than the unreachable one.
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
