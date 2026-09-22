//! HISTORY §2.2 / §6.2 — config pattern canonicalization, matching and specificity.
//!
//! Matching itself is the PEER'S, not ours. §6.2 says "Pattern matching uses the core
//! `matches_pattern` algorithm", and `capability::matches_pattern` is `pub` on this
//! peer — so re-transcribing it here would be a second reading of a shared algorithm,
//! the exact class of divergence `gates/chunking-parity` exists to catch for §3.6.
//!
//! **This is the one file where `rust` is the LEAST constrained of the three ports and
//! it is worth saying so, because the usual direction is the opposite.** `python`'s
//! equivalents are leading-underscore and `typescript`'s are behind a `Paths` façade;
//! here `canonicalize` and `matches_pattern` are free functions with `pub` on them.
//! Everything below is what the spec adds ON TOP of core, and nothing below is a
//! reimplementation of anything core owns.

use entity_core_protocol::peer::capability;

/// §2.2 `canonicalize_pattern`. Deliberately different from core §5.4's `canonicalize`,
/// and the spec is explicit about that: "This function is specific to history config
/// pattern evaluation. The core `canonicalize` is unchanged."
///
/// # The leading-`*` form is normalized to `/*/`, and that is a declared deviation
///
/// §2.2's pseudocode passes a leading `*` segment through unchanged, and its pattern
/// table lists a leading-star pattern meaning "that subtree in any peer's namespace".
/// But core §5.4's `canonicalize` REJECTS that spelling —
///
/// ```text
/// if path starts with "*/": return error("ambiguous: use /*/rest for peer
///                                        wildcard patterns")
/// ```
///
/// — and core's `matches_pattern` only recognises a peer wildcard as `/*/rest`. A
/// pattern left as `*/project/*` reaches `matches_pattern`, matches none of the three
/// wildcard forms, and falls through to exact string comparison, where it matches
/// nothing at all. So §2.2's documented behaviour and §2.2's own pseudocode disagree,
/// and the pseudocode is the one that produces silence.
///
/// We implement the TABLE, by rewriting `*/rest` → `/*/rest`, which is the spelling
/// core §5.4 names as correct for exactly this intent. Routed to arch; recorded in
/// `EXTENSION.toml`.
pub fn canonicalize_pattern(pattern: &str, local_peer: &str) -> String {
    if pattern.starts_with('/') {
        return pattern.to_string(); // already absolute
    }
    if pattern == "*" {
        // §2.2's table: "`*` | Match everything". Core §5.4 canonicalizes a bare `*` to
        // `/{local}/*` — local peer, all paths — which is NARROWER than "everything".
        // §6.3's worked example uses `pattern: "*"` for a peer that "wants history for
        // all paths", and on a single-peer composition the two readings name the same
        // set. We take core's, because a pattern is matched by core's matcher and
        // diverging here would mean our `*` and a grant's `*` cover different paths on
        // one peer.
        return format!("/{local_peer}/*");
    }
    if let Some(rest) = pattern.strip_prefix("*/") {
        return format!("/*/{rest}"); // see the doc comment above
    }
    format!("/{local_peer}/{pattern}")
}

/// §6.2's specificity keys, as an ordered tuple.
///
/// v1.7 makes this a MUST and states the reason: "A scalar cannot carry a two-key
/// order, so an implementation that collapses the keys into one number manufactures
/// ties §2.2 does not have and then resolves them by whatever the store happened to
/// yield."
///
/// | Key | Value | Direction |
/// |-----|-------|-----------|
/// | 1 | count of literal (non-`*`) segments | higher wins |
/// | 2 | total segment depth | higher wins |
/// | 3 | lexicographic byte order on the canonical form | **lower** wins |
///
/// Key 3 is what makes the order TOTAL, and §6.2 is explicit that keys 1–2 are not:
/// `a/*/c` and `a/b/*` are each 2 literal segments at depth 3. Without key 3 the winner
/// is enumeration order, which is the defect the MUST exists to prevent.
///
/// **A derived `Ord` would be wrong here**, which is why one is not derived: it would
/// order `canonical` ascending along with the other two, and key 3 inverts. That is the
/// same trap in a different costume from the one §6.2 describes — a total order that is
/// stable and picks the other pattern.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Specificity {
    pub literals: usize,
    pub depth: usize,
    pub canonical: String,
}

pub fn pattern_specificity(canonical_pattern: &str) -> Specificity {
    let segments: Vec<&str> = canonical_pattern
        .strip_prefix('/')
        .unwrap_or(canonical_pattern)
        .split('/')
        .collect();
    Specificity {
        literals: segments.iter().filter(|s| **s != "*").count(),
        depth: segments.len(),
        canonical: canonical_pattern.to_string(),
    }
}

/// Order two specificities. Returns `> 0` when `a` is more specific than `b`.
///
/// Returns an `i32` rather than an `Ordering` on purpose: the three ports are compared
/// name for name by `tools/sdk-parity.py` and behaviour for behaviour by their tests,
/// and a signature that reads the same in all three is worth more here than the
/// idiomatic one. The sign convention is `typescript`'s and `python`'s.
pub fn compare_specificity(a: &Specificity, b: &Specificity) -> i32 {
    if a.literals != b.literals {
        return a.literals as i32 - b.literals as i32;
    }
    if a.depth != b.depth {
        return a.depth as i32 - b.depth as i32;
    }
    // Lexicographic BYTE order. §6.2 requires that "every conformant peer selects the
    // same config", so this must not depend on a collation table.
    match a.canonical.as_bytes().cmp(b.canonical.as_bytes()) {
        std::cmp::Ordering::Equal => 0,
        std::cmp::Ordering::Less => 1, // lower canonical WINS
        std::cmp::Ordering::Greater => -1,
    }
}

/// §6.2 — does this canonicalized pattern cover this canonicalized path?
///
/// Core's, not ours. The argument order is `(path, pattern)` in all three ports even
/// though this peer's own free function takes the same two the same way round: a
/// consumer reading two of our ports must not find the third has swapped them.
pub fn pattern_matches(path: &str, canonical_pattern: &str) -> bool {
    capability::matches_pattern(path, canonical_pattern)
}
