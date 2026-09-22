#!/usr/bin/env python3
"""py-compute — the composition host. **The wiring program.**

One core peer (`entity-core-protocol-python`, keystone, read-only), one extension
(COMPUTE v3.29), and the wiring program that installs it.

# This host is keystone's host plus one install (W-18, the keystone peer contract S1)

``entity_core.peer.run_host(argv, configure)`` is keystone's own host as a library
function -- ``embed.host_main`` in their ``KEYSTONE-PEER-REPORT.json``, certified at
``fd31d9cacc90``. The CLI, the named identity, the seed policy, the frame budget, the
readiness record, the accept loop and the listener close are theirs; ``configure`` runs
after the peer is built and before anything listens. The hand copy of their ``main`` this
file used to carry is deleted.

**Where the post-traffic observation went.** ``COMPOSED-FINAL`` used to be printed from
this file's own ``finally`` around its own ``stop.wait()``, neither of which exists now --
the stop handlers and the listener close are ``run_host``'s. It is printed instead when
``run_host`` RETURNS, which is strictly after its stop event and therefore strictly after
the traffic. That is the same hook the typescript twin uses; on ``rust``, whose
``run.stop`` ends the process by signal with no hook at all, the same observation needs a
monitor thread.
"""

from __future__ import annotations

import sys

from entity_core.peer import run_host

from entity_compute import install_compute

#: Captured in ``configure``, read after ``run_host`` returns.
INSTALLED = None


def configure(peer) -> None:
    """Install the composition. Runs before anything listens."""
    global INSTALLED

    # -- The composition. PLAN.json install_order = ["COMPUTE"]. -------------------
    #
    # `sdk-native`: in-process against a live Peer. NOTE the reason has changed and the
    # value has not -- core §6.2's `system/*` reservation, which every earlier wiring
    # program in this tree cites here, was WITHDRAWN by `ENTITY-CORE-PROTOCOL` 0.8.2.13.
    # This peer still refuses a wire register at a `system/*` pattern, so `sdk-native` is
    # still the only route that works; it is now a measured property of this peer rather
    # than a rule anything inherits. See
    # `extension-contracts/content/EXTENSION.toml [substrate.wire_install_refusal]`.
    #
    # On this peer `install_compute` performs every §11.6.1 write itself; there is no
    # registration surface to call. That is the single largest difference between this
    # wiring program and the typescript one, and it is entirely inside the extension.
    compute = install_compute(peer)
    INSTALLED = compute

    # THE FIFTH FACE IS REPORTED HERE AND NOWHERE ELSE -- the one fact about this
    # composition that no other composition in the tree can produce. It is OBSERVED:
    # `install_compute` asks the peer for the seam rather than asserting its absence, so
    # when keystone landed H7 on this peer the line changed by itself (D13's Read layer;
    # keystone planted exactly that defect against their own H7 work).
    sys.stderr.write(
        f"COMPOSED extensions=COMPUTE pattern={compute.pattern} "
        f"types={len(compute.type_paths)} "
        f"handler_writes={len(compute.handler_paths)} "
        f"consumers=1 "
        f"evaluator={compute.evaluator_face} "
        f"rebuilt={compute.rebuilt}\n"
    )
    sys.stderr.flush()


def main(argv: list[str]) -> int:
    code = run_host(argv, configure)

    # THE POST-TRAFFIC OBSERVATION, and the reason it is here rather than beside the
    # COMPOSED line: the COMPOSED line is printed before the peer has served anything, so
    # `rebuilt` is necessarily 0 and the dependency index is empty. The question §7 turns
    # on -- did the oracle's installs actually register dependencies, and did any subgraph
    # FREEZE -- can only be answered after the traffic. `tools/host-launch` reaps the host
    # before surfacing its stderr, so this needs no new harness.
    if INSTALLED is not None:
        engine = INSTALLED.engine
        sys.stderr.write(
            f"COMPOSED-FINAL evaluator={INSTALLED.evaluator_face} "
            f"dependencies={engine.registered_dependencies} "
            f"watched={len(engine.watched_paths)}\n"
        )
        sys.stderr.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
