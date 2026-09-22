/**
 * The §3.4 MUST, enforced by the module resolver rather than by review.
 *
 *   "Implementations MUST NOT expose `reassemble_content` as a public substrate
 *    primitive callable from third-party / SDK / external consumer code without an
 *    explicit capability-checking wrapper."   — EXTENSION-CONTENT §3.4
 *
 * The import below is **by package name**, self-referencing through this package's own
 * `exports` map — the same resolution a third party gets. That is the point: reading
 * `index.ts` and seeing no `export { reassembleContent }` is a source read, and a source
 * read decides what to build, never what is true (D13). What decides here is node.
 *
 * D13's Access row in one sentence: the boundary is not the class, it is the boundary.
 * For npm the boundary is the `exports` map. Four of this ecosystem's control nominations
 * were made by reading `public` and stopping; three were wrong.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import * as publicSurface from "@entity-core/extension-content";

test("§3.4: no public export reassembles content", () => {
  const names = Object.keys(publicSurface);
  const offenders = names.filter((n) => /reassemble/i.test(n) && n !== "reassembleUnderCapability");
  assert.deepEqual(
    offenders,
    [],
    `§3.4 MUST: these are reachable across the packaging boundary and reassemble: ${offenders.join(", ")}`,
  );
});

test("§3.4: the only reassembly route requires a HandlerContext", () => {
  assert.equal(typeof publicSurface.reassembleUnderCapability, "function");
  // Arity is the structural half of the check: the first parameter is the context a
  // consumer cannot manufacture. A zero/one-arg variant would mean somebody "simplified"
  // the wrapper into the primitive the MUST forbids.
  assert.equal(
    publicSurface.reassembleUnderCapability.length,
    2,
    "reassembleUnderCapability(ctx, blobHash) — the ctx argument IS the capability check",
  );
});

test("§3.4: the wrapper refuses a context from another handler's dispatch", () => {
  const foreign = { pattern: "local/files", callerCapability: {} } as never;
  assert.throws(
    () => publicSurface.reassembleUnderCapability(foreign, new Uint8Array(33)),
    /system\/content handler context/,
  );
});

test("§3.4: the wrapper refuses a context carrying no caller capability", () => {
  const uncapped = { pattern: "system/content", callerCapability: null } as never;
  assert.throws(
    () => publicSurface.reassembleUnderCapability(uncapped, new Uint8Array(33)),
    /no caller capability/,
  );
});

test("the internal module is not reachable through the exports map", async () => {
  // `exports` publishes exactly one entry ("."). A deep import of the internal path is
  // what a determined consumer would try next, and node must refuse it — otherwise the
  // omission from index.ts is decoration.
  //
  // The specifier is assembled at runtime on purpose. Written as a literal, `tsc`
  // resolves it at COMPILE time, fails with TS2307, and the build dies before the
  // assertion can run — the check passing and the check being unrunnable look
  // identical from the outside. Built at runtime, node is the one that refuses, which
  // is the layer the MUST is about.
  const deepImport = "@entity-core/extension-content" + "/internal/reassemble.js";
  await assert.rejects(
    () => import(deepImport),
    (err: unknown) => {
      const code = (err as { code?: string }).code;
      return code === "ERR_PACKAGE_PATH_NOT_EXPORTED" || code === "ERR_MODULE_NOT_FOUND";
    },
    "a deep import into internal/ must be refused by the exports map",
  );
});
