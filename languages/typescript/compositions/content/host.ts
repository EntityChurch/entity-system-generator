/**
 * ts-content — the composition host. **The wiring program.**
 *
 * One core peer (`entity-core-protocol-typescript`, keystone, read-only), one extension
 * (CONTENT v3.7), and the wiring program that installs it.
 *
 * # This host is keystone's host plus one install (W-18, the keystone peer contract S1)
 *
 * `runHost(argv, configure)` is keystone's own host as a library function — `embed.host_main`
 * in their `KEYSTONE-PEER-REPORT.json`, certified at `fd31d9cacc90`. The CLI, the named
 * identity, the seed policy, the frame budget, the one readiness record, the accept loop and
 * the bounded teardown are THEIRS; `configure` runs after the peer is built and before
 * anything listens. The bare arm of `make regression` is the same function with a no-op
 * closure.
 *
 * **What this file used to carry and no longer does:** its own flag parser, its own
 * `~/.entity/peers/NAME/keypair` PEM reader and base64 decode, its own `new Peer({...})`, its
 * own `LISTENING` line and its own signal wait. 138 lines to 61. That code was a hand copy of
 * keystone's `main` — nine copies across this tree — and every copy was a place their fix
 * would not arrive.
 *
 * What is composition-specific, and all that a generator would fill from `PLAN.json`:
 * the import list and the `install*` calls, one per entry in `install_order`.
 *
 * The `COMPOSED` line on stderr is required by `tools/host-launch`: a composed peer that
 * silently installed nothing is byte-identical to a bare one from the outside, and every
 * content check would then fail with a message about the PEER.
 */

import { runHost } from "entity-core-protocol-typescript";
import { installContent } from "@entity-core/extension-content";

runHost(process.argv.slice(2), (peer) => {
  // ── The composition. PLAN.json install_order = ["CONTENT"]. ──────────────────
  //
  // `sdk-native`: in-process against a live Peer. The reason has changed and the value
  // has not — core §6.2's `system/*` reservation was WITHDRAWN by `ENTITY-CORE-PROTOCOL`
  // 0.8.2.13, and this peer still refuses a wire register at a `system/*` pattern. It is
  // a measured property of this peer rather than a rule anything inherits; see
  // `extension-contracts/content/EXTENSION.toml [substrate.wire_install_refusal]`.
  //
  // One extension, so the install order is trivially satisfied and is stated anyway: the
  // first two-extension composition is where an unstated ordering rule becomes an
  // ordering bug (SYSTEM-COMPOSITION §2.2).
  const content = installContent(peer);

  // The proof-of-install line, printed inside `configure` and therefore before the
  // readiness record — `runHost`'s `recordFields` are fixed before `configure` runs
  // (keystone K-21), so the readiness record cannot carry read-back install state.
  process.stderr.write(
    `COMPOSED extensions=CONTENT pattern=${content.pattern} types=${content.typePaths.length}\n`,
  );
}).then(
  (code) => process.exit(code),
  (err: unknown) => {
    process.stderr.write(
      `fatal: ${err instanceof Error ? (err.stack ?? err.message) : String(err)}\n`,
    );
    process.exit(1);
  },
);
