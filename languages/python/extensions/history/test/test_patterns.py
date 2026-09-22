"""§2.2 canonicalization and §6.2's three-key specificity.

Including this repo's attempt at the spec's own REQUIRED vector, and why it is partial.
Kept assertion-for-assertion in step with
``../../../typescript/extensions/history/test/patterns.test.ts``.
"""

from __future__ import annotations

from entity_history import (
    canonicalize_pattern,
    compare_specificity,
    pattern_matches,
    pattern_specificity,
)

PEER = "z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH"
OTHER = "z6MkfZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"


def spec(p: str):
    return pattern_specificity(canonicalize_pattern(p, PEER))


# ── §2.2 canonicalize_pattern ───────────────────────────────────────────────────


def test_an_absolute_pattern_passes_through():
    assert canonicalize_pattern("/" + PEER + "/project/*", PEER) == "/" + PEER + "/project/*"


def test_a_short_form_pattern_resolves_to_the_local_namespace():
    assert canonicalize_pattern("project/*", PEER) == "/" + PEER + "/project/*"
    assert canonicalize_pattern("project/readme", PEER) == "/" + PEER + "/project/readme"


def test_a_leading_star_pattern_becomes_cores_peer_wildcard_spelling():
    """§2.2's pseudocode returns it unchanged; §2.2's TABLE says it means "any peer's
    namespace"; core §5.4 rejects the unchanged spelling. We implement the table."""
    assert canonicalize_pattern("*/project/*", PEER) == "/*/project/*"


def test_the_normalized_peer_wildcard_actually_matches_another_peers_path():
    """The half that makes the deviation worth making: under §2.2's literal pseudocode
    this fails, because the un-normalized pattern falls through to an exact string
    compare and matches nothing at all."""
    canonical = canonicalize_pattern("*/project/*", PEER)
    assert pattern_matches("/" + OTHER + "/project/readme", canonical) is True
    assert pattern_matches("/" + OTHER + "/other/readme", canonical) is False


def test_a_bare_star_covers_the_local_namespace_which_is_what_the_oracle_exercises():
    canonical = canonicalize_pattern("*", PEER)
    assert canonical == "/" + PEER + "/*"
    assert pattern_matches("/" + PEER + "/system/validate/history-ext/test-record", canonical)


# ── §6.2 specificity ────────────────────────────────────────────────────────────


def test_key_1_more_literal_segments_wins():
    exact = spec("a/b/c/d")       # 5 literal (peer + 4), depth 5
    wild = spec("*/a/b/c/*")      # 3 literal, depth 5
    assert exact.literals == 5
    assert wild.literals == 3
    assert compare_specificity(exact, wild) > 0


def test_an_explicit_peer_beats_a_wildcard_peer_without_a_rule_of_its_own():
    """§6.2 says so directly: an explicit peer segment is literal and a `*` peer segment
    is not, so key 1 already ranks it."""
    explicit = spec("project/*")      # /{PEER}/project/*  : 2 literal, depth 3
    wildcard = spec("*/project/*")    # /*/project/*       : 1 literal, depth 3
    assert explicit.depth == wildcard.depth
    assert compare_specificity(explicit, wildcard) > 0


def test_key_2_at_equal_literals_greater_depth_wins():
    from entity_history import Specificity

    assert compare_specificity(Specificity(2, 5, "x"), Specificity(2, 4, "x")) > 0


def test_key_3_the_order_is_total_and_lower_bytes_win():
    """§6.2's own tie example: `a/*/c` and `a/b/*` are each 2 literal segments at depth 3.
    Without key 3 the winner is whatever the store listed first."""
    a = pattern_specificity("/p/a/*/c")
    b = pattern_specificity("/p/a/b/*")
    assert a.literals == b.literals
    assert a.depth == b.depth
    forward = compare_specificity(a, b)
    assert forward != 0
    assert (forward > 0) != (compare_specificity(b, a) > 0)
    # '*' (0x2A) < 'b' (0x62), and LOWER wins.
    assert compare_specificity(a, b) > 0


def test_hist_config_specificity_1_partial_insertion_order_independence():
    """``HIST-CONFIG-SPECIFICITY-1`` — §6.2 marks this REQUIRED. **This is as close as it
    can be constructed, and the gap is a spec finding rather than a shortcut.**

    §6.2's worked pair is ``a/b/c/d`` against ``a/*/c/*/e`` and asks for a path BOTH
    MATCH. Under core §5.4 there is none: the grammar has exactly three wildcard forms —
    bare ``*``, leading ``/*/rest``, trailing ``pattern/*`` — and a mid-path ``*`` segment
    is not one of them, so ``a/*/c/*/e`` falls through to EXACT MATCH. One pattern is
    exact at depth 4, the other exact at depth 5; no path is both.

    Nor can the tie the MUST defends against occur. With ``scalar = literals + depth``:
    exact = 2D (even), peer-literal trailing = 2D-1 (odd), peer-wildcard trailing = 2D-2
    (even). A tie with different literal counts needs D2 = D1+1, and a trailing-``/*``
    pattern one segment deeper than an exact pattern cannot match that exact pattern's
    path. **So scalar and tuple can never disagree on a pair core §5.4 can express.**

    Implemented the tuple anyway — free, and correct the day the grammar gains mid-path
    wildcards. Asserted here is the half that survives: §6.2 asks for both insertion
    orders explicitly, "since a peer that ties resolves by enumeration and will pass one
    order by luck".
    """
    path = "/" + PEER + "/a/b/c/d"
    specific = spec("a/b/c/d")
    general = spec("*/a/b/c/*")

    assert pattern_matches(path, specific.canonical)
    assert pattern_matches(path, general.canonical)

    def best(cands):
        out = cands[0]
        for c in cands[1:]:
            if compare_specificity(c, out) > 0:
                out = c
        return out

    assert best([specific, general]).canonical == specific.canonical
    assert best([general, specific]).canonical == specific.canonical


def test_the_comparator_is_a_strict_total_order():
    """Key 3's whole purpose. Over a SET rather than a pair, because a comparator can be
    antisymmetric on every pair and still be non-transitive."""
    import functools

    patterns = [spec(p) for p in ("a/b/c/d", "a/b/*", "*/a/b/c/*", "*/a/b/*", "*", "a/b/c/e")]
    for x in patterns:
        for y in patterns:
            c = compare_specificity(x, y)
            if x.canonical == y.canonical:
                assert c == 0
            else:
                assert c != 0, f"{x.canonical} vs {y.canonical} must not tie"
                assert (c > 0) != (compare_specificity(y, x) > 0)

    ordered = sorted(patterns, key=functools.cmp_to_key(compare_specificity), reverse=True)
    for i in range(1, len(ordered)):
        assert compare_specificity(ordered[i - 1], ordered[i]) > 0
