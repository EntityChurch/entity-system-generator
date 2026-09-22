/**
 * COMPUTE §3.3 `audit_subgraph` and §7.1 `walk_tree_lookups` — **ONE walker.**
 *
 * §3.3 permits this in as many words (*"Implementations MAY factor them into one
 * walker with multiple visitors"*), and here it is not an optimisation, it is the
 * only way to get the right answer. The two listings disagree, and the one that is
 * wrong is the one that authorizes:
 *
 * | | §3.3 `audit_walk` | §7.1 `walk` |
 * |---|---|---|
 * | descends a scalar `system/hash` field | yes | yes |
 * | descends **into `apply.args` / `let.bindings`** | **NO** | yes, `[MUST, v3.27]` |
 *
 * v3.27 promoted §7.1's *"all `compute/lookup/tree` paths reachable in the expression
 * graph are registered"* from a description to a `[MUST]` **and rewrote its walker to
 * descend containers** — and §3.3's walker, four sections earlier and sharing the same
 * paragraph of prose, was not touched. A literal transcription of §3.3 therefore
 * capability-checks a tree read at the top level of an expression and **skips the same
 * read one function-argument deep**, which is an authorization hole rather than a
 * coverage one. Routed to arch as A-17; see `[assumptions].audit_walk_containers`.
 *
 * Two further clauses this file implements that §3.3's listing does not carry, both
 * MUST-ed elsewhere in the same document:
 *
 *  - **Q23** (§2.1, `[MUST]`, and §2.1 says *"it is enforced at install time too"*): a
 *    builtin-path `compute/apply` carrying `capability` or `resource` is
 *    `invalid_expression`. §3.3's listing fail-fasts F5 and installs this shape clean,
 *    which §2.1's own words call *"internally inconsistent"*. A-18.
 *  - **SA-11** (§3.3's own subgraph-boundary paragraph): the pure collection builtins
 *    *"require no install-time handler-target authorization grant"*. §3.3's listing
 *    appends **every** builtin apply to `handler_targets`, so under a narrow grant the
 *    prose admits a `map` and the pseudocode rejects it. A-19.
 *
 * Nothing here evaluates. The audit is a static walk over the expression graph; a
 * value that is only knowable at runtime (a dynamic `store` path, a dynamic
 * capability) is deliberately left to the runtime check, which is §3.3's declared
 * conservative-static / runtime-dynamic split.
 */

import {
  Ecf,
  Entity,
  Permissions,
  CapabilityToken,
  ResourceTarget,
  type ContentStore,
  type EntityTree,
  type codec,
} from "entity-core-protocol-typescript";

import {
  APPLY, LITERAL, LOOKUP_HASH, LOOKUP_TREE,
  BUILTINS_PREFIX,
  CODE_INVALID_EXPRESSION,
  isComputeType,
} from "../types.js";
import { canonicalize, cleanPath, hexOf } from "./evaluator.js";

/** The §1.2 `system/hash` wire width: one format byte plus a 32-byte digest. */
const CONTENT_HASH_LENGTH = 33;

const STORE_BUILTIN = BUILTINS_PREFIX + "/store";

/** §3.3 Phase 1's `handler_targets` entry. `resource` is null when dynamic or absent. */
export interface HandlerTarget {
  readonly path: string;
  readonly operation: string | null;
  readonly resource: ResourceTarget | null;
}

/** §3.3 Phase 2b's `data_hashes` entry (v3.7 D3/D6). `path` is the hint, or null. */
export interface DataHashRef {
  readonly hash: Uint8Array;
  readonly path: string | null;
}

/**
 * What one walk produced.
 *
 * **`readPaths` serves §3.3's `read_paths` AND §7.1's `deps`, and that is a
 * deliberate identification rather than a shortcut.** The two listings differ by one
 * `canonicalize` call on the absolute form — §7.1 canonicalizes so the dependency
 * matches the absolute-at-rest path a tree write notifies on, §3.3 does not because
 * `check_path_permission` canonicalizes internally. Canonicalizing once, here, makes
 * both correct and removes the place they could drift.
 */
export interface SubgraphAudit {
  readonly readPaths: readonly string[];
  readonly handlerTargets: readonly HandlerTarget[];
  readonly writePaths: readonly string[];
  readonly dataHashes: readonly DataHashRef[];
}

/** A refusal carrying the status/code pair §3.3 names for it. Never thrown. */
export class AuditRefusal {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly message: string,
  ) {}
}

/** What the audit reads. No budget, no scope: nothing here evaluates. */
export interface AuditContext {
  readonly tree: EntityTree;
  readonly contentStore: ContentStore;
  readonly localPeerId: string;
  /** §4.2 step 1 — the EXECUTE envelope's `included` map, keyed by hex hash. */
  readonly included: ReadonlyMap<string, Entity>;
  /** `ctx.execute.data.author` — the installer's identity hash, for CP1. */
  readonly author: Uint8Array | null;
}

interface WalkState {
  readonly visited: Set<string>;
  readonly readPaths: string[];
  readonly handlerTargets: HandlerTarget[];
  readonly writePaths: string[];
  readonly dataHashes: DataHashRef[];
  readonly rootPath: string;
  readonly ctx: AuditContext;
}

/**
 * §3.3 Phase 1 — walk the expression graph from `root` and collect the four
 * categories, or refuse on a static structural error.
 *
 * `rootPath` is the resolution prefix for `relative: true` paths (§2.1) and MUST be
 * the canonical absolute form; the caller canonicalizes once, at the EXECUTE
 * boundary, so this function never has to decide.
 */
export function auditSubgraph(
  root: Entity,
  rootPath: string,
  ctx: AuditContext,
): SubgraphAudit | AuditRefusal {
  const st: WalkState = {
    visited: new Set(),
    readPaths: [],
    handlerTargets: [],
    writePaths: [],
    dataHashes: [],
    rootPath,
    ctx,
  };
  const refusal = walkNode(root, st);
  if (refusal !== null) return refusal;
  return {
    readPaths: st.readPaths,
    handlerTargets: st.handlerTargets,
    writePaths: st.writePaths,
    dataHashes: st.dataHashes,
  };
}

function walkNode(entity: Entity, st: WalkState): AuditRefusal | null {
  // §3.3's cycle detection, keyed on the content hash exactly as the listing is.
  const hex = hexOf(entity.contentHash);
  if (st.visited.has(hex)) return null;
  st.visited.add(hex);

  if (entity.type === LOOKUP_TREE) {
    st.readPaths.push(lookupPath(entity, st));
    return null; // §3.3: a lookup is a leaf — its `path` is text, not a reference.
  }

  if (entity.type === LOOKUP_HASH) {
    // v3.7 D3/D6. The `hash` field points at arbitrary DATA, not at an expression,
    // so this arm returning early is what keeps the generic descent below from
    // treating a data reference as a sub-expression to audit.
    const hash = Ecf.optBytes(entity.data, "hash");
    if (hash === null) {
      return new AuditRefusal(400, CODE_INVALID_EXPRESSION, "compute/lookup/hash requires a hash field");
    }
    const hint = Ecf.optText(entity.data, "path");
    const relative = Ecf.optBool(entity.data, "relative") === true;
    st.dataHashes.push({
      hash,
      path: hint === null ? null : relative ? cleanPath(st.rootPath + "/" + hint) : hint,
    });
    return null;
  }

  if (entity.type === APPLY) {
    const refusal = auditApply(entity, st);
    if (refusal !== null) return refusal;
    // and FALL THROUGH — §3.3's listing recurses into an apply's fields after
    // collecting its target, which is how a `lookup/tree` inside `args` is reached.
  }

  // §7.1's `walk_value`, applied to §3.3's walk as well. THIS LOOP IS A-17: §3.3's
  // own listing tests `if field_value is system/hash` and descends no container.
  let fields: readonly (readonly [string, codec.EcfValue])[];
  try {
    fields = Ecf.entries(entity.data);
  } catch {
    return null; // data is not a map — nothing to descend into, and not an error.
  }
  for (const [, value] of fields) {
    const refusal = walkValue(value, st);
    if (refusal !== null) return refusal;
  }
  return null;
}

function walkValue(value: codec.EcfValue, st: WalkState): AuditRefusal | null {
  switch (value.kind) {
    case "bytes": {
      if (value.value.length !== CONTENT_HASH_LENGTH) return null;
      const referenced = resolveForAudit(value.value, st.ctx);
      // §3.3's *"Audit scope (normative)"*: a hash that resolves to a NON-compute
      // entity is skipped. This is also what stops a `compute/literal` whose value
      // happens to be a 33-byte capability hash (CP1's shape) from being walked.
      if (referenced === null || !isComputeType(referenced.type)) return null;
      return walkNode(referenced, st);
    }
    case "array": {
      for (const item of value.items) {
        const refusal = walkValue(item, st);
        if (refusal !== null) return refusal;
      }
      return null;
    }
    case "map": {
      for (const [, member] of value.pairs) {
        const refusal = walkValue(member, st);
        if (refusal !== null) return refusal;
      }
      return null;
    }
    default:
      return null;
  }
}

/**
 * §3.3's `compute/apply` arm — Q23, F5, CP1, F3, then the `store` write target.
 *
 * **The order is normative and each step is presence-only or static-literal-only.**
 * Q23 first because §2.1 makes it a SHAPE check that runs before any field is
 * resolved; CP1 before F3 because §3.3 says so in a comment that also says why
 * (chain-root is cheaper and more fundamental than scope coverage).
 */
function auditApply(entity: Entity, st: WalkState): AuditRefusal | null {
  const path = Ecf.optText(entity.data, "path");
  if (path === null) return null; // closure mode — nothing to authorize.

  const hasCapability = Ecf.optBytes(entity.data, "capability") !== null;
  const hasResource = Ecf.optBytes(entity.data, "resource") !== null;
  const builtin = builtinName(path);

  // Q23 (§2.1) — a builtin dispatches no EXECUTE, so neither field has a referent.
  if (builtin !== null && (hasCapability || hasResource)) {
    return new AuditRefusal(
      400,
      CODE_INVALID_EXPRESSION,
      "compute/apply on a builtin path MUST NOT carry capability or resource (§2.1 Q23, install-time)",
    );
  }

  // F5 (v3.10) — a capability override with no resource cannot be dual-checked.
  if (hasCapability && !hasResource) {
    return new AuditRefusal(
      400,
      CODE_INVALID_EXPRESSION,
      "compute/apply with capability field MUST also have resource field (§2.1 F5)",
    );
  }

  // CP1 (v3.11) — a STATIC-LITERAL embedded capability must have the installer in
  // its authority chain. A dynamic capability is deferred to the runtime dual-check.
  if (hasCapability) {
    const refusal = checkEmbeddedCapability(entity, st);
    if (refusal !== null) return refusal;
  }

  // F3 (v3.10) — a static-literal resource is audited; a dynamic one is deferred.
  let resource: ResourceTarget | null = null;
  if (hasResource) {
    const literal = resolveLiteral(Ecf.requireBytes(entity.data, "resource"), st.ctx);
    if (literal !== null) {
      const value = Ecf.field(literal.data, "value");
      if (value !== null) {
        try {
          resource = ResourceTarget.fromEcf(value);
        } catch {
          resource = null; // not a resource-target struct — runtime's problem, not ours.
        }
      }
    }
  }

  // SA-11, and this is A-19: **no builtin path is ever a handler target.** §3.3's
  // listing appends every apply-with-a-path unconditionally; the same section's prose
  // says the pure collection builtins *"require no install-time handler-target
  // authorization grant"* and that *"only `store` is authorization-gated at install
  // time, VIA ITS `write_path`"*. Those are the same sentence read twice: a builtin
  // dispatches no EXECUTE (§2.1 Q23's own premise), so there is no handler+operation
  // pair for a grant to cover, and demanding one would reject a legal `map` under any
  // grant narrower than `*`.
  if (builtin === null) {
    st.handlerTargets.push({
      path,
      operation: Ecf.optText(entity.data, "operation"),
      resource,
    });
  }

  // §3.3's `store` special case: a LITERAL path argument becomes a static write
  // target. A computed one is not knowable here and is checked at the store site.
  if (relativePattern(path) === STORE_BUILTIN) {
    const argsField = Ecf.field(entity.data, "args");
    if (argsField !== null) {
      const pathArg = Ecf.field(argsField, "path");
      if (pathArg !== null && pathArg.kind === "bytes" && pathArg.value.length === CONTENT_HASH_LENGTH) {
        const literal = resolveLiteral(pathArg.value, st.ctx);
        if (literal !== null) {
          const target = Ecf.field(literal.data, "value");
          if (target !== null && target.kind === "text") st.writePaths.push(target.value);
        }
      }
    }
  }
  return null;
}

/**
 * CP1 / §10.1 — *"the install audit MUST verify that `ctx.execute.data.author` appears
 * **as a granter anywhere in** the static-literal `compute/apply.capability` authority
 * chain … in-chain, NOT rooted-at-author."*
 *
 * **In-chain and not chain-root is the whole content of this function**, and the
 * distinction is not academic: a dispatch capability minted by a client is parented at
 * the CONNECTION capability, whose granter is the REMOTE peer — so the chain ROOTS at
 * the peer and the installer is the leaf granter. An implementation reading
 * "rooted at author" rejects every legitimate embedded capability, which is the
 * over-rejection `cp1_install_static_literal_self_issued_accepted` exists to catch.
 */
function checkEmbeddedCapability(entity: Entity, st: WalkState): AuditRefusal | null {
  const capRef = resolveLiteral(Ecf.requireBytes(entity.data, "capability"), st.ctx);
  if (capRef === null) return null; // dynamic capability — runtime dual-check applies.

  const value = Ecf.field(capRef.data, "value");
  if (value === null || value.kind !== "bytes" || value.value.length !== CONTENT_HASH_LENGTH) {
    // §3.3: *"else: cap entity unreachable at install — surface as chain_unreachable."*
    return new AuditRefusal(404, "chain_unreachable", "Static compute/apply.capability does not name a capability entity");
  }
  const capEntity = lookupEntity(value.value, st.ctx);
  if (capEntity === undefined) {
    return new AuditRefusal(404, "chain_unreachable", "Static compute/apply.capability authority chain not fully resolvable");
  }

  const author = st.ctx.author;
  if (author === null) {
    return new AuditRefusal(403, "embedded_cap_unauthorized", "Install has no author identity to check the chain against");
  }

  let current: Entity | undefined = capEntity;
  // ENTITY-CORE-PROTOCOL §5.5's `collect_authority_chain` bound, restated rather than
  // imported: the peer's own `collectAuthorityChain` is module-private.
  for (let depth = 0; depth <= 64; depth++) {
    if (current === undefined) {
      return new AuditRefusal(404, "chain_unreachable", "Static compute/apply.capability authority chain not fully resolvable");
    }
    let token: CapabilityToken;
    try {
      token = new CapabilityToken(current);
    } catch {
      return new AuditRefusal(404, "chain_unreachable", "Static compute/apply.capability chain contains a non-capability entity");
    }
    if (token.granter !== null && bytesEqual(token.granter, author)) {
      return null; // IN-CHAIN as a granter — the installer authorized this delegation.
    }
    if (token.parent === null) break; // root reached, installer never appeared.
    current = lookupEntity(token.parent, st.ctx);
  }

  return new AuditRefusal(
    403,
    "embedded_cap_unauthorized",
    "Installer identity not in static compute/apply.capability chain",
  );
}

// ── Phase 2 — the capability checks ─────────────────────────────────────────────

/**
 * §3.3's `check_grant_covers(path, operation, resource, capability, local_peer_id)` —
 * ENTITY-CORE-PROTOCOL §5.2's grant probe **without a synthetic EXECUTE**.
 *
 * Mirrors the peer's own `Permissions.checkPermission` dimension for dimension, with
 * the one difference that gives this function its reason to exist: there is no
 * `Execute` to read a URI and operation off, so handler/operation/resource arrive as
 * arguments. All matched dimensions MUST come from a SINGLE grant entry — the loop
 * `continue`s rather than accumulating, which is the clause an implementation that
 * checks each dimension against the whole token gets wrong.
 */
export function grantCovers(
  capability: CapabilityToken,
  handlerPattern: string,
  operation: string | null,
  resource: ResourceTarget | null,
  localPeerId: string,
  granterPeerId: string,
): boolean {
  for (const grant of capability.grants) {
    if (operation !== null && !grant.operations.matches(operation, localPeerId, "id")) continue;
    if (!grant.handlers.matches(handlerPattern, localPeerId, "path")) continue;
    if (!grant.effectivePeers(localPeerId).matches(localPeerId, localPeerId, "id")) continue;
    if (resource !== null && !Permissions.checkResourceScope(resource, grant.resources, localPeerId, granterPeerId)) {
      continue;
    }
    return true;
  }
  return false;
}

// ── resolution ──────────────────────────────────────────────────────────────────

/**
 * The audit's resolver: the envelope's `included` map, then the content store.
 *
 * **Deliberately NOT §4.2's three-tier gate.** The tiers exist so an EVALUATION
 * cannot use the content store as an oracle for entities the caller never had; the
 * audit walks the installer's own expression graph before anything is authorized, and
 * its one filter — *"skip hash references that resolve to non-compute entities"* — is
 * applied by the caller in {@link walkValue}, where §3.3 puts it.
 */
function resolveForAudit(hash: Uint8Array, ctx: AuditContext): Entity | null {
  return lookupEntity(hash, ctx) ?? null;
}

function lookupEntity(hash: Uint8Array, ctx: AuditContext): Entity | undefined {
  return ctx.included.get(hexOf(hash)) ?? ctx.contentStore.get(hash);
}

/** Resolve a reference and return it only if it is a `compute/literal`. */
function resolveLiteral(hash: Uint8Array, ctx: AuditContext): Entity | null {
  const found = lookupEntity(hash, ctx);
  return found !== undefined && found.type === LITERAL ? found : null;
}

function lookupPath(entity: Entity, st: WalkState): string {
  const raw = Ecf.requireText(entity.data, "path");
  return Ecf.optBool(entity.data, "relative") === true
    ? cleanPath(st.rootPath + "/" + raw)
    : canonicalize(raw, st.ctx.localPeerId);
}

/** The path with any leading `/{peer}/` removed — handler patterns are peer-relative. */
function relativePattern(path: string): string {
  return path.startsWith("/") ? path.slice(path.indexOf("/", 1) + 1) : path;
}

/** The builtin's short name, or null when `path` is not under the builtin prefix. */
function builtinName(path: string): string | null {
  const relative = relativePattern(path);
  if (relative === BUILTINS_PREFIX) return "";
  if (!relative.startsWith(BUILTINS_PREFIX + "/")) return null;
  return relative.slice(BUILTINS_PREFIX.length + 1);
}

function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}
