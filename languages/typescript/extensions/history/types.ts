/**
 * HISTORY — the six owned entity types (§9.2, defined at §2.1–§2.4 and §4.3.2).
 *
 * Rendered through the PEER'S OWN `TypeDef` / `FSpec` builder, for the same reason
 * CONTENT does it: our type entities cannot drift from the peer's rendering
 * convention in a way a review would miss, and the oracle reads these entities by
 * content hash.
 *
 * WHY THE MODULE PUBLISHES THESE AT ALL — measured for CONTENT and unchanged here:
 * keystone's handler registration writes the §11.6.1 handler entity, interface
 * entity, grant and signature, and NO type entities. The oracle's `history`
 * category declares six `type_*` checks (`history.go:30-35`), and nobody else
 * writes them.
 *
 * §9.2 is an explicit six-line list, which is why `EXTENSION.toml`'s `owned_types`
 * is a derivation with the same confidence as a transcription — see that file's
 * `[contract.derived_from]`.
 */

import { Entity, FSpec, TypeDef, type EntityTree } from "entity-core-protocol-typescript";

const ref = FSpec.ref;
const arrayOf = FSpec.array;

/**
 * Type-path constants, FLAT — and the bundle below is the alias, not the other way round.
 *
 * CONTENT shipped these bundled into a `ContentTypes` object in `typescript` and flat in
 * `python`/`rust`, and `tools/sdk-parity.py`'s first run reported eight names of drift
 * from that one decision (`EXTENSION.toml [sdk_surface].drift`). It was a choice made
 * once in the first port and never made again.
 *
 * **This is the second extension, and the gate exists now**, so the decision gets made
 * deliberately instead: the flat names are the CONTRACT, in every port, and
 * {@link HistoryTypes} stays as an ergonomic grouping for callers who want one. D16's
 * promotion criterion is "if it survives a second extension" — it does not get to.
 */
export const TRANSITION = "system/history/transition";
export const CONFIG = "system/history/config";
export const QUERY_PARAMS = "system/history/query-params";
export const QUERY_RESULT = "system/history/query-result";
export const ROLLBACK_PARAMS = "system/history/rollback-params";
export const ROLLBACK_RESULT = "system/history/rollback-result";

/** §9.2's six, in the spec's listed order. */
export const ALL_TYPES: readonly string[] = [
  TRANSITION,
  CONFIG,
  QUERY_PARAMS,
  QUERY_RESULT,
  ROLLBACK_PARAMS,
  ROLLBACK_RESULT,
];

/** The grouped form. Same six strings as the flat exports above. */
export const HistoryTypes = {
  Transition: "system/history/transition",
  Config: "system/history/config",
  QueryParams: "system/history/query-params",
  QueryResult: "system/history/query-result",
  RollbackParams: "system/history/rollback-params",
  RollbackResult: "system/history/rollback-result",
} as const;

/** The handler pattern (§4.1). Everything the module binds derives from this. */
export const HISTORY_PATTERN = "system/history";

/**
 * §3.1 — the head-pointer prefix, and §3.2's self-guard subject.
 *
 * These are the SAME STRING for a reason worth stating: the guard in §3.2 targets
 * `system/history/head`, which is exactly the prefix this module writes to. The
 * guard is deliberately NARROWER than `system/history/` — §3.2 says config paths
 * "SHOULD be recorded as normal transitions for audit purposes" — so a constant
 * named `HISTORY_NAMESPACE` would be the wrong thing to guard on and is not
 * defined here on purpose.
 */
export const HEAD_PREFIX = "system/history/head";

/** §6.1 — where configurations live. NOT self-guarded; see above. */
export const CONFIG_PREFIX = "system/history/config";

/**
 * §2.1's event vocabulary. Four values, and `Accessed` is the MAY (§9.1).
 *
 * **These are not the core's strings.** The peer's emit pathway derives
 * `created | modified | deleted` (§6.10); §2.1's table says
 * `created | updated | deleted | accessed`. `modified` and `updated` are the same
 * event under two names — see {@link fromCoreEventType}, and
 * `EXTENSION.toml [assumptions].event_vocabulary`.
 */
export const EVENT_CREATED = "created";
export const EVENT_UPDATED = "updated";
export const EVENT_DELETED = "deleted";
export const EVENT_ACCESSED = "accessed";

/** The grouped form. Same four strings as the flat exports above. */
export const HistoryEvent = {
  Created: EVENT_CREATED,
  Updated: EVENT_UPDATED,
  Deleted: EVENT_DELETED,
  Accessed: EVENT_ACCESSED,
} as const;

/** §2.2 "Default events". `accessed` is opt-in and this composition never records it. */
export const DEFAULT_EVENTS: readonly string[] = [
  HistoryEvent.Created,
  HistoryEvent.Updated,
  HistoryEvent.Deleted,
];

/** §2.3 — "Maximum transitions to return. Default: 50". */
export const DEFAULT_QUERY_LIMIT = 50;

/**
 * Map a core tree-change `eventType` onto §2.1's vocabulary.
 *
 * The ONLY difference is `modified` → `updated`. Returning `null` for anything
 * else is deliberate: an unrecognised core event is not silently recorded as some
 * nearest neighbour, because the event string is a field of a content-addressed
 * entity and a wrong value there is a wrong hash forever.
 */
export function fromCoreEventType(coreEventType: string): string | null {
  switch (coreEventType) {
    case "created":
      return HistoryEvent.Created;
    case "modified":
      return HistoryEvent.Updated;
    case "deleted":
      return HistoryEvent.Deleted;
    default:
      return null;
  }
}

/**
 * The six type definitions, in §9.2's listed order.
 *
 * Field order inside a definition does NOT affect the rendered bytes — the codec
 * re-sorts map keys length-then-lex — but it is kept in spec order so a reader can
 * diff this against §2.1 line by line.
 */
export function historyTypeDefs(): readonly TypeDef[] {
  return [
    // §2.1 — the transition. Thirteen fields, four of them non-optional, and the
    // two that matter for §9.1's MUST are `author` and `capability`.
    //
    // `provenance` IS NOT HERE. It is ours, not the spec's, and adding a field to
    // a spec-declared type would change the entity's content hash away from every
    // other implementation's — the exact silent cross-impl break the CONTENT work
    // was about. It is recorded out-of-band; see `internal/recorder.ts`.
    new TypeDef(HistoryTypes.Transition)
      .f("path", ref("system/tree/path"))
      .f("event", ref("primitive/string"))
      .f("hash", ref("system/hash").opt())
      .f("previous_hash", ref("system/hash").opt())
      .f("author", ref("system/hash"))
      .f("capability", ref("system/hash"))
      .f("caller_capability", ref("system/hash").opt())
      .f("handler", ref("system/tree/path"))
      .f("operation", ref("primitive/string"))
      .f("timestamp", ref("primitive/uint"))
      .f("clock", ref("system/clock/state").opt())
      .f("chain_id", ref("primitive/string").opt())
      .f("parent_chain_id", ref("primitive/string").opt())
      .f("previous", ref("system/hash").opt()),

    // §2.2 — per-path-pattern configuration.
    new TypeDef(HistoryTypes.Config)
      .f("pattern", ref("system/tree/path"))
      .f("enabled", ref("primitive/bool"))
      .f("events", arrayOf(ref("primitive/string")).opt())
      .f("max_depth", ref("primitive/uint").opt()),

    // §2.3
    new TypeDef(HistoryTypes.QueryParams)
      .f("path", ref("system/tree/path"))
      .f("limit", ref("primitive/uint").opt())
      .f("since", ref("system/hash").opt())
      .f("before", ref("primitive/uint").opt())
      .f("events", arrayOf(ref("primitive/string")).opt()),

    // §2.4 — `transitions` is an array of the ENTITIES, not of hashes. §4.3.1 says
    // the handler SHOULD return a `system/envelope` when it includes them; see
    // handler.ts for which form we emit and why.
    new TypeDef(HistoryTypes.QueryResult)
      .f("path", ref("system/tree/path"))
      .f("head", ref("system/hash").opt())
      .f("transitions", arrayOf(ref(HistoryTypes.Transition)))
      .f("has_more", ref("primitive/bool")),

    // §4.3.2
    new TypeDef(HistoryTypes.RollbackParams)
      .f("path", ref("system/tree/path"))
      .f("target_hash", ref("system/hash")),

    new TypeDef(HistoryTypes.RollbackResult)
      .f("path", ref("system/tree/path"))
      .f("restored", ref("system/hash")),
  ];
}

/** `(typeName, system/type entity)` for each of the six — the materialised form. */
export function historyTypeEntities(): readonly (readonly [string, Entity])[] {
  return historyTypeDefs().map((def) => [def.treePath.replace(/^system\/type\//, ""), def.toEntity()] as const);
}

/**
 * Publish the type entities into the peer's tree at `system/type/{name}`.
 *
 * I1 (owned-namespace containment) holds structurally: every path is
 * `system/type/` + a name from {@link HistoryTypes}, and `system/type/*` is the
 * core's shared type index every extension writes into by design.
 */
export function publishHistoryTypes(tree: EntityTree, localPeerId: string): readonly string[] {
  const written: string[] = [];
  for (const def of historyTypeDefs()) {
    const path = "/" + localPeerId + "/" + def.treePath;
    tree.put(path, def.toEntity());
    written.push(path);
  }
  return written;
}

/** Build one of our own entities without reaching for `Entity.create` at each site. */
export function historyEntity(type: string, data: Parameters<typeof Entity.create>[1]): Entity {
  return Entity.create(type, data);
}
