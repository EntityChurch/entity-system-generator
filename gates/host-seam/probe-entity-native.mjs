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

import { dirname, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

const DEFAULT_DIST = resolvePath(
  HERE,
  "../../../entity-core-keystone/protocol-generator/typescript/dist/src/index.js",
);

function argValue(flag, fallback) {
  const i = process.argv.indexOf(flag);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : fallback;
}

const distPath = resolvePath(argValue("--dist", DEFAULT_DIST));

const { Peer, Entity, Ecf, HandlerResult, ResourceTarget, TypeNames } = await import(distPath);

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

async function scenario({ installEvaluator }) {
  const seen = [];
  const host = new Peer({ debugOpenGrants: true });
  seedExpressions(host);
  if (installEvaluator) {
    host.registerHandler(computeEvaluatorHandler(seen));
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
  return { reg, dispatch, direct, seen, seenViaDispatch };
}

function line(label, s) {
  const detail = s.code !== null ? `${s.code}` : s.value !== null ? `value=${s.value}` : (s.type ?? "-");
  console.log(`  ${label.padEnd(46)} status=${String(s.status).padEnd(4)} ${detail}`);
}

console.log(`peer package: ${distPath}`);
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

const registerOk = s1.reg.literal.status === 200 && s1.reg.arith.status === 200;
const literalWorks = s1.dispatch.literal.status === 200 && s1.dispatch.literal.value === "42";
const arithWorks = s1.dispatch.arith.status === 200;
const evaluatorLive = s2.direct?.status === 200 && s2.direct?.value === COMPUTE_WITNESS;
const delegates = s2.dispatch.arith.status === 200 || s2.seenViaDispatch.length > 0;

console.log("\nVERDICT");
console.log(`  register accepted an entity-native manifest:      ${registerOk ? "yes" : "NO — probe is vacuous"}`);
console.log(`  model 3 reaches a compute/literal body:           ${literalWorks ? "MEASURED yes" : "no"}`);
console.log(`  model 3 reaches a compute/arithmetic body:        ${arithWorks ? "MEASURED yes" : `NO — ${s1.dispatch.arith.status} ${s1.dispatch.arith.code}`}`);
console.log(`  installed evaluator is live and reachable:        ${evaluatorLive ? "yes (control D)" : "NO — control C is not attributable"}`);
console.log(`  dispatch DELEGATES to the installed evaluator:    ${delegates ? "yes" : "NO — the evaluator is never asked"}`);
console.log("");
console.log(
  !arithWorks && evaluatorLive && !delegates
    ? "  => H7 MEASURED ON THIS PEER: the entity-native evaluator is not delegable.\n" +
        "     Installing EXTENSION-COMPUTE does not widen the model-3 body language.\n" +
        "     Model 3 on this peer means compute/literal and nothing else."
    : "  => read the rows above; the H7 shape did not reproduce as stated.",
);

// Exit 0 when every control behaved (including the negatives) — the probe's own
// integrity, not the peer's verdict. A vacuous run must not read as green.
process.exit(registerOk && literalWorks && evaluatorLive ? 0 : 1);
