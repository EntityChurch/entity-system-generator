/**
 * ts-content-history — the composition host. **The wiring program.**
 *
 * One core peer (`entity-core-protocol-typescript`, keystone, read-only), two extensions
 * (CONTENT v3.7 and HISTORY v1.10), the wiring program that installs them, and the one
 * piece of composition POLICY in this tree — the history config write.
 *
 * # This host is keystone's host plus the installs (W-18, the keystone peer contract S1)
 *
 * `runHost(argv, configure)` is keystone's own host as a library function — `embed.host_main`
 * in their `KEYSTONE-PEER-REPORT.json`, certified at `fd31d9cacc90`. The CLI, the named
 * identity, the seed policy, the frame budget, the readiness record, the accept loop and the
 * bounded teardown are theirs; `configure` runs after the peer is built and before anything
 * listens. The hand copy of their `main` this file used to carry is deleted.
 *
 * **Where the post-traffic observation went.** `COMPOSED-FINAL` used to be printed from this
 * file's own SIGTERM wait, which no longer exists — the stop handlers are `runHost`'s. It is
 * printed instead when `runHost` RESOLVES, which is strictly after its `stopped` promise and
 * therefore strictly after the traffic. That is a better hook than the one it replaced and it
 * needs no second signal listener: on `rust`, whose `run.stop` ends the process by signal with
 * no hook at all, the same observation needs a monitor thread.
 */

import { runHost } from "entity-core-protocol-typescript";
import { installContent } from "@entity-core/extension-content";
import { configPath, historyConfig, installHistory } from "@entity-core/extension-history";

/**
 * Captured in `configure`, read after `runHost` resolves. The TYPE is
 * `ReturnType<typeof installHistory>` and never a hand-written shape: the first draft of
 * this file restated the recorder's fields here and got `contextAvailable()` wrong — it
 * returns `"yes" | "not-observed" | "unknown"`, not a boolean — which `tsc` caught on the
 * first build. A second copy of a type is a second place for it to drift.
 */
let installed: ReturnType<typeof installHistory> | null = null;

runHost(process.argv.slice(2), (peer) => {
  // ── The composition. PLAN.json install_order = ["CONTENT", "HISTORY"]. ───────
  //
  // `sdk-native` for both: this peer refuses a wire register at a `system/*` pattern and
  // both patterns are `system/*`. Not a shortcut — the only route.
  const content = installContent(peer);

  // HISTORY second. The order is the plan's, and for these two it carries no ordering
  // CONSTRAINT — neither declares a dependency on the other, and §2.2's consumer
  // positions do not apply because CONTENT registers no consumer.
  //
  // What DOES matter is that `installHistory` registers its emit consumer LAST, inside
  // itself, after its own §11.6.1 writes and type publication. Otherwise the recorder
  // observes its own installation: four tree writes plus six type entities would be
  // recorded as application transitions before the peer ever listens. That is the
  // "installing a handler emits tree-change events" finding cycle 1 routed, and here it
  // is not theoretical — it is the difference between an audit log that starts empty and
  // one that starts with ten entries nobody performed.
  const history = installHistory(peer);

  // ── Composition POLICY: configure history (§6.1, §6.3). ──────────────────────
  //
  // Not extension code. §6.1 is explicit that configuration "uses the standard tree
  // `put`" and needs no handler operation, so which paths a deployment audits is the
  // composition's decision and lives here.
  //
  // `pattern: "*"` is §6.3's own worked example for "a peer that wants history for all
  // paths". It is also what the oracle REQUIRES without saying so: the history category
  // writes to `system/validate/history-ext/*` and never configures history first, so an
  // unconfigured peer records nothing and fails twenty checks having done nothing wrong.
  //
  // Written AFTER the recorder is registered, so this write is itself the first recorded
  // transition — which is correct and is the behaviour §3.2 describes: the self-guard
  // covers `system/history/head`, and config paths "SHOULD be recorded as normal
  // transitions for audit purposes".
  peer.tree.put(
    configPath(peer.localPeerId, "everything"),
    historyConfig({ pattern: "*", enabled: true }),
  );

  installed = history;

  const stats = history.recorder.stats;
  process.stderr.write(
    `COMPOSED extensions=CONTENT,HISTORY ` +
      `patterns=${content.pattern},${history.pattern} ` +
      `types=${content.typePaths.length + history.typePaths.length} ` +
      `consumers=1 ` +
      // The honest field. It means every transition's `author` and `capability` are the
      // §2.1 autonomous-case values rather than the caller's. A reader of the audit trail
      // needs this at the seam, not buried in a report.
      `context_available=${history.contextAvailable()} ` +
      `contexts=${stats.contextContexts} ` +
      `fallbacks=${stats.fallbackContexts} ` +
      `recorded=${stats.recorded}\n`,
  );
}).then(
  (code) => {
    // THE POST-TRAFFIC OBSERVATION. The COMPOSED line above is printed before the peer has
    // served anything, so its `context_available` necessarily reflects only the peer's own
    // bootstrap. The question §9.1 turns on — does a WIRE-DRIVEN write carry the caller's
    // context — can only be answered after the traffic. `tools/host-launch` reaps the host
    // before surfacing its stderr, so this line is captured.
    if (installed !== null) {
      const s = installed.recorder.stats;
      process.stderr.write(
        `COMPOSED-FINAL context_available=${installed.contextAvailable()} ` +
          `contexts=${s.contextContexts} ` +
          `fallbacks=${s.fallbackContexts} ` +
          `observed=${s.observed} ` +
          `recorded=${s.recorded}\n`,
      );
    }
    process.exit(code);
  },
  (err: unknown) => {
    process.stderr.write(
      `fatal: ${err instanceof Error ? (err.stack ?? err.message) : String(err)}\n`,
    );
    process.exit(1);
  },
);
