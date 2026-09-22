# Gate — `host-seam`

**Axis:** `host-seam`. **Authority:** `GUIDE-CONFORMANCE` §7d (arch, proposed) + the keystone peer
host contract H1/H2/H6/**H7** (keystone's, negotiated with us) + `ENTITY-CORE-PROTOCOL` §6.1 for the
entity-native path. **Runner:** none yet — see `../README.md`.

**Two probes, one per handler execution model.** `probe-seam.mjs` → model 2 (language-native body).
`probe-entity-native.mjs` → model 3 (compute-expression body). A peer's host state is not one column.

**This is a gate, not a demo.** It began as a one-off probe; a one-off probe that stays a one-off
probe is how an axis goes stale, so it lives here under a named axis with a named authority and it
runs on every composition that targets a peer whose host state is `unknown`.

**What it is not:** a substitute for keystone's harness. It measures one peer in one runtime. The
46-toolchain version is theirs.

## What it does

`probe-seam.mjs` is `GUIDE-CONFORMANCE` §7d in its smallest honest form, against one peer:

1. Construct a keystone peer **as a library**, importing only its published entry point — resolved
   *from* `package.json`'s `exports["."]` map rather than guessed (see below). No internals, no test
   hooks.
2. Install a language-native handler at `system/content` through the **public** `registerHandler`,
   with a nonce captured at registration time.
3. Report which of §11.6.1's writes the registration surface performed, by probing the tree.
4. Construct a second peer, `connect`, and send a real EXECUTE over TCP.
5. Assert the response carries **a value derived from a request field concatenated with the
   registration-time nonce** — which no `compute/literal` entity-native body can produce. That is the
   inattributability rule: it fails if the peer wrote the tree entities and then dispatched to
   something other than the installed callable.
6. **Run the negative control** — same probe, handler not installed. A check that cannot go RED
   measures nothing.
7. Probe whether the body can reach the connection's configured frame budget
   (`EXTENSION-CONTENT` §6.2 / §4.2 MUST).

## Result, `entity-core-keystone` read 2026-09-03 → 2026-09-04 (H6 landing)

```
§11.6.1 writes:  handler_entity yes · interface_entity yes · grant yes · types NO
Control A (installed):    200, witness=cycle-1:seam-witness-7f3a
Control B (not installed): 404, not_found
H1 MEASURED PASS · negative control discriminates · H2 yes · tree+contentStore yes
CONTENT §6.2 frame budget reachable:  NO  before H6 (read 2026-09-03)
                                     YES  after  H6 (read 2026-09-04)   ← this probe was NOT modified
```

**That last row is the useful one.** `frame_budget_reachable` is the field that raised H6 as a
finding; keystone shipped `ctx.frameBudget()` and it flipped on a re-run with **no change to this
file**. Their fix, our instrument, no coordination — which is what a gate is for.

`typescript` is the only peer above `unknown`, and this is why. See `AGENTS.md` **D13**.

## `probe-entity-native.mjs` — the other half of the same seam

`probe-seam.mjs` measures **model 2** (`SDK-OPERATIONS` §11.3): a language-native body installed
through the peer's own registration surface. `probe-entity-native.mjs` measures **model 3**: the body
is a compute expression in the tree, reached through `expression_path` per `ENTITY-CORE-PROTOCOL`
§6.1. Model 3 is the one that would let an extension be written **once** and run on 46 peers, so how
far it actually reaches is worth measuring rather than reading.

**Six controls across three scenarios.** Registers over the **wire** (`system/handler:register` with
an `expression_path`), dispatches over the wire, and — because *"the evaluator answered"* and *"the
evaluator was never asked"* are different failures — installs a live handler and calls it **directly**
as its own positive control. Scenario 3 installs an evaluator through the **H7 seam** and checks both
halves of its contract: that a richer body reaches it, and that the `compute/literal` floor does not.

### Result — `entity-core-keystone` read 2026-09-03 (before the H7 seam), then 2026-09-04 (after it)

```
Scenario 1 — nothing installed
A. body = compute/literal{42}                    200  value=42
B. body = compute/arithmetic{add,2,3}            501  unsupported_expression

Scenario 2 — a handler installed AT system/compute (deliberately not the seam)
C. body = compute/arithmetic{add,2,3}            501  unsupported_expression
D. that handler called directly                  200  witness returned
   evaluator invoked BY DISPATCH:  (none — never asked)

Scenario 3 — an evaluator installed THROUGH the H7 seam    [before H7: absent]
E. body = compute/arithmetic{add,2,3}            200  value=5      ← computed from the tree
F. body = compute/literal{42}   (the floor)      200  value=42
   evaluator invoked by dispatch:  evaluate:compute/arithmetic    ← and NOT for F
```

**Before the H7 seam landed this measured H7 absent** — the entity-native evaluator was not delegable, so model 3
meant `compute/literal` and nothing else. Sent to the peer generator's team.

**With the seam in place H7 is SATISFIED, by execution.** `Peer.setExpressionEvaluator` is consulted after the
built-in literal path and before the `501`. E's witness is **the computed sum `5`, read out of the
expression graph in the tree** — no constant-returning body and no `compute/literal` can produce it.
F is the safety property: the floor answers first and the evaluator is **never consulted for it**,
which is why installing one cannot move a conformance result.

**Scenario 2 is kept and still reports NO, deliberately.** Installing a handler *at `system/compute`*
is not the seam — `entity-core-go` does not route `expression_path` through a wire handler either.
Keeping it makes the distinction a measured negative instead of an assumption, and it is the control
that stops a future reader concluding the two are interchangeable.

Analysis: `docs/DESIGN-THE-COMPUTE-TRACK.md` §1.

The exit code is the **probe's** integrity, not the peer's verdict: `0` when the run was not vacuous
— register succeeded, the literal path worked, control D answered, and (where the seam exists) E and F
behaved. **A `501` on B and C is the finding, not a probe failure.** On a peer with no
`setExpressionEvaluator`, scenario 3 is reported **SKIPPED** and does not gate the exit — an absent
seam is a fact about the peer, not a broken probe.

## How the peer under test is resolved — and when these probes refuse to answer

Both probes share `peer-under-test.mjs`, which does two things neither should do by hand:

1. **Resolves through the manifest, not a guessed path.** `package.json`'s `exports["."]` is the
   packaging boundary; a type exported from `src/` but never re-exported to the package root is
   invisible to these probes, **which is the point** (D13's Access layer). `--dist` overrides it and
   the run says so, because an override does not exercise the boundary.
2. **Refuses to measure a stale build.** Newest `src/**` mtime versus newest `dist/**`; if `src` is
   newer the probe prints `unknown` and **exits 2**. *Exit 2 is not a verdict about the peer* — it is
   the probe saying it could not run. Adopted from `entity-core-keystone`, whose own instrument
   reported H7 unsatisfied against source that satisfied it after a planted-defect run left a mutated
   `dist/` on disk. **The guard has its own control** (a fixture with `src` newer than `dist`, which
   must exit 2 and print no verdict).

## Run it

```
node languages/typescript/gates/host-seam/probe-seam.mjs          [--peer-root <path>/typescript] [--dist <entry>]
node languages/typescript/gates/host-seam/probe-entity-native.mjs [--peer-root <path>/typescript] [--dist <entry>]
```

Defaults to the sibling keystone checkout. Needs the peer's `dist/` built (it ships built). Ran on
node 20.19.5 despite the package's `engines: >=24`, because nothing on this path uses a node-24 API —
do not read that as a supported configuration.

## Boundaries

- **Read-only against `entity-core-keystone`.** Nothing here writes to another team's tree, and the
  peer is never patched. If a peer cannot host what we generate, that is a finding about the seam,
  and it is routed.
- **One peer is one peer.** This probe measures `typescript`. It says nothing about the other 45 and
  is not a substitute for keystone's harness, which has to run in 46 toolchains — the part that is
  actually hard and is theirs.
