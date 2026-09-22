/**
 * HISTORY §4 — the system history handler. Two operations, `query` (§4.3.1) and
 * `rollback` (§4.3.2).
 *
 * The distinguishing feature against CONTENT's handler is §4.2's **dual capability
 * model**: every operation authorizes twice, once for the handler and once for the
 * TARGET PATH. §7.1 is explicit about why — "This prevents using the history system to
 * access data the caller couldn't otherwise read." A handler grant on `system/history`
 * alone must not become a read primitive over the whole tree.
 */

import {
  Ecf,
  Entity,
  HandlerResult,
  Paths,
  Permissions,
  Status,
  errorResult,
  type ContentStore,
  type EntityTree,
  type Handler,
  type HandlerContext,
  type HandlerOperations,
} from "entity-core-protocol-typescript";

import { DEFAULT_QUERY_LIMIT, HISTORY_PATTERN, HEAD_PREFIX, HistoryTypes } from "./types.js";

export interface HistoryHandlerOptions {
  /** Cap on transitions walked in one query, whatever `limit` asks for. See `#query`. */
  readonly maxWalk?: number;
}

/**
 * A walk bound that is NOT in the spec, and is here because its absence is a denial of
 * service on an audited path. §2.3's `limit` defaults to 50 but is caller-supplied and
 * unbounded above; a chain is as long as the path has been written. §4.3.1's algorithm
 * walks `while current_hash is not null and len(transitions) < limit`, so a caller asking
 * for `limit: 2^53` walks the entire chain and materialises it.
 *
 * Declared in `EXTENSION.toml [assumptions].max_walk` rather than silently applied: it
 * changes an observable answer (`has_more` goes true earlier than a naive reading), and a
 * cap nobody declared is exactly the kind of local decision this repo does not get to make
 * quietly.
 */
const DEFAULT_MAX_WALK = 1000;

export class HistoryHandler implements Handler {
  readonly pattern = HISTORY_PATTERN;
  readonly name = "history";

  /** §4.1 / §9.3, verbatim — including the input/output types §4.1's manifest names. */
  readonly operations: HandlerOperations = {
    query: {
      inputType: HistoryTypes.QueryParams,
      outputType: HistoryTypes.QueryResult,
    },
    rollback: {
      inputType: HistoryTypes.RollbackParams,
      outputType: HistoryTypes.RollbackResult,
    },
  };

  readonly #maxWalk: number;

  constructor(options: HistoryHandlerOptions = {}) {
    this.#maxWalk = options.maxWalk ?? DEFAULT_MAX_WALK;
  }

  async handle(ctx: HandlerContext): Promise<HandlerResult> {
    // §4.3.1/§4.3.2's EXECUTE examples both carry `resource: {targets: [...]}`, and
    // GUIDE-EXTENSION-DEVELOPMENT §4.1 makes a resource-less directly-callable op a
    // `400 path_required`. Same code, same authority, same caveat as CONTENT's: it is
    // in `[error_surface].unresolved` because no spec code set defines it.
    if (ctx.resource === null) {
      return errorResult(
        Status.BadRequest,
        "path_required",
        `${HISTORY_PATTERN}:${ctx.operation} requires a resource naming the handler path (§4.3)`,
      );
    }

    switch (ctx.operation) {
      case "query":
        return this.#query(ctx);
      case "rollback":
        return this.#rollback(ctx);
      default:
        return errorResult(Status.NotSupported, "unsupported_operation", ctx.operation);
    }
  }

  /**
   * §4.2 `check_history_access` — the dual check, both halves.
   *
   * Returns `null` on ALLOW, or the error result to return.
   *
   * **Check 1 is already done and re-doing it would be wrong.** §4.2's first check is
   * "can caller use the history handler?", which the dispatcher performed before it built
   * this context — a `HandlerContext` exists only because `check_permission` returned
   * ALLOW for this pattern and operation. Re-running it here against `ctx.callerCapability`
   * would re-derive an answer we already have, and would answer DENY for an in-process
   * caller that legitimately has no caller capability at all.
   *
   * **Check 2 is the one that is ours**, and it is the one nothing else performs: the
   * target path is inside `params`, not inside `resource`, so the dispatcher's resource
   * scoping never sees it.
   */
  #checkTargetAccess(ctx: HandlerContext, targetPath: string): HandlerResult | null {
    const targetOperation = ctx.operation === "rollback" ? "put" : "get";

    if (ctx.callerCapability === null) {
      // In-process dispatch with no caller capability. The dispatcher does not build a
      // context without ALLOW, so check 1 passed; there is no token to run check 2
      // against. We DENY rather than allow: §7.1's whole purpose is that history must not
      // widen what a caller can reach, and "no token" is not evidence of authority.
      return errorResult(
        Status.Forbidden,
        "capability_denied",
        `${ctx.operation} requires a capability covering ${targetOperation} on ${targetPath} (§4.2)`,
      );
    }

    // §4.2 names `check_path_permission` from core and passes `"system/tree"` as the
    // handler pattern — NOT `system/history`. That is deliberate in the spec and it is
    // the crux of the dual model: the caller must hold authority over the target path as
    // a TREE path, exactly as if they were reading or writing it directly.
    const ok = Permissions.checkPathPermission(
      targetOperation,
      targetPath,
      ctx.callerCapability,
      "system/tree",
      ctx.peer.localPeerId,
    );
    if (!ok) {
      return errorResult(
        Status.Forbidden,
        "capability_denied",
        `capability does not cover ${targetOperation} on ${targetPath} (§4.2 dual check)`,
      );
    }
    return null;
  }

  /** The head-pointer path for a tracked path (§3.1). */
  #headPath(ctx: HandlerContext, canonicalTargetPath: string): string {
    return "/" + ctx.peer.localPeerId + "/" + HEAD_PREFIX + canonicalTargetPath;
  }

  // ── §4.3.1 query ────────────────────────────────────────────────────────────

  #query(ctx: HandlerContext): HandlerResult {
    let rawPath: string;
    try {
      rawPath = Ecf.requireText(ctx.params.data, "path");
    } catch {
      return errorResult(
        Status.BadRequest,
        "unexpected_params",
        "query expects {path: system/tree/path} (§2.3)",
      );
    }

    // §2.3: "The `path` field ... accepts short-form input. The handler canonicalizes it
    // before processing."
    const path = Paths.canonicalize(rawPath, ctx.peer.localPeerId);

    const denied = this.#checkTargetAccess(ctx, path);
    if (denied !== null) {
      return denied;
    }

    const limit = Number(Ecf.optUint(ctx.params.data, "limit") ?? BigInt(DEFAULT_QUERY_LIMIT));
    const before = Ecf.optUint(ctx.params.data, "before");
    const since = Ecf.optBytes(ctx.params.data, "since");
    const eventsFilter = Ecf.field(ctx.params.data, "events");
    const events =
      eventsFilter === null ? null : Ecf.asArray(eventsFilter).map((e) => Ecf.asText(e));

    const tree: EntityTree = ctx.peer.tree;
    const store: ContentStore = ctx.peer.contentStore;
    const headHash = tree.getHash(this.#headPath(ctx, path)) ?? null;

    if (headHash === null) {
      // §4.3.1: no history → empty result, NOT a 404. The path may simply never have
      // been written, and "no history" is a fact rather than a failure.
      return HandlerResult.ok(
        Entity.create(
          HistoryTypes.QueryResult,
          Ecf.map(
            ["path", Ecf.text(path)],
            ["transitions", Ecf.array([])],
            // `has_more` is REQUIRED (§2.4, not optional). `Ecf.map` drops a pair only
            // when the VALUE IS `null` — `Ecf.bool(false)` is a real value and survives —
            // so `false` encodes as present-and-false, which is what the oracle's
            // `HasMore bool \`cbor:"has_more"\`` (no `omitempty`) requires. Asserted in
            // `test/handler.test.ts` rather than left to the reader.
            ["has_more", Ecf.bool(false)],
          ),
        ),
      );
    }

    const collected: Entity[] = [];
    let current: Uint8Array | null = headHash;
    let walked = 0;

    while (current !== null && collected.length < limit && walked < this.#maxWalk) {
      const transition: Entity | undefined = store.get(current);
      if (transition === undefined) {
        break; // §4.3.1: "if transition is null: break"
      }
      walked += 1;

      // §4.3.1's filter order, transcribed. `since` BREAKS (it is an exclusive lower
      // bound on the walk); `before` and `events` CONTINUE (they skip an entry and keep
      // walking). Collapsing the three into one predicate changes the result set.
      if (since !== null && bytesEqual(current, since)) {
        break;
      }

      const ts = Ecf.optUint(transition.data, "timestamp");
      const previous = Ecf.optBytes(transition.data, "previous");

      if (before !== null && ts !== null && ts >= before) {
        current = previous;
        continue;
      }
      if (events !== null) {
        const ev = Ecf.optText(transition.data, "event");
        if (ev === null || !events.includes(ev)) {
          current = previous;
          continue;
        }
      }

      collected.push(transition);
      current = previous;
    }

    const hasMore = current !== null;

    // `transitions` carries each transition's DATA MAP INLINE, not its hash.
    //
    // §2.4 types the field `array_of: {type_ref: "system/history/transition"}`, which on
    // its own admits both readings — a `system/hash` field elsewhere in the same type is
    // also a reference to an entity. The oracle settles it: `HistoryQueryResultData` is
    // `Transitions []TransitionData` and it `ecf.Decode`s the array elements straight
    // into the field struct (`core/types/history.go:113-118`). A hash array decodes as
    // nothing there, and an array of `{type, data}` entity maps decodes as a struct with
    // every field zero — which would pass `transition_recorded` (the array is non-empty)
    // and fail `transition_event_created` with an empty event string. The wrong reading
    // fails four checks down, not here.
    //
    // §4.3.1's `system/envelope` form is a SHOULD "for efficiency"; the plain result is
    // conformant and the oracle's `unwrapResultEnvelope` accepts either. We send the
    // plain form and still pass `collected` as `included`, so a caller that resolves
    // transitions by hash gets the entities without a second round trip.
    const result = Entity.create(
      HistoryTypes.QueryResult,
      Ecf.map(
        ["path", Ecf.text(path)],
        ["head", Ecf.bytes(headHash)],
        ["transitions", Ecf.array(collected.map((t) => t.data))],
        ["has_more", Ecf.bool(hasMore)],
      ),
    );
    return HandlerResult.ok(result, collected);
  }

  // ── §4.3.2 rollback ─────────────────────────────────────────────────────────

  #rollback(ctx: HandlerContext): HandlerResult {
    let rawPath: string;
    let targetHash: Uint8Array;
    try {
      rawPath = Ecf.requireText(ctx.params.data, "path");
      targetHash = Ecf.requireBytes(ctx.params.data, "target_hash");
    } catch {
      return errorResult(
        Status.BadRequest,
        "unexpected_params",
        "rollback expects {path, target_hash} (§4.3.2)",
      );
    }

    const path = Paths.canonicalize(rawPath, ctx.peer.localPeerId);

    const denied = this.#checkTargetAccess(ctx, path);
    if (denied !== null) {
      return denied;
    }

    const tree: EntityTree = ctx.peer.tree;
    const store: ContentStore = ctx.peer.contentStore;

    // §7.5 History Exfiltration Prevention — THE security check of this operation.
    // "This prevents using rollback to write arbitrary content to a path — you can only
    // restore entities that were previously at that path." Without it, `rollback` is an
    // unrestricted `put` that bypasses every type and validation path a real put has.
    if (!this.#isInHistory(tree, store, ctx, path, targetHash)) {
      return errorResult(
        Status.NotFound,
        "not_in_history",
        "Target hash not found in history for this path",
      );
    }

    const entity = store.get(targetHash);
    if (entity === undefined) {
      // In history but no longer in the content store — GC'd per §3.3. Distinguished
      // from `not_in_history` on purpose: one says "you may not", the other says "it is
      // gone", and the caller's remedy differs.
      // `500 storage_error`, NOT a 404, and NOT CONTENT's `blob_not_found`.
      //
      // Two things are wrong with the obvious answer. A 404 says "not in history", which
      // is false — we just proved it IS in history — and would be indistinguishable from
      // the branch above. And `blob_not_found` is CONTENT's owned code; HISTORY can be
      // installed without CONTENT (§8.3 independence), so borrowing it would emit a code
      // whose defining spec is absent from the peer.
      //
      // Core §3.3's 500 row enumerates `storage_error` as "a content-store or tree
      // bind/read failed", which is exactly this: the chain references an entity the
      // store no longer holds, per §3.3's GC. Core-defined, so no code is invented here.
      return errorResult(
        Status.InternalError,
        "storage_error",
        "Target hash is in this path's history but the entity is no longer in the content store (§3.3 GC)",
      );
    }

    // §4.3.2: "Restore by rebinding the path to the old entity's content hash... This
    // goes through normal put, which will itself be recorded in history." So this write
    // fires the emit pathway and our own recorder observes it — the rollback appears in
    // the chain as an ordinary `updated`, which is what §4.3.2's closing paragraph says.
    //
    // §4.3.2: "the transition's `operation` field will reflect the rollback operation", and §2.1
    // records the remote caller as `author`. So the write carries THIS dispatch's execution context.
    // It did not in any of our three ports until 2026-09-12 (cross-port review): every rollback was
    // recorded as the peer's own `system/tree:put`, and the oracle's `rollback_new_transition`
    // checks only `event` and `hash`, so nothing could see it.
    tree.put(path, entity, ctx.emitContext());

    return HandlerResult.ok(
      Entity.create(
        HistoryTypes.RollbackResult,
        Ecf.map(["path", Ecf.text(path)], ["restored", Ecf.bytes(targetHash)]),
      ),
    );
  }

  /**
   * §4.3.2 `is_in_history`, transcribed — including the part that is easy to drop.
   *
   * It matches on `hash` **OR** `previous_hash`. Dropping the second disjunct still
   * passes a test that rolls back to a value the path once held, because that value is
   * some transition's `hash`. It fails only for the FIRST entity ever at the path when
   * you roll back past the write that replaced it — the oldest reachable state, which is
   * the one an undo most wants.
   *
   * **UNCAPPED, deliberately** — unlike `query`. `maxWalk` bounds a READ whose caller has
   * `has_more` to continue with; applied here it turned a real rollback target deeper than
   * `maxWalk` transitions into a false `404 not_in_history`, which breaks §4.3.2's MUST. The chain
   * is content-addressed and cannot cycle. (`[assumptions].max_walk`; 2026-09-12 cross-port review.)
   */
  #isInHistory(
    tree: EntityTree,
    store: ContentStore,
    ctx: HandlerContext,
    path: string,
    targetHash: Uint8Array,
  ): boolean {
    let current: Uint8Array | null = tree.getHash(this.#headPath(ctx, path)) ?? null;
    while (current !== null) {
      const transition: Entity | undefined = store.get(current);
      if (transition === undefined) {
        return false;
      }
      const h = Ecf.optBytes(transition.data, "hash");
      const ph = Ecf.optBytes(transition.data, "previous_hash");
      if ((h !== null && bytesEqual(h, targetHash)) || (ph !== null && bytesEqual(ph, targetHash))) {
        return true;
      }
      current = Ecf.optBytes(transition.data, "previous");
    }
    return false;
  }
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
