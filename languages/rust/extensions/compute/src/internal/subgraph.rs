//! COMPUTE §3.3 `audit_subgraph` and §7.1 `walk_tree_lookups` — **ONE walker**, as §3.3 permits.
//!
//! Here it is not an optimisation. The two listings disagree and the wrong one is the one that
//! authorizes: §7.1's walker descends `apply.args` / `let.bindings` `[MUST, v3.27]` and §3.3's does
//! not, so a literal §3.3 capability-checks a tree read at the top level and skips the same read one
//! argument deep (A-17, routed). Two clauses §3.3's listing does not carry are implemented because
//! the same document MUSTs them elsewhere: **Q23** (§2.1, a builtin-path apply carrying
//! `capability`/`resource` is `invalid_expression`, *"enforced at install time too"*; A-18) and
//! **SA-11** (no builtin path is a handler target; A-19).
//!
//! Nothing here evaluates. A value only knowable at runtime is left to the runtime check.
//!
//! A port of `../../../../python/extensions/compute/_internal/subgraph.py`. [`path_permitted`] is
//! keystone's H9 predicate, called; [`grant_covers`] goes through the peer's §5.2 `check_permission`
//! with the granter frame resolved, because chain attenuation is a different question from H9's.

use std::collections::{BTreeMap, HashSet};

use entity_core_protocol::peer::capability::{self, Verdict, MAX_CHAIN_DEPTH};
use entity_core_protocol::peer::model::{Entity, Envelope};
use entity_core_protocol::peer::store::Store;
use entity_core_protocol::peer::wire::{self, ExecuteFields};
use entity_core_protocol::value::{Key, Value};

use super::evaluator::{
    builtin_name, canonicalize_path, clean_path, relative_pattern, CONTENT_HASH_LENGTH,
};
use crate::types::{
    is_compute_type, APPLY, BUILTINS_PREFIX, CODE_INVALID_EXPRESSION, LITERAL, LOOKUP_HASH,
    LOOKUP_TREE,
};

/// §3.3 Phase 1's `handler_targets` entry. `resource` is `None` when dynamic or absent.
#[derive(Clone, Debug)]
pub struct HandlerTarget {
    pub path: String,
    pub operation: Option<String>,
    pub resource: Option<Value>,
}

/// §3.3 Phase 2b's `data_hashes` entry (v3.7 D3/D6). `path` is the hint, or `None`.
#[derive(Clone, Debug)]
pub struct DataHashRef {
    pub hash: Vec<u8>,
    pub path: Option<String>,
}

/// What one walk produced. `read_paths` serves §3.3's `read_paths` AND §7.1's `deps`, canonicalized
/// once here so the two cannot drift.
#[derive(Clone, Debug, Default)]
pub struct SubgraphAudit {
    pub read_paths: Vec<String>,
    pub handler_targets: Vec<HandlerTarget>,
    pub write_paths: Vec<String>,
    pub data_hashes: Vec<DataHashRef>,
}

/// A refusal carrying the status/code pair §3.3 names for it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuditRefusal {
    pub status: u64,
    pub code: String,
    pub message: String,
}

fn refusal(status: u64, code: &str, message: &str) -> AuditRefusal {
    AuditRefusal {
        status,
        code: code.to_string(),
        message: message.to_string(),
    }
}

/// What the audit reads. No budget, no scope.
pub struct AuditContext<'a> {
    pub store: &'a Store,
    pub local_peer: &'a str,
    /// §4.2 step 1 — the EXECUTE envelope's `included` map.
    pub included: &'a BTreeMap<Vec<u8>, Entity>,
    /// `ctx.execute.data.author` — the installer's identity hash, for CP1.
    pub author: Option<Vec<u8>>,
}

struct WalkState<'a, 'c> {
    root_path: &'a str,
    ctx: &'a AuditContext<'c>,
    visited: HashSet<Vec<u8>>,
    out: SubgraphAudit,
}

const STORE_BUILTIN_SUFFIX: &str = "/store";

/// §3.3 Phase 1 — walk the expression graph from `root` and collect the four categories, or refuse
/// on a static structural error. `root_path` MUST already be canonical.
pub fn audit_subgraph(
    root: &Entity,
    root_path: &str,
    ctx: &AuditContext,
) -> Result<SubgraphAudit, AuditRefusal> {
    let mut st = WalkState {
        root_path,
        ctx,
        visited: HashSet::new(),
        out: SubgraphAudit::default(),
    };
    walk_node(root, &mut st)?;
    Ok(st.out)
}

fn walk_node(entity: &Entity, st: &mut WalkState) -> Result<(), AuditRefusal> {
    // §3.3's cycle detection, keyed on the content hash exactly as the listing is.
    if !st.visited.insert(entity.hash.clone()) {
        return Ok(());
    }

    if entity.typ == LOOKUP_TREE {
        let path = lookup_path(entity, st);
        st.out.read_paths.push(path);
        return Ok(()); // a leaf — its `path` is text, not a reference.
    }

    if entity.typ == LOOKUP_HASH {
        // The `hash` points at DATA, not an expression; returning here keeps the generic descent
        // from auditing a data reference as a sub-expression.
        let Some(hash) = entity.bytes_field("hash") else {
            return Err(refusal(
                400,
                CODE_INVALID_EXPRESSION,
                "compute/lookup/hash requires a hash field",
            ));
        };
        let resolved_hint = entity.text_field("path").map(|hint| {
            if matches!(entity.field("relative"), Some(Value::Bool(true))) {
                clean_path(&format!("{}/{hint}", st.root_path))
            } else {
                hint.to_string()
            }
        });
        st.out.data_hashes.push(DataHashRef {
            hash: hash.to_vec(),
            path: resolved_hint,
        });
        return Ok(());
    }

    if entity.typ == APPLY {
        audit_apply(entity, st)?;
        // and FALL THROUGH — how a `lookup/tree` inside `args` is reached.
    }

    // §7.1's `walk_value`, applied to §3.3's walk too. THIS LOOP IS A-17.
    if let Value::Map(entries) = &entity.data {
        for (_, value) in entries {
            walk_value(value, st)?;
        }
    }
    Ok(())
}

fn walk_value(value: &Value, st: &mut WalkState) -> Result<(), AuditRefusal> {
    match value {
        Value::Bytes(b) => {
            if b.len() != CONTENT_HASH_LENGTH {
                return Ok(());
            }
            // §3.3's audit scope (normative): a hash resolving to a NON-compute entity is skipped —
            // which is also what stops a literal holding a 33-byte capability hash from being walked.
            match lookup_entity(b, st.ctx) {
                Some(referenced) if is_compute_type(&referenced.typ) => walk_node(&referenced, st),
                _ => Ok(()),
            }
        }
        Value::Array(items) => {
            for item in items {
                walk_value(item, st)?;
            }
            Ok(())
        }
        Value::Map(entries) => {
            for (_, member) in entries {
                walk_value(member, st)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

/// §3.3's `compute/apply` arm — Q23, F5, CP1, F3, then the `store` write target. The order is
/// normative.
fn audit_apply(entity: &Entity, st: &mut WalkState) -> Result<(), AuditRefusal> {
    let Some(path) = entity.text_field("path") else {
        return Ok(()); // closure mode — nothing to authorize.
    };
    let has_capability = entity.bytes_field("capability").is_some();
    let has_resource = entity.bytes_field("resource").is_some();
    let builtin = builtin_name(path);

    // Q23 (§2.1).
    if builtin.is_some() && (has_capability || has_resource) {
        return Err(refusal(
            400,
            CODE_INVALID_EXPRESSION,
            "compute/apply on a builtin path MUST NOT carry capability or resource (§2.1 Q23, install-time)",
        ));
    }
    // F5 (v3.10).
    if has_capability && !has_resource {
        return Err(refusal(
            400,
            CODE_INVALID_EXPRESSION,
            "compute/apply with capability field MUST also have resource field (§2.1 F5)",
        ));
    }
    // CP1 (v3.11) — a STATIC-LITERAL embedded capability must have the installer IN its chain.
    if has_capability {
        check_embedded_capability(entity, st)?;
    }
    // F3 (v3.10) — a static-literal resource is audited; a dynamic one is deferred.
    let mut resource = None;
    if has_resource {
        if let Some(literal) = resolve_literal(entity.bytes_field("resource"), st.ctx) {
            if let Some(value) = literal.field("value") {
                if matches!(map_get(value, "targets"), Some(Value::Array(_))) {
                    resource = Some(value.clone());
                }
            }
        }
    }
    // SA-11 / A-19 — no builtin path is ever a handler target.
    if builtin.is_none() {
        st.out.handler_targets.push(HandlerTarget {
            path: path.to_string(),
            operation: entity.text_field("operation").map(str::to_string),
            resource,
        });
    }
    // §3.3's `store` special case: a LITERAL path argument becomes a static write target.
    if relative_pattern(path) == format!("{BUILTINS_PREFIX}{STORE_BUILTIN_SUFFIX}") {
        if let Some(Value::Map(args)) = entity.field("args") {
            let path_arg = args.iter().find_map(|(k, v)| match (k, v) {
                (Key::Text(t), Value::Bytes(b))
                    if t == "path" && b.len() == CONTENT_HASH_LENGTH =>
                {
                    Some(b)
                }
                _ => None,
            });
            if let Some(h) = path_arg {
                if let Some(literal) = resolve_literal(Some(h), st.ctx) {
                    if let Some(Value::Text(target)) = literal.field("value") {
                        st.out.write_paths.push(target.clone());
                    }
                }
            }
        }
    }
    Ok(())
}

/// CP1 / §10.1 — the installer MUST appear **as a granter anywhere in** the static-literal chain.
/// In-chain, NOT rooted-at-author: a client-minted dispatch capability roots at the REMOTE peer's
/// connection capability and has the installer as the leaf granter.
fn check_embedded_capability(entity: &Entity, st: &WalkState) -> Result<(), AuditRefusal> {
    let Some(cap_ref) = resolve_literal(entity.bytes_field("capability"), st.ctx) else {
        return Ok(()); // dynamic capability — runtime dual-check applies.
    };
    let unreachable_chain = |m: &str| refusal(404, "chain_unreachable", m);

    let value = match cap_ref.field("value") {
        Some(Value::Bytes(b)) if b.len() == CONTENT_HASH_LENGTH => b.clone(),
        _ => {
            return Err(unreachable_chain(
                "Static compute/apply.capability does not name a capability entity",
            ))
        }
    };
    let Some(cap_entity) = lookup_entity(&value, st.ctx) else {
        return Err(unreachable_chain(
            "Static compute/apply.capability authority chain not fully resolvable",
        ));
    };
    let Some(author) = st.ctx.author.as_deref() else {
        return Err(refusal(
            403,
            "embedded_cap_unauthorized",
            "Install has no author identity to check the chain against",
        ));
    };

    // §5.5's chain bound, from the peer's own public constant.
    let mut current = Some(cap_entity);
    for _ in 0..=MAX_CHAIN_DEPTH {
        let Some(cap) = current else {
            return Err(unreachable_chain(
                "Static compute/apply.capability authority chain not fully resolvable",
            ));
        };
        if cap.typ != "system/capability/token" {
            return Err(unreachable_chain(
                "Static compute/apply.capability chain contains a non-capability entity",
            ));
        }
        if cap.bytes_field("granter") == Some(author) {
            return Ok(()); // IN-CHAIN as a granter.
        }
        let Some(parent) = cap.bytes_field("parent") else {
            break; // root reached, installer never appeared.
        };
        current = lookup_entity(parent, st.ctx);
    }
    Err(refusal(
        403,
        "embedded_cap_unauthorized",
        "Installer identity not in static compute/apply.capability chain",
    ))
}

// ── Phase 2 — the capability checks ─────────────────────────────────────────────────

/// A carrier EXECUTE for the peer's §5.2 predicate. Never dispatched, signed or sent.
fn carrier(handler_pattern: &str, operation: &str, resource: Option<Value>) -> Entity {
    wire::make_execute(ExecuteFields {
        request_id: "audit-phase2",
        // A peer-relative pattern makes `extract_peer` answer the local peer.
        uri: handler_pattern,
        operation,
        params: wire::empty_params(),
        resource,
        author: None,
        capability: None,
    })
}

/// Core §6.3's path check — keystone's H9 `check_path_permission`, called rather than re-derived.
///
/// **Local frame, no granter frame, `system/tree` as the handler pattern** — the scope H9 names and
/// the call the other two ports make. Until keystone landed H9 on this peer the question went through
/// `check_permission` over a carrier EXECUTE, which also matched the grant's `peers` scope; that one
/// extra dimension is gone with the carrier.
pub fn path_permitted(operation: &str, path: &str, token: &Entity, local_peer: &str) -> bool {
    capability::check_path_permission(operation, path, token, "system/tree", local_peer)
}

/// §3.3's `check_grant_covers(path, operation, resource, capability, local_peer_id)`, through the
/// peer's own §5.2 predicate — never a re-derived grant walk (HISTORY paid for that: 23 of 34).
///
/// **The granter frame IS resolved here** (§PR-8): this is the chain-attenuation surface, where
/// omitting the frame would over-admit a cross-peer grant. Contrast [`path_permitted`].
pub fn grant_covers(
    store: &Store,
    included: &BTreeMap<Vec<u8>, Entity>,
    capability_token: &Entity,
    handler_pattern: &str,
    operation: Option<&str>,
    resource: Option<Value>,
    local_peer: &str,
) -> bool {
    let exec = carrier(handler_pattern, operation.unwrap_or(""), resource);
    let envelope = Envelope::with_included(exec.clone(), included.values().cloned().collect());
    let granter = capability::granter_frame(&envelope, store, local_peer, capability_token);
    capability::check_permission(
        local_peer,
        &granter,
        &exec,
        capability_token,
        handler_pattern,
    ) == Verdict::Allow
}

// ── resolution ──────────────────────────────────────────────────────────────────────

/// The audit's resolver: `included`, then the content store. Deliberately NOT §4.2's tiers.
fn lookup_entity(hash: &[u8], ctx: &AuditContext) -> Option<Entity> {
    ctx.included
        .get(hash)
        .cloned()
        .or_else(|| ctx.store.get_by_hash(hash))
}

fn resolve_literal(hash: Option<&[u8]>, ctx: &AuditContext) -> Option<Entity> {
    lookup_entity(hash?, ctx).filter(|e| e.typ == LITERAL)
}

fn lookup_path(entity: &Entity, st: &WalkState) -> String {
    match entity.text_field("path") {
        // No path cannot name a read; recorded as "" so Phase 2 refuses rather than authorizing nothing.
        None => String::new(),
        Some(raw) if matches!(entity.field("relative"), Some(Value::Bool(true))) => {
            clean_path(&format!("{}/{raw}", st.root_path))
        }
        Some(raw) => canonicalize_path(raw, st.ctx.local_peer),
    }
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
