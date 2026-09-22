/**
 * `@entity-core/extension-history` — HISTORY v1.7 for the `typescript` peer.
 *
 * THE PUBLIC ENTRY POINT. What is absent from it is as deliberate as what is present:
 * `internal/recorder.js` is not re-exported and `package.json`'s `exports` map refuses a
 * deep import into it. A caller able to reach `recordTransition` could write a forged
 * entry into an audit chain — choosing its own `author` and `capability` — which is a
 * strictly worse escalation than the one CONTENT §3.4 forbids. `test/export-surface.test.ts`
 * asserts on the module resolver's refusal, not on a review.
 */

import { type Peer } from "entity-core-protocol-typescript";

import { HistoryHandler, type HistoryHandlerOptions } from "./handler.js";
import { HistoryRecorder } from "./sdk.js";
import { type RecorderIdentity } from "./internal/recorder.js";
import { HISTORY_PATTERN, publishHistoryTypes } from "./types.js";

export {
  // flat first — these are the cross-port CONTRACT (see types.ts)
  TRANSITION,
  CONFIG,
  QUERY_PARAMS,
  QUERY_RESULT,
  ROLLBACK_PARAMS,
  ROLLBACK_RESULT,
  ALL_TYPES,
  EVENT_CREATED,
  EVENT_UPDATED,
  EVENT_DELETED,
  EVENT_ACCESSED,
  historyTypeEntities,
  // grouped aliases
  HistoryTypes,
  HISTORY_PATTERN,
  HEAD_PREFIX,
  CONFIG_PREFIX,
  HistoryEvent,
  DEFAULT_EVENTS,
  DEFAULT_QUERY_LIMIT,
  fromCoreEventType,
  historyTypeDefs,
  publishHistoryTypes,
  historyEntity,
} from "./types.js";

export {
  canonicalizePattern,
  patternSpecificity,
  compareSpecificity,
  patternMatches,
  type Specificity,
} from "./patterns.js";

export { HistoryHandler, type HistoryHandlerOptions } from "./handler.js";

export {
  HistoryRecorder,
  buildContext,
  historyConfig,
  configPath,
  resolveConfig,
  type RecorderStats,
} from "./sdk.js";

export type { RecorderIdentity, RecordedTransition, TransitionContext, HistoryConfig }
  from "./internal/recorder.js";

export interface HistoryInstallation {
  readonly pattern: string;
  readonly interfacePath: string;
  readonly typePaths: readonly string[];
  readonly recorder: HistoryRecorder;
  /**
   * Whether the peer's tree-change events can carry an execution context AT ALL.
   *
   * `false` on every peer measured so far, and the composition prints it. It is on the
   * installation result rather than buried in stats because a system that records
   * transitions with fabricated provenance and a system that records real provenance are
   * different systems, and the difference has to be visible at the seam where someone
   * decides to trust the audit trail.
   */
  readonly contextAvailable: () => "unknown" | "yes" | "not-observed";
}

/**
 * Install HISTORY into a live peer: handler, types, and the position-4 emit consumer.
 *
 * **The order of the three steps matters and is not arbitrary.**
 *
 *  1. `registerHandler` performs the §11.6.1 writes (manifest, interface, grant,
 *     signature). Those are tree writes, and if the recorder were already registered it
 *     would observe them — §5.1's own installation-emits problem, which this repo routed
 *     during cycle 1 and which arch has not closed. Registering the consumer LAST makes
 *     the exposure window empty by construction rather than by configuration.
 *  2. `publishHistoryTypes` — same reasoning, same window.
 *  3. `registerConsumer` last.
 *
 * The consumer is appended to the peer's `EmitBus` list, and SYSTEM-COMPOSITION §2.2 puts
 * history at position 4. **This function cannot enforce that** — the bus has no position
 * argument and appends. In a composition with CONTENT only, history is the sole consumer
 * and position 4 is vacuously satisfied. With CLOCK or COMPUTE present it would not be,
 * and the composition would have to control call order. Declared in the composition's
 * `SYSTEM.toml`, not asserted here.
 */
export function installHistory(
  peer: Peer,
  options: HistoryHandlerOptions = {},
): HistoryInstallation {
  peer.registerHandler(new HistoryHandler(options));

  const interfacePath = "/" + peer.localPeerId + "/system/handler/" + HISTORY_PATTERN;
  const typePaths = publishHistoryTypes(peer.tree, peer.localPeerId);

  // §2.1's autonomous-case values, captured once at install time. `handlerGrantHash` is
  // the grant `registerHandler` just bound for our own pattern — the "handler grant" §2.1
  // names. Read back from the tree rather than reconstructed, so it is the same bytes the
  // peer published.
  const grantPath =
    "/" + peer.localPeerId + "/system/capability/grants/" + HISTORY_PATTERN;
  const grantHash = peer.tree.getHash(grantPath);

  const identity: RecorderIdentity = {
    localIdentityHash: peer.localIdentity.identityHash,
    // Falling back to the identity hash when the grant is unreadable keeps the field
    // non-empty (§2.1 makes `capability` required) and is recorded as a distinct
    // condition by the composition report rather than passed off as a grant.
    handlerGrantHash: grantHash ?? peer.localIdentity.identityHash,
    localPeerId: peer.localPeerId,
  };

  const recorder = new HistoryRecorder(peer, identity);
  peer.emit.registerConsumer(recorder);

  return {
    pattern: HISTORY_PATTERN,
    interfacePath,
    typePaths,
    recorder,
    // OBSERVED, never declared. Was a hardcoded `false` that said "measured" — a
    // claim about another team's peer, frozen here and asserted by our own tests.
    contextAvailable: () => recorder.contextObserved(),
  };
}
