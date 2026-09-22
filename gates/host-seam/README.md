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

1. Construct a keystone peer **as a library**, importing only its published entry point — the
   prebuilt `dist/src/index.js`, which is what `package.json`'s `exports` `.` map resolves. No
   internals, no test hooks.
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

## Result, keystone `4821b09`

```
§11.6.1 writes:  handler_entity yes · interface_entity yes · grant yes · types NO
Control A (installed):    200, witness=cycle-1:seam-witness-7f3a
Control B (not installed): 404, not_found
H1 MEASURED PASS · negative control discriminates · H2 yes · tree+contentStore yes
CONTENT §6.2 frame budget reachable: NO
```

`typescript` is the only peer above `unknown`, and this is why. See `AGENTS.md` **D13**.

## `probe-entity-native.mjs` — the other half of the same seam

`probe-seam.mjs` measures **model 2** (`SDK-OPERATIONS` §11.3): a language-native body installed
through the peer's own registration surface. `probe-entity-native.mjs` measures **model 3**: the body
is a compute expression in the tree, reached through `expression_path` per `ENTITY-CORE-PROTOCOL`
§6.1. Model 3 is the one that would let an extension be written **once** and run on 46 peers, so how
far it actually reaches is worth measuring rather than reading.

Four controls. Registers over the **wire** (`system/handler:register` with an `expression_path`),
dispatches over the wire, and — because "the evaluator answered" and "the evaluator was never asked"
are different failures — installs a live evaluator at `system/compute` and calls it **directly** as
its own positive control.

### Result, keystone `46d599b`

```
A. body = compute/literal{42}                    200  value=42
B. body = compute/arithmetic{add,2,3}            501  unsupported_expression
C. same, with a live handler at system/compute   501  unsupported_expression
D. that handler called directly                  200  witness returned
   evaluator invoked BY DISPATCH:  (none — never asked)
```

**H7 measured on this peer: the entity-native evaluator is not delegable.** Model 3 here means
`compute/literal` and nothing else, and installing `EXTENSION-COMPUTE` would not widen it. Routed
(`docs/status/ROUTING-2026-09-03-b-*`); analysed (`docs/DESIGN-THE-COMPUTE-TRACK.md`).

The exit code is the **probe's** integrity, not the peer's verdict: it is `0` when register succeeded,
the literal path worked, and control D answered — i.e. when the run was not vacuous. A `501` on B and
C is the finding, not a probe failure.

## Run it

```
node gates/host-seam/probe-seam.mjs          [--dist <path>/typescript/dist/src/index.js]
node gates/host-seam/probe-entity-native.mjs [--dist <path>/typescript/dist/src/index.js]
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
