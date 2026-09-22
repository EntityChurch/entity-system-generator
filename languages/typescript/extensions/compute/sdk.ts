/**
 * COMPUTE — the in-process SDK surface.
 *
 * Same rule as CONTENT and HISTORY: there is no conformance gate on this face and
 * per the operator that is correct, so **the extension is the instrument** — the
 * handler's own wire-gated path runs THROUGH this class rather than beside it, and
 * so does the H7 evaluator seam. Two consumers, one implementation; if this surface
 * were wrong the `compute` category would say so.
 *
 * **This is also the file that owns §4's override prohibition**, which as of v3.29
 * is ours to enforce and was not before. See {@link assertNotBuiltinOverride}.
 */

import {
  Ecf,
  Entity,
  type ContentStore,
  type EntityTree,
  type codec,
} from "entity-core-protocol-typescript";

import {
  BUILTINS_PREFIX,
  DEFAULT_MAX_DEPTH,
  DEFAULT_MAX_OPS,
} from "./types.js";
import {
  ComputeError,
  emptyScope,
  evaluate,
  isError,
  materialize,
  type Budget,
  type EvalContext,
} from "./internal/evaluator.js";

/** §9.3's two peer-wide defaults, as a value rather than as two arguments. */
export interface EvaluatorLimits {
  readonly maxOperations: number;
  readonly maxDepth: number;
}

export const DEFAULT_LIMITS: EvaluatorLimits = {
  maxOperations: DEFAULT_MAX_OPS,
  maxDepth: DEFAULT_MAX_DEPTH,
};

/**
 * The subset of the peer this extension reads.
 *
 * Declared structurally rather than as `Peer`, because the H7 evaluator seam and the
 * handler path reach the same services from two different objects (`HandlerContext.peer`
 * is `PeerServices`, and the composition holds a `Peer`). Naming the four members we
 * actually use is what lets one implementation serve both without either caller
 * widening what it hands us.
 */
export interface ComputePeerServices {
  readonly tree: EntityTree;
  readonly contentStore: ContentStore;
  readonly localPeerId: string;
}

/**
 * What an evaluation produced. Exactly one of the two fields is non-null.
 *
 * **`value` is the MATERIALIZED form and never an in-flight one** (§2.3, v3.19c
 * option α). This interface is the compute→non-compute crossing for both of this
 * extension's consumers — the handler's `eval` and the H7 evaluator seam — so it is
 * the one place the boundary has to be enforced, and enforcing it here is why
 * neither consumer had to learn what an in-flight value is.
 */
export interface EvalOutcome {
  readonly value: codec.EcfValue | Entity | null;
  readonly error: ComputeError | null;
  /** Steps actually charged — `maxOperations` minus what is left. §4.2's counter. */
  readonly operationsUsed: number;
}

export interface EvaluateOptions {
  /** §3.2's `params.budget` knob. `null` means the caller did not ask. */
  readonly budget?: number | null;
  /** §4.2 Tier 0 — the `content_store_access` allowance. Default false. */
  readonly contentStoreAccess?: boolean;
  /** §4.2 step 1 — the envelope's pre-authorized `included` map, keyed by hex hash. */
  readonly included?: ReadonlyMap<string, Entity>;
  /**
   * §4.2 Tier 2 — an installed subgraph's SEALED set, hex-encoded.
   *
   * Empty unless the caller is §7.2's reactive path, which is the only caller that
   * has one: the set is sealed by §3.3 Phase 2b and lives on the subgraph metadata.
   * An earlier draft of this class passed the ENCOUNTERED set here, which would have
   * made every hash an evaluation happened to write Tier-2 authorized — an
   * authorization tier admitting whatever the program itself produced.
   */
  readonly authorizedDataHashes?: ReadonlySet<string>;
  /**
   * §4.1 / §6.3 — the two path predicates, when the caller HOLDS a capability object.
   *
   * **Default `() => true`, and that default is the declared substrate gap rather
   * than an oversight.** On the explicit-eval path this port has no capability object
   * to narrow with: `HandlerContext.callerCapability` is a token and the peer exposes
   * no path-scope predicate an extension can call — so §6.2 is satisfied at the
   * DISPATCH boundary and not per tree read. See
   * {@link CAPABILITY_CHECK_IS_DISPATCH_SCOPED}.
   *
   * §7.2's reactive path is different in kind and that is why these are parameters:
   * it evaluates under the INSTALLATION GRANT, which is an entity it fetched from the
   * content store, so it can and does answer both per path. One port, two authority
   * models, because the spec gives the two paths two authorities.
   */
  readonly canReadPath?: (path: string) => boolean;
  readonly canWritePath?: (path: string) => boolean;
  /**
   * §3.2 E1 — scope bindings pre-populated by a dispatch layer (`operation`, `params`,
   * `resource`, `caller_capability` for an entity-native body). Empty by default. A binding
   * carries no authority: it is a value an expression can read through `compute/lookup/scope`.
   */
  readonly bindings?: ReadonlyMap<string, codec.EcfValue | Entity>;
}

/**
 * The evaluator, as an in-process object.
 *
 * One instance per evaluation is the intended use — it carries the encountered-hash
 * set, which §4.2 scopes to a single evaluation. Reusing one across evaluations would
 * widen `resolve()`'s reach past what the section allows, which is the kind of change
 * that makes more programs work and is still wrong.
 */
export class ComputeEvaluator {
  readonly #peer: ComputePeerServices;
  readonly #limits: EvaluatorLimits;
  readonly #encountered = new Set<string>();
  readonly #dependencies = new Set<string>();

  constructor(peer: ComputePeerServices, limits: EvaluatorLimits = DEFAULT_LIMITS) {
    this.#peer = peer;
    this.#limits = limits;
  }

  /** Paths §7.1 would register as reactive dependencies. Read after an evaluation. */
  get dependencies(): readonly string[] {
    return [...this.#dependencies];
  }

  /**
   * Evaluate `expression`, with `subgraphRoot` as the base for `relative: true` paths.
   *
   * **`subgraphRoot` is a required parameter and not a default**, because §2.1 gives
   * it two different sources — the expression URI for an explicit eval, the subgraph
   * metadata's `root_expression_path` for a reactive one — and "same value, different
   * source" is exactly the kind of sentence that becomes a bug when one caller is
   * allowed to omit it.
   */
  evaluateAt(expression: Entity, subgraphRoot: string, options: EvaluateOptions = {}): EvalOutcome {
    // §5.2's minimum rule, in the one place it can be applied: the caller's ask and
    // the peer default, whichever is smaller. A caller cannot raise its own ceiling.
    const asked = options.budget ?? null;
    const operations =
      asked === null ? this.#limits.maxOperations : Math.min(asked, this.#limits.maxOperations);

    const budget: Budget = { operations, depth: this.#limits.maxDepth };
    const ctx = this.#context(subgraphRoot, options);

    const scope = emptyScope();
    for (const [name, value] of options.bindings ?? []) scope.bindings.set(name, value);
    const out = evaluate(expression, scope, budget, ctx);
    const used = operations - budget.operations;

    if (isError(out)) {
      // `isError` is kind-based (§4.1), so this catches BOTH an in-flight
      // ComputeError and a compute/error entity that evaluated successfully. The
      // second is why the branch converts rather than casting.
      const error =
        out instanceof ComputeError
          ? out
          : new ComputeError(readErrorCode(out), "evaluated to a stored compute/error");
      return { value: null, error, operationsUsed: used };
    }
    // §2.3 / v3.19c option α — THE BOUNDARY. Everything above this line may be an
    // in-flight typed value; nothing below it is. `materialize` also stores what the
    // bare form references, which is the half of the rule that is easy to drop: a
    // returned entity whose `system/hash` field points at nothing the store has is a
    // reference the caller cannot follow, and no vector for that failure exists.
    return { value: materialize(out, ctx), error: null, operationsUsed: used };
  }

  #context(subgraphRoot: string, options: EvaluateOptions): EvalContext {
    const peer = this.#peer;
    const encountered = this.#encountered;
    const dependencies = this.#dependencies;
    return {
      tree: peer.tree,
      contentStore: peer.contentStore,
      localPeerId: peer.localPeerId,
      subgraphRoot,
      included: options.included ?? new Map(),
      hasContentStoreAccess: options.contentStoreAccess === true,
      // §4.2 TIER 2 — empty on the explicit-eval path and the SEALED set on the
      // reactive one. The default is empty rather than "whatever this evaluation has
      // touched": an earlier draft passed the ENCOUNTERED set, which would have made
      // every hash the program itself produced Tier-2 authorized.
      //
      // `markEncountered` still feeds nothing here, and that is also deliberate:
      // §10.1's encountered-during-read guarantee is scoped to compute-typed
      // entities, which Tier 1 already admits. The set is kept so the call sites
      // match §4.4/§4.3 N6.
      authorizedDataHashes: options.authorizedDataHashes ?? new Set<string>(),
      canReadPath: options.canReadPath ?? (() => true),
      // §6.3's `store` write. A distinct member rather than an alias of
      // `canReadPath` because §6.3 gives the two different authorities — a tree READ
      // rides `ctx.capability` and a `store` WRITE rides the caller's with the
      // handler forbidden from substituting its own grant (no silent escalation) —
      // and §7.2 is the caller that supplies two different answers.
      canWritePath: options.canWritePath ?? (() => true),
      registerDependency: (path: string) => {
        dependencies.add(path);
      },
      markEncountered: (hex: string) => {
        encountered.add(hex);
      },
    };
  }
}

/**
 * §6.2's capability check — **which of this extension's entry points narrows per tree
 * read, and which cannot.**
 *
 * §4.1 guards `compute/lookup/tree` with
 * `check_path_permission("get", path, ctx.capability, "system/tree", ...)`. There are
 * three ways into this evaluator and they do not get the same answer, which is D13's
 * face amendment applied one level down — to the *caller*, not the peer:
 *
 * | entry point | capability object | §6.2 |
 * |---|---|---|
 * | `system/compute:eval` (handler) | `HandlerContext.callerCapability` | **per tree read** |
 * | §7.2 reactive re-evaluation | the installation grant, from the store | **per tree read** |
 * | the H7 evaluator seam | none — `ExpressionRequest` carries the `Execute`, not a verified token | dispatch-scoped |
 *
 * **THIS CONSTANT USED TO READ `true` AND THE REASON IT WAS WRONG IS WORTH KEEPING.**
 * It was `true` because a contract in this tree stated that the peer exposed no
 * path-scope predicate an extension could call. It does:
 * `Permissions.checkPathPermission` is public, takes a `CapabilityToken`, and is the
 * primitive this repo itself routed to keystone as **H9** — closed, landed, and on
 * our own tracker. The gap was never in the substrate; it was a source read nobody
 * re-ran against the tree it described (D12 / L8).
 *
 * It stays exported, and false, because the third row is still true and an inline
 * `() => true` on that path would be the same behaviour with nothing to grep for.
 */
export const CAPABILITY_CHECK_IS_DISPATCH_SCOPED = false;

/**
 * §4's override prohibition — **ours to enforce as of v3.29, and it was not before.**
 *
 * Through v3.28 §3.5 described this rule as *"a subset of"* core's `system/*`
 * reservation and told implementers that enforcing that reservation needed *"no
 * separate compute-specific guard."* `ENTITY-CORE-PROTOCOL` 0.8.2.13 **withdrew the
 * reservation**, so v3.29 restates the prohibition on its own basis: it binds **every
 * installation path** because it is a cross-peer determinism requirement, not a
 * namespace policy. Two peers disagreeing about what `"add"` means is an interop
 * failure — which is precisely what an installed evaluator could cause, since the H7
 * seam hands it every body the built-in path refuses.
 *
 * There is now nothing upstream that refuses a registration at
 * `system/compute/builtins/*` on our behalf, so this function is the enforcement
 * point, and it is called from {@link installCompute}'s path rather than left as
 * documentation.
 */
export function assertNotBuiltinOverride(pattern: string): void {
  const relative = pattern.startsWith("/") ? pattern.slice(pattern.indexOf("/", 1) + 1) : pattern;
  if (relative === BUILTINS_PREFIX || relative.startsWith(BUILTINS_PREFIX + "/")) {
    throw new Error(
      `EXTENSION-COMPUTE §4: a handler MUST NOT be registered at ${pattern}. ` +
        "The builtin handlers are the cross-peer determinism floor; overriding one " +
        "makes two peers disagree about what an operation means. (v3.29 — this rule " +
        "no longer delegates to the withdrawn core system/* reservation.)",
    );
  }
}

function readErrorCode(value: unknown): string {
  // A `compute/error` with no readable `code` is malformed. Saying so with the
  // §9.1 code for a malformed expression beats inventing a plausible one.
  //
  // `unknown` rather than `Entity`, because `isError` is kind-based and admits an
  // in-flight construct whose `entity_type` is `compute/error` as well as a stored
  // one (§2.4 — the disposition must not depend on which form arrived).
  const entity =
    value instanceof Entity
      ? value
      : ((value as { entity?: Entity }).entity ?? null);
  if (entity === null) return "invalid_expression";
  return Ecf.optText(entity.data, "code") ?? "invalid_expression";
}
