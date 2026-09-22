#!/usr/bin/env python3
"""python / compute — the composed peer host. **The wiring program.**

The `typescript` twin is `../../../typescript/compositions/compute/host.ts`, and the two are
worth diffing: the composition-specific part is the import and the one `install_*` call, and
everything else — the CLI, the readiness line, the teardown — is the LANGUAGE's, which is why
`languages/<target>/` owns those and a composition does not.

Hand-written in cycle 1, deliberately: write the code you want the generator to emit before
writing the generator. Three wiring programs in one language is now the input a template should
be derived from, and this one is the specimen that carries a face verdict.

The CLI is byte-compatible with keystone's own `entity_core.host`: the oracle's harness waits on
a single `LISTENING ...` line on stdout, and a composed peer that spoke a different dialect
would need a forked harness.
"""

from __future__ import annotations

import base64
import os
import signal
import sys
import threading
from pathlib import Path

from entity_core.peer import Identity, Peer, listen

from entity_compute import install_compute

#: Fixed 32-byte Ed25519 seed -> stable peer identity across runs (no --name).
DEFAULT_SEED = bytes([0x11] * 32)


def load_seed_from_name(name: str) -> bytes:
    """The standard on-disk keypair (Go entity-peer --name / peer-manager convention):
    ~/.entity/peers/NAME/keypair, a PEM whose body is base64(seed)."""
    path = Path.home() / ".entity" / "peers" / name / "keypair"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"error: --name {name}: {exc}\n")
        raise SystemExit(2)
    body = "".join(line for line in text.splitlines() if line and not line.startswith("-"))
    seed = base64.b64decode(body)
    if len(seed) != 32:
        sys.stderr.write(f"error: --name {name}: expected a 32-byte seed, got {len(seed)} bytes\n")
        raise SystemExit(2)
    return seed


def main(argv: list[str]) -> int:
    port = 7777
    open_grants = False
    validate = False
    seed = DEFAULT_SEED
    max_frame_bytes: int | None = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--port":
            i += 1
            if i >= len(argv) or not argv[i].lstrip("-").isdigit():
                sys.stderr.write("error: --port requires an integer argument\n")
                return 2
            port = int(argv[i])
        elif arg == "--name":
            i += 1
            if i >= len(argv):
                sys.stderr.write("error: --name requires a NAME argument\n")
                return 2
            seed = load_seed_from_name(argv[i])
        elif arg == "--max-frame-bytes":
            # Not in keystone's host CLI, and present here for the reason the other python
            # wiring programs carry it: the §6.2 Amendment 1 MUST is about the CONFIGURED
            # budget, so a host that cannot be configured with a non-default one cannot
            # demonstrate the difference.
            i += 1
            if i >= len(argv) or not argv[i].isdigit():
                sys.stderr.write("error: --max-frame-bytes requires an integer argument\n")
                return 2
            max_frame_bytes = int(argv[i])
        elif arg == "--debug-open-grants":
            open_grants = True
        elif arg == "--validate":
            validate = True
        elif arg in ("-h", "--help"):
            sys.stdout.write(
                "usage: host [--port N] [--name NAME] [--max-frame-bytes N] "
                "[--debug-open-grants] [--validate]\n"
            )
            return 0
        else:
            sys.stderr.write(f"error: unknown argument '{arg}'\n")
            return 2
        i += 1

    peer_kwargs: dict = {"open_grants": open_grants, "conformance": validate}
    if max_frame_bytes is not None:
        peer_kwargs["max_frame_bytes"] = max_frame_bytes
    peer = Peer(seed, **peer_kwargs)

    # ── The composition. PLAN.json install_order = ["COMPUTE"]. ────────────────────
    #
    # `sdk-native`: in-process against a live Peer. NOTE the reason has changed and the value
    # has not — core §6.2's `system/*` reservation, which every earlier wiring program in this
    # tree cites here, was WITHDRAWN by `ENTITY-CORE-PROTOCOL` 0.8.2.13. This peer still
    # refuses a wire register at a `system/*` pattern, so `sdk-native` is still the only route
    # that works; it is now a measured property of this peer rather than a rule anything
    # inherits. See `extension-contracts/content/EXTENSION.toml
    # [substrate.wire_install_refusal]`.
    #
    # On this peer `install_compute` performs every §11.6.1 write itself; there is no
    # registration surface to call. That is the single largest difference between this wiring
    # program and the typescript one, and it is entirely inside the extension.
    compute = install_compute(peer)

    listener = listen(peer, port)
    bound = listener.port

    sys.stdout.write(
        f"LISTENING 127.0.0.1:{bound} peer_id={peer.local_peer} "
        f"open_grants={str(open_grants).lower()} validate={str(validate).lower()}\n"
    )
    sys.stdout.flush()
    # A second line, on stderr so no harness parsing `LISTENING` can trip on it: what the
    # composition actually installed. A composed peer that silently installed nothing looks
    # exactly like a bare peer to everything except the failing checks.
    #
    # THE FIFTH FACE IS REPORTED HERE AND NOWHERE ELSE, and on this peer it reads
    # `not-installable` — the one fact about this composition that no other composition in the
    # tree can produce. It is OBSERVED: `install_compute` asks the peer for the seam rather than
    # asserting its absence, so the day keystone lands H7 on this peer this line changes by
    # itself (D13's Read layer; keystone planted exactly that defect against their own H7 work).
    sys.stderr.write(
        f"COMPOSED extensions=COMPUTE pattern={compute.pattern} "
        f"types={len(compute.type_paths)} "
        f"handler_writes={len(compute.handler_paths)} "
        f"consumers=1 "
        f"evaluator={compute.evaluator_face} "
        f"rebuilt={compute.rebuilt}\n"
    )
    sys.stderr.flush()

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        stop.wait()
    finally:
        # THE POST-TRAFFIC OBSERVATION, and the reason it is here rather than beside the
        # COMPOSED line: the COMPOSED line is printed before the peer has served anything, so
        # `rebuilt` is necessarily 0 and the dependency index is empty. The question §7 turns on
        # -- did the oracle's installs actually register dependencies, and did any subgraph
        # FREEZE -- can only be answered after the traffic. `tools/host-launch` already surfaces
        # the host's stderr after the oracle finishes, so this needs no new harness.
        engine = compute.engine
        sys.stderr.write(
            f"COMPOSED-FINAL evaluator={compute.evaluator_face} "
            f"dependencies={engine.registered_dependencies} "
            f"watched={len(engine.watched_paths)}\n"
        )
        sys.stderr.flush()
        listener.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        os._exit(0)
