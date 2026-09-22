"""Installation: the §11.6.1 writes, the 33 types, and the FIFTH FACE that is not installable.

**THIS FILE IS THE PORT'S ONE NEW INSTRUMENT, AND THE EVALUATOR-FACE TEST IS WHY.**
``install_compute`` answers ``not-installable`` for the H7 evaluator seam on this peer, and
that is the right answer — but a detector that can ONLY answer ``not-installable`` is
indistinguishable from one that is broken, which is AP-3's shape: a check that cannot reach the
branch it exists to test. D13's enforcement point wants an executed probe with BOTH controls,
and the three tests at the bottom of this file are that: one stand-in peer with no seam, one
whose setter stores, one whose setter SWALLOWS. The composed peer then tells us which of the
three the real substrate is, and the composition prints it.

The verdict on the REAL peer is measured by ``make build`` + the composition's ``COMPOSED``
line, not here — a fake peer is a control for our detector, never evidence about keystone's
tree (D13: source reads decide what to build, they never decide what is true).
"""

from __future__ import annotations

import importlib

import pytest
from entity_core.peer import Entity, Peer
from entity_core.peer.handlers import Outcome

import entity_compute
from entity_compute import (
    ALL_TYPES,
    BUILTINS_PREFIX,
    COMPUTE_PATTERN,
    RESULT,
    assert_not_builtin_override,
    install_compute,
)
from entity_compute.handler import OPERATION_SPECS

SEED = bytes([0x33] * 32)


def peer() -> Peer:
    return Peer(SEED, open_grants=True)


# ── §11.6.1 — the four writes this peer has no registration surface for ─────────


def test_install_performs_all_four_11_6_1_writes():
    """**This peer has no registration surface** (measured —
    ``languages/python/gates/host-seam/probe-seam.py``; ``profile.toml``
    keystone's python peer has no registration call), so all four writes are ours, through
    public names only. `typescript` calls ``peer.registerHandler`` and gets all four for free,
    which is the largest single difference between the two wiring programs and is entirely
    inside the extension.
    """
    p = peer()
    inst = install_compute(p)
    local = p.local_peer

    assert len(inst.handler_paths) == 4
    # (1) the manifest at the pattern path — what `_resolve_handler` walks for.
    manifest = p.store.get_at("/" + local + "/" + COMPUTE_PATTERN)
    assert manifest is not None and manifest.type == "system/handler"
    assert manifest.text("interface") == "system/handler/" + COMPUTE_PATTERN
    # (2) the interface entity — the oracle's `handler_manifest_decode` reads this.
    iface = p.store.get_at(inst.interface_path)
    assert iface is not None and iface.type == "system/handler/interface"
    assert iface.text("pattern") == COMPUTE_PATTERN
    assert set(iface.field("operations")) == {"eval", "install", "uninstall"}
    # (3)+(4) the self-issued handler grant and its signature at the §3.5 invariant pointer.
    grant = p.store.get_at("/" + local + "/system/capability/grants/" + COMPUTE_PATTERN)
    assert grant is not None and grant.type == "system/capability/token"
    assert p.store.get_at("/" + local + "/system/signature/" + grant.hash.hex()) is not None
    # (6) the executable body, in the container dispatch consults.
    assert COMPUTE_PATTERN in p.handlers


def test_the_manifest_declares_all_THREE_operations():
    """§3.1 declares three and the oracle hard-FAILs a manifest that omits ``install`` or
    ``uninstall`` (``FailCheck("compute handler missing operation: " + op)``), with 6 of the
    128 checks blocked behind ``handler_op_install``. §10.2 calls them SHOULDs while §10.1 MUSTs
    three behaviours OF install — four documents, three answers, and the measurable answer is
    three."""
    assert set(OPERATION_SPECS) == {"eval", "install", "uninstall"}
    assert OPERATION_SPECS["install"]["input_type"] == "system/compute/install-request"
    assert OPERATION_SPECS["install"]["output_type"] == "system/compute/install-result"
    # `eval` is `primitive/any` on BOTH sides and that is §3.2's shape, not a placeholder: the
    # input is any compute expression and the output is a value, a result or an error.
    assert OPERATION_SPECS["eval"] == {
        "input_type": "primitive/any", "output_type": "primitive/any",
    }


def test_all_33_types_are_published_at_system_type():
    """63 of this composition's core improvements are the oracle's ``type_compute_*_match``
    checks over these bytes — the one extension in the corpus whose type layer has a real
    cross-impl oracle."""
    p = peer()
    inst = install_compute(p)
    assert len(inst.type_paths) == 33
    assert len(ALL_TYPES) == 33
    for name in ALL_TYPES:
        path = "/" + p.local_peer + "/system/type/" + name
        assert path in inst.type_paths, name
        ent = p.store.get_at(path)
        assert ent is not None and ent.type == "system/type", name
        assert ent.field("name") == name


def test_the_consumer_is_registered_AFTER_the_installation_writes():
    """The ORDER, asserted rather than commented.

    For HISTORY, registering first meant the recorder observed its own installation — an audit
    log starting with ten entries nobody performed. Here it is stronger, because **COMPUTE's
    consumer WRITES BACK**: a §11.6.1 registration write arriving before the handler exists
    would re-enter an evaluator with a half-built peer behind it.

    Measured by counting what the engine saw. A consumer registered first would see 37 tree
    writes; registered last it sees none, because ``rebuild`` finds no processes on a fresh peer.
    """
    p = peer()
    seen: list[str] = []
    inst = install_compute(p)
    p.store.register_tree_consumer(lambda ev: seen.append(ev.path))
    assert inst.rebuilt == 0
    assert inst.engine.registered_dependencies == 0
    # And the engine IS live now: a write to a registered path would wake it. Nothing is
    # registered, so nothing fires — the state this assertion is about.
    p.store.bind("/" + p.local_peer + "/app/anything", Entity.make("app/x", {"v": 1}))
    assert seen == ["/" + p.local_peer + "/app/anything"]
    assert inst.engine.registered_dependencies == 0


# ── §4's override prohibition ────────────────────────────────────────────────────


def test_the_builtins_override_guard_refuses_a_builtin_pattern():
    """§4 / §3.5's prohibition, **ours to enforce as of v3.29 and not before.**

    Through v3.28 the rule described itself as a subset of core's ``system/*`` reservation;
    0.8.2.13 WITHDREW the reservation, so v3.29 restates it on its own basis — a cross-peer
    determinism requirement binding every installation path. There is nothing upstream that
    would refuse this on our behalf any more.
    """
    with pytest.raises(ValueError, match="§4"):
        assert_not_builtin_override(BUILTINS_PREFIX)
    with pytest.raises(ValueError):
        assert_not_builtin_override(BUILTINS_PREFIX + "/map")
    with pytest.raises(ValueError):
        assert_not_builtin_override("/somepeer/" + BUILTINS_PREFIX + "/fold")


def test_the_guard_does_NOT_refuse_a_NEAR_MISS_or_our_own_pattern():
    """Two controls, and the first is the one the separator test exists for:
    ``system/compute/builtinsomething`` is not a builtin, so a ``startswith`` guard would refuse
    a legal pattern. The second is the call ``install_compute`` actually makes."""
    assert_not_builtin_override(BUILTINS_PREFIX + "omething")
    assert_not_builtin_override(COMPUTE_PATTERN)
    assert_not_builtin_override("system/content")


# ── the FIFTH FACE, and the FOUR verdicts the detector must be able to give ──────


class _NoSeam:
    """A peer with no ``set_expression_evaluator``.

    What keystone's `python` peer was until their S3 bring-up; 44 of the 46 peers still.
    """

    def __init__(self) -> None:
        self.store = None
        self.local_peer = "z6Mkfake"


class _StoringSeam(_NoSeam):
    """A peer whose setter stores what it is handed — the `typescript` peer's behaviour."""

    def __init__(self) -> None:
        super().__init__()
        self.expression_evaluator = None

    def set_expression_evaluator(self, fn) -> None:
        self.expression_evaluator = fn


class _SwallowingSeam(_NoSeam):
    """A peer whose setter writes NOTHING.

    **This is not a hypothetical.** Keystone planted exactly this defect against their own H7
    work — a setter shaped like `julia`'s dead register map — which is why D13 has a Read layer
    at all: a call site is not a capability.
    """

    def __init__(self) -> None:
        super().__init__()
        self.expression_evaluator = None

    def set_expression_evaluator(self, fn) -> None:  # noqa: ARG002
        return None


class _NoReadBackSeam(_NoSeam):
    """A peer whose setter STORES, privately, and exposes no read-back attribute.

    **This is keystone's `python` peer, exactly** — the evaluator lives at ``Peer._evaluator``
    and they declined to add a public property on purpose, because a read-back that came back
    matching would have read ``installed`` over a signature mismatch and put a false green in
    our gate (their 13-c §3). The detector must not report this as ``not-observed``: nothing
    was observed to disagree, there is simply nothing to observe.
    """

    def __init__(self) -> None:
        super().__init__()
        self._evaluator = None

    def set_expression_evaluator(self, fn) -> None:
        self._evaluator = fn


def test_the_evaluator_face_reads_not_installable_when_the_seam_is_ABSENT():
    """The verdict on this peer today, measured through the detector rather than declared.

    ``Peer._entity_native_dispatch`` evaluates the built-in ``compute/literal`` shape and then
    answers ``501 unsupported_expression``, with no consultation step between the two at any
    visibility. So the face is ``not-installable`` — the substrate does not host it — rather
    than ``not-installed``, which would be a thing we had not built.
    """
    from entity_compute import _install_evaluator
    from entity_compute.sdk import DEFAULT_LIMITS

    assert _install_evaluator(_NoSeam(), DEFAULT_LIMITS) == "not-installable"


def test_the_evaluator_face_reads_installed_when_the_setter_STORES():
    """Control 1. Without it, ``not-installable`` is the only answer this detector has ever been
    seen to give, and an always-``not-installable`` function would be indistinguishable from a
    correct one — AP-3's shape in our own installer."""
    from entity_compute import _install_evaluator
    from entity_compute.sdk import DEFAULT_LIMITS

    fake = _StoringSeam()
    assert _install_evaluator(fake, DEFAULT_LIMITS) == "installed"
    assert callable(fake.expression_evaluator)


def test_the_evaluator_face_reads_not_observed_when_the_setter_SWALLOWS():
    """Control 2, and the reason the value is READ BACK rather than assumed. The one thing a
    setter cannot tell you is whether it set anything."""
    from entity_compute import _install_evaluator
    from entity_compute.sdk import DEFAULT_LIMITS

    assert _install_evaluator(_SwallowingSeam(), DEFAULT_LIMITS) == "not-observed"


def test_the_evaluator_face_reads_unverifiable_when_there_is_NOTHING_TO_READ_BACK():
    """Control 3, added 2026-09-14, and it is the one that separates two facts a single
    ``getattr(..., None)`` had been collapsing.

    ``_SwallowingSeam`` and ``_NoReadBackSeam`` both make ``getattr(peer,
    "expression_evaluator", None)`` return ``None``, and they are opposite situations: one is a
    peer defect we would owe keystone a packet about, the other is a missing instrument we
    would owe them a REQUEST about. Reporting both as ``not-observed`` understates the
    capability, which is the direction D14 records as the one nothing re-checks.

    **The negative control is the pair**: this assertion is only worth anything beside the
    ``_SwallowingSeam`` one above, because a detector that answered ``unverifiable`` for both
    would pass this test alone.
    """
    from entity_compute import _install_evaluator
    from entity_compute.sdk import DEFAULT_LIMITS

    seam = _NoReadBackSeam()
    assert _install_evaluator(seam, DEFAULT_LIMITS) == "unverifiable"
    # ...and the setter really did receive it. Without this the verdict would be satisfiable by
    # a peer that took the call and dropped it, which is the `_SwallowingSeam` case.
    assert callable(seam._evaluator)
    assert _install_evaluator(_SwallowingSeam(), DEFAULT_LIMITS) == "not-observed"


def test_install_reports_unverifiable_on_the_real_peer_and_installs_everything_else():
    """The D13 face amendment applied to our own installer rather than only to our reports: the
    other faces install regardless.

    **This is the only assertion in this file about the REAL peer**, and it has now flipped
    once, exactly as it was built to.** It read ``not-installable`` while keystone's `python`
    peer had no ``set_expression_evaluator``; their S3 bring-up landed the seam, so it reads
    ``unverifiable`` — installed through the certified two-argument binding, with no public
    read-back on the peer to confirm it. It becomes ``installed`` the day keystone adds
    ``Peer.expression_evaluator``, with no edit to the port. That is the whole reason the value
    is observed instead of written down.
    """
    p = peer()
    inst = install_compute(p)
    assert inst.evaluator_face == "unverifiable"
    assert len(inst.type_paths) == 33          # types face: installed
    assert COMPUTE_PATTERN in p.handlers        # handler face: installed
    assert inst.engine is not None              # emit_consumer face: installed


def test_the_installed_evaluator_DECLINES_a_non_compute_body():
    """The H7 seam's composition rule: returning None is how an evaluator DECLINES, and
    declining is the COMMON case rather than an error path. The peer's own
    ``501 unsupported_expression`` then stands, which is a better answer than one we invented
    about a body we do not understand — and it is what lets two installed evaluators compose.

    **Driven on a stand-in with a read-back, not on the real peer**, so the object handed to
    the setter can be recovered and CALLED. That is the only reason the stand-in is still here
    now that the real peer has the seam: keystone exposes no read-back, so there is no way to
    reach the installed callable through the peer.

    **The call shape below IS the certified binding**, and it is the assertion that would have
    caught the defect this file shipped with: ``evaluator(request, ctx) -> Outcome | None``.
    A one-argument callable raises ``TypeError`` inside the peer's ``except Exception`` and
    every compute body answers ``500 internal_error``.
    """
    from entity_compute import _install_evaluator
    from entity_compute.sdk import DEFAULT_LIMITS

    p = peer()

    class _SeamPeer:
        def __init__(self) -> None:
            self.store = p.store
            self.local_peer = p.local_peer
            self.expression_evaluator = None

        def set_expression_evaluator(self, fn) -> None:
            self.expression_evaluator = fn

    seam = _SeamPeer()
    assert _install_evaluator(seam, DEFAULT_LIMITS) == "installed"

    class _Request:
        def __init__(self, expression, path) -> None:
            self.expression = expression
            self.expression_path = path

    # `ctx` is the §6.8a HandlerContext, and it is READ rather than merely accepted: §4.1's
    # handler grant comes off it, and so do §3.2 E1's four scope bindings. A stand-in carrying
    # exactly the five attributes this evaluator reads — a real `HandlerContext` cannot be
    # constructed outside the peer's dispatcher, which is `context.unforgeable` doing its job.
    class _Ctx:
        def __init__(self, grant) -> None:
            self.handler_grant = grant
            self.operation = "eval"
            self.params = None
            self.resource = None
            self.caller_capability = None

    token, _sig = p.mint_token(p.identity.identity_hash, [], None)
    ctx = _Ctx(token)

    # Not a compute expression: DECLINED.
    assert seam.expression_evaluator(
        _Request(Entity.make("app/thing", {"x": 1}), "/p/app/x"), ctx
    ) is None

    # A compute expression: ANSWERED as an `Outcome`, and §3.2 E1 UNWRAPS the primitive at the
    # dispatch boundary — `primitive/any`, not the `compute/result` envelope §2.4 uses on the
    # handler path. Returning the wrapper here is K-12, the defect we routed against the peer's
    # own literal floor.
    lit = Entity.make("compute/literal", {"value": 7})
    answered = seam.expression_evaluator(_Request(lit, "/p/app/x"), ctx)
    assert isinstance(answered, Outcome)
    assert answered.status == 200
    assert answered.result.type == "primitive/any"
    assert answered.result.data == 7
    assert answered.result.type != RESULT

    # CONTROL — §4.1 FAILS CLOSED with no handler grant. This is the assertion that caught the
    # port: the test above was written passing `ctx = None` and went red at `403` the moment the
    # grant read landed, which is the evaluator refusing rather than the test being wrong.
    # Evaluating under the caller's capability instead would let
    # `capability = lookup/scope("caller_capability")` pass its own ceiling.
    refused = seam.expression_evaluator(_Request(lit, "/p/app/x"), _Ctx(None))
    assert isinstance(refused, Outcome)
    assert refused.status == 403
    assert refused.result.field("code") == "capability_denied"


# ── the surface ──────────────────────────────────────────────────────────────────


def test_every_declared_name_actually_exists():
    """``__all__`` is what `tools/sdk-parity.py` reads across ports; an entry naming nothing
    would be compared as present and be a phantom in the parity table."""
    missing = [n for n in entity_compute.__all__ if not hasattr(entity_compute, n)]
    assert missing == [], missing


def test_install_compute_is_idempotent_enough_to_re_run():
    """Not a spec clause — a property the wiring program needs. A composition that installed
    twice (a retry, a test fixture) must not accumulate a second consumer's worth of state in
    the index, because §7.1's ``register`` replaces rather than appends."""
    p = peer()
    first = install_compute(p)
    second = install_compute(p)
    assert first.pattern == second.pattern
    assert second.rebuilt == 0
    assert second.engine.registered_dependencies == 0
