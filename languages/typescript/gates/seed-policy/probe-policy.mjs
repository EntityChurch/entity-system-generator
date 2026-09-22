/**
 * languages/typescript/gates/seed-policy/probe-policy.mjs — the `typescript` arm.
 *
 * Does a NARROW §6.9a seed policy make authorization observable on this peer, where the
 * degenerate `default -> *` posture we actually run cannot? See `gates/seed-policy/README.md`
 * for why the question is about the posture rather than about an extension.
 *
 * THREE ARMS, AND THE THIRD IS THE ONE THAT CARRIES THE ARGUMENT:
 *
 *   default -> *      permit / permit    the posture we run in -- UNDISCRIMINATING.
 *                                        This IS the negative control: D15's sharpened
 *                                        clause says the control is the absence of the
 *                                        SUBJECT, and here the subject is the narrow scope.
 *   narrow            permit / refuse    authorization is observable.
 *   discovery floor   refuse / refuse    the resource scope is genuinely READ.
 *
 * Without the floor arm, "narrow refuses" is equally well explained by a policy that refuses
 * everything, and a two-arm gate passes either way. That is D15's false green in its cheapest
 * form, so the floor arm is not optional garnish -- it is the discriminator on the
 * discriminator.
 *
 * AND A PLANTED DEFECT, because three arms agreeing is not evidence the predicate is what
 * produced them: `--self-test` replaces `checkPathPermission` with `() => true` and requires
 * the narrow arm to go RED. An instrument is not trusted until it has been seen producing the
 * other answer (D15).
 *
 * WHAT THIS DOES NOT SHOW. In-process predicate behaviour, not wire reach. A capability
 * DELIVERED by §4.6 authenticate from a declared policy is a different measurement and needs
 * a host accepting `--seed-policy`; no keystone host binary implements one
 * (`ROUTING-2026-09-11-b-keystone-the-seed-policy-replacement-reaches-no-host-binary.md` §1).
 * This arm reads on the `policy_discriminates` axis and on nothing else.
 */

import { writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = process.env.GENERATOR_ROOT ?? path.resolve(import.meta.dirname, "../../../..");
const COMP = process.env.COMP ?? "compute";
const STAGE = `${ROOT}/languages/typescript/output/${COMP}/build`;
const SELF_TEST = process.argv.includes("--self-test");

// Resolve THROUGH the packaging boundary the way a consumer does, not by guessing a path into
// someone's build output (`gates/README.md`). ESM resolves a bare specifier relative to the
// importing file, so the import has to happen from inside the stage -- which is a write into
// the thing we are measuring, hence D19's reserved `gate-probe-*` prefix. `tools/gate-stage`
// excludes it from the staleness scan and `tools/check-structure.py` FAILS any other name.
const LOADER = `${STAGE}/gate-probe-seed-policy-loader.mjs`;
let peerMod;
try {
  writeFileSync(LOADER, 'export * from "entity-core-protocol-typescript";\n');
  peerMod = await import(pathToFileURL(LOADER).href);
} catch (err) {
  // VACUITY REFUSAL #1 -- no stage. A gate that silently skips when its subject is missing
  // reports a clean verdict over nothing measured, which is the state it will actually be in
  // the day it breaks.
  console.error(`REFUSING: cannot load the peer from ${STAGE}: ${err.message}`);
  console.error(`  run: make build TARGET=typescript COMPOSITION=${COMP}`);
  process.exit(2);
}

const { Peer, PeerIdentity, SeedPolicy, GrantEntry, Scope, CapabilityToken, Permissions } = peerMod;

// VACUITY REFUSAL #2 -- the surface this arm exists to exercise. On a peer whose seed policy
// is a BOOLEAN there is no narrow policy to construct and the honest output is a refusal, not
// two green arms. `python` and `rust` are in exactly that state today (keystone K-7).
for (const [name, sym] of [["SeedPolicy", SeedPolicy], ["GrantEntry", GrantEntry], ["Scope", Scope]]) {
  if (typeof sym !== "function") {
    console.error(`REFUSING: the peer exports no \`${name}\` -- a seed policy is not a value on`);
    console.error("  this substrate, so the narrow arm has nothing to construct. Two arms is");
    console.error("  not a verdict on a three-arm question.");
    process.exit(2);
  }
}
if (typeof SeedPolicy.of !== "function") {
  console.error("REFUSING: `SeedPolicy.of` is absent -- only the canned policies are");
  console.error("  constructible, so an arbitrary narrow policy cannot be expressed.");
  process.exit(2);
}

const identity = PeerIdentity.fromSeed(new Uint8Array(32).fill(0x11));
const peerId = new Peer({ identity }).localPeerId;

// The A-17 shape: one subtree granted, so a read one function-argument deep into a DIFFERENT
// subtree is precisely what §3.3 Phase 2 must refuse and what `default -> *` cannot.
const IN = `/${peerId}/app/allowed/x`;
const OUT = `/${peerId}/app/secret/x`;

const narrow = SeedPolicy.of([
  new GrantEntry(
    new Scope(["system/tree"], null),
    new Scope([`/${peerId}/app/allowed/*`], null),
    new Scope(["get"], null),
    null, null, null,
  ),
]);

// The planted defect: a predicate that authorizes everything. This is what an extension that
// never really checks looks like from the outside, and the narrow arm is the only one of the
// three whose verdict moves when it is installed.
const check = SELF_TEST
  ? () => true
  : (op, p, tok) => Permissions.checkPathPermission(op, p, tok, "system/tree", peerId);

function arm(grants, label) {
  const { token } = CapabilityToken.createRoot(identity, identity.identityHash, grants, 0n);
  const inScope = check("get", IN, token);
  const outScope = check("get", OUT, token);
  console.log(`  ${label.padEnd(24)} in-scope=${String(inScope).padEnd(5)} out-of-scope=${outScope}`);
  return { inScope, outScope };
}

console.log(`seed-policy [typescript] peer_id=${peerId}${SELF_TEST ? "  (SELF-TEST: predicate planted as `() => true`)" : ""}`);
console.log(`  IN  = ${IN}`);
console.log(`  OUT = ${OUT}`);

const open = arm(SeedPolicy.openGrants(), "default -> * (deprecated)");
const narr = arm(narrow.defaultGrants, "narrow (app/allowed/*)");
const floor = arm(SeedPolicy.discoveryFloor(), "discovery floor");
console.log();

const undiscriminating = open.inScope === true && open.outScope === true;
const discriminates = narr.inScope === true && narr.outScope === false;
const scopeIsRead = floor.inScope === false && floor.outScope === false;

const rows = [
  ["the posture we run is UNDISCRIMINATING", undiscriminating],
  ["a narrow policy DISCRIMINATES", discriminates],
  ["the resource scope is READ (floor refuses both)", scopeIsRead],
];
for (const [label, ok] of rows) console.log(`  ${ok ? "ok  " : "FAIL"}  ${label}`);

const pass = undiscriminating && discriminates && scopeIsRead;

if (SELF_TEST) {
  // The control must move the NARROW arm and only it: `default -> *` already permits both, so
  // a planted `() => true` is invisible there. An instrument whose control reddens the arm
  // that was already green has not been controlled.
  console.log();
  if (discriminates) {
    console.error("SELF-TEST FAILED: the narrow arm still discriminates with the predicate");
    console.error("  planted as `() => true` -- the verdict is not coming from the predicate.");
    process.exit(1);
  }
  if (!undiscriminating) {
    console.error("SELF-TEST FAILED: the `default -> *` arm moved. It should be INSENSITIVE to");
    console.error("  the plant -- it permits both paths either way, which is the whole point.");
    process.exit(1);
  }
  console.log("SELF-TEST OK -- the plant reddens the narrow arm and leaves `default -> *` alone.");
  process.exit(0);
}

console.log();
if (!pass) {
  console.error("SEED-POLICY: FAIL -- see the rows above.");
  process.exit(1);
}
console.log("SEED-POLICY: OK -- authorization is observable on this peer under a narrow");
console.log("  declared policy, and is NOT observable under the one we launch with.");
console.log("  Axis: policy_discriminates. In-process; says nothing about wire reach.");
