/**
 * §5.1 `emit_entity` — the transition recorder. **MODULE-PRIVATE.**
 *
 * This is the emit-consumer body. It is not exported from `index.ts` and it is not part
 * of the SDK face, for the same structural reason CONTENT's `reassemble` is not: the only
 * legitimate caller is the consumer the peer invokes. A third party able to call this
 * could forge a transition — write an entry into an audit chain claiming an author and a
 * capability of its choosing — which is a strictly worse capability-escalation surface
 * than the one §3.4 forbids for CONTENT, and no clause anywhere authorises it.
 *
 * `test/export-surface.test.ts` asserts the package's public entry reaches nothing here.
 */

import { Entity, Ecf, type ContentStore, type EntityTree } from "entity-core-protocol-typescript";

import {
  CONFIG_PREFIX,
  DEFAULT_EVENTS,
  HEAD_PREFIX,
  HistoryTypes,
  fromCoreEventType,
} from "../types.js";
import {
  canonicalizePattern,
  compareSpecificity,
  patternMatches,
  patternSpecificity,
} from "../patterns.js";

/**
 * The execution-context values a transition needs (§2.1), and where they came from.
 *
 * `provenance` is OURS, not §2.1's. It never enters the transition entity — adding a
 * field to a spec-declared type would change its content hash away from every other
 * implementation's, which is the silent cross-impl break this ecosystem keeps paying
 * for. It is returned alongside so the composition can report it and so
 * `RecordedTransition` can carry it to a test.
 */
export interface TransitionContext {
  readonly author: Uint8Array;
  readonly capability: Uint8Array;
  readonly callerCapability: Uint8Array | null;
  readonly handlerPattern: string;
  readonly operation: string;
  readonly chainId: string | null;
  readonly parentChainId: string | null;
  readonly provenance: "context" | "autonomous-fallback";
}

/** What the recorder captures at registration time, because the event does not carry it. */
export interface RecorderIdentity {
  /** §2.1: "For autonomous operations (no external request), the local peer's identity hash." */
  readonly localIdentityHash: Uint8Array;
  /** §2.1: "For autonomous operations, the handler grant." */
  readonly handlerGrantHash: Uint8Array;
  readonly localPeerId: string;
}

export interface RecordedTransition {
  readonly path: string;
  readonly event: string;
  readonly transitionHash: Uint8Array;
  readonly headPath: string;
  readonly provenance: "context" | "autonomous-fallback";
}

/**
 * §3.2 `is_local_history_path` — the self-guard, transcribed.
 *
 * Two properties of this function are load-bearing and both are easy to get wrong in the
 * direction that still passes a naive test:
 *
 *  1. **It guards `system/history/head`, NOT `system/history/`.** §3.2: config paths
 *     "are handler-written via explicit EXECUTE and do not create recursion risk — they
 *     SHOULD be recorded as normal transitions for audit purposes." Guarding the whole
 *     namespace would silently drop config-change auditing, and nothing would fail.
 *  2. **It is LOCAL-ONLY.** A remote peer's `system/history/...` arriving via sync is
 *     ordinary tracked content. §3.2 walks through why there is no recursion risk: the
 *     resulting head pointer lands at `/{local}/system/history/head/{remote}/...`, which
 *     this same check excludes.
 */
export function isLocalHistoryPath(path: string, localPeerId: string): boolean {
  const prefix = "/" + localPeerId + "/";
  if (!path.startsWith(prefix)) {
    return false; // remote namespace — no recursion risk (§3.2)
  }
  return path.slice(prefix.length).startsWith(HEAD_PREFIX);
}

/** A parsed `system/history/config` entity plus the pattern it was stored with. */
export interface HistoryConfig {
  readonly pattern: string;
  readonly canonicalPattern: string;
  readonly enabled: boolean;
  readonly events: readonly string[];
  readonly maxDepth: number | null;
  readonly configPath: string;
}

function parseConfig(path: string, entity: Entity, localPeerId: string): HistoryConfig | null {
  if (entity.type !== HistoryTypes.Config) {
    return null;
  }
  try {
    const pattern = Ecf.requireText(entity.data, "pattern");
    const enabled = Ecf.asBool(Ecf.require(entity.data, "enabled"));
    const rawEvents = Ecf.field(entity.data, "events");
    const events =
      rawEvents === null ? DEFAULT_EVENTS : Ecf.asArray(rawEvents).map((e) => Ecf.asText(e));
    const rawDepth = Ecf.optUint(entity.data, "max_depth");
    const maxDepth = rawDepth === null ? null : Number(rawDepth);
    return {
      pattern,
      canonicalPattern: canonicalizePattern(pattern, localPeerId),
      enabled,
      events,
      maxDepth,
      configPath: path,
    };
  } catch {
    // A malformed config is skipped, not fatal. §6.2 iterates configs to find a match;
    // one unreadable entity must not make every path un-audited. It is also not silent:
    // the caller counts them (see `findHistoryConfig`'s `skipped`).
    return null;
  }
}

/**
 * §6.2 `find_history_config`, with v1.7's three-key ordering.
 *
 * Returns the most specific ENABLED-or-not matching config — the enabled check belongs to
 * the caller (§5.1 checks `config is null or not config.data.enabled` separately), and
 * folding it in here would change which config wins: a specific `enabled: false` must
 * SHADOW a general `enabled: true`, or "turn history off for this subtree" cannot be
 * expressed. That is not stated in §6.2 and it is the only reading under which the
 * `enabled` field is useful, so it is recorded in `[assumptions].disabled_shadows`.
 */
export function findHistoryConfig(
  tree: EntityTree,
  path: string,
  localPeerId: string,
): { config: HistoryConfig | null; considered: number; skipped: number } {
  const base = "/" + localPeerId + "/" + CONFIG_PREFIX + "/";
  const listing = tree.list(base);

  let best: HistoryConfig | null = null;
  let considered = 0;
  let skipped = 0;

  for (const [name, entry] of listing) {
    if (entry.hash === null) {
      continue;
    }
    const configPath = base + name;
    const entity = tree.get(configPath);
    if (entity === undefined) {
      continue;
    }
    const parsed = parseConfig(configPath, entity, localPeerId);
    if (parsed === null) {
      skipped += 1;
      continue;
    }
    considered += 1;
    if (!patternMatches(path, parsed.canonicalPattern)) {
      continue;
    }
    if (
      best === null ||
      compareSpecificity(
        patternSpecificity(parsed.canonicalPattern),
        patternSpecificity(best.canonicalPattern),
      ) > 0
    ) {
      best = parsed;
    }
  }
  return { config: best, considered, skipped };
}

/**
 * §5.1's transition build + head advance, and §3.3's prune.
 *
 * Returns `null` when the write is not recorded, which is a normal outcome and not an
 * error: unconfigured paths, disabled configs, unlisted event types and the §3.2
 * self-guard all land here. History is opt-in (§2.2).
 */
export function recordTransition(
  tree: EntityTree,
  store: ContentStore,
  identity: RecorderIdentity,
  ev: {
    readonly eventType: string;
    readonly path: string;
    readonly newHash: Uint8Array | null;
    readonly previousHash: Uint8Array | null;
  },
  ctx: TransitionContext,
  nowMs: bigint,
): RecordedTransition | null {
  // §3.2 self-guard FIRST. Before the config lookup, because the lookup lists the tree
  // and the guard is what stops this consumer re-entering on its own head write.
  if (isLocalHistoryPath(ev.path, identity.localPeerId)) {
    return null;
  }

  const event = fromCoreEventType(ev.eventType);
  if (event === null) {
    return null; // an event vocabulary we do not recognise is never guessed at (types.ts)
  }

  const { config } = findHistoryConfig(tree, ev.path, identity.localPeerId);
  if (config === null || !config.enabled) {
    return null; // §2.2: "If history is not configured for a path, no transitions are recorded"
  }
  if (!config.events.includes(event)) {
    return null; // §5.1: "event type not configured"
  }

  const headPath = "/" + identity.localPeerId + "/" + HEAD_PREFIX + ev.path;
  const previousTransitionHash = tree.getHash(headPath) ?? null;

  // §2.1 field order follows the spec's table so this diffs line by line. `null` entries
  // are dropped by the omit-empty encoder, which is exactly the §1.3 absent-key rule the
  // `optional: true` fields in `types.ts` declare.
  const transition = Entity.create(
    HistoryTypes.Transition,
    Ecf.map(
      ["path", Ecf.text(ev.path)],
      ["event", Ecf.text(event)],
      ["hash", ev.newHash === null ? null : Ecf.bytes(ev.newHash)],
      ["previous_hash", ev.previousHash === null ? null : Ecf.bytes(ev.previousHash)],
      ["author", Ecf.bytes(ctx.author)],
      ["capability", Ecf.bytes(ctx.capability)],
      // §5.1: recorded "only when it differs from capability". The comparison is on
      // BYTES, not on reference identity — the fallback path hands us the same array
      // object twice and a `!==` check would emit a redundant field on every write.
      [
        "caller_capability",
        ctx.callerCapability === null || bytesEqual(ctx.callerCapability, ctx.capability)
          ? null
          : Ecf.bytes(ctx.callerCapability),
      ],
      ["handler", Ecf.text(ctx.handlerPattern)],
      ["operation", Ecf.text(ctx.operation)],
      ["timestamp", Ecf.uint(nowMs)],
      // `clock` is omitted: §2.1 says "Absent when the clock extension is not installed",
      // and CLOCK is not in this composition. See [assumptions].timestamp_source.
      ["chain_id", ctx.chainId === null ? null : Ecf.text(ctx.chainId)],
      ["parent_chain_id", ctx.parentChainId === null ? null : Ecf.text(ctx.parentChainId)],
      ["previous", previousTransitionHash === null ? null : Ecf.bytes(previousTransitionHash)],
    ),
  );

  // §3.1: "All transition entities are in the content store. Only the head pointer is in
  // the tree." Binding the transition AT the head path accomplishes both in one call —
  // `EntityTree.put` puts to the content store and binds the path to the entity's hash,
  // so `tree.getHash(headPath)` IS "hash of latest transition entity" per §3.1.
  tree.put(headPath, transition);

  if (config.maxDepth !== null) {
    pruneHistory(tree, store, headPath, config.maxDepth);
  }

  return {
    path: ev.path,
    event,
    transitionHash: transition.contentHash,
    headPath,
    provenance: ctx.provenance,
  };
}

/**
 * §3.3 `prune_history`.
 *
 * **This severs nothing today and the comment is the deliverable.** §3.3's algorithm
 * walks to the `max_depth`-th transition and then says: "sever the chain — the old
 * transition keeps its previous field (immutable in content store), but it's no longer
 * reachable from the head."
 *
 * A content-addressed entity cannot be edited, so "severing" means writing a NEW
 * transition identical to the last-kept one except with `previous` absent — which
 * changes its content hash, which changes the hash the transition BEFORE it points at,
 * which cascades to the head. Rewriting the chain is the only way to truncate it, and
 * rewriting an audit chain is the opposite of what an audit chain is for.
 *
 * So this walks and reports, and does not rewrite. `max_depth` pruning is a SHOULD
 * (§9.1), the transitions beyond the depth remain reachable, and the honest statement is
 * that we do not implement it rather than that we do. Routed to arch as A-3: §3.3's
 * pseudocode describes an in-place mutation of immutable entities.
 */
export function pruneHistory(
  tree: EntityTree,
  store: ContentStore,
  headPath: string,
  maxDepth: number,
): { walked: number; severedAt: Uint8Array | null } {
  const headHash = tree.getHash(headPath);
  if (headHash === undefined) {
    return { walked: 0, severedAt: null };
  }
  let current: Uint8Array | null = headHash;
  let count = 0;
  while (current !== null && count < maxDepth) {
    const entity: Entity | undefined = store.get(current);
    if (entity === undefined) {
      break;
    }
    current = Ecf.optBytes(entity.data, "previous");
    count += 1;
  }
  return { walked: count, severedAt: current };
}

function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) {
    return false;
  }
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) {
      return false;
    }
  }
  return true;
}
