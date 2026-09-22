/**
 * §4 — the evaluation algorithm, exercised through the PUBLIC surface.
 *
 * These tests reach `ComputeEvaluator`, not `internal/evaluator.js`, and that is the
 * same argument `export-surface.test.ts` makes from the other side: if the evaluator
 * can only be driven through the SDK face, then the SDK face is exercised by every
 * test here, which is what `DESIGN-THE-SDK-LAYER` §1.1a means by *the extension is
 * the instrument*.
 *
 * **WHAT THESE ARE FOR, AND WHAT THEY ARE NOT.** They are not a conformance claim —
 * that is `entity-core-go`'s `compute` category, 128 checks, and the standing rule is
 * that an official green requires the suite we do not author. These cover the clauses
 * where §4.1 says something a reasonable implementation would get wrong, and each one
 * names which clause and why it is not obvious.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ContentStore,
  Ecf,
  Entity,
  EntityTree,
  codec,
} from "entity-core-protocol-typescript";

import {
  ARITHMETIC, COMPARE, CONSTRUCT, ERROR, FIELD, IF, INDEX, LAMBDA, LENGTH, LET,
  LITERAL, LOGIC, LOOKUP_HASH, LOOKUP_SCOPE, LOOKUP_TREE, NUMERIC_CAST, APPLY, CLOSURE,
  RESULT, SCOPE,
  ComputeEvaluator,
  isComputeExpression,
  isComputeType,
  computeTypeDefs,
} from "@entity-core/extension-compute";

const PEER = "z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH";

/**
 * A peer stand-in carrying exactly the three members the SDK's interface names.
 *
 * `EntityTree` takes the content store as a constructor argument — the tree is
 * `path -> hash` and the store is what a hash resolves through, which is the first of
 * this ecosystem's five load-bearing invariants. Building the two independently would
 * give a tree whose `get` cannot see anything the evaluator wrote.
 */
function services(): { tree: EntityTree; contentStore: ContentStore; localPeerId: string } {
  const contentStore = new ContentStore();
  return { tree: new EntityTree(contentStore), contentStore, localPeerId: PEER };
}

/** Store an entity and return the hash the parent expression references it by. */
function put(cs: ContentStore, e: Entity): Uint8Array {
  cs.put(e);
  return e.contentHash;
}

function literal(cs: ContentStore, value: codec.EcfValue): Uint8Array {
  return put(cs, Entity.create(LITERAL, Ecf.map(["value", value])));
}

function uint(n: number | bigint): codec.EcfValue {
  return codec.ecfInt(BigInt(n));
}

/** Evaluate `expr` and return the outcome, with the root at a fixed path. */
function run(
  peer: ReturnType<typeof services>,
  expr: Entity,
  options: Parameters<ComputeEvaluator["evaluateAt"]>[2] = {},
) {
  return new ComputeEvaluator(peer).evaluateAt(expr, "/" + PEER + "/app/expr", options);
}

/**
 * Read an int out of an evaluated value.
 *
 * The failure message uses `node?.kind` rather than `JSON.stringify(v)`, and that is
 * not a style choice: the value model carries integers as `bigint` (R1/F7 — `number`
 * is exact only to 2^53 and the protocol carries u64), and `JSON.stringify` THROWS on
 * a BigInt. The first draft of this helper built its message eagerly, so every call
 * threw inside the assertion instead of asserting — ten tests reported a TypeError
 * from the harness and none of them reported what the evaluator did. AP-3's shape in
 * our own test helper: a check that cannot reach its own assertion.
 */
function intOf(v: unknown): bigint {
  const node = v as codec.EcfInt;
  assert.equal(node?.kind, "int", `expected an int, got kind=${String((v as { kind?: string })?.kind)}`);
  return codec.ecfIntValue(node);
}

function boolOf(v: unknown): boolean {
  const node = v as { kind: string; value: boolean };
  assert.equal(node.kind, "bool");
  return node.value;
}

// ── §2.1 / §4.1 — the core forms ────────────────────────────────────────────────

test("§4.1: a literal evaluates to its value", () => {
  const peer = services();
  const out = run(peer, Entity.create(LITERAL, Ecf.map(["value", uint(42)])));
  assert.equal(out.error, null);
  assert.equal(intOf(out.value), 42n);
});

test("§4.1: arithmetic reads operands through hash references", () => {
  const peer = services();
  const expr = Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("add")],
    ["left", Ecf.bytes(literal(peer.contentStore, uint(2)))],
    ["right", Ecf.bytes(literal(peer.contentStore, uint(3)))],
  ));
  const out = run(peer, expr);
  assert.equal(out.error, null);
  assert.equal(intOf(out.value), 5n);
});

test("§4.1 div: an EXACT integer quotient stays an integer, an inexact one promotes", () => {
  // The three-behaviour operator. A port that always promotes passes every test whose
  // operands happen to divide evenly.
  const peer = services();
  const div = (a: number, b: number) => run(peer, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("div")],
    ["left", Ecf.bytes(literal(peer.contentStore, uint(a)))],
    ["right", Ecf.bytes(literal(peer.contentStore, uint(b)))],
  )));

  const exact = div(6, 3);
  assert.equal(exact.error, null);
  assert.equal((exact.value as codec.EcfInt).kind, "int", "6/3 must stay an integer");
  assert.equal(intOf(exact.value), 2n);

  const inexact = div(7, 2);
  assert.equal(inexact.error, null);
  assert.equal((inexact.value as codec.EcfFloat).kind, "float", "7/2 must promote to float");
  assert.equal((inexact.value as codec.EcfFloat).value, 3.5);
});

test("§4.1 div: INTEGER division by zero is an error; FLOAT division by zero is IEEE-754", () => {
  // §4.1's ladder, and the half that is easy to miss. `1.0 / 0` is `Infinity` and is
  // NOT `division_by_zero` — reading the two branches as one produces a port that
  // errors where the corpus expects a value.
  const peer = services();
  const intDiv = run(peer, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("div")],
    ["left", Ecf.bytes(literal(peer.contentStore, uint(1)))],
    ["right", Ecf.bytes(literal(peer.contentStore, uint(0)))],
  )));
  assert.equal(intDiv.error?.code, "division_by_zero");

  const floatDiv = run(peer, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("div")],
    ["left", Ecf.bytes(literal(peer.contentStore, codec.ecfFloat(1)))],
    ["right", Ecf.bytes(literal(peer.contentStore, uint(0)))],
  )));
  assert.equal(floatDiv.error, null, "float division by zero is a value, not an error");
  assert.equal((floatDiv.value as codec.EcfFloat).value, Infinity);
});

test("§4.1 mod: TRUNCATED remainder, which differs from a floored one in sign", () => {
  // `truncated_remainder(a, b) = a - trunc(a/b)*b`. For (-7, 2) that is -1; a floored
  // `%` gives +1. Python's operator is floored, so this is the exact place the second
  // port diverges silently if it reaches for the language's own `%`.
  const peer = services();
  const out = run(peer, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("mod")],
    ["left", Ecf.bytes(literal(peer.contentStore, codec.ecfInt(-7n)))],
    ["right", Ecf.bytes(literal(peer.contentStore, uint(2)))],
  )));
  assert.equal(out.error, null);
  assert.equal(intOf(out.value), -1n, "truncated remainder of -7 mod 2 is -1, not 1");
});

test("§4.1 compare: eq across type classes is FALSE, not a type_mismatch", () => {
  // Only the four ORDERING ops demand compatible operands. `eq`/`neq` accept anything.
  const peer = services();
  const out = run(peer, Entity.create(COMPARE, Ecf.map(
    ["op", Ecf.text("eq")],
    ["left", Ecf.bytes(literal(peer.contentStore, uint(1)))],
    ["right", Ecf.bytes(literal(peer.contentStore, Ecf.text("1")))],
  )));
  assert.equal(out.error, null, "eq across type classes must not error");
  assert.equal(boolOf(out.value), false);
});

test("§4.1 compare: ordering across type classes IS a type_mismatch", () => {
  const peer = services();
  const out = run(peer, Entity.create(COMPARE, Ecf.map(
    ["op", Ecf.text("lt")],
    ["left", Ecf.bytes(literal(peer.contentStore, uint(1)))],
    ["right", Ecf.bytes(literal(peer.contentStore, Ecf.text("a")))],
  )));
  assert.equal(out.error?.code, "type_mismatch");
});

test("§4.1 compare: string ordering is UTF-8 BYTE order, not UTF-16 code units", () => {
  // The one case where JavaScript's own `<` gives the wrong answer. U+1D400 encodes to
  // f0 9d 90 80 in UTF-8 (first byte 0xF0) and to a surrogate pair D835 DC00 in UTF-16
  // (first unit 0xD835). Against U+FFFD (ef bf bd / FFFD) the two orders DISAGREE.
  const peer = services();
  const cmp = (a: string, b: string) => run(peer, Entity.create(COMPARE, Ecf.map(
    ["op", Ecf.text("lt")],
    ["left", Ecf.bytes(literal(peer.contentStore, Ecf.text(a)))],
    ["right", Ecf.bytes(literal(peer.contentStore, Ecf.text(b)))],
  )));
  const out = cmp("\u{1D400}", "�");
  assert.equal(out.error, null);
  // UTF-8 bytes: f0... vs ef... -> "\u{1D400}" is GREATER. UTF-16 units: D835 vs FFFD
  // -> JavaScript would say LESS. The assertion is the byte answer.
  assert.equal(boolOf(out.value), false, "UTF-8 byte order puts U+1D400 after U+FFFD");
  assert.equal("\u{1D400}" < "�", true, "and JS string < disagrees, which is the point");
});

test("§4.1 logic: `not` returns before `right` is resolved", () => {
  // `right` is optional on the type precisely so a `not` can omit it. Resolving it
  // first would turn a well-formed `not` into a `not_found`.
  const peer = services();
  const out = run(peer, Entity.create(LOGIC, Ecf.map(
    ["op", Ecf.text("not")],
    ["left", Ecf.bytes(literal(peer.contentStore, Ecf.bool(false)))],
  )));
  assert.equal(out.error, null);
  assert.equal(boolOf(out.value), true);
});

test("§4.5 truthiness: null, false, 0, empty string and empty array are falsy", () => {
  const peer = services();
  const falsy: codec.EcfValue[] = [
    codec.ecfNull(), Ecf.bool(false), uint(0), Ecf.text(""), Ecf.array([]),
  ];
  for (const v of falsy) {
    const out = run(peer, Entity.create(IF, Ecf.map(
      ["condition", Ecf.bytes(literal(peer.contentStore, v))],
      ["then", Ecf.bytes(literal(peer.contentStore, Ecf.text("T")))],
      ["else", Ecf.bytes(literal(peer.contentStore, Ecf.text("F")))],
    )));
    assert.equal(out.error, null);
    // `v.kind`, not `JSON.stringify(v)` — the value model carries integers as bigint
    // and JSON.stringify throws on one. Second instance in this file of the same
    // harness defect; the first was `intOf`.
    assert.equal((out.value as codec.EcfText).value, "F", `${v.kind} should be falsy`);
  }
});

test("§4.1 if: a falsy condition with NO else branch returns null, not an error", () => {
  const peer = services();
  const out = run(peer, Entity.create(IF, Ecf.map(
    ["condition", Ecf.bytes(literal(peer.contentStore, Ecf.bool(false)))],
    ["then", Ecf.bytes(literal(peer.contentStore, Ecf.text("T")))],
  )));
  assert.equal(out.error, null);
  assert.equal((out.value as { kind: string }).kind, "null");
});

test("§4.1 let: bindings are SEQUENTIAL — a later one sees an earlier one", () => {
  // §4.1's own comment calls it Scheme's `let*`. Evaluating each binding in the OUTER
  // scope instead is a different language that passes every single-binding test.
  const peer = services();
  const x = literal(peer.contentStore, uint(2));
  const lookupX = put(peer.contentStore, Entity.create(LOOKUP_SCOPE, Ecf.map(["name", Ecf.text("x")])));
  const lookupY = put(peer.contentStore, Entity.create(LOOKUP_SCOPE, Ecf.map(["name", Ecf.text("y")])));

  const out = run(peer, Entity.create(LET, Ecf.map(
    ["bindings", Ecf.array([
      Ecf.map(["name", Ecf.text("x")], ["value", Ecf.bytes(x)]),
      Ecf.map(["name", Ecf.text("y")], ["value", Ecf.bytes(lookupX)]),
    ])],
    ["body", Ecf.bytes(lookupY)],
  )));
  assert.equal(out.error, null);
  assert.equal(intOf(out.value), 2n, "y must see the binding x made in the same let");
});

test("§4.1 lookup/scope: a missing name is not_found and does NOT fall through to the tree", () => {
  // §2.1 is explicit: lookup/scope is strictly scope-local. A fallthrough would make a
  // typo in a binding name silently read an entity.
  const peer = services();
  peer.tree.put("/" + PEER + "/nope", Entity.create(LITERAL, Ecf.map(["value", uint(9)])));
  const out = run(peer, Entity.create(LOOKUP_SCOPE, Ecf.map(["name", Ecf.text("nope")])));
  assert.equal(out.error?.code, "not_found");
});

test("§2.1 lookup/tree: a stored EXPRESSION evaluates; a stored VALUE is returned as-is", () => {
  // The spreadsheet semantic, and its exception. A `compute/closure` at a tree path is
  // a VALUE and must come back unevaluated — §2.1 says so in the lookup/tree note.
  const peer = services();
  const exprPath = "/" + PEER + "/app/formula";
  peer.tree.put(exprPath, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("add")],
    ["left", Ecf.bytes(literal(peer.contentStore, uint(20)))],
    ["right", Ecf.bytes(literal(peer.contentStore, uint(22)))],
  )));
  const viaExpr = run(peer, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text("app/formula")])));
  assert.equal(viaExpr.error, null);
  assert.equal(intOf(viaExpr.value), 42n, "a stored expression is evaluated");

  const closurePath = "/" + PEER + "/app/fn";
  const closure = Entity.create(CLOSURE, Ecf.map(
    ["params", Ecf.array([Ecf.text("n")])],
    ["body", Ecf.bytes(literal(peer.contentStore, uint(1)))],
  ));
  peer.tree.put(closurePath, closure);
  const viaClosure = run(peer, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text("app/fn")])));
  assert.equal(viaClosure.error, null);
  assert.ok(viaClosure.value instanceof Entity, "a stored closure comes back as an entity");
  assert.equal((viaClosure.value as Entity).type, CLOSURE, "and is NOT evaluated");
});

test("§2.1 lookup/tree: a peer-relative path is canonicalized, and the dependency records the canonical form", () => {
  // §2.1's parenthetical names this as a silent footgun: a dependency stored as `app/x`
  // never matches a write to `/{peer}/app/x`, and the reactive subgraph never recomputes.
  const peer = services();
  peer.tree.put("/" + PEER + "/app/x", Entity.create(LITERAL, Ecf.map(["value", uint(7)])));
  const ev = new ComputeEvaluator(peer);
  const out = ev.evaluateAt(
    Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text("app/x")])),
    "/" + PEER + "/app/expr",
  );
  assert.equal(out.error, null);
  assert.equal(intOf(out.value), 7n);
  assert.deepEqual(ev.dependencies, ["/" + PEER + "/app/x"]);
});

// ── §2.2 N.1 / N.4 — the three inline types both membership lists omit ───────────

test("§2.2 index/length/numeric-cast evaluate, and their types are in BOTH membership lists", () => {
  // ROUTED as A-10. §4.7 lists 13 of the 16 expression types and §4.2 lists 20 of the
  // 23; both omit exactly these three. §4.2's omission is the functional one — Tier 1
  // is the only tier that admits an ordinary sub-expression, so a peer transcribing it
  // answers `not_found` on a valid program. This test is the assertion that we did not.
  for (const t of [INDEX, LENGTH, NUMERIC_CAST]) {
    assert.equal(isComputeExpression(t), true, `${t} must be an expression (§2.2, §10.1)`);
    assert.equal(isComputeType(t), true, `${t} must be Tier-1 resolvable (§4.2)`);
  }

  const peer = services();
  const arr = literal(peer.contentStore, Ecf.array([uint(10), uint(20), uint(30)]));

  const len = run(peer, Entity.create(LENGTH, Ecf.map(["array", Ecf.bytes(arr)])));
  assert.equal(len.error, null);
  assert.equal(intOf(len.value), 3n);

  const idx = run(peer, Entity.create(INDEX, Ecf.map(
    ["array", Ecf.bytes(arr)],
    ["index", Ecf.bytes(literal(peer.contentStore, uint(1)))],
  )));
  assert.equal(idx.error, null);
  assert.equal(intOf(idx.value), 20n);

  const cast = run(peer, Entity.create(NUMERIC_CAST, Ecf.map(
    ["value", Ecf.bytes(literal(peer.contentStore, codec.ecfFloat(3.9)))],
    ["to_type", Ecf.text("primitive/int")],
  )));
  assert.equal(cast.error, null);
  assert.equal(intOf(cast.value), 3n, "float -> int truncates toward zero");
});

test("§2.2: a NEGATIVE index is index_out_of_range, never type_mismatch", () => {
  // §2.2's cross-impl ruling: an out-of-domain MAGNITUDE is not a type error. Two
  // conformant peers must return the same code here.
  const peer = services();
  const arr = literal(peer.contentStore, Ecf.array([uint(1)]));
  const out = run(peer, Entity.create(INDEX, Ecf.map(
    ["array", Ecf.bytes(arr)],
    ["index", Ecf.bytes(literal(peer.contentStore, codec.ecfInt(-1n)))],
  )));
  assert.equal(out.error?.code, "index_out_of_range");
});

test("§2.2 rule 11: casting NaN or Inf to an integer is cast_out_of_range", () => {
  const peer = services();
  for (const f of [NaN, Infinity, -Infinity]) {
    const out = run(peer, Entity.create(NUMERIC_CAST, Ecf.map(
      ["value", Ecf.bytes(literal(peer.contentStore, codec.ecfFloat(f)))],
      ["to_type", Ecf.text("primitive/int")],
    )));
    assert.equal(out.error?.code, "cast_out_of_range", `cast of ${f}`);
  }
});

// ── §5 — budget and depth ───────────────────────────────────────────────────────

test("§5.1: the budget charges evaluate() STEPS and nothing else", () => {
  // §4.2's normative note makes this a cross-impl determinism surface: two conformant
  // peers must reach budget_exhausted at the SAME step count. `resolve()` costs zero,
  // which is why an expression referencing three literals costs 4 and not 7.
  const peer = services();
  const expr = Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("add")],
    ["left", Ecf.bytes(literal(peer.contentStore, uint(1)))],
    ["right", Ecf.bytes(literal(peer.contentStore, uint(1)))],
  ));
  const out = run(peer, expr);
  assert.equal(out.error, null);
  // 1 for the arithmetic node + 1 for each operand's evaluate() = 3.
  assert.equal(out.operationsUsed, 3, "add(literal, literal) is three evaluate() steps");
});

test("§5.1: an exhausted budget yields budget_exhausted", () => {
  const peer = services();
  const out = run(peer, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("add")],
    ["left", Ecf.bytes(literal(peer.contentStore, uint(1)))],
    ["right", Ecf.bytes(literal(peer.contentStore, uint(1)))],
  )), { budget: 2 });
  assert.equal(out.error?.code, "budget_exhausted");
});

test("§5.2: a caller CANNOT raise its own ceiling", () => {
  // The minimum rule. A `params.budget` above the peer default is clamped, not honoured.
  const peer = services();
  const ev = new ComputeEvaluator(peer, { maxOperations: 5, maxDepth: 100 });
  const out = ev.evaluateAt(
    Entity.create(ARITHMETIC, Ecf.map(
      ["op", Ecf.text("add")],
      ["left", Ecf.bytes(literal(peer.contentStore, uint(1)))],
      ["right", Ecf.bytes(literal(peer.contentStore, uint(1)))],
    )),
    "/" + PEER + "/app/expr",
    { budget: 1_000_000 },
  );
  assert.equal(out.error, null);
  assert.ok(out.operationsUsed <= 5);
});

// ── §4.1 — the `is_error` MUST ──────────────────────────────────────────────────

test("§4.1: a compute/error reached by evaluation short-circuits its CONSUMER (kind-based is_error)", () => {
  // THE MUST THIS FILE EXISTS FOR, and the first draft of this test had the wrong
  // subject. It evaluated a stored `compute/error` DIRECTLY and expected its code back;
  // that answers `unknown_type`, correctly, because §4.7 makes `compute/error` a VALUE
  // type and not an expression. The predicate is not about what `evaluate` returns —
  // §4.1 says so in as many words: "SA-1 governs what evaluate returns; this predicate
  // governs what the CONSUMER does with it, and the guard sits between them."
  //
  // So the real path: a `compute/lookup/hash` resolves a stored error and returns it as
  // a value (SA-1, unchanged), and the arithmetic node consuming that operand must
  // short-circuit to it. Under the outcome-based reading the error would fall past the
  // guard and be embedded into the result — the cross-peer split this MUST prevents.
  const peer = services();
  const stored = Entity.create(ERROR, Ecf.map(["code", Ecf.text("division_by_zero")]));
  peer.contentStore.put(stored);

  const viaHash = put(peer.contentStore, Entity.create(LOOKUP_HASH, Ecf.map(
    ["hash", Ecf.bytes(stored.contentHash)],
  )));

  const out = run(peer, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("add")],
    ["left", Ecf.bytes(viaHash)],
    ["right", Ecf.bytes(literal(peer.contentStore, uint(1)))],
  )));

  assert.notEqual(out.error, null, "the consumer must short-circuit, not embed");
  assert.equal(out.error?.code, "division_by_zero", "and the error's OWN code survives (§2.4)");
});

// ── §4.1 / §2.3 — closures ──────────────────────────────────────────────────────

test("§4.1: a lambda captures scope and apply binds params in the CLOSURE's scope", () => {
  const peer = services();
  const lookupN = put(peer.contentStore, Entity.create(LOOKUP_SCOPE, Ecf.map(["name", Ecf.text("n")])));
  const lambda = put(peer.contentStore, Entity.create(LAMBDA, Ecf.map(
    ["params", Ecf.array([Ecf.text("n")])],
    ["body", Ecf.bytes(lookupN)],
  )));
  const out = run(peer, Entity.create(APPLY, Ecf.map(
    ["fn", Ecf.bytes(lambda)],
    ["args", Ecf.map(["n", Ecf.bytes(literal(peer.contentStore, uint(11)))])],
  )));
  assert.equal(out.error, null);
  assert.equal(intOf(out.value), 11n);
});

test("§4.1: a missing argument is missing_argument, named after the PARAM", () => {
  // The loop runs over the closure's params, not over the supplied args — which is
  // what makes a missing one an error rather than a silently unbound name.
  const peer = services();
  const lookupN = put(peer.contentStore, Entity.create(LOOKUP_SCOPE, Ecf.map(["name", Ecf.text("n")])));
  const lambda = put(peer.contentStore, Entity.create(LAMBDA, Ecf.map(
    ["params", Ecf.array([Ecf.text("n")])],
    ["body", Ecf.bytes(lookupN)],
  )));
  const out = run(peer, Entity.create(APPLY, Ecf.map(["fn", Ecf.bytes(lambda)])));
  assert.equal(out.error?.code, "missing_argument");
});

test("§2.1 Q23: a builtin-path apply carrying capability or resource is invalid_expression", () => {
  // A SHAPE check whose ORDERING is normative: it runs before any field is resolved,
  // so an error-valued `resource` cannot short-circuit to a different code. Two
  // conformant impls must agree on the code for one malformed expression.
  const peer = services();
  const out = run(peer, Entity.create(APPLY, Ecf.map(
    ["path", Ecf.text("system/compute/builtins/arithmetic")],
    ["operation", Ecf.text("eval")],
    ["resource", Ecf.bytes(literal(peer.contentStore, uint(1)))],
  )));
  assert.equal(out.error?.code, "invalid_expression");
});

test("§2.1 MUST: an apply carrying BOTH path and fn is invalid_expression, before either mode", () => {
  // CONTROL: the same closure applied through `fn` alone evaluates. Without it, a closure that
  // itself errored would satisfy the code assertion for a reason the rule does not name.
  const peer = services();
  const lambda = put(peer.contentStore, Entity.create(LAMBDA, Ecf.map(
    ["params", Ecf.array([])],
    ["body", Ecf.bytes(literal(peer.contentStore, uint(7)))],
  )));
  assert.equal(run(peer, Entity.create(APPLY, Ecf.map(["fn", Ecf.bytes(lambda)]))).error, null);
  const both = run(peer, Entity.create(APPLY, Ecf.map(
    ["path", Ecf.text("system/compute/builtins/arithmetic")],
    ["operation", Ecf.text("eval")],
    ["fn", Ecf.bytes(lambda)],
  )));
  assert.equal(both.error?.code, "invalid_expression");
  assert.match(both.error?.detail ?? "", /not both/);
});

// ── §4.1 — construct ────────────────────────────────────────────────────────────

test("§4.1 construct: fields evaluate in ECF CANONICAL key order (length, then lex)", () => {
  // Length-then-lex, not plain lex: "z" sorts BEFORE "aa". The order is observable
  // through the budget, so a plain-lex implementation disagrees with every other peer
  // about which field's error is returned when two of them fail.
  const peer = services();
  const constructed = run(peer, Entity.create(CONSTRUCT, Ecf.map(
    ["entity_type", Ecf.text("app/thing")],
    ["fields", Ecf.map(
      ["aa", Ecf.bytes(literal(peer.contentStore, uint(1)))],
      ["z", Ecf.bytes(literal(peer.contentStore, uint(2)))],
    )],
  )));
  assert.equal(constructed.error, null);
  assert.ok(constructed.value instanceof Entity);
  assert.equal((constructed.value as Entity).type, "app/thing");

  // The assertion that catches a plain-lex sort: with a budget that admits the
  // construct node and exactly ONE field, the field that got evaluated is the SHORTER
  // key, so the error names the second one either way — but the step count differs.
  const out = run(peer, Entity.create(CONSTRUCT, Ecf.map(
    ["entity_type", Ecf.text("app/thing")],
    ["fields", Ecf.map(
      ["aa", Ecf.bytes(literal(peer.contentStore, uint(1)))],
      ["z", Ecf.bytes(literal(peer.contentStore, uint(2)))],
    )],
  )), { budget: 2 });
  assert.equal(out.error?.code, "budget_exhausted");
});

test("§4.1 field: navigation reads an entity's .data by KIND, never by shape", () => {
  const peer = services();
  const inner = Entity.create("app/user", Ecf.map(["name", Ecf.text("alice")]));
  peer.contentStore.put(inner);
  peer.tree.put("/" + PEER + "/app/u", inner);
  const target = put(peer.contentStore, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text("app/u")])));
  const out = run(peer, Entity.create(FIELD, Ecf.map(
    ["name", Ecf.text("name")],
    ["entity", Ecf.bytes(target)],
  )));
  assert.equal(out.error, null);
  assert.equal((out.value as codec.EcfText).value, "alice");
});

// ── §2.4 — the materialized error is code-only ──────────────────────────────────

test("§2.4: a materialized compute/error carries `code` and NOTHING else", () => {
  // `message`, `at` and `expression` are in-flight diagnostics. Materializing one forks
  // the containing array's bytes across two conformant peers (v3.26), which is why the
  // in-flight detail rides beside the value where the codec cannot see it.
  const peer = services();
  const out = run(peer, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("add")],
    ["left", Ecf.bytes(literal(peer.contentStore, Ecf.text("x")))],
    ["right", Ecf.bytes(literal(peer.contentStore, uint(1)))],
  )));
  assert.equal(out.error?.code, "type_mismatch");
  assert.ok((out.error?.detail ?? "").length > 0, "the diagnostic exists in flight");

  const materialized = out.error!.toEntity();
  const keys = Ecf.entries(materialized.data).map(([k]) => k);
  assert.deepEqual(keys, ["code"], "only `code` is materialized");
});

// ── the type set ────────────────────────────────────────────────────────────────

test("33 types are defined, and the subgraph carries the field §10.1 MUSTs", () => {
  const defs = computeTypeDefs();
  assert.equal(defs.length, 33);

  const subgraph = defs.find((d) => d.name === "system/compute/subgraph");
  assert.ok(subgraph !== undefined);
  const fields = Ecf.entries(Ecf.require(subgraph.toData(), "fields")).map(([k]) => k);
  // ROUTED as A-11: §2.5 declares six, §3.3 writes seven, and four normative sites
  // require the seventh. `entity-core-go` publishes seven.
  assert.ok(
    fields.includes("authorized_data_hashes"),
    "§3.3/§4.2/§1.1/§10.1 all require it; only §2.5's field map omits it",
  );
  assert.equal(fields.length, 7);
});

test("a compute/result wraps a primitive with the source expression's hash", () => {
  const e = Entity.create(RESULT, Ecf.map(
    ["value", uint(1)],
    ["expression", Ecf.bytes(new Uint8Array(33))],
  ));
  assert.equal(e.type, RESULT);
});

// ── §2.3 SA-1 — a value type evaluates to itself ─────────────────────────────────

test("§2.3 SA-1: each of the four VALUE types evaluates to itself, unchanged", () => {
  // §4.1's `evaluate_inner` has NO arm for these four, so a literal transcription of
  // the pseudocode answers `unknown_type` — which is exactly what this port did until
  // the oracle's `v319b_scope_unreachable` caught it. Routed as A-12.
  const peer = services();

  const closure = Entity.create(CLOSURE, Ecf.map(
    ["params", Ecf.array([Ecf.text("x")])],
    ["body", Ecf.bytes(literal(peer.contentStore, uint(1)))],
    ["env", null],
  ));
  const scope = Entity.create(SCOPE, Ecf.map(["bindings", Ecf.map()]));
  const result = Entity.create(RESULT, Ecf.map(
    ["value", uint(7)],
    ["expression", Ecf.bytes(new Uint8Array(33))],
  ));

  for (const value of [closure, scope, result]) {
    const out = run(peer, value);
    assert.equal(out.error, null, `${value.type} must not error`);
    assert.ok(out.value instanceof Entity);
    assert.equal((out.value as Entity).contentHashHex, value.contentHashHex,
      `${value.type} must come back byte-identical, not re-encoded`);
  }

  // `compute/error` is the fourth and it goes down the OTHER branch of the outcome,
  // because SA-1 returns it and `is_error` is kind-based — so the SDK reports it as an
  // error rather than as a value. Both statements are true at once and that is the
  // point of §3.5's "behaves identically however it was produced".
  const stored = run(peer, Entity.create(ERROR, Ecf.map(["code", Ecf.text("not_found")])));
  assert.equal(stored.value, null);
  assert.equal(stored.error?.code, "not_found");
});

test("§2.3 SA-1: THE NEGATIVE — a non-value, non-expression type is still unknown_type", () => {
  // The control for the arm above. Widening the fallthrough to "return anything that
  // is not an expression" would pass every SA-1 test and turn §4.1's `unknown_type`
  // into dead code — and `eval_error_non_expression` is a live oracle check.
  const peer = services();
  const out = run(peer, Entity.create("compute/does-not-exist", Ecf.map(["x", uint(1)])));
  assert.equal(out.error?.code, "unknown_type");

  const appEntity = run(peer, Entity.create("app/user", Ecf.map(["name", Ecf.text("alice")])));
  assert.equal(appEntity.error?.code, "unknown_type");
});

test("§4.3 N8: a closure STORED and applied reaches load_scope, not the default arm", () => {
  // The shape of `v319b_scope_unreachable`, reproduced locally: the failure it reports
  // is `scope_unreachable`, and before SA-1 this port answered `unknown_type` because
  // the closure entity itself never evaluated. Two different codes, one of which says
  // "we do not know this type" about a type the spec defines.
  const peer = services();
  const ghost = new Uint8Array(33);
  ghost.fill(0xff);
  ghost[0] = 0x00;

  const scopeEnt = Entity.create(SCOPE, Ecf.map(["bindings", Ecf.map(
    ["ghost", Ecf.map(["kind", Ecf.text("entity")], ["entity_hash", Ecf.bytes(ghost)])],
  )]));
  peer.contentStore.put(scopeEnt);

  const closure = Entity.create(CLOSURE, Ecf.map(
    ["params", Ecf.array([Ecf.text("_")])],
    ["body", Ecf.bytes(literal(peer.contentStore, uint(42)))],
    ["env", Ecf.bytes(scopeEnt.contentHash)],
  ));
  peer.contentStore.put(closure);

  const out = run(peer, Entity.create(APPLY, Ecf.map(
    ["fn", Ecf.bytes(closure.contentHash)],
    ["args", Ecf.map(["_", Ecf.bytes(literal(peer.contentStore, uint(0)))])],
  )));
  assert.equal(out.error?.code, "scope_unreachable");
});

// ── §2.3 / v3.19c option α — in-flight navigation vs. read-back ──────────────────

test("v3.19c: navigation composes through a construct INSIDE one evaluation", () => {
  // `field(field(construct(app/wrapper,{inner:construct(app/user,{name:'alice'})}),
  // 'inner'),'name')` → 'alice'. §4.1's construct arm assigns the STORED HASH into
  // `result_fields` and keeps nothing typed, so a transcription of it answers
  // `type_mismatch` on the second hop. Routed as A-13.
  const peer = services();
  const cs = peer.contentStore;

  const innerCtor = Entity.create(CONSTRUCT, Ecf.map(
    ["entity_type", Ecf.text("app/user")],
    ["fields", Ecf.map(["name", Ecf.bytes(literal(cs, Ecf.text("alice")))])],
  ));
  const outerCtor = Entity.create(CONSTRUCT, Ecf.map(
    ["entity_type", Ecf.text("app/wrapper")],
    ["fields", Ecf.map(["inner", Ecf.bytes(put(cs, innerCtor))])],
  ));
  const innerField = Entity.create(FIELD, Ecf.map(
    ["name", Ecf.text("inner")],
    ["entity", Ecf.bytes(put(cs, outerCtor))],
  ));
  const out = run(peer, Entity.create(FIELD, Ecf.map(
    ["name", Ecf.text("name")],
    ["entity", Ecf.bytes(put(cs, innerField))],
  )));
  assert.equal(out.error, null);
  assert.equal((out.value as codec.EcfText).value, "alice");
});

test("v3.19c: THE NEGATIVE — read-back nav on a MATERIALIZED entity returns the hash", () => {
  // The other half of the same sentence, and the control that keeps the branch above
  // from becoming a shape-sniffing auto-resolve. §2.3 forbids identifying a reference
  // by byte length or shape: `system/hash` is variable-length with an extensible
  // LEB128 format code, so "33 bytes" is today's accident. A hand-built wrapper read
  // back through `lookup/tree` has no in-flight typing, and its `inner` field MUST
  // come back as bytes.
  const peer = services();
  const inner = Entity.create("app/user", Ecf.map(["name", Ecf.text("alice")]));
  peer.contentStore.put(inner);
  const wrapper = Entity.create("app/wrapper", Ecf.map(["inner", Ecf.bytes(inner.contentHash)]));
  peer.contentStore.put(wrapper);
  peer.tree.put("/" + PEER + "/app/w", wrapper);

  const lookup = put(peer.contentStore, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text("app/w")])));
  const out = run(peer, Entity.create(FIELD, Ecf.map(
    ["name", Ecf.text("inner")],
    ["entity", Ecf.bytes(lookup)],
  )));
  assert.equal(out.error, null);
  assert.equal((out.value as { kind: string }).kind, "bytes",
    "a materialized system/hash field yields the HASH; the caller follows it explicitly");
});

test("v3.19c: the MATERIALIZED form of a nested construct is the bare V7 §1.4 shape", () => {
  // The M1 hash gate, locally: the boundary form must be byte-identical to the same
  // entity built outside compute. This is what stops the in-flight representation
  // above from leaking into a content hash — and it is the assertion that would fail
  // if `ConstructedValue` were returned from the SDK instead of materialized.
  const peer = services();
  const cs = peer.contentStore;

  const innerCtor = Entity.create(CONSTRUCT, Ecf.map(
    ["entity_type", Ecf.text("app/user")],
    ["fields", Ecf.map(["name", Ecf.bytes(literal(cs, Ecf.text("alice")))])],
  ));
  const outerCtor = Entity.create(CONSTRUCT, Ecf.map(
    ["entity_type", Ecf.text("app/wrapper")],
    ["fields", Ecf.map(["inner", Ecf.bytes(put(cs, innerCtor))])],
  ));
  const out = run(peer, outerCtor);
  assert.equal(out.error, null);
  assert.ok(out.value instanceof Entity, "the boundary hands back a bare Entity");

  const handBuiltInner = Entity.create("app/user", Ecf.map(["name", Ecf.text("alice")]));
  const handBuiltOuter = Entity.create("app/wrapper", Ecf.map(["inner", Ecf.bytes(handBuiltInner.contentHash)]));
  assert.equal((out.value as Entity).contentHashHex, handBuiltOuter.contentHashHex);

  // And the reference it hands back is FOLLOWABLE — the store has the inner entity.
  assert.notEqual(cs.get(handBuiltInner.contentHash), undefined,
    "materialize stores what the bare form references, or the caller cannot follow it");
});
