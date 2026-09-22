//! §2.2 canonicalization and §6.2's three-key specificity — including this repo's
//! attempt at the spec's own REQUIRED conformance vector, and the reason the attempt is
//! partial.
//!
//! The same assertions as `../../typescript/extensions/history/test/patterns.test.ts`
//! and `../../python/extensions/history/test/test_patterns.py`, deliberately: this is
//! the one part of HISTORY where all three ports run the SAME algorithm against the
//! SAME peer primitive (`matches_pattern`), so a divergence would be ours alone.

use entity_history::{
    canonicalize_pattern, compare_specificity, pattern_matches, pattern_specificity, Specificity,
};

const PEER: &str = "z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH";
const OTHER: &str = "z6MkfZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ";

fn spec(p: &str) -> Specificity {
    pattern_specificity(&canonicalize_pattern(p, PEER))
}

fn signum(n: i32) -> i32 {
    match n {
        0 => 0,
        n if n > 0 => 1,
        _ => -1,
    }
}

// ── §2.2 canonicalize_pattern ────────────────────────────────────────────────

#[test]
fn an_absolute_pattern_passes_through_unchanged() {
    let p = format!("/{PEER}/project/*");
    assert_eq!(canonicalize_pattern(&p, PEER), p);
}

#[test]
fn a_short_form_pattern_resolves_to_the_local_namespace() {
    assert_eq!(
        canonicalize_pattern("project/*", PEER),
        format!("/{PEER}/project/*")
    );
    assert_eq!(
        canonicalize_pattern("project/readme", PEER),
        format!("/{PEER}/project/readme")
    );
}

/// §2.2's pseudocode returns a leading-star pattern unchanged; §2.2's TABLE says it
/// means "that subtree in any peer's namespace"; core §5.4 rejects the unchanged
/// spelling and names `/*/rest` as the form that carries that meaning. We implement the
/// table. Routed to arch.
#[test]
fn a_leading_star_pattern_becomes_core_5_4s_peer_wildcard_spelling() {
    assert_eq!(canonicalize_pattern("*/project/*", PEER), "/*/project/*");
}

/// The half that makes the deviation worth making. **Under §2.2's literal pseudocode
/// this assertion fails**, because the un-normalized `*/project/*` matches none of core
/// `matches_pattern`'s three wildcard forms, falls through to an exact string compare,
/// and matches nothing at all — silently, with the config well-formed and stored.
#[test]
fn the_normalized_peer_wildcard_actually_matches_another_peers_path() {
    let canonical = canonicalize_pattern("*/project/*", PEER);
    assert!(pattern_matches(
        &format!("/{OTHER}/project/readme"),
        &canonical
    ));
    assert!(!pattern_matches(
        &format!("/{OTHER}/other/readme"),
        &canonical
    ));

    // And the control: the spelling §2.2's pseudocode would have produced matches
    // NOTHING. Without this arm the test above passes for any implementation that
    // happens to be permissive, and the deviation would be untested rather than proven.
    assert!(!pattern_matches(
        &format!("/{OTHER}/project/readme"),
        "*/project/*"
    ));
}

/// §6.3's own worked example — `pattern: "*"` for a peer that "wants history for all
/// paths" — and the exact path shape the oracle writes to.
#[test]
fn a_bare_star_covers_the_local_namespace_which_is_what_the_oracle_exercises() {
    let canonical = canonicalize_pattern("*", PEER);
    assert_eq!(canonical, format!("/{PEER}/*"));
    assert!(pattern_matches(
        &format!("/{PEER}/system/validate/history-ext/test-record"),
        &canonical
    ));
}

// ── §6.2 specificity ─────────────────────────────────────────────────────────

#[test]
fn key_1_more_literal_segments_wins() {
    let exact = spec("a/b/c/d"); // /{PEER}/a/b/c/d : 5 literal, depth 5
    let wild = spec("*/a/b/c/*"); // /*/a/b/c/*      : 3 literal, depth 5
    assert_eq!(exact.literals, 5);
    assert_eq!(wild.literals, 3);
    assert!(compare_specificity(&exact, &wild) > 0);
}

/// §6.2 says so directly: "§2.2's peer-ID rule needs no separate key — an explicit peer
/// segment is literal and a `*` peer segment is not, so key 1 already ranks it."
#[test]
fn an_explicit_peer_beats_a_wildcard_peer_without_a_rule_of_its_own() {
    let explicit = spec("project/*"); // /{PEER}/project/* : 2 literal, depth 3
    let wildcard = spec("*/project/*"); // /*/project/*     : 1 literal, depth 3
    assert_eq!(explicit.depth, wildcard.depth);
    assert!(compare_specificity(&explicit, &wildcard) > 0);
}

#[test]
fn key_2_at_equal_literals_greater_depth_wins() {
    let deep = Specificity {
        literals: 2,
        depth: 5,
        canonical: "x".into(),
    };
    let shallow = Specificity {
        literals: 2,
        depth: 4,
        canonical: "x".into(),
    };
    assert!(compare_specificity(&deep, &shallow) > 0);
}

/// §6.2's own example of a key-1/key-2 tie: "`a/*/c` and `a/b/*` are each 2 literal
/// segments at depth 3". Without key 3 the winner is whatever the store listed first.
#[test]
fn key_3_the_order_is_total_and_lower_bytes_win() {
    let a = pattern_specificity("/p/a/*/c");
    let b = pattern_specificity("/p/a/b/*");
    assert_eq!(a.literals, b.literals);
    assert_eq!(a.depth, b.depth);
    let forward = compare_specificity(&a, &b);
    assert_ne!(forward, 0, "keys 1-2 tie, so key 3 must break it");
    assert_eq!(signum(forward), -signum(compare_specificity(&b, &a)));
    // '*' (0x2A) < 'b' (0x62), and the LOWER canonical wins. Getting this inversion
    // backwards still produces a total order and still passes any test that only checks
    // determinism — it just picks the other pattern.
    assert!(forward > 0);
}

/// `HIST-CONFIG-SPECIFICITY-1` — §6.2 marks this REQUIRED. **This is as close as the
/// vector can be constructed, and the gap is a spec finding rather than a shortcut.**
///
/// §6.2's worked pair is `a/b/c/d` (4 literal, depth 4) against `a/*/c/*/e` (3 literal,
/// depth 5), and it asks for a path BOTH MATCH. Under core §5.4 there is no such path:
/// its grammar has exactly three wildcard forms — bare `*`, leading `/*/rest`, and
/// trailing `pattern/*` — and a mid-path `*` segment is not one of them, so `a/*/c/*/e`
/// falls through to an exact compare and matches only that literal string.
///
/// And the tie the MUST defends against cannot occur under that grammar either. With
/// `scalar = 2*literals + wildcards = literals + depth`, the three constructible shapes
/// give exact = 2D (even), peer-literal trailing = 2D-1 (odd), peer-wildcard trailing =
/// 2D-2 (even). A tie with different literal counts needs `D2 = D1 + 1`, and a
/// trailing-`/*` pattern one segment deeper than an exact pattern cannot match that
/// exact pattern's path.
///
/// **So the scalar and the tuple can never disagree on a pair core §5.4 can express.**
/// The v1.7 MUST is right in principle and its worked example is unreachable in
/// practice. Implemented anyway — free, and correct the day the grammar gains mid-path
/// wildcards. Routed as `ROUTING-2026-09-06-c-arch-*` A-2.
///
/// What IS asserted is the half the vector can still buy: **selection does not depend on
/// enumeration order.** §6.2 asks for both orders explicitly, "since a peer that ties
/// resolves by enumeration and will pass one order by luck".
#[test]
fn hist_config_specificity_1_partial_selection_is_insertion_order_independent() {
    let path = format!("/{PEER}/a/b/c/d");
    let specific = spec("a/b/c/d");
    let general = spec("*/a/b/c/*");

    assert!(
        pattern_matches(&path, &specific.canonical),
        "both must match"
    );
    assert!(
        pattern_matches(&path, &general.canonical),
        "both must match"
    );

    let pick = |candidates: Vec<&Specificity>| -> String {
        let mut best = candidates[0];
        for c in &candidates[1..] {
            if compare_specificity(c, best) > 0 {
                best = c;
            }
        }
        best.canonical.clone()
    };
    assert_eq!(pick(vec![&specific, &general]), specific.canonical);
    assert_eq!(pick(vec![&general, &specific]), specific.canonical);
}

/// The property key 3 exists to provide, asserted over a SET rather than a pair —
/// because a comparator can be antisymmetric on every pair and still be non-transitive,
/// and it is transitivity that makes "every conformant peer selects the same config"
/// true.
#[test]
fn the_comparator_is_a_strict_total_order_over_the_constructible_shapes() {
    let patterns: Vec<Specificity> = ["a/b/c/d", "a/b/*", "*/a/b/c/*", "*/a/b/*", "*", "a/b/c/e"]
        .iter()
        .map(|p| spec(p))
        .collect();

    for x in &patterns {
        for y in &patterns {
            let c = compare_specificity(x, y);
            if x.canonical == y.canonical {
                assert_eq!(c, 0);
            } else {
                assert_ne!(c, 0, "{} vs {} must not tie", x.canonical, y.canonical);
                assert_eq!(signum(c), -signum(compare_specificity(y, x)));
            }
        }
    }

    let mut sorted = patterns.clone();
    // Descending by specificity: `x` sorts before `y` when `x` is the more specific,
    // which is `compare_specificity(y, x)` being negative.
    sorted.sort_by(|x, y| compare_specificity(y, x).cmp(&0));
    for w in sorted.windows(2) {
        assert!(
            compare_specificity(&w[0], &w[1]) > 0,
            "sorting by the comparator must produce a strictly descending chain: {} then {}",
            w[0].canonical,
            w[1].canonical
        );
    }
}

// ── v1.8's REQUIRED vectors, as the spec now writes them ────────────────────────
//
// v1.8 REWROTE `HIST-CONFIG-SPECIFICITY-1` and ADDED `-2`. The test above implements
// v1.7's version, and its doc comment derives — two days before the spec did — exactly
// why v1.7's worked pair could not be built and why a scalar and the tuple cannot
// disagree. **v1.8 says both in its own words** and retracts the pair: "v1.7's worked
// pair ... used `a/*/c/*/e`, which is not a pattern, so no path distinguishes the
// readings," and "under §5.4's grammar a scalar and the tuple agree on every pair a peer
// can construct." The old test is kept: it asserts real behaviour and it is the record.
//
// Kept assertion-for-assertion in step with the `python` and `typescript` cells.

/// §6.2 `find_history_config`'s selection, over an explicit candidate ORDER.
///
/// A slice rather than a set because insertion order is the whole point of both vectors:
/// "an implementation that returns the first match rather than the most specific one
/// passes exactly one order, by luck."
fn select(candidates: &[&Specificity]) -> String {
    let mut best = candidates[0];
    for c in &candidates[1..] {
        if compare_specificity(c, best) > 0 {
            best = c;
        }
    }
    best.canonical.clone()
}

/// `HIST-CONFIG-SPECIFICITY-1` (REQUIRED, v1.8). Configure `a/b/*` and `a/*`, write at
/// `a/b/c`. Both match; key 1 is 3 against 2, so `a/b/*` MUST be selected. Both orders.
#[test]
fn hist_config_specificity_1_v1_8_key_1_separates() {
    let path = format!("/{PEER}/a/b/c");
    let specific = spec("a/b/*"); // /{PEER}/a/b/* : literals PEER,a,b = 3, depth 4
    let general = spec("a/*"); //    /{PEER}/a/*   : literals PEER,a   = 2, depth 3

    assert!(
        pattern_matches(&path, &specific.canonical),
        "both must match"
    );
    assert!(
        pattern_matches(&path, &general.canonical),
        "both must match"
    );
    assert_eq!(specific.literals, 3);
    assert_eq!(general.literals, 2);

    assert_eq!(select(&[&specific, &general]), specific.canonical);
    assert_eq!(select(&[&general, &specific]), specific.canonical);
}

/// `HIST-CONFIG-SPECIFICITY-2` (REQUIRED, new in v1.8). Configure `*` (canonicalizes to
/// `/{local}/*` — 1 literal, depth 2) and `/*/a/*` (1 literal, depth 3) and write at
/// `a/b`. **Key 1 TIES at 1 and only key 2 separates them.**
///
/// This is the pair that fails an implementation comparing literal counts alone and never
/// consulting depth — the case v1.7's text had no equivalent of.
#[test]
fn hist_config_specificity_2_v1_8_key_2_is_load_bearing() {
    let path = format!("/{PEER}/a/b");
    let everything = spec("*"); //   /{PEER}/* : literals PEER = 1, depth 2
    let peer_wild = spec("*/a/*"); // /*/a/*   : literals a    = 1, depth 3

    assert_eq!(everything.canonical, format!("/{PEER}/*"));
    assert_eq!(peer_wild.canonical, "/*/a/*");
    assert!(
        pattern_matches(&path, &everything.canonical),
        "both must match"
    );
    assert!(
        pattern_matches(&path, &peer_wild.canonical),
        "both must match"
    );

    // The tie is the point: assert it exists before asserting what breaks it.
    assert_eq!(everything.literals, peer_wild.literals);
    assert_eq!(everything.literals, 1);
    assert_eq!(everything.depth, 2);
    assert_eq!(peer_wild.depth, 3);

    assert_eq!(select(&[&everything, &peer_wild]), peer_wild.canonical);
    assert_eq!(select(&[&peer_wild, &everything]), peer_wild.canonical);
}
