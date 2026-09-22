//! COMPUTE — the in-process SDK surface, for the `rust` peer.
//!
//! **The gated path runs through it.** `system/compute:eval` and the H7 evaluator both evaluate
//! through [`ComputeEvaluator`], so the extension is its own instrument on this peer as on the other
//! two. Until keystone landed H1/H7 here (2026-09-12) no wire request could reach this code, and the
//! only instruments were `tests/` and the cross-port gates.
//!
//! # The stack, and why every evaluation runs on its own thread
//!
//! §4.1's evaluator recurses, and §9.3's `max_depth` of 1024 is the bound. On `python` and
//! `typescript` a runaway recursion is a catchable `RecursionError` / `RangeError`. **On this
//! substrate a thread that overflows its stack ABORTS THE PROCESS** — the peer, every connection on
//! it, and every other extension composed into it. So `max_depth` is a liveness bound here, not
//! only a semantic one, and the stack it needs is provisioned rather than hoped for:
//! [`EVAL_STACK_BYTES`] per evaluation, on a scoped thread. `tests/evaluator.rs` drives a
//! 1024-deep non-tail recursion through it as the control.

use std::collections::{BTreeMap, HashSet};
use std::rc::Rc;

use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::{ExecContext, Store};
use entity_core_protocol::value::Value;

use crate::internal::evaluator::{
    as_compute_error, evaluate, is_error, materialize, Binding, Budget, ComputeError, Dispatcher,
    EvalContext, Scope, Val,
};
use crate::types::{BUILTINS_PREFIX, DEFAULT_MAX_DEPTH, DEFAULT_MAX_OPS};

/// §9.3's two peer-wide defaults, as a value rather than as two arguments.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct EvaluatorLimits {
    pub max_operations: u64,
    pub max_depth: u64,
}

/// §9.3's recommended pair.
pub const DEFAULT_LIMITS: EvaluatorLimits = EvaluatorLimits {
    max_operations: DEFAULT_MAX_OPS,
    max_depth: DEFAULT_MAX_DEPTH,
};

/// The stack each evaluation runs on. Reserved address space, not committed memory: the pages
/// are touched only as deep as the recursion actually goes.
///
/// Sized from a measurement, not a guess — see `tests/evaluator.rs`
/// `depth_limit_is_reached_without_overflowing_the_stack`, which drives a 1024-deep non-tail
/// recursion through the debug build the composition ships.
pub const EVAL_STACK_BYTES: usize = 256 * 1024 * 1024;

/// What an evaluation produced. **Exactly one of `value`, `entity` and `error` is `Some`.**
///
/// `value` and `entity` are the MATERIALIZED form, never an in-flight one (§2.3, option α). A
/// genuine null result is `value: Some(Value::Null)`, so unlike `python` there is no ambiguity
/// between "errored" and "evaluated to null" to read around.
#[derive(Clone, Debug)]
pub struct EvalOutcome {
    pub value: Option<Value>,
    pub entity: Option<Entity>,
    pub error: Option<ComputeError>,
    /// Steps actually charged — §4.2's counter.
    pub operations_used: u64,
}

/// `typescript`'s `EvaluateOptions`, and the reason this port has the type where `python` has
/// keyword arguments: Rust has neither keyword nor default arguments, so six optional settings are
/// a struct with `Default` or they are six positional `Option`s. `[sdk_surface].substrate`.
#[derive(Default)]
pub struct EvaluateOptions<'o> {
    /// §3.2's `params.budget`. `None` means the caller did not ask; §5.2's minimum rule applies.
    pub budget: Option<u64>,
    /// §4.2 Tier 0. Default false.
    pub content_store_access: bool,
    /// §4.2 step 1 — the envelope's `included` map.
    pub included: Option<&'o BTreeMap<Vec<u8>, Entity>>,
    /// §4.2 Tier 2 — an installed subgraph's SEALED set. Never the encountered set.
    pub authorized_data_hashes: Option<&'o HashSet<Vec<u8>>>,
    /// §4.1 / §6.3's two path predicates. Default permissive. `Sync` because the evaluation runs on
    /// its own thread.
    pub can_read_path: Option<&'o (dyn Fn(&str) -> bool + Sync)>,
    pub can_write_path: Option<&'o (dyn Fn(&str) -> bool + Sync)>,
}

/// What an entry point inside a dispatched request adds to an evaluation. Empty for every in-process
/// caller of [`ComputeEvaluator::evaluate_at`].
#[derive(Default)]
pub(crate) struct RequestContext<'r> {
    pub capability: Option<&'r Entity>,
    pub dispatch: Option<&'r Dispatcher<'r>>,
    pub bindings: Vec<(String, Binding)>,
    /// §6.8a — the execution context of the dispatch this evaluation is running inside, carried
    /// onto any tree write the evaluation performs (§3.5's `store` builtin, today the only one).
    ///
    /// **`None` is a POSITION, not a missing value.** A write with no context is the AUTONOMOUS
    /// case (`EXTENSION-HISTORY` §2.1: author = the local peer's identity hash), so a request-
    /// driven write that reaches the store without this field is not merely unlabelled — it is
    /// labelled, wrongly, as the peer's own. That is H8's defect, and it is what
    /// `embed.data/bind-carries-context` measures.
    pub exec_context: Option<&'r ExecContext>,
}

/// The evaluator, as an in-process object. One instance per evaluation: it carries the dependency
/// list §7.1 would register, which is scoped to one evaluation.
///
/// Takes the store and the local peer id rather than a peer, matching `../content` and `../history`
/// on this target — a caller already holds `peer.store`, and a test can evaluate against a bare
/// `Store::new()`.
pub struct ComputeEvaluator<'a> {
    store: &'a Store,
    local_peer: &'a str,
    limits: EvaluatorLimits,
    dependencies: Vec<String>,
}

impl<'a> ComputeEvaluator<'a> {
    pub fn new(store: &'a Store, local_peer: &'a str, limits: EvaluatorLimits) -> ComputeEvaluator<'a> {
        ComputeEvaluator {
            store,
            local_peer,
            limits,
            dependencies: Vec::new(),
        }
    }

    /// Paths §7.1 would register as reactive dependencies. Read after an evaluation.
    pub fn dependencies(&self) -> &[String] {
        &self.dependencies
    }

    /// Evaluate `expression`, with `subgraph_root` as the base for `relative: true` paths.
    ///
    /// `subgraph_root` is required because §2.1 gives it two sources — the expression URI for an
    /// explicit eval, `root_expression_path` for a reactive one.
    pub fn evaluate_at(
        &mut self,
        expression: &Entity,
        subgraph_root: &str,
        options: EvaluateOptions<'_>,
    ) -> EvalOutcome {
        self.evaluate_in_request(expression, subgraph_root, options, RequestContext::default())
    }

    /// [`Self::evaluate_at`] from inside a dispatched request: §4.1's `ctx.capability`, its
    /// `dispatch_execute`, and §3.2 E1's pre-populated scope. Crate-private, because a caller able to
    /// pass a dispatcher could dispatch under any capability it names.
    pub(crate) fn evaluate_in_request(
        &mut self,
        expression: &Entity,
        subgraph_root: &str,
        options: EvaluateOptions<'_>,
        request: RequestContext<'_>,
    ) -> EvalOutcome {
        // §5.2's minimum rule: the caller's ask and the peer default, whichever is smaller.
        let operations = match options.budget {
            Some(b) => b.min(self.limits.max_operations),
            None => self.limits.max_operations,
        };
        let depth = self.limits.max_depth;

        let empty_included = BTreeMap::new();
        let empty_sealed = HashSet::new();
        let allow = |_: &str| true;
        let included = options.included.unwrap_or(&empty_included);
        let sealed = options.authorized_data_hashes.unwrap_or(&empty_sealed);
        let can_read: &(dyn Fn(&str) -> bool + Sync) = options.can_read_path.unwrap_or(&allow);
        let can_write: &(dyn Fn(&str) -> bool + Sync) = options.can_write_path.unwrap_or(&allow);
        let store = self.store;
        let local_peer = self.local_peer;
        let content_store_access = options.content_store_access;
        let RequestContext { capability, dispatch, bindings, exec_context } = request;

        let (outcome, dependencies) = std::thread::scope(|s| {
            std::thread::Builder::new()
                .name("compute-eval".into())
                .stack_size(EVAL_STACK_BYTES)
                .spawn_scoped(s, move || {
                    let ctx = EvalContext {
                        store,
                        local_peer,
                        subgraph_root: subgraph_root.to_string(),
                        included,
                        has_content_store_access: content_store_access,
                        authorized_data_hashes: sealed,
                        can_read_path: can_read,
                        can_write_path: can_write,
                        dependencies: Default::default(),
                        encountered: Default::default(),
                        capability,
                        dispatch,
                        exec_context,
                    };
                    let mut initial = Scope::default();
                    for (name, binding) in bindings {
                        let value = match binding {
                            Binding::Data(d) => Val::Data(d),
                            Binding::Entity(e) => Val::Entity(e),
                        };
                        initial.bindings.insert(name, value);
                    }
                    let mut budget = Budget {
                        operations: operations.min(i64::MAX as u64) as i64,
                        depth: depth.min(i64::MAX as u64) as i64,
                    };
                    let out = evaluate(expression, &Rc::new(initial), &mut budget, &ctx);
                    let used = operations.saturating_sub(budget.operations.max(0) as u64);
                    let outcome = if is_error(&out) {
                        EvalOutcome {
                            value: None,
                            entity: None,
                            error: Some(as_compute_error(&out)),
                            operations_used: used,
                        }
                    } else {
                        // §2.3 / option α — THE BOUNDARY. Nothing below is in-flight.
                        match materialize(&out, &ctx) {
                            Val::Entity(e) => EvalOutcome {
                                value: None,
                                entity: Some(e),
                                error: None,
                                operations_used: used,
                            },
                            Val::Data(d) => EvalOutcome {
                                value: Some(d),
                                entity: None,
                                error: None,
                                operations_used: used,
                            },
                            _ => unreachable!("materialize yields an entity or data"),
                        }
                    };
                    (outcome, ctx.dependencies.into_inner())
                })
                .expect("spawn the evaluation thread")
                .join()
                // A panic inside the evaluator is a defect in this crate, not an evaluation
                // outcome, and it is surfaced as one rather than dressed up as a compute/error.
                .expect("the evaluation thread panicked")
        });
        self.dependencies = dependencies;
        outcome
    }
}

/// §6.2's capability check — whether any entry point of this port evaluates WITHOUT narrowing per
/// tree read.
///
/// **`false`, and on this peer for a reason neither other port has.** All three entry points narrow:
/// `system/compute:eval` and §7.2's reactive path as on the other two, AND the H7 evaluator, because
/// this peer's `HandlerContext` carries the HANDLER GRANT (§4.1's authority for an entity-native
/// body) where `typescript`'s `ExpressionRequest` carries no capability at all. So the row that keeps the constant meaningful on `typescript` —
/// "the H7 seam is dispatch-scoped" — is not true here. An in-process caller of
/// [`ComputeEvaluator::evaluate_at`] supplies the predicates in [`EvaluateOptions`] or accepts the
/// documented permissive default.
pub const CAPABILITY_CHECK_IS_DISPATCH_SCOPED: bool = false;

/// §4's override prohibition — **ours to enforce as of v3.29**: `ENTITY-CORE-PROTOCOL` 0.8.2.13
/// withdrew the core `system/*` reservation this rule used to delegate to.
///
/// `Err` rather than a `compute/error`: this is an installation fault in the host program,
/// discovered before the peer serves anything.
pub fn assert_not_builtin_override(pattern: &str) -> Result<(), String> {
    let relative = crate::internal::evaluator::relative_pattern(pattern);
    if relative == BUILTINS_PREFIX || relative.starts_with(&format!("{BUILTINS_PREFIX}/")) {
        return Err(format!(
            "EXTENSION-COMPUTE §4: a handler MUST NOT be registered at {pattern}. The builtin \
             handlers are the cross-peer determinism floor; overriding one makes two peers disagree \
             about what an operation means. (v3.29 — this rule no longer delegates to the withdrawn \
             core system/* reservation.)"
        ));
    }
    Ok(())
}
