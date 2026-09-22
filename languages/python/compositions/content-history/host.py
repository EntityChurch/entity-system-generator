#!/usr/bin/env python3
"""python / content-history — the composed peer host. **The wiring program.**

The `typescript` twin is `../../../typescript/compositions/content-history/host.ts`, and
the two are worth diffing: the composition-specific part is the imports, the two
`install_*` calls and the config write, and everything else
— the CLI, the readiness line, the teardown — is the LANGUAGE's, which is why
`languages/<lang>/` owns those and a composition does not.

Hand-written in cycle 1, deliberately: write the code you want the generator to emit
before writing the generator. Two working wiring programs in two languages is the input a
template should be derived from; one is a sample of size one.

The CLI is byte-compatible with keystone's own `entity_core.host`: the oracle's harness
waits on a single `LISTENING ...` line on stdout, and a composed peer that spoke a
different dialect would need a forked harness.
"""

from __future__ import annotations

import base64
import os
import signal
import sys
import threading
from pathlib import Path

from entity_core.peer import Identity, Peer, listen

from entity_content import install_content
from entity_history import config_path, history_config, install_history

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
            # Not in keystone's host CLI, and present here on purpose: the §6.2
            # Amendment 1 MUST is about the CONFIGURED budget, so a host that cannot be
            # configured with a non-default one cannot demonstrate the difference.
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

    # ── The composition. PLAN.json install_order = ["CONTENT"]. ────────────────
    #
    # `sdk-native`: in-process against a live Peer, because the wire register op refuses
    # `system/*` patterns (core §6.2). Not a shortcut -- the only route.
    #
    # On this peer `install_content` performs every §11.6.1 write itself; there is no
    # registration surface to call. That is the single largest difference between this
    # wiring program and the typescript one, and it is entirely inside the extension.
    content = install_content(peer)

    # HISTORY second. The order is the plan's; for these two it carries no ordering
    # CONSTRAINT — neither declares a dependency on the other, and §2.2's consumer
    # positions do not apply because CONTENT registers no consumer.
    #
    # What matters is that `install_history` registers its emit consumer LAST, inside
    # itself, after its own §11.6.1 writes and type publication. Otherwise the recorder
    # observes its own installation and the audit log starts with ten entries nobody
    # performed.
    history = install_history(peer)

    # ── Composition POLICY: configure history (§6.1, §6.3). ────────────────────
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

    listener = listen(peer, port)
    bound = listener.port

    sys.stdout.write(
        f"LISTENING 127.0.0.1:{bound} peer_id={peer.local_peer} "
        f"open_grants={str(open_grants).lower()} validate={str(validate).lower()}\n"
    )
    sys.stdout.flush()
    # A second line, on stderr so no harness parsing `LISTENING` can trip on it: what the
    # composition actually installed. A composed peer that silently installed nothing
    # looks exactly like a bare peer to everything except the failing checks.
    sys.stderr.write(
        f"COMPOSED extensions=CONTENT,HISTORY "
        f"patterns={content.pattern},{history.pattern} "
        f"types={len(content.type_paths) + len(history.type_paths)} "
        f"handler_writes={len(content.handler_paths) + len(history.handler_paths)} "
        f"consumers=1 "
        # The honest field, and it is now THREE-VALUED and OBSERVED rather than a
        # hardcoded `false` that said "measured". `unknown` until an event arrives; then
        # `yes` or `no` by what the recorder actually saw. The counts are printed beside
        # it because a verdict with no quantity under it cannot be debugged by the person
        # who runs it.
        f"context_available={history.context_available} "
        f"contexts={history.recorder.stats.context_contexts} "
        f"fallbacks={history.recorder.stats.fallback_contexts} "
        f"recorded={history.recorder.stats.recorded}\n"
    )
    sys.stderr.flush()

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        stop.wait()
    finally:
        # THE POST-TRAFFIC OBSERVATION, and the reason it is here rather than beside the
        # COMPOSED line: the COMPOSED line is printed before the peer has served anything,
        # so its `context_available` is necessarily `unknown` or reflects the peer's own
        # bootstrap. The question §9.1 turns on -- does a WIRE-DRIVEN write carry the
        # caller's context -- can only be answered after the traffic. `tools/host-launch`
        # already surfaces the host's stderr after the oracle finishes, so this needs no
        # new harness.
        stats = history.recorder.stats
        sys.stderr.write(
            f"COMPOSED-FINAL context_available={history.context_available} "
            f"contexts={stats.context_contexts} "
            f"fallbacks={stats.fallback_contexts} "
            f"observed={stats.observed} recorded={stats.recorded}\n"
        )
        sys.stderr.flush()
        listener.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        os._exit(0)
