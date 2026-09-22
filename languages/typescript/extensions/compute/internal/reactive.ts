/**
 * COMPUTE §7 — reactive mode: the dependency index (§7.1), the re-evaluation trigger
 * (§7.2) and the cascade bound (§7.3).
 *
 * **THE SIXTH FACE ARRIVES HERE, AND IT IS THE ONE THE OTHER FIVE COULD NOT SHOW.**
 * COMPUTE's `emit_consumer` face is not a recorder like HISTORY's — it is the seam by
 * which a tree write RE-ENTERS the evaluator and writes back. That makes two
 * properties of this peer load-bearing that no earlier composition depended on:
 *
 *  1. **Delivery is sync-inline.** `EmitBus` calls every consumer inside
 *     `EntityTree.put`, before it returns. So by the time the oracle's `tree:put` of
 *     `A1 = 25` has answered, `B1/result` already holds `50`. An async bus would make
 *     every §7.2 vector a race, and §7.2 pins no delivery mode — it is §9.4
 *     impl-defined. Declared in `[substrate.emit_delivery_is_sync_inline]`, because a
 *     peer that batches would need a different shape here and nothing in the spec
 *     would have warned us.
 *  2. **A write from inside a consumer re-enters the bus.** That is what makes a
 *     cascade a cascade (§7.2's *"subgraph A's result write notifies the emit
 *     pipeline, which triggers subgraph B"*) — and it is also why the bound in §7.3
 *     is not decoration: on this peer an unbounded cascade is unbounded RECURSION.
 *
 * **What is deliberately NOT here: a second evaluator.** Re-evaluation runs the same
 * {@link ComputeEvaluator} the handler's `eval` and the H7 seam run, with a different
 * authority and a different budget. §7.2's only semantic additions are the grant
 * check, the convergence check and the freeze; every one of those is in this file and
 * none of them is in the evaluator.
 */

import {
  Ecf,
  Entity,
  Permissions,
  CapabilityToken,
  crypto,
  type ContentStore,
  type ContentStoreEvent,
  type EmitConsumer,
  type EmitContext,
  type EntityTree,
  type PeerIdentity,
  type TreeChangeEvent,
  type codec,
} from "entity-core-protocol-typescript";

import {
  COMPUTE_PATTERN,
  CODE_CASCADE_LIMIT,
  CODE_INSTALLATION_GRANT_INVALID,
  ERROR,
  PROCESSES_PREFIX,
  RECOMMENDED_MAX_CASCADE_DEPTH,
  RESULT,
  SUBGRAPH,
  isComputeExpression,
} from "../types.js";
import { ComputeEvaluator, type EvaluatorLimits } from "../sdk.js";
import { AuditRefusal, auditSubgraph, type AuditContext, type SubgraphAudit } from "./subgraph.js";
import { canonicalize, hexOf } from "./evaluator.js";

/** The peer surface reactive mode needs. A superset of `ComputePeerServices`. */
export interface ReactivePeerServices {
  readonly tree: EntityTree;
  readonly contentStore: ContentStore;
  readonly localPeerId: string;
  readonly localIdentity: PeerIdentity;
  readonly nowMs: bigint;
}

/** §7.1's index entry: the two things a matched path has to produce. */
interface DependencyEntry {
  readonly expressionUri: string;
  readonly subgraphPath: string;
}

/**
 * §7.1's dependency index — `path -> (expression_uri, subgraph_path)`.
 *
 * **EXACT-MATCH, and the section says so twice.** `match(path)` returns entries whose
 * registered path EQUALS the written one; a write at `app/data/sheet1/cells/A1` does
 * NOT wake an expression depending on `app/data/sheet1`. A prefix index here would
 * make more programs appear to work and would be wrong — §7.1 names the three
 * compositions (content-addressed parent, subscription + aggregation, history query)
 * that an application uses instead, precisely so compute needs no subtree primitive.
 *
 * Comparison is on canonical absolute-at-rest paths. Registration canonicalizes
 * through the same `canonicalize` the evaluator's `compute/lookup/tree` arm uses, and
 * the peer's tree writes on canonical paths, so the two sides cannot drift.
 */
class DependencyIndex {
  readonly #byPath = new Map<string, DependencyEntry[]>();
  readonly #bySubgraph = new Map<string, string[]>();

  add(path: string, entry: DependencyEntry): void {
    const list = this.#byPath.get(path);
    if (list === undefined) {
      this.#byPath.set(path, [entry]);
    } else if (!list.some((e) => e.subgraphPath === entry.subgraphPath)) {
      list.push(entry);
    }
    const paths = this.#bySubgraph.get(entry.subgraphPath);
    if (paths === undefined) this.#bySubgraph.set(entry.subgraphPath, [path]);
    else if (!paths.includes(path)) paths.push(path);
  }

  match(path: string): readonly DependencyEntry[] {
    return this.#byPath.get(path) ?? [];
  }

  removeSubgraph(subgraphPath: string): void {
    const paths = this.#bySubgraph.get(subgraphPath);
    if (paths === undefined) return;
    for (const path of paths) {
      const list = this.#byPath.get(path);
      if (list === undefined) continue;
      const kept = list.filter((e) => e.subgraphPath !== subgraphPath);
      if (kept.length === 0) this.#byPath.delete(path);
      else this.#byPath.set(path, kept);
    }
    this.#bySubgraph.delete(subgraphPath);
  }

  /** Diagnostics only — the count of registered (path, subgraph) pairs. */
  get size(): number {
    let n = 0;
    for (const list of this.#byPath.values()) n += list.length;
    return n;
  }

  get watchedPaths(): readonly string[] {
    return [...this.#byPath.keys()];
  }
}

/**
 * The §7 engine: an `EmitConsumer` that owns the dependency index.
 *
 * One instance per peer, created by `installCompute` and handed to the handler, so
 * §3.3's Phase 4 (`register_subgraph_dependencies`) and §7.2's trigger are the same
 * object's two halves rather than two structures that have to agree.
 */
export class ReactiveEngine implements EmitConsumer {
  readonly name = "compute";

  readonly #peer: ReactivePeerServices;
  readonly #limits: EvaluatorLimits;
  readonly #index = new DependencyIndex();

  /**
   * §7.3's bound, as a RE-ENTRANCY counter, beside the context-carried one.
   *
   * **Two bounds, because they fail in different places.** `cascade_depth` travels on
   * the emission context and is the spec's mechanism — it survives a hop through
   * another handler and across peers (SYSTEM-COMPOSITION §3.4). This counter does
   * not travel and measures something else: how deep inside `EntityTree.put` we
   * currently are. It exists because §7.2's ERROR write passes the emission context
   * **unchanged** — the pseudocode increments only on the converged-result path — so
   * a subgraph whose error result feeds its own dependency would recurse with a
   * cascade depth that never moves. On a sync-inline bus that is a stack overflow
   * rather than a runaway loop, and a peer that dies is a worse answer than a frozen
   * subgraph.
   *
   * **MEASURED, THREE ARMS, 2026-09-10** — `test/reactive.test.ts`'s self-feeding
   * subgraph, each bound disabled in turn:
   *
   * | disabled | outcome |
   * |---|---|
   * | neither | freezes with `cascade_limit` |
   * | this counter only | freezes — the spec's `cascade_depth` gate holds |
   * | the `cascade_depth` gate only | freezes — this counter holds |
   * | **both** | **`RangeError: Maximum call stack size exceeded`** |
   *
   * So this one is genuinely a BACKSTOP on the corpus we have — the spec's counter
   * fires first in every case we can construct — and the bottom row is why §7.3's
   * *"this cascade MUST be bounded"* is not decoration on a peer that delivers
   * sync-inline. Declared in `[assumptions].reentrancy_backstop`.
   */
  #reentry = 0;

  constructor(peer: ReactivePeerServices, limits: EvaluatorLimits) {
    this.#peer = peer;
    this.#limits = limits;
  }

  /** §6.10's other event. Compute observes tree binds only; content-store puts are not dependencies. */
  onContentStore(_ev: ContentStoreEvent): void {
    // Intentionally empty. §7.1 registers TREE paths; a content-store put has no path
    // and therefore no index key. An implementation that reacted here would fire on
    // every entity the evaluator itself materializes (D19: an instrument does not read
    // a quantity its own execution writes — here, does not TRIGGER on one).
  }

  /** §7.2 `on_tree_change`. */
  onTreeChange(ev: TreeChangeEvent): void {
    const entries = this.#index.match(ev.path);
    if (entries.length === 0) return;

    if (this.#reentry >= REENTRY_LIMIT) {
      for (const entry of entries) this.#freeze(entry.subgraphPath, CODE_CASCADE_LIMIT, ev.context);
      return;
    }

    const depth = cascadeDepth(ev.context);
    this.#reentry++;
    try {
      for (const entry of entries) {
        const subgraph = this.#peer.tree.get(entry.subgraphPath);
        if (subgraph === undefined || subgraph.type !== SUBGRAPH) {
          // §7.2: uninstalled out from under us — clean the stale registration.
          this.#index.removeSubgraph(entry.subgraphPath);
          continue;
        }
        if (Ecf.optText(subgraph.data, "status") === "frozen") continue;
        if (depth >= BigInt(RECOMMENDED_MAX_CASCADE_DEPTH)) {
          this.#freeze(entry.subgraphPath, CODE_CASCADE_LIMIT, ev.context);
          continue;
        }
        this.#reEvaluate(entry, subgraph, ev.context, depth);
      }
    } finally {
      this.#reentry--;
    }
  }

  // ── §3.3 Phase 4 / §7.1 `register_subgraph_dependencies` ──────────────────────

  /**
   * Register every tree dependency of `expression` against `subgraphPath`.
   *
   * `readPaths` comes from the SAME walk §3.3 Phase 1 ran — see `subgraph.ts`. That
   * is §7.1's *"Implementations MAY factor them into one walker"*, taken up because
   * the alternative is two walkers with one `[MUST]` between them and no instrument
   * able to say they disagree.
   */
  register(subgraphPath: string, expressionUri: string, audit: SubgraphAudit): void {
    this.#index.removeSubgraph(subgraphPath); // re-install replaces, never accumulates.
    for (const path of audit.readPaths) {
      this.#index.add(path, { expressionUri, subgraphPath });
    }
  }

  unregister(subgraphPath: string): void {
    this.#index.removeSubgraph(subgraphPath);
  }

  /**
   * §7.1's `rebuild_dependency_index` — scan `system/compute/processes/*` and
   * re-register from the CURRENT expression at each root path.
   *
   * Called at install time rather than only at restart, because this port holds the
   * index in memory and an in-process composition never restarts. It is here because
   * §7.1 MUSTs it and because it is the one path that reads the metadata back rather
   * than trusting what install put in memory.
   */
  rebuild(): number {
    const prefix = canonicalize(PROCESSES_PREFIX, this.#peer.localPeerId);
    let n = 0;
    // `EntityTree.list` yields one level of NAMES, not paths — the full path is
    // rebuilt here. Reading the name as a path is the kind of near-miss that produces
    // an index of zero entries and a clean-looking verdict.
    for (const [name] of this.#peer.tree.list(prefix)) {
      const path = prefix + "/" + name;
      const subgraph = this.#peer.tree.get(path);
      if (subgraph === undefined || subgraph.type !== SUBGRAPH) continue;
      // §7.1: read the CURRENT expression at the tree path, not the hash recorded at
      // installation. `root_expression` is the audit record; the expression may have
      // been modified since, and the per-operation checks catch an unauthorized one
      // at evaluation time.
      const rootPath = Ecf.optText(subgraph.data, "root_expression_path");
      if (rootPath === null) continue;
      const expression = this.#peer.tree.get(rootPath);
      if (expression === undefined || !isComputeExpression(expression.type)) continue;
      const audit = auditSubgraph(expression, rootPath, this.#auditContext());
      if (audit instanceof AuditRefusal) continue;
      this.register(path, rootPath, audit);
      n++;
    }
    return n;
  }

  /** Diagnostics for the composition's startup line and for our own tests. */
  get registeredDependencies(): number {
    return this.#index.size;
  }

  get watchedPaths(): readonly string[] {
    return this.#index.watchedPaths;
  }

  /**
   * §3.3's *"Implementations SHOULD … perform an initial evaluation after
   * installation"*, reachable from the handler so install and re-install take the
   * same path. Returns the result hash written, or null when nothing was written.
   */
  evaluateNow(subgraphPath: string, context: EmitContext | null): Uint8Array | null {
    const subgraph = this.#peer.tree.get(subgraphPath);
    if (subgraph === undefined || subgraph.type !== SUBGRAPH) return null;
    const expressionUri = Ecf.optText(subgraph.data, "root_expression_path");
    if (expressionUri === null) return null;
    return this.#reEvaluate({ expressionUri, subgraphPath }, subgraph, context, cascadeDepth(context));
  }

  // ── §7.2 `re_evaluate` ────────────────────────────────────────────────────────

  #reEvaluate(
    entry: DependencyEntry,
    subgraph: Entity,
    context: EmitContext | null,
    depth: bigint,
  ): Uint8Array | null {
    const resultPath = Ecf.optText(subgraph.data, "result_path");
    if (resultPath === null) return null;

    // §7.2 — the installation grant must still be available and unexpired. Revocation
    // is NOT checked here and that is the spec's own ruling: `verify_request`
    // (ENTITY-CORE-PROTOCOL §5.2 step 4) catches it on the first dispatched impure op,
    // and the resulting error freezes the subgraph through the ordinary path. Calling
    // `is_revoked` here would be a permitted fail-fast optimization and nothing more.
    const grantHash = Ecf.optBytes(subgraph.data, "installation_grant");
    const grantEntity = grantHash === null ? undefined : this.#peer.contentStore.get(grantHash);
    let grant: CapabilityToken | null = null;
    if (grantEntity !== undefined) {
      try {
        grant = new CapabilityToken(grantEntity);
      } catch {
        grant = null;
      }
    }
    if (grant === null || isExpired(grant, this.#peer.nowMs)) {
      this.#freeze(entry.subgraphPath, CODE_INSTALLATION_GRANT_INVALID, context);
      return null;
    }

    const expression = this.#peer.tree.get(entry.expressionUri);
    if (expression === undefined) {
      // §7.2: the expression is gone. The subgraph metadata survives; the
      // registrations do not, because there is nothing left to wake.
      this.#index.removeSubgraph(entry.subgraphPath);
      return null;
    }

    const budget = reactiveBudget(grant, this.#limits);
    const evaluator = new ComputeEvaluator(this.#peer, budget);
    const outcome = evaluator.evaluateAt(expression, entry.expressionUri, {
      // §7.2's *"Authorization source"*: the installation grant authorizes every
      // impure operation, and it was verified at install to cover all of them. This
      // is the ONE path in this port where the capability check is per-path rather
      // than dispatch-scoped — the reactive path holds a capability object, and the
      // explicit-eval path does not. See `[assumptions].capability_check_scope`.
      canReadPath: (path) => Permissions.checkPathPermission("get", path, grant, "system/tree", this.#peer.localPeerId),
      canWritePath: (path) => Permissions.checkPathPermission("put", path, grant, "system/tree", this.#peer.localPeerId),
      // §4.2 Tier 2 — the set §3.3 Phase 2b SEALED. This is the first composition in
      // which it is non-empty, and it is why `authorized_data_hashes` is a field on
      // the metadata rather than a local of the install call.
      authorizedDataHashes: authorizedHashes(subgraph),
    });

    const result = outcome.error !== null
      ? outcome.error.toEntity()
      : resultEntity(outcome.value, expression);

    if (outcome.error !== null) {
      // §7.2's reactive error handling: the error entity IS the result. It is written
      // with the incoming context — the pseudocode increments only on the converged
      // path — and the subgraph stays ACTIVE. A budget exhaustion may be transient
      // (§7.3), and freezing on every evaluation error would make an error a
      // permanent state that only re-installation clears.
      this.#write(resultPath, result, context);
      return result.contentHash;
    }

    // §7.2's convergence check. Same hash → no write → no event → no cascade. The
    // tree would also suppress an identical bind, but doing it here is what makes the
    // NON-write observable to this function, which is what a cascade test measures.
    const previous = this.#peer.tree.getHash(resultPath);
    if (previous !== undefined && hexOf(previous) === hexOf(result.contentHash)) {
      return null;
    }
    this.#write(resultPath, result, { ...(context ?? {}), cascadeDepth: depth + 1n });
    return result.contentHash;
  }

  /**
   * §7.2's freeze: a code-only `compute/error` at the result path, `status: "frozen"`
   * on the metadata. Recovery is re-installation (§3.3), which is the only thing that
   * clears it — deliberately, because both conditions that reach here (`cascade_limit`
   * and `installation_grant_invalid`) are structural and retrying changes nothing.
   */
  #freeze(subgraphPath: string, code: string, context: EmitContext | null): void {
    const subgraph = this.#peer.tree.get(subgraphPath);
    if (subgraph === undefined || subgraph.type !== SUBGRAPH) return;
    const resultPath = Ecf.optText(subgraph.data, "result_path");
    if (resultPath !== null) {
      // §2.4 — the materialized form is CODE-ONLY. `message` and `at` are in-flight
      // diagnostics; putting one in a tree-written entity forks the content hash
      // across two conformant peers.
      this.#write(resultPath, Entity.create(ERROR, Ecf.map(["code", Ecf.text(code)])), context);
    }
    this.#write(subgraphPath, withStatus(subgraph, "frozen"), context);
  }

  #write(path: string, entity: Entity, context: EmitContext | null): void {
    this.#peer.tree.put(path, entity, this.#emitContext(context));
  }

  /**
   * The execution context our writes carry.
   *
   * `chain_id` is INHERITED and never regenerated — SYSTEM-COMPOSITION §3.4 makes
   * that a composition-level invariant, and it is the field a cross-peer cascade is
   * traced by. `author` is the local peer, because §7.2 evaluates as
   * `local_peer_identity`; `callerCapability` is deliberately dropped rather than
   * inherited, because the authority for this write is the installation grant and not
   * whoever happened to touch the dependency.
   */
  #emitContext(context: EmitContext | null): EmitContext {
    return {
      ...(context?.chainId !== undefined ? { chainId: context.chainId } : {}),
      ...(context?.parentChainId !== undefined ? { parentChainId: context.parentChainId } : {}),
      ...(context?.requestId !== undefined ? { requestId: context.requestId } : {}),
      ...(context?.cascadeDepth !== undefined ? { cascadeDepth: context.cascadeDepth } : {}),
      author: this.#peer.localIdentity.identityHash,
      handlerPattern: COMPUTE_PATTERN,
      operation: "eval",
    };
  }

  #auditContext(): AuditContext {
    return {
      tree: this.#peer.tree,
      contentStore: this.#peer.contentStore,
      localPeerId: this.#peer.localPeerId,
      included: new Map(),
      author: null,
    };
  }
}

/**
 * The re-entrancy backstop's bound. Twice the cascade limit, so it can only fire
 * where the spec's own counter has already failed to move — which is the error-write
 * path (§7.2 passes the context unchanged there) and nothing else.
 */
const REENTRY_LIMIT = RECOMMENDED_MAX_CASCADE_DEPTH * 2;

/** SYSTEM-COMPOSITION §3.1 — an absent counter is depth 0, never "unknown". */
function cascadeDepth(context: EmitContext | null): bigint {
  return context?.cascadeDepth ?? 0n;
}

/**
 * §7.4 `reactive_budget` — fresh and independent, bounded by the installation grant's
 * `constraints["system/compute"]`, falling back to the peer defaults (§9.3).
 *
 * **The constraint lives on the GRANT ENTRY, not on the token**, and §5.2/§5.5 both
 * spell it `capability.data.constraints["system/compute"]`. ENTITY-CORE-PROTOCOL §5
 * carries `constraints` on each entry of `grants`, which is where this peer parses it
 * from and where a delegation preserves it byte-equal. Reading the tightest value
 * across the entries is the only choice that cannot widen a grant. Routed as A-21;
 * declared in `[assumptions].constraints_location`.
 */
function reactiveBudget(grant: CapabilityToken, limits: EvaluatorLimits): EvaluatorLimits {
  let operations = limits.maxOperations;
  let depth = limits.maxDepth;
  for (const entry of grant.grants) {
    if (entry.constraints === null) continue;
    const compute = Ecf.field(entry.constraints, COMPUTE_PATTERN);
    if (compute === null) continue;
    const ops = optNumber(compute, "max_compute_operations");
    if (ops !== null) operations = Math.min(operations, ops);
    const d = optNumber(compute, "max_compute_depth");
    if (d !== null) depth = Math.min(depth, d);
  }
  return { maxOperations: operations, maxDepth: depth };
}

function optNumber(value: codec.EcfValue, key: string): number | null {
  try {
    const found = Ecf.optUint(value, key);
    return found === null ? null : Number(found);
  } catch {
    return null;
  }
}

/** §4.2 Tier 2 — the sealed set, as hex, from the metadata's seventh field. */
function authorizedHashes(subgraph: Entity): ReadonlySet<string> {
  const out = new Set<string>();
  const field = Ecf.field(subgraph.data, "authorized_data_hashes");
  if (field === null || field.kind !== "array") return out;
  for (const item of field.items) {
    if (item.kind === "bytes") out.add(hexOf(item.value));
  }
  return out;
}

/**
 * §2.4 — a primitive result is wrapped in a `compute/result` carrying the SOURCE
 * EXPRESSION's hash; an entity result travels as itself.
 *
 * Identical to the handler's `eval` return, and that identity is the point: a caller
 * reading `{root}/result` after a reactive update and a caller reading the response
 * of an explicit `eval` are looking at the same bytes for the same expression.
 */
function resultEntity(value: codec.EcfValue | Entity | null, expression: Entity): Entity {
  if (value instanceof Entity) return value;
  return Entity.create(
    RESULT,
    Ecf.map(
      ["value", value as codec.EcfValue],
      ["expression", Ecf.bytes(expression.contentHash)],
    ),
  );
}

function withStatus(subgraph: Entity, status: string): Entity {
  const pairs: (readonly [string, codec.EcfValue | null])[] = [];
  for (const [key, value] of Ecf.entries(subgraph.data)) {
    pairs.push([key, key === "status" ? Ecf.text(status) : value]);
  }
  return Entity.create(SUBGRAPH, Ecf.map(...pairs));
}

/** §7.2's `is_expired` — `expires_at` against the peer clock. */
function isExpired(grant: CapabilityToken, nowMs: bigint): boolean {
  return grant.expiresAt !== null && grant.expiresAt < nowMs;
}

/**
 * §3.3's `deterministic_id` — `base32_lower_no_padding(sha256(utf8_bytes(root_path)))`.
 *
 * **The SHA-256 here is NOT a `content_hash_format` dispatch site**, and v7.68 pins
 * that explicitly: the `subgraph_id` is a deterministic path-segment identifier, not
 * part of the content-address space, so every implementation uses SHA-256 regardless
 * of its configured hash format — precisely so cross-peer subgraph inspection works
 * in a mixed-format cohort. Using the peer's configured hash function here would look
 * more consistent and would break the property the clause exists to protect.
 */
export function deterministicId(rootPath: string): string {
  const digest = crypto.defaultProvider.sha256.digest(new TextEncoder().encode(rootPath));
  return base32LowerNoPadding(digest);
}

const BASE32_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567";

function base32LowerNoPadding(bytes: Uint8Array): string {
  let out = "";
  let buffer = 0;
  let bits = 0;
  for (const byte of bytes) {
    buffer = (buffer << 8) | byte;
    bits += 8;
    while (bits >= 5) {
      out += BASE32_ALPHABET[(buffer >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  if (bits > 0) out += BASE32_ALPHABET[(buffer << (5 - bits)) & 31];
  return out;
}
