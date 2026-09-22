/**
 * Shared peer resolution for this gate's probes — the two things that make an
 * import-a-build-artifact probe honest, in one place so both probes get both.
 *
 * 1. RESOLVE THE PEER THE WAY A CONSUMER DOES. Read `exports["."]` out of the peer's
 *    own `package.json` rather than guessing `dist/src/index.js`. If the map moves, this
 *    moves with it; if the map stops publishing an entry point, that is a real H4 failure
 *    and the probe must say so instead of reaching around it into `src/`. D13's Access
 *    layer: the boundary is the manifest, not the module.
 *
 * 2. REFUSE TO MEASURE A STALE BUILD. A probe that imports `dist/` and does not check its
 *    age is a gate on the past. `entity-core-keystone` caught exactly this on their own
 *    instrument — after a planted-defect run left a mutated `dist/` on disk, their probe
 *    reported H7 unsatisfied against source that satisfied it. Adopted here before it
 *    happens to us, because both of our probes import `dist/` the same way.
 *
 * A stale build reports `unknown` and exits 2. **Exit 2 is not a verdict about the peer** —
 * it is the probe saying it could not run, which is the only honest answer available.
 */

import { readdirSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

export const DEFAULT_PEER_ROOT = resolvePath(
  HERE,
  "../../../entity-core-keystone/protocol-generator/typescript",
);

export function argValue(flag, fallback) {
  const i = process.argv.indexOf(flag);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : fallback;
}

function newestMtime(dir) {
  let newest = 0;
  const walk = (d) => {
    for (const ent of readdirSync(d, { withFileTypes: true })) {
      if (ent.name === "node_modules" || ent.name.startsWith(".")) continue;
      const full = resolvePath(d, ent.name);
      if (ent.isDirectory()) walk(full);
      else newest = Math.max(newest, statSync(full).mtimeMs);
    }
  };
  try {
    walk(dir);
  } catch {
    return null;
  }
  return newest;
}

/**
 * Resolve, freshness-check, and import the peer under test.
 * Exits 2 (`unknown`) rather than returning a verdict when it cannot honestly measure.
 */
export async function loadPeerUnderTest() {
  const peerRoot = resolvePath(argValue("--peer-root", DEFAULT_PEER_ROOT));
  const override = argValue("--dist", null);

  let entryPath;
  let howResolved;
  if (override !== null) {
    entryPath = resolvePath(override);
    howResolved = "--dist override (packaging boundary NOT exercised)";
  } else {
    const require = createRequire(import.meta.url);
    let manifest;
    try {
      manifest = require(resolvePath(peerRoot, "package.json"));
    } catch (e) {
      console.error(`unknown: no package.json under ${peerRoot} — ${e.message}`);
      process.exit(2);
    }
    const dot = manifest.exports?.["."];
    const entry = typeof dot === "string" ? dot : (dot?.import ?? dot?.default);
    if (typeof entry !== "string") {
      console.error(`unknown: package.json publishes no exports["."] entry point — that is a real H4 failure, not a probe defect`);
      process.exit(2);
    }
    entryPath = resolvePath(peerRoot, entry);
    howResolved = `package.json exports["."] -> ${entry}`;
  }

  const srcAge = newestMtime(resolvePath(peerRoot, "src"));
  const distAge = newestMtime(resolvePath(peerRoot, "dist"));
  if (srcAge === null || distAge === null) {
    console.error(`unknown: cannot compare src/ and dist/ under ${peerRoot} — build the peer first`);
    process.exit(2);
  }
  if (srcAge > distAge) {
    const behindSec = Math.round((srcAge - distAge) / 1000);
    console.error(
      `unknown: dist/ is ${behindSec}s older than src/ — this would measure a build nobody asked for.\n` +
        `         Rebuild the peer, then re-run. (Exit 2 is not a verdict about the peer.)`,
    );
    process.exit(2);
  }

  const peer = await import(entryPath);
  return { peer, entryPath, peerRoot, howResolved, distAge, srcAge };
}
