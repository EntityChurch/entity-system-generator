//! `entity_compute` — COMPUTE v3.29 for the `rust` keystone peer.
//!
//! **THE PUBLIC SURFACE.** `mod internal` is declared without `pub`, so the evaluator, the install
//! audit and their context types are invisible outside this crate — `error[E0603]`, not a
//! convention. It matters more here than for CONTENT or HISTORY: `evaluate` takes its whole
//! authority as a context, and a caller able to build one could grant itself §4.2 Tier 0 (the
//! evaluator as a content-store oracle) or pass a path predicate that always answers yes.
//! `src/bin/deep_import.rs` is the fixture; `languages/rust/test` requires it to fail with E0603.
//!
//! # The five faces, and the answer this port gives each
//!
//! | face | on this peer | how we know |
//! |---|---|---|
//! | types (§10.2) | **installed** | `Store::bind` is `pub`; 63 core `type_compute_*_match` checks compare the bytes against `entity-core-go`'s own transcription |
//! | handler (§3) | **installed** — `Peer::register_handler` (keystone H1, landed for K-9) | the `compute` category runs through it; `languages/rust/gates/host-seam` scenario 1 measures the install with both controls |
//! | emit consumer (§7.2) | **installed** | `Store::register_tree_consumer`; live on the wire now that `system/compute:install` can reach the engine |
//! | SDK | **installed** — the handler runs THROUGH [`ComputeEvaluator`] | the gated path is the handler |
//! | evaluator (H7) | **installed, OBSERVED** — `Peer::set_expression_evaluator` | read back off the peer after the call; host-seam scenario 5 dispatches an entity-native body through it |
//!
//! Until keystone landed H1/H6/H7/H9 on this peer (their
//! `ROUTING-2026-09-12-a-entity-system-generator-rust-can-install-a-handler-and-h1-status-no-longer-reads-the-wire-probe`)
//! the handler and the evaluator had nowhere to go, and this crate deliberately had no
//! `install_compute` — one call must not mean "installed" on two peers and "partly installed" on a
//! third. With every face installable the reason is gone, so the name is the other ports' name.

pub mod handler;
pub mod sdk;
pub mod types;

/// **NOT `pub`.** This keyword's absence is the boundary. See `internal/mod.rs`.
mod internal;

use std::sync::Arc;

use entity_core_protocol::peer::handler::{
    ExpressionEvaluator, ExpressionRequest, Handler, HandlerContext, HandlerResult, HandlerSpec,
    RegisterError,
};
use entity_core_protocol::peer::store::TreeChangeEvent;
use entity_core_protocol::peer::Peer;
use entity_core_protocol::value::Value;

use internal::evaluator::Binding;

pub use handler::{ComputeHandler, ComputeOutcome, HandlerRequest};
pub use internal::reactive::{deterministic_id, ReactiveEngine};
pub use sdk::{
    assert_not_builtin_override, ComputeEvaluator, EvalOutcome, EvaluateOptions, EvaluatorLimits,
    CAPABILITY_CHECK_IS_DISPATCH_SCOPED, DEFAULT_LIMITS,
};
pub use types::{
    compute_entity, compute_type_defs, compute_type_entities, is_compute_expression,
    is_compute_type, publish_compute_types, ALL_TYPES, APPLY, ARITHMETIC, ASSOC_ARGS,
    BUILTINS_PREFIX, CLOSURE, CODE_AMBIGUOUS_RESOURCE, CODE_BUDGET_EXHAUSTED, CODE_CASCADE_LIMIT,
    CODE_CAST_OUT_OF_RANGE, CODE_COUNT_OUT_OF_RANGE, CODE_DEPTH_EXCEEDED, CODE_DIVISION_BY_ZERO,
    CODE_INDEX_OUT_OF_RANGE, CODE_INSTALLATION_GRANT_INVALID, CODE_INVALID_EXPRESSION,
    CODE_MISSING_ARGUMENT, CODE_NOT_FOUND, CODE_PERMISSION_DENIED, CODE_SCOPE_UNREACHABLE,
    CODE_TYPE_MISMATCH, CODE_UNKNOWN_TYPE, COMPARE, COMPUTE_PATTERN, CONCAT_ARGS, CONSTRUCT,
    CORE_EXPRESSION_TYPES, DEFAULT_MAX_DEPTH, DEFAULT_MAX_OPS, ERROR, FIELD, FILTER_ARGS,
    FOLD_ARGS, GROUP, GROUP_BY_ARGS, IF, INDEX, INLINE_EXPRESSION_TYPES, INSTALL_REQUEST,
    INSTALL_RESULT, LAMBDA, LENGTH, LET, LITERAL, LOGIC, LOOKUP_HASH, LOOKUP_SCOPE, LOOKUP_TREE,
    MAP_ARGS, NUMERIC_CAST, PROCESSES_PREFIX, RANGE_ARGS, RECOMMENDED_MAX_CASCADE_DEPTH, RESULT,
    SCOPE, SCOPE_BINDING, STORE_ARGS, SUBGRAPH,
};

/// What [`install_compute`] installed, so a caller can assert on it.
#[derive(Clone)]
pub struct ComputeInstallation {
    pub pattern: String,
    pub interface_path: String,
    pub type_paths: Vec<String>,
    /// `"installed"` | `"not-observed"` — READ BACK off the peer, never declared. There is no
    /// `"not-installable"` on this target: the seam is a method and always compiles, so the only
    /// way it can fail is a setter that stores nothing, which is what the read-back catches.
    pub evaluator_face: &'static str,
    /// §7's engine — the `emit_consumer` face, and the owner of the dependency index.
    pub engine: Arc<ReactiveEngine>,
    /// §7.1's rebuild count: subgraphs re-registered from `system/compute/processes/*`.
    pub rebuilt: usize,
}

/// Install COMPUTE onto a live peer: the handler, 33 types, the H7 evaluator, and §7's consumer.
///
/// **The order is the other two ports' and it is load-bearing.** `register_handler` binds four
/// §11.6.1 entities and type publication thirty-three more; the consumer is registered LAST so it
/// does not observe them. For COMPUTE that is stronger than hygiene: the consumer WRITES BACK.
///
/// Refuses (keystone H3) when a handler is already bound at [`COMPUTE_PATTERN`] — nothing else is
/// written in that case, because the refusal comes first.
pub fn install_compute(
    peer: &Arc<Peer>,
    limits: EvaluatorLimits,
) -> Result<ComputeInstallation, RegisterError> {
    // §4's override prohibition, before anything is written. As of v3.29 nothing upstream refuses a
    // registration at `system/compute/builtins/*` on our behalf.
    assert_not_builtin_override(COMPUTE_PATTERN).expect("COMPUTE_PATTERN is not a builtin path");

    // ONE engine, TWO halves: §3.3's Phase 4 runs through the handler and §7.2's trigger through the
    // emit bus. The engine holds a `Weak<Peer>`; the peer holds the handler, which holds the engine.
    let engine = Arc::new(ReactiveEngine::new(peer, limits));
    register_for_peer_life(
        peer,
        Arc::new(ComputeHandler::new(Some(engine.clone()), limits)),
    )?;

    let type_paths = publish_compute_types(&peer.store, &peer.local_peer);

    let evaluator: Arc<dyn ExpressionEvaluator> = Arc::new(ComputeExpressionEvaluator { limits });
    peer.set_expression_evaluator(Some(evaluator.clone()));
    // READ BACK, never assume — keystone planted a setter that stores nothing against their own H7.
    let evaluator_face = match peer.expression_evaluator() {
        Some(installed) if Arc::ptr_eq(&installed, &evaluator) => "installed",
        _ => "not-observed",
    };

    let consumer = engine.clone();
    peer.store
        .register_tree_consumer(move |ev: &TreeChangeEvent| consumer.on_tree_change(ev));
    let rebuilt = engine.rebuild();

    Ok(ComputeInstallation {
        pattern: COMPUTE_PATTERN.to_string(),
        interface_path: format!("/{}/system/handler/{COMPUTE_PATTERN}", peer.local_peer),
        type_paths,
        evaluator_face,
        engine,
        rebuilt,
    })
}

/// Install `handler` through the surface keystone's contract CERTIFIES — `Peer::register_handler`
/// (`install.handler`, `install.remove` in `KEYSTONE-PEER-REPORT.json`) — and keep it for the peer's
/// life. `Peer::install_handler` does the same work but is not the binding the report names, and an
/// extension builds on what is certified (AGENTS.md, the keystone peer contract).
///
/// **`detach()` is load-bearing.** The handle unregisters on drop; without it the handler would be
/// gone before the host's `configure` closure returned, and the peer would listen with nothing at
/// the pattern.
fn register_for_peer_life(
    peer: &Arc<Peer>,
    handler: Arc<dyn Handler>,
) -> Result<(), RegisterError> {
    let spec = HandlerSpec::new(handler.pattern(), handler.name()).operations(handler.operations());
    peer.register_handler(spec, move |ctx: &HandlerContext<'_>| handler.handle(ctx))?
        .detach();
    Ok(())
}

/// The H7 evaluator for entity-native handler bodies.
///
/// **Declines anything that is not a compute expression** (`None`), so the peer's own
/// `501 unsupported_expression` stands and evaluators compose. The peer answers the built-in
/// `compute/literal` shape before asking, which is what keeps `core_register_body_binding` out of
/// this code's reach. Private: the seam is the peer's; the object is an implementation detail.
struct ComputeExpressionEvaluator {
    limits: EvaluatorLimits,
}

impl ExpressionEvaluator for ComputeExpressionEvaluator {
    fn evaluate(
        &self,
        request: &ExpressionRequest<'_>,
        ctx: &HandlerContext<'_>,
    ) -> Option<HandlerResult> {
        if !is_compute_expression(&request.expression.typ) {
            return None;
        }
        // §4.1 — "Entity-native dispatch: the handler (HANDLER GRANT authorizes the expression)".
        // Tree reads narrow under it, the F2 dual check uses it as the ceiling, and a
        // `compute/apply` dispatches under it. FAIL CLOSED without one: evaluating under the
        // caller's capability instead would let `capability = lookup/scope("caller_capability")`
        // pass its own ceiling, which is the escape the dual check exists to block.
        let Some(grant) = ctx.handler_grant().cloned() else {
            return Some(HandlerResult::error(
                403,
                "capability_denied",
                Some("entity-native evaluation runs under the handler grant (§4.1) and this handler has none"),
            ));
        };
        let peer = ctx.peer();
        let local = peer.local_peer.clone();
        let can_read = |path: &str| internal::subgraph::path_permitted("get", path, &grant, &local);
        let can_write =
            |path: &str| internal::subgraph::path_permitted("put", path, &grant, &local);
        // §3.2 E1 — the dispatch layer pre-populates `{operation, params, resource,
        // caller_capability}`, which the body reads through `compute/lookup/scope`.
        let null_or = |v: Option<Binding>| v.unwrap_or(Binding::Data(Value::Null));
        let bindings = vec![
            (
                "operation".to_string(),
                Binding::Data(Value::Text(ctx.operation().to_string())),
            ),
            (
                "params".to_string(),
                null_or(ctx.params().map(Binding::Entity)),
            ),
            (
                "resource".to_string(),
                null_or(ctx.resource().cloned().map(Binding::Data)),
            ),
            (
                "caller_capability".to_string(),
                null_or(ctx.caller_capability().cloned().map(Binding::Entity)),
            ),
        ];
        let dispatch = handler::local_dispatcher(ctx, Some(grant.clone()));
        // §6.8a — entity-native evaluation is still a DISPATCHED request, so a `builtins/store`
        // write inside it carries the caller's context. `exec_context()` returns an owned value,
        // so it is bound here rather than called inline: the `RequestContext` borrows it.
        let exec_ctx = ctx.exec_context();
        // A fresh evaluator per dispatch: §4.2 scopes the encountered set to one evaluation.
        let outcome = ComputeEvaluator::new(&peer.store, &peer.local_peer, self.limits)
            .evaluate_in_request(
                request.expression,
                request.expression_path,
                EvaluateOptions {
                    can_read_path: Some(&can_read),
                    can_write_path: Some(&can_write),
                    ..Default::default()
                },
                sdk::RequestContext {
                    capability: Some(&grant),
                    dispatch: Some(&dispatch),
                    bindings,
                    exec_context: Some(&exec_ctx),
                },
            );
        Some(HandlerResult::ok(unwrap_at_dispatch_boundary(outcome)))
    }
}

/// §3.2 E1 — "the result is unwrapped at the dispatch boundary": `compute/result` → its value;
/// `compute/error` → the result entity at 200 (F10); a bare primitive → `{type: "primitive/any",
/// data}`; an entity → as-is.
///
/// NOTE the peer's own `compute/literal` floor answers BEFORE this evaluator and returns a
/// `compute/result` entity rather than unwrapping — keystone's, routed; it is why the oracle's
/// `entity_native.result_unwrapped` (a literal body) cannot pass on any keystone peer whatever we do.
fn unwrap_at_dispatch_boundary(outcome: EvalOutcome) -> entity_core_protocol::peer::model::Entity {
    use entity_core_protocol::peer::model::Entity;
    if let Some(error) = outcome.error {
        return error.to_entity();
    }
    let value = match outcome.entity {
        Some(e) if e.typ == RESULT => e.field("value").cloned().unwrap_or(Value::Null),
        Some(e) => return e,
        None => outcome.value.unwrap_or(Value::Null),
    };
    Entity::make("primitive/any", value)
}
