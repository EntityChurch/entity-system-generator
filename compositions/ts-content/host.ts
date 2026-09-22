/**
 * ts-content — the composed peer host. **The wiring program.**
 *
 * This is the artifact `DESIGN-THE-SYSTEM-STRUCTURE` §2 calls emitted-and-never-edited.
 * In cycle 1 it is HAND-WRITTEN, deliberately: write the code you want the generator to
 * emit before writing the generator. A template factored out of one working wiring
 * program beats a template derived from a spec read, and this file is the specimen.
 *
 * What is composition-specific and would be filled from `PLAN.json`:
 *   - the import list and the `install*` calls, one per entry in `install_order`
 *   - nothing else. The CLI, the readiness line and the teardown are the LANGUAGE's,
 *     not the composition's, which is why they are identical to the peer's own
 *     `test/host.ts` and why `languages/typescript/` owns them.
 *
 * The CLI is deliberately byte-compatible with keystone's `test/host.js`: the oracle's
 * harness waits on a single `LISTENING ...` line on stdout, and a composed peer that
 * spoke a different dialect would need a forked harness. Adding a composition entry
 * point BESIDE the bare-peer launcher is the whole of the integration; we are not
 * inventing a harness.
 */

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

import { Peer, PeerIdentity } from "entity-core-protocol-typescript";
import { installContent } from "@entity-core/extension-content";

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

  // ── The composition. PLAN.json install_order = ["CONTENT"]. ──────────────────
  //
  // `sdk-native`: in-process against a live Peer, because the wire register op
  // refuses `system/*` patterns (core §6.2). Not a shortcut — the only route.
  const content = installContent(peer);

  const bound = await peer.listen(port);

  process.stdout.write(
    `LISTENING 127.0.0.1:${bound} peer_id=${peer.localPeerId} open_grants=${openGrants} validate=${validate}\n`,
  );
  // A second line, on stderr so no harness parsing `LISTENING` can trip on it: what
  // the composition actually installed. A composed peer that silently installed
  // nothing looks exactly like a bare peer to everything except the failing checks.
  process.stderr.write(
    `COMPOSED extensions=CONTENT pattern=${content.pattern} types=${content.typePaths.length}\n`,
  );

  await new Promise<void>((resolve) => {
    const shutdown = (): void => resolve();
    process.once("SIGINT", shutdown);
    process.once("SIGTERM", shutdown);
  });

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
