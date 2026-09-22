/**
 * The evaluator is module-private, enforced by the MODULE RESOLVER rather than by review.
 *
 * CONTENT had a §3.4 MUST to point at and HISTORY had none. COMPUTE has neither, and the
 * surface is the most dangerous of the three: `evaluate(entity, scope, budget, ctx)` takes
 * its whole authority as an argument. A caller able to reach it constructs its own
 * `EvalContext` and sets `hasContentStoreAccess: true`, which is §4.2's Tier 0 — the
 * allowance that bypasses all three resolution tiers and turns the evaluator into exactly
 * the content-store oracle §4.2's D2 ruling exists to prevent. It can also hand itself an
 * unbounded `Budget`, which is §5 removed.
 *
 * So this is OUR boundary, set for the same reason `[sdk_surface]` is ours: where the
 * corpus declines to standardise, the standard is ours to set (D16).
 *
 * D13's Access row: **the boundary is the `exports` map, not the file layout.** Reading
 * `index.ts` and seeing no re-export is a source read, and a source read never decides what
 * is true. These tests import the package BY NAME, so they resolve through the map a
 * consumer resolves through.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import * as publicSurface from "@entity-core/extension-compute";

test("no public export evaluates an expression with a caller-supplied context", () => {
  // `evaluate` is the internal entry point. `ComputeEvaluator` IS public and is the
  // difference that matters: it builds the `EvalContext` itself, so a caller cannot
  // set Tier 0 or widen the budget past the peer's ceiling.
  const offenders = Object.keys(publicSurface).filter((n) => n === "evaluate" || n === "evaluateInner");
  assert.deepEqual(
    offenders,
    [],
    `reachable across the packaging boundary and takes its authority as an argument: ${offenders.join(", ")}`,
  );
});

test("no public export names the internal scope or context primitives", () => {
  const offenders = Object.keys(publicSurface).filter(
    (n) => /^(emptyScope|loadScope|captureScope|resolveOrError|validateComputeResolvable)$/.test(n),
  );
  assert.deepEqual(offenders, []);
});

test("the deep import into internal/ is refused by the exports map", async () => {
  // THE ASSERTION THAT IS ABOUT THE BOUNDARY RATHER THAN ABOUT THE FILE. A literal
  // specifier here would make `tsc` fail the build before the assertion could run —
  // which is AP-3's shape, a check that cannot reach its own assertion — so the
  // specifier is built at runtime.
  const deep = ["@entity-core/extension-compute", "dist", "internal", "evaluator.js"].join("/");
  await assert.rejects(
    () => import(deep),
    (e: unknown) => {
      const code = (e as { code?: string }).code ?? "";
      return code === "ERR_PACKAGE_PATH_NOT_EXPORTED" || code === "ERR_MODULE_NOT_FOUND";
    },
    "a deep import into internal/ must be refused by the resolver, not merely undocumented",
  );
});

test("the public surface exports the operations `[sdk_surface].required` names", () => {
  // D16's gate needs two ports to compare and there is one. This is the half that can
  // run at N=1: the names the contract declares are actually exported, so the second
  // port has something to disagree WITH rather than a list nobody checked.
  const required = [
    "ComputeEvaluator", "ComputeHandler", "installCompute",
    "isComputeExpression", "isComputeType",
    "computeTypeDefs", "computeTypeEntities", "publishComputeTypes", "computeEntity",
    "assertNotBuiltinOverride", "DEFAULT_LIMITS",
    "COMPUTE_PATTERN", "BUILTINS_PREFIX", "PROCESSES_PREFIX",
    "CORE_EXPRESSION_TYPES", "INLINE_EXPRESSION_TYPES", "ALL_TYPES",
    "ReactiveEngine", "deterministicId",
  ];
  const missing = required.filter((n) => !(n in publicSurface));
  assert.deepEqual(missing, [], `declared in [sdk_surface].required and not exported: ${missing.join(", ")}`);
});

test("§4: the builtin override guard refuses, and refuses only builtin paths", () => {
  // OURS TO ENFORCE AS OF v3.29, AND IT WAS NOT BEFORE. Through v3.28 §3.5 described
  // this rule as a subset of core's `system/*` reservation and said an implementation
  // enforcing that reservation "needs no separate compute-specific guard".
  // `ENTITY-CORE-PROTOCOL` 0.8.2.13 withdrew the reservation, so v3.29 restates the
  // prohibition on its own basis and nothing upstream refuses this on our behalf.
  //
  // BOTH DIRECTIONS. A guard that refuses everything is not a guard, and no oracle
  // check anywhere attempts a registration at a builtins path — so this negative
  // control is the only thing standing between the rule and a `throw` nobody tested.
  const { assertNotBuiltinOverride } = publicSurface;

  assert.throws(() => assertNotBuiltinOverride("system/compute/builtins/arithmetic"));
  assert.throws(() => assertNotBuiltinOverride("system/compute/builtins"));
  assert.throws(() => assertNotBuiltinOverride("/z6Mk.../system/compute/builtins/logic"));

  assert.doesNotThrow(() => assertNotBuiltinOverride("system/compute"));
  assert.doesNotThrow(() => assertNotBuiltinOverride("system/content"));
  // The near-miss that a `startsWith` without the separator would wrongly refuse.
  assert.doesNotThrow(() => assertNotBuiltinOverride("system/compute/builtinsomething"));
});
