/**
 * ts-compute — the composition host. **The wiring program.**
 *
 * One core peer (`entity-core-protocol-typescript`, keystone, read-only), one extension
 * (COMPUTE v3.29), and the wiring program that installs it.
 *
 * # This host is keystone's host plus one install (W-18, the keystone peer contract S1)
 *
 * `runHost(argv, configure)` is keystone's own host as a library function — `embed.host_main`
 * in their `KEYSTONE-PEER-REPORT.json`, certified at `fd31d9cacc90`. The CLI, the named
 * identity, the seed policy, the frame budget, the readiness record, the accept loop and the
 * bounded teardown are theirs; `configure` runs after the peer is built and before anything
 * listens. The hand copy of their `main` this file used to carry is deleted.
 */

import { runHost } from "entity-core-protocol-typescript";
import { installCompute } from "@entity-core/extension-compute";

runHost(process.argv.slice(2), (peer) => {
  // ── The composition. PLAN.json install_order = ["COMPUTE"]. ──────────────────
  //
  // `sdk-native`: in-process against a live Peer. NOTE the reason has changed and the
  // value has not — core §6.2's `system/*` reservation, which every earlier wiring
  // program in this tree cites here, was WITHDRAWN by `ENTITY-CORE-PROTOCOL` 0.8.2.13.
  // This peer still refuses a wire register at a `system/*` pattern, so `sdk-native` is
  // still the only route that works; it is now a measured property of this peer rather
  // than a rule anything inherits. See
  // `extension-contracts/content/EXTENSION.toml [substrate.wire_install_refusal]`.
  const compute = installCompute(peer);

  // THE FIFTH FACE IS REPORTED HERE AND NOWHERE ELSE, because it is the one fact about
  // this composition that no other composition in the tree can produce. It is OBSERVED —
  // `installCompute` reads the evaluator back off the peer rather than assuming the
  // setter did anything (D13's Read layer; keystone planted exactly that defect against
  // their own H7 work).
  process.stderr.write(
    `COMPOSED extensions=COMPUTE pattern=${compute.pattern} types=${compute.typePaths.length}` +
      ` evaluator=${compute.evaluatorFace}\n`,
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
