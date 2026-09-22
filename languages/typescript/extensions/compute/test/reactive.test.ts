/**
 * §3.3 and §7 — the clauses the oracle's `compute` category cannot reach.
 *
 * **THIS FILE EXISTS BECAUSE OF WHAT THE 14 CHECKS MEASURE, NOT BECAUSE THEY FAILED.**
 * `validate-peer`'s reactive family is a wire client: it writes a dependency, reads a
 * result path and compares a number. Every check in it is an assertion about a value
 * that APPEARED. Four of §7's normative clauses are assertions about something that
 * did NOT happen, or about a value no wire read can see:
 *
 * | clause | what it asserts | why the wire cannot see it |
 * |---|---|---|
 * | §7.2 convergence | a re-evaluation producing the same hash writes **nothing** | the value at `result_path` is right either way |
 * | §7.3 cascade bound | a runaway cascade **freezes** rather than recursing | a peer that recursed would be down, not wrong |
 * | §7.2 grant validity | an expired grant freezes with `installation_grant_invalid` | no vector expires a grant mid-run |
 * | §3.3 Phase 3 | the caller's capability **entity** reaches the content store | the install answers 200 without it; the FIRST re-evaluation is what breaks |
 * | §3.3 `deterministic_id` | the id is cross-peer identical | nothing reads `subgraph_path` back |
 *
 * That list is this port's honest answer to *"which rows are ours"* in
 * `EXTENSION.toml [conformance]`, and it is the only part of §7 where we are both the
 * implementer and the instrument. Where a reference vector exists it is used instead
 * of our own reading — see the `deterministic_id` test, whose expectations are
 * `entity-core-go`'s output and not ours.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CapabilityToken,
  ContentStore,
  Permissions,
  Ecf,
  EmitBus,
  Entity,
  EntityTree,
  Envelope,
  Execute,
  GrantEntry,
  HandlerContext,
  PeerIdentity,
  ResourceTarget,
  Scope,
  codec,
} from "entity-core-protocol-typescript";

import {
  APPLY, ARITHMETIC, CLOSURE, ERROR, IF, LET, LITERAL, LOOKUP_SCOPE, LOOKUP_TREE,
  PROCESSES_PREFIX, RESULT, SUBGRAPH,
  DEFAULT_MAX_DEPTH, DEFAULT_MAX_OPS,
  ComputeEvaluator,
  ComputeHandler,
  ReactiveEngine,
  deterministicId,
} from "@entity-core/extension-compute";

const PEER = "z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH";
const LIMITS = { maxOperations: DEFAULT_MAX_OPS, maxDepth: DEFAULT_MAX_DEPTH };

// ── §3.3 `deterministic_id` ─────────────────────────────────────────────────────

test("§3.3 deterministic_id agrees with the reference implementation, vector for vector", () => {
  // ** THE EXPECTATIONS ARE `entity-core-go`'s OUTPUT, NOT OUR READING. ** §3.3 makes
  // this derivation normative for a reason it states plainly: *"a subgraph installed
  // by Peer A at root path `app/cell/A1` is discoverable at the same
  // `system/compute/processes/{subgraph_id}` on ANY peer"*. It is therefore a
  // cross-peer identity, and no check in `validate-peer` reads `subgraph_path` back —
  // so two implementations could disagree about it forever and every conformance run
  // would stay green.
  //
  // A second reading of the same prose by the same team is not evidence (L18). These
  // four strings were produced by running `deterministicID` out of
  // `entity-core-go/ext/compute/engine.go` on 2026-09-10, which is a different
  // codebase, a different base32 library and a different author.
  const reference: readonly (readonly [string, string])[] = [
    ["/peer/app/cell/A1", "ffb4c3uopfuogfzn35cv7wdmsgf74ubjlpntxey64wr4dh6fgqoq"],
    ["app/cell/A1", "mijknkgplgoibnth6mdfl3kerwp22d7w73jqfae4dtrw7xzz6gra"],
    ["", "4oymiquy7qobjgx36tejs35zeqt24qpemsnzgtfeswmrw6csxbkq"],
    ["a", "zklycewkdo64v6wcggzzui64jwtyn37ycr6e44vzqb3yll7ojc5q"],
  ];
  for (const [path, expected] of reference) {
    assert.equal(deterministicId(path), expected, `deterministic_id(${JSON.stringify(path)})`);
  }
  // §3.3: *"The result is a 52-character string"* — the length is stated normatively
  // because a padded or truncated encoding still round-trips locally.
  for (const [path] of reference) assert.equal(deterministicId(path).length, 52);
});

test("§3.3 deterministic_id: THE NEGATIVE — different paths give different ids", () => {
  // A constant function passes every equality assertion above if the vectors were
  // ours. They are not, but the guard costs one line and it is the assertion that
  // would survive someone regenerating the vectors from this file.
  const ids = new Set(["a", "b", "/x/a", "/x/a/"].map(deterministicId));
  assert.equal(ids.size, 4);
});

// ── §7.1 — the completeness PROPERTY ────────────────────────────────────────────

test("§7.1 [MUST]: every reachable compute/lookup/tree is registered, container or not", () => {
  // ** THE MUST IS THE PROPERTY, AND THE PSEUDOCODE IS ITS ILLUSTRATION. ** v3.27 says
  // so in as many words, and then says why: *"dependency registration produces no
  // boundary, so a subgraph with an unregistered dependency evaluates correctly
  // exactly once and is then never woken again."* There is no hash to compare and no
  // status to read — the failure is a thing that stops happening.
  //
  // So this asserts the property over a graph that puts a reference in EVERY shape
  // §2.1's grammar allows, rather than over the two shapes v3.27 enumerates. A walker
  // written to the enumeration passes the enumeration; the point of the MUST is the
  // type that gets added next.
  const { tree, contentStore, engine } = harness();
  const root = "/" + PEER + "/app/root";

  const dep = (name: string): Uint8Array =>
    put(contentStore, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text("/" + PEER + "/data/" + name)])));

  //  scalar field          — arithmetic.left
  //  map-valued field      — apply.args["n"]           (§2.1's first enumerated exception)
  //  array-of-maps field   — let.bindings[0].value     (§2.1's second)
  //  behind an if branch   — if.else_branch            (conservative static collection)
  //  inside a closure body — closure.body              (§7.1 walks body and env)
  const body = put(contentStore, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("add")],
    ["left", Ecf.bytes(dep("in-closure-body"))],
    ["right", Ecf.bytes(literal(contentStore, uint(1)))],
  )));
  const closure = put(contentStore, Entity.create(CLOSURE, Ecf.map(
    ["params", Ecf.array([Ecf.text("n")])],
    ["body", Ecf.bytes(body)],
  )));
  const apply = put(contentStore, Entity.create(APPLY, Ecf.map(
    ["fn", Ecf.bytes(closure)],
    ["args", Ecf.map(["n", Ecf.bytes(dep("in-apply-args"))])],
  )));
  const branch = put(contentStore, Entity.create(IF, Ecf.map(
    ["condition", Ecf.bytes(literal(contentStore, codec.ecfBool(true)))],
    ["then_branch", Ecf.bytes(apply)],
    ["else_branch", Ecf.bytes(dep("behind-untaken-branch"))],
  )));
  const letExpr = Entity.create(LET, Ecf.map(
    ["bindings", Ecf.array([Ecf.map(["name", Ecf.text("x")], ["value", Ecf.bytes(dep("in-let-binding"))])])],
    ["body", Ecf.bytes(branch)],
  ));
  tree.put(root, letExpr);

  const subgraphPath = install(tree, contentStore, root, root + "/result");
  engine.rebuild();

  const watched = new Set(engine.watchedPaths);
  for (const name of ["in-closure-body", "in-apply-args", "behind-untaken-branch", "in-let-binding"]) {
    assert.ok(watched.has("/" + PEER + "/data/" + name), `unregistered dependency: ${name}`);
  }
  assert.ok(subgraphPath.startsWith("/" + PEER + "/" + PROCESSES_PREFIX + "/"));
});

test("§7.1: THE NEGATIVE — a lookup/scope is not a tree dependency, and neither is a plain 33-byte value", () => {
  // The walker's hash detector is a LENGTH test, which is what `system/hash` is on the
  // wire. That makes a `compute/literal` carrying 33 bytes of anything look exactly
  // like a reference — CP1's vectors carry a capability hash in precisely that shape —
  // so the guard that matters is §3.3's *"Audit scope (normative)"*: a hash resolving
  // to a NON-compute entity is skipped. Without it the audit walks arbitrary data and
  // the index fills with paths nothing writes.
  const { tree, contentStore, engine } = harness();
  const root = "/" + PEER + "/app/root";

  const scoped = put(contentStore, Entity.create(LOOKUP_SCOPE, Ecf.map(["name", Ecf.text("x")])));
  const capShaped = put(contentStore, Entity.create(LITERAL, Ecf.map(["value", Ecf.bytes(new Uint8Array(33).fill(7))])));
  tree.put(root, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("add")],
    ["left", Ecf.bytes(scoped)],
    ["right", Ecf.bytes(capShaped)],
  )));

  install(tree, contentStore, root, root + "/result");
  engine.rebuild();
  assert.deepEqual(engine.watchedPaths, [], "§7.1: only compute/lookup/tree registers a tree dependency");
});

// ── §7.2 — the convergence check, which is a NON-write ──────────────────────────

test("§7.2 convergence: OUR check decides not to write, and a changed result still writes", () => {
  // ** THE FIRST DRAFT OF THIS TEST WAS A FALSE GREEN AND THE REASON IS THE FINDING. **
  // It asserted the OBSERVABLE — the result path's hash did not move and no bind event
  // fired — and it passed with §7.2's convergence check DELETED. Both halves are
  // guaranteed by the substrate underneath us: `EntityTree.put` emits only when
  // `changed`, and `ContentStore.put` only when the hash is new. So on this peer the
  // clause is REDUNDANT, every observable is the peer's answer rather than ours, and a
  // port that never implemented it is indistinguishable here.
  //
  // That is a `[substrate]` row, not a reason to drop the assertion: a peer whose
  // `put` emits unconditionally — which §7.2 permits, since it pins no such guard —
  // would cascade forever on a converged subgraph. **So the test asserts BOTH: the
  // observable, which is what a consumer sees, and `#reEvaluate`'s own return value,
  // which is the only thing in this process that reflects OUR decision.** The second
  // is what goes red on the planted defect; the first is what would go red on a
  // substrate that did not cover for us.
  const { tree, contentStore, engine, events } = harness();
  const depPath = "/" + PEER + "/data/x";
  const root = "/" + PEER + "/app/root";

  // B = dep * 0 — so B's value is 0 for every dep, and the result hash never moves.
  tree.put(depPath, Entity.create(LITERAL, Ecf.map(["value", uint(5)])));
  const depRef = put(contentStore, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text(depPath)])));
  tree.put(root, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("mul")],
    ["left", Ecf.bytes(depRef)],
    ["right", Ecf.bytes(literal(contentStore, uint(0)))],
  )));

  const subgraphPath = install(tree, contentStore, root, root + "/result");
  engine.rebuild();

  // ** THE ASSERTION THAT ISOLATES OUR CODE. ** `evaluateNow` returns the hash it
  // WROTE, or `null` when the convergence check stopped it. Two identical evaluations:
  // the first writes, the second must decline. Nothing in the substrate can produce
  // that `null` on our behalf.
  const first = engine.evaluateNow(subgraphPath, null);
  assert.notEqual(first, null, "the initial evaluation must write a result");
  assert.equal(
    engine.evaluateNow(subgraphPath, null),
    null,
    "§7.2: a re-evaluation whose result hash equals the stored one MUST NOT write",
  );

  const before = tree.getHash(root + "/result");
  assert.notEqual(before, undefined, "the initial evaluation must have written a result");
  events.length = 0;

  tree.put(depPath, Entity.create(LITERAL, Ecf.map(["value", uint(9)])));
  assert.deepEqual(tree.getHash(root + "/result"), before, "§7.2: converged — the result hash did not move");
  assert.deepEqual(
    events.filter((p) => p === root + "/result"),
    [],
    "§7.2: a converged re-evaluation performs NO tree write, so no event reaches the pipeline",
  );

  // THE POSITIVE CONTROL, and it is the half that makes the assertion above mean
  // something: the same machinery, a dependency change that DOES move the result.
  const root2 = "/" + PEER + "/app/root2";
  tree.put(root2, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("mul")],
    ["left", Ecf.bytes(depRef)],
    ["right", Ecf.bytes(literal(contentStore, uint(2)))],
  )));
  const sg2 = install(tree, contentStore, root2, root2 + "/result");
  engine.rebuild();
  engine.evaluateNow(sg2, null);
  const before2 = tree.getHash(root2 + "/result");
  tree.put(depPath, Entity.create(LITERAL, Ecf.map(["value", uint(11)])));
  assert.notDeepEqual(tree.getHash(root2 + "/result"), before2, "a real change must write");
  assert.equal(resultValue(tree, root2 + "/result"), 22n);
});

// ── §7.2 — the installation grant ───────────────────────────────────────────────

test("§7.2: a missing installation grant freezes the subgraph with installation_grant_invalid", () => {
  // **This is §3.3 Phase 3's clause, tested from the far side.** §3.3 spends a
  // five-line comment on *"the compute handler MUST persist the caller's capability
  // entity to the content store before recording its content hash"*, and the failure
  // it prevents is entirely invisible at install time: the install answers 200, the
  // metadata is well-formed, and the FIRST re-evaluation cannot resolve the grant.
  const { tree, contentStore, engine } = harness();
  const depPath = "/" + PEER + "/data/x";
  const root = "/" + PEER + "/app/root";
  tree.put(depPath, Entity.create(LITERAL, Ecf.map(["value", uint(5)])));
  const depRef = put(contentStore, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text(depPath)])));
  tree.put(root, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("mul")],
    ["left", Ecf.bytes(depRef)],
    ["right", Ecf.bytes(literal(contentStore, uint(2)))],
  )));

  // Installed with a grant hash that resolves to NOTHING — exactly the state a port
  // that skipped the `content_store.put` leaves behind.
  const subgraphPath = install(tree, contentStore, root, root + "/result", { grantEntity: null });
  engine.rebuild();
  tree.put(depPath, Entity.create(LITERAL, Ecf.map(["value", uint(9)])));

  const result = tree.get(root + "/result");
  assert.equal(result?.type, ERROR);
  assert.equal(Ecf.optText(result!.data, "code"), "installation_grant_invalid");
  // §2.4: the MATERIALIZED form is CODE-ONLY. `message` and `at` are in-flight
  // diagnostics; one written here forks the content hash across conformant peers.
  assert.deepEqual(Ecf.entries(result!.data).map(([k]) => k), ["code"]);
  assert.equal(Ecf.optText(tree.get(subgraphPath)!.data, "status"), "frozen");
});

test("§7.2: THE NEGATIVE — a valid grant does not freeze", () => {
  const { tree, contentStore, engine } = harness();
  const depPath = "/" + PEER + "/data/x";
  const root = "/" + PEER + "/app/root";
  tree.put(depPath, Entity.create(LITERAL, Ecf.map(["value", uint(5)])));
  const depRef = put(contentStore, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text(depPath)])));
  tree.put(root, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("mul")],
    ["left", Ecf.bytes(depRef)],
    ["right", Ecf.bytes(literal(contentStore, uint(2)))],
  )));
  const subgraphPath = install(tree, contentStore, root, root + "/result");
  engine.rebuild();
  tree.put(depPath, Entity.create(LITERAL, Ecf.map(["value", uint(9)])));

  assert.equal(resultValue(tree, root + "/result"), 18n);
  assert.equal(Ecf.optText(tree.get(subgraphPath)!.data, "status"), "active");
});

// ── §7.3 — the cascade bound ────────────────────────────────────────────────────

test("§7.3 [MUST]: a self-feeding cascade terminates in a frozen subgraph, not a stack", () => {
  // **§7.3's bound is the one clause in §7 whose failure mode is not a wrong answer.**
  // This peer delivers emit events SYNC-INLINE — `EmitBus` calls every consumer inside
  // `EntityTree.put`, before it returns — which is what makes a cascade observable to
  // the oracle at all (the result is already written when `tree:put` answers). The
  // same property means an unbounded cascade is unbounded RECURSION: the peer dies,
  // and a dead peer is not a failing check.
  //
  // The subgraph below depends on its OWN result path, with an expression whose value
  // moves every round, so the convergence check can never stop it. Only the bound can.
  //
  // **THE NEGATIVE CONTROL WAS RUN AND IT IS RECORDED IN `internal/reactive.ts`.**
  // Disabling the spec's `cascade_depth` gate: still freezes (the re-entrancy backstop
  // holds). Disabling the backstop: still freezes (the spec's counter holds).
  // Disabling BOTH: `RangeError: Maximum call stack size exceeded` — which is the
  // whole reason this test asserts on a frozen STATUS rather than on a value.
  const { tree, contentStore, engine } = harness();
  const root = "/" + PEER + "/app/loop";
  const resultPath = root + "/result";

  const selfRef = put(contentStore, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text(resultPath)])));
  // add(field("value", lookup(result)), 1) — strictly increasing, never converges.
  const prior = put(contentStore, Entity.create("compute/field", Ecf.map(
    ["name", Ecf.text("value")],
    ["entity", Ecf.bytes(selfRef)],
  )));
  tree.put(root, Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("add")],
    ["left", Ecf.bytes(prior)],
    ["right", Ecf.bytes(literal(contentStore, uint(1)))],
  )));
  tree.put(resultPath, Entity.create(RESULT, Ecf.map(["value", uint(0)])));

  const subgraphPath = install(tree, contentStore, root, resultPath);
  engine.rebuild();

  // The trigger. If the bound were missing this line would not return.
  tree.put(resultPath, Entity.create(RESULT, Ecf.map(["value", uint(1)])));

  assert.equal(
    Ecf.optText(tree.get(subgraphPath)!.data, "status"),
    "frozen",
    "§7.3: the cascade MUST be bounded, and the bound freezes the subgraph",
  );
  const result = tree.get(resultPath);
  assert.equal(result?.type, ERROR);
  assert.equal(Ecf.optText(result!.data, "code"), "cascade_limit");
});

// ── §6.2 — the per-tree-read capability check ───────────────────────────────────

test("§6.2: a tree read outside the capability's resource scope is permission_denied", () => {
  // ** THE ORACLE CANNOT SEE THIS CHECK AT ALL, IN EITHER DIRECTION. ** `validate-peer`
  // runs against a host launched with `--debug-open-grants`, so the capability every
  // vector wields is the wide-open `*` admin grant and every `check_path_permission`
  // answers true. A port that implemented §6.2 per tree read and a port that answered
  // `true` unconditionally produce the same 128 numbers. This is the negative control
  // the corpus structurally cannot contain.
  //
  // It matters because the predicate is new here — §6.2 was `gap` in [conformance]
  // until 2026-09-10 on the strength of a claim about the peer that was false (see
  // `CAPABILITY_CHECK_IS_DISPATCH_SCOPED`). A check added on the back of a corrected
  // reading, and never seen refusing, would be the same mistake wearing a fix.
  const { tree, contentStore } = harness();
  const allowed = "/" + PEER + "/app/ok";
  const denied = "/" + PEER + "/secret/key";
  tree.put(allowed, Entity.create(LITERAL, Ecf.map(["value", uint(7)])));
  tree.put(denied, Entity.create(LITERAL, Ecf.map(["value", uint(99)])));

  // A grant over `/{peer}/app/*` and nothing else — the narrow case the open-grants
  // host never produces.
  const identity = PeerIdentity.fromSeed(new Uint8Array(32).fill(0x11));
  const { token } = CapabilityToken.createRoot(
    identity,
    identity.identityHash,
    [new GrantEntry(
      new Scope(["system/tree"], null),
      new Scope(["app/*"], null),
      new Scope(["get"], null),
      null, null, null,
    )],
    0n,
  );
  const authority = {
    canReadPath: (p: string) =>
      Permissions.checkPathPermission("get", p, token, "system/tree", PEER),
  };

  const read = (path: string): ReturnType<ComputeEvaluator["evaluateAt"]> => {
    const ref = Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text(path)]));
    return new ComputeEvaluator({ tree, contentStore, localPeerId: PEER }, LIMITS)
      .evaluateAt(ref, "/" + PEER + "/app/expr", authority);
  };

  // THE POSITIVE: inside the grant, the read succeeds and returns the stored literal.
  assert.equal(read(allowed).error, null, "a covered path must read");

  // THE NEGATIVE: outside it, §4.1's guard fires BEFORE the read and before the
  // dependency registration — so an unauthorized path does not leak its existence
  // through a registered dependency either.
  const refused = read(denied);
  assert.equal(refused.error?.code, "permission_denied");
  assert.equal(refused.value, null);
});

test("§6.2: the HANDLER hands the caller's own capability to the evaluator", () => {
  // ** THE TEST ABOVE WOULD PASS IF `pathAuthority` RETURNED `{}`. ** It drives
  // `ComputeEvaluator` directly with the predicate already built, so it proves the
  // evaluator HONORS `canReadPath` and says nothing about whether anything supplies
  // one. That is the same gap the convergence test had in its first draft — an
  // assertion one layer away from the code it is named after — so this drives
  // `ComputeHandler.handle` through a real `HandlerContext` instead.
  //
  // The condition that flips it: `pathAuthority` returning an empty object, or the
  // handler passing a token other than `ctx.callerCapability`. Neither is reachable
  // from the oracle, which runs `--debug-open-grants`.
  const identity = PeerIdentity.fromSeed(new Uint8Array(32).fill(0x11));
  const contentStore = new ContentStore();
  const emit = new EmitBus();
  const tree = new EntityTree(contentStore, emit);
  const peer = {
    localPeerId: PEER,
    localIdentity: identity,
    tree,
    contentStore,
    emit,
    nowMs: 1_000_000n,
    maxFrameBytes: 1 << 20,
  };

  const denied = "/" + PEER + "/secret/key";
  tree.put(denied, Entity.create(LITERAL, Ecf.map(["value", uint(99)])));
  const exprPath = "/" + PEER + "/app/expr";
  tree.put(exprPath, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text(denied)])));

  const { token } = CapabilityToken.createRoot(
    identity,
    identity.identityHash,
    [new GrantEntry(
      new Scope(["system/tree"], null),
      new Scope(["app/*"], null),   // covers the expression, NOT `secret/*`
      new Scope(["get"], null),
      null, null, null,
    )],
    0n,
  );

  const execute = new Execute(Entity.create("system/protocol/execute", Ecf.map(
    ["request_id", Ecf.text("t-1")],
    ["uri", Ecf.text("entity://" + PEER + "/system/compute")],
    ["operation", Ecf.text("eval")],
    // `Execute.params` decodes a nested `{type, data, content_hash}` entity map, so
    // the field carries a real entity's wire form and not a bare map. Getting this
    // wrong is what the first run of this test found — and it found it in OUR code
    // too: `#eval` read `ctx.params` OUTSIDE the try that guards the decode, so a
    // malformed params threw out of the handler instead of being treated as absent.
    ["params", codec.ecfPreEncoded(Entity.create("primitive/any", Ecf.emptyMap()).wireBytes)],
    ["resource", new ResourceTarget([exprPath], null).toEcf()],
  )));
  const ctx = new HandlerContext({
    peer,
    execute,
    envelope: new Envelope(execute.entity, []),
    pattern: "system/compute",
    suffix: "",
    callerCapability: token,
    handlerGrant: null,
    author: identity.identityHash,
    connection: null,
  });

  return new ComputeHandler().handle(ctx).then((result) => {
    // F10 — an evaluated refusal is a compute/error VALUE at status 200, never a 4xx.
    assert.equal(result.status, 200);
    assert.equal(result.result.type, ERROR);
    assert.equal(Ecf.optText(result.result.data, "code"), "permission_denied");
  });
});

// ── §3.4 ────────────────────────────────────────────────────────────────────────

test("§3.4: uninstall clears the registrations and leaves the expression in the tree", () => {
  const { tree, contentStore, engine } = harness();
  const depPath = "/" + PEER + "/data/x";
  const root = "/" + PEER + "/app/root";
  tree.put(depPath, Entity.create(LITERAL, Ecf.map(["value", uint(5)])));
  const depRef = put(contentStore, Entity.create(LOOKUP_TREE, Ecf.map(["path", Ecf.text(depPath)])));
  const expression = Entity.create(ARITHMETIC, Ecf.map(
    ["op", Ecf.text("mul")],
    ["left", Ecf.bytes(depRef)],
    ["right", Ecf.bytes(literal(contentStore, uint(2)))],
  ));
  tree.put(root, expression);
  const subgraphPath = install(tree, contentStore, root, root + "/result");
  engine.rebuild();
  assert.equal(engine.registeredDependencies, 1);

  engine.unregister(subgraphPath);
  tree.remove(subgraphPath);

  assert.equal(engine.registeredDependencies, 0);
  // §3.4: *"Does not delete the expression entities — they remain in the tree as
  // inert data."* Uninstall withdraws the standing authorization, not the program.
  assert.deepEqual(tree.get(root)?.contentHash, expression.contentHash);
});

// ── harness ─────────────────────────────────────────────────────────────────────

interface Harness {
  readonly tree: EntityTree;
  readonly contentStore: ContentStore;
  readonly engine: ReactiveEngine;
  /** Every path the emit bus saw a bind on — how a NON-write is asserted. */
  readonly events: string[];
}

function harness(): Harness {
  const identity = PeerIdentity.fromSeed(new Uint8Array(32).fill(0x11));
  const contentStore = new ContentStore();
  const emit = new EmitBus();
  const tree = new EntityTree(contentStore, emit);
  const events: string[] = [];
  const engine = new ReactiveEngine(
    { tree, contentStore, localPeerId: PEER, localIdentity: identity, nowMs: 1_000_000n },
    LIMITS,
  );
  // The recorder is registered FIRST so it sees the engine's own writes as well as the
  // driving ones; the engine is the consumer under test and registration order between
  // two consumers is the composition's business (SYSTEM-COMPOSITION §2.2), not a
  // property this file should depend on.
  emit.registerConsumer({
    name: "test-recorder",
    onContentStore: () => {},
    onTreeChange: (ev) => { events.push(ev.path); },
  });
  emit.registerConsumer(engine);
  return { tree, contentStore, engine, events };
}

/**
 * Write subgraph metadata by hand, as §3.3 Phase 3 would.
 *
 * The handler's `#install` is not reachable without a full `HandlerContext` (an
 * `Execute`, an `Envelope`, a verified capability), and driving it would test the
 * dispatch plumbing rather than §7. What §7 reads off the metadata is six fields, and
 * those are what this writes — so a change to Phase 3's field names breaks these
 * tests, which is the coupling worth having.
 */
function install(
  tree: EntityTree,
  contentStore: ContentStore,
  rootPath: string,
  resultPath: string,
  options: { grantEntity?: Entity | null } = {},
): string {
  const identity = PeerIdentity.fromSeed(new Uint8Array(32).fill(0x11));
  const { token } = CapabilityToken.createRoot(
    identity,
    identity.identityHash,
    [new GrantEntry(new Scope(["*"], null), new Scope(["*"], null), new Scope(["*"], null), null, null, null)],
    0n,
  );
  // `grantEntity: null` models the port that recorded the hash and never stored the
  // entity — §3.3 Phase 3's dropped clause.
  if (options.grantEntity !== null) contentStore.put(token.entity);

  const expression = tree.get(rootPath)!;
  const subgraphPath = "/" + PEER + "/" + PROCESSES_PREFIX + "/" + deterministicId(rootPath);
  tree.put(subgraphPath, Entity.create(SUBGRAPH, Ecf.map(
    ["root_expression_path", Ecf.text(rootPath)],
    ["root_expression", Ecf.bytes(expression.contentHash)],
    ["installation_grant", Ecf.bytes(token.contentHash)],
    ["installed_by", Ecf.bytes(identity.identityHash)],
    ["result_path", Ecf.text(resultPath)],
    ["status", Ecf.text("active")],
  )));
  return subgraphPath;
}

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

/** The int inside a `compute/result` at `path`, or null. */
function resultValue(tree: EntityTree, path: string): bigint | null {
  const entity = tree.get(path);
  if (entity === undefined || entity.type !== RESULT) return null;
  const value = Ecf.field(entity.data, "value");
  return value !== null && value.kind === "int" ? codec.ecfIntValue(value) : null;
}
