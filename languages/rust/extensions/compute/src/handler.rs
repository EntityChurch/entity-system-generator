//! COMPUTE §3 — the `system/compute` handler, for the `rust` peer.
//!
//! # Installed through `Peer::register_handler` (keystone H1)
//!
//! Until keystone landed H1 on this peer this body was written, tested and had nowhere to go
//! (`register_handler` private, `E0624`). It is installed by [`crate::install_compute`] now, and the
//! [`Handler`] impl below is the whole of the change: it reads the request out of the peer's
//! [`HandlerContext`] into [`HandlerRequest`] and hands the outcome back as a [`HandlerResult`]. The
//! body did not change, which is what "the day H1 lands, this file does not change" promised and
//! what the unit tests — which still drive [`ComputeHandler::handle`] directly — keep true.
//!
//! [`HandlerRequest`] stays OURS rather than becoming `HandlerContext`: a third party cannot build a
//! `HandlerContext` (its fields are `pub(crate)`), so the tests could not reach the body through it.
//!
//! Per-path checks go through `internal::subgraph::path_permitted`, which is keystone's H9
//! `check_path_permission`.

use std::collections::BTreeMap;
use std::sync::Arc;

use entity_core_protocol::peer::handler::{
    Handler, HandlerContext, HandlerResult, LocalExecute, OperationSpec,
};
use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::{ExecContext, Store};
use entity_core_protocol::peer::wire;
use entity_core_protocol::value::{Key, Value};

use crate::internal::evaluator::{canonicalize_path, DispatchCall, Dispatcher};
use crate::internal::reactive::{deterministic_id, ReactiveEngine};
use crate::internal::subgraph::{
    audit_subgraph, grant_covers, path_permitted, AuditContext, SubgraphAudit,
};
use crate::sdk::{ComputeEvaluator, EvaluateOptions, EvaluatorLimits, RequestContext};
use crate::types::{
    is_compute_expression, CODE_AMBIGUOUS_RESOURCE, CODE_INVALID_EXPRESSION, CODE_NOT_FOUND,
    CODE_PERMISSION_DENIED, COMPUTE_PATTERN, INSTALL_REQUEST, INSTALL_RESULT, PROCESSES_PREFIX,
    RESULT, SUBGRAPH,
};

/// §3.1 / §9.2's three operations, in ladder order.
pub const OPERATIONS: [&str; 3] = ["eval", "install", "uninstall"];

/// §3.1's manifest operations, in the mapped §3.7 form, as `(operation, input_type, output_type)`.
///
/// `uninstall` takes `primitive/any` — empty params per V7 §3.2; the `uninstall-request` type was
/// eliminated in v3.12 and the declaration header still names it (§9.2 drift, filed).
pub const OPERATION_SPECS: [(&str, &str, &str); 3] = [
    ("eval", "primitive/any", "primitive/any"),
    ("install", INSTALL_REQUEST, INSTALL_RESULT),
    ("uninstall", "primitive/any", "system/protocol/status"),
];

/// What the body reads from a request. Built from the peer's [`HandlerContext`] on the dispatch
/// path, and by hand in `tests/`.
pub struct HandlerRequest<'a> {
    /// The `system/protocol/execute` entity (§3.2).
    pub exec: &'a Entity,
    /// Registration-time capture.
    pub store: &'a Store,
    pub local_peer: &'a str,
    /// The caller's capability token, as the dispatcher would have resolved it. `None` models an
    /// in-process call with no token.
    pub caller_capability: Option<&'a Entity>,
    /// §4.2 step 1 — the envelope's `included` map.
    pub included: &'a BTreeMap<Vec<u8>, Entity>,
    /// The §6.8a execution context a dispatcher would stamp on this request's writes.
    pub context: Option<&'a ExecContext>,
}

/// A handler outcome. Kept rather than replaced by the peer's [`HandlerResult`]: the body has no
/// `included` entities to bundle, and the tests assert on this shape.
#[derive(Clone, Debug)]
pub struct ComputeOutcome {
    pub status: u64,
    pub result: Entity,
}

impl ComputeOutcome {
    fn ok(result: Entity) -> ComputeOutcome {
        ComputeOutcome {
            status: 200,
            result,
        }
    }

    fn err(status: u64, code: &str, message: &str) -> ComputeOutcome {
        ComputeOutcome {
            status,
            result: wire::error_result(code, Some(message)),
        }
    }
}

/// The §3.1 handler.
pub struct ComputeHandler {
    limits: EvaluatorLimits,
    /// §7's engine, or `None` when reactive mode is not installed. `install` refuses without one
    /// rather than recording a subgraph nothing can ever wake.
    engine: Option<Arc<ReactiveEngine>>,
}

impl ComputeHandler {
    /// A method-configured constructor rather than a `ComputeHandlerOptions` struct: two settings,
    /// both with §9.3 defaults, is `new` plus `limits`. `[sdk_surface].substrate`.
    pub fn new(engine: Option<Arc<ReactiveEngine>>, limits: EvaluatorLimits) -> ComputeHandler {
        ComputeHandler { limits, engine }
    }

    /// Serve one operation with no dispatcher: `compute/apply` handler mode answers
    /// `invalid_expression` naming that. The dispatch path is the [`Handler`] impl below.
    pub fn handle(&self, operation: &str, req: &HandlerRequest) -> ComputeOutcome {
        self.handle_dispatching(operation, req, None)
    }

    fn handle_dispatching(
        &self,
        operation: &str,
        req: &HandlerRequest,
        dispatch: Option<&Dispatcher<'_>>,
    ) -> ComputeOutcome {
        match operation {
            "eval" => self.eval(req, dispatch),
            "install" => self.install(req),
            "uninstall" => self.uninstall(req),
            other => ComputeOutcome::err(
                400,
                "unknown_operation",
                &format!("{COMPUTE_PATTERN} has no operation '{other}' (§3.1)"),
            ),
        }
    }

    // ── §3.2 handle_eval ─────────────────────────────────────────────────────────────

    /// §3.2 `handle_eval`. The three refusals in §3.2's order; an evaluated `compute/error` comes
    /// back at **status 200** (F10).
    fn eval(&self, req: &HandlerRequest, dispatch: Option<&Dispatcher<'_>>) -> ComputeOutcome {
        let Some(target) = single_resource_target(req.exec) else {
            return ComputeOutcome::err(
                400,
                CODE_AMBIGUOUS_RESOURCE,
                "eval requires exactly one resource target (the expression path)",
            );
        };
        let absolute = canonicalize_path(&target, req.local_peer);
        let Some(expression) = req.store.get_at(&absolute) else {
            return ComputeOutcome::err(404, CODE_NOT_FOUND, "No entity at path");
        };
        if !is_compute_expression(&expression.typ) {
            return ComputeOutcome::err(
                400,
                CODE_INVALID_EXPRESSION,
                "Entity at path is not a compute expression",
            );
        }

        let local = req.local_peer.to_string();
        let cap = req.caller_capability.cloned();
        let can_read = |path: &str| {
            cap.as_ref()
                .is_none_or(|c| path_permitted("get", path, c, &local))
        };
        let can_write = |path: &str| {
            cap.as_ref()
                .is_none_or(|c| path_permitted("put", path, c, &local))
        };

        let mut evaluator = ComputeEvaluator::new(req.store, req.local_peer, self.limits);
        let outcome = evaluator.evaluate_in_request(
            &expression,
            &absolute,
            EvaluateOptions {
                budget: params_entity(req.exec).and_then(|p| p.uint_field("budget")),
                included: Some(req.included),
                can_read_path: Some(&can_read),
                can_write_path: Some(&can_write),
                ..Default::default()
            },
            RequestContext {
                capability: req.caller_capability,
                dispatch,
                bindings: Vec::new(),
                // §6.8a — `system/compute:eval` is a dispatched request, so a `builtins/store`
                // write inside this evaluation is the CALLER's, not the peer's. `req.context` is
                // `ctx.exec_context()` (handler.rs, `HandlerRequest::from_context`).
                exec_context: req.context,
            },
        );

        if let Some(error) = outcome.error {
            return ComputeOutcome::ok(error.to_entity());
        }
        if let Some(entity) = outcome.entity {
            return ComputeOutcome::ok(entity);
        }
        ComputeOutcome::ok(Entity::make(
            RESULT,
            Value::Map(vec![
                (
                    Key::Text("value".into()),
                    outcome.value.unwrap_or(Value::Null),
                ),
                (
                    Key::Text("expression".into()),
                    Value::Bytes(expression.hash.clone()),
                ),
            ]),
        ))
    }

    // ── §3.3 handle_install ──────────────────────────────────────────────────────────

    /// §3.3 `handle_install` — four phases, PRE-FLIGHT then COMMIT. Nothing is written before the
    /// last check passes, because Phase 2b SEALS `authorized_data_hashes`.
    fn install(&self, req: &HandlerRequest) -> ComputeOutcome {
        let Some(engine) = self.engine.as_ref() else {
            return ComputeOutcome::err(
                501,
                "not_implemented",
                "system/compute:install requires §7 reactive mode, which is not installed in this \
                 composition (the emit_consumer face). An install with no engine behind it would \
                 record a subgraph nothing can ever wake.",
            );
        };
        let Some(target) = single_resource_target(req.exec) else {
            return ComputeOutcome::err(
                400,
                CODE_AMBIGUOUS_RESOURCE,
                "install requires exactly one resource target (the root expression path)",
            );
        };
        let local = req.local_peer;
        let root_path = canonicalize_path(&target, local);
        let Some(expression) = req.store.get_at(&root_path) else {
            return ComputeOutcome::err(404, CODE_NOT_FOUND, "No expression at path");
        };
        if !is_compute_expression(&expression.typ) {
            return ComputeOutcome::err(
                400,
                CODE_INVALID_EXPRESSION,
                "Entity at path is not a compute expression",
            );
        }

        // ── Phase 1 ──
        let audit_ctx = AuditContext {
            store: req.store,
            local_peer: local,
            included: req.included,
            author: req.exec.bytes_field("author").map(<[u8]>::to_vec),
        };
        let audit = match audit_subgraph(&expression, &root_path, &audit_ctx) {
            Ok(a) => a,
            Err(r) => return ComputeOutcome::err(r.status, &r.code, &r.message),
        };

        // ── Phase 2 ──
        let Some(capability) = req.caller_capability else {
            return ComputeOutcome::err(
                403,
                CODE_PERMISSION_DENIED,
                "install requires a verified caller capability to audit against",
            );
        };
        for path in &audit.read_paths {
            if !path_permitted("get", path, capability, local) {
                return ComputeOutcome::err(
                    403,
                    CODE_PERMISSION_DENIED,
                    &format!("Caller capability does not cover read: {path}"),
                );
            }
        }
        for t in &audit.handler_targets {
            if !grant_covers(
                req.store,
                req.included,
                capability,
                &t.path,
                t.operation.as_deref(),
                t.resource.clone(),
                local,
            ) {
                return ComputeOutcome::err(
                    403,
                    CODE_PERMISSION_DENIED,
                    &format!(
                        "Caller capability does not cover handler: {}.{}",
                        t.path,
                        t.operation.as_deref().unwrap_or("")
                    ),
                );
            }
        }
        let result_path = match params_entity(req.exec)
            .and_then(|p| p.text_field("result_path").map(str::to_string))
        {
            Some(requested) => canonicalize_path(&requested, local),
            None => format!("{root_path}/result"),
        };
        if !path_permitted("put", &result_path, capability, local) {
            return ComputeOutcome::err(
                403,
                CODE_PERMISSION_DENIED,
                &format!("Caller capability does not cover result write: {result_path}"),
            );
        }
        for path in &audit.write_paths {
            let canonical = canonicalize_path(path, local);
            if !path_permitted("put", &canonical, capability, local) {
                return ComputeOutcome::err(
                    403,
                    CODE_PERMISSION_DENIED,
                    &format!("Caller capability does not cover write: {canonical}"),
                );
            }
        }

        // ── Phase 2b — each data hash validated three ways before it is admitted ──
        let mut authorized: Vec<Value> = Vec::new();
        for entry in &audit.data_hashes {
            let Some(hint) = &entry.path else {
                return ComputeOutcome::err(
                    400,
                    "no_authorization_path",
                    "compute/lookup/hash without path hint requires reverse index or content_store_access",
                );
            };
            let hint_path = canonicalize_path(hint, local);
            let Some(bound) = req.store.get_at(&hint_path) else {
                return ComputeOutcome::err(
                    404,
                    CODE_NOT_FOUND,
                    &format!("No entity at hint path: {hint_path}"),
                );
            };
            if bound.hash != entry.hash {
                return ComputeOutcome::err(
                    400,
                    "hash_mismatch",
                    &format!(
                        "Entity at {hint_path} has hash {}, expression references {}",
                        hex(&bound.hash),
                        hex(&entry.hash)
                    ),
                );
            }
            if !path_permitted("get", &hint_path, capability, local) {
                return ComputeOutcome::err(
                    403,
                    CODE_PERMISSION_DENIED,
                    &format!("Caller grant does not cover tree GET at: {hint_path}"),
                );
            }
            authorized.push(Value::Bytes(entry.hash.clone()));
        }

        // ── Phase 3 — commit. The capability entity reaches the content store BEFORE its hash is
        //    recorded: §7.2 fetches it by hash on every re-evaluation.
        let subgraph_path = format!(
            "{}/{}",
            canonicalize_path(PROCESSES_PREFIX, local),
            deterministic_id(&root_path)
        );
        req.store.put_entity(capability);
        let mut data = vec![
            (
                Key::Text("root_expression_path".into()),
                Value::Text(root_path.clone()),
            ),
            (
                Key::Text("root_expression".into()),
                Value::Bytes(expression.hash.clone()),
            ),
            (
                Key::Text("installation_grant".into()),
                Value::Bytes(capability.hash.clone()),
            ),
            (
                Key::Text("result_path".into()),
                Value::Text(result_path.clone()),
            ),
            (Key::Text("status".into()), Value::Text("active".into())),
        ];
        if let Some(author) = req.exec.bytes_field("author") {
            data.push((
                Key::Text("installed_by".into()),
                Value::Bytes(author.to_vec()),
            ));
        }
        // The SEVENTH field, omitted when empty so the bytes agree with the reference's `omitempty`.
        if !authorized.is_empty() {
            data.push((
                Key::Text("authorized_data_hashes".into()),
                Value::Array(authorized),
            ));
        }
        let subgraph = Entity::make(SUBGRAPH, Value::Map(data));
        req.store
            .bind_with_context(&subgraph_path, &subgraph, req.context.cloned());

        // ── Phase 4 — register, then evaluate once ──
        engine.register(&subgraph_path, &root_path, &audit);
        engine.evaluate_now(&subgraph_path, req.context);

        ComputeOutcome::ok(Entity::make(
            INSTALL_RESULT,
            Value::Map(vec![
                (
                    Key::Text("subgraph_path".into()),
                    Value::Text(subgraph_path),
                ),
                (
                    Key::Text("impure_operations".into()),
                    impure_operations(&audit),
                ),
                (Key::Text("result_path".into()), Value::Text(result_path)),
            ]),
        ))
    }

    // ── §3.4 handle_uninstall ────────────────────────────────────────────────────────

    /// §3.4 — clear the registrations, delete the metadata. The expression entities stay.
    fn uninstall(&self, req: &HandlerRequest) -> ComputeOutcome {
        let Some(engine) = self.engine.as_ref() else {
            return ComputeOutcome::err(
                501,
                "not_implemented",
                "system/compute:uninstall requires §7 reactive mode, which is not installed in this composition",
            );
        };
        let Some(target) = single_resource_target(req.exec) else {
            return ComputeOutcome::err(
                400,
                CODE_AMBIGUOUS_RESOURCE,
                "uninstall requires exactly one resource target (the subgraph path)",
            );
        };
        let subgraph_path = canonicalize_path(&target, req.local_peer);
        match req.store.get_at(&subgraph_path) {
            Some(s) if s.typ == SUBGRAPH => {}
            _ => return ComputeOutcome::err(404, CODE_NOT_FOUND, "No installed subgraph at path"),
        }
        engine.unregister(&subgraph_path);
        req.store
            .unbind_with_context(&subgraph_path, req.context.cloned());
        // §3.4 returns the status and nothing else; `system/protocol/status` is a type no registry
        // defines (§9.2 drift), so the body is the empty-ack shape rather than a minted type.
        ComputeOutcome::ok(Entity::make("primitive/any", Value::Map(vec![])))
    }
}

/// H1 — the dispatch path. `route` calls this after §6.6 resolution and the dispatch-time
/// `check_permission` have allowed the request.
impl Handler for ComputeHandler {
    fn pattern(&self) -> &str {
        COMPUTE_PATTERN
    }

    fn name(&self) -> &str {
        "compute"
    }

    fn operations(&self) -> Vec<OperationSpec> {
        OPERATION_SPECS
            .iter()
            .map(|(name, input, output)| OperationSpec::typed(name, input, output))
            .collect()
    }

    fn handle(&self, ctx: &HandlerContext<'_>) -> HandlerResult {
        let peer = ctx.peer();
        let context = ctx.exec_context();
        let req = HandlerRequest {
            exec: ctx.execute(),
            store: &peer.store,
            local_peer: &peer.local_peer,
            caller_capability: ctx.caller_capability(),
            included: &ctx.envelope().included,
            context: Some(&context),
        };
        let dispatch = local_dispatcher(ctx, None);
        let outcome = self.handle_dispatching(ctx.operation(), &req, Some(&dispatch));
        HandlerResult {
            status: outcome.status,
            result: outcome.result,
            included: vec![],
        }
    }
}

/// §4.1 `ctx.dispatch_execute`, over keystone's `HandlerContext::dispatch_execute` (K-5, `rust`
/// only): the same §6.6 resolution, `check_permission` and body selection a wire EXECUTE takes,
/// in-process. A dispatch runs under the apply's provided capability when it has one, else under
/// `ctx.capability` — `default_capability`, which is `None` (the caller's verified capability) for
/// an explicit eval and the handler grant for an entity-native body.
pub(crate) fn local_dispatcher<'c>(
    ctx: &'c HandlerContext<'c>,
    default_capability: Option<Entity>,
) -> impl Fn(DispatchCall) -> (u64, Entity) + Sync + 'c {
    move |call: DispatchCall| {
        let mut local = LocalExecute::new(&call.path, &call.operation, call.params);
        local.resource = call.resource;
        local.capability = call.capability.or_else(|| default_capability.clone());
        let result = ctx.dispatch_execute(local);
        (result.status, result.result)
    }
}

fn params_entity(exec: &Entity) -> Option<Entity> {
    exec.entity_field("params")
}

/// §3.2/§3.3/§3.4: exactly one resource target, or `None`.
fn single_resource_target(exec: &Entity) -> Option<String> {
    let Some(Value::Map(resource)) = exec.field("resource") else {
        return None;
    };
    let targets = resource.iter().find_map(|(k, v)| match (k, v) {
        (Key::Text(t), Value::Array(items)) if t == "targets" => Some(items),
        _ => None,
    })?;
    match targets.as_slice() {
        [Value::Text(only)] => Some(only.clone()),
        _ => None,
    }
}

/// §3.3's `impure_operations` — the audit, verbatim.
fn impure_operations(audit: &SubgraphAudit) -> Value {
    let text_array =
        |items: &[String]| Value::Array(items.iter().map(|s| Value::Text(s.clone())).collect());
    Value::Map(vec![
        (
            Key::Text("read_paths".into()),
            text_array(&audit.read_paths),
        ),
        (
            Key::Text("handler_targets".into()),
            Value::Array(
                audit
                    .handler_targets
                    .iter()
                    .map(|t| {
                        let mut m = vec![(Key::Text("path".into()), Value::Text(t.path.clone()))];
                        if let Some(op) = &t.operation {
                            m.push((Key::Text("operation".into()), Value::Text(op.clone())));
                        }
                        Value::Map(m)
                    })
                    .collect(),
            ),
        ),
        (
            Key::Text("write_paths".into()),
            text_array(&audit.write_paths),
        ),
        (
            Key::Text("data_hashes".into()),
            Value::Array(
                audit
                    .data_hashes
                    .iter()
                    .map(|d| Value::Bytes(d.hash.clone()))
                    .collect(),
            ),
        ),
    ])
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
