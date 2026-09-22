//! COMPUTE §4 — the evaluation algorithm, for the `rust` peer.
//!
//! **Behind the crate boundary.** `lib.rs` declares `mod internal;` without `pub`, so nothing in
//! this file is reachable from outside the crate — `error[E0603]`, enforced by rustc. That matters
//! more for this extension than for either of the first two: [`evaluate`] takes its whole
//! authority as an [`EvalContext`], so a caller able to build one with
//! `has_content_store_access = true` would hold §4.2 Tier 0 — the evaluator as the content-store
//! oracle §4.2 exists to prevent.
//!
//! # What this file is faithful to
//!
//! §4.1's pseudocode, clause for clause, with the trampoline, the depth accounting and the
//! `is_error` guard placement preserved exactly. It is a port of
//! `../../../../python/extensions/compute/_internal/evaluator.py`, re-read against the spec at every
//! arm rather than transcribed from that file (L18), and the places the two differ are the
//! substrate's, listed below.
//!
//!  - **`is_error` is KIND-based, not outcome-based** (§4.1's opening MUST).
//!  - **The budget charges `evaluate()` steps and nothing else** (§4.2). `resolve()` costs zero.
//!  - **Tail calls do not consume depth but DO decrement the budget** (§10.1).
//!
//! The four declared deviations from the spec text are the other ports': sixteen-type membership
//! predicates (`../types.rs`), the normative arithmetic helpers over §2.2's prose, an arm for the
//! §2.3 VALUE TYPES (SA-1), and the in-flight [`Constructed`] value (v3.19c option α).
//!
//! **`compute/apply` HANDLER MODE is implemented on this port and on no other**, because this is the
//! one peer with a re-entrant local dispatch: keystone's `HandlerContext::dispatch_execute`, landed
//! for K-5 on `rust` only. The evaluator does not know the peer; it calls [`EvalContext::dispatch`],
//! which the handler and the H7 evaluator build from their `HandlerContext`. §7.2's reactive path
//! runs from an emit consumer with no request context, so it has no dispatcher and handler mode
//! there answers `invalid_expression` naming that — `[assumptions].apply_handler_mode`.
//!
//! **Not implemented, named so the absence is not mistaken for an oversight:** §4.6 memoization,
//! and §5.3's shared in-process budget pool — a dispatched evaluation starts its own budget.
//!
//! # Where the substrate makes this port differ from `python`'s
//!
//!  1. **THE VALUE MODEL IS TAGGED**, like `typescript`'s. `Value::Bool`, `UInt`, `NInt` and `Float`
//!     are distinct variants, so `bool` cannot be mistaken for an integer and `eq(true, 1)` is false
//!     by construction. Three of `python`'s seven native-semantics risks do not exist here.
//!  2. **INTEGERS ARE SPLIT BY SIGN.** `UInt(u64)` and `NInt(n)` (value `-1 - n`) together cover
//!     `[-2^64, 2^64)`. Every integer operation lifts to `i128`, which holds any single operand
//!     exactly, and `mul` computes its bit pattern with `u64::wrapping_mul` because the product of
//!     two `u64`s overflows `i128`.
//!  3. **THE HOST'S OPERATORS AGREE WITH §4.1 WHERE `python`'s DID NOT.** Rust's integer `%` and `/`
//!     truncate toward zero, and `f64` division by zero is IEEE-754. No helper is needed to
//!     override the host; the helpers below exist so the rule is visible, not to correct it.
//!  4. **A NATIVE CAST SATURATES SILENTLY.** `f64 as i64` clamps and maps NaN to 0, which is the
//!     opposite of §2.2 rule 11's `cast_out_of_range`. [`numeric_cast`] range-checks in `f64` before
//!     any `as`.
//!  5. **STACK OVERFLOW IS NOT CATCHABLE.** `python` raises `RecursionError` and `typescript` a
//!     `RangeError`; a Rust thread that overflows its stack aborts the whole process. `max_depth`
//!     (§9.3, 1024) is therefore a liveness bound for the PEER here, not only a semantic one — see
//!     `sdk.rs`, which runs every evaluation on a thread with a stack sized for it.
//!  6. **THE PEER'S `canonicalize` DOES NOT REFUSE `./x`, `../x` OR `*/x`.** `python`'s peer returns
//!     `None` for them and that port answers `invalid_expression`; this peer prefixes them like any
//!     relative path, which is `typescript`'s behaviour. We call the peer's primitive either way
//!     (D12), so the three ports now split two against one by what their PEER does.

use std::cell::RefCell;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::rc::Rc;

use entity_core_protocol::cbor;
use entity_core_protocol::peer::capability;
use entity_core_protocol::peer::model::Entity;
use entity_core_protocol::peer::store::{ExecContext, Store};
use entity_core_protocol::value::{Key, Value};

use super::subgraph::grant_covers;
use crate::types::{
    is_compute_expression, is_compute_type, APPLY, ARITHMETIC, BUILTINS_PREFIX, CLOSURE,
    CODE_BUDGET_EXHAUSTED, CODE_CASCADE_LIMIT, CODE_CAST_OUT_OF_RANGE, CODE_COUNT_OUT_OF_RANGE,
    CODE_DEPTH_EXCEEDED, CODE_DIVISION_BY_ZERO, CODE_INDEX_OUT_OF_RANGE, CODE_INVALID_EXPRESSION,
    CODE_MISSING_ARGUMENT, CODE_NOT_FOUND, CODE_PERMISSION_DENIED, CODE_SCOPE_UNREACHABLE,
    CODE_TYPE_MISMATCH, CODE_UNKNOWN_TYPE, COMPARE, CONSTRUCT, ERROR, FIELD, GROUP, IF, INDEX,
    LAMBDA, LENGTH, LET, LITERAL, LOGIC, LOOKUP_HASH, LOOKUP_SCOPE, LOOKUP_TREE, NUMERIC_CAST,
    RESULT, SCOPE,
};

/// The §1.2 `system/hash` wire width: one format byte plus a 32-byte digest.
pub(crate) const CONTENT_HASH_LENGTH: usize = 33;

/// §3.5's *"an `n` exceeding the maximum representable array length"* for `range`.
///
/// **IMPLEMENTATION-DEFINED, AND THIS IS THE THIRD VALUE.** §3.5 pins the code and the
/// refuse-not-clamp rule and leaves the bound open (A-26, routed). `typescript` uses V8's
/// `2^32 - 2`, `python` uses `sys.maxsize`. This runtime's answer is the largest `Vec<Value>` a
/// `Layout` can describe: `isize::MAX` bytes divided by the element size. A larger `n` cannot be
/// allocated at all; a smaller one that exceeds free memory ABORTS the process on allocation
/// failure, which `[substrate.native_value_model]` records.
pub(crate) fn max_array_length() -> i128 {
    (isize::MAX as usize / std::mem::size_of::<Value>()) as i128
}

// ── the carriers ──────────────────────────────────────────────────────────────────────

/// §2.4 — a `compute/error`, built with `code` ONLY.
///
/// `detail` is an in-flight diagnostic the codec never sees. `message`, `at` and `expression` are
/// declared by the type and never materialized (v3.26): the moment one is written into the tree
/// or a contained collection position, the containing bytes fork across conformant peers.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ComputeError {
    pub code: String,
    pub detail: String,
}

impl ComputeError {
    pub(crate) fn new(code: &str, detail: impl Into<String>) -> ComputeError {
        ComputeError {
            code: code.to_string(),
            detail: detail.into(),
        }
    }

    /// The materialized form — `code` only, per §2.4.
    pub fn to_entity(&self) -> Entity {
        Entity::make(
            ERROR,
            Value::Map(vec![(
                Key::Text("code".into()),
                Value::Text(self.code.clone()),
            )]),
        )
    }
}

/// A constructed entity that has not crossed a materialization boundary yet (§2.3, option α).
///
/// `entity` is the bare materialized form — the normative one, and the M1 hash gate's subject.
/// `fields` is the in-flight typed form that lets `field(field(construct(...), 'inner'), 'x')`
/// compose. The bare form is built EAGERLY so the M1 hash has exactly one code path.
#[derive(Clone, Debug)]
pub(crate) struct Constructed {
    pub entity: Entity,
    pub fields: BTreeMap<String, Val>,
}

/// An evaluation value.
///
/// `Data` is an ECF value that is not entity-kinded — including a bare `system/hash`, which is a
/// byte string and is NOT followed implicitly (§2.3). `Entity` and `Constructed` are
/// entity-KINDED, the distinction §2.3 N3 draws by kind and never by shape. `Error` is a minted
/// in-flight error; a stored `compute/error` reached by evaluation is an `Entity` and is still an
/// error for every purpose here, because [`is_error`] is kind-based.
#[derive(Clone, Debug)]
pub(crate) enum Val {
    Data(Value),
    Entity(Entity),
    Constructed(Rc<Constructed>),
    Error(ComputeError),
}

/// §4.3 — a flat name → value map, copied on `let` and on closure apply.
#[derive(Clone, Debug, Default)]
pub(crate) struct Scope {
    pub bindings: HashMap<String, Val>,
}

/// §5.1 — the two counters, mutated in place exactly as §4.1's pseudocode does.
#[derive(Clone, Copy, Debug)]
pub(crate) struct Budget {
    pub operations: i64,
    pub depth: i64,
}

/// §4.1's `ctx.dispatch_execute(path, operation, resource, params, capability)`, as data. The
/// dispatcher answers `(status, result entity)`.
pub(crate) struct DispatchCall {
    pub path: String,
    pub operation: String,
    pub resource: Option<Value>,
    pub params: Entity,
    /// `None` dispatches under `ctx.capability`; `Some` is the §2.1 voluntary restriction.
    pub capability: Option<Entity>,
}

/// The dispatcher an entry point hands the evaluator. `Sync` because evaluation runs on its own
/// thread (`sdk.rs`).
pub(crate) type Dispatcher<'a> = dyn Fn(DispatchCall) -> (u64, Entity) + Sync + 'a;

/// A scope binding an entry point pre-populates (§3.2 E1's `{operation, params, resource,
/// caller_capability}`). Not a [`Val`], because a `Val` may hold an `Rc` and bindings cross onto the
/// evaluation thread.
pub(crate) enum Binding {
    Data(Value),
    Entity(Entity),
}

/// §4.1's `ctx`. Every field is something the evaluator READS; nothing is derived inside.
pub(crate) struct EvalContext<'a> {
    pub store: &'a Store,
    pub local_peer: &'a str,
    /// §2.1 — the root a `relative: true` path resolves against.
    pub subgraph_root: String,
    /// §4.2 step 1 — the envelope's pre-authorized `included` map, keyed by content hash.
    pub included: &'a BTreeMap<Vec<u8>, Entity>,
    /// §4.2 Tier 0.
    pub has_content_store_access: bool,
    /// §4.2 Tier 2 — an installed subgraph's SEALED set.
    pub authorized_data_hashes: &'a HashSet<Vec<u8>>,
    /// §4.1 — `check_path_permission("get", path, ...)`.
    pub can_read_path: &'a dyn Fn(&str) -> bool,
    /// §6.3 — the `store` builtin's write check. Separate from the read predicate because §6.3 gives
    /// the two different authorities.
    pub can_write_path: &'a dyn Fn(&str) -> bool,
    /// §7.1 — paths a reactive install would register.
    pub dependencies: RefCell<Vec<String>>,
    /// §4.4 / §4.3 N6 — hashes written or read during this evaluation.
    pub encountered: RefCell<HashSet<Vec<u8>>>,
    /// §4.1 `ctx.capability` — the F2 dual check's ceiling. `None` skips the ceiling half, as the
    /// reference does for a context with no capability; the provided capability is still checked.
    pub capability: Option<&'a Entity>,
    /// §4.1 `ctx.dispatch_execute`. `None` on a path with no request context (§7.2 reactive).
    pub dispatch: Option<&'a Dispatcher<'a>>,
    /// §6.8a — the execution context to carry onto a tree write this evaluation performs. See
    /// [`crate::sdk::RequestContext::exec_context`]: `None` is the AUTONOMOUS position, not a
    /// missing value.
    pub exec_context: Option<&'a ExecContext>,
}

impl<'a> EvalContext<'a> {
    fn register_dependency(&self, path: &str) {
        let mut deps = self.dependencies.borrow_mut();
        if !deps.iter().any(|p| p == path) {
            deps.push(path.to_string());
        }
    }

    fn mark_encountered(&self, hash: &[u8]) {
        self.encountered.borrow_mut().insert(hash.to_vec());
    }
}

/// §4.1's trampoline token, plus the ordinary return. Never escapes [`evaluate`].
enum Step {
    Done(Val),
    Tail(Entity, Rc<Scope>),
}

/// `Err` is a structurally malformed expression (a required field absent or the wrong ECF type),
/// caught at the top of [`evaluate_inner`] and returned as `invalid_expression` at status 200 —
/// `python`'s disposition, which §2.4/F10 makes the spec-faithful one.
type Stepped = Result<Step, ComputeError>;

fn err(code: &str, detail: impl Into<String>) -> Val {
    Val::Error(ComputeError::new(code, detail))
}

fn done(v: Val) -> Stepped {
    Ok(Step::Done(v))
}

fn fail(code: &str, detail: impl Into<String>) -> Stepped {
    Ok(Step::Done(err(code, detail)))
}

// ── kind tests ────────────────────────────────────────────────────────────────────────

/// Is this value entity-KINDED? §2.3 N3's rule as a variant test, with no shape sniff.
fn is_entity_like(v: &Val) -> bool {
    matches!(v, Val::Entity(_) | Val::Constructed(_))
}

fn int_of(v: &Value) -> Option<i128> {
    match v {
        Value::UInt(u) => Some(*u as i128),
        Value::NInt(n) => Some(-1 - (*n as i128)),
        _ => None,
    }
}

fn val_int(v: &Val) -> Option<i128> {
    match v {
        Val::Data(d) => int_of(d),
        _ => None,
    }
}

fn val_float(v: &Val) -> Option<f64> {
    match v {
        Val::Data(Value::Float(f)) => Some(*f),
        _ => None,
    }
}

fn is_int(v: &Val) -> bool {
    val_int(v).is_some()
}

fn is_float(v: &Val) -> bool {
    val_float(v).is_some()
}

fn is_numeric(v: &Val) -> bool {
    is_int(v) || is_float(v)
}

fn val_text(v: &Val) -> Option<&str> {
    match v {
        Val::Data(Value::Text(s)) => Some(s.as_str()),
        _ => None,
    }
}

fn val_array(v: &Val) -> Option<&Vec<Value>> {
    match v {
        Val::Data(Value::Array(items)) => Some(items),
        _ => None,
    }
}

/// `to_float(value)` — §4.1's `ieee754_convert`. `i128 as f64` rounds to nearest, ties to even.
fn to_float(v: &Val) -> f64 {
    if let Some(f) = val_float(v) {
        return f;
    }
    match val_int(v) {
        Some(i) => i as f64,
        None => f64::NAN,
    }
}

/// An integer back into the ECF value tree. `v` MUST be in `[-2^64, 2^64)`.
fn value_of_int(v: i128) -> Value {
    if v >= 0 {
        Value::UInt(v as u64)
    } else {
        Value::NInt((-1 - v) as u64)
    }
}

/// §4.1 — entity identity is the MATERIALIZED content hash, never the in-flight form.
fn entity_identity(v: &Val) -> Option<&[u8]> {
    match v {
        Val::Entity(e) => Some(&e.hash),
        Val::Constructed(c) => Some(&c.entity.hash),
        _ => None,
    }
}

/// §2.3 — the four VALUE types. Not expressions; SA-1 returns them unchanged.
const VALUE_TYPES: [&str; 4] = [CLOSURE, SCOPE, RESULT, ERROR];

/// §4.1's `is_error(v)` — **kind-based**. True for a minted error AND for an entity whose type is
/// `compute/error`, however it was reached.
pub(crate) fn is_error(v: &Val) -> bool {
    match v {
        Val::Error(_) => true,
        Val::Entity(e) => e.typ == ERROR,
        Val::Constructed(c) => c.entity.typ == ERROR,
        Val::Data(_) => false,
    }
}

/// Narrow an `is_error`-true value to a [`ComputeError`], reading `code` off a stored one.
pub(crate) fn as_compute_error(v: &Val) -> ComputeError {
    match v {
        Val::Error(e) => e.clone(),
        other => {
            let entity = match other {
                Val::Entity(e) => Some(e),
                Val::Constructed(c) => Some(&c.entity),
                _ => None,
            };
            let code = entity
                .and_then(|e| e.text_field("code"))
                .unwrap_or(CODE_INVALID_EXPRESSION);
            ComputeError::new(code, "evaluated to a stored compute/error")
        }
    }
}

// ── field readers ─────────────────────────────────────────────────────────────────────

fn malformed(entity: &Entity, what: &str, key: &str) -> ComputeError {
    ComputeError::new(
        CODE_INVALID_EXPRESSION,
        format!("{} requires {what} `{key}`", entity.typ),
    )
}

fn req_text<'e>(entity: &'e Entity, key: &str) -> Result<&'e str, ComputeError> {
    entity
        .text_field(key)
        .ok_or_else(|| malformed(entity, "text", key))
}

fn req_bytes<'e>(entity: &'e Entity, key: &str) -> Result<&'e [u8], ComputeError> {
    entity
        .bytes_field(key)
        .ok_or_else(|| malformed(entity, "hash", key))
}

fn req_list<'e>(entity: &'e Entity, key: &str) -> Result<&'e Vec<Value>, ComputeError> {
    match entity.field(key) {
        Some(Value::Array(items)) => Ok(items),
        _ => Err(malformed(entity, "array", key)),
    }
}

fn opt_bool(entity: &Entity, key: &str) -> bool {
    matches!(entity.field(key), Some(Value::Bool(true)))
}

fn map_get_text<'v>(map: &'v Value, key: &str) -> Option<&'v Value> {
    match map {
        Value::Map(entries) => entries.iter().find_map(|(k, v)| match k {
            Key::Text(t) if t == key => Some(v),
            _ => None,
        }),
        _ => None,
    }
}

// ── materialization ───────────────────────────────────────────────────────────────────

/// §2.3 SA-1 / §4.4 — bring a value to its materialized form, storing what it references.
///
/// The call sites are §2.3 N1's three placement boundaries plus the evaluator's own exit. One
/// function, so the bare form cannot be derived twice.
pub(crate) fn materialize(value: &Val, ctx: &EvalContext) -> Val {
    let entity = match value {
        Val::Constructed(c) => c.entity.clone(),
        Val::Entity(e) => e.clone(),
        other => return other.clone(),
    };
    ctx.store.put_entity(&entity);
    ctx.mark_encountered(&entity.hash);
    Val::Entity(entity)
}

fn materialized_hash(value: &Val, ctx: &EvalContext) -> Vec<u8> {
    match materialize(value, ctx) {
        Val::Entity(e) => e.hash,
        _ => unreachable!("materialized_hash is only called on entity-like values"),
    }
}

// ── evaluate ──────────────────────────────────────────────────────────────────────────

/// §4.1 `evaluate` — the depth frame, the budget charge, and the trampoline.
///
/// The three `depth` mutations are where §4.1 puts them, including the one that is easy to miss:
/// **the budget-exhaustion path restores the depth frame before returning**.
pub(crate) fn evaluate(
    entity: &Entity,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Val {
    if budget.depth <= 0 {
        return err(CODE_DEPTH_EXCEEDED, "Maximum evaluation depth exceeded");
    }
    budget.depth -= 1;

    let mut current = entity.clone();
    let mut current_scope = scope.clone();

    loop {
        budget.operations -= 1;
        if budget.operations <= 0 {
            budget.depth += 1;
            return err(CODE_BUDGET_EXHAUSTED, "Computation budget exhausted");
        }

        match evaluate_inner(&current, &current_scope, budget, ctx) {
            Step::Tail(next, next_scope) => {
                current = next;
                current_scope = next_scope;
            }
            Step::Done(result) => {
                budget.depth += 1;
                return result;
            }
        }
    }
}

fn evaluate_inner(
    entity: &Entity,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Step {
    match dispatch(entity, scope, budget, ctx) {
        Ok(step) => step,
        Err(malformed) => Step::Done(Val::Error(malformed)),
    }
}

/// The short-circuit the `python` port spells `if is_error(target): return target`, for a RESOLVED
/// target. A resolution failure is a minted error; a target that resolves to a stored
/// `compute/error` is also an error by §4.1's kind rule and short-circuits BEFORE it is evaluated.
///
/// Not used at every resolution site, and the exceptions are deliberate: operand pairs, builtin
/// args and a closure body applied to in-hand values test only for a minted error, so a stored
/// `compute/error` there is evaluated (SA-1 returns it unchanged, one step) and then caught. That is
/// one budget step of difference on a corner nothing scores, kept identical to the other ports.
macro_rules! resolved {
    ($hash:expr, $ctx:expr, $label:expr) => {
        match resolve_or_error($hash, $ctx, $label) {
            Err(e) => return done(Val::Error(e)),
            Ok(t) if t.typ == ERROR => return done(Val::Entity(t)),
            Ok(t) => t,
        }
    };
}

/// Evaluate and short-circuit on any error value, returning it unchanged.
macro_rules! evaluated {
    ($target:expr, $scope:expr, $budget:expr, $ctx:expr) => {{
        let v = evaluate(&$target, $scope, $budget, $ctx);
        if is_error(&v) {
            return done(v);
        }
        v
    }};
}

fn dispatch(entity: &Entity, scope: &Rc<Scope>, budget: &mut Budget, ctx: &EvalContext) -> Stepped {
    let kind = entity.typ.as_str();

    match kind {
        LITERAL => done(literal_value(entity)),

        LOOKUP_SCOPE => {
            let name = req_text(entity, "name")?;
            match scope.bindings.get(name) {
                Some(v) => done(v.clone()),
                None => fail(CODE_NOT_FOUND, format!("No scope binding: {name}")),
            }
        }

        LOOKUP_TREE => {
            let raw = req_text(entity, "path")?;
            let path = if opt_bool(entity, "relative") {
                clean_path(&format!("{}/{raw}", ctx.subgraph_root))
            } else {
                canonicalize_path(raw, ctx.local_peer)
            };
            // §6.2 — the capability check BEFORE the read and before the dependency registration,
            // so an unauthorized path does not leak its existence through a registered dependency.
            if !(ctx.can_read_path)(&path) {
                return fail(
                    CODE_PERMISSION_DENIED,
                    format!("Capability does not cover tree read: {path}"),
                );
            }
            // §7.1 — A SENTINEL IS NOT A PATH, so it does not become a reactive dependency.
            // Since keystone's 0.8.2.20 work `capability::canonicalize` is TOTAL and returns
            // `NEVER_MATCH` for the §1.4 reserved forms (`./x`, `../x`, `*/x`) instead of
            // prefixing them. That value is "unreachable as a canonical path by CONSTRUCTION"
            // (their comment), so registering it would mean "re-evaluate when this path
            // changes" about a path that cannot change — and every reserved-form lookup in
            // every subgraph would share the one key, which is cross-talk rather than a
            // dependency. The peer's own constant, never a copy of the string: the whole
            // failure this avoids is our spelling drifting from theirs.
            if path != capability::NEVER_MATCH {
                ctx.register_dependency(&path);
            }
            match ctx.store.get_at(&path) {
                None => fail(CODE_NOT_FOUND, format!("No entity at path: {path}")),
                // §2.1's spreadsheet semantic: a stored EXPRESSION evaluates; a stored value —
                // including a compute/closure — is returned as-is.
                Some(found) if is_compute_expression(&found.typ) => {
                    Ok(Step::Tail(found, scope.clone()))
                }
                Some(found) => done(Val::Entity(found)),
            }
        }

        LOOKUP_HASH => {
            let target = resolved!(req_bytes(entity, "hash")?, ctx, "hash lookup");
            if is_compute_expression(&target.typ) {
                return Ok(Step::Tail(target, scope.clone()));
            }
            done(Val::Entity(target))
        }

        APPLY => eval_apply(entity, scope, budget, ctx),

        IF => {
            let cond_target = resolved!(req_bytes(entity, "condition")?, ctx, "if condition");
            let condition = evaluated!(cond_target, scope, budget, ctx);
            if truthy(&condition) {
                let then_target = resolved!(req_bytes(entity, "then")?, ctx, "if then");
                return Ok(Step::Tail(then_target, scope.clone()));
            }
            if let Some(else_ref) = entity.bytes_field("else") {
                let else_target = resolved!(else_ref, ctx, "if else");
                return Ok(Step::Tail(else_target, scope.clone()));
            }
            // §4.1 returns null explicitly for a falsy `if` with no else. Not an error.
            done(Val::Data(Value::Null))
        }

        LET => {
            let mut new_scope: Scope = (**scope).clone();
            for binding in req_list(entity, "bindings")? {
                if !matches!(binding, Value::Map(_)) {
                    return fail(CODE_INVALID_EXPRESSION, "compute/let binding is not a map");
                }
                let name = match map_get_text(binding, "name") {
                    Some(Value::Text(n)) => n.clone(),
                    _ => {
                        return fail(
                            CODE_INVALID_EXPRESSION,
                            "compute/let binding needs {name, value}",
                        )
                    }
                };
                let value_ref = match map_get_text(binding, "value") {
                    Some(Value::Bytes(b)) => b.clone(),
                    _ => {
                        return fail(
                            CODE_INVALID_EXPRESSION,
                            "compute/let binding needs {name, value}",
                        )
                    }
                };
                let value_target = resolved!(&value_ref, ctx, &format!("let binding {name}"));
                // SEQUENTIAL, in the scope being built — §4.1 calls it Scheme's `let*`. The snapshot
                // is taken per binding, which is observably the same as mutating one map: nothing
                // evaluated here outlives the call except by capture, and capture serializes.
                let snapshot = Rc::new(new_scope.clone());
                let value = evaluated!(value_target, &snapshot, budget, ctx);
                new_scope.bindings.insert(name, value);
            }
            let body_target = resolved!(req_bytes(entity, "body")?, ctx, "let body");
            Ok(Step::Tail(body_target, Rc::new(new_scope)))
        }

        LAMBDA => {
            // Capture and produce a closure. The body is NOT evaluated.
            let body_hash = req_bytes(entity, "body")?.to_vec();
            let env_hash = capture_scope(scope, ctx);
            let params = req_list(entity, "params")?.clone();
            let mut data = vec![
                (Key::Text("params".into()), Value::Array(params)),
                (Key::Text("body".into()), Value::Bytes(body_hash)),
            ];
            if let Some(env) = env_hash {
                data.push((Key::Text("env".into()), Value::Bytes(env)));
            }
            done(Val::Entity(Entity::make(CLOSURE, Value::Map(data))))
        }

        ARITHMETIC => {
            let (left, right) = (req_bytes(entity, "left")?, req_bytes(entity, "right")?);
            let ops = match eval_operand_pair(left, right, scope, budget, ctx) {
                Ok(ops) => ops,
                Err(e) => return done(Val::Error(e)),
            };
            done(apply_arithmetic(req_text(entity, "op")?, &ops))
        }

        COMPARE => {
            let (left, right) = (req_bytes(entity, "left")?, req_bytes(entity, "right")?);
            let ops = match eval_operand_pair(left, right, scope, budget, ctx) {
                Ok(ops) => ops,
                Err(e) => return done(Val::Error(e)),
            };
            done(apply_compare(req_text(entity, "op")?, &ops))
        }

        LOGIC => {
            let op = req_text(entity, "op")?;
            let left = req_bytes(entity, "left")?;
            let right = entity.bytes_field("right");
            apply_logic(op, left, right, scope, budget, ctx)
        }

        FIELD => {
            let name = req_text(entity, "name")?;
            let target_ref = resolved!(req_bytes(entity, "entity")?, ctx, "field target");
            let target = evaluated!(target_ref, scope, budget, ctx);
            done(navigate_field(&target, name))
        }

        INDEX => {
            let arr_ref = resolved!(req_bytes(entity, "array")?, ctx, "index array");
            let arr = evaluated!(arr_ref, scope, budget, ctx);
            let idx_ref = resolved!(req_bytes(entity, "index")?, ctx, "index index");
            let idx = evaluated!(idx_ref, scope, budget, ctx);
            done(index_into(&arr, &idx))
        }

        LENGTH => {
            let arr_ref = resolved!(req_bytes(entity, "array")?, ctx, "length array");
            let arr = evaluated!(arr_ref, scope, budget, ctx);
            done(length_of(&arr))
        }

        NUMERIC_CAST => {
            let val_ref = resolved!(req_bytes(entity, "value")?, ctx, "numeric-cast value");
            let value = evaluated!(val_ref, scope, budget, ctx);
            done(numeric_cast(&value, req_text(entity, "to_type")?))
        }

        CONSTRUCT => {
            let mut fields: Vec<(String, Vec<u8>)> = Vec::new();
            if let Some(Value::Map(entries)) = entity.field("fields") {
                for (k, v) in entries {
                    if let (Key::Text(name), Value::Bytes(h)) = (k, v) {
                        fields.push((name.clone(), h.clone()));
                    }
                }
            }
            let entity_type = req_text(entity, "entity_type")?;
            done(construct_from(entity_type, fields, scope, budget, ctx))
        }

        // §2.3 SA-1 — A VALUE-TYPE ENTITY EVALUATES TO ITSELF. At the fallthrough, because SA-1
        // generalizes the lookup/hash rule rather than naming four types.
        _ if VALUE_TYPES.contains(&kind) => done(Val::Entity(entity.clone())),

        _ => fail(CODE_UNKNOWN_TYPE, format!("Unknown compute type: {kind}")),
    }
}

/// `compute/literal`'s `value`, distinguishing a stored ECF null (a VALUE, §4.5) from absence.
fn literal_value(entity: &Entity) -> Val {
    if !matches!(entity.data, Value::Map(_)) {
        return err(CODE_INVALID_EXPRESSION, "compute/literal has no data map");
    }
    match map_get_text(&entity.data, "value") {
        Some(v) => Val::Data(v.clone()),
        None => err(
            CODE_INVALID_EXPRESSION,
            "compute/literal has no `value` field",
        ),
    }
}

// ── apply ─────────────────────────────────────────────────────────────────────────────

/// §4.1's `compute/apply`. **Closure mode and the §3.5 builtins only** — handler mode needs a
/// re-entrant local dispatch no peer exposes (K-5), and shipping half of it runs WIDER than the
/// caller asked, because the F2 dual check only ever narrows.
fn eval_apply(
    entity: &Entity,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Stepped {
    // §2.1 [MUST] — "either `path` or `fn`, not both and not neither". §4.1's pseudocode tests
    // `path` first and would silently take handler mode; the prose MUST is the rule, so a shape
    // carrying both is refused before either mode is entered (routed: the listing omits it).
    if entity.field("path").is_some() && entity.field("fn").is_some() {
        return fail(
            CODE_INVALID_EXPRESSION,
            "compute/apply MUST have either path or fn, not both",
        );
    }
    if let Some(path) = entity.text_field("path") {
        let has_capability = entity.bytes_field("capability").is_some();
        let has_resource = entity.bytes_field("resource").is_some();
        let builtin = builtin_name(path);

        // §2.1 Q23 — SHAPE CHECK, BEFORE ANY RESOLUTION (normative).
        if builtin.is_some() && (has_capability || has_resource) {
            return fail(
                CODE_INVALID_EXPRESSION,
                "compute/apply on a builtin path MUST NOT carry capability or resource",
            );
        }
        let operation = match entity.text_field("operation") {
            Some(op) => op,
            None => {
                return fail(
                    CODE_INVALID_EXPRESSION,
                    "compute/apply handler mode requires operation",
                )
            }
        };
        // F5 — a capability override without a resource cannot be dual-checked.
        if has_capability && !has_resource {
            return fail(
                CODE_INVALID_EXPRESSION,
                "compute/apply with capability field MUST also have resource field",
            );
        }
        if let Some(name) = builtin {
            if operation != "eval" {
                return fail(
                    CODE_INVALID_EXPRESSION,
                    format!("§3.5: a builtin's only operation is `eval`, got: {operation}"),
                );
            }
            return done(eval_builtin(&name, &arg_hashes(entity), scope, budget, ctx));
        }
        return eval_apply_handler(entity, path, operation, scope, budget, ctx);
    }

    if let Some(fn_ref) = entity.bytes_field("fn") {
        let fn_target = resolved!(fn_ref, ctx, "closure fn");
        let fn_value = evaluated!(fn_target, scope, budget, ctx);
        let closure = match fn_value {
            Val::Entity(e) if e.typ == CLOSURE => e,
            _ => return fail(CODE_TYPE_MISMATCH, "Apply target is not a closure"),
        };

        let mut new_scope = match load_scope(closure.bytes_field("env"), ctx) {
            Ok(s) => s,
            Err(e) => return done(Val::Error(e)),
        };
        let arg_map = arg_hashes(entity);

        // Over the CLOSURE'S PARAMS, not the supplied args — §4.1's loop. A missing argument is
        // `missing_argument`, an extra one is ignored.
        for raw_param in req_list(&closure, "params")? {
            let param = param_name(raw_param);
            let arg_hash = match arg_map.get(&param) {
                Some(h) => h.clone(),
                None => return fail(CODE_MISSING_ARGUMENT, format!("Missing argument: {param}")),
            };
            let arg_target = resolved!(&arg_hash, ctx, &format!("closure arg {param}"));
            // Evaluated in the CALLER's scope, bound into the CLOSURE's.
            let arg = evaluated!(arg_target, scope, budget, ctx);
            new_scope.bindings.insert(param, arg);
        }

        let body_target = resolved!(req_bytes(&closure, "body")?, ctx, "closure body");
        return Ok(Step::Tail(body_target, Rc::new(new_scope)));
    }

    fail(CODE_INVALID_EXPRESSION, "compute/apply requires path or fn")
}

/// §4.1's handler-mode arm, after the three shape checks `eval_apply` has already made.
///
/// **Where §4.1 is silent this follows `entity-core-go`'s `evalApplyHandler`, and each such place is
/// declared in `[assumptions].apply_handler_mode` rather than decided here:** an operation with no
/// declared `input_type` builds a `primitive/any` params entity; a dispatch answering `>= 400` is
/// the dispatched `compute/error` when the result is one and `not_found` otherwise.
fn eval_apply_handler(
    entity: &Entity,
    path: &str,
    operation: &str,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Stepped {
    let Some(dispatch) = ctx.dispatch else {
        return fail(
            CODE_INVALID_EXPRESSION,
            "handler dispatch not available: this evaluation has no request context to dispatch from \
             (§7.2 reactive re-evaluation runs from an emit consumer)",
        );
    };

    // §4.1 — `resolve_handler`, then the operation, BEFORE any arg is evaluated: an arg error must
    // not mask `not_found` / `invalid_expression`. Resolution is §6.6's longest-prefix walk, the one
    // the dispatch will take, so SI-3 reads the interface of the handler that will actually run.
    let Some(interface) = resolve_handler_interface(path, ctx) else {
        return fail(CODE_NOT_FOUND, format!("No handler at path: {path}"));
    };
    let Some(spec) = operation_spec(&interface, operation) else {
        return fail(
            CODE_INVALID_EXPRESSION,
            format!("Handler has no operation: {operation}"),
        );
    };
    // §2.1 SI-3 — the declared input_type.
    let (params_type, field_types) = match spec_input_type(spec) {
        Some(t) => {
            let fields = input_field_types(&t, ctx);
            (t, fields)
        }
        None => ("primitive/any".to_string(), None),
    };

    // §4.1 — args in ECF canonical map key order, each evaluated, materialized (M3 boundary 4) and
    // encoded into its field position (§2.1 SA-2).
    let mut resolved_args: Vec<(Key, Value)> = Vec::new();
    for (name, hash) in canonical_sorted_args(entity) {
        let target = resolved!(&hash, ctx, &format!("arg {name}"));
        let value = evaluated!(target, scope, budget, ctx);
        let value = materialize(&value, ctx);
        let encoded = match encode_arg_for_field(&name, value, field_types.as_ref(), ctx) {
            Ok(v) => v,
            Err(e) => return done(Val::Error(e)),
        };
        resolved_args.push((Key::Text(name), encoded));
    }
    let params = Entity::make(&params_type, Value::Map(resolved_args));

    // F2/F4 — the resource, resolved and evaluated, must be a resource-target.
    let mut resource: Option<Value> = None;
    if let Some(resource_ref) = entity.bytes_field("resource") {
        let target = resolved!(resource_ref, ctx, "apply resource");
        let value = evaluated!(target, scope, budget, ctx);
        resource = match resource_target(&value, ctx) {
            Some(r) => Some(r),
            None => {
                return fail(
                    CODE_TYPE_MISMATCH,
                    "compute/apply resource must evaluate to a system/protocol/resource-target",
                )
            }
        };
    }

    // F2 — the dual check at full resolution, when a capability is provided.
    let mut provided: Option<Entity> = None;
    if let Some(cap_ref) = entity.bytes_field("capability") {
        let target = resolved!(cap_ref, ctx, "apply capability");
        let value = evaluated!(target, scope, budget, ctx);
        let cap = match materialize(&value, ctx) {
            Val::Entity(e) => e,
            _ => {
                return fail(
                    CODE_TYPE_MISMATCH,
                    "compute/apply capability field must resolve to an entity",
                )
            }
        };
        // FAIL CLOSED: §4.1 always checks `ctx.capability`. The reference skips the ceiling when
        // its context has none; an evaluation with no ceiling to check is refused here instead.
        let Some(ceiling) = ctx.capability else {
            return fail(CODE_PERMISSION_DENIED, "compute/apply capability override with no evaluation capability to dual-check against");
        };
        if !grant_covers(
            ctx.store,
            ctx.included,
            ceiling,
            path,
            Some(operation),
            resource.clone(),
            ctx.local_peer,
        ) {
            return fail(
                CODE_PERMISSION_DENIED,
                format!("Handler grant does not cover target: {path}.{operation}"),
            );
        }
        if !grant_covers(
            ctx.store,
            ctx.included,
            &cap,
            path,
            Some(operation),
            resource.clone(),
            ctx.local_peer,
        ) {
            return fail(
                CODE_PERMISSION_DENIED,
                format!("provided capability does not cover target: {path}.{operation}"),
            );
        }
        provided = Some(cap);
    }

    let (status, result) = dispatch(DispatchCall {
        path: path.to_string(),
        operation: operation.to_string(),
        resource,
        params,
        capability: provided,
    });
    if status >= 400 {
        if result.typ == ERROR {
            return done(Val::Entity(result));
        }
        // §3.2 v3.19c [normative] — a dispatch the capability blocks is `permission_denied` as a
        // VALUE at 200, not a transport error. The peer's local dispatch answers that as `403`.
        if status == 403 {
            return fail(
                CODE_PERMISSION_DENIED,
                format!("dispatch to {path}.{operation} refused: status 403"),
            );
        }
        return fail(
            CODE_NOT_FOUND,
            format!("handler dispatch failed: status {status}"),
        );
    }
    // §2.1 SA-4 — a bare primitive return (any `primitive/*` wrapper) is re-wrapped in
    // `compute/result`; an entity-typed return, including a `compute/result`, passes through.
    if result.typ.starts_with("primitive/") {
        return done(Val::Entity(Entity::make(
            RESULT,
            Value::Map(vec![
                (Key::Text("value".into()), result.data.clone()),
                (
                    Key::Text("expression".into()),
                    Value::Bytes(entity.hash.clone()),
                ),
            ]),
        )));
    }
    done(Val::Entity(result))
}

/// §6.6's resolution, as the dispatch will perform it: the longest prefix of `path` bound to a
/// `system/handler` entity, and the interface that entity names.
fn resolve_handler_interface(path: &str, ctx: &EvalContext) -> Option<Entity> {
    let canonical = canonicalize_path(path, ctx.local_peer);
    let mut end = canonical.len();
    loop {
        let prefix = &canonical[..end];
        if let Some(handler) = ctx.store.get_at(prefix) {
            if handler.typ == "system/handler" {
                let interface = handler.text_field("interface")?;
                return ctx
                    .store
                    .get_at(&canonicalize_path(interface, ctx.local_peer));
            }
        }
        match canonical[..end].rfind('/') {
            Some(i) if i > 0 => end = i,
            _ => return None,
        }
    }
}

/// The interface's `operations[operation]`, or `None` when the handler does not declare it.
fn operation_spec<'e>(interface: &'e Entity, operation: &str) -> Option<&'e Value> {
    let Some(Value::Map(ops)) = interface.field("operations") else {
        return None;
    };
    ops.iter().find_map(|(k, v)| match k {
        Key::Text(name) if name == operation => Some(v),
        _ => None,
    })
}

/// `input_type` from an operation spec; `None` when absent (§3.7 makes both types optional).
fn spec_input_type(spec: &Value) -> Option<String> {
    match spec {
        Value::Map(fields) => fields.iter().find_map(|(k, v)| match (k, v) {
            (Key::Text(f), Value::Text(t)) if f == "input_type" && !t.is_empty() => Some(t.clone()),
            _ => None,
        }),
        _ => None,
    }
}

/// `system/type/<input_type>`'s `fields`, as name → `type_ref`. `None` is §2.1's no-type-extension
/// fallback: every arg inlined.
fn input_field_types(type_name: &str, ctx: &EvalContext) -> Option<HashMap<String, String>> {
    if type_name == "primitive/any" {
        return None;
    }
    let def = ctx.store.get_at(&canonicalize_path(
        &format!("system/type/{type_name}"),
        ctx.local_peer,
    ))?;
    if def.typ != "system/type" {
        return None;
    }
    let Some(Value::Map(fields)) = def.field("fields") else {
        return None;
    };
    let out: HashMap<String, String> = fields
        .iter()
        .filter_map(|(k, v)| match (k, v) {
            (Key::Text(name), Value::Map(spec)) => {
                spec.iter().find_map(|(sk, sv)| match (sk, sv) {
                    (Key::Text(f), Value::Text(t)) if f == "type_ref" => {
                        Some((name.clone(), t.clone()))
                    }
                    _ => None,
                })
            }
            _ => None,
        })
        .collect();
    (!out.is_empty()).then_some(out)
}

/// §4.1 `encode_arg_for_field`, over an already-materialized value (an `Entity` or `Data`).
///
/// The `primitive/<specific>` row's `type_mismatch` is NOT enforced, which is the reference's
/// reading too (`encodeArgForField` inlines every non-`system/hash` field); declared with the
/// silence it rests on in `[assumptions].apply_handler_mode`.
fn encode_arg_for_field(
    name: &str,
    value: Val,
    field_types: Option<&HashMap<String, String>>,
    ctx: &EvalContext,
) -> Result<Value, ComputeError> {
    let declared = field_types.and_then(|f| f.get(name)).map(String::as_str);
    match (declared, value) {
        (Some("system/hash"), Val::Entity(e)) => {
            ctx.store.put_entity(&e);
            ctx.mark_encountered(&e.hash);
            Ok(Value::Bytes(e.hash))
        }
        (Some("system/hash"), _) => Err(ComputeError::new(
            CODE_TYPE_MISMATCH,
            format!("Field {name} expects system/hash, got primitive"),
        )),
        (_, Val::Entity(e)) => Ok(e.to_cbor()),
        (_, Val::Data(d)) => Ok(d),
        (_, other) => unreachable!("materialized values are entities or data, got {other:?}"),
    }
}

/// A `compute/apply.resource` value as the EXECUTE's `resource` map: a `{targets: [...]}` record,
/// or an entity of that shape.
fn resource_target(value: &Val, ctx: &EvalContext) -> Option<Value> {
    let data = match materialize(value, ctx) {
        Val::Data(d) => d,
        Val::Entity(e) => e.data.clone(),
        _ => return None,
    };
    match &data {
        Value::Map(pairs)
            if pairs.iter().any(
                |(k, v)| matches!((k, v), (Key::Text(t), Value::Array(_)) if t == "targets"),
            ) =>
        {
            Some(data)
        }
        _ => None,
    }
}

/// `compute/apply.args` in ECF canonical map key order — encoded key length, then bytes (§8.2).
fn canonical_sorted_args(entity: &Entity) -> Vec<(String, Vec<u8>)> {
    let mut args: Vec<(String, Vec<u8>)> = arg_hashes(entity).into_iter().collect();
    args.sort_by(|(a, _), (b, _)| {
        a.len()
            .cmp(&b.len())
            .then_with(|| a.as_bytes().cmp(b.as_bytes()))
    });
    args
}

/// A closure parameter as a binding name. Text is the only well-formed shape; anything else is
/// rendered rather than rejected, which is what `python`'s `str(raw_param)` does.
fn param_name(raw: &Value) -> String {
    match raw {
        Value::Text(s) => s.clone(),
        other => match int_of(other) {
            Some(i) => i.to_string(),
            None => format!("{other:?}"),
        },
    }
}

/// §2.1 — `compute/apply.args` is a `{name -> system/hash}` map, or absent.
fn arg_hashes(entity: &Entity) -> BTreeMap<String, Vec<u8>> {
    let mut out = BTreeMap::new();
    if let Some(Value::Map(entries)) = entity.field("args") {
        for (k, v) in entries {
            if let (Key::Text(name), Value::Bytes(h)) = (k, v) {
                out.insert(name.clone(), h.clone());
            }
        }
    }
    out
}

/// The path with any leading `/{peer}/` removed — handler patterns are peer-relative.
pub(crate) fn relative_pattern(path: &str) -> &str {
    if let Some(rest) = path.strip_prefix('/') {
        return match rest.find('/') {
            Some(i) => &rest[i + 1..],
            None => path,
        };
    }
    path
}

/// The builtin's short name, or `None` when `path` is not under the builtin prefix. The test is
/// the separator, so `system/compute/builtinsomething` is not a builtin.
pub(crate) fn builtin_name(path: &str) -> Option<String> {
    let relative = relative_pattern(path);
    if relative == BUILTINS_PREFIX {
        return Some(String::new());
    }
    relative
        .strip_prefix(BUILTINS_PREFIX)
        .and_then(|rest| rest.strip_prefix('/'))
        .map(str::to_string)
}

// ── §3.5 — the builtin handlers, evaluated INTERNALLY as §3.5 asks ──────────────────────

fn eval_builtin(
    name: &str,
    args: &BTreeMap<String, Vec<u8>>,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Val {
    macro_rules! ok_or_return {
        ($e:expr) => {
            match $e {
                Ok(v) => v,
                Err(e) => return Val::Error(e),
            }
        };
    }

    match name {
        // ── the five inline-equivalent aliases (§10.2 SHOULD), sharing the inline code path ──
        "arithmetic" | "compare" => {
            let op = ok_or_return!(arg_text(args, "op", scope, budget, ctx));
            let (Some(left), Some(right)) = (args.get("left"), args.get("right")) else {
                return err(
                    CODE_MISSING_ARGUMENT,
                    format!("builtins/{name} requires `left` and `right`"),
                );
            };
            let ops = ok_or_return!(eval_operand_pair(left, right, scope, budget, ctx));
            if name == "arithmetic" {
                apply_arithmetic(&op, &ops)
            } else {
                apply_compare(&op, &ops)
            }
        }
        "logic" => {
            let op = ok_or_return!(arg_text(args, "op", scope, budget, ctx));
            let Some(left) = args.get("left") else {
                return err(CODE_MISSING_ARGUMENT, "builtins/logic requires `left`");
            };
            match apply_logic(
                &op,
                left,
                args.get("right").map(Vec::as_slice),
                scope,
                budget,
                ctx,
            ) {
                Ok(Step::Done(v)) => v,
                Ok(Step::Tail(..)) => unreachable!("apply_logic never tail-calls"),
                Err(e) => Val::Error(e),
            }
        }
        "field" => {
            let field_name = ok_or_return!(arg_text(args, "name", scope, budget, ctx));
            let target = arg_value(args, "entity", scope, budget, ctx);
            if is_error(&target) {
                return Val::Error(as_compute_error(&target));
            }
            navigate_field(&target, &field_name)
        }
        "construct" => {
            let entity_type = ok_or_return!(arg_text(args, "entity_type", scope, budget, ctx));
            // Every arg EXCEPT the reserved `entity_type` key is a field — the whole difference
            // between the two forms, and why the bytes agree.
            let fields = args
                .iter()
                .filter(|(k, _)| k.as_str() != "entity_type")
                .map(|(k, v)| (k.clone(), v.clone()))
                .collect();
            construct_from(&entity_type, fields, scope, budget, ctx)
        }

        // ── the collection primitives (§10.1 MUST) ───────────────────────────────────
        "map" | "filter" | "group-by" => {
            let items = ok_or_return!(arg_array(args, "collection", scope, budget, ctx));
            let closure = ok_or_return!(arg_closure(args, "fn", scope, budget, ctx));
            match name {
                "map" => builtin_map(&items, &closure, budget, ctx),
                "filter" => builtin_filter(&items, &closure, budget, ctx),
                _ => builtin_group_by(&items, &closure, budget, ctx),
            }
        }
        "fold" => {
            let items = ok_or_return!(arg_array(args, "collection", scope, budget, ctx));
            let closure = ok_or_return!(arg_closure(args, "fn", scope, budget, ctx));
            if !args.contains_key("initial") {
                return err(CODE_MISSING_ARGUMENT, "builtins/fold requires `initial`");
            }
            // §3.5 v3.27 — THE ACCUMULATOR CONTAINS: `fold` MUST NOT abort on an error
            // accumulator, so `initial` gets no `is_error` guard. Only a halting code stops it.
            match arg_value(args, "initial", scope, budget, ctx) {
                Val::Error(e) if is_halting_code(&e.code) => Val::Error(e),
                Val::Error(e) => {
                    builtin_fold(&items, &closure, Val::Entity(e.to_entity()), budget, ctx)
                }
                initial => builtin_fold(&items, &closure, initial, budget, ctx),
            }
        }
        "range" => {
            let n = arg_value(args, "n", scope, budget, ctx);
            if is_error(&n) {
                return Val::Error(as_compute_error(&n));
            }
            let Some(raw) = val_int(&n) else {
                return err(CODE_TYPE_MISMATCH, "builtins/range requires an integer `n`");
            };
            let count = to_signed64(raw);
            // §3.5 v3.25 — negative, or past the maximum array length, is `count_out_of_range`
            // and is NOT clamped to `[]`.
            if count < 0 || count > max_array_length() {
                return err(
                    CODE_COUNT_OUT_OF_RANGE,
                    format!("builtins/range n out of range: {count}"),
                );
            }
            Val::Data(Value::Array((0..count as u64).map(Value::UInt).collect()))
        }
        "concat" => {
            // v3.27 — ONE hash of an expression evaluating to an array OF arrays.
            let outer = ok_or_return!(arg_array(args, "collections", scope, budget, ctx));
            let mut out = Vec::new();
            for sub in outer {
                match sub {
                    // ONE LEVEL, order-preserving.
                    Value::Array(items) => out.extend(items),
                    _ => {
                        return err(
                            CODE_TYPE_MISMATCH,
                            "builtins/concat requires an array of arrays",
                        )
                    }
                }
            }
            Val::Data(Value::Array(out))
        }
        "assoc" => {
            let items = ok_or_return!(arg_array(args, "collection", scope, budget, ctx));
            let idx = arg_value(args, "index", scope, budget, ctx);
            // `index` is CONSUMED — read to position the write.
            if is_error(&idx) {
                return Val::Error(as_compute_error(&idx));
            }
            let Some(raw) = val_int(&idx) else {
                return err(
                    CODE_TYPE_MISMATCH,
                    "builtins/assoc requires an integer `index`",
                );
            };
            let i = to_signed64(raw);
            if i < 0 || i >= items.len() as i128 {
                return err(
                    CODE_INDEX_OUT_OF_RANGE,
                    format!("builtins/assoc index out of range: {i}"),
                );
            }
            let value = arg_value(args, "value", scope, budget, ctx);
            if let Val::Error(e) = &value {
                if is_halting_code(&e.code) {
                    return value;
                }
            }
            // `value` is CONTAINED — the SA-9 store case, placed without being read.
            let mut out = items;
            out[i as usize] = contained_element(&value, ctx);
            Val::Data(Value::Array(out))
        }
        "store" => builtin_store(args, scope, budget, ctx),
        _ => err(
            CODE_INVALID_EXPRESSION,
            format!("§3.5 defines no builtin `{name}` ({BUILTINS_PREFIX}/{name})"),
        ),
    }
}

/// §3.5 / §6.3's `store`, through SA-10's second door — a direct capability-checked write rather
/// than a `system/tree:put` dispatch, because the first door needs re-entrant dispatch (K-5).
/// `Store::bind_with_context` runs the §6.10 emit pathway itself, so an emit consumer sees a
/// `store` write exactly as it sees any other.
///
/// **And for two days the call below was `Store::bind`, which passes NO context** — so a
/// consumer would have read a caller's `builtins/store` write as AUTONOMOUS and attributed it to
/// the local peer. The doc comment above named `bind_with_context` the whole time; the code did
/// not do it. Keystone found it by reading, not by driving, and could not have driven it: no
/// composition of ours runs COMPUTE and HISTORY together, so the only consumer that would have
/// noticed does not exist in any arm we run
/// (`ROUTING-2026-09-13-b-entity-system-generator-embed-data-is-measured-the-store-refuses-a-forged-hash-and-one-bind-in-your-evaluator-drops-the-caller`
/// §4). Fixed 2026-09-14.
///
/// **A doc comment asserting the call it sits above is the weakest form of evidence in this
/// tree**, and this is the instance that proves it: the sentence was correct about the API and
/// false about the caller, and nothing in `make check` reads a doc comment.
fn builtin_store(
    args: &BTreeMap<String, Vec<u8>>,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Val {
    if !args.contains_key("path") || !args.contains_key("value") {
        return err(
            CODE_INVALID_EXPRESSION,
            "builtins/store requires `path` and `value`",
        );
    }
    // `path` is CONSUMED — it steers where the write goes.
    let raw_path = arg_value(args, "path", scope, budget, ctx);
    if is_error(&raw_path) {
        return Val::Error(as_compute_error(&raw_path));
    }
    let Some(raw) = val_text(&raw_path) else {
        return err(CODE_TYPE_MISMATCH, "builtins/store `path` must be text");
    };
    let target = canonicalize_path(raw, ctx.local_peer);

    // §6.3 — the caller's capability MUST cover the write; the handler MUST NOT substitute its own.
    if !(ctx.can_write_path)(&target) {
        return err(
            CODE_PERMISSION_DENIED,
            format!("Capability does not cover tree write: {target}"),
        );
    }

    let value = arg_value(args, "value", scope, budget, ctx);
    if let Val::Error(e) = &value {
        if is_halting_code(&e.code) {
            return value;
        }
    }

    // SA-9 — a WRITE site, not a consumed position: an error is written code-only.
    let stored = if is_error(&value) {
        as_compute_error(&value).to_entity()
    } else if is_entity_like(&value) {
        match materialize(&value, ctx) {
            Val::Entity(e) => e,
            _ => unreachable!("an entity-like value materializes to an entity"),
        }
    } else {
        // SA-9 — a bare primitive is wrapped in `primitive/any`, whose data IS the value.
        let Val::Data(data) = value else {
            unreachable!("every non-error, non-entity value is data")
        };
        Entity::make("primitive/any", data)
    };

    // THE RETURNED `bool` IS CHECKED, and it is not defensive programming. Since keystone's
    // 13-b the store REFUSES an entity whose carried hash is not its own content hash and
    // returns `false`, storing nothing and firing no event. Dropping that would let
    // `builtins/store` answer with the entity it "wrote" to a tree that does not hold it —
    // a write that reads as done and is not, which is the failure mode the refusal exists to
    // stop. `Entity::make` above always produces a holding hash, so this is unreachable today;
    // it is written because `stored` comes from three branches and only one of them is
    // `Entity::make`.
    if !ctx
        .store
        .bind_with_context(&target, &stored, ctx.exec_context.cloned())
    {
        return err(
            CODE_INVALID_EXPRESSION,
            format!(
                "Store refused the write at {target}: the entity's hash is not its content hash"
            ),
        );
    }
    ctx.mark_encountered(&stored.hash);
    // §3.5 does not pin the return value. We return the entity written, which every
    // implementation has in hand. Routed as a question.
    Val::Entity(stored)
}

fn builtin_map(items: &[Value], closure: &Entity, budget: &mut Budget, ctx: &EvalContext) -> Val {
    let mut out = Vec::with_capacity(items.len());
    for item in items {
        let r = apply_closure_to_values(closure, vec![Val::Data(item.clone())], budget, ctx);
        if let Val::Error(e) = &r {
            if is_halting_code(&e.code) {
                return r;
            }
        }
        // §3.5 v3.27 — the OUTPUT element CONTAINS.
        out.push(contained_element(&r, ctx));
    }
    Val::Data(Value::Array(out))
}

fn builtin_filter(
    items: &[Value],
    closure: &Entity,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Val {
    let mut out = Vec::new();
    for item in items {
        let verdict = apply_closure_to_values(closure, vec![Val::Data(item.clone())], budget, ctx);
        // §3.5 v3.27 — THE PREDICATE RESULT SHORT-CIRCUITS: an error has no truth value, and
        // coercing it to false would silently drop the element.
        if is_error(&verdict) {
            return Val::Error(as_compute_error(&verdict));
        }
        if truthy(&verdict) {
            out.push(contained_element(&Val::Data(item.clone()), ctx));
        }
    }
    Val::Data(Value::Array(out))
}

fn builtin_fold(
    items: &[Value],
    closure: &Entity,
    initial: Val,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Val {
    let mut acc = initial;
    for item in items {
        let next =
            apply_closure_to_values(closure, vec![acc, Val::Data(item.clone())], budget, ctx);
        acc = match next {
            Val::Error(e) if is_halting_code(&e.code) => return Val::Error(e),
            // The accumulator CONTAINS: passed onward as an ordinary bound value.
            Val::Error(e) => Val::Entity(e.to_entity()),
            other => other,
        };
    }
    acc
}

fn builtin_group_by(
    items: &[Value],
    closure: &Entity,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Val {
    let mut order: Vec<Vec<u8>> = Vec::new();
    let mut members: HashMap<Vec<u8>, Vec<Value>> = HashMap::new();
    let mut keys: HashMap<Vec<u8>, Val> = HashMap::new();

    for item in items {
        let key = apply_closure_to_values(closure, vec![Val::Data(item.clone())], budget, ctx);
        // The DERIVED KEY is consumed — compared to assign a group — so it short-circuits.
        if is_error(&key) {
            return Val::Error(as_compute_error(&key));
        }
        let ident = key_identity(&key, ctx);
        if !members.contains_key(&ident) {
            order.push(ident.clone());
            members.insert(ident.clone(), Vec::new());
            keys.insert(ident.clone(), key);
        }
        members
            .get_mut(&ident)
            .expect("inserted above")
            .push(contained_element(&Val::Data(item.clone()), ctx));
    }

    let mut out = Vec::with_capacity(order.len());
    for ident in order {
        let group = Entity::make(
            GROUP,
            Value::Map(vec![
                (
                    Key::Text("key".into()),
                    contained_element(&keys[&ident], ctx),
                ),
                (
                    Key::Text("members".into()),
                    Value::Array(members.remove(&ident).unwrap_or_default()),
                ),
            ]),
        );
        ctx.store.put_entity(&group);
        ctx.mark_encountered(&group.hash);
        out.push(Value::Bytes(group.hash));
    }
    Val::Data(Value::Array(out))
}

/// §3.5's key equality — byte identity over the canonical ECF encoding of the MATERIALIZED key
/// (v3.27 D4). The prefix byte keeps an entity key from colliding with a data key whose encoding
/// happens to equal a hash.
///
/// **`cbor::encode` IS PUBLIC ON THIS PEER**, so this compares the encoding itself. `python` has to
/// go through `content_hash` over a wrapper type because its encoder is module-private; the
/// question decided is the same.
fn key_identity(key: &Val, ctx: &EvalContext) -> Vec<u8> {
    match key {
        k if is_entity_like(k) => {
            let mut out = vec![b'e'];
            out.extend(materialized_hash(k, ctx));
            out
        }
        Val::Data(v) => {
            let mut out = vec![b'v'];
            out.extend(cbor::encode(v));
            out
        }
        // Errors short-circuit before this is called.
        Val::Error(e) => {
            let mut out = vec![b'x'];
            out.extend(e.code.as_bytes());
            out
        }
        _ => unreachable!(),
    }
}

/// Apply a closure to values already in hand. Uses [`evaluate`] rather than a tail call because the
/// builtin must inspect the result, so the per-element evaluation legitimately consumes a depth frame.
fn apply_closure_to_values(
    closure: &Entity,
    args: Vec<Val>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Val {
    let mut loaded = match load_scope(closure.bytes_field("env"), ctx) {
        Ok(s) => s,
        Err(e) => return Val::Error(e),
    };
    let params = match req_list(closure, "params") {
        Ok(p) => p,
        Err(e) => return Val::Error(e),
    };
    let mut args = args.into_iter();
    for raw in params {
        let param = param_name(raw);
        match args.next() {
            Some(v) => {
                loaded.bindings.insert(param, v);
            }
            None => return err(CODE_MISSING_ARGUMENT, format!("Missing argument: {param}")),
        }
    }
    let body_hash = match req_bytes(closure, "body") {
        Ok(h) => h,
        Err(e) => return Val::Error(e),
    };
    match resolve_or_error(body_hash, ctx, "closure body") {
        Err(e) => Val::Error(e),
        Ok(body) => evaluate(&body, &Rc::new(loaded), budget, ctx),
    }
}

/// §3.5's evaluation-limit rule (v3.27 D5/D6) — **the counter decides**. `budget_exhausted` and
/// `cascade_limit` short-circuit in every position; `depth_exceeded` is element-local and contains.
fn is_halting_code(code: &str) -> bool {
    code == CODE_BUDGET_EXHAUSTED || code == CODE_CASCADE_LIMIT
}

/// §3.5 v3.26 — the form a CONTAINED value takes in a collection position: an entity by bare hash,
/// an error materialized code-only and referenced the same way, anything else inline.
fn contained_element(v: &Val, ctx: &EvalContext) -> Value {
    if is_error(v) {
        let e = as_compute_error(v).to_entity();
        ctx.store.put_entity(&e);
        ctx.mark_encountered(&e.hash);
        return Value::Bytes(e.hash);
    }
    match v {
        v if is_entity_like(v) => Value::Bytes(materialized_hash(v, ctx)),
        Val::Data(d) => d.clone(),
        _ => unreachable!(),
    }
}

// ── builtin argument readers ──────────────────────────────────────────────────────────

/// Resolve an `args` hash and evaluate it. The result MAY be an error — the caller decides.
fn arg_value(
    args: &BTreeMap<String, Vec<u8>>,
    name: &str,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Val {
    let Some(hash) = args.get(name) else {
        return err(CODE_MISSING_ARGUMENT, format!("Missing argument: {name}"));
    };
    match resolve_or_error(hash, ctx, &format!("builtin arg {name}")) {
        Err(e) => Val::Error(e),
        Ok(target) => evaluate(&target, scope, budget, ctx),
    }
}

fn arg_text(
    args: &BTreeMap<String, Vec<u8>>,
    name: &str,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Result<String, ComputeError> {
    let v = arg_value(args, name, scope, budget, ctx);
    if is_error(&v) {
        return Err(as_compute_error(&v));
    }
    val_text(&v).map(str::to_string).ok_or_else(|| {
        ComputeError::new(
            CODE_TYPE_MISMATCH,
            format!("builtin arg `{name}` must be text"),
        )
    })
}

fn arg_array(
    args: &BTreeMap<String, Vec<u8>>,
    name: &str,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Result<Vec<Value>, ComputeError> {
    let v = arg_value(args, name, scope, budget, ctx);
    if is_error(&v) {
        return Err(as_compute_error(&v));
    }
    val_array(&v).cloned().ok_or_else(|| {
        ComputeError::new(
            CODE_TYPE_MISMATCH,
            format!("builtin arg `{name}` must be an array"),
        )
    })
}

fn arg_closure(
    args: &BTreeMap<String, Vec<u8>>,
    name: &str,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Result<Entity, ComputeError> {
    let v = arg_value(args, name, scope, budget, ctx);
    if is_error(&v) {
        return Err(as_compute_error(&v));
    }
    match v {
        Val::Entity(e) if e.typ == CLOSURE => Ok(e),
        other => Err(ComputeError::new(
            CODE_TYPE_MISMATCH,
            format!(
                "builtin arg `{name}` must be a closure, got {}",
                describe(&other)
            ),
        )),
    }
}

// ── construct ─────────────────────────────────────────────────────────────────────────

/// The construct body, for the inline form AND §3.5's `builtins/construct` alias.
///
/// **Fields are evaluated in ECF CANONICAL MAP KEY ORDER** (length-then-lex). Materialization is
/// by RUNTIME KIND, never by the declared schema.
fn construct_from(
    entity_type: &str,
    fields: Vec<(String, Vec<u8>)>,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Val {
    let mut data: Vec<(Key, Value)> = Vec::new();
    let mut typed: BTreeMap<String, Val> = BTreeMap::new();

    for (name, field_hash) in canonical_sorted(fields) {
        let target = match resolve_or_error(&field_hash, ctx, &format!("construct field {name}")) {
            Err(e) => return Val::Error(e),
            Ok(t) if t.typ == ERROR => return Val::Entity(t),
            Ok(t) => t,
        };
        let value = evaluate(&target, scope, budget, ctx);
        // The guard returns FIRST, so a compute/error never reaches materialization (v3.23).
        if is_error(&value) {
            return value;
        }
        let stored = if is_entity_like(&value) {
            Value::Bytes(materialized_hash(&value, ctx))
        } else {
            match &value {
                Val::Data(d) => d.clone(),
                _ => unreachable!(),
            }
        };
        data.push((Key::Text(name.clone()), stored));
        typed.insert(name, value);
    }
    Val::Constructed(Rc::new(Constructed {
        entity: Entity::make(entity_type, Value::Map(data)),
        fields: typed,
    }))
}

/// §4.1's `canonical_sorted` — by ENCODED BYTE LENGTH first, then bytewise. `"z"` before `"aa"`.
fn canonical_sorted(mut entries: Vec<(String, Vec<u8>)>) -> Vec<(String, Vec<u8>)> {
    entries.sort_by(|a, b| {
        a.0.len()
            .cmp(&b.0.len())
            .then_with(|| a.0.as_bytes().cmp(b.0.as_bytes()))
    });
    entries
}

// ── scope capture and load ────────────────────────────────────────────────────────────

/// §4.4 `capture_scope` — FULL capture, not referenced-only, because the captured entity's content
/// hash is what §2.3's N2 pins across implementations. `None` for an empty scope.
fn capture_scope(scope: &Scope, ctx: &EvalContext) -> Option<Vec<u8>> {
    if scope.bindings.is_empty() {
        return None;
    }
    let bindings: Vec<(Key, Value)> = scope
        .bindings
        .iter()
        .map(|(name, value)| (Key::Text(name.clone()), binding_of(value, ctx)))
        .collect();
    let scope_entity = Entity::make(
        SCOPE,
        Value::Map(vec![(Key::Text("bindings".into()), Value::Map(bindings))]),
    );
    ctx.store.put_entity(&scope_entity);
    ctx.mark_encountered(&scope_entity.hash);
    Some(scope_entity.hash)
}

/// §2.3's kind-tagged binding (v3.19b N1). The tag is an explicit discriminator, never inferred.
fn binding_of(value: &Val, ctx: &EvalContext) -> Value {
    let pairs = if is_entity_like(value) || is_error(value) {
        // A scope is a MATERIALIZATION boundary (§2.3 N1's first placement).
        let hash = if is_error(value) {
            let e = as_compute_error(value).to_entity();
            ctx.store.put_entity(&e);
            e.hash
        } else {
            materialized_hash(value, ctx)
        };
        vec![
            (Key::Text("kind".into()), Value::Text("entity".into())),
            (Key::Text("entity_hash".into()), Value::Bytes(hash)),
        ]
    } else {
        let Val::Data(d) = value else { unreachable!() };
        vec![
            (Key::Text("kind".into()), Value::Text("value".into())),
            (Key::Text("value".into()), d.clone()),
        ]
    };
    Value::Map(pairs)
}

/// §4.3 `load_scope`, with N4a's EAGER resolution of every `kind:"entity"` binding, and N6's
/// content-store-direct resolution (scope entities bypass §4.2's tiers).
fn load_scope(env_hash: Option<&[u8]>, ctx: &EvalContext) -> Result<Scope, ComputeError> {
    let Some(env_hash) = env_hash else {
        return Ok(Scope::default());
    };
    let env = ctx
        .store
        .get_by_hash(env_hash)
        .ok_or_else(|| ComputeError::new(CODE_NOT_FOUND, "Closure scope entity not found"))?;
    ctx.mark_encountered(env_hash);

    let mut scope = Scope::default();
    let Some(Value::Map(bindings)) = env.field("bindings") else {
        return Ok(scope);
    };
    for (k, binding) in bindings {
        let name = match k {
            Key::Text(t) => t.clone(),
            other => format!("{other:?}"),
        };
        if !matches!(binding, Value::Map(_)) {
            return Err(ComputeError::new(
                CODE_TYPE_MISMATCH,
                format!("Scope binding is not a map: {name}"),
            ));
        }
        match map_get_text(binding, "kind") {
            Some(Value::Text(kind)) if kind == "entity" => {
                let Some(Value::Bytes(h)) = map_get_text(binding, "entity_hash") else {
                    return Err(ComputeError::new(
                        CODE_TYPE_MISMATCH,
                        format!("Scope binding has no entity_hash: {name}"),
                    ));
                };
                let target = ctx.store.get_by_hash(h).ok_or_else(|| {
                    // N8 — an error VALUE at status 200.
                    ComputeError::new(
                        CODE_SCOPE_UNREACHABLE,
                        format!("Scope binding does not resolve: {name}"),
                    )
                })?;
                scope.bindings.insert(name, Val::Entity(target));
            }
            Some(Value::Text(kind)) if kind == "value" => match map_get_text(binding, "value") {
                Some(v) => {
                    scope.bindings.insert(name, Val::Data(v.clone()));
                }
                None => {
                    return Err(ComputeError::new(
                        CODE_TYPE_MISMATCH,
                        format!("Scope binding has no value: {name}"),
                    ))
                }
            },
            _ => {
                return Err(ComputeError::new(
                    CODE_TYPE_MISMATCH,
                    format!("Scope binding has no kind tag: {name}"),
                ))
            }
        }
    }
    Ok(scope)
}

// ── resolution ────────────────────────────────────────────────────────────────────────

fn resolve_or_error(hash: &[u8], ctx: &EvalContext, label: &str) -> Result<Entity, ComputeError> {
    resolve(hash, ctx).ok_or_else(|| {
        ComputeError::new(CODE_NOT_FOUND, format!("Cannot resolve hash for {label}"))
    })
}

/// §4.2 `resolve` — included map, then content store, then the three-tier gate. The tree-scoped
/// fallback uses the encountered-during-read minimum §10.1 names.
pub(crate) fn resolve(hash: &[u8], ctx: &EvalContext) -> Option<Entity> {
    let found = match ctx.included.get(hash) {
        Some(e) => e.clone(),
        None => ctx.store.get_by_hash(hash)?,
    };
    validate_compute_resolvable(found, hash, ctx)
}

/// §4.2 `validate_compute_resolvable` — the three tiers. Compute is not a content-store oracle.
fn validate_compute_resolvable(entity: Entity, hash: &[u8], ctx: &EvalContext) -> Option<Entity> {
    if ctx.has_content_store_access
        || is_compute_type(&entity.typ)
        || ctx.authorized_data_hashes.contains(hash)
    {
        return Some(entity);
    }
    None
}

// ── value helpers ─────────────────────────────────────────────────────────────────────

/// §4.5 truthiness. `null`, `false`, `0`, `0.0`, `""` and `[]` are falsy; everything else is not —
/// including an empty map and an empty byte string.
pub(crate) fn truthy(value: &Val) -> bool {
    match value {
        Val::Data(Value::Null) => false,
        Val::Data(Value::Bool(b)) => *b,
        Val::Data(Value::UInt(n)) => *n != 0,
        Val::Data(Value::NInt(_)) => true,
        Val::Data(Value::Float(f)) => *f != 0.0,
        Val::Data(Value::Text(s)) => !s.is_empty(),
        Val::Data(Value::Array(items)) => !items.is_empty(),
        _ => true,
    }
}

const U64_MOD: i128 = 1 << 64;
const I64_MIN_MAGNITUDE: i128 = 1 << 63;

/// §2.2 rule 10 — read a 64-bit pattern by its SIGNED interpretation.
fn to_signed64(v: i128) -> i128 {
    let m = v.rem_euclid(U64_MOD);
    if m >= I64_MIN_MAGNITUDE {
        m - U64_MOD
    } else {
        m
    }
}

/// §2.2 rule 11 — read the same pattern by its UNSIGNED interpretation.
fn as_unsigned64(v: i128) -> i128 {
    v.rem_euclid(U64_MOD)
}

/// §2.2 rule 8 — integer arithmetic wraps at 2^64. A non-negative result keeps its unsigned
/// magnitude; a negative one keeps the two's-complement reading. The asymmetry is the reference's
/// and both halves are asserted by `v316_int_wraparound_add` / `v316_uint_wraparound_add`.
fn wrap64(v: i128) -> Value {
    if v >= 0 {
        Value::UInt(v.rem_euclid(U64_MOD) as u64)
    } else {
        value_of_int(to_signed64(v))
    }
}

/// `mul` cannot be computed exactly in `i128` (two `u64`s multiply to 2^128), so the bit pattern
/// comes from `wrapping_mul` and the SIGN of the true product decides which reading `wrap64` keeps.
fn wrapping_mul(l: i128, r: i128) -> Value {
    let bits = (l.rem_euclid(U64_MOD) as u64).wrapping_mul(r.rem_euclid(U64_MOD) as u64);
    let negative = l != 0 && r != 0 && ((l < 0) != (r < 0));
    if negative {
        value_of_int(to_signed64(bits as i128))
    } else {
        Value::UInt(bits)
    }
}

struct Operands {
    left: Val,
    right: Val,
    /// §2.2 rule 11 — a property of the EXPRESSION GRAPH, true when either operand entity is
    /// DIRECTLY a `compute/numeric-cast` to `primitive/uint`. Any indirection drops it.
    unsigned_intent: bool,
}

/// Resolve then evaluate, LEFT FULLY BEFORE RIGHT, guard after each step. The order is observable
/// through the budget.
fn eval_operand_pair(
    left_hash: &[u8],
    right_hash: &[u8],
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Result<Operands, ComputeError> {
    let left_target = resolve_or_error(left_hash, ctx, "left operand")?;
    let left_unsigned = is_direct_uint_cast(&left_target);
    let left = evaluate(&left_target, scope, budget, ctx);
    if is_error(&left) {
        return Err(as_compute_error(&left));
    }

    let right_target = resolve_or_error(right_hash, ctx, "right operand")?;
    let right_unsigned = is_direct_uint_cast(&right_target);
    let right = evaluate(&right_target, scope, budget, ctx);
    if is_error(&right) {
        return Err(as_compute_error(&right));
    }

    Ok(Operands {
        left,
        right,
        unsigned_intent: left_unsigned || right_unsigned,
    })
}

fn is_direct_uint_cast(operand: &Entity) -> bool {
    operand.typ == NUMERIC_CAST && operand.text_field("to_type") == Some("primitive/uint")
}

/// §4.1's `compute/logic`. `not` returns BEFORE `right` is resolved; `and`/`or` are NOT
/// short-circuiting (the step count is a determinism surface).
fn apply_logic(
    op: &str,
    left_hash: &[u8],
    right_hash: Option<&[u8]>,
    scope: &Rc<Scope>,
    budget: &mut Budget,
    ctx: &EvalContext,
) -> Stepped {
    let left_target = resolved!(left_hash, ctx, "logic left");
    let left = evaluated!(left_target, scope, budget, ctx);
    if op == "not" {
        return done(Val::Data(Value::Bool(!truthy(&left))));
    }
    let Some(right_hash) = right_hash else {
        return fail(
            CODE_INVALID_EXPRESSION,
            format!("compute/logic '{op}' requires a right operand"),
        );
    };
    let right_target = resolved!(right_hash, ctx, "logic right");
    let right = evaluated!(right_target, scope, budget, ctx);
    match op {
        "and" => done(Val::Data(Value::Bool(truthy(&left) && truthy(&right)))),
        "or" => done(Val::Data(Value::Bool(truthy(&left) || truthy(&right)))),
        _ => fail(
            CODE_INVALID_EXPRESSION,
            format!("compute/logic op must be and|or|not, got: {op}"),
        ),
    }
}

fn invalid_arith_op(op: &str) -> Val {
    err(
        CODE_INVALID_EXPRESSION,
        format!("compute/arithmetic op must be one of add|sub|mul|div|mod, got: {op}"),
    )
}

/// §4.1's `apply_arithmetic`, normative (v3.6 A1).
fn apply_arithmetic(op: &str, ops: &Operands) -> Val {
    let (left, right) = (&ops.left, &ops.right);
    if !is_numeric(left) || !is_numeric(right) {
        return err(CODE_TYPE_MISMATCH, "Arithmetic requires numeric operands");
    }

    if is_float(left) || is_float(right) {
        let (l, r) = (to_float(left), to_float(right));
        let f = match op {
            "add" => l + r,
            "sub" => l - r,
            "mul" => l * r,
            // IEEE-754 division, including by zero — NOT division_by_zero. Rust's `/` on f64
            // already is; nothing to override.
            "div" => l / r,
            "mod" => {
                if r == 0.0 {
                    return err(CODE_DIVISION_BY_ZERO, "Modulo by zero");
                }
                // Rust's `%` on f64 is C `fmod`: truncated, which is §4.1's rule.
                l % r
            }
            _ => return invalid_arith_op(op),
        };
        return Val::Data(Value::Float(f));
    }

    let raw_l = val_int(left).expect("numeric and not float");
    let raw_r = val_int(right).expect("numeric and not float");

    // add/sub/mul are SIGN-AGNOSTIC; div/mod are SIGNED-DEFAULT unless rule 11's unsigned intent.
    let read = |v: i128| {
        if ops.unsigned_intent {
            as_unsigned64(v)
        } else {
            to_signed64(v)
        }
    };
    match op {
        "add" => Val::Data(wrap64(raw_l + raw_r)),
        "sub" => Val::Data(wrap64(raw_l - raw_r)),
        "mul" => Val::Data(wrapping_mul(raw_l, raw_r)),
        "div" => {
            let (l, r) = (read(raw_l), read(raw_r));
            if r == 0 {
                return err(CODE_DIVISION_BY_ZERO, "Division by zero");
            }
            // i128 `%` and `/` truncate toward zero, which is §4.1's `truncated_remainder`.
            if l % r == 0 {
                return Val::Data(wrap64(l / r));
            }
            // §4.1: `to_float(left) / to_float(right)` — each operand converted, THEN divided.
            Val::Data(Value::Float(l as f64 / r as f64))
        }
        "mod" => {
            let (l, r) = (read(raw_l), read(raw_r));
            if r == 0 {
                return err(CODE_DIVISION_BY_ZERO, "Modulo by zero");
            }
            Val::Data(wrap64(l % r))
        }
        _ => invalid_arith_op(op),
    }
}

/// §4.1's `apply_compare`, normative (v3.6 A2). `eq`/`neq` accept any operand types; only the four
/// ORDERING ops demand compatible operands. Strings order by UTF-8 bytes, no normalization.
fn apply_compare(op: &str, ops: &Operands) -> Val {
    let (left, right) = (&ops.left, &ops.right);

    if op == "eq" || op == "neq" {
        let same = same_type_class(left, right) && value_equals(left, right);
        return Val::Data(Value::Bool(if op == "eq" { same } else { !same }));
    }
    if !matches!(op, "lt" | "gt" | "lte" | "gte") {
        return err(
            CODE_INVALID_EXPRESSION,
            format!("compute/compare op must be one of eq|neq|lt|gt|lte|gte, got: {op}"),
        );
    }

    if !is_numeric(left) || !is_numeric(right) {
        if let (Some(a), Some(b)) = (val_text(left), val_text(right)) {
            return Val::Data(Value::Bool(order(op, a.as_bytes().cmp(b.as_bytes()))));
        }
        return err(
            CODE_TYPE_MISMATCH,
            "Ordering comparison requires numeric or string operands",
        );
    }

    if is_float(left) || is_float(right) {
        let (l, r) = (to_float(left), to_float(right));
        // NaN is unordered: every ordering comparison against it is false.
        return Val::Data(Value::Bool(match l.partial_cmp(&r) {
            None => false,
            Some(c) => order(op, c),
        }));
    }

    let (raw_l, raw_r) = (val_int(left).unwrap(), val_int(right).unwrap());
    let (l, r) = if ops.unsigned_intent {
        (as_unsigned64(raw_l), as_unsigned64(raw_r))
    } else {
        (to_signed64(raw_l), to_signed64(raw_r))
    };
    Val::Data(Value::Bool(order(op, l.cmp(&r))))
}

fn order(op: &str, cmp: std::cmp::Ordering) -> bool {
    use std::cmp::Ordering::*;
    match op {
        "lt" => cmp == Less,
        "gt" => cmp == Greater,
        "lte" => cmp != Greater,
        _ => cmp != Less,
    }
}

/// §4.1 — numerics are one class; otherwise the primitive types must match.
fn same_type_class(a: &Val, b: &Val) -> bool {
    if is_numeric(a) && is_numeric(b) {
        return true;
    }
    if is_entity_like(a) || is_entity_like(b) {
        return is_entity_like(a) && is_entity_like(b);
    }
    match (a, b) {
        (Val::Data(x), Val::Data(y)) => std::mem::discriminant(x) == std::mem::discriminant(y),
        _ => false,
    }
}

fn value_equals(a: &Val, b: &Val) -> bool {
    if let (Some(x), Some(y)) = (entity_identity(a), entity_identity(b)) {
        return x == y;
    }
    if is_entity_like(a) || is_entity_like(b) {
        return false;
    }
    if let (Some(x), Some(y)) = (val_int(a), val_int(b)) {
        return x == y;
    }
    if is_numeric(a) && is_numeric(b) {
        return to_float(a) == to_float(b);
    }
    match (a, b) {
        // Arrays and maps (and every scalar left) compare by canonical encoding — the only
        // definition that agrees with content addressing.
        (Val::Data(x), Val::Data(y)) => cbor::encode(x) == cbor::encode(y),
        _ => false,
    }
}

/// §4.1 `compute/field`, with §2.3 N3's kind rule and option α's in-flight half.
fn navigate_field(target: &Val, name: &str) -> Val {
    let container = match target {
        Val::Constructed(c) => {
            return match c.fields.get(name) {
                Some(v) => v.clone(),
                None => err(CODE_NOT_FOUND, format!("Field not found: {name}")),
            }
        }
        Val::Entity(e) => &e.data,
        Val::Data(d) => d,
        Val::Error(_) => {
            return err(
                CODE_TYPE_MISMATCH,
                format!(
                    "Field access requires an entity or record, got: {}",
                    describe(target)
                ),
            )
        }
    };
    if !matches!(container, Value::Map(_)) {
        return err(
            CODE_TYPE_MISMATCH,
            format!(
                "Field access requires an entity or record, got: {}",
                describe(target)
            ),
        );
    }
    match map_get_text(container, name) {
        Some(v) => Val::Data(v.clone()),
        None => err(CODE_NOT_FOUND, format!("Field not found: {name}")),
    }
}

/// §2.2 N.1 — `compute/index`. An out-of-domain MAGNITUDE is `index_out_of_range`, never a type error.
fn index_into(arr: &Val, idx: &Val) -> Val {
    let Some(items) = val_array(arr) else {
        return err(CODE_TYPE_MISMATCH, "compute/index requires an array");
    };
    let Some(i) = val_int(idx) else {
        return err(
            CODE_TYPE_MISMATCH,
            "compute/index requires an integer index",
        );
    };
    if i < 0 || i >= items.len() as i128 {
        return err(CODE_INDEX_OUT_OF_RANGE, format!("Index out of range: {i}"));
    }
    Val::Data(items[i as usize].clone())
}

/// §2.2 N.1 — `compute/length`, over an ARRAY and nothing else (`v314_length_type_mismatch`).
fn length_of(v: &Val) -> Val {
    match val_array(v) {
        Some(items) => Val::Data(Value::UInt(items.len() as u64)),
        None => err(CODE_TYPE_MISMATCH, "compute/length requires an array"),
    }
}

const TWO_POW_64_F: f64 = 18_446_744_073_709_551_616.0;
const TWO_POW_63_F: f64 = 9_223_372_036_854_775_808.0;

/// §2.2 N.4 — `compute/numeric-cast`, with §9.1's `cast_out_of_range`.
///
/// **The range check runs in `f64` BEFORE any `as`**, because `f64 as i64` in Rust SATURATES and
/// maps NaN to 0 — a silent wrong answer the language supplies by itself.
fn numeric_cast(value: &Val, to_type: &str) -> Val {
    if !is_numeric(value) {
        return err(
            CODE_TYPE_MISMATCH,
            "compute/numeric-cast requires a numeric value",
        );
    }
    if to_type == "primitive/float" {
        return Val::Data(Value::Float(to_float(value)));
    }
    if to_type != "primitive/int" && to_type != "primitive/uint" {
        return err(
            CODE_TYPE_MISMATCH,
            format!("compute/numeric-cast target is not a numeric primitive: {to_type}"),
        );
    }
    let unsigned = to_type == "primitive/uint";
    let n: i128 = match val_int(value) {
        Some(i) => i,
        None => {
            let f = to_float(value);
            if f.is_nan() || f.is_infinite() {
                return err(CODE_CAST_OUT_OF_RANGE, "Cast of NaN or Inf to integer");
            }
            let t = f.trunc();
            // Only a FLOAT source can be out of range: an integer source is a bit pattern being
            // reinterpreted, a float is a value being converted.
            let out_of_range = if unsigned {
                t >= TWO_POW_64_F || t < 0.0
            } else {
                t >= TWO_POW_63_F || t < -TWO_POW_63_F
            };
            if out_of_range {
                return err(
                    CODE_CAST_OUT_OF_RANGE,
                    format!("Cast target cannot represent {t}"),
                );
            }
            t as i128
        }
    };
    // A NEGATIVE INTEGER CAST TO uint IS NOT AN ERROR (`v314_cast_int_to_uint_negative`).
    if unsigned {
        Val::Data(Value::UInt(as_unsigned64(n) as u64))
    } else {
        Val::Data(value_of_int(to_signed64(n)))
    }
}

fn describe(v: &Val) -> String {
    match v {
        Val::Constructed(c) => format!("in-flight entity {}", c.entity.typ),
        Val::Entity(e) => format!("entity {}", e.typ),
        Val::Error(e) => format!("error {}", e.code),
        Val::Data(d) => match d {
            Value::Null => "null".into(),
            Value::Bool(_) => "bool".into(),
            Value::UInt(_) | Value::NInt(_) => "int".into(),
            Value::Float(_) => "float".into(),
            Value::Text(_) => "text".into(),
            Value::Bytes(_) => "bytes".into(),
            Value::Array(_) => "array".into(),
            Value::Map(_) => "map".into(),
        },
    }
}

// ── paths ─────────────────────────────────────────────────────────────────────────────

/// V7 §5.4 canonicalization through **the peer's own primitive** (D12). On this peer it never
/// refuses — see the module doc, item 6.
pub(crate) fn canonicalize_path(path: &str, local_peer: &str) -> String {
    capability::canonicalize(local_peer, path)
}

/// §2.1's `clean_path` for the relative form — collapse `.`/`..` and empty segments.
pub(crate) fn clean_path(path: &str) -> String {
    let absolute = path.starts_with('/');
    let mut out: Vec<&str> = Vec::new();
    for seg in path.split('/') {
        match seg {
            "" | "." => {}
            ".." => {
                out.pop();
            }
            s => out.push(s),
        }
    }
    let joined = out.join("/");
    if absolute {
        format!("/{joined}")
    } else {
        joined
    }
}
