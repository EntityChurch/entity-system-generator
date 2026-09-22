"""HISTORY §2.2 / §6.2 — config pattern canonicalization, matching and specificity.

Matching itself is the PEER'S: ``entity_core.peer.capability.matches_pattern`` is core
§5.4 and is public (no underscore). §6.2 says "Pattern matching uses the core
``matches_pattern`` algorithm", so re-transcribing it would be a second reading of a
shared algorithm.

**The argument order differs from the `typescript` peer's and that is a per-substrate
fact, not a bug**: here it is ``canonicalize(local_peer, path)``, there it is
``Paths.canonicalize(path, localPeerId)``. Recorded because a port written by translating
the other one would silently swap them, and both arguments are strings.
"""

from __future__ import annotations

from dataclasses import dataclass

from entity_core.peer.capability import matches_pattern


def canonicalize_pattern(pattern: str, local_peer: str) -> str:
    """§2.2 ``canonicalize_pattern`` — explicitly NOT core's ``canonicalize``.

    The leading-star form is normalized to core §5.4's ``/*/rest`` spelling. §2.2's
    pseudocode passes it through unchanged; §2.2's TABLE says it means "any peer's
    namespace"; core §5.4 rejects the unchanged spelling outright and names ``/*/rest``
    as the form carrying that meaning. Left as written, the pattern reaches
    ``matches_pattern``, matches none of the three wildcard forms, and falls through to
    exact string comparison — where it matches nothing at all.

    We implement the table. Declared in ``EXTENSION.toml`` and routed to arch.
    """
    if pattern.startswith("/"):
        return pattern
    if pattern == "*":
        # §2.2's table reads "match everything"; core §5.4 canonicalizes a bare `*` to
        # `/{local}/*`, which is the LOCAL peer's paths only. We take core's, so that our
        # `*` and a grant's `*` cover the same set on the same peer.
        return "/" + local_peer + "/*"
    if pattern.startswith("*/"):
        return "/*/" + pattern[2:]
    return "/" + local_peer + "/" + pattern


@dataclass(frozen=True, slots=True)
class Specificity:
    """§6.2's three ordered keys."""

    literals: int
    depth: int
    canonical: str


def pattern_specificity(canonical_pattern: str) -> Specificity:
    segments = canonical_pattern.lstrip("/").split("/")
    literals = sum(1 for s in segments if s != "*")
    return Specificity(literals=literals, depth=len(segments), canonical=canonical_pattern)


def compare_specificity(a: Specificity, b: Specificity) -> int:
    """> 0 when ``a`` is more specific.

    v1.7 makes the ordered-tuple comparison a MUST: "A scalar cannot carry a two-key
    order, so an implementation that collapses the keys into one number manufactures ties
    §2.2 does not have and then resolves them by whatever the store happened to yield."

    Key 3 is lexicographic byte order with the LOWER value winning — the inversion is
    easy to write backwards, and getting it backwards still yields a total order and
    still passes any test that only checks determinism. The unit test asserts the winner.
    """
    if a.literals != b.literals:
        return a.literals - b.literals
    if a.depth != b.depth:
        return a.depth - b.depth
    if a.canonical == b.canonical:
        return 0
    # Python compares `str` by code point, which for the ASCII path alphabet is byte
    # order. Not `locale.strcoll` — §6.2 requires every conformant peer to select the
    # same config, and a locale-sensitive comparison makes that a property of the host.
    return 1 if a.canonical < b.canonical else -1


def pattern_matches(path: str, canonical_pattern: str) -> bool:
    """§6.2 — does this canonicalized pattern cover this canonicalized path?"""
    return matches_pattern(path, canonical_pattern)
