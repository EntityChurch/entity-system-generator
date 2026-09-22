/**
 * content-history — the composed peer host. **The wiring program.**
 *
 * THE FIRST TWO-EXTENSION COMPOSITION. What changed from `content/host.ts` is exactly
 * three things, and everything else is byte-identical on purpose — the CLI, the readiness
 * line and the teardown belong to `languages/typescript/`, not to a composition:
 *
 *   1. two `install*` calls instead of one, in `PLAN.json`'s `install_order`
 *   2. the history CONFIG write, which is composition policy and not extension code
 *   3. the `COMPOSED` line reports both, plus the provenance of what history records
 *
 * Still hand-written, still deliberately: `DESIGN-THE-SYSTEM-STRUCTURE` §2 calls this
 * emitted-and-never-edited, and the plan was always to write the second and third worked
 * examples before factoring the emitter. This is the second.
 */

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

import { Peer, PeerIdentity } from "entity-core-protocol-typescript";
import { installContent } from "@entity-core/extension-content";
import { configPath, historyConfig, installHistory } from "@entity-core/extension-history";

/** Fixed 32-byte Ed25519 seed → stable peer identity across runs (no --name). */
const DEFAULT_SEED = new Uint8Array(32).fill(0x11);

function loadSeedFromName(name: string): Uint8Array {
  const path = join(homedir(), ".entity", "peers", name, "keypair");
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch (err) {
    process.stderr.write(`error: --name ${name}: ${err instanceof Error ? err.message : String(err)}\n`);
    process.exit(2);
  }
  const body = text
    .split(/\r?\n/)
    .filter((line) => line.length > 0 && !line.startsWith("-"))
    .join("");
  const seed = new Uint8Array(Buffer.from(body, "base64"));
  if (seed.length !== 32) {
    process.stderr.write(`error: --name ${name}: expected a 32-byte seed, got ${seed.length} bytes\n`);
    process.exit(2);
  }
  return seed;
}

async function main(): Promise<number> {
  let port = 7777;
  let openGrants = false;
  let validate = false;
  let seed = DEFAULT_SEED;

  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    switch (arg) {
      case "--port": {
        const next = argv[++i];
        const parsed = next === undefined ? NaN : Number(next);
        if (!Number.isInteger(parsed)) {
          process.stderr.write("error: --port requires an integer argument\n");
          return 2;
        }
        port = parsed;
        break;
      }
      case "--name": {
        const next = argv[++i];
        if (next === undefined) {
          process.stderr.write("error: --name requires a NAME argument\n");
          return 2;
        }
        seed = loadSeedFromName(next);
        break;
      }
      case "--debug-open-grants":
        openGrants = true;
        break;
      case "--validate":
        validate = true;
        break;
      case "-h":
      case "--help":
        process.stdout.write("usage: host [--port N] [--name NAME] [--debug-open-grants] [--validate]\n");
        return 0;
      default:
        process.stderr.write(`error: unknown argument '${arg}'\n`);
        return 2;
    }
  }

  const peer = new Peer({
    identity: PeerIdentity.fromSeed(seed),
    debugOpenGrants: openGrants,
    conformanceHandlers: validate,
  });

  // ── The composition. PLAN.json install_order = ["CONTENT", "HISTORY"]. ───────
  //
  // `sdk-native` for both: the wire register op refuses `system/*` patterns (core
  // §6.2) and both patterns are `system/*`. Not a shortcut — the only route.
  const content = installContent(peer);

  // HISTORY second. The order is the plan's, and for these two it carries no
  // ordering CONSTRAINT — neither declares a dependency on the other, and §2.2's
  // consumer positions do not apply because CONTENT registers no consumer.
  //
  // What DOES matter is that `installHistory` registers its emit consumer LAST,
  // inside itself, after its own §11.6.1 writes and type publication. Otherwise the
  // recorder observes its own installation: four tree writes plus six type entities
  // would be recorded as application transitions before the peer ever listens. That
  // is the "installing a handler emits tree-change events" finding cycle 1 routed,
  // and here it is not theoretical — it is the difference between an audit log that
  // starts empty and one that starts with ten entries nobody performed.
  const history = installHistory(peer);

  // ── Composition POLICY: configure history (§6.1, §6.3). ──────────────────────
  //
  // Not extension code. §6.1 is explicit that configuration "uses the standard tree
  // `put`" and needs no handler operation, so which paths a deployment audits is the
  // composition's decision and lives here.
  //
  // `pattern: "*"` is §6.3's own worked example for "a peer that wants history for
  // all paths". It is also what the oracle REQUIRES without saying so: the history
  // category writes to `system/validate/history-ext/*` and never configures history
  // first, so an unconfigured peer records nothing and fails twenty checks having
  // done nothing wrong.
  //
  // Written AFTER the recorder is registered, so this write is itself the first
  // recorded transition — which is correct and is the behaviour §3.2 describes: the
  // self-guard covers `system/history/head`, and config paths "SHOULD be recorded as
  // normal transitions for audit purposes".
  peer.tree.put(
    configPath(peer.localPeerId, "everything"),
    historyConfig({ pattern: "*", enabled: true }),
  );

  const bound = await peer.listen(port);

  process.stdout.write(
    `LISTENING 127.0.0.1:${bound} peer_id=${peer.localPeerId} open_grants=${openGrants} validate=${validate}\n`,
  );
  // A second line, on stderr so no harness parsing `LISTENING` can trip on it: what
  // the composition actually installed. A composed peer that silently installed
  // nothing looks exactly like a bare peer to everything except the failing checks.
  const stats = history.recorder.stats;
  process.stderr.write(
    `COMPOSED extensions=CONTENT,HISTORY ` +
      `patterns=${content.pattern},${history.pattern} ` +
      `types=${content.typePaths.length + history.typePaths.length} ` +
      `consumers=1 ` +
      // The honest field. `false` on every peer measured, and it means every
      // transition's `author` and `capability` are the §2.1 autonomous-case values
      // rather than the caller's. A reader of the audit trail needs this at the seam,
      // not buried in a report.
      `context_available=${history.contextAvailable()} ` +
      `contexts=${history.recorder.stats.contextContexts} ` +
      `fallbacks=${history.recorder.stats.fallbackContexts} ` +
      `recorded=${stats.recorded}\n`,
  );

  await new Promise<void>((resolve) => {
    const shutdown = (): void => resolve();
    process.once("SIGINT", shutdown);
    process.once("SIGTERM", shutdown);
  });

  // THE POST-TRAFFIC OBSERVATION. The COMPOSED line above is printed before the peer has
  // served anything, so its `context_available` necessarily reflects only the peer's own
  // bootstrap. The question §9.1 turns on -- does a WIRE-DRIVEN write carry the caller's
  // context -- can only be answered after the traffic. `tools/host-launch` reaps the host
  // before surfacing its stderr, so this line is captured.
  process.stderr.write(
    `COMPOSED-FINAL context_available=${history.contextAvailable()} ` +
      `contexts=${history.recorder.stats.contextContexts} ` +
      `fallbacks=${history.recorder.stats.fallbackContexts} ` +
      `observed=${history.recorder.stats.observed} ` +
      `recorded=${history.recorder.stats.recorded}\n`,
  );

  await peer.dispose();
  return 0;
}

main().then(
  (code) => process.exit(code),
  (err: unknown) => {
    process.stderr.write(`fatal: ${err instanceof Error ? (err.stack ?? err.message) : String(err)}\n`);
    process.exit(1);
  },
);
