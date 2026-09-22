"""The evaluator is module-private — and on THIS peer that is a convention, not a boundary.

CONTENT §3.4 clause 1 split three ways across the ports: node's ``exports`` map ENFORCES,
python is CONVENTION ONLY, rust is enforced by the compiler. This file asserts BOTH halves so
the two ports' claims are never read as equal.

**FOR THIS EXTENSION THE GAP IS WIDER THAN IT WAS FOR EITHER OF THE FIRST TWO, and that is
worth stating rather than inheriting.** HISTORY's private surface let a caller forge an audit
entry; CONTENT's let one reach a chunker. ``evaluate`` takes its ENTIRE AUTHORITY AS AN
ARGUMENT: a caller who constructs an ``EvalContext`` with ``has_content_store_access=True``
holds §4.2 Tier 0, which turns the evaluator into the content-store oracle §4.2 exists to
prevent — and can also pass ``can_read_path=lambda _: True``, which is §6.2's capability check
removed. On `typescript` the module resolver refuses that reach and the test asserts on the
refusal. Here nothing refuses it, and the last test in this file says so out loud.
"""

from __future__ import annotations

import importlib

import entity_compute


def test_no_public_name_evaluates_with_a_caller_supplied_context():
    """The one-line version of this file's whole argument: the public surface has no entry point
    that takes an ``EvalContext``. :class:`entity_compute.ComputeEvaluator` takes a PEER and
    builds the context itself, so ``has_content_store_access`` and the two path predicates are
    ours to set and a caller's to influence only through the documented keywords."""
    offenders = [n for n in entity_compute.__all__ if "context" in n.lower()]
    assert offenders == [], offenders
    assert not hasattr(entity_compute, "evaluate")
    assert not hasattr(entity_compute, "EvalContext")


def test_no_public_name_reaches_the_three_tier_gate_directly():
    """§4.2's ``resolve`` / ``validate_compute_resolvable`` are the gate itself. A caller holding
    either can ask the content store for an entity it never had, which is the exact capability
    the tiers exist to withhold."""
    for name in ("resolve", "validate_compute_resolvable", "materialize"):
        assert not hasattr(entity_compute, name), name


#: Names reachable in the package namespace that are NOT ours and NOT surface: the package's own
#: submodules, and third-party symbols the module body imports to define its API with. Listed
#: explicitly rather than filtered by a pattern, because the whole point of the check below is
#: that a NEW name cannot arrive without someone deciding — and a wildcard exclusion would let
#: it.
_NOT_SURFACE = {
    # submodules, bound by `from .x import y`
    "handler", "sdk", "types",
    # `from __future__ import annotations`
    "annotations",
    # imported to DEFINE the API, not to export it. `from entity_compute import *` does reach
    # these, which is a real (small) leak this test exists to keep bounded rather than to
    # pretend is absent.
    "Any", "Entity", "dataclass",
    # §3.1's manifest, read by `install_compute` and by `test_install.py`. NOT surface on
    # purpose: `typescript` carries the same data as `ComputeHandler.operations`, an instance
    # field with no exported name, so putting this in `__all__` would be drift with no
    # counterpart rather than a contract.
    "OPERATION_SPECS",
}


def test_the_module_namespace_matches___all__():
    """``__all__`` is the declaration; ``dir()`` is what a ``from ... import *`` reaches.

    A name present in the module and absent from ``__all__`` is exactly the "a name arrived
    without anyone deciding" failure D16's gate exists for — and `tools/sdk-parity.py` reads
    ``__all__``, so a name that is reachable and undeclared is invisible to the parity table
    while being usable by a consumer.
    """
    public = {n for n in dir(entity_compute) if not n.startswith("_")}
    declared = set(entity_compute.__all__)
    assert public - declared - _NOT_SURFACE == set()


def test_every_declared_name_exists_and_the_list_has_no_duplicates():
    """Both directions. A missing entry is a phantom in the parity table; a duplicate makes the
    declared count disagree with the declared SET, which is AP-8's mechanism (``Blob``/``BLOB``
    collapsing to one key) in a hand-maintained list."""
    missing = [n for n in entity_compute.__all__ if not hasattr(entity_compute, n)]
    assert missing == [], missing
    assert len(entity_compute.__all__) == len(set(entity_compute.__all__))


def test_the_surface_carries_all_33_type_constants_FLAT():
    """D16 / ``[sdk_surface]``: flat names are the contract in every port and a grouped object is
    an alias, never the other way round. CONTENT paid 18 drift entries for learning it the other
    way, and HISTORY settled it — 22 names in both ports with 20 differing, because one port
    bundled the constants and the other did not."""
    from entity_compute import ALL_TYPES

    for name in (
        "LITERAL", "LOOKUP_SCOPE", "LOOKUP_TREE", "LOOKUP_HASH", "APPLY", "IF", "LET", "LAMBDA",
        "ARITHMETIC", "COMPARE", "LOGIC", "FIELD", "CONSTRUCT", "INDEX", "LENGTH",
        "NUMERIC_CAST", "CLOSURE", "SCOPE", "SCOPE_BINDING", "RESULT", "ERROR", "SUBGRAPH",
        "INSTALL_REQUEST", "INSTALL_RESULT", "MAP_ARGS", "FILTER_ARGS", "FOLD_ARGS",
        "RANGE_ARGS", "GROUP_BY_ARGS", "GROUP", "CONCAT_ARGS", "ASSOC_ARGS", "STORE_ARGS",
    ):
        assert name in entity_compute.__all__, name
    assert len(ALL_TYPES) == 33
    # No grouped alias object, in either direction.
    assert not hasattr(entity_compute, "COMPUTE_TYPES")
    assert not hasattr(entity_compute, "ComputeTypes")


def test_all_sixteen_9_1_codes_are_public():
    """§9.1's set, and the reason it is surface at all: `tools/check-error-codes.py` reads the
    port's EMIT SITES and requires every code to be declared with an authority, in BOTH
    directions since 2026-09-08 — a code the SPEC names and no port emits is a deviation too.
    Exporting the constants is what keeps the emit sites from carrying string literals the gate
    has to guess at."""
    codes = [n for n in entity_compute.__all__ if n.startswith("CODE_")]
    assert len(codes) == 16, sorted(codes)


def test_the_convention_holds_AND_can_be_walked_around():
    """**Both halves, deliberately.**

    The first assertions are the claim; the last is the LIMIT of the claim. Python enforces
    nothing, and a port that asserted only the first would be reporting the `typescript` port's
    resolver-enforced guarantee while shipping this one's convention.
    """
    assert not hasattr(entity_compute, "evaluate")
    assert not hasattr(entity_compute, "EvalContext")
    assert not hasattr(entity_compute, "ConstructedValue")

    walked = importlib.import_module("entity_compute._internal.evaluator")
    assert hasattr(walked, "evaluate"), (
        "the private module IS importable — python enforces nothing, and this port's "
        "§3.4-shaped claim is CONVENTION ONLY. Recorded so it is not read as the typescript "
        "port's resolver-enforced boundary."
    )
    assert hasattr(walked, "EvalContext")
