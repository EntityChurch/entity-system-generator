/**
 * POC — does the `typescript` keystone peer's public registration seam actually
 * dispatch to a language-native handler body installed after construction?
 *
 * This is the §7d host-seam check in its smallest honest form: install through the
 * PUBLIC surface only, then assert OVER THE WIRE. Source reads settle what to
 * build; they do not settle what is true (keystone's `unknown`-until-executed
 * rule). Three source reads by two seats passed `julia` and `csharp`, both of
 * which fail this probe's class.
 *
 * The reference body returns a value NO `compute/literal` can produce: a string
 * derived from a REQUEST field concatenated with REGISTRATION-TIME captured state.
 * If the response carries it, the installed callable ran. If a peer merely wrote
 * the tree entities and fell through to the entity-native path, the value cannot
 * appear — which is the inattributability rule the check exists for.
 *
 * Both controls are required (a check that cannot go RED measures nothing):
 *   A. handler installed          → expect 200 + the derived value
 *   B. handler NOT installed      → expect non-200 (nothing at the pattern)
 *
 * Read-only against keystone: nothing here writes into another team's tree. The
 * peer is imported from its own prebuilt `dist/`, exactly as an external npm
 * consumer would resolve `entity-core-protocol-typescript`'s `exports` `.` map.
 *
 * Run:  node probe-seam.mjs [--dist <path to typescript/dist/src/index.js>]
 */

import { loadPeerUnderTest } from "./peer-under-test.mjs";

const { peer: peerPkg, entryPath, howResolved } = await loadPeerUnderTest();
const { Peer, Entity, Ecf, HandlerResult, ResourceTarget } = peerPkg;

/** Registration-time captured state — unreachable to an entity-native body. */
const REGISTRATION_NONCE = "seam-witness-7f3a";

/**
 * The reference handler. A plain object: `Handler` is an interface, so an external
 * consumer implements it structurally — which is the export-layer property that
 * `cpp` and `csharp` fail (their body type cannot be named outside the module).
 */
function referenceHandler(nonce) {
  return {
    pattern: "system/content",
    name: "content",
    operations: ["get", "ingest"],
    async handle(ctx) {
      // Derived from a request field AND registration-time state (§5 both-halves rule).
      const probe = Ecf.optText(ctx.params.data, "probe") ?? "<absent>";
      const result = Entity.create(
        "system/content/content-response",
        Ecf.map(
          ["found", Ecf.array([])],
          ["missing", Ecf.array([])],
          ["witness", Ecf.text(`${probe}:${nonce}`)],
          ["operation", Ecf.text(ctx.operation)],
          ["suffix", Ecf.text(ctx.suffix)],
          ["resource_present", Ecf.bool(ctx.resource !== null)],
          ["has_tree", Ecf.bool(typeof ctx.peer.tree?.get === "function")],
          ["has_content_store", Ecf.bool(typeof ctx.peer.contentStore?.put === "function")],
          ["has_emit", Ecf.bool(ctx.peer.emit !== undefined && ctx.peer.emit !== null)],
          ["connection_present", Ecf.bool(ctx.connection !== null)],
          ["frame_budget_reachable", Ecf.bool(findFrameBudget(ctx) !== null)],
        ),
      );
      return HandlerResult.ok(result, []);
    },
  };
}

/**
 * Can the body consult the connection's configured frame budget? CONTENT v3.6
 * Amendment 1 §6.2/§4.2 makes this a MUST ("the connection's configured budget at
 * response-construction time, NOT a hardcoded 16 MiB literal"). Probed, not assumed:
 * walk everything the body can legally see.
 */
function findFrameBudget(ctx) {
  const candidates = [
    ctx.connection,
    ctx.peer,
    ctx.peer?.transport,
    ctx,
  ];
  for (const candidate of candidates) {
    if (candidate === null || candidate === undefined) continue;
    for (const key of Object.keys(candidate)) {
      if (/frame/i.test(key) && /(max|limit|budget|bytes)/i.test(key)) {
        return { on: candidate.constructor?.name ?? "object", key };
      }
    }
  }
  return null;
}

async function runOnce({ install }) {
  const host = new Peer({ debugOpenGrants: true });
  if (install) {
    host.registerHandler(referenceHandler(REGISTRATION_NONCE));
  }
  const port = await host.listen(0);

  const client = new Peer();
  const session = await client.connect("127.0.0.1", port);

  const params = Entity.create("system/content/get-request", Ecf.map(["probe", Ecf.text("cycle-1")]));
  const response = await session.execute(
    `entity://${host.localPeerId}/system/content`,
    "get",
    params,
    new ResourceTarget(["system/content"], null),
  );

  const out = { status: response.statusCode, data: null, error: null };
  try {
    const result = response.result;
    out.type = result.type;
    if (result.type === "system/protocol/error") {
      out.error = Ecf.optText(result.data, "code");
    } else {
      out.data = Object.fromEntries(
        Ecf.entries(result.data).map(([k, v]) => {
          try {
            return [k, v.kind === "text" ? Ecf.asText(v) : v.kind === "bool" ? Ecf.asBool(v) : v.kind];
          } catch {
            return [k, v.kind];
          }
        }),
      );
    }
  } catch (err) {
    out.error = `decode: ${err instanceof Error ? err.message : String(err)}`;
  }

  await client.close?.();
  await host.close?.();
  return out;
}

// Also probe the tree state the registration surface wrote (§11.6.1 steps 1–3),
// in-process, so the probe reports WHAT the seam did rather than only that it worked.
function inspectRegistrationWrites() {
  const peer = new Peer({ debugOpenGrants: true });
  const before = {
    handler: peer.tree.isBound(`/${peer.localPeerId}/system/content`),
  };
  peer.registerHandler(referenceHandler(REGISTRATION_NONCE));
  const after = {
    handler_entity: peer.tree.isBound(`/${peer.localPeerId}/system/content`),
    interface_entity: peer.tree.isBound(`/${peer.localPeerId}/system/handler/system/content`),
    grant: peer.tree.isBound(`/${peer.localPeerId}/system/capability/grants/system/content`),
    type_blob: peer.tree.isBound(`/${peer.localPeerId}/system/type/system/content/blob`),
    type_chunk: peer.tree.isBound(`/${peer.localPeerId}/system/type/system/content/chunk`),
    type_descriptor: peer.tree.isBound(`/${peer.localPeerId}/system/type/system/content/descriptor`),
  };
  return { before, after };
}

console.log(`peer package: ${entryPath}`);
console.log(`resolved via: ${howResolved}`);
console.log(`node: ${process.version}\n`);

const writes = inspectRegistrationWrites();
console.log("§11.6.1 writes performed by the registration surface (in-process):");
for (const [k, v] of Object.entries(writes.after)) {
  console.log(`  ${v ? "yes" : "NO "}  ${k}`);
}

console.log("\nControl A — handler installed through the public seam:");
const a = await runOnce({ install: true });
console.log(`  status=${a.status} type=${a.type ?? "-"} error=${a.error ?? "-"}`);
if (a.data) {
  for (const [k, v] of Object.entries(a.data)) console.log(`    ${k} = ${v}`);
}

console.log("\nControl B — nothing installed at the pattern (must go RED):");
const b = await runOnce({ install: false });
console.log(`  status=${b.status} type=${b.type ?? "-"} error=${b.error ?? "-"}`);

const witnessOk = a.status === 200 && a.data?.witness === `cycle-1:${REGISTRATION_NONCE}`;
const negativeOk = b.status !== 200;

console.log("\nVERDICT");
console.log(`  H1 (installed body reached by dispatch):        ${witnessOk ? "MEASURED PASS" : "FAIL"}`);
console.log(`  negative control discriminates:                ${negativeOk ? "yes" : "NO — check is vacuous"}`);
console.log(`  H2 (emit reachable from the body):             ${a.data?.has_emit ? "yes" : "no"}`);
console.log(`  tree + contentStore reachable from the body:   ${a.data?.has_tree && a.data?.has_content_store ? "yes" : "no"}`);
console.log(`  CONTENT §6.2 frame budget reachable:           ${a.data?.frame_budget_reachable ? "yes" : "NO — Amendment 1 MUST unimplementable"}`);

process.exit(witnessOk && negativeOk ? 0 : 1);
