# Status

The rolling log. One file, not dated — the dated snapshots under `docs/status/` are internal.

---

## Where this is

**Bring-up. Nothing is generated yet, and that is the honest state.**

The repo exists and the design is written (`DESIGN-THE-GENERATION-MODEL.md`). No system has been
generated, no conformance number exists, and there is nothing here to claim.

## What is established

- **The unit of generation is a *system*** — one core peer, one language, a declared extension set,
  and a generated **wiring program** that installs them in the normative order. Composition is
  static at init time (`SYSTEM-COMPOSITION` §1.2: *"the peer builder/wiring code is responsible for
  registering consumers in the correct order"*), so the wiring is a build artifact, not a runtime
  loader.
- **An extension has three surfaces and all three have a mechanism.** Handler (`SDK-OPERATIONS`
  §11.6) · **emit consumer** — `emit` is the primitive (`SYSTEM-COMPOSITION` §1.1) and the
  registration API is the implementer's, which is what §1.2 means; `entity-core-go` built it as
  `AddNamedSyncHook` / `WithNamedSyncHook` (`7262f17`) · entity types (`HandlerSpec.types`). **The
  generator needs to know each peer's registration API — a profile fact, not a spec gap.**
- **The composition spine is already normative** — §2.2's nine ordered consumer positions with their
  classes, a separate content-event list, and ordering *constraints* (auto-version MUST precede
  subscription, or subscribers see a change with no version entry). **We implement it; we do not
  design it.**
- **The dependency graph is machine-readable and shallow.** Every extension declares a `**Depends**:`
  line; parsed across all 26, **15 have no extension prerequisite at all**, and the deepest closure is
  four. So the resolver's job is small: honour what is declared, refuse what cannot be satisfied.
- **The two-generator split.** `entity-core-keystone` generates core peers from the three core spec
  files; this repo generates the layer above. The boundary is the input snapshot, and it is the
  correct seam rather than a limitation.
- **The phase model retargets cleanly** — S0′ resolve, S1′ profile, S3′ modules, S3.5′ wire, S4′
  conformance, S5′ publish — with **S2 (codec) dropped entirely**, because an extension inherits the
  peer's canonical encoder. Roughly a third of keystone's per-language difficulty, gone for free.
- **The handler half of the seam is smaller than it looked.** Of §11.6.1's four mutations, three are
  implemented **and gated** across all 46 peers by an eleven-check `core_register_*` family. The
  fourth — bind the *language-native* body — is missing because it is the only one a wire oracle can
  never drive: the existing body-binding check installs an entity-native `compute/literal`, and a
  `compute/literal` cannot be a CONTENT handler.
- **The conformance surface is the complement of keystone's**, not a blank page: 52 of
  `validate-peer`'s 68 categories are extension categories. **Our second failure mode is one keystone
  never has** — *the peer was right and we broke it* — so every run re-measures the core 16 too.
- **Extensions are modular and independently installable, and there is no prescribed order.** Core
  plus TREE alone is a system; core plus CONTENT alone is a system. The design owes only that a
  **declared** dependency is honoured. Two facts a build should know, neither of them an ordering:
  `TREE` and `TYPE` extend an already-bootstrapped core handler and collide at `409` under §11.6.1
  (arch-owed, proposal-first), and `NETWORK` / `SIGNALING` / `REGISTRY` are service-owning and need
  §11.6.9's start/stop lifecycle.

## What is blocking

**Nothing blocks the first cycle. That was wrong when it was written and is corrected.**

`ENTITY-CORE-PROTOCOL` §6.2 L3140 carves bootstrap out — *"Bootstrap handlers bypass this — they exist
before the capability system (§6.9)"* — and in the peers the reserved-pattern guard has exactly one
call site, inside the **wire** `register` operation (`go/src/peer/handlers.go:495,505`). A composition
program that constructs the peer and installs before listening is the bootstrap class. **H1 + H3 alone
unblock it.** D1 still lands for the wire/remote install story; it gates nothing here.

**Keystone has accepted H1–H5** (`HANDOFF-TO-GENERATOR-2026-09-02`, their tree) and is doing the H4
survey, the `[host]` profile blocks, the roster column, and the `go`/`rust` exposure work.

**The decision that was gating the first build is made, by measurement rather than by choice.** The
bar is `SDK-OPERATIONS` §11.6, not a raw map write: dispatch resolves a pattern by walking the tree
for a `system/handler` entity, so a handler with no §11.6.1 entities returns `404` whatever the index
holds. The registration surface owns the writes; **the generated composition does not perform them.**

**And the peer that decision was framed around does not host anything.** `julia`'s exported
`register_handler!` writes a container **nothing reads** — S3 residue orphaned by S4's rewrite to
store-based dispatch. It was arch's own nominated control and it is retracted. **`typescript` and
`csharp` are the controls**: both public, both read at dispatch, both already writing three of
§11.6.1's four artifacts. What the cohort is missing is now narrow and identical in both — `types`,
the `409`, and the handle lifecycle.

## What is next here, and it depends on neither

- ✅ **The dispatch-surface census** — `CENSUS-DISPATCH-SURFACE.md`, 12 peers; keystone has since
  measured all 26 M1/M2/M3 and is carrying the rest as `[host]` profile values rather than a table.
  **Roster reads `unknown` for all 46 until a harness executes** — their rule and the right one.
- ✅ **The host contract** — `DRAFT-KEYSTONE-PEER-HOST-CONTRACT.md`, H1–H5, routed and **accepted**,
  with three corrections from keystone and two back to them (`cpp`'s `register_handler` is private;
  `julia`'s writes a dead map). **It is keystone's document** — a requirement on keystone peers,
  settled between keystone and here, with arch not a party. What stays arch's is `SDK-OPERATIONS`
  §11.6 and `GUIDE-CONFORMANCE` §7d, which bind every SDK rather than only keystone's peers.
- **`typescript` × `CONTENT` — the first build.** Zero peer changes, a live seam verified at the
  resolution site, and the runtime where "use it as a library" is the normal case. `csharp` is the
  second zero-change peer, so a generator bug and a peer bug stay separable on the first cycle.
- **The S0′ resolver** — dependency closure, consumer-position assignment, ordering-constraint
  validation. The graph is already machine-readable in the corpus.

Specs are read out of `entity-system-architecture` in this checkout; copy them if convenient.

## What this repo will not do

- **Fork a peer.** If a generated peer cannot host what we generate, that is a finding about the seam
  or the phase contract, and it is routed. A patched peer ends the property that makes the cohort
  worth anything.
- **Close a spec gap locally.** `entity-system-architecture` is the spec authority. Ambiguities route
  there as spec issues.
- **Treat its own output as evidence.** N generated implementations of one extension are N copies of
  one reading — generation lineage, not convergence.
