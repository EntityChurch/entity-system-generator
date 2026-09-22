/**
 * `@entity-core/extension-compute` — COMPUTE v3.29 for the `typescript` peer.
 *
 * THE PUBLIC ENTRY POINT, and what is absent is as deliberate as what is present:
 * `internal/evaluator.js` is not re-exported and `package.json`'s `exports` map
 * refuses a deep import into it. A caller able to reach `evaluate` directly could
 * run an expression with an `EvalContext` of its own construction — including
 * `hasContentStoreAccess: true`, which is §4.2's Tier 0 and turns the evaluator into
 * the content-store oracle §4.2 exists to prevent.
 *
 * **THIS EXTENSION HAS A FIFTH FACE, AND IT IS THE FIRST ONE IN THE CORPUS.**
 * `DESIGN-THE-SDK-LAYER` §1 names four — `types` · `handler` · `emit_consumer` ·
 * `sdk` — and D13's face amendment pins that vocabulary because a seam claim naming
 * a peer without naming a face is a category error. COMPUTE installs a fifth:
 * **the expression evaluator**, through `Peer.setExpressionEvaluator` (keystone's H7,
 * which this repo routed on 2026-09-03 and which landed the same day).
 *
 * It is a face and not an implementation detail by D13's own test — it installs or it
 * does not, independently of the other four, through a seam of its own, and a peer
 * can host any subset. `rust` is the standing proof that faces get different answers
 * on one peer; here `handler` and `evaluator` are different seams into the same
 * dispatch path, and a peer with no `setExpressionEvaluator` hosts the first and not
 * the second. Recorded in `EXTENSION.toml [surfaces]` and routed as a vocabulary
 * question, because `tools/compose.py` validates `[system.faces]` against a
 * four-value list that does not have a word for this.
 */

import {
  Ecf,
  Entity,
  HandlerResult,
  type ExpressionEvaluator,
  type ExpressionRequest,
  type Peer,
  type codec,
} from "entity-core-protocol-typescript";

import { ComputeHandler, type ComputeHandlerOptions } from "./handler.js";
import { ComputeEvaluator, assertNotBuiltinOverride, type EvaluatorLimits } from "./sdk.js";
import { ReactiveEngine } from "./internal/reactive.js";
import {
  COMPUTE_PATTERN,
  DEFAULT_MAX_DEPTH,
  DEFAULT_MAX_OPS,
  RESULT,
  isComputeExpression,
  publishComputeTypes,
} from "./types.js";

export {
  // Type-path constants, FLAT — the cross-port CONTRACT. HISTORY settled this
  // (D16, `[sdk_surface]`): flat names are the contract in every port and a grouped
  // object is an alias, never the other way round. CONTENT paid 18 drift entries for
  // learning it the other way.
  LITERAL, LOOKUP_SCOPE, LOOKUP_TREE, LOOKUP_HASH, APPLY, IF, LET, LAMBDA,
  ARITHMETIC, COMPARE, LOGIC, FIELD, CONSTRUCT, INDEX, LENGTH, NUMERIC_CAST,
  CLOSURE, SCOPE, SCOPE_BINDING, RESULT, ERROR,
  SUBGRAPH, INSTALL_REQUEST, INSTALL_RESULT,
  MAP_ARGS, FILTER_ARGS, FOLD_ARGS, RANGE_ARGS, GROUP_BY_ARGS, GROUP,
  CONCAT_ARGS, ASSOC_ARGS, STORE_ARGS,
  CORE_EXPRESSION_TYPES, INLINE_EXPRESSION_TYPES, ALL_TYPES,
  COMPUTE_PATTERN, BUILTINS_PREFIX, PROCESSES_PREFIX,
  CODE_BUDGET_EXHAUSTED, CODE_DEPTH_EXCEEDED, CODE_TYPE_MISMATCH,
  CODE_DIVISION_BY_ZERO, CODE_NOT_FOUND, CODE_UNKNOWN_TYPE,
  CODE_MISSING_ARGUMENT, CODE_INVALID_EXPRESSION, CODE_CASCADE_LIMIT,
  CODE_PERMISSION_DENIED, CODE_INSTALLATION_GRANT_INVALID,
  CODE_INDEX_OUT_OF_RANGE, CODE_CAST_OUT_OF_RANGE, CODE_COUNT_OUT_OF_RANGE,
  CODE_SCOPE_UNREACHABLE, CODE_AMBIGUOUS_RESOURCE,
  DEFAULT_MAX_OPS, DEFAULT_MAX_DEPTH, RECOMMENDED_MAX_CASCADE_DEPTH,
  isComputeExpression, isComputeType,
  computeTypeDefs, computeTypeEntities, publishComputeTypes, computeEntity,
} from "./types.js";

export { ComputeHandler, type ComputeHandlerOptions } from "./handler.js";

/**
 * §7's engine, PUBLIC — and the reasoning is the mirror image of the evaluator's.
 *
 * `internal/evaluator.js` is module-private because `evaluate` takes its whole
 * authority as an argument: a caller constructs an `EvalContext` and sets
 * `hasContentStoreAccess: true`, which is §4.2 Tier 0. `ReactiveEngine` has no such
 * door — every re-evaluation reads its authority from the installation grant recorded
 * on the subgraph metadata, so a caller holding the engine can register a dependency
 * and trigger a re-evaluation, and neither widens what that evaluation may read.
 *
 * It is public because it IS the `emit_consumer` face's object, the same way
 * `HistoryRecorder` is HISTORY's, and an in-process embedder that wants reactive mode
 * without the wire needs to reach it. Declared in `[sdk_surface].required`.
 */
export { ReactiveEngine, deterministicId } from "./internal/reactive.js";

export {
  ComputeEvaluator,
  DEFAULT_LIMITS,
  assertNotBuiltinOverride,
  CAPABILITY_CHECK_IS_DISPATCH_SCOPED,
  type ComputePeerServices,
  type EvalOutcome,
  type EvaluateOptions,
  type EvaluatorLimits,
} from "./sdk.js";

export interface ComputeInstallation {
  readonly pattern: string;
  readonly interfacePath: string;
  readonly typePaths: readonly string[];
  /**
   * Whether the peer accepted an expression evaluator through the H7 seam.
   *
   * **Three-valued and OBSERVED, never declared.** HISTORY shipped a hardcoded
   * `contextAvailable = false` commented "measured", which was a claim about another
   * team's peer frozen in our source and asserted by our own tests; when the
   * substrate moved nothing could notice. This is read off the peer after the call:
   * `installed` when `peer.expressionEvaluator` comes back as the object we handed
   * it, `not-installable` when the seam is absent, `not-observed` when the seam
   * exists and the read-back does not agree.
   */
  readonly evaluatorFace: "installed" | "not-installable" | "not-observed";
  /** §7's engine — the `emit_consumer` face, and the owner of the dependency index. */
  readonly engine: ReactiveEngine;
  /** §7.1's rebuild count: subgraphs re-registered from `system/compute/processes/*`. */
  readonly rebuilt: number;
}

/**
 * Install COMPUTE into a live peer: handler, types, and the H7 evaluator.
 *
 * **Order matters and is the same argument HISTORY's install makes.** The
 * §11.6.1 registration writes four tree entities, and type publication writes
 * thirty-three more; both are ordinary tree writes that any registered emit consumer
 * observes. COMPUTE registers none itself, but a composition that also installs
 * HISTORY would record all thirty-seven as transitions. Registering the evaluator
 * LAST is free here and keeps the pattern uniform.
 */
export function installCompute(peer: Peer, options: ComputeHandlerOptions = {}): ComputeInstallation {
  // §4's override prohibition, enforced before anything is written. As of v3.29 this
  // rule stands on its own — the core `system/*` reservation it used to delegate to
  // was withdrawn (0.8.2.13), so nothing upstream would refuse this on our behalf.
  // Checking our OWN pattern looks redundant and is not: it is the one call site that
  // a future change to `COMPUTE_PATTERN` would run through.
  assertNotBuiltinOverride(COMPUTE_PATTERN);

  const limits: EvaluatorLimits = {
    maxOperations: options.maxOperations ?? DEFAULT_MAX_OPS,
    maxDepth: options.maxDepth ?? DEFAULT_MAX_DEPTH,
  };
  // ONE engine, TWO halves: §3.3's Phase 4 runs through the handler and §7.2's
  // trigger runs through the emit bus, and they are the same object's two entry
  // points rather than two structures that have to agree about what is installed.
  const engine = new ReactiveEngine(peer, limits);

  peer.registerHandler(new ComputeHandler(options, engine));

  const interfacePath = "/" + peer.localPeerId + "/system/handler/" + COMPUTE_PATTERN;
  const typePaths = publishComputeTypes(peer.tree, peer.localPeerId);

  const evaluatorFace = installEvaluator(peer, options);

  // REGISTERED LAST, and HISTORY's install makes the same argument for the same
  // reason: everything above writes tree entities, and a consumer registered first
  // would observe this extension's own installation as a stream of transitions. Here
  // it is stronger than hygiene — COMPUTE's consumer WRITES BACK, so a §11.6.1
  // registration write arriving before the handler exists would re-enter an evaluator
  // with a half-built peer behind it.
  peer.emit.registerConsumer(engine);

  // §7.1's `rebuild_dependency_index`. Vacuous on a fresh peer and not vacuous in
  // general: a composition installed onto a peer whose tree was restored from
  // elsewhere has subgraphs in `system/compute/processes/` and an empty index, which
  // is precisely the state §7.1 MUSTs a rebuild for.
  const rebuilt = engine.rebuild();

  return { pattern: COMPUTE_PATTERN, interfacePath, typePaths, evaluatorFace, engine, rebuilt };
}

/**
 * The H7 seam: hand the peer an evaluator for entity-native handler bodies.
 *
 * `ENTITY-CORE-PROTOCOL` §6.6's dispatch evaluates the built-in `compute/literal`
 * shape in-process, then consults an installed evaluator, then answers
 * `501 unsupported_expression`. **That ordering is the whole safety argument**:
 * `core_register_body_binding` drives the literal path on every peer in the cohort,
 * so the literal floor is out of an evaluator's reach and installing one cannot move
 * a conformance result. Measured here on 2026-09-04 with five controls — scenario 3
 * of `languages/typescript/gates/host-seam/probe-entity-native.mjs`.
 *
 * **Returning `null` is how an evaluator DECLINES**, and declining is the common case
 * rather than an error path: a body this evaluator does not recognise falls through
 * to the peer's own `501`, so evaluators compose instead of each having to claim
 * every shape. We decline anything that is not a compute expression.
 *
 * **The seam is detected, not assumed.** `setExpressionEvaluator` is keystone's
 * addition and 45 of the 46 peers read `unknown` for it. A peer without the method
 * gets `not-installable` and everything else still installs — which is the D13 face
 * amendment applied to our own installer rather than only to our reports.
 */
function installEvaluator(
  peer: Peer,
  options: ComputeHandlerOptions,
): ComputeInstallation["evaluatorFace"] {
  // Structural detection rather than a version check. 45 of 46 peers read `unknown`
  // for this seam and a `[host]` profile value would be a claim we cannot make about
  // any of them; asking the object is the only thing that is true at runtime.
  const seam = peer as Peer & {
    setExpressionEvaluator?: (e: ExpressionEvaluator) => void;
    expressionEvaluator?: ExpressionEvaluator | null;
  };
  if (typeof seam.setExpressionEvaluator !== "function") {
    return "not-installable";
  }

  const limits: EvaluatorLimits = {
    maxOperations: options.maxOperations ?? DEFAULT_MAX_OPS,
    maxDepth: options.maxDepth ?? DEFAULT_MAX_DEPTH,
  };

  const evaluator: ExpressionEvaluator = {
    evaluate(request: ExpressionRequest): HandlerResult | null {
      // DECLINE anything that is not a compute expression. The peer's own
      // `501 unsupported_expression` then stands — which is a better answer than one
      // we invented about a body we do not understand, and it is what makes two
      // installed evaluators compose.
      if (!isComputeExpression(request.expression.type)) return null;

      // §3.2 E1 — the dispatch layer pre-populates `{operation, params, resource,
      // caller_capability}`. The first three come off the EXECUTE this peer hands us.
      // `caller_capability` binds null: `ExpressionRequest` carries no verified token on
      // this peer (`[substrate.evaluator_seam]`), and the EXECUTE's `capability` is a hash,
      // not the capability entity E1 names.
      const exec = request.execute;
      const bindings = new Map<string, codec.EcfValue | Entity>([
        ["operation", Ecf.text(exec.operation)],
        ["params", Ecf.field(exec.entity.data, "params") === null ? Ecf.nullValue : exec.params],
        ["resource", Ecf.field(exec.entity.data, "resource") ?? Ecf.nullValue],
        ["caller_capability", Ecf.nullValue],
      ]);

      // A fresh evaluator per dispatch: §4.2 scopes the encountered set to one
      // evaluation, so a shared instance would widen `resolve()`'s reach across
      // unrelated requests.
      const outcome = new ComputeEvaluator(peer, limits).evaluateAt(
        request.expression,
        request.expressionPath,
        { bindings },
      );

      // §3.2 E1 — "the result is unwrapped at the dispatch boundary": `compute/result` →
      // its value; `compute/error` → the result entity at 200 (F10, a program that RAN and
      // produced an error is not a transport failure); a bare primitive →
      // `{type: "primitive/any", data}`; an entity → as-is. This used to return a
      // `compute/result` wrapper, which is what the peer's own literal floor still does
      // (keystone's, routed).
      if (outcome.error !== null) return HandlerResult.ok(outcome.error.toEntity());
      const value = outcome.value;
      if (value instanceof Entity && value.type !== RESULT) return HandlerResult.ok(value);
      const bare = value instanceof Entity ? (Ecf.field(value.data, "value") ?? Ecf.nullValue) : value;
      return HandlerResult.ok(Entity.create("primitive/any", bare ?? Ecf.nullValue));
    },
  };

  seam.setExpressionEvaluator(evaluator);
  // READ BACK, never assume. The one thing a setter cannot tell you is whether it
  // set anything — keystone planted exactly that defect against their own H7 work
  // (a setter writing nothing, shaped like `julia`'s dead register map), and D13's
  // Read layer exists because a call site is not a capability.
  return seam.expressionEvaluator === evaluator ? "installed" : "not-observed";
}
