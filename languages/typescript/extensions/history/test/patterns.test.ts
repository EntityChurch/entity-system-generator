/**
 * §2.2 canonicalization and §6.2's three-key specificity — including this repo's attempt
 * at the spec's own REQUIRED conformance vector, and the reason the attempt is partial.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  canonicalizePattern,
  compareSpecificity,
  patternMatches,
  patternSpecificity,
} from "@entity-core/extension-history";

const PEER = "z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH";

// ── §2.2 canonicalize_pattern ───────────────────────────────────────────────────

test("§2.2: an absolute pattern passes through unchanged", () => {
  assert.equal(canonicalizePattern("/" + PEER + "/project/*", PEER), "/" + PEER + "/project/*");
});

test("§2.2: a short-form pattern resolves to the local namespace", () => {
  assert.equal(canonicalizePattern("project/*", PEER), "/" + PEER + "/project/*");
  assert.equal(canonicalizePattern("project/readme", PEER), "/" + PEER + "/project/readme");
});

test("§2.2: a leading-star pattern becomes core §5.4's peer-wildcard spelling", () => {
  // §2.2's pseudocode returns it unchanged; §2.2's TABLE says it means "any peer's
  // namespace"; core §5.4 rejects the unchanged spelling and names `/*/rest` as the form
  // that carries that meaning. We implement the table. See patterns.ts.
  assert.equal(canonicalizePattern("*/project/*", PEER), "/*/project/*");
});

test("the normalized peer-wildcard actually matches another peer's path", () => {
  // The half that makes the deviation worth making: under §2.2's literal pseudocode this
  // assertion fails, because the un-normalized pattern falls through core's matcher to an
  // exact string compare and matches nothing at all.
  const other = "z6MkfZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ";
  const canonical = canonicalizePattern("*/project/*", PEER);
  assert.equal(patternMatches("/" + other + "/project/readme", canonical), true);
  assert.equal(patternMatches("/" + other + "/other/readme", canonical), false);
});

test("§6.3: a bare `*` covers the local namespace, which is what the oracle exercises", () => {
  const canonical = canonicalizePattern("*", PEER);
  assert.equal(canonical, "/" + PEER + "/*");
  assert.equal(patternMatches("/" + PEER + "/system/validate/history-ext/test-record", canonical), true);
});

// ── §6.2 specificity ────────────────────────────────────────────────────────────

const spec = (p: string) => patternSpecificity(canonicalizePattern(p, PEER));

test("§6.2 key 1: more literal segments wins, regardless of depth", () => {
  const exact = spec("a/b/c/d"); // 5 literal (peer + 4), depth 5
  const wild = spec("*/a/b/c/*"); // 3 literal, depth 5
  assert.equal(exact.literals, 5);
  assert.equal(wild.literals, 3);
  assert.ok(compareSpecificity(exact, wild) > 0, "the exact pattern is more specific");
});

test("§6.2: an explicit peer beats a wildcard peer WITHOUT a rule of its own", () => {
  // §6.2 says so directly: "§2.2's peer-ID rule needs no separate key — an explicit peer
  // segment is literal and a `*` peer segment is not, so key 1 already ranks it."
  const explicitPeer = spec("project/*"); // -> /{PEER}/project/*  : 2 literal, depth 3
  const wildcardPeer = spec("*/project/*"); // -> /*/project/*      : 1 literal, depth 3
  assert.equal(explicitPeer.depth, wildcardPeer.depth);
  assert.ok(compareSpecificity(explicitPeer, wildcardPeer) > 0);
});

test("§6.2 key 2: at equal literals, greater depth wins", () => {
  const deep = patternSpecificity("/*/a/b/c/*"); // 3 literal, depth 5
  const shallow = patternSpecificity("/*/a/b/*"); // 2 literal, depth 4
  // (different literals here, so construct the equal-literal case directly)
  const eqDeep = { literals: 2, depth: 5, canonical: "x" };
  const eqShallow = { literals: 2, depth: 4, canonical: "x" };
  assert.ok(compareSpecificity(eqDeep, eqShallow) > 0);
  assert.ok(deep.literals > shallow.literals);
});

test("§6.2 key 3: the order is TOTAL, and lower bytes win", () => {
  // §6.2's own example of a key-1/key-2 tie: "`a/*/c` and `a/b/*` are each 2 literal
  // segments at depth 3". Without key 3 the winner is whatever the store listed first.
  const a = patternSpecificity("/p/a/*/c");
  const b = patternSpecificity("/p/a/b/*");
  assert.equal(a.literals, b.literals);
  assert.equal(a.depth, b.depth);
  const forward = compareSpecificity(a, b);
  const reverse = compareSpecificity(b, a);
  assert.notEqual(forward, 0, "keys 1-2 tie, so key 3 must break it");
  assert.equal(Math.sign(forward), -Math.sign(reverse), "the order is antisymmetric");
  // Lower bytes win: "/p/a/*/c" < "/p/a/b/*" because '*' (0x2A) < 'b' (0x62).
  assert.ok(compareSpecificity(a, b) > 0, "the lexicographically LOWER pattern wins");
});

/**
 * `HIST-CONFIG-SPECIFICITY-1` — §6.2 marks this REQUIRED. **This is as close as the
 * vector can be constructed, and the gap is a spec finding rather than a shortcut.**
 *
 * §6.2's worked pair is `a/b/c/d` (4 literal, depth 4) against `a/*\/c/*\/e` (3 literal,
 * depth 5), and it asks for a path BOTH MATCH. Under core §5.4 there is no such path:
 *
 *   - §5.4's grammar has exactly three wildcard forms — bare `*`, leading `/*\/rest`, and
 *     trailing `pattern/*`. A mid-path `*` segment is not one of them; the enumerated
 *     "Pattern types in entity data" list is `*`, `pattern/*`, `pattern`, `/*\/*`,
 *     `/*\/pattern/*`, `/{P}/pattern/*`, and nothing else.
 *   - So `a/*\/c/*\/e` falls through to EXACT MATCH and matches only that literal string.
 *   - `a/b/c/d` is exact at depth 4; the other is exact at depth 5. No path is both.
 *
 * And the tie the MUST defends against cannot occur under that grammar either. With
 * `scalar = 2*literals + 1*wildcards = literals + depth`, the three constructible shapes
 * give exact = 2D (even), peer-literal trailing = 2D-1 (odd), peer-wildcard trailing =
 * 2D-2 (even). A tie with DIFFERENT literal counts needs 2D1 = 2D2-2, i.e. D2 = D1+1 —
 * and a trailing-`/*` pattern one segment deeper than an exact pattern cannot match that
 * exact pattern's path, because the prefix comparison requires a strictly deeper path.
 *
 * **So the scalar and the tuple can never disagree on a pair core §5.4 can express.** The
 * v1.7 MUST is right in principle and its worked example is unreachable in practice.
 * Implemented anyway — it is free, and it is correct the day the grammar gains mid-path
 * wildcards. Routed as `ROUTING-2026-09-06-c-arch-*` A-2.
 *
 * What IS asserted here is the half the vector can still buy: **selection does not depend
 * on enumeration order.** §6.2 asks for both insertion orders explicitly, "since a peer
 * that ties resolves by enumeration and will pass one order by luck".
 */
test("HIST-CONFIG-SPECIFICITY-1 (partial): selection is insertion-order independent", () => {
  const path = "/" + PEER + "/a/b/c/d";
  const specific = spec("a/b/c/d");
  const general = spec("*/a/b/c/*");

  assert.equal(patternMatches(path, specific.canonical), true, "both must match the path");
  assert.equal(patternMatches(path, general.canonical), true, "both must match the path");

  // Both insertion orders, and the winner must be the same one.
  const forward = [specific, general].reduce((best, c) =>
    compareSpecificity(c, best) > 0 ? c : best,
  );
  const backward = [general, specific].reduce((best, c) =>
    compareSpecificity(c, best) > 0 ? c : best,
  );
  assert.equal(forward.canonical, specific.canonical);
  assert.equal(backward.canonical, specific.canonical);
});

test("the specificity comparator is a strict total order over the constructible shapes", () => {
  // The property key 3 exists to provide. Asserted over a set rather than a pair, because
  // a comparator can be antisymmetric on every pair and still be non-transitive.
  const patterns = ["a/b/c/d", "a/b/*", "*/a/b/c/*", "*/a/b/*", "*", "a/b/c/e"].map(spec);
  for (const x of patterns) {
    for (const y of patterns) {
      const c = compareSpecificity(x, y);
      if (x.canonical === y.canonical) {
        assert.equal(c, 0);
      } else {
        assert.notEqual(c, 0, `${x.canonical} vs ${y.canonical} must not tie`);
        assert.equal(Math.sign(c), -Math.sign(compareSpecificity(y, x)));
      }
    }
  }
  const sorted = [...patterns].sort((x, y) => compareSpecificity(y, x));
  for (let i = 1; i < sorted.length; i += 1) {
    assert.ok(
      compareSpecificity(sorted[i - 1]!, sorted[i]!) > 0,
      "sorting by the comparator must produce a strictly descending chain",
    );
  }
});

// ── v1.8's REQUIRED vectors, as the spec now writes them ────────────────────────
//
// v1.8 REWROTE `HIST-CONFIG-SPECIFICITY-1` and ADDED `-2`. The test above implements
// v1.7's version and its comment explains why v1.7's worked pair could not be built —
// `a/*/c/*/e` is a mid-path spelling that is not a pattern, so no path matches both.
// **v1.8 retracts that pair for exactly that reason.** The old test is kept: it asserts
// real behaviour and it is the record of what we found.
//
// Kept assertion-for-assertion in step with
// `../../../../python/extensions/history/test/test_patterns.py`.

/** §6.2 `find_history_config`'s selection, over an explicit candidate ORDER. */
function select(candidates: ReturnType<typeof spec>[]) {
  return candidates.reduce((best, c) => (compareSpecificity(c, best) > 0 ? c : best));
}

test("HIST-CONFIG-SPECIFICITY-1 (REQUIRED, v1.8): key 1 separates, both insertion orders", () => {
  // Configure `a/b/*` and `a/*`, write at `a/b/c`. Both match; key 1 is 3 against 2.
  const path = "/" + PEER + "/a/b/c";
  const specific = spec("a/b/*"); // /{PEER}/a/b/* : literals PEER,a,b = 3, depth 4
  const general = spec("a/*"); //    /{PEER}/a/*   : literals PEER,a   = 2, depth 3

  assert.ok(patternMatches(path, specific.canonical));
  assert.ok(patternMatches(path, general.canonical));
  assert.equal(specific.literals, 3);
  assert.equal(general.literals, 2);

  assert.equal(select([specific, general]).canonical, specific.canonical);
  assert.equal(select([general, specific]).canonical, specific.canonical);
});

test("HIST-CONFIG-SPECIFICITY-2 (REQUIRED, new in v1.8): key 1 ties and only key 2 separates", () => {
  // Configure `*` (-> `/{local}/*`, 1 literal, depth 2) and `/*/a/*` (1 literal, depth 3)
  // and write at `a/b`. This is the pair that fails an implementation comparing literal
  // counts alone and never consulting depth — the case v1.7's text had no equivalent of.
  const path = "/" + PEER + "/a/b";
  const everything = spec("*"); //   /{PEER}/* : literals PEER = 1, depth 2
  const peerWild = spec("*/a/*"); // /*/a/*    : literals a    = 1, depth 3

  assert.equal(everything.canonical, "/" + PEER + "/*");
  assert.equal(peerWild.canonical, "/*/a/*");
  assert.ok(patternMatches(path, everything.canonical));
  assert.ok(patternMatches(path, peerWild.canonical));

  // The tie is the point: assert it exists before asserting what breaks it.
  assert.equal(everything.literals, peerWild.literals);
  assert.equal(everything.literals, 1);
  assert.equal(everything.depth, 2);
  assert.equal(peerWild.depth, 3);

  assert.equal(select([everything, peerWild]).canonical, peerWild.canonical);
  assert.equal(select([peerWild, everything]).canonical, peerWild.canonical);
});
