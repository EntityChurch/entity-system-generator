"""The §3.4 MUST — and the honest statement of how much weaker it is here.

  "Implementations MUST NOT expose `reassemble_content` as a public substrate primitive
   callable from third-party / SDK / external consumer code without an explicit
   capability-checking wrapper."   — EXTENSION-CONTENT §3.4

**The `typescript` port's equivalent test asserts on what NODE refuses**: it imports the
module by package name through its own `exports` map and confirms a deep import into
`internal/` raises `ERR_PACKAGE_PATH_NOT_EXPORTED`. The module resolver is the enforcer,
and the test only reads its verdict.

**There is no such enforcer in this language, and these tests say so twice** — once by
asserting the convention holds, and once by asserting, explicitly, that the convention
CAN be walked around. That second test looks like it is testing nothing. It is testing
the honesty of the claim: a capability statement that read identically in both ports
would be wrong in this one, and D13's whole subject is capability claims that transfer a
verdict across a boundary that is not the same boundary.
"""

from __future__ import annotations

import importlib

import pytest

import entity_content


def test_no_public_export_reassembles():
    """§3.4: nothing on the public surface reassembles, except the wrapper."""
    offenders = [
        name
        for name in entity_content.__all__
        if "reassemble" in name.lower() and name != "reassemble_under_capability"
    ]
    assert offenders == [], f"§3.4 MUST: public exports that reassemble: {offenders}"


def test_reassemble_content_is_not_reachable_through_the_package():
    """The bare algorithm is not an attribute of the package, under any name."""
    assert not hasattr(entity_content, "reassemble_content")
    assert "_internal" not in entity_content.__all__


def test_the_only_route_takes_a_context_and_a_target():
    """The signature is the structural half of the check.

    `target` was not a parameter until 2026-09-16 and its absence was the whole tell: **a
    capability check needs something to check the capability AGAINST**, and §3.4 scopes
    materialization to a PATH, so a wrapper with nowhere to put one could not have been
    checking anything. Losing `target` again would silently turn the check back into the
    two caller-supplied assertions it used to be.
    """
    import inspect

    params = list(inspect.signature(entity_content.reassemble_under_capability).parameters)
    assert params[0] == "ctx", "reassemble_under_capability(ctx, ...) — the ctx IS the anchor"
    assert params[1] == "target", "the target is what the grant is checked against (§3.4 clause 2)"
    assert "blob_hash" in params


# The three cases below are duck-typed ON PURPOSE and stay that way: they measure the gates
# that fire BEFORE any capability is read, so they must keep working for a caller holding
# nothing that resembles a dispatch. The capability decision itself needs a real context and
# a real grant, and lives in `test_sdk.py`.

TARGET = "/p/system/content/x"


def test_the_wrapper_refuses_a_context_from_another_handlers_dispatch():
    class Foreign:
        handler_pattern = "local/files"
        caller_cap = object()
        has_cap = True

    with pytest.raises(PermissionError, match="requires a system/content handler context"):
        entity_content.reassemble_under_capability(
            Foreign(), TARGET, b"\x00" * 33, store=object(), local_peer="p"
        )


def test_the_wrapper_refuses_a_context_carrying_no_caller_capability():
    class Uncapped:
        handler_pattern = entity_content.CONTENT_PATTERN
        caller_cap = None
        has_cap = False

    with pytest.raises(PermissionError, match="no caller capability"):
        entity_content.reassemble_under_capability(
            Uncapped(), TARGET, b"\x00" * 33, store=object(), local_peer="p"
        )


def test_the_wrapper_refuses_a_capped_context_with_no_captured_store_or_peer():
    """python's DispatchCtx carries no peer (measured), so BOTH the store and the local peer
    id must be passed. A caller that forgot either gets a refusal rather than a module-level
    singleton — and `local_peer` joined `store` here in 2026-09-16, because the §6.3
    predicate canonicalizes the target and the grant's scopes in that frame."""

    class Capped:
        handler_pattern = entity_content.CONTENT_PATTERN
        caller_cap = object()
        has_cap = True

    with pytest.raises(ValueError, match="carries no peer"):
        entity_content.reassemble_under_capability(Capped(), TARGET, b"\x00" * 33, store=object())
    with pytest.raises(ValueError, match="carries no peer"):
        entity_content.reassemble_under_capability(Capped(), TARGET, b"\x00" * 33, local_peer="p")


def test_the_boundary_is_convention_and_this_language_does_not_enforce_it():
    """**The uncomfortable test, and the reason it exists.**

    A deep import into `_internal` WORKS. Python has no `exports` map, no `internal`
    keyword, no assembly boundary — the underscore is a promise and nothing more. Asserting
    that the promise can be broken is what stops this port's §3.4 claim from being read as
    equivalent to the `typescript` port's, where the same import is refused by the runtime.

    If Python ever grows an enforced boundary and this test starts failing, that is good
    news and the assertion inverts.
    """
    module = importlib.import_module("entity_content._internal.reassemble")
    assert callable(module.reassemble_content), (
        "the algorithm is reachable by a determined consumer — "
        "the §3.4 boundary in this language is convention, not a mechanism"
    )
