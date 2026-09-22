"""§5.1 recording and §3.2's self-guard, through the REAL emit pathway.

The recorder is registered on the peer's own store and driven by real ``store.bind``
calls, never by calling ``record_transition`` directly. That is D13's Reach row applied to
a consumer: a body that works when you call it and is never invoked by the pathway is the
failure this ecosystem has already shipped once.
"""

from __future__ import annotations

import pytest
from entity_core.peer import Peer
from entity_core.peer.model import Entity

from entity_history import (
    EVENT_CREATED,
    EVENT_UPDATED,
    HEAD_PREFIX,
    config_path,
    history_config,
    install_history,
    resolve_config,
)

TRACKED = "docs/report"


def payload(v: str) -> Entity:
    return Entity.make("system/validate/history-test", {"v": v})


@pytest.fixture
def rig():
    """A peer with history installed and `*` configured — the composition's posture."""
    peer = Peer(bytes([0x22] * 32), open_grants=True)
    install = install_history(peer)
    peer.store.bind(config_path(peer.local_peer, "everything"), history_config(pattern="*"))

    class Rig:
        def __init__(self):
            self.peer = peer
            self.install = install

        def abs(self, rel: str) -> str:
            return "/" + peer.local_peer + "/" + rel

        def head_hex(self, abs_path: str) -> str:
            return peer.store.hash_at("/" + peer.local_peer + "/" + HEAD_PREFIX + abs_path)

        def transition_at(self, abs_path: str) -> Entity:
            e = peer.store.get_at("/" + peer.local_peer + "/" + HEAD_PREFIX + abs_path)
            assert e is not None, f"no head pointer for {abs_path}"
            return e

    return Rig()


# ── §5.1 recording ──────────────────────────────────────────────────────────────


def test_a_tracked_write_is_recorded_with_created(rig):
    rig.peer.store.bind(rig.abs(TRACKED), payload("v1"))
    t = rig.transition_at(rig.abs(TRACKED))
    assert t.type == "system/history/transition"
    assert t.text("event") == EVENT_CREATED
    assert t.text("path") == rig.abs(TRACKED)


def test_the_event_vocabulary_is_historys_not_the_core_pathways(rig):
    """The peer emits `modified`; §2.1's table says `updated`.

    Asserted on the SECOND write, because the first is `created` in both vocabularies — a
    test that wrote once would pass with the mapping deleted.
    """
    rig.peer.store.bind(rig.abs(TRACKED), payload("v1"))
    rig.peer.store.bind(rig.abs(TRACKED), payload("v2"))
    t = rig.transition_at(rig.abs(TRACKED))
    assert t.text("event") == EVENT_UPDATED
    assert t.text("event") != "modified"


def test_created_has_no_previous_hash_and_updated_carries_it(rig):
    rig.peer.store.bind(rig.abs(TRACKED), payload("v1"))
    first = rig.transition_at(rig.abs(TRACKED))
    assert first.bytes_("previous_hash") is None
    v1_hash = first.bytes_("hash")
    assert v1_hash is not None

    rig.peer.store.bind(rig.abs(TRACKED), payload("v2"))
    second = rig.transition_at(rig.abs(TRACKED))
    assert second.bytes_("previous_hash") == v1_hash


def test_the_chain_links_through_previous_and_the_head_advances(rig):
    rig.peer.store.bind(rig.abs(TRACKED), payload("v1"))
    first_head = rig.head_hex(rig.abs(TRACKED))

    rig.peer.store.bind(rig.abs(TRACKED), payload("v2"))
    second_head = rig.head_hex(rig.abs(TRACKED))

    assert first_head != second_head
    second = rig.transition_at(rig.abs(TRACKED))
    prev = second.bytes_("previous")
    assert prev is not None
    assert prev.hex() == first_head


def test_author_capability_and_timestamp_are_present(rig):
    """§9.1's MUST, as a presence check — and see the test below for what it does NOT say."""
    rig.peer.store.bind(rig.abs(TRACKED), payload("v1"))
    t = rig.transition_at(rig.abs(TRACKED))
    assert t.bytes_("author") is not None
    assert t.bytes_("capability") is not None
    assert (t.uint("timestamp") or 0) > 0


def test_an_autonomous_write_records_the_autonomous_reading(rig):
    """THE MOST IMPORTANT ASSERTION IN THIS FILE — and it has already done its job once.

    **It was written as a tripwire and the tripwire fired.** Its previous form asserted
    ``context_available is False`` and said, in its own docstring: *"if this ever fails
    because fallback_contexts is 0, the peer started supplying a context... that is the
    good failure, and it is why this is asserted rather than commented."* On 2026-09-07
    keystone landed H8, and it failed. Writing an assertion whose failure you have
    described in advance is the cheapest early-warning this repo has, and it is worth
    more than the assertion itself.

    **What it asserts now is narrower and true.** ``rig`` drives a bare ``store.bind`` —
    no dispatch above it, so no execution context — and §2.1 defines that case exactly:
    author is the local peer's identity hash, capability is the handler grant. So this is
    the AUTONOMOUS control, and it stays valuable for the opposite reason it used to: it
    is what must keep passing once the context path works, or the recorder has started
    inventing provenance for writes that genuinely have none.

    ``context_available`` reads ``"not-observed"`` here, NOT ``"no"``: these events carried
    no context, which is a fact about these events and not about the peer. The wire-driven
    counterpart is the composition's job, not this rig's.
    """
    rig.peer.store.bind(rig.abs(TRACKED), payload("v1"))
    stats = rig.install.recorder.stats
    assert rig.install.context_available == "not-observed"
    assert stats.context_contexts == 0
    assert stats.recorded > 0
    assert stats.fallback_contexts == stats.observed - stats.skipped_self_guard
    assert stats.fallback_contexts > 0
    assert rig.install.recorder.recorded_transitions[0].provenance == "autonomous-fallback"


def test_caller_capability_is_omitted_when_it_would_equal_capability(rig):
    """§5.1 records it "only when it differs". The oracle's `w6_caller_cap_absent` too."""
    rig.peer.store.bind(rig.abs(TRACKED), payload("v1"))
    t = rig.transition_at(rig.abs(TRACKED))
    assert t.bytes_("caller_capability") is None


def test_clock_is_absent_because_clock_is_not_installed(rig):
    rig.peer.store.bind(rig.abs(TRACKED), payload("v1"))
    t = rig.transition_at(rig.abs(TRACKED))
    assert t.field("clock") is None


# ── §3.2 the self-guard ─────────────────────────────────────────────────────────


def test_the_head_pointer_write_does_not_recurse(rig):
    """Without the guard this is an unbounded loop.

    Two recorded, not one: the config write in the fixture is itself a tracked write and
    §3.2 says it SHOULD be recorded.
    """
    rig.peer.store.bind(rig.abs(TRACKED), payload("v1"))
    stats = rig.install.recorder.stats
    assert stats.skipped_self_guard > 0
    assert stats.recorded == 2
    tracked = [r for r in rig.install.recorder.recorded_transitions if r.path == rig.abs(TRACKED)]
    assert len(tracked) == 1


def test_the_guard_covers_head_not_the_whole_history_namespace(rig):
    """The easy wrong implementation guards `system/history/` and silently stops auditing
    configuration changes. §3.2 says config writes SHOULD be recorded."""
    cfg = config_path(rig.peer.local_peer, "everything")
    recorded = [r.path for r in rig.install.recorder.recorded_transitions]
    assert cfg in recorded, recorded


def test_a_bare_star_config_does_not_reach_another_peers_namespace(rig):
    """`canonicalize_pattern("*")` resolves to `/{local}/*` per core §5.4, so a remote
    path matches no config. A real scoping property, and the reason §6.3's
    "match everything" example is narrower than it reads."""
    remote = "z6MkfZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"
    remote_path = "/" + remote + "/project/readme"
    before = rig.install.recorder.stats.recorded
    rig.peer.store.bind(remote_path, payload("synced"))
    assert rig.install.recorder.stats.recorded == before
    assert resolve_config(rig.peer, remote_path, rig.peer.local_peer)[0] is None


def test_a_remote_history_path_is_trackable_and_its_head_write_is_guarded():
    """§3.2: "Remote peers' `system/history/` paths ... MAY be tracked ... The local
    peer's resulting head pointer update is ... excluded by the check above."

    Needs a PEER-WILDCARD config, not `*` — see the test above.
    """
    peer = Peer(bytes([0x23] * 32), open_grants=True)
    install = install_history(peer)
    peer.store.bind(
        config_path(peer.local_peer, "all-peers"),
        history_config(pattern="*/system/history/*"),
    )
    remote = "z6MkfZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"
    remote_history_path = "/" + remote + "/system/history/head/whatever"

    before_guard = install.recorder.stats.skipped_self_guard
    peer.store.bind(remote_history_path, payload("synced"))

    head = peer.store.hash_at("/" + peer.local_peer + "/" + HEAD_PREFIX + remote_history_path)
    assert head, "a remote history path is trackable (§3.2)"
    assert install.recorder.stats.skipped_self_guard == before_guard + 1


# ── §2.2 / §6.2 configuration ───────────────────────────────────────────────────


def test_history_is_opt_in():
    peer = Peer(bytes([0x24] * 32), open_grants=True)
    install = install_history(peer)
    peer.store.bind("/" + peer.local_peer + "/" + TRACKED, payload("v1"))
    assert install.recorder.stats.recorded == 0
    assert install.recorder.stats.skipped_unconfigured > 0


def test_a_disabled_config_records_nothing_and_parses_as_disabled():
    """The failure guarded: a `False` dropped by an omit-empty rule decodes as an ABSENT
    required field, `_parse_config` skips the entity, and the path is un-audited BY
    ACCIDENT rather than by instruction — silently re-enabling history for the path
    somebody wrote a config to turn off."""
    peer = Peer(bytes([0x25] * 32), open_grants=True)
    install = install_history(peer)
    peer.store.bind(config_path(peer.local_peer, "off"), history_config(pattern="*", enabled=False))
    abs_path = "/" + peer.local_peer + "/" + TRACKED
    peer.store.bind(abs_path, payload("v1"))

    config, _considered, skipped = resolve_config(peer, abs_path, peer.local_peer)
    assert config is not None, "the config must PARSE, not be skipped as malformed"
    assert config.enabled is False
    assert skipped == 0
    assert install.recorder.stats.recorded == 0


def test_an_event_outside_the_configs_list_is_not_recorded():
    peer = Peer(bytes([0x26] * 32), open_grants=True)
    install = install_history(peer)
    peer.store.bind(
        config_path(peer.local_peer, "creates-only"),
        history_config(pattern="*", events=[EVENT_CREATED]),
    )
    abs_path = "/" + peer.local_peer + "/" + TRACKED
    peer.store.bind(abs_path, payload("v1"))
    after_create = install.recorder.stats.recorded
    peer.store.bind(abs_path, payload("v2"))
    assert install.recorder.stats.recorded == after_create


def test_the_most_specific_matching_config_wins():
    peer = Peer(bytes([0x27] * 32), open_grants=True)
    install_history(peer)
    abs_path = "/" + peer.local_peer + "/" + TRACKED

    peer.store.bind(config_path(peer.local_peer, "everything"), history_config(pattern="*"))
    peer.store.bind(
        config_path(peer.local_peer, "docs"),
        history_config(pattern="docs/*", events=[EVENT_CREATED]),
    )

    config, _c, _s = resolve_config(peer, abs_path, peer.local_peer)
    assert config is not None
    assert config.pattern == "docs/*"
    assert config.events == (EVENT_CREATED,)


# ── §2.2 v1.10 exclusions — HIST-R16 ────────────────────────────────────────────
#
# The MUST is the ORDER, not the matching. §2.2: exclusion is checked AFTER the most
# specific matching configuration is selected and BEFORE the event-type filter, and an
# excluded path "does not fall through to a less specific configuration -- an exclusion
# is a decision, not a failure to match." The spec says two conformant readings exist
# without that sentence and that they differ on a path two configurations cover, so
# `test_an_excluded_path_does_not_fall_through` is the one that discriminates: the other
# reading (fold exclusion into matching, treat it as a non-match) passes every other test
# in this block.
#
# EVERY ASSERTION HERE IS A DELTA, and the first draft's were absolute — which failed,
# correctly, because a `pattern: "*"` config RECORDS ITS OWN WRITE. §3.2 keeps config
# paths out of the self-guard on purpose ("SHOULD be recorded as normal transitions for
# audit purposes"), so setup is not free and a count taken before it is not a baseline.


def _armed(peer, install, *configs):
    """Bind the configs, then return the recorded count — the baseline AFTER setup.

    Every config write is itself a tracked write under a `*` pattern, so this is the only
    honest place to take the reading.
    """
    for name, cfg in configs:
        peer.store.bind(config_path(peer.local_peer, name), cfg)
    return install.recorder.stats.recorded


def test_an_excluded_path_is_not_recorded():
    peer = Peer(bytes([0x28] * 32), open_grants=True)
    install = install_history(peer)
    before = _armed(
        peer,
        install,
        ("all-but-machinery", history_config(pattern="*", pattern_exclude=["system/capability/*"])),
    )
    peer.store.bind("/" + peer.local_peer + "/system/capability/grant-1", payload("v1"))
    assert install.recorder.stats.recorded == before


def test_the_control_the_same_path_IS_recorded_without_the_exclusion():
    """Without this, the test above passes for a peer that records nothing at all."""
    peer = Peer(bytes([0x29] * 32), open_grants=True)
    install = install_history(peer)
    before = _armed(peer, install, ("all", history_config(pattern="*")))
    peer.store.bind("/" + peer.local_peer + "/system/capability/grant-1", payload("v1"))
    assert install.recorder.stats.recorded == before + 1


def test_an_excluded_path_does_not_fall_through_to_a_less_specific_config():
    """§2.2's `[MUST]`, and the only test here that separates the two readings.

    `docs/*` is selected (more literal segments) and excludes the path. A reading that
    treated the exclusion as a NON-MATCH would continue the search, select `*`, and record
    the write — auditing a path the operator excluded, under a config they wrote to be
    more permissive elsewhere.
    """
    peer = Peer(bytes([0x2A] * 32), open_grants=True)
    install = install_history(peer)
    before = _armed(
        peer,
        install,
        ("everything", history_config(pattern="*")),
        ("docs", history_config(pattern="docs/*", pattern_exclude=["docs/secret/*"])),
    )

    peer.store.bind("/" + peer.local_peer + "/docs/secret/salaries", payload("v1"))
    assert install.recorder.stats.recorded == before, "fell through to the `*` config"

    # And the selected config still records everything it did not exclude.
    peer.store.bind("/" + peer.local_peer + "/docs/public/readme", payload("v1"))
    assert install.recorder.stats.recorded == before + 1


def test_exclusion_is_checked_BEFORE_the_event_filter():
    """Order, the second half. An excluded path is excluded for EVERY event type, so a
    `created`-only config must not record an excluded path's create either. The second
    assertion is the one that carries the weight: it shows the config is live and the
    first assertion is not passing because nothing was recorded at all."""
    peer = Peer(bytes([0x2B] * 32), open_grants=True)
    install = install_history(peer)
    before = _armed(
        peer,
        install,
        (
            "creates",
            history_config(
                pattern="*", pattern_exclude=["docs/secret/*"], events=[EVENT_CREATED]
            ),
        ),
    )
    peer.store.bind("/" + peer.local_peer + "/docs/secret/x", payload("v1"))
    assert install.recorder.stats.recorded == before
    peer.store.bind("/" + peer.local_peer + "/docs/open/x", payload("v1"))
    assert install.recorder.stats.recorded == before + 1


def test_a_bare_star_exclusion_is_canonicalized_like_a_pattern():
    """§2.2: exclusions "use the same core §5.4 pattern syntax as `pattern`; this field
    does not define a matcher of its own." So `canonicalize_pattern`'s bare-`*` rule — the
    one v1.8 corrected and this port already implements — applies here too. A port that
    canonicalized `pattern` and matched `pattern_exclude` RAW would silently exclude
    nothing, which reads exactly like a deployment that configured no exclusions."""
    peer = Peer(bytes([0x2C] * 32), open_grants=True)
    install = install_history(peer)
    before = _armed(
        peer, install, ("self-negating", history_config(pattern="*", pattern_exclude=["*"]))
    )
    peer.store.bind("/" + peer.local_peer + "/" + TRACKED, payload("v1"))
    assert install.recorder.stats.recorded == before
