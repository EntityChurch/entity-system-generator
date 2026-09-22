/**
 * POC — how far does the ENTITY-NATIVE handler path actually reach on a keystone peer?
 *
 * `SDK-OPERATIONS` §11.3 names three handler execution models. Model 3 — the body is a
 * compute expression in the tree, dispatched through `expression_path` per
 * `ENTITY-CORE-PROTOCOL` §6.13(a) / §6.6 — is the one every peer in the cohort appears
 * to support, because every hardcoded peer ends its dispatch switch on that path. If it
 * really works, an extension written ONCE as a compute expression runs on 46 peers and
 * the language axis collapses. That is the theory this probe exists to settle.
 *
 * A source read of `typescript`'s `Dispatcher.#runEntityNative` says the evaluator is
 * hardcoded to `compute/literal` and answers `501 unsupported_expression` for anything
 * richer. Source reads decide what to build; they never decide what is true (D13). So:
 * execute it, with controls, and also test whether INSTALLING an evaluator at
 * `system/compute/*` changes the answer — because if it does not, the compute extension
 * cannot be reached from the dispatch path at all, and model 3 has a host-contract gap
 * nobody has written down.
 *
 * Four controls. Every one is required; a check that cannot go RED measures nothing.
 *
 *   A. entity-native body = `compute/literal{value:42}`   → does the seam work at all?
 *   B. entity-native body = `compute/arithmetic{add,2,3}` → does it evaluate anything richer?
 *   C. `system/compute` handler installed, then re-run B  → does dispatch DELEGATE to it?
 *   D. that same `system/compute` handler called directly → is it actually installed and live?
 *
 * D is C's positive control and the reason C is attributable: without it, a failure in C
 * could be "the evaluator was never installed" rather than "the dispatcher never asks."
 *
 * Read-only against keystone. The peer is imported from its own prebuilt `dist/`, exactly
 * as an external npm consumer resolves the `exports` `.` map. Expression entities are
 * written in-process, which is the position a generated composition program occupies.
 *
 * Run:  node probe-entity-native.mjs [--dist <path to typescript/dist/src/index.js>]
 */

import { loadPeerUnderTest } from "./peer-under-test.mjs";

const { peer: peerPkg, entryPath, howResolved } = await loadPeerUnderTest();
const { Peer, Entity, Ecf, HandlerResult, ResourceTarget, TypeNames } = peerPkg;

/** Non-reserved patterns: §6.2 forbids a wire-installed handler at `system/*`. */
const LITERAL_PATTERN = "app/probe/en-literal";
const ARITH_PATTERN = "app/probe/en-arith";

const EXPR_LITERAL = "app/probe/expr/lit";
const EXPR_TWO = "app/probe/expr/two";
const EXPR_THREE = "app/probe/expr/three";
const EXPR_ARITH = "app/probe/expr/arith";

/** The evaluator stand-in for the compute extension, installed language-natively. */
const COMPUTE_WITNESS = "compute-evaluator-was-asked";

function computeEvaluatorHandler(seen) {
  return {
    pattern: "system/compute",
    name: "compute",
    operations: ["eval", "install", "uninstall"],
    async handle(ctx) {
      seen.push(ctx.operation);
      const result = Entity.create(
        "compute/result",
        Ecf.map(["value", Ecf.text(COMPUTE_WITNESS)], ["operation", Ecf.text(ctx.operation)]),
      );
      return HandlerResult.ok(result, []);
    },
  };
}

/** Bind the expression graph a model-3 body needs, in the position the loader occupies. */
function seedExpressions(peer) {
  const abs = (rel) => `/${peer.localPeerId}/${rel}`;

  const lit42 = Entity.create("compute/literal", Ecf.map(["value", Ecf.uint(42n)]));
  const two = Entity.create("compute/literal", Ecf.map(["value", Ecf.uint(2n)]));
  const three = Entity.create("compute/literal", Ecf.map(["value", Ecf.uint(3n)]));
  const arith = Entity.create(
    "compute/arithmetic",
    Ecf.map(
      ["op", Ecf.text("add")],
      ["left", Ecf.bytes(two.contentHash)],
      ["right", Ecf.bytes(three.contentHash)],
    ),
  );

  peer.tree.put(abs(EXPR_LITERAL), lit42);
  peer.tree.put(abs(EXPR_TWO), two);
  peer.tree.put(abs(EXPR_THREE), three);
  peer.tree.put(abs(EXPR_ARITH), arith);

  for (const e of [lit42, two, three, arith]) {
    EXPR_BY_HASH.set(Buffer.from(e.contentHash).toString("hex"), e);
  }
}

/** Wire `system/handler:register` with an `expression_path` — the model-3 install. */
async function registerEntityNative(session, hostPeerId, pattern, expressionPath) {
  const manifest = Ecf.map(
    ["name", Ecf.text(pattern)],
    [
      "operations",
      Ecf.map([
        "compute",
        Ecf.map(["input_type", Ecf.text("primitive/any")], ["output_type", Ecf.text("primitive/any")]),
      ]),
    ],
    ["expression_path", Ecf.text(expressionPath)],
  );
  const req = Entity.create(TypeNames.HandlerRegisterRequest, Ecf.map(["manifest", manifest]));

  return session.execute(
    `entity://${hostPeerId}/system/handler`,
    "register",
    req,
    new ResourceTarget([`system/handler/${pattern}`], null),
  );
}

function summarize(response) {
  const out = { status: response.statusCode, type: null, code: null, message: null, value: null };
  try {
    const result = response.result;
    out.type = result.type;
    if (result.type === "system/protocol/error") {
      out.code = Ecf.optText(result.data, "code");
      out.message = Ecf.optText(result.data, "message");
    } else {
      const v = Ecf.field(result.data, "value");
      if (v !== null) {
        try {
          out.value = v.kind === "text" ? Ecf.asText(v) : String(Ecf.asUint(v));
        } catch {
          out.value = v.kind;
        }
      }
    }
  } catch (err) {
    out.message = `decode: ${err instanceof Error ? err.message : String(err)}`;
  }
  return out;
}

/**
 * A real evaluator installed through the H7 seam. It answers `compute/arithmetic` with
 * an actually-computed sum — **derived from the expression graph in the tree**, not a
 * constant — so a peer that routed to the evaluator and a peer that happened to answer
 * `200` some other way are distinguishable. It declines everything else with `null`,
 * which is the seam's documented compose semantics.
 */
function expressionEvaluator(peer, seen) {
  return {
    evaluate({ expression, expressionPath }) {
      seen.push(`evaluate:${expression.type}`);
      if (expression.type !== "compute/arithmetic") return null; // not mine — peer's 501 stands
      const op = Ecf.asText(Ecf.require(expression.data, "op"));
      const operand = (key) => {
        const hash = Ecf.asBytes(Ecf.require(expression.data, key));
        const hex = Buffer.from(hash).toString("hex");
        const ent = peer.contentStore?.get(hash) ?? EXPR_BY_HASH.get(hex);
        return Ecf.asUint(Ecf.require(ent.data, "value"));
      };
      if (op !== "add") return null;
      const sum = operand("left") + operand("right");
      const result = Entity.create(
        "compute/result",
        Ecf.map(["value", Ecf.uint(sum)], ["expression_path", Ecf.text(expressionPath)]),
      );
      return HandlerResult.ok(result, []);
    },
  };
}

/** Hash → expression entity, so the evaluator can resolve operands it was handed by hash. */
const EXPR_BY_HASH = new Map();

async function scenario({ installEvaluator, installSeam }) {
  const seen = [];
  const seamSeen = [];
  const host = new Peer({ debugOpenGrants: true });
  seedExpressions(host);
  if (installEvaluator) {
    host.registerHandler(computeEvaluatorHandler(seen));
  }
  if (installSeam) {
    if (typeof host.setExpressionEvaluator !== "function") {
      throw new Error("peer has no setExpressionEvaluator — H7 seam absent, rerun without --seam");
    }
    host.setExpressionEvaluator(expressionEvaluator(host, seamSeen));
  }
  const port = await host.listen(0);

  const client = new Peer();
  const session = await client.connect("127.0.0.1", port);

  const reg = {
    literal: summarize(await registerEntityNative(session, host.localPeerId, LITERAL_PATTERN, EXPR_LITERAL)),
    arith: summarize(await registerEntityNative(session, host.localPeerId, ARITH_PATTERN, EXPR_ARITH)),
  };

  const params = Entity.create(TypeNames.PrimitiveAny, Ecf.emptyMap());
  const dispatch = {
    literal: summarize(
      await session.execute(
        `entity://${host.localPeerId}/${LITERAL_PATTERN}`,
        "compute",
        params,
        new ResourceTarget([LITERAL_PATTERN], null),
      ),
    ),
    arith: summarize(
      await session.execute(
        `entity://${host.localPeerId}/${ARITH_PATTERN}`,
        "compute",
        params,
        new ResourceTarget([ARITH_PATTERN], null),
      ),
    ),
  };

  // Snapshot BEFORE control D runs: D invokes the evaluator itself, so counting
  // invocations afterwards would report D's own call as evidence of delegation.
  const seenViaDispatch = seen.slice();

  let direct = null;
  if (installEvaluator) {
    direct = summarize(
      await session.execute(
        `entity://${host.localPeerId}/system/compute`,
        "eval",
        params,
        new ResourceTarget([EXPR_ARITH], null),
      ),
    );
  }

  await client.dispose?.();
  await host.dispose?.();
  return { reg, dispatch, direct, seen, seenViaDispatch, seamSeen };
}

function line(label, s) {
  const detail = s.code !== null ? `${s.code}` : s.value !== null ? `value=${s.value}` : (s.type ?? "-");
  console.log(`  ${label.padEnd(46)} status=${String(s.status).padEnd(4)} ${detail}`);
}

console.log(`peer package: ${entryPath}`);
console.log(`resolved via: ${howResolved}`);
console.log(`node: ${process.version}\n`);

console.log("=== Scenario 1 — no evaluator installed ===");
const s1 = await scenario({ installEvaluator: false });
console.log(" register (must succeed, else nothing below is attributable):");
line("register literal-bodied handler", s1.reg.literal);
line("register arithmetic-bodied handler", s1.reg.arith);
console.log(" dispatch:");
line("A. body = compute/literal{42}", s1.dispatch.literal);
line("B. body = compute/arithmetic{add,2,3}", s1.dispatch.arith);

console.log("\n=== Scenario 2 — a language-native evaluator installed at system/compute ===");
const s2 = await scenario({ installEvaluator: true });
console.log(" dispatch:");
line("C. body = compute/arithmetic{add,2,3}", s2.dispatch.arith);
line("D. system/compute:eval called directly", s2.direct);
console.log(`  evaluator invoked BY DISPATCH (C):     ${s2.seenViaDispatch.length ? s2.seenViaDispatch.join(", ") : "(none — never asked)"}`);
console.log(`  evaluator invoked in total (C + D):     ${s2.seen.length ? s2.seen.join(", ") : "(none)"}`);

const seamPresent = typeof new Peer({ debugOpenGrants: true }).setExpressionEvaluator === "function";
let s3 = null;
if (seamPresent) {
  console.log("\n=== Scenario 3 — an evaluator installed through the H7 seam ===");
  s3 = await scenario({ installEvaluator: false, installSeam: true });
  console.log(" dispatch:");
  line("E. body = compute/arithmetic{add,2,3}", s3.dispatch.arith);
  line("F. body = compute/literal{42} (floor)", s3.dispatch.literal);
  console.log(`  evaluator invoked by dispatch:         ${s3.seamSeen.length ? s3.seamSeen.join(", ") : "(none — never asked)"}`);
} else {
  console.log("\n=== Scenario 3 — SKIPPED: this peer has no setExpressionEvaluator (H7 absent) ===");
}

const registerOk = s1.reg.literal.status === 200 && s1.reg.arith.status === 200;
const literalWorks = s1.dispatch.literal.status === 200 && s1.dispatch.literal.value === "42";
const arithWorks = s1.dispatch.arith.status === 200;
const evaluatorLive = s2.direct?.status === 200 && s2.direct?.value === COMPUTE_WITNESS;
const delegatesToHandler = s2.dispatch.arith.status === 200 || s2.seenViaDispatch.length > 0;
// The witness is the computed sum, which no constant-returning body and no
// compute/literal floor can produce: 2 + 3 read out of the tree.
const seamWorks = s3 !== null && s3.dispatch.arith.status === 200 && s3.dispatch.arith.value === "5";
// The built-in floor must be UNAFFECTED by an installed evaluator — that ordering is
// the whole reason installing one cannot move a conformance result.
const floorIntact = s3 === null || (s3.dispatch.literal.status === 200 && s3.dispatch.literal.value === "42");
const floorNotIntercepted = s3 === null || !s3.seamSeen.some((s) => s.endsWith("compute/literal"));

console.log("\nVERDICT");
console.log(`  register accepted an entity-native manifest:      ${registerOk ? "yes" : "NO — probe is vacuous"}`);
console.log(`  model 3 reaches a compute/literal body:           ${literalWorks ? "MEASURED yes" : "no"}`);
console.log(`  built-in floor alone reaches compute/arithmetic:  ${arithWorks ? "yes" : `NO — ${s1.dispatch.arith.status} ${s1.dispatch.arith.code} (expected)`}`);
console.log(`  a handler at system/compute IS the seam:          ${delegatesToHandler ? "yes" : "NO — and it should not be; see E"}`);
console.log(`    (that handler was live and directly callable:   ${evaluatorLive ? "yes, control D" : "NO — control C not attributable"})`);
console.log(`  H7 — an evaluator installed through the seam:     ${!seamPresent ? "ABSENT — no setExpressionEvaluator" : seamWorks ? "MEASURED PASS — 200, value=5 computed from the tree" : `FAIL — ${s3.dispatch.arith.status} ${s3.dispatch.arith.code}`}`);
console.log(`  the compute/literal floor is unaffected by it:    ${floorIntact && floorNotIntercepted ? "yes — answered first, evaluator never consulted" : "NO — an installed evaluator moved the floor"}`);
console.log("");
console.log(
  seamWorks && floorIntact && floorNotIntercepted
    ? "  => H7 SATISFIED ON THIS PEER, BY EXECUTION. Model 3 is delegable: a body the\n" +
        "     built-in path refuses is routed to an installed evaluator, and the floor the\n" +
        "     cohort's register round-trip depends on is untouched. Extensions may now ship\n" +
        "     their own compute semantics on this peer."
    : seamPresent
      ? "  => the H7 seam is present but did not behave as contracted; read the rows above."
      : "  => H7 ABSENT on this peer: model 3 means compute/literal and nothing else.",
);

// Exit 0 when every control behaved — the probe's own integrity, not the peer's verdict.
// Scenario 3 only gates the exit when the seam exists to measure.
process.exit(registerOk && literalWorks && evaluatorLive && (!seamPresent || (seamWorks && floorIntact && floorNotIntercepted)) ? 0 : 1);
