/**
 * HISTORY — the SDK face, and the **emit-consumer face**.
 *
 * The emit consumer is the reason this extension was built second. `DESIGN-THE-SDK-LAYER`
 * §1 named four faces and CONTENT exercised three; this file is the fourth. Everything
 * about it that is interesting is about the two things the peer does not give us:
 * the execution context (see `buildContext`) and read events (see `EXTENSION.toml
 * [substrate.accessed_event]`).
 */

import {
  Ecf,
  Entity,
  type ContentStoreEvent,
  type EmitConsumer,
  type EntityTree,
  type Peer,
  type TreeChangeEvent,
} from "entity-core-protocol-typescript";

import {
  recordTransition,
  findHistoryConfig,
  isLocalHistoryPath,
  type RecordedTransition,
  type RecorderIdentity,
  type TransitionContext,
} from "./internal/recorder.js";
import { CONFIG_PREFIX, HistoryTypes, HISTORY_PATTERN } from "./types.js";

// ── the emit consumer (§5.1, SYSTEM-COMPOSITION §2.2 position 4) ─────────────────

/**
 * What the recorder does when the tree-change event carries no execution context.
 *
 * **On all three peers, it never carries one.** `typescript` declares an `EmitContext`
 * with almost exactly SYSTEM-COMPOSITION §1.4's field inventory and constructs it at zero
 * sites; `python` and `rust` have no context field on the event at all. So this is not a
 * fallback that fires occasionally — today it fires on every write, and the constant is
 * named `AUTONOMOUS_FALLBACK` rather than something reassuring for that reason.
 *
 * §2.1 defines the values for the autonomous case exactly:
 *   author     — "For autonomous operations (no external request), the local peer's
 *                 identity hash."
 *   capability — "For autonomous operations, the handler grant."
 *
 * A tree-change event with no execution context is, from the recorder's vantage,
 * indistinguishable from an autonomous write, so those are the values recorded. **That is
 * a reading of the spec, and it is also wrong about the world**: a `system/tree:put` that
 * arrived over the wire from a remote caller is not autonomous, and the transition will
 * say it was. §7.2 calls `capability` the answer to "under what authority?" — and on these
 * peers the answer is always "its own".
 *
 * Which is why `provenance` exists and why the composition reports it. Routed to keystone
 * as H8; see `EXTENSION.toml [substrate.execution_context]`.
 */
const AUTONOMOUS_FALLBACK = "autonomous-fallback" as const;

/**
 * Map a peer tree-change event's context onto §2.1's fields.
 *
 * `ev.context` is typed on the `typescript` peer and absent from the other two, so this
 * function takes the already-extracted pieces rather than the event: the per-target
 * difference is which of them can ever be non-null, and that belongs at the boundary, not
 * threaded through the recorder.
 */
export function buildContext(
  identity: RecorderIdentity,
  operation: string,
  handlerPattern: string,
  carried: {
    readonly author?: Uint8Array;
    readonly callerCapability?: Uint8Array;
    readonly handlerGrant?: Uint8Array;
    readonly handlerPattern?: string;
    readonly operation?: string;
    readonly chainId?: string;
    readonly parentChainId?: string;
  } | null,
): TransitionContext {
  if (carried === null || carried.author === undefined) {
    return {
      author: identity.localIdentityHash,
      capability: identity.handlerGrantHash,
      callerCapability: null,
      handlerPattern,
      operation,
      chainId: null,
      parentChainId: null,
      provenance: AUTONOMOUS_FALLBACK,
    };
  }
  // §2.1 `capability`: "For caller-authorized writes, the external caller's capability...
  // For handler-authorized writes, the handler's own grant." The peer's own EmitContext
  // comment says `capability` was "dropped as redundant with callerCapability /
  // handlerGrant", which is the same derivation read from the other side.
  const capability =
    carried.handlerGrant ?? carried.callerCapability ?? identity.handlerGrantHash;
  return {
    author: carried.author,
    capability,
    callerCapability: carried.callerCapability ?? null,
    handlerPattern: carried.handlerPattern ?? handlerPattern,
    operation: carried.operation ?? operation,
    chainId: carried.chainId ?? null,
    parentChainId: carried.parentChainId ?? null,
    provenance: "context",
  };
}

/** Counters the composition and the tests read. Not part of §2.1. */
export interface RecorderStats {
  readonly observed: number;
  readonly recorded: number;
  readonly skippedSelfGuard: number;
  readonly skippedUnconfigured: number;
  readonly fallbackContexts: number;
  /**
   * Events whose carried context supplied an author. The counterpart of
   * {@link fallbackContexts}; together they are the evidence behind
   * `contextObserved()`, counted rather than inferred so the composition can print the
   * quantity beside the verdict.
   */
  readonly contextContexts: number;
}

/**
 * The §5.1 recorder, as a peer emit consumer.
 *
 * **Registration order is the composition's job, not this class's**, and that is
 * SYSTEM-COMPOSITION §2.2: history is position 4, after clock (2, 3) and before compute
 * (5) and subscription (8). This peer's `EmitBus` is a plain ordered list with no
 * position argument — `registerConsumer` appends — so ordering is achieved by the order
 * the composition calls it in, and there is nothing here that can enforce it. That is
 * recorded in the composition's `SYSTEM.toml` and is the first real work
 * `tools/compose.py`'s ordering has to do.
 */
export class HistoryRecorder implements EmitConsumer {
  readonly name = "history";

  #observed = 0;
  #recorded = 0;
  #skippedSelfGuard = 0;
  #skippedUnconfigured = 0;
  #fallbackContexts = 0;
  #contextContexts = 0;

  readonly #tree: EntityTree;
  readonly #store: Peer["contentStore"];
  readonly #identity: RecorderIdentity;
  readonly #nowMs: () => bigint;
  readonly #last: RecordedTransition[] = [];

  constructor(peer: Peer, identity: RecorderIdentity) {
    this.#tree = peer.tree;
    this.#store = peer.contentStore;
    this.#identity = identity;
    this.#nowMs = () => peer.nowMs;
  }

  /**
   * §6.10's content-store event. History does not consume it: §5.1 records TREE
   * transitions, and a content-store put with no binding is not a transition — the same
   * bytes may be bound at many paths or none. Implemented as an explicit no-op rather
   * than omitted, because `EmitConsumer` requires the method and an empty body with no
   * comment reads as an oversight.
   */
  onContentStore(_ev: ContentStoreEvent): void {
    /* not a tree transition — see the doc comment */
  }

  onTreeChange(ev: TreeChangeEvent): void {
    this.#observed += 1;

    if (isLocalHistoryPath(ev.path, this.#identity.localPeerId)) {
      this.#skippedSelfGuard += 1;
      return;
    }

    const ctx = buildContext(this.#identity, "put", "system/tree", ev.context);
    if (ctx.provenance === AUTONOMOUS_FALLBACK) {
      this.#fallbackContexts += 1;
    } else {
      this.#contextContexts += 1;
    }

    const recorded = recordTransition(
      this.#tree,
      this.#store,
      this.#identity,
      ev,
      ctx,
      this.#nowMs(),
    );
    if (recorded === null) {
      this.#skippedUnconfigured += 1;
      return;
    }
    this.#recorded += 1;
    this.#last.push(recorded);
  }

  /**
   * `"unknown"` | `"yes"` | `"not-observed"` — what this recorder has SEEN.
   *
   * **`"not-observed"`, never `"no"`, and the name is the whole correction.** "No" is a
   * claim about the PEER; what this counter knows is a fact about THESE EVENTS. A
   * composition driven only by autonomous writes legitimately sees zero contexts on a
   * peer that delivers them perfectly.
   *
   * This replaced a hardcoded `contextAvailable: false` carrying the comment "measured":
   * a claim about ANOTHER TEAM'S PEER, frozen in our source and asserted by our own
   * tests. When keystone landed H8 the peers began delivering a context and all three
   * ports went on reporting `false`. Nothing could have noticed — we wrote the value and
   * we wrote the check. D13 already forbids the shape; it had been applied to every claim
   * about a peer except the one we stored in our own struct.
   */
  contextObserved(): "unknown" | "yes" | "not-observed" {
    if (this.#contextContexts > 0) return "yes";
    if (this.#observed > 0) return "not-observed";
    return "unknown";
  }

  get stats(): RecorderStats {
    return {
      observed: this.#observed,
      recorded: this.#recorded,
      skippedSelfGuard: this.#skippedSelfGuard,
      skippedUnconfigured: this.#skippedUnconfigured,
      fallbackContexts: this.#fallbackContexts,
      contextContexts: this.#contextContexts,
    };
  }

  /** The transitions recorded so far, oldest first. Test and composition surface. */
  get recordedTransitions(): readonly RecordedTransition[] {
    return this.#last;
  }
}

// ── configuration (§6.1) ────────────────────────────────────────────────────────

/**
 * Build a `system/history/config` entity (§2.2).
 *
 * §6.1 is explicit that no handler operation is needed — "configuration uses the standard
 * tree `put`" — so this builds the entity and the caller binds it. Exposed because a
 * composition and a test both need to configure history, and hand-building the map at
 * each site is how two call sites end up with different `events` defaults.
 */
export function historyConfig(options: {
  readonly pattern: string;
  readonly enabled?: boolean;
  readonly events?: readonly string[];
  readonly maxDepth?: number | null;
}): Entity {
  return Entity.create(
    HistoryTypes.Config,
    Ecf.map(
      ["pattern", Ecf.text(options.pattern)],
      // §2.2 types `enabled` as a required `primitive/bool`. `Ecf.map` drops a pair only
      // when the value is `null`, so `Ecf.bool(false)` survives as present-and-false —
      // which matters, because a disabled config that decoded as malformed would be
      // SKIPPED by `parseConfig` and would silently RE-ENABLE history for the path it was
      // written to turn off. Asserted in `test/config.test.ts`.
      ["enabled", Ecf.bool(options.enabled ?? true)],
      [
        "events",
        options.events === undefined
          ? null
          : Ecf.array(options.events.map((e) => Ecf.text(e))),
      ],
      [
        "max_depth",
        options.maxDepth === undefined || options.maxDepth === null
          ? null
          : Ecf.uint(BigInt(options.maxDepth)),
      ],
    ),
  );
}

/** The tree path a named config binds at (§6.1). */
export function configPath(localPeerId: string, name: string): string {
  return "/" + localPeerId + "/" + CONFIG_PREFIX + "/" + name;
}

/**
 * Resolve which config governs a path (§6.2) — the public form of the recorder's own
 * lookup, exposed because it is the only way an operator can answer "is this path
 * audited, and by which rule" without writing to it and looking.
 */
export function resolveConfig(tree: EntityTree, path: string, localPeerId: string) {
  return findHistoryConfig(tree, path, localPeerId);
}

/** §4.1's pattern, re-exported so a caller does not retype the literal. */
export { HISTORY_PATTERN };
