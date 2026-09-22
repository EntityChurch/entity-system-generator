#!/usr/bin/env python3
"""py-content — the composition host. **The wiring program.**

One core peer (`entity-core-protocol-python`, keystone, read-only), one extension
(CONTENT v3.7), and the wiring program that installs it.

# This host is keystone's host plus one install (W-18, the keystone peer contract S1)

``entity_core.peer.run_host(argv, configure)`` is keystone's own host as a library
function -- ``embed.host_main`` in their ``KEYSTONE-PEER-REPORT.json``, certified at
``fd31d9cacc90``. The CLI, the named identity, the seed policy, the frame budget, the one
readiness record, the accept loop and the listener close are THEIRS; ``configure`` runs
after the peer is built and before anything listens. The bare arm of ``make regression``
is the same function with a no-op configure.

**What this file used to carry and no longer does:** its own flag parser, its own
``~/.entity/peers/NAME/keypair`` PEM reader and base64 decode, its own ``Peer(...)``
construction, its own ``LISTENING`` line, its own signal handlers and its own
``threading.Event``. 144 lines to 64. That code was a hand copy of keystone's ``main`` --
nine copies across this tree -- and every copy was a place their fix would not arrive.

Its twins are ``../../../typescript/compositions/content/host.ts`` and
``../../../rust/compositions/content/host.rs``, and the three are worth diffing: what
differs between them now is the spelling of one function call.
"""

from __future__ import annotations

import sys

from entity_core.peer import run_host

from entity_content import install_content


def configure(peer) -> None:
    """Install the composition. Runs before anything listens."""
    # -- The composition. PLAN.json install_order = ["CONTENT"]. -------------------
    #
    # `sdk-native`: in-process against a live Peer. The reason has changed and the value
    # has not -- core §6.2's `system/*` reservation was WITHDRAWN by
    # `ENTITY-CORE-PROTOCOL` 0.8.2.13, and this peer still refuses a wire register at a
    # `system/*` pattern. A measured property of this peer, not a rule anything inherits;
    # see `extension-contracts/content/EXTENSION.toml [substrate.wire_install_refusal]`.
    #
    # On this peer `install_content` performs every §11.6.1 write itself; there is no
    # registration surface to call. That is the single largest difference between this
    # wiring program and the typescript one, and it is entirely inside the extension.
    content = install_content(peer)

    # The proof-of-install line, required by `tools/host-launch`: a composed peer that
    # silently installed nothing is byte-identical to a bare one from the outside, and
    # every content check would then fail with a message about the PEER. Printed inside
    # `configure` and therefore before the readiness record -- `run_host`'s
    # `extra_record_fields` are fixed before `configure` runs (keystone K-21).
    sys.stderr.write(
        f"COMPOSED extensions=CONTENT pattern={content.pattern} "
        f"types={len(content.type_paths)} handler_writes={len(content.handler_paths)}\n"
    )
    sys.stderr.flush()


if __name__ == "__main__":
    raise SystemExit(run_host(sys.argv[1:], configure))
