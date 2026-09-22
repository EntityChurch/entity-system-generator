/**
 * COMPUTE §4 — the evaluation algorithm.
 *
 * MODULE-PRIVATE, and for the same reason HISTORY's recorder is: `package.json`'s
 * `exports` map refuses a deep import here. An evaluator reachable from outside the
 * extension is a way to run an expression with a `ctx.capability` of the caller's
 * choosing, which is the §6.2 capability check removed. `test/export-surface.test.ts`
 * asserts on the module resolver's refusal, not on a review.
 *
 * WHAT THIS FILE IS FAITHFUL TO, AND WHERE IT DELIBERATELY IS NOT
 * ---------------------------------------------------------------
 * §4.1's pseudocode, clause for clause, with the trampoline, the depth accounting
 * and the `is_error` guard placement preserved exactly — those three are the parts
 * §4.1 spends its prose on, and each of them is a cross-impl determinism surface:
 *
 *   - **`is_error` is KIND-based, not outcome-based** (§4.1's opening `[MUST]`). A
 *     `compute/error` that evaluated *successfully* — a literal holding one, or a
 *     `lookup/hash` resolving to a stored one — is an error for every purpose in
 *     this file. The two readings are each self-consistent and split only at the
 *     cross-peer seam, which is why the spec pins it and why {@link isError} tests
 *     the type and never a control-flow outcome.
 *   - **The budget charges `evaluate()` steps and nothing else** (§4.2's normative
 *     note). `resolve()` costs zero. Two conformant peers must hit
 *     `budget_exhausted` at the same step count on the same `(IR, inputs, budget)`.
 *   - **Tail calls do not consume depth but DO decrement the budget** (§10.1). The
 *     `while (true)` loop below is that rule; a recursive implementation of the same
 *     algorithm is not conformant, it just looks like it works until a chain is long.
 *
 * TWO DECLARED DEVIATIONS FROM THE SPEC TEXT, both routed as
 * `ROUTING-2026-09-09-d-arch-*` and both implemented the way the rest of the spec
 * requires rather than the way the local block says:
 *
 *   1. **`isComputeType` / `isComputeExpression` carry all sixteen expression
 *      types.** §4.2's and §4.7's own lists omit `compute/index`, `compute/length`
 *      and `compute/numeric-cast`. Transcribing §4.2 literally makes any expression
 *      graph containing one of those three unresolvable — Tier 1 is the only tier
 *      that admits an ordinary sub-expression. See `../types.ts`.
 *   2. **Arithmetic and comparison follow §4.1's helpers**, which are normative and
 *      more specific than §2.2's prose. Where they differ in emphasis the helper
 *      wins, because the helper is what the conformance corpus was blessed against.
 *   3. **§4.1's `evaluate_inner` has no arm for the §2.3 VALUE TYPES and this one
 *      does** — {@link isValueType}, SA-1. A literal transcription answers
 *      `unknown_type` for a stored `compute/closure`, which is what this port did
 *      until the oracle's `v319b_scope_unreachable` said so.
 *   4. **`compute/construct` produces an IN-FLIGHT typed value**
 *      ({@link ConstructedValue}), not only the bare materialized entity §4.1's
 *      pseudocode assigns into `result_fields`. v3.19c option α puts materialization
 *      at the four compute→non-compute crossings, and §2.3's read-back clause makes
 *      in-flight navigation compose *"only where the kind is known"*. §4.1's arm
 *      keeps no in-flight representation at all, so a transcription of it cannot
 *      navigate two levels inside one evaluation.
 *
 * **DEVIATIONS 3 AND 4 SHARE ONE CAUSE WITH 1, AND IT IS THE FINDING RATHER THAN THE
 * FIX.** §4.1's pseudocode is downstream of every amendment in the document and is
 * the artifact an implementer transcribes; §2.3's SA-1 and §2.3's option-α clause
 * both reached the prose and the conformance corpus without reaching it. Routed as
 * A-12/A-13 with A-10/A-11's evidence.
 *
 * NOT IMPLEMENTED HERE, AND NAMED SO THE ABSENCE IS NOT MISTAKEN FOR AN OVERSIGHT:
 * `compute/apply` handler mode (§4.1's `dispatch_execute` branch), §3.5's builtin
 * collection primitives, §4.6 memoization, and §7 reactive mode. Each is declared
 * in `EXTENSION.toml` with the requirement rows it leaves uncovered. **A `501`-shaped
 * silent fallthrough is exactly what this repo routes against**, so every one of them
 * returns a real `compute/error` naming the reason rather than a wrong answer.
 */

import { Entity, Ecf, codec, type ContentStore, type EntityTree } from "entity-core-protocol-typescript";

import {
  APPLY, ARITHMETIC, CLOSURE, COMPARE, CONSTRUCT, ERROR, FIELD, IF, INDEX, LAMBDA,
  LENGTH, LET, LITERAL, LOGIC, LOOKUP_HASH, LOOKUP_SCOPE, LOOKUP_TREE, NUMERIC_CAST,
  RESULT, SCOPE, SCOPE_BINDING,
  BUILTINS_PREFIX, GROUP,
  CODE_BUDGET_EXHAUSTED, CODE_CASCADE_LIMIT, CODE_CAST_OUT_OF_RANGE,
  CODE_COUNT_OUT_OF_RANGE, CODE_DEPTH_EXCEEDED,
  CODE_DIVISION_BY_ZERO, CODE_INDEX_OUT_OF_RANGE, CODE_INVALID_EXPRESSION,
  CODE_MISSING_ARGUMENT, CODE_NOT_FOUND, CODE_PERMISSION_DENIED,
  CODE_SCOPE_UNREACHABLE, CODE_TYPE_MISMATCH, CODE_UNKNOWN_TYPE,
  isComputeExpression, isComputeType,
} from "../types.js";

/**
 * §3.5's *"an `n` exceeding the maximum representable array length"* for `range`.
 *
 * **Implementation-defined, and named rather than inlined because it is a place two
 * ports can silently disagree.** §3.5 pins the CODE (`count_out_of_range`) and the
 * refusal-not-clamp rule; it does not pin the bound. This is V8's own maximum array
 * length, which is the largest value this runtime could materialize — a smaller
 * arbitrary constant would refuse programs another peer accepts. Declared in
 * `EXTENSION.toml [assumptions]` and worth a spec question rather than a guess
 * repeated three times.
 */
const MAX_ARRAY_LENGTH = 2 ** 32 - 2;

type EcfValue = codec.EcfValue;

/**
 * A constructed entity that has not crossed a materialization boundary yet.
 *
 * **Two representations of one value, and both are needed** (v3.19c option α, §2.3):
 *
 * - `entity` is the **materialized bare form** — the normative one. Entity-valued
 *   fields are bare `system/hash` references, no `kind` tags anywhere, byte-identical
 *   to the same entity built outside compute. It is what crosses every boundary and
 *   what the oracle's M1 hash gate compares against `entity.NewEntity`.
 * - `fields` is the **in-flight typed form** — implementation-private by §2.3's own
 *   words, and the thing that makes `field(field(construct(...), 'inner'), 'name')`
 *   compose inside one evaluation. §2.3: navigation composes transparently *"only
 *   where the kind is known (in-flight typed values …); on a bare materialized
 *   entity, a reference is followed explicitly."*
 *
 * **The bare form is built EAGERLY and that is deliberate.** §4.1's pseudocode
 * materializes at the construct arm and this keeps the M1 hash on exactly one code
 * path — a second, lazier path is the fork `v319c_inline_vs_builtin_construct_hash_agreement`
 * exists to catch. What option α actually requires is not that the store write be
 * deferred; it is that **navigation between hops does not have to go through the
 * materialized form**, and `fields` is that. The extra content-store put for an
 * intermediate construct is invisible: the store is content-addressed, and §5.3
 * charges `evaluate()` steps rather than writes.
 */
export class ConstructedValue {
  constructor(
    readonly entity: Entity,
    readonly fields: ReadonlyMap<string, EvalValue>,
  ) {}
}

/**
 * An evaluated value: an ECF value tree, an `Entity` (§4.1 returns whole entities
 * from `lookup/tree`, `lookup/hash` and `lambda`), or a {@link ConstructedValue}.
 *
 * **`null` is a real value here, not an absence** — §4.1's `compute/if` with no
 * `else` branch returns it explicitly, and §4.5 makes it falsy. An `undefined`
 * never appears in this file for that reason.
 */
export type EvalValue = EcfValue | Entity | ConstructedValue;

/** What leaves the evaluator: §2.3's materialized form and nothing in-flight. */
export type BoundaryValue = EcfValue | Entity;

/**
 * Is this value entity-KINDED? §2.3 N3's rule, as a type guard rather than a shape
 * test — the one form of the rule that has no heuristic to get wrong.
 */
function isEntityLike(v: EvalValue): v is Entity | ConstructedValue {
  return v instanceof Entity || v instanceof ConstructedValue;
}

/** The complement: a plain ECF value tree, with a `kind` discriminator to read. */
function isPlainValue(v: EvalValue): v is EcfValue {
  return !isEntityLike(v);
}

/** §4.1 — entity identity is the MATERIALIZED content hash, never the in-flight form. */
function entityIdentity(v: Entity | ConstructedValue): string {
  return v instanceof ConstructedValue ? v.entity.contentHashHex : v.contentHashHex;
}

/**
 * §2.3 — the four VALUE types. Not expressions; SA-1 returns them unchanged.
 *
 * `compute/error` is in the set and its presence is not a special case: §4.1's
 * `is_error` is kind-based, so an error returned here short-circuits at the next
 * CONSUMPTION site exactly as a minted one does (§3.5's *"behaves identically however
 * it was produced"*).
 */
const VALUE_TYPES: readonly string[] = [CLOSURE, SCOPE, RESULT, ERROR];

function isValueType(typeName: string): boolean {
  return VALUE_TYPES.includes(typeName);
}

/**
 * §2.3 SA-1 / §4.4 — bring a value to its materialized form, storing what it
 * references.
 *
 * The three call sites are §2.3 N1's three placement boundaries plus the evaluator's
 * own exit: a `compute/construct` field, a `compute/scope` binding, and
 * {@link ComputeEvaluator.evaluateAt}'s return. Keeping them on one function is what
 * stops the bare form being derived twice — the fork the oracle's inline-versus-builtin
 * hash-agreement vector exists to detect.
 */
export function materialize(value: EvalValue, ctx: EvalContext): BoundaryValue {
  const out = value instanceof ConstructedValue ? value.entity : value;
  if (out instanceof Entity) {
    ctx.contentStore.put(out);
    ctx.markEncountered(out.contentHashHex);
  }
  return out;
}

/** §5.1 — the two counters. Mutated in place, exactly as §4.1's pseudocode does. */
export interface Budget {
  operations: number;
  depth: number;
}

/** §4.3 — a scope is a flat name → value map, copied on `let` and on closure apply. */
export interface Scope {
  readonly bindings: Map<string, EvalValue>;
}

export function emptyScope(): Scope {
  return { bindings: new Map() };
}

function copyScope(scope: Scope): Scope {
  return { bindings: new Map(scope.bindings) };
}

/**
 * §4.1's `ctx`. Every field is something the evaluator READS; nothing here is
 * derived inside the evaluator, so a caller can see the whole authority surface
 * in one place.
 */
export interface EvalContext {
  readonly tree: EntityTree;
  readonly contentStore: ContentStore;
  readonly localPeerId: string;
  /** §2.1 — the root a `relative: true` path resolves against. */
  readonly subgraphRoot: string;
  /** §4.2 step 1 — the envelope's pre-authorized `included` map, by hex hash. */
  readonly included: ReadonlyMap<string, Entity>;
  /** §4.2 Tier 0 — the `content_store_access` allowance. */
  readonly hasContentStoreAccess: boolean;
  /** §4.2 Tier 2 — an installed subgraph's sealed set, hex-encoded. */
  readonly authorizedDataHashes: ReadonlySet<string>;
  /** §4.1 — `check_path_permission("get", path, ...)`. See {@link EvalContext.canReadPath}. */
  canReadPath(path: string): boolean;
  /**
   * §6.3 — `check_path_permission("put", path, capability)` for the `store` builtin.
   *
   * Separate from {@link EvalContext.canReadPath} because §6.3's table gives the two
   * different authorities: a tree READ rides `ctx.capability`, and a `store` WRITE
   * rides the caller's capability with the handler explicitly forbidden from
   * substituting its own grant (no-silent-escalation). This port answers both at the
   * dispatch boundary, which is the declared substrate gap — but collapsing them into
   * one predicate would hide that they are two questions.
   */
  canWritePath(path: string): boolean;
  /** §7.1 — reactive dependency registration. A no-op outside an installed subgraph. */
  registerDependency(path: string): void;
  /** §4.4 / §4.3 N6 — make a just-written content hash locally resolvable. */
  markEncountered(hashHex: string): void;
}

// ── errors ──────────────────────────────────────────────────────────────────────

/**
 * §2.4 — a `compute/error`, built with `code` ONLY.
 *
 * `message`, `at` and `expression` are declared by the type and are **in-flight
 * diagnostics that are never materialized** (§2.4, v3.26). Building them here and
 * dropping them at the boundary would be the same bug with an extra step: the
 * moment one is written into the tree or into a contained collection position, the
 * containing array's bytes fork across two conformant peers. So this constructor
 * takes a code and nothing else, and the diagnostic rides beside the value in
 * {@link ComputeError.detail} where the codec can never see it.
 */
export class ComputeError {
  constructor(
    readonly code: string,
    readonly detail: string = "",
  ) {}

  /** The materialized form — `code` only, per §2.4. */
  toEntity(): Entity {
    return Entity.create(ERROR, Ecf.map(["code", Ecf.text(this.code)]));
  }
}

function err(code: string, detail = ""): ComputeError {
  return new ComputeError(code, detail);
}

/**
 * §4.1's `is_error(v)` `[MUST]` — **kind-based**.
 *
 * True for our in-flight {@link ComputeError} AND for an `Entity` whose type is
 * `compute/error`, because §4.1 is explicit that a stored one reached by evaluation
 * is an error for every purpose in that section. Testing only the in-flight class
 * would implement the outcome-based reading the spec rejects.
 */
export function isError(v: EvalValue | ComputeError): v is ComputeError | Entity | ConstructedValue {
  if (v instanceof ComputeError) return true;
  // An in-flight construct whose `entity_type` IS `compute/error` is an error by the
  // same kind-based test. §4.1's guard means one can never be produced by a failing
  // sub-expression, so this is the deliberately-built case only — and answering it
  // any other way would let the in-flight representation decide the disposition,
  // which is what §2.4 forbids.
  if (v instanceof ConstructedValue) return v.entity.type === ERROR;
  return v instanceof Entity && v.type === ERROR;
}

// ── the trampoline ──────────────────────────────────────────────────────────────

interface TailCall {
  readonly _tailCall: true;
  readonly entity: Entity;
  readonly scope: Scope;
}

function tailCall(entity: Entity, scope: Scope): TailCall {
  return { _tailCall: true, entity, scope };
}

function isTailCall(v: unknown): v is TailCall {
  return typeof v === "object" && v !== null && (v as TailCall)._tailCall === true;
}

type InnerResult = EvalValue | ComputeError | TailCall;

// ── evaluate ────────────────────────────────────────────────────────────────────

/**
 * §4.1 `evaluate` — the depth frame, the budget charge, and the trampoline.
 *
 * The three `budget.depth` mutations are in the same three places §4.1 puts them,
 * including the one that is easy to miss: **the budget-exhaustion path restores the
 * depth frame before returning** (`budget.depth += 1`), so a caller that catches the
 * error and continues is not left one frame short. Removing it changes how deep a
 * subsequent expression may go, which is observable.
 */
export function evaluate(
  entity: Entity,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): EvalValue | ComputeError {
  if (budget.depth <= 0) {
    return err(CODE_DEPTH_EXCEEDED, "Maximum evaluation depth exceeded");
  }
  budget.depth -= 1;

  let current = entity;
  let currentScope = scope;

  for (;;) {
    budget.operations -= 1;
    if (budget.operations <= 0) {
      budget.depth += 1;
      return err(CODE_BUDGET_EXHAUSTED, "Computation budget exhausted");
    }

    const result = evaluateInner(current, currentScope, budget, ctx);

    if (isTailCall(result)) {
      current = result.entity;
      currentScope = result.scope;
      continue;
    }

    budget.depth += 1;
    return result;
  }
}

function evaluateInner(
  entity: Entity,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): InnerResult {
  switch (entity.type) {
    case LITERAL:
      // SA-1: returned unchanged, including when the value IS a compute/error.
      // The `is_error` guard at each CONSUMPTION site is what short-circuits it —
      // this branch does not, and that separation is §4.1's opening MUST.
      //
      // ** READ DIRECTLY, NOT THROUGH `Ecf.require`, AND THE REASON IS A REAL VALUE. **
      // `Ecf.field` documents itself as returning JS null "if absent (or explicitly
      // null)" — it COLLAPSES a stored ECF null with a missing key, so `Ecf.require`
      // throws on `compute/literal{value: null}`. And null is a first-class compute
      // value: §4.5 makes it falsy, so it is a legitimate `compute/if` condition, and
      // §4.1's `if` with no `else` RETURNS it. A literal holding one has to round-trip.
      // Found by running the §4.5 truthiness test, which failed on its first element.
      // Recorded as `[substrate].ecf_null_is_indistinguishable_from_absent`.
      return literalValue(entity);

    case LOOKUP_SCOPE: {
      const name = Ecf.requireText(entity.data, "name");
      const bound = scope.bindings.get(name);
      // `has`, not `!== undefined` — a binding whose VALUE is the ECF null is a
      // real binding, and §4.5 makes it falsy rather than absent.
      if (scope.bindings.has(name)) return bound as EvalValue;
      return err(CODE_NOT_FOUND, "No scope binding: " + name);
    }

    case LOOKUP_TREE: {
      const raw = Ecf.requireText(entity.data, "path");
      const relative = Ecf.optBool(entity.data, "relative") === true;
      const path = relative
        ? cleanPath(ctx.subgraphRoot + "/" + raw)
        : canonicalize(raw, ctx.localPeerId);

      // §6.2 — the capability check comes BEFORE the read and before the
      // dependency registration, so an unauthorized path does not leak its
      // existence through a registered dependency.
      if (!ctx.canReadPath(path)) {
        return err(CODE_PERMISSION_DENIED, "Capability does not cover tree read: " + path);
      }
      ctx.registerDependency(path);
      const found = ctx.tree.get(path);
      if (found === undefined) {
        return err(CODE_NOT_FOUND, "No entity at path: " + path);
      }
      // §2.1's spreadsheet semantic: a stored EXPRESSION evaluates; a stored value
      // — including a compute/closure — is returned as-is.
      if (isComputeExpression(found.type)) return tailCall(found, scope);
      return found;
    }

    case LOOKUP_HASH: {
      const h = Ecf.requireBytes(entity.data, "hash");
      const target = resolveOrError(h, ctx, "hash lookup");
      if (isError(target)) return target;
      const ent = target as Entity;
      if (isComputeExpression(ent.type)) return tailCall(ent, scope);
      return ent;
    }

    case APPLY:
      return evalApply(entity, scope, budget, ctx);

    case IF: {
      const condTarget = resolveOrError(Ecf.requireBytes(entity.data, "condition"), ctx, "if condition");
      if (isError(condTarget)) return condTarget;
      const condition = evaluate(condTarget as Entity, scope, budget, ctx);
      if (isError(condition)) return condition;
      if (truthy(condition)) {
        const thenTarget = resolveOrError(Ecf.requireBytes(entity.data, "then"), ctx, "if then");
        if (isError(thenTarget)) return thenTarget;
        return tailCall(thenTarget as Entity, scope);
      }
      const elseRef = Ecf.optBytes(entity.data, "else");
      if (elseRef !== null) {
        const elseTarget = resolveOrError(elseRef, ctx, "if else");
        if (isError(elseTarget)) return elseTarget;
        return tailCall(elseTarget as Entity, scope);
      }
      // §4.1 returns null explicitly for a falsy `if` with no else. Not an error.
      return codec.ecfNull();
    }

    case LET: {
      const newScope = copyScope(scope);
      for (const binding of Ecf.asArray(Ecf.require(entity.data, "bindings"))) {
        const name = Ecf.requireText(binding, "name");
        const valueTarget = resolveOrError(
          Ecf.requireBytes(binding, "value"), ctx, "let binding " + name,
        );
        if (isError(valueTarget)) return valueTarget;
        // SEQUENTIAL, in `newScope` — §4.1's own comment calls it Scheme's `let*`,
        // so a later binding sees an earlier one. Evaluating in `scope` instead
        // would be a different language that passes every single-binding test.
        const value = evaluate(valueTarget as Entity, newScope, budget, ctx);
        if (isError(value)) return value;
        newScope.bindings.set(name, value);
      }
      const bodyTarget = resolveOrError(Ecf.requireBytes(entity.data, "body"), ctx, "let body");
      if (isError(bodyTarget)) return bodyTarget;
      return tailCall(bodyTarget as Entity, newScope);
    }

    case LAMBDA: {
      // Capture and produce a closure. The body is NOT evaluated.
      const bodyHash = Ecf.requireBytes(entity.data, "body");
      const envHash = captureScope(scope, ctx);
      return Entity.create(
        CLOSURE,
        Ecf.map(
          ["params", Ecf.require(entity.data, "params")],
          ["body", Ecf.bytes(bodyHash)],
          ["env", envHash === null ? null : Ecf.bytes(envHash)],
        ),
      );
    }

    case ARITHMETIC: {
      const ops = evalBinaryOperands(entity, scope, budget, ctx);
      if (ops instanceof ComputeError) return ops;
      return applyArithmetic(Ecf.requireText(entity.data, "op"), ops);
    }

    case COMPARE: {
      const ops = evalBinaryOperands(entity, scope, budget, ctx);
      if (ops instanceof ComputeError) return ops;
      return applyCompare(Ecf.requireText(entity.data, "op"), ops);
    }

    case LOGIC:
      return applyLogic(
        Ecf.requireText(entity.data, "op"),
        Ecf.requireBytes(entity.data, "left"),
        Ecf.optBytes(entity.data, "right"),
        scope,
        budget,
        ctx,
      );

    case FIELD: {
      const name = Ecf.requireText(entity.data, "name");
      const targetRef = resolveOrError(Ecf.requireBytes(entity.data, "entity"), ctx, "field target");
      if (isError(targetRef)) return targetRef;
      const target = evaluate(targetRef as Entity, scope, budget, ctx);
      if (isError(target)) return target;
      return navigateField(target, name);
    }

    case INDEX: {
      const arrRef = resolveOrError(Ecf.requireBytes(entity.data, "array"), ctx, "index array");
      if (isError(arrRef)) return arrRef;
      const arr = evaluate(arrRef as Entity, scope, budget, ctx);
      if (isError(arr)) return arr;
      const idxRef = resolveOrError(Ecf.requireBytes(entity.data, "index"), ctx, "index index");
      if (isError(idxRef)) return idxRef;
      const idx = evaluate(idxRef as Entity, scope, budget, ctx);
      if (isError(idx)) return idx;
      return indexInto(arr, idx);
    }

    case LENGTH: {
      const arrRef = resolveOrError(Ecf.requireBytes(entity.data, "array"), ctx, "length array");
      if (isError(arrRef)) return arrRef;
      const arr = evaluate(arrRef as Entity, scope, budget, ctx);
      if (isError(arr)) return arr;
      return lengthOf(arr);
    }

    case NUMERIC_CAST: {
      const valRef = resolveOrError(Ecf.requireBytes(entity.data, "value"), ctx, "numeric-cast value");
      if (isError(valRef)) return valRef;
      const value = evaluate(valRef as Entity, scope, budget, ctx);
      if (isError(value)) return value;
      return numericCast(value, Ecf.requireText(entity.data, "to_type"));
    }

    case CONSTRUCT:
      return evalConstruct(entity, scope, budget, ctx);

    default:
      // §2.3 SA-1 — A VALUE-TYPE ENTITY EVALUATES TO ITSELF, UNCHANGED. §4.1's
      // `evaluate_inner` has no arm for the four, so a literal transcription falls
      // straight into `unknown_type` below, and that is what this port did: the
      // oracle's `v319b_scope_unreachable` stores a `compute/closure` at a tree path
      // and applies it, and we answered `unknown_type` where the vector wants
      // `scope_unreachable`. The closure never reached `load_scope` at all.
      //
      // The arm sits HERE rather than as four `case`s beside the expression types on
      // purpose: SA-1's own words are that it *"generalizes the `compute/lookup/hash`
      // return-non-expressions-as-values rule"*, which is a statement about the
      // FALLTHROUGH and not about four types. A future value type is covered by
      // §4.7's own list moving, not by someone remembering this switch.
      if (isValueType(entity.type)) return entity;
      return err(CODE_UNKNOWN_TYPE, "Unknown compute type: " + entity.type);
  }
}

/**
 * Read `compute/literal`'s `value` field, distinguishing a stored ECF null from an
 * absent key.
 *
 * The peer's `Ecf.field` cannot: it maps `{kind:"null"}` and "no such key" onto the
 * same JS `null`, which is right for the §1.3 optional-field convention every protocol
 * entity uses and wrong for a `primitive/any` position where null is a VALUE. So this
 * walks the pairs, which is the only place in this extension that reaches past the
 * ergonomic layer, and it is confined to the one field that needs it.
 */
function literalValue(entity: Entity): EvalValue | ComputeError {
  const data = entity.data;
  if (data.kind !== "map") {
    return err(CODE_INVALID_EXPRESSION, "compute/literal has no data map");
  }
  for (const [k, v] of data.pairs) {
    if (k.kind === "text" && k.value === "value") return v;
  }
  return err(CODE_INVALID_EXPRESSION, "compute/literal has no `value` field");
}

// ── apply ───────────────────────────────────────────────────────────────────────

/**
 * §4.1's `compute/apply`. **Closure mode only in this port.**
 *
 * Handler mode needs `ctx.dispatch_execute` — a re-entrant dispatch into the peer
 * from inside an evaluation, with the F2 dual capability check and the V30
 * `encode_arg_for_field` typed-params construction. That is a seam question before
 * it is a code question (it is the path by which an expression can originate a
 * request), and shipping half of it would be worse than not shipping it: the F2
 * check only ever NARROWS, so a partial implementation runs WIDER than the caller
 * asked. It returns an honest `invalid_expression` naming the reason instead.
 *
 * The §2.1 Q23 shape check IS implemented, because it runs before any field is
 * resolved and its ORDERING is normative — rejecting after evaluation would make
 * the returned code depend on the field's value.
 */
function evalApply(entity: Entity, scope: Scope, budget: Budget, ctx: EvalContext): InnerResult {
  const path = Ecf.optText(entity.data, "path");
  const fnRef = Ecf.optBytes(entity.data, "fn");

  if (path !== null) {
    // §2.1 Q23 / §3.3 — a builtin path dispatches no EXECUTE, so `capability` and
    // `resource` have no referent. SHAPE CHECK, BEFORE ANY RESOLUTION (normative).
    const builtin = builtinName(path);
    if (builtin !== null) {
      if (Ecf.optBytes(entity.data, "capability") !== null || Ecf.optBytes(entity.data, "resource") !== null) {
        return err(
          CODE_INVALID_EXPRESSION,
          "compute/apply on a builtin path MUST NOT carry capability or resource",
        );
      }
    }
    const operation = Ecf.optText(entity.data, "operation");
    if (operation === null) {
      return err(CODE_INVALID_EXPRESSION, "compute/apply handler mode requires operation");
    }
    // F5 — a capability override without a resource cannot be dual-checked.
    if (Ecf.optBytes(entity.data, "capability") !== null && Ecf.optBytes(entity.data, "resource") === null) {
      return err(CODE_INVALID_EXPRESSION, "compute/apply with capability field MUST also have resource field");
    }
    if (builtin !== null) {
      if (operation !== "eval") {
        return err(CODE_INVALID_EXPRESSION, "§3.5: a builtin's only operation is `eval`, got: " + operation);
      }
      return evalBuiltin(builtin, argHashes(entity), scope, budget, ctx);
    }
    return err(
      CODE_INVALID_EXPRESSION,
      "compute/apply handler mode is not implemented in this port (§4.1 dispatch_execute); " +
        "see EXTENSION.toml [assumptions].apply_handler_mode",
    );
  }

  if (fnRef !== null) {
    const fnTarget = resolveOrError(fnRef, ctx, "closure fn");
    if (isError(fnTarget)) return fnTarget;
    const fnValue = evaluate(fnTarget as Entity, scope, budget, ctx);
    if (isError(fnValue)) return fnValue;
    if (!(fnValue instanceof Entity) || fnValue.type !== CLOSURE) {
      return err(CODE_TYPE_MISMATCH, "Apply target is not a closure");
    }

    const envHash = Ecf.optBytes(fnValue.data, "env");
    const loaded = loadScope(envHash, ctx);
    // `isError` is for EvalValues; `loadScope` returns a Scope or an error, so the
    // guard is an instanceof. Keeping the two distinct is deliberate — a Scope is not
    // a value and must never flow into a position that takes one.
    if (loaded instanceof ComputeError) return loaded;
    const newScope = loaded;

    const argMap = argHashes(entity);

    // Iterated over the CLOSURE'S PARAMS, not over the supplied args — §4.1's loop.
    // The difference is what makes a missing argument `missing_argument` rather
    // than a silently-unbound name, and it means an extra arg is ignored.
    for (const p of Ecf.asArray(Ecf.require(fnValue.data, "params"))) {
      const param = Ecf.asText(p);
      const argHash = argMap.get(param);
      if (argHash === undefined) {
        return err(CODE_MISSING_ARGUMENT, "Missing argument: " + param);
      }
      const argTarget = resolveOrError(argHash, ctx, "closure arg " + param);
      if (isError(argTarget)) return argTarget;
      // Evaluated in the CALLER's scope, bound into the CLOSURE's — §4.1's two
      // scopes, and the reason `scope` and `newScope` are both live here.
      const arg = evaluate(argTarget as Entity, scope, budget, ctx);
      if (isError(arg)) return arg;
      newScope.bindings.set(param, arg);
    }

    const bodyTarget = resolveOrError(Ecf.requireBytes(fnValue.data, "body"), ctx, "closure body");
    if (isError(bodyTarget)) return bodyTarget;
    return tailCall(bodyTarget as Entity, newScope);
  }

  return err(CODE_INVALID_EXPRESSION, "compute/apply requires path or fn");
}

/** §2.1 — `compute/apply.args` is a `{name -> system/hash}` map, or absent. */
function argHashes(entity: Entity): Map<string, Uint8Array> {
  const out = new Map<string, Uint8Array>();
  const raw = Ecf.field(entity.data, "args");
  if (raw !== null) {
    for (const [k, v] of Ecf.entries(raw)) out.set(k, Ecf.asBytes(v));
  }
  return out;
}

/** §3.5 / §4.1 — is this a `system/compute/builtins/*` path? */
function isBuiltinPath(path: string): boolean {
  return builtinName(path) !== null;
}

/**
 * The builtin's short name, or `null` when `path` is not a builtin path at all.
 *
 * ONE parser for the two questions, because they were two before and the near-miss is
 * the reason: `system/compute/builtinsomething` must not be a builtin, so the test is
 * the separator and not a `startsWith`. `assertNotBuiltinOverride` in `sdk.ts` carries
 * a negative control for exactly that string.
 */
function builtinName(path: string): string | null {
  const relative = path.startsWith("/") ? path.slice(path.indexOf("/", 1) + 1) : path;
  if (relative === BUILTINS_PREFIX) return "";
  if (!relative.startsWith(BUILTINS_PREFIX + "/")) return null;
  return relative.slice(BUILTINS_PREFIX.length + 1);
}

// ── §3.5 — the builtin handlers ─────────────────────────────────────────────────
//
// EVALUATED INTERNALLY, WHICH THE SECTION ASKS FOR RATHER THAN MERELY PERMITS.
// §3.5's closing paragraph: *"Because `map`/`filter`/`fold` apply a caller-provided
// closure per element, they need the evaluator's scope/budget/context — a real
// handler-dispatch boundary would lose these. Implementations SHOULD therefore
// evaluate the collection builtins internally within the evaluator … `system/compute/
// builtins/{map,filter,fold,range,group-by,concat,assoc}` is a canonical/LOGICAL
// operation name; on such implementations it MAY NOT resolve to a distinct handler
// entity in the tree."* So nothing is registered at these paths and a `tree:get` of
// one returns nothing — that is conformant, not a gap.
//
// THE ALIASES ARE §10.2 SHOULDs AND THE REST ARE §10.1 MUSTs, which is the opposite
// of what the reading order suggests. `{arithmetic,compare,logic,field,construct}`
// duplicate an inline type and are SHOULD; `{map,filter,fold}`, the four v3.24
// primitives and `store` have no inline form and were **promoted out of §10.3 into
// §10.1** at v3.14 — *"every compute-deterministic capability is MUST-given-COMPUTE …
// only resource bounds stay flexible."*
//
// AND EVERY ALIAS SHARES THE INLINE CODE PATH, deliberately.
// `v319c_inline_vs_builtin_construct_hash_agreement` exists because `entity-core-rust`
// shipped two construct paths that disagreed on the materialized hash; the vector
// passes trivially on a single-path implementation and catches the fork on any other.
// So `builtins/arithmetic` resolves its `op` arg and calls `applyArithmetic`, and
// there is no second copy of any operator's semantics in this file.

/** The nine §3.5 rows plus the four v3.24 primitives. */
function evalBuiltin(
  name: string,
  args: ReadonlyMap<string, Uint8Array>,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): InnerResult {
  switch (name) {
    // ── the five inline-equivalent aliases (§10.2 SHOULD) ──────────────────────
    case "arithmetic":
    case "compare": {
      const op = argText(args, "op", scope, budget, ctx);
      if (op instanceof ComputeError) return op;
      const left = args.get("left");
      const right = args.get("right");
      if (left === undefined || right === undefined) {
        return err(CODE_MISSING_ARGUMENT, "builtins/" + name + " requires `left` and `right`");
      }
      const ops = evalOperandPair(left, right, scope, budget, ctx);
      if (ops instanceof ComputeError) return ops;
      return name === "arithmetic" ? applyArithmetic(op, ops) : applyCompare(op, ops);
    }

    case "logic": {
      const op = argText(args, "op", scope, budget, ctx);
      if (op instanceof ComputeError) return op;
      const left = args.get("left");
      if (left === undefined) return err(CODE_MISSING_ARGUMENT, "builtins/logic requires `left`");
      return applyLogic(op, left, args.get("right") ?? null, scope, budget, ctx);
    }

    case "field": {
      const fieldName = argText(args, "name", scope, budget, ctx);
      if (fieldName instanceof ComputeError) return fieldName;
      const target = argValue(args, "entity", scope, budget, ctx);
      if (target instanceof ComputeError) return target;
      if (isError(target)) return asComputeError(target);
      return navigateField(target, fieldName);
    }

    case "construct": {
      const entityType = argText(args, "entity_type", scope, budget, ctx);
      if (entityType instanceof ComputeError) return entityType;
      // Every arg EXCEPT the reserved `entity_type` key is a field. That exclusion is
      // the whole difference between the two forms, and it is why an entity built
      // this way is byte-identical to the inline one: same fields, same code path.
      const fields = [...args.entries()].filter(([k]) => k !== "entity_type");
      return constructFrom(entityType, fields, scope, budget, ctx);
    }

    // ── the collection primitives (§10.1 MUST) ─────────────────────────────────
    case "map":
    case "filter":
    case "group-by": {
      const items = argArray(args, "collection", scope, budget, ctx);
      if (items instanceof ComputeError) return items;
      const fn = argClosure(args, "fn", scope, budget, ctx);
      if (fn instanceof ComputeError) return fn;
      if (name === "map") return builtinMap(items, fn, budget, ctx);
      if (name === "filter") return builtinFilter(items, fn, budget, ctx);
      return builtinGroupBy(items, fn, budget, ctx);
    }

    case "fold": {
      const items = argArray(args, "collection", scope, budget, ctx);
      if (items instanceof ComputeError) return items;
      const fn = argClosure(args, "fn", scope, budget, ctx);
      if (fn instanceof ComputeError) return fn;
      const initialHash = args.get("initial");
      if (initialHash === undefined) return err(CODE_MISSING_ARGUMENT, "builtins/fold requires `initial`");
      // §3.5 v3.27 — THE ACCUMULATOR CONTAINS, so `initial` is NOT short-circuited:
      // *"`fold` MUST NOT abort on an error accumulator"*, and a closure that ignores
      // its accumulator recovers. This is the one position where the two readings
      // produce a different VALUE rather than a different cost, which is why the
      // `isError` guard every other arg gets is absent here on purpose.
      const initial = argValue(args, "initial", scope, budget, ctx);
      if (initial instanceof ComputeError && !isHalting(initial)) {
        // A minted error still becomes the starting accumulator, in value form.
        return builtinFold(items, fn, initial.toEntity(), budget, ctx);
      }
      if (initial instanceof ComputeError) return initial;
      return builtinFold(items, fn, initial, budget, ctx);
    }

    case "range": {
      const n = argValue(args, "n", scope, budget, ctx);
      if (n instanceof ComputeError) return n;
      if (isError(n)) return asComputeError(n);
      if (!isInt(n)) return err(CODE_TYPE_MISMATCH, "builtins/range requires an integer `n`");
      const count = toSigned64(intValue(n));
      // §3.5 v3.25 — a negative `n`, or one past the maximum array length, is
      // `count_out_of_range` and NOT `type_mismatch` (§2.2's ruling: int/uint are
      // annotations, so an out-of-domain MAGNITUDE is not a type error). And it is
      // NOT clamped to `[]`: `n` is a loop bound, so a silent empty array propagates
      // through every downstream map/filter/fold as a well-formed wrong answer.
      if (count < 0n || count > BigInt(MAX_ARRAY_LENGTH)) {
        return err(CODE_COUNT_OUT_OF_RANGE, "builtins/range n out of range: " + count.toString());
      }
      const out: EcfValue[] = [];
      for (let i = 0n; i < count; i += 1n) out.push(codec.ecfInt(i));
      return Ecf.array(out);
    }

    case "concat": {
      // §3.5 v3.27 — `collections` is ONE hash of an expression evaluating to an
      // array OF arrays, never a literal array of hashes. The literal shape freezes
      // `concat`'s arity at authoring time, which would make the one primitive
      // adopted to join k arrays the one whose k is a constant.
      const outer = argArray(args, "collections", scope, budget, ctx);
      if (outer instanceof ComputeError) return outer;
      const out: EcfValue[] = [];
      for (const sub of outer) {
        // Each `collection` is CONSUMED — its length is read to copy — so an error
        // here short-circuits. Its ELEMENTS are contained and flow through untouched.
        if (isError(sub)) return asComputeError(sub);
        const items = asArrayValue(sub);
        if (items === null) return err(CODE_TYPE_MISMATCH, "builtins/concat requires an array of arrays");
        // ONE LEVEL, order-preserving — no recursive flatten.
        out.push(...items);
      }
      return Ecf.array(out);
    }

    case "assoc": {
      const items = argArray(args, "collection", scope, budget, ctx);
      if (items instanceof ComputeError) return items;
      const idx = argValue(args, "index", scope, budget, ctx);
      if (idx instanceof ComputeError) return idx;
      // `index` is CONSUMED — read to position the write.
      if (isError(idx)) return asComputeError(idx);
      if (!isInt(idx)) return err(CODE_TYPE_MISMATCH, "builtins/assoc requires an integer `index`");
      const i = toSigned64(intValue(idx));
      // §3.5 v3.25 — the same code and the same condition as `compute/index`. v3.24
      // said `type_mismatch` here and was corrected: one document must not answer one
      // malformed program with two codes depending on which array operation it reached.
      if (i < 0n || i >= BigInt(items.length)) {
        return err(CODE_INDEX_OUT_OF_RANGE, "builtins/assoc index out of range: " + i.toString());
      }
      const value = argValue(args, "value", scope, budget, ctx);
      if (value instanceof ComputeError && isHalting(value)) return value;
      // `value` is CONTAINED — the SA-9 store case, placed without being read.
      const out = [...items];
      out[Number(i)] = containedElement(value, ctx);
      return Ecf.array(out);
    }

    case "store":
      return builtinStore(args, scope, budget, ctx);

    default:
      return err(
        CODE_INVALID_EXPRESSION,
        "§3.5 defines no builtin `" + name + "` (" + BUILTINS_PREFIX + "/" + name + ")",
      );
  }
}

/**
 * §3.5 / §6.3's `store`, and **the write mechanism is a declared deviation from
 * SA-10's first sentence.**
 *
 * SA-10 says *"implementations dispatch the write via `system/tree:put`, so
 * capability-gating, path normalization, history, and reactive cascade are uniform
 * with all other tree writes"* — and then permits the alternative in the same breath:
 * *"a direct capability-checked `emit` is equally compliant, but `tree:put` keeps
 * attribution uniform."* This port takes the second door because the first needs
 * re-entrant dispatch, the same seam `compute/apply` handler mode is waiting on.
 *
 * **The half of SA-10's rationale we DO get, measured rather than assumed:** the
 * peer's `EntityTree.put` runs the §6.10 emit pathway itself — Store step then Bind
 * step, with a tree-change event when the binding changes — so a registered emit
 * consumer (HISTORY's recorder, say) sees a `store` write exactly as it sees any
 * other. **The halves we do NOT get are named in `EXTENSION.toml`:** no per-path
 * capability check (this port is dispatch-scoped, already declared), and no §6.8a
 * execution context on the event, which is `ROUTING-2026-09-06-d`'s finding and has
 * nothing to do with `store`.
 */
function builtinStore(
  args: ReadonlyMap<string, Uint8Array>,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): InnerResult {
  if (args.get("path") === undefined || args.get("value") === undefined) {
    return err(CODE_INVALID_EXPRESSION, "builtins/store requires `path` and `value`");
  }
  // `path` is a CONSUMED operand — it steers WHERE the write goes, exactly as
  // `assoc`'s `index` steers where the update lands — so an error path short-circuits
  // rather than becoming a `type_mismatch`.
  const rawPath = argValue(args, "path", scope, budget, ctx);
  if (rawPath instanceof ComputeError) return rawPath;
  if (isError(rawPath)) return asComputeError(rawPath);
  if (!isText(rawPath)) return err(CODE_TYPE_MISMATCH, "builtins/store `path` must be text");
  const target = canonicalize(rawPath.value, ctx.localPeerId);

  // §6.3 — the caller's capability MUST cover the write, and the handler MUST NOT
  // substitute its own grant (no-silent-escalation). Named rather than inlined for
  // the same reason `canReadPath` is: this port answers it at the dispatch boundary
  // and not per path, and an inline `true` leaves nothing to grep for.
  if (!ctx.canWritePath(target)) {
    return err(CODE_PERMISSION_DENIED, "Capability does not cover tree write: " + target);
  }

  const value = argValue(args, "value", scope, budget, ctx);
  if (value instanceof ComputeError && isHalting(value)) return value;

  // SA-9 — `store` is a WRITE / materialization site, not a consumed position, so an
  // error reaching `value` is WRITTEN code-only rather than short-circuited. §2.4's
  // reactive `result_path` crossing is the same rule on the reactive path.
  //
  // §200's error-short-circuit list names `compute/apply` handler mode among the
  // consumers, and the store builtin IS a handler-mode apply — so the two rules point
  // opposite ways for this one field. We follow the write-site taxonomy, which is
  // what `entity-core-go` does and what N1/§2.4/SA-9 say directly. NOT resolved
  // locally: the contradiction is arch's to settle and is routed.
  let stored: Entity;
  if (value instanceof ComputeError) {
    stored = value.toEntity();
  } else if (isError(value)) {
    stored = asComputeError(value).toEntity();
  } else if (isEntityLike(value)) {
    stored = materialize(value, ctx) as Entity;
  } else {
    // SA-9 — *"a bare-primitive result is wrapped in `primitive/any`"*. The wrapper's
    // data IS the value, not a map holding it, which is the wire shape `primitive/*`
    // uses for a bare value.
    stored = Entity.create("primitive/any", value);
  }

  ctx.tree.put(target, stored);
  ctx.contentStore.put(stored);
  ctx.markEncountered(stored.contentHashHex);
  // **§3.5 DOES NOT PIN THE RETURN VALUE**, and the reference's answer is not
  // portable: `entity-core-go` returns the `system/tree:put` response's result
  // entity, which a port with no re-entrant dispatch cannot produce. We return the
  // entity that was written — the one thing every implementation has in hand at this
  // point. Routed as a question, because a sequencing chain's `in _2` returns it and
  // §3.5's own example says so.
  return stored;
}

/** §3.5 — `map`: `fn` applied to each element in index order. */
function builtinMap(
  items: readonly EvalValue[],
  fn: Entity,
  budget: Budget,
  ctx: EvalContext,
): InnerResult {
  const out: EcfValue[] = [];
  for (const item of items) {
    // The element is BOUND into the closure, not read by `map` — so an error element
    // passes through and the closure's own operators short-circuit inside it.
    const r = applyClosureToValues(fn, [item], budget, ctx);
    if (r instanceof ComputeError && isHalting(r)) return r;
    // §3.5 v3.27 — the OUTPUT element CONTAINS. `map` never reads the closure's
    // result; it places it. So `map(f, [1,2,3])` where `f` fails only on element 2
    // yields `[a, E, c]` — §1.5's *"same model as NaN propagation in IEEE 754"* is
    // element-wise, and short-circuiting the whole array is exception semantics,
    // which §1.5 explicitly declined.
    out.push(containedElement(r, ctx));
  }
  return Ecf.array(out);
}

/** §3.5 — `filter`: the elements whose predicate result is truthy, in index order. */
function builtinFilter(
  items: readonly EvalValue[],
  fn: Entity,
  budget: Budget,
  ctx: EvalContext,
): InnerResult {
  const out: EcfValue[] = [];
  for (const item of items) {
    const verdict = applyClosureToValues(fn, [item], budget, ctx);
    // §3.5 v3.27 — THE PREDICATE RESULT SHORT-CIRCUITS, and this is the row that
    // differs from `map`'s. It is read for truthiness (§4.5) to decide inclusion,
    // which makes it a consumed operand by §7.2's plain terms. Containing it fails
    // the same way clamping a negative `range(n)` to `[]` would: an error has no
    // truth value, and coercing it to false SILENTLY DROPS the element.
    if (verdict instanceof ComputeError) return verdict;
    if (isError(verdict)) return asComputeError(verdict);
    if (truthy(verdict)) out.push(containedElement(item, ctx));
  }
  return Ecf.array(out);
}

/** §3.5 — `fold`: `initial` threaded through `fn(acc, element)` left to right. */
function builtinFold(
  items: readonly EvalValue[],
  fn: Entity,
  initial: EvalValue,
  budget: Budget,
  ctx: EvalContext,
): InnerResult {
  let acc: EvalValue = initial;
  for (const item of items) {
    const next = applyClosureToValues(fn, [acc, item], budget, ctx);
    if (next instanceof ComputeError && isHalting(next)) return next;
    // The accumulator CONTAINS at every step and as the result: `fold` binds it into
    // the next invocation and never reads it, so an error accumulator is passed
    // onward as an ordinary bound value and a closure that does not consult it
    // RECOVERS. Aborting here is the reading v3.27 rejected.
    acc = next instanceof ComputeError ? next.toEntity() : next;
  }
  return acc;
}

/** §3.5 — `group-by`: one pass, groups ordered by FIRST APPEARANCE of their key. */
function builtinGroupBy(
  items: readonly EvalValue[],
  fn: Entity,
  budget: Budget,
  ctx: EvalContext,
): InnerResult {
  const order: string[] = [];
  const members = new Map<string, EcfValue[]>();
  const keys = new Map<string, EvalValue>();

  for (const item of items) {
    const key = applyClosureToValues(fn, [item], budget, ctx);
    // The DERIVED KEY is consumed — it is compared to assign a group — so it
    // short-circuits even though the key has an output position. Grouping by an error
    // would make its message string structurally load-bearing: two failures worded
    // differently would become two groups.
    if (key instanceof ComputeError) return key;
    if (isError(key)) return asComputeError(key);

    const id = keyIdentity(key, ctx);
    if (id instanceof ComputeError) return id;
    if (!members.has(id)) {
      order.push(id);
      members.set(id, []);
      keys.set(id, key);
    }
    // The element is COPIED into `members` — contained.
    (members.get(id) as EcfValue[]).push(containedElement(item, ctx));
  }

  const out: EcfValue[] = [];
  for (const id of order) {
    const group = Entity.create(
      GROUP,
      Ecf.map(
        ["key", containedElement(keys.get(id) as EvalValue, ctx)],
        ["members", Ecf.array(members.get(id) as EcfValue[])],
      ),
    );
    ctx.contentStore.put(group);
    ctx.markEncountered(group.contentHashHex);
    out.push(Ecf.bytes(group.contentHash));
  }
  return Ecf.array(out);
}

/**
 * §3.5's key equality — byte-identity over the canonical ECF encoding of the
 * **materialized** key (v3.27 D4).
 *
 * For an entity-valued key that is the bare-entity bytes, and a content hash IS the
 * digest of exactly those bytes, so comparing hashes and comparing bytes decide the
 * same question. Reading the in-flight form instead would make an
 * implementation-private representation part of a group's identity, which is the same
 * thing §2.4 forbids for the in-flight error.
 */
function keyIdentity(key: EvalValue, ctx: EvalContext): string | ComputeError {
  if (isEntityLike(key)) return "e:" + (materialize(key, ctx) as Entity).contentHashHex;
  try {
    return "v:" + hexOf(Ecf.encodeEcf(key));
  } catch {
    return err(CODE_TYPE_MISMATCH, "builtins/group-by key is not encodable");
  }
}

/**
 * Apply a closure to values already in hand.
 *
 * §4.1's `compute/apply` binds args by resolving HASHES; a collection builtin has an
 * element in hand and nothing to resolve. This is the same body with the resolution
 * step removed, and it uses `evaluate` rather than a tail call **because the builtin
 * has to inspect the result** — a `map` decides whether to contain an error, so its
 * per-element evaluation is not in tail position and legitimately consumes a depth
 * frame.
 */
function applyClosureToValues(
  closure: Entity,
  args: readonly EvalValue[],
  budget: Budget,
  ctx: EvalContext,
): EvalValue | ComputeError {
  const loaded = loadScope(Ecf.optBytes(closure.data, "env"), ctx);
  if (loaded instanceof ComputeError) return loaded;

  const params = Ecf.asArray(Ecf.require(closure.data, "params")).map((p) => Ecf.asText(p));
  // Over the CLOSURE'S PARAMS, as §4.1 does — a supplied extra is ignored and a
  // missing one is `missing_argument` named after the param, never a silently
  // unbound name.
  for (let i = 0; i < params.length; i += 1) {
    if (i >= args.length) {
      return err(CODE_MISSING_ARGUMENT, "Missing argument: " + (params[i] as string));
    }
    loaded.bindings.set(params[i] as string, args[i] as EvalValue);
  }

  const bodyTarget = resolveOrError(Ecf.requireBytes(closure.data, "body"), ctx, "closure body");
  if (bodyTarget instanceof ComputeError) return bodyTarget;
  return evaluate(bodyTarget, loaded, budget, ctx);
}

/**
 * §3.5's evaluation-limit rule (v3.27 D5/D6) — **the counter decides, not the code's
 * "limit-ness"**, and the discriminator is whether the counter is restored when an
 * element finishes.
 *
 * `budget_exhausted` and `cascade_limit` short-circuit in EVERY position including the
 * contained ones, because `operations` is cumulative and monotonic and the cascade
 * counter is shared across the whole causal chain — so whether element *i* trips
 * either depends on what came before it, and a contained one is a different array per
 * peer for the same program. `depth_exceeded` is element-local (§5.1 restores `depth`
 * on return) and contains like any other error.
 *
 * **Keyed on the `code`, in both arms.** A value-form error carrying one of the two
 * codes short-circuits exactly as a minted one does — §7.3 *requires* the value form
 * to exist (*"budget exhaustion during reactive re-evaluation writes a `compute/error`
 * to the result_path"*), so this is not hypothetical, and keying on provenance is
 * what §2.4 forbids.
 */
function isHalting(v: EvalValue | ComputeError): boolean {
  if (!isError(v)) return false;
  const code = asComputeError(v).code;
  return code === CODE_BUDGET_EXHAUSTED || code === CODE_CASCADE_LIMIT;
}

/**
 * §3.5 v3.26 — the form a CONTAINED value takes in a collection position.
 *
 * An entity- or closure-valued element is referenced by a bare `system/hash`; an error
 * materializes **code-only** and is referenced the same way. The code-only form is
 * load-bearing rather than tidy: if a contained error carried `message`, two
 * conformant peers whose diagnostics differ would produce different bytes for the
 * containing array, so the array's content hash would fork cross-impl on a string no
 * spec pins.
 *
 * **A minted and a value-form error come out identical**, which is v3.27 D1: two
 * errors with the same `code` ARE the same materialized entity, so no rule may
 * distinguish them — including this one, which is why a stored `compute/error`
 * carrying a `message` is re-materialized here rather than passed through.
 */
function containedElement(v: EvalValue | ComputeError, ctx: EvalContext): EcfValue {
  if (isError(v)) {
    const e = asComputeError(v).toEntity();
    ctx.contentStore.put(e);
    ctx.markEncountered(e.contentHashHex);
    return Ecf.bytes(e.contentHash);
  }
  if (isEntityLike(v)) return Ecf.bytes((materialize(v, ctx) as Entity).contentHash);
  return v;
}

/** Resolve an `args` hash and evaluate it. The result MAY be an error — caller decides. */
function argValue(
  args: ReadonlyMap<string, Uint8Array>,
  name: string,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): EvalValue | ComputeError {
  const hash = args.get(name);
  if (hash === undefined) return err(CODE_MISSING_ARGUMENT, "Missing argument: " + name);
  const target = resolveOrError(hash, ctx, "builtin arg " + name);
  if (target instanceof ComputeError) return target;
  return evaluate(target, scope, budget, ctx);
}

/**
 * An `args` position that must evaluate to text.
 *
 * The alias builtins carry `op` / `name` / `entity_type` as a HASH of an expression,
 * where the inline form carries the same thing as a plain text field. That difference
 * is the whole shape gap between the two forms, and it is why the alias costs one
 * extra `evaluate()` step per such field — the same for every peer, since the extra
 * step is charged for an entity that is genuinely in the input.
 */
function argText(
  args: ReadonlyMap<string, Uint8Array>,
  name: string,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): string | ComputeError {
  const v = argValue(args, name, scope, budget, ctx);
  if (v instanceof ComputeError) return v;
  if (isError(v)) return asComputeError(v);
  if (!isText(v)) return err(CODE_TYPE_MISMATCH, "builtin arg `" + name + "` must be text");
  return v.value;
}

/** An `args` position that must evaluate to an array. CONSUMED — its length is read. */
function argArray(
  args: ReadonlyMap<string, Uint8Array>,
  name: string,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): readonly EcfValue[] | ComputeError {
  const v = argValue(args, name, scope, budget, ctx);
  if (v instanceof ComputeError) return v;
  if (isError(v)) return asComputeError(v);
  const items = asArrayValue(v);
  if (items === null) return err(CODE_TYPE_MISMATCH, "builtin arg `" + name + "` must be an array");
  return items;
}

/**
 * An `args` position that must evaluate to a `compute/closure`.
 *
 * The arg is normally a hash of a `compute/lambda` EXPRESSION, which evaluates to a
 * closure. A hash of a pre-computed `compute/closure` also works now — §2.3's SA-1
 * returns a value type unchanged — and the oracle's own note says the pre-computed
 * form *"only works on impls that bypass arg evaluation"*, which is a divergence SA-1
 * closes rather than a shape to reject.
 */
function argClosure(
  args: ReadonlyMap<string, Uint8Array>,
  name: string,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): Entity | ComputeError {
  const v = argValue(args, name, scope, budget, ctx);
  if (v instanceof ComputeError) return v;
  if (isError(v)) return asComputeError(v);
  if (!(v instanceof Entity) || v.type !== CLOSURE) {
    return err(CODE_TYPE_MISMATCH, "builtin arg `" + name + "` must be a closure, got " + describe(v));
  }
  return v;
}

// ── construct ───────────────────────────────────────────────────────────────────

/**
 * §4.1's `compute/construct`, with v3.19c option α's materialization rule.
 *
 * **Fields are evaluated in ECF CANONICAL MAP KEY ORDER** (§8.2 via
 * `canonical_sorted`), not in insertion order. That is observable whenever a field
 * expression has an effect or exhausts the budget: two peers iterating differently
 * charge the budget in different orders and can disagree about WHICH field's error
 * is returned.
 *
 * **Materialization is by RUNTIME KIND, never by the declared schema** — an entity
 * or closure value is stored and referenced by a bare `system/hash`; anything else
 * is inlined. No `kind` tags appear in the materialized data; kind-tagging is
 * confined to `compute/scope`.
 *
 * **AND IT RETURNS A {@link ConstructedValue}, NOT THE BARE ENTITY.** §4.1's arm
 * assigns the stored hash into `result_fields` and keeps nothing else, so a
 * transcription of it produces a value that `compute/field` can only navigate one
 * level into: the second hop reads a bare `system/hash` and answers `type_mismatch`.
 * v3.19c option α puts materialization at the four compute→non-compute crossings and
 * §2.3 makes in-flight navigation compose *"where the kind is known"*, which requires
 * the typed field map this returns alongside the bare form.
 */
function evalConstruct(entity: Entity, scope: Scope, budget: Budget, ctx: EvalContext): InnerResult {
  const raw = Ecf.field(entity.data, "fields");
  return constructFrom(
    Ecf.requireText(entity.data, "entity_type"),
    raw === null ? [] : Ecf.entries(raw).map(([k, v]) => [k, Ecf.asBytes(v)] as const),
    scope,
    budget,
    ctx,
  );
}

/**
 * The construct body, addressed by a `(name, hash)` list.
 *
 * **ONE CODE PATH FOR THE INLINE FORM AND FOR §3.5's `builtins/construct` ALIAS**, and
 * that is not tidiness: `v319c_inline_vs_builtin_construct_hash_agreement` exists
 * because `entity-core-rust` shipped two paths and they disagreed on the materialized
 * hash. A second derivation of the bare form is the defect that vector detects, so the
 * alias resolves its `entity_type` arg and then calls this.
 */
function constructFrom(
  entityType: string,
  fields: readonly (readonly [string, Uint8Array])[],
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): InnerResult {
  const pairs: (readonly [string, EcfValue | null])[] = [];
  const typed = new Map<string, EvalValue>();

  const entries = canonicalSorted(fields);
  for (const [name, fieldHash] of entries) {
    const target = resolveOrError(fieldHash, ctx, "construct field " + name);
    if (isError(target)) return target;
    const value = evaluate(target as Entity, scope, budget, ctx);
    // The guard returns FIRST, so a compute/error never reaches materialization.
    // v3.23 made that normative and removed compute/error from N1's placement
    // list; three implementations had read the two clauses in two different orders.
    if (isError(value)) return value;

    // The in-flight half: the value AS EVALUATED, with its kind intact.
    typed.set(name, value);

    if (isEntityLike(value)) {
      // NOTE: this peer's `ContentStore.put` returns VOID, where §4.1's pseudocode
      // reads `result_fields[name] = ctx.content_store.put(...)`. The hash comes off
      // the entity itself (`contentHash`), which is the same value — recorded in
      // `AUTHORING-NOTES` because it is a signature difference a second port will
      // meet and a template derived from the pseudocode would get wrong.
      const bare = materialize(value, ctx) as Entity;
      pairs.push([name, Ecf.bytes(bare.contentHash)]);
    } else {
      pairs.push([name, value]);
    }
  }
  return new ConstructedValue(Entity.create(entityType, Ecf.map(...pairs)), typed);
}

/**
 * §4.1's `canonical_sorted` — ECF canonical map key order: by ENCODED BYTE LENGTH
 * first, then lexicographically by byte value (`ENTITY-CBOR-ENCODING` §4.1 Rule 2).
 *
 * Length-then-lex, not plain lex. `"z"` sorts before `"aa"`. Getting this wrong
 * produces a correct-looking evaluator that disagrees with every other peer about
 * evaluation order the moment two field names differ in length.
 */
function canonicalSorted<T>(
  entries: readonly (readonly [string, T])[],
): readonly (readonly [string, T])[] {
  const enc = new TextEncoder();
  return [...entries].sort((a, b) => {
    const ka = enc.encode(a[0]);
    const kb = enc.encode(b[0]);
    if (ka.length !== kb.length) return ka.length - kb.length;
    for (let i = 0; i < ka.length; i += 1) {
      if (ka[i] !== kb[i]) return (ka[i] as number) - (kb[i] as number);
    }
    return 0;
  });
}

// ── scope capture and load ──────────────────────────────────────────────────────

/**
 * §4.4 `capture_scope`. Returns the content hash of the `compute/scope` entity, or
 * `null` for an empty scope (§4.4 permits skipping the write).
 *
 * **Full capture, not referenced-only.** §4.4 makes referenced-only a SHOULD and an
 * optimization; it also changes the captured entity's content hash, which is the
 * one thing N2 pins by digest across implementations. Taking the SHOULD would put
 * us in disagreement with every peer that did not. Declared in `EXTENSION.toml`.
 */
function captureScope(scope: Scope, ctx: EvalContext): Uint8Array | null {
  if (scope.bindings.size === 0) return null;

  const pairs: (readonly [string, EcfValue | null])[] = [];
  for (const [name, value] of scope.bindings) {
    pairs.push([name, bindingOf(value, ctx)]);
  }
  const scopeEntity = Entity.create(SCOPE, Ecf.map(["bindings", Ecf.map(...pairs)]));
  ctx.contentStore.put(scopeEntity);
  ctx.markEncountered(scopeEntity.contentHashHex);
  return scopeEntity.contentHash;
}

/**
 * §2.3's kind-tagged binding (v3.19b N1).
 *
 * An entity- or closure-valued binding is referenced by hash and tagged
 * `kind: "entity"`; anything else is inlined and tagged `kind: "value"`. The tag is
 * an **explicit discriminator** and is never inferred from the value's shape or
 * byte length — §2.3's N2 note spells out why (`system/hash` is variable-length with
 * an extensible LEB128 format code, so "33 bytes" is only today's size).
 */
function bindingOf(value: EvalValue, ctx: EvalContext): EcfValue {
  if (isEntityLike(value)) {
    // A `compute/scope` is a MATERIALIZATION boundary (§2.3 N1's first of three
    // placements), so an in-flight construct captured into a closure's environment
    // is materialized here rather than carried. Carrying it would put an
    // implementation-private form inside the one compute container that round-trips
    // by content hash — the digest §2.3's N2 note pins across implementations.
    const bare = materialize(value, ctx) as Entity;
    return Ecf.map(["kind", Ecf.text("entity")], ["entity_hash", Ecf.bytes(bare.contentHash)]);
  }
  return Ecf.map(["kind", Ecf.text("value")], ["value", value]);
}

/**
 * §4.3 `load_scope`, with N4a's eager resolution.
 *
 * **Every `kind:"entity"` binding is resolved at apply time, whether or not the body
 * reads it** — N4a is explicit that this is normative and that all three references
 * do it, so an unresolvable binding surfaces as `scope_unreachable` even for a
 * closure that never touches it. A lazy implementation returns a value where a
 * conformant one returns an error.
 *
 * Resolution is **content-store-direct** (N6): scope entities and their bindings ride
 * the closure's own authorization and bypass §4.2's tiers entirely.
 */
function loadScope(envHash: Uint8Array | null, ctx: EvalContext): Scope | ComputeError {
  if (envHash === null) return emptyScope();
  const env = ctx.contentStore.get(envHash);
  if (env === undefined) {
    return err(CODE_NOT_FOUND, "Closure scope entity not found");
  }
  ctx.markEncountered(hexOf(envHash));

  const scope = emptyScope();
  const bindings = Ecf.field(env.data, "bindings");
  if (bindings === null) return scope;

  for (const [name, binding] of Ecf.entries(bindings)) {
    const kind = Ecf.optText(binding, "kind");
    if (kind === "entity") {
      const h = Ecf.requireBytes(binding, "entity_hash");
      const target = ctx.contentStore.get(h);
      if (target === undefined) {
        // N8 — an error VALUE at status 200, not a transport failure.
        return err(CODE_SCOPE_UNREACHABLE, "Scope binding does not resolve: " + name);
      }
      scope.bindings.set(name, target);
    } else if (kind === "value") {
      scope.bindings.set(name, Ecf.require(binding, "value"));
    } else {
      return err(CODE_TYPE_MISMATCH, "Scope binding has no kind tag: " + name);
    }
  }
  return scope;
}

// ── resolution ──────────────────────────────────────────────────────────────────

/** §4.1's V31 helper — `resolve` plus a `not_found` on a null return. */
function resolveOrError(hash: Uint8Array, ctx: EvalContext, label: string): Entity | ComputeError {
  const entity = resolve(hash, ctx);
  if (entity === null) {
    return err(CODE_NOT_FOUND, "Cannot resolve hash for " + label);
  }
  return entity;
}

/**
 * §4.2 `resolve` — included map, then content store, then the three-tier gate.
 *
 * The tree-scoped fallback (`resolve_via_tree`) is where §4.2 leaves the mechanism
 * implementation-defined but fixes the semantic contract. This port uses the
 * **encountered-during-read** form, which §10.1 names as the minimum guarantee: a
 * hash written or read during this evaluation is resolvable. A reverse index would
 * be a permitted enhancement; it is not required and is not here.
 */
function resolve(hash: Uint8Array, ctx: EvalContext): Entity | null {
  const hex = hexOf(hash);

  const included = ctx.included.get(hex);
  if (included !== undefined) return validateComputeResolvable(included, hex, ctx);

  const stored = ctx.contentStore.get(hash);
  if (stored === undefined) return null;
  return validateComputeResolvable(stored, hex, ctx);
}

/**
 * §4.2 `validate_compute_resolvable` — the three tiers.
 *
 * Tier 1 uses OUR sixteen-plus-seven list rather than §4.2's twenty, for the reason
 * in `../types.ts`: §4.2's list omits three types §2.2 defines and §10.1 MUSTs, and
 * Tier 1 is the only tier that admits an ordinary sub-expression.
 */
function validateComputeResolvable(entity: Entity, hex: string, ctx: EvalContext): Entity | null {
  if (ctx.hasContentStoreAccess) return entity;              // Tier 0
  if (isComputeType(entity.type)) return entity;             // Tier 1
  if (ctx.authorizedDataHashes.has(hex)) return entity;      // Tier 2
  // The whole point of the gate: compute is not a content-store oracle. External
  // data goes through `compute/lookup/tree`, which is capability-checked.
  return null;
}

// ── value helpers ───────────────────────────────────────────────────────────────

/** §4.5 truthiness. `null`, `false`, `0`, `""` and `[]` are falsy; everything else is not. */
export function truthy(value: EvalValue): boolean {
  if (isEntityLike(value)) return true;
  switch (value.kind) {
    case "null": return false;
    case "bool": return value.value;
    case "int": return !(value.negative === false && value.argument === 0n);
    case "float": return value.value !== 0;
    case "text": return value.value !== "";
    case "array": return value.items.length > 0;
    default: return true;
  }
}

function isInt(v: EvalValue): v is codec.EcfInt {
  return isPlainValue(v) && v.kind === "int";
}

function isFloat(v: EvalValue): v is codec.EcfFloat {
  return isPlainValue(v) && v.kind === "float";
}

function isNumeric(v: EvalValue): boolean {
  return isInt(v) || isFloat(v);
}

function isText(v: EvalValue): v is codec.EcfText {
  return isPlainValue(v) && v.kind === "text";
}

function intValue(v: codec.EcfInt): bigint {
  return codec.ecfIntValue(v);
}

function toFloat(v: EvalValue): number {
  if (isFloat(v)) return v.value;
  if (isInt(v)) return Number(intValue(v));
  return NaN;
}

/**
 * §4.1's operand pair for `compute/arithmetic` and `compute/compare` — resolve, then
 * evaluate, LEFT FULLY BEFORE RIGHT, with the `is_error` guard after each of the four
 * steps.
 *
 * Factored out because the two branches are character-for-character identical in §4.1
 * and a second copy is a second place for the ORDER to drift. The order is observable:
 * both operands are charged to the budget, so a left operand that exhausts it must
 * return `budget_exhausted` before the right one is ever resolved.
 */
interface Operands {
  readonly left: EvalValue;
  readonly right: EvalValue;
  /**
   * §2.2 rule 11 — whether this operation is UNSIGNED, which is a property of the
   * EXPRESSION GRAPH and not of either value.
   *
   * True when either operand entity is *directly* a `compute/numeric-cast` to
   * `primitive/uint`. "Directly" is the whole rule: `div(numeric-cast(y, uint), 2)` is
   * unsigned, and `let y = numeric-cast(x, uint) in div(y, 2)` is signed-default,
   * because the cast is no longer the operand entity. Any indirection — a `let`, an
   * `if` branch, a `lookup/scope`, a `construct` field, a closure-arg binding — drops
   * the intent. That is why this is computed HERE, off the resolved operand entity,
   * and cannot be carried on the value: rule 8 is explicit that signedness is not a
   * value-level tag.
   */
  readonly unsignedIntent: boolean;
}

function evalBinaryOperands(
  entity: Entity,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): Operands | ComputeError {
  return evalOperandPair(
    Ecf.requireBytes(entity.data, "left"),
    Ecf.requireBytes(entity.data, "right"),
    scope,
    budget,
    ctx,
  );
}

/**
 * The same pair, addressed by HASH rather than by field.
 *
 * Factored out for §3.5's `builtins/{arithmetic,compare}` aliases, which carry their
 * operands in `apply.args` instead of in the inline expression's own fields. **Rule
 * 11's unsigned intent still comes off the resolved OPERAND ENTITY**, which is why the
 * alias can share this function at all: the rule is about the expression graph, and
 * `args.left` names the same entity the inline `left` field would.
 */
function evalOperandPair(
  leftHash: Uint8Array,
  rightHash: Uint8Array,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): Operands | ComputeError {
  const leftTarget = resolveOrError(leftHash, ctx, "left operand");
  if (leftTarget instanceof ComputeError) return leftTarget;
  const leftUnsigned = isDirectUintCast(leftTarget);
  const left = evaluate(leftTarget, scope, budget, ctx);
  if (isError(left)) return asComputeError(left);

  const rightTarget = resolveOrError(rightHash, ctx, "right operand");
  if (rightTarget instanceof ComputeError) return rightTarget;
  const rightUnsigned = isDirectUintCast(rightTarget);
  const right = evaluate(rightTarget, scope, budget, ctx);
  if (isError(right)) return asComputeError(right);

  return { left, right, unsignedIntent: leftUnsigned || rightUnsigned };
}

/**
 * §4.1's `compute/logic`, addressed by hash so §3.5's `builtins/logic` alias shares it.
 *
 * `not` returns BEFORE `right` is resolved — §4.1's ordering, and it is why `right` is
 * optional on the type. Resolving it first would turn a well-formed `not` with no
 * `right` into a `not_found`.
 *
 * `and`/`or` are **NOT short-circuiting**, and that is the spec's shape rather than an
 * oversight: §4.1 evaluates both operands and then combines. Short-circuiting would
 * change the observable step count, which §4.2 makes a cross-impl determinism surface.
 */
function applyLogic(
  op: string,
  leftHash: Uint8Array,
  rightHash: Uint8Array | null,
  scope: Scope,
  budget: Budget,
  ctx: EvalContext,
): InnerResult {
  const leftTarget = resolveOrError(leftHash, ctx, "logic left");
  if (isError(leftTarget)) return leftTarget;
  const left = evaluate(leftTarget as Entity, scope, budget, ctx);
  if (isError(left)) return left;
  if (op === "not") return codec.ecfBool(!truthy(left));

  if (rightHash === null) {
    return err(CODE_INVALID_EXPRESSION, "compute/logic '" + op + "' requires a right operand");
  }
  const rightTarget = resolveOrError(rightHash, ctx, "logic right");
  if (isError(rightTarget)) return rightTarget;
  const right = evaluate(rightTarget as Entity, scope, budget, ctx);
  if (isError(right)) return right;

  if (op === "and") return codec.ecfBool(truthy(left) && truthy(right));
  if (op === "or") return codec.ecfBool(truthy(left) || truthy(right));
  return err(CODE_INVALID_EXPRESSION, "compute/logic op must be and|or|not, got: " + op);
}

/** §2.2 rule 11's "the cast is the direct operand entity of that operation". */
function isDirectUintCast(operand: Entity): boolean {
  if (operand.type !== NUMERIC_CAST) return false;
  return Ecf.optText(operand.data, "to_type") === "primitive/uint";
}

/**
 * Narrow an `is_error`-true value to a `ComputeError`.
 *
 * The kind-based predicate is true for BOTH the in-flight class and a `compute/error`
 * ENTITY that evaluated successfully (§4.1's opening MUST). Only the first is already
 * a `ComputeError`, so a caller that has to return one has to convert — and the
 * conversion reads the entity's `code`, which is §2.4's only materialized field.
 */
function asComputeError(v: EvalValue | ComputeError): ComputeError {
  if (v instanceof ComputeError) return v;
  const ent = v instanceof ConstructedValue ? v.entity : v;
  const code =
    ent instanceof Entity ? (Ecf.optText(ent.data, "code") ?? CODE_INVALID_EXPRESSION) : CODE_INVALID_EXPRESSION;
  return new ComputeError(code, "evaluated to a stored compute/error");
}

/**
 * §4.1's `apply_arithmetic`, normative (v3.6 A1).
 *
 * **The float-promotion test runs BEFORE the numeric test**, exactly as the
 * pseudocode has it. Reordering them changes nothing observable today but is the
 * kind of local tidy-up that stops matching the corpus when a case is added.
 *
 * The `div` ladder is the one worth reading twice: integer division by zero is
 * `division_by_zero`, but FLOAT division by zero is IEEE-754 (`±Inf`/`NaN`) and is
 * NOT an error. An exact integer quotient stays an integer; an inexact one promotes
 * to float. Three behaviours behind one operator.
 */
function applyArithmetic(op: string, ops: Operands): EvalValue | ComputeError {
  const { left, right, unsignedIntent } = ops;
  const floatMode = isFloat(left) || isFloat(right);

  if (!isNumeric(left) || !isNumeric(right)) {
    return err(CODE_TYPE_MISMATCH, "Arithmetic requires numeric operands");
  }

  if (floatMode) {
    const l = toFloat(left);
    const r = toFloat(right);
    switch (op) {
      case "add": return codec.ecfFloat(l + r);
      case "sub": return codec.ecfFloat(l - r);
      case "mul": return codec.ecfFloat(l * r);
      // IEEE-754 division, including by zero — NOT division_by_zero (§4.1).
      case "div": return codec.ecfFloat(l / r);
      case "mod":
        if (r === 0) return err(CODE_DIVISION_BY_ZERO, "Modulo by zero");
        return codec.ecfFloat(truncatedRemainderFloat(l, r));
      default:
        return err(CODE_INVALID_EXPRESSION, "compute/arithmetic op must be one of add|sub|mul|div|mod, got: " + op);
    }
  }

  // ── §2.2 rules 8 / 10 / 11, and the split is the part that is easy to miss ──
  //
  // `add`/`sub`/`mul` are SIGN-AGNOSTIC: they operate on 64-bit two's-complement bit
  // patterns and the interpretation of the operands does not matter. `div`/`mod` (and
  // the ordering comparisons, see applyCompare) are SIGNED-DEFAULT: an operand whose
  // magnitude is >= 2^63 is read as its negative counterpart, UNLESS the operation
  // carries rule 11's unsigned intent.
  //
  // We had this wrong: operands were used at their raw magnitude, so
  // `div(2^64 - 2, 2)` answered 2^63 - 1 where the spec says -1 (`int64(2^64-2)` is
  // -2). Four oracle checks caught it — the `v316`/`v317` cast-indirection family,
  // which exists precisely because rule 11 is about the expression graph rather than
  // about the value.
  const rawL = intValue(left as codec.EcfInt);
  const rawR = intValue(right as codec.EcfInt);

  switch (op) {
    case "add": return codec.ecfInt(wrap64(rawL + rawR));
    case "sub": return codec.ecfInt(wrap64(rawL - rawR));
    case "mul": return codec.ecfInt(wrap64(rawL * rawR));
    case "div": {
      const [l, r] = unsignedIntent ? [asUnsigned64(rawL), asUnsigned64(rawR)] : [toSigned64(rawL), toSigned64(rawR)];
      if (r === 0n) return err(CODE_DIVISION_BY_ZERO, "Division by zero");
      if (l % r === 0n) return codec.ecfInt(wrap64(l / r));
      return codec.ecfFloat(Number(l) / Number(r));
    }
    case "mod": {
      const [l, r] = unsignedIntent ? [asUnsigned64(rawL), asUnsigned64(rawR)] : [toSigned64(rawL), toSigned64(rawR)];
      if (r === 0n) return err(CODE_DIVISION_BY_ZERO, "Modulo by zero");
      // TRUNCATED remainder (§4.1 `truncated_remainder`), which is JS/BigInt `%`
      // semantics and is NOT Python's floored `%`. The two differ in sign whenever the
      // operands' signs differ — a silent cross-port divergence if the python port
      // reaches for its own operator.
      return codec.ecfInt(wrap64(l % r));
    }
    default:
      return err(CODE_INVALID_EXPRESSION, "compute/arithmetic op must be one of add|sub|mul|div|mod, got: " + op);
  }
}

/** §2.2 rule 10 — read a 64-bit pattern by its SIGNED interpretation. */
function toSigned64(v: bigint): bigint {
  const M = 1n << 64n;
  const m = ((v % M) + M) % M;
  return m >= 1n << 63n ? m - M : m;
}

/** §2.2 rule 11 — read the same pattern by its UNSIGNED interpretation. */
function asUnsigned64(v: bigint): bigint {
  const M = 1n << 64n;
  return ((v % M) + M) % M;
}

/**
 * §2.2 rule 8 — integer arithmetic wraps at 2⁶⁴.
 *
 * The value model carries a full unsigned-64 argument in a `bigint`, so a sum can
 * legitimately exceed the range the codec will encode. Wrapping here rather than
 * letting `ecfInt` throw is what makes overflow a VALUE rather than an exception.
 */
function wrap64(v: bigint): bigint {
  const M = 1n << 64n;
  if (v >= 0n) return v % M;
  const m = ((v % M) + M) % M;
  // Keep the two's-complement reading for a negative result in i64 range.
  return m >= 1n << 63n ? m - M : m;
}

function truncatedRemainderFloat(a: number, b: number): number {
  return a - Math.trunc(a / b) * b;
}

/**
 * §4.1's `apply_compare`, normative (v3.6 A2).
 *
 * `eq`/`neq` accept ANY operand types and answer `false`/`true` across type classes
 * rather than erroring — only the four ORDERING ops demand compatible operands. And
 * string ordering is **lexicographic UTF-8 byte order with no Unicode
 * normalization**, so this cannot use JavaScript's `<` on strings, which compares
 * UTF-16 code units: the two disagree for anything above U+FFFF.
 */
function applyCompare(op: string, ops: Operands): EvalValue | ComputeError {
  const { left, right, unsignedIntent } = ops;

  if (op === "eq" || op === "neq") {
    const same = sameTypeClass(left, right) && valueEquals(left, right);
    return codec.ecfBool(op === "eq" ? same : !same);
  }
  if (op !== "lt" && op !== "gt" && op !== "lte" && op !== "gte") {
    return err(CODE_INVALID_EXPRESSION, "compute/compare op must be one of eq|neq|lt|gt|lte|gte, got: " + op);
  }

  if (!isNumeric(left) || !isNumeric(right)) {
    if (isText(left) && isText(right)) {
      const cmp = byteCompare(left.value, right.value);
      return codec.ecfBool(order(op, cmp));
    }
    return err(CODE_TYPE_MISMATCH, "Ordering comparison requires numeric or string operands");
  }

  if (isFloat(left) || isFloat(right)) {
    const l = toFloat(left);
    const r = toFloat(right);
    const cmp = l < r ? -1 : l > r ? 1 : 0;
    // NaN is unordered: every ordering comparison against it is false, which the
    // `l < r ? ... : 0` collapse above would report as "equal". Handled explicitly.
    if (Number.isNaN(l) || Number.isNaN(r)) return codec.ecfBool(false);
    return codec.ecfBool(order(op, cmp));
  }

  // §10.1: `div`/`mod`/`compare` are SIGNED-DEFAULT, with rule 11's unsigned intent
  // read off the operand entity rather than off either value.
  const rawL = intValue(left as codec.EcfInt);
  const rawR = intValue(right as codec.EcfInt);
  const [l, r] = unsignedIntent ? [asUnsigned64(rawL), asUnsigned64(rawR)] : [toSigned64(rawL), toSigned64(rawR)];
  const cmp = l < r ? -1 : l > r ? 1 : 0;
  return codec.ecfBool(order(op, cmp));
}

/** The four ordering ops over a three-way comparison result. */
function order(op: string, cmp: number): boolean {
  switch (op) {
    case "lt": return cmp < 0;
    case "gt": return cmp > 0;
    case "lte": return cmp <= 0;
    default: return cmp >= 0;
  }
}

/** §4.1 — numerics are one class; otherwise the primitive types must match. */
function sameTypeClass(a: EvalValue, b: EvalValue): boolean {
  if (isNumeric(a) && isNumeric(b)) return true;
  if (isEntityLike(a) || isEntityLike(b)) {
    return isEntityLike(a) && isEntityLike(b);
  }
  return a.kind === b.kind;
}

function valueEquals(a: EvalValue, b: EvalValue): boolean {
  if (isEntityLike(a) && isEntityLike(b)) {
    // §2.3 — identity is the MATERIALIZED hash. Reading it off the in-flight form
    // would make an implementation-private representation decide equality, which is
    // the same thing §3.5 forbids for a `group-by` key.
    return entityIdentity(a) === entityIdentity(b);
  }
  if (isEntityLike(a) || isEntityLike(b)) return false;
  if (isNumeric(a) && isNumeric(b)) {
    if (isInt(a) && isInt(b)) return intValue(a) === intValue(b);
    return toFloat(a) === toFloat(b);
  }
  switch (a.kind) {
    case "text": return isText(b) && a.value === b.value;
    case "bool": return b.kind === "bool" && a.value === b.value;
    case "null": return b.kind === "null";
    case "bytes":
      return b.kind === "bytes" && hexOf(a.value) === hexOf(b.value);
    default:
      // Arrays and maps compare by canonical encoding — the only definition that
      // agrees with content addressing.
      return hexOf(Ecf.encodeEcf(a)) === hexOf(Ecf.encodeEcf(b));
  }
}

/** Lexicographic UTF-8 BYTE order. Not `<` on JS strings, which is UTF-16 units. */
function byteCompare(a: string, b: string): number {
  const enc = new TextEncoder();
  const ba = enc.encode(a);
  const bb = enc.encode(b);
  const n = Math.min(ba.length, bb.length);
  for (let i = 0; i < n; i += 1) {
    if (ba[i] !== bb[i]) return (ba[i] as number) - (bb[i] as number);
  }
  return ba.length - bb.length;
}

/**
 * §4.1 `compute/field`, with §2.3 N3's kind rule.
 *
 * **Navigation is by KIND, never by shape.** An `Entity` navigates its `.data`; a
 * record value navigates flat. N3 explicitly forbids distinguishing the two by
 * inspecting keys — a `{type, data}` record is a legitimate record and a heuristic
 * misfires on it. Here the distinction is carried by the TypeScript type, which is
 * the strongest form the rule can take: there is no shape test to get wrong.
 */
function navigateField(target: EvalValue, name: string): EvalValue | ComputeError {
  // ── §2.3, the IN-FLIGHT half — and the two halves are one sentence read from two
  // sides. On a value whose field KINDS are still known, navigation composes and
  // returns the typed value; on a bare materialized entity, a `system/hash` field
  // yields the hash and the caller follows it with `compute/lookup/hash`. The oracle
  // has a vector for each (`v319c_construct_navigation_chain` and
  // `v319c_readback_navigation_returns_hash`), and they are the reason both branches
  // exist rather than one auto-resolving heuristic that would pass one and fail the
  // other. **No shape test decides which branch runs**: the discriminator is the
  // TypeScript type, so N3's forbidden byte-length sniff has nowhere to live.
  if (target instanceof ConstructedValue) {
    if (!target.fields.has(name)) return err(CODE_NOT_FOUND, "Field not found: " + name);
    return target.fields.get(name) as EvalValue;
  }
  const container = target instanceof Entity ? target.data : target;
  if (container instanceof Entity || container.kind !== "map") {
    return err(CODE_TYPE_MISMATCH, "Field access requires an entity or record, got: " + describe(target));
  }
  const found = Ecf.field(container, name);
  if (found === null) return err(CODE_NOT_FOUND, "Field not found: " + name);
  return found;
}

function asArrayValue(v: EvalValue): readonly EcfValue[] | null {
  if (!isPlainValue(v)) return null;
  return v.kind === "array" ? v.items : null;
}

/** §2.2 N.1 — `compute/index`, with §9.1's `index_out_of_range`. */
function indexInto(arr: EvalValue, idx: EvalValue): EvalValue | ComputeError {
  const items = asArrayValue(arr);
  if (items === null) return err(CODE_TYPE_MISMATCH, "compute/index requires an array");
  if (!isInt(idx)) return err(CODE_TYPE_MISMATCH, "compute/index requires an integer index");
  const i = intValue(idx);
  // §2.2's cross-impl ruling: an out-of-domain MAGNITUDE is not a type error. A
  // negative index is `index_out_of_range`, never `type_mismatch`.
  if (i < 0n || i >= BigInt(items.length)) {
    return err(CODE_INDEX_OUT_OF_RANGE, "Index out of range: " + i.toString());
  }
  return items[Number(i)] as EcfValue;
}

/**
 * §2.2 N.1 — `compute/length`, over an ARRAY and nothing else.
 *
 * The first draft also accepted a string, which looked like a kindness and was an
 * invented semantic: §2.2's field is `array: {type_ref: "system/hash"} ; Hash of array
 * expression`, and the oracle's `v314_length_type_mismatch` asserts that
 * `length("hello")` is `type_mismatch`. A port that answers 5 there is more useful and
 * less interoperable, which is the trade this repo does not get to make.
 */
function lengthOf(v: EvalValue): EvalValue | ComputeError {
  const items = asArrayValue(v);
  if (items === null) return err(CODE_TYPE_MISMATCH, "compute/length requires an array");
  return codec.ecfInt(BigInt(items.length));
}

/**
 * §2.2 N.4 — `compute/numeric-cast`, with §9.1's `cast_out_of_range`.
 *
 * §2.2 rule 11 (v3.17 SA-AMD3-1) makes the float→integer failure modes explicit and
 * they are all one code: out of range, `NaN`, and `±Inf`.
 */
function numericCast(value: EvalValue, toType: string): EvalValue | ComputeError {
  if (!isNumeric(value)) return err(CODE_TYPE_MISMATCH, "compute/numeric-cast requires a numeric value");

  if (toType === "primitive/float") {
    return codec.ecfFloat(toFloat(value));
  }
  if (toType === "primitive/int" || toType === "primitive/uint") {
    let n: bigint;
    if (isInt(value)) {
      n = intValue(value);
    } else {
      const f = (value as codec.EcfFloat).value;
      if (Number.isNaN(f) || !Number.isFinite(f)) {
        return err(CODE_CAST_OUT_OF_RANGE, "Cast of NaN or Inf to integer");
      }
      n = BigInt(Math.trunc(f));
      // §2.2 rule 11: only the FLOAT source can be out of range. An INTEGER source is a
      // 64-bit pattern being REINTERPRETED, which is always representable — but a float
      // is a VALUE being converted, so a negative one has no `primitive/uint` to land
      // in. `cast(-1.5, uint)` is `cast_out_of_range` while `cast(-1, uint)` is
      // 2^64 - 1, and the difference is the source kind rather than the sign.
      const limit = toType === "primitive/uint" ? 1n << 64n : 1n << 63n;
      if (n >= limit || n < (toType === "primitive/uint" ? 0n : -limit)) {
        return err(CODE_CAST_OUT_OF_RANGE, "Cast target cannot represent " + n.toString());
      }
    }
    // ** A NEGATIVE INTEGER CAST TO uint IS NOT AN ERROR. ** Rule 11's parenthetical is
    // explicit: "a standalone or indirected `numeric-cast -> uint` reinterprets the bits
    // and yields the non-negative MAGNITUDE... the `v314_cast_int_to_uint_negative`
    // vector confirms `cast(-1, uint)` -> 2^64 - 1". The first draft returned
    // `cast_out_of_range` here, which is the C-programmer's instinct and is a different
    // language: compute integers are bit patterns and `int`/`uint` are annotations.
    return codec.ecfInt(toType === "primitive/uint" ? asUnsigned64(n) : toSigned64(n));
  }
  return err(CODE_TYPE_MISMATCH, "compute/numeric-cast target is not a numeric primitive: " + toType);
}

function describe(v: EvalValue): string {
  if (v instanceof ConstructedValue) return "in-flight entity " + v.entity.type;
  return v instanceof Entity ? "entity " + v.type : v.kind;
}

// ── paths ───────────────────────────────────────────────────────────────────────

/**
 * V7 §5.4 canonicalization, as §2.1 requires it: a peer-relative path is qualified
 * to the local peer's namespace; an already-absolute path is used as-is.
 *
 * §2.1's own parenthetical says why this is not optional: *"storing the verbatim
 * peer-relative string instead is a silent footgun — the dependency `app/x` never
 * matches a write to the canonical `/{local_peer_id}/app/x`, and the reactive
 * subgraph never recomputes."* The SAME function must run at resolution and at
 * dependency registration, which is why `registerDependency` is called with the
 * canonicalized value above and never with the raw one.
 */
export function canonicalize(path: string, localPeerId: string): string {
  return path.startsWith("/") ? path : "/" + localPeerId + "/" + path;
}

/** §2.1's `clean_path` for the relative form — collapse `.`/`..` and empty segments. */
export function cleanPath(path: string): string {
  const absolute = path.startsWith("/");
  const out: string[] = [];
  for (const seg of path.split("/")) {
    if (seg === "" || seg === ".") continue;
    if (seg === "..") {
      out.pop();
      continue;
    }
    out.push(seg);
  }
  return (absolute ? "/" : "") + out.join("/");
}

export function hexOf(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += b.toString(16).padStart(2, "0");
  return s;
}
