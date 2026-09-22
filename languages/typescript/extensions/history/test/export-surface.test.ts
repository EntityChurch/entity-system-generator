/**
 * The recorder is module-private, enforced by the module resolver rather than by review.
 *
 * CONTENT had a MUST to point at (§3.4). HISTORY has none — and the surface is more
 * dangerous, not less. A caller able to reach `recordTransition` can append an entry to
 * an audit chain naming any `author` and any `capability` it likes, at any path, with a
 * `previous` that links it into the real chain. §7.2 calls the capability field the answer
 * to "under what authority?"; a forgeable answer is worse than no answer, because it is
 * believed.
 *
 * So this is OUR boundary, set for the same reason `[sdk_surface]` is ours: where the
 * corpus declines to standardise, the standard is ours to set (D16). Recorded in
 * `EXTENSION.toml [sdk].RecordTransition.public = false`.
 *
 * D13's Access row: the boundary is the `exports` map, not the file layout. Reading
 * `index.ts` and seeing no re-export is a source read, and a source read never decides
 * what is true.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import * as publicSurface from "@entity-core/extension-history";

test("no public export records a transition", () => {
  const offenders = Object.keys(publicSurface).filter((n) => /^record/i.test(n));
  assert.deepEqual(
    offenders,
    [],
    `reachable across the packaging boundary and able to write an audit entry: ${offenders.join(", ")}`,
  );
});

test("no public export prunes or severs a chain", () => {
  const offenders = Object.keys(publicSurface).filter((n) => /prune|sever/i.test(n));
  assert.deepEqual(offenders, []);
});

test("the recorder is reachable only as a consumer the peer invokes", () => {
  // `HistoryRecorder` IS exported — a composition has to construct one. What must not be
  // exported is the write path it wraps. The class exposes `onTreeChange`, which is the
  // peer's own callback signature and takes an event the peer constructs.
  assert.equal(typeof publicSurface.HistoryRecorder, "function");
  const proto = publicSurface.HistoryRecorder.prototype as unknown as Record<string, unknown>;
  assert.equal(typeof proto["onTreeChange"], "function");
  assert.equal(
    typeof proto["recordTransition"],
    "undefined",
    "the recorder must not re-expose the raw write path as a method",
  );
});

test("the deep import into internal/ is refused by the resolver, not by convention", async () => {
  // The negative control for the three assertions above, and the only one of the four
  // that tests the BOUNDARY rather than the surface. Everything above would still pass if
  // `internal/recorder.js` were importable directly.
  await assert.rejects(
    // The specifier is built at runtime so `tsc` cannot resolve it statically and kill
    // the build before the assertion runs — which is exactly how the CONTENT version of
    // this check failed on its first write (AP-3).
    async () => import(["@entity-core/extension-history", "dist", "internal", "recorder.js"].join("/")),
    (err: unknown) => {
      const code = (err as { code?: string }).code;
      assert.equal(
        code,
        "ERR_PACKAGE_PATH_NOT_EXPORTED",
        `expected the exports map to refuse the deep import, got ${String(code)}`,
      );
      return true;
    },
  );
});

test("the public surface is the declared one — no name arrived without a decision", () => {
  // D16 in miniature, inside the port. `tools/sdk-parity.py` compares ACROSS ports; this
  // asserts the shape WITHIN one, and it earned its place on the day the ports were
  // aligned — adding the flat constants failed this test before `sdk-parity` ran.
  //
  // Only RUNTIME-visible names. TypeScript `export type` is erased, so `Object.keys()`
  // never sees `Specificity`, `RecorderIdentity`, `RecordedTransition`,
  // `TransitionContext`, `HistoryConfig`, `RecorderStats`, `HistoryInstallation` or
  // `HistoryHandlerOptions`. They ARE public surface — `sdk-parity` reads them out of the
  // source and compares them across ports — and the two instruments see different halves
  // of one surface on purpose: this one sees what a caller can CALL, that one sees what a
  // caller can NAME.
  const expected = [
    "ALL_TYPES",
    "CONFIG",
    "CONFIG_PREFIX",
    "DEFAULT_EVENTS",
    "DEFAULT_QUERY_LIMIT",
    "EVENT_ACCESSED",
    "EVENT_CREATED",
    "EVENT_DELETED",
    "EVENT_UPDATED",
    "HEAD_PREFIX",
    "HISTORY_PATTERN",
    "HistoryEvent",
    "HistoryHandler",
    "HistoryRecorder",
    "HistoryTypes",
    "QUERY_PARAMS",
    "QUERY_RESULT",
    "ROLLBACK_PARAMS",
    "ROLLBACK_RESULT",
    "TRANSITION",
    "buildContext",
    "canonicalizePattern",
    "compareSpecificity",
    "configPath",
    "fromCoreEventType",
    "historyConfig",
    "historyEntity",
    "historyTypeDefs",
    "historyTypeEntities",
    "installHistory",
    "patternMatches",
    "patternSpecificity",
    "publishHistoryTypes",
    "resolveConfig",
  ].sort();
  assert.deepEqual(Object.keys(publicSurface).sort(), expected);
});
