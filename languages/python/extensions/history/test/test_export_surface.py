"""The recorder is module-private — and on THIS peer that is a convention, not a boundary.

CONTENT §3.4 clause 1 split three ways across the ports: node's ``exports`` map ENFORCES,
python is CONVENTION ONLY, rust is enforced by the compiler. The same split applies here,
and this file asserts BOTH halves so the two ports' claims are never read as equal.

There is no MUST to point at — HISTORY has none. The boundary is ours, for the reason
``[sdk_surface]`` is (D16): a caller able to reach ``record_transition`` can append a
forged entry to an audit chain naming any author and any capability, linked into the real
chain by ``previous``. §7.2 calls that field the answer to "under what authority?", and a
forgeable answer is worse than none because it is believed.
"""

from __future__ import annotations

import importlib

import entity_history


def test_no_public_name_records_a_transition():
    offenders = [n for n in entity_history.__all__ if n.startswith("record") and n != "RecordedTransition"]
    assert offenders == [], offenders


def test_no_public_name_prunes_or_severs():
    offenders = [n for n in entity_history.__all__ if "prune" in n.lower() or "sever" in n.lower()]
    assert offenders == []


#: Names reachable in the package namespace that are NOT ours and NOT surface: the
#: package's own submodules, and third-party symbols the module body imports to define
#: its API with. Listed explicitly rather than filtered by a pattern, because the whole
#: point of the check below is that a NEW name cannot arrive without someone deciding —
#: and a wildcard exclusion would let it.
_NOT_SURFACE = {
    # submodules, bound by `from .x import y`
    "handler", "patterns", "sdk", "types",
    # `from __future__ import annotations`
    "annotations",
    # imported to DEFINE the API, not to export it. `from entity_history import *` does
    # reach these, which is a real (small) leak this test exists to keep bounded rather
    # than to pretend is absent — see below.
    "Entity", "dataclass",
}


def test_the_module_namespace_matches___all__():
    """``__all__`` is the declaration; ``dir()`` is what a ``from ... import *`` reaches.

    A name present in the module and absent from ``__all__`` is exactly the "a name
    arrived without anyone deciding" failure D16's gate exists for.

    **This found two on its first run** — ``Entity`` and ``dataclass``, imported by
    ``__init__.py`` to define ``HistoryInstallation`` with. They are reachable through a
    star-import and they are not our API. They are enumerated in ``_NOT_SURFACE`` rather
    than filtered away, so a THIRD one cannot arrive quietly; `python` has no
    ``exports`` map to refuse them, which is the same convention-versus-enforcement split
    this file's last test is about.
    """
    public = {n for n in dir(entity_history) if not n.startswith("_")}
    declared = set(entity_history.__all__)
    assert public - declared - _NOT_SURFACE == set()


def test_every_declared_name_actually_exists():
    """The other direction, and the one that catches a rename. ``__all__`` is what
    `tools/sdk-parity.py` reads across ports; an entry naming nothing would be compared
    as present and be a phantom in the parity table."""
    missing = [n for n in entity_history.__all__ if not hasattr(entity_history, n)]
    assert missing == [], missing


def test_the_convention_holds_AND_can_be_walked_around():
    """**Both halves, deliberately.**

    The first assertion is the claim; the second is the LIMIT of the claim. Python
    enforces nothing, and a port that asserted only the first would be reporting the
    `typescript` port's guarantee while shipping this one's.
    """
    assert not hasattr(entity_history, "record_transition")

    walked = importlib.import_module("entity_history._internal.recorder")
    assert hasattr(walked, "record_transition"), (
        "the private module IS importable — python enforces nothing, and this port's "
        "§3.4-shaped claim is CONVENTION ONLY. Recorded so it is not read as the "
        "typescript port's resolver-enforced boundary."
    )
