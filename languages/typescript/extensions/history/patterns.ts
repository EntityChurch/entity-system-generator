/**
 * HISTORY §2.2 / §6.2 — config pattern canonicalization, matching and specificity.
 *
 * Matching itself is the PEER'S, not ours: `Paths.matchesPattern` is core §5.4 and is
 * public. §6.2 says "Pattern matching uses the core `matches_pattern` algorithm", so
 * re-transcribing it here would be a second reading of a shared algorithm — the exact
 * class of divergence `gates/chunking-parity` exists to catch for §3.6. We reuse.
 *
 * What IS ours: §2.2's `canonicalize_pattern` (which is explicitly NOT core's
 * `canonicalize` — the spec says so), and §6.2's three-key specificity ordering.
 */

import { Paths } from "entity-core-protocol-typescript";

/**
 * §2.2 `canonicalize_pattern`. Deliberately different from core §5.4's `canonicalize`,
 * and the spec is explicit about that: "This function is specific to history config
 * pattern evaluation. The core `canonicalize` is unchanged."
 *
 * THE LEADING `*` + `/` FORM IS NORMALIZED TO `/*\/`, AND THAT IS A DECLARED DEVIATION.
 *
 * §2.2's pseudocode passes a leading `*` segment through unchanged, and its pattern
 * table lists a leading-star pattern with the meaning "Peer wildcard — that subtree in any
 * peer's namespace". But core §5.4's `canonicalize` REJECTS that spelling outright —
 *
 *     if path starts with "*\/": return error("ambiguous: use /*\/rest for peer
 *                                             wildcard patterns")
 *
 * — and core's `matches_pattern` only recognises a peer wildcard as `/*\/rest`. A pattern
 * left as `*\/project/*` reaches `matches_pattern`, matches none of the three wildcard
 * forms, and falls through to exact string comparison, where it matches nothing at all.
 * So §2.2's documented behaviour and §2.2's pseudocode disagree, and the pseudocode is
 * the one that produces silence.
 *
 * We implement the TABLE (the stated meaning), by rewriting `*\/rest` → `/*\/rest`, which
 * is the spelling core §5.4 names as correct for exactly this intent. Recorded in
 * `EXTENSION.toml` (`[conformance]` H-R15) and routed to arch.
 *
 * CLOSED AT THE v1.8 RE-PIN (2026-09-08). v1.8's pseudocode emits `"/*\/" + rest`,
 * corrects the table's example from `*\/project/*` to `/*\/project/*`, and adds a §9.1
 * MUST for it (H-R15). The bare-`*` case is now tested FIRST in the spec's own pseudocode
 * for our reason — the first-segment check "would otherwise read it as a peer wildcard and
 * emit the degenerate `/*\/`". The code below is unchanged; only this comment is.
 */
export function canonicalizePattern(pattern: string, localPeerId: string): string {
  if (pattern.startsWith("/")) {
    return pattern; // already absolute
  }
  if (pattern === "*") {
    // §2.2's table: "`*` | Match everything". Core §5.4 canonicalizes a bare `*` to
    // `/{local}/*` — local peer, all paths — which is NARROWER than "everything".
    // §6.3's worked example uses `pattern: "*"` for a peer that "wants history for all
    // paths", and on a single-peer composition the two readings are the same set. We
    // take core's, because a pattern is matched by core's matcher and diverging here
    // would mean our `*` and a grant's `*` cover different paths on the same peer.
    return "/" + localPeerId + "/*";
  }
  if (pattern.startsWith("*/")) {
    return "/*/" + pattern.slice(2); // see the block comment above
  }
  return "/" + localPeerId + "/" + pattern;
}

/**
 * §6.2's specificity keys, as an ordered tuple. v1.7 makes this a MUST and the reason is
 * stated there: "A scalar cannot carry a two-key order, so an implementation that
 * collapses the keys into one number manufactures ties §2.2 does not have and then
 * resolves them by whatever the store happened to yield."
 *
 * | Key | Value                                        | Direction |
 * |-----|----------------------------------------------|-----------|
 * | 1   | count of literal (non-`*`) segments          | higher wins |
 * | 2   | total segment depth                          | higher wins |
 * | 3   | lexicographic byte order on the canonical form | LOWER wins |
 *
 * Key 3 is what makes the order TOTAL, and §6.2 is explicit that keys 1–2 are not:
 * `a/*\/c` and `a/b/*` are each 2 literal segments at depth 3. Without key 3 the winner
 * is enumeration order, which is the defect the MUST exists to prevent.
 *
 * §2.2's peer-ID rule needs no key of its own — §6.2 says so, and it is right: an
 * explicit peer segment is literal and a `*` peer segment is not, so key 1 already ranks
 * `/{peerA}/project/*` above `/*\/project/*`.
 */
export interface Specificity {
  readonly literals: number;
  readonly depth: number;
  readonly canonical: string;
}

export function patternSpecificity(canonicalPattern: string): Specificity {
  const segments = canonicalPattern.replace(/^\//, "").split("/");
  let literals = 0;
  for (const s of segments) {
    if (s !== "*") {
      literals += 1;
    }
  }
  return { literals, depth: segments.length, canonical: canonicalPattern };
}

/**
 * Order two specificities. Returns > 0 when `a` is more specific than `b`.
 *
 * Note the inversion on key 3: keys 1 and 2 are "higher wins", key 3 is "lower wins".
 * Getting that backwards still produces a total order and still passes any test that
 * only checks determinism — it just picks the other pattern. The unit test asserts the
 * WINNER, not merely that the winner is stable.
 */
export function compareSpecificity(a: Specificity, b: Specificity): number {
  if (a.literals !== b.literals) {
    return a.literals - b.literals;
  }
  if (a.depth !== b.depth) {
    return a.depth - b.depth;
  }
  // Lexicographic BYTE order, not locale collation — `localeCompare` would make the
  // selection depend on the host's ICU data, and §6.2 requires that "every conformant
  // peer selects the same config".
  if (a.canonical === b.canonical) {
    return 0;
  }
  return a.canonical < b.canonical ? 1 : -1;
}

/** §6.2 — does this canonicalized pattern cover this canonicalized path? */
export function patternMatches(path: string, canonicalPattern: string): boolean {
  return Paths.matchesPattern(path, canonicalPattern);
}
