#!/usr/bin/env python3
"""py-content-history — the composition host. **The wiring program.**

One core peer (`entity-core-protocol-python`, keystone, read-only), two extensions
(CONTENT v3.7 and HISTORY v1.10), the wiring program that installs them, and the one piece
of composition POLICY in this tree -- the history config write.

# This host is keystone's host plus the installs (W-18, the keystone peer contract S1)

``entity_core.peer.run_host(argv, configure)`` is keystone's own host as a library
function -- ``embed.host_main`` in their ``KEYSTONE-PEER-REPORT.json``, certified at
``fd31d9cacc90``. The CLI, the named identity, the seed policy, the frame budget, the
readiness record, the accept loop and the listener close are theirs; ``configure`` runs
after the peer is built and before anything listens. The hand copy of their ``main`` this
file used to carry is deleted.

**Where the post-traffic observation went.** ``COMPOSED-FINAL`` used to be printed from
this file's own ``finally`` around its own ``stop.wait()``, neither of which exists now.
It is printed when ``run_host`` RETURNS, which is strictly after its stop event and
therefore strictly after the traffic -- the same hook the typescript twin uses. On
``rust``, whose ``run.stop`` ends the process by signal with no hook at all, the same
observation needs a monitor thread; that is a real per-substrate difference and it is
recorded in that host rather than smoothed over here.
"""

from __future__ import annotations

import sys

from entity_core.peer import run_host

from entity_content import install_content
from entity_history import config_path, history_config, install_history

#: Captured in ``configure``, read after ``run_host`` returns.
INSTALLED = None


def configure(peer) -> None:
    """Install the composition. Runs before anything listens."""
    global INSTALLED

    # -- The composition. PLAN.json install_order = ["CONTENT", "HISTORY"]. --------
    #
    # `sdk-native` for both: this peer refuses a wire register at a `system/*` pattern and
    # both patterns are `system/*`. Not a shortcut -- the only route.
    #
    # On this peer `install_content` performs every §11.6.1 write itself; there is no
    # registration surface to call. That is the single largest difference between this
    # wiring program and the typescript one, and it is entirely inside the extension.
    content = install_content(peer)

    # HISTORY second. The order is the plan's; for these two it carries no ordering
    # CONSTRAINT -- neither declares a dependency on the other, and §2.2's consumer
    # positions do not apply because CONTENT registers no consumer.
    #
    # What matters is that `install_history` registers its emit consumer LAST, inside
    # itself, after its own §11.6.1 writes and type publication. Otherwise the recorder
    # observes its own installation and the audit log starts with ten entries nobody
    # performed.
    history = install_history(peer)
    INSTALLED = history

    # -- Composition POLICY: configure history (§6.1, §6.3). -----------------------
    #
    # Not extension code. §6.1: configuration "uses the standard tree `put`" and needs no
    # handler operation, so which paths a deployment audits is the composition's call.
    #
    # `pattern: "*"` is §6.3's own worked example for "a peer that wants history for all
    # paths". It is also what the oracle requires without saying so: the history category
    # writes to `system/validate/history-ext/*` and never configures history first, so an
    # unconfigured peer records nothing and fails twenty checks having done nothing wrong.
    peer.store.bind(
        config_path(peer.local_peer, "everything"),
        history_config(pattern="*", enabled=True),
    )

    sys.stderr.write(
        f"COMPOSED extensions=CONTENT,HISTORY "
        f"patterns={content.pattern},{history.pattern} "
        f"types={len(content.type_paths) + len(history.type_paths)} "
        f"handler_writes={len(content.handler_paths) + len(history.handler_paths)} "
        f"consumers=1 "
        # The honest field, and it is THREE-VALUED and OBSERVED rather than a hardcoded
        # `false` that said "measured". `unknown` until an event arrives; then `yes` or
        # `no` by what the recorder actually saw. The counts are printed beside it because
        # a verdict with no quantity under it cannot be debugged by the person who runs it.
        f"context_available={history.context_available} "
        f"contexts={history.recorder.stats.context_contexts} "
        f"fallbacks={history.recorder.stats.fallback_contexts} "
        f"recorded={history.recorder.stats.recorded}\n"
    )
    sys.stderr.flush()


def main(argv: list[str]) -> int:
    code = run_host(argv, configure)

    # THE POST-TRAFFIC OBSERVATION. The COMPOSED line is printed before the peer has served
    # anything, so its `context_available` is necessarily `unknown` or reflects the peer's
    # own bootstrap. The question §9.1 turns on -- does a WIRE-DRIVEN write carry the
    # caller's context -- can only be answered after the traffic. `tools/host-launch` reaps
    # the host before surfacing its stderr, so this line is captured.
    if INSTALLED is not None:
        stats = INSTALLED.recorder.stats
        sys.stderr.write(
            f"COMPOSED-FINAL context_available={INSTALLED.context_available} "
            f"contexts={stats.context_contexts} "
            f"fallbacks={stats.fallback_contexts} "
            f"observed={stats.observed} recorded={stats.recorded}\n"
        )
        sys.stderr.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
