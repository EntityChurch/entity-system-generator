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

**One normative delta upstream, and one contract that does not exist yet.**

0. **The keystone peer host contract — the real gap.** A keystone peer is more than a core protocol
   peer: it is the foundation extensions install into, so it must *expose the hook points*. Core
   protocol does not require them and is right not to. **Measured, and it already bites:** `go` has a
   real dispatch index (`peer.go:414`) and `typescript` a public `registerHandler`; **`haskell`
   dispatches through a hardcoded `case` on the pattern string** (`EntityCore/Peer.hs:840–847`) with
   no index at all. **All three are fully conformant** — `system/handler:register` writes tree
   entities, and writing tree entities is not the same as having somewhere to bind a body. No gate
   distinguishes them. Generating an extension for Haskell would fail at the last step for a reason
   that is nobody's bug. See `DESIGN-WHERE-THE-LINE-IS.md`.

1. **Handler install (surface 1) — DRAFTED.** The corpus has three words for the party that installs
   a handler — §6.2's *"user-installed"*, §9.1's *"user"*, §11.6.7's *"application-owned"* — all
   meaning application code, so the **extension installer** is named nowhere. Every standard
   extension lives under `system/*`, so the wire path refuses all of them and the in-process path is
   authorized nowhere. `PROPOSAL-EXTENSION-HOST-INSTALL-SEAM` (`entity-system-architecture`, DRAFT).
2. **Nothing else.** A second delta was drafted for consumer registration and **withdrawn** after
   reading the trees: `emit` is the primitive and the registration mechanism is the implementer's,
   exactly as §1.2 says. Specifying it would have been arch inventing an API three implementations
   already ship.

**One finding routed rather than blocking.** `entity-core-go`'s `cmd/entity-peer/main.go:423–429`
wires `compute/reactive` *after* structural summaries and auto-version, where §2.2 puts it before
both — and **no conformance category tests consumer ordering**. Their tree, their call; the missing
check is D12 here. It is also the clearest argument for generating the wiring: the composition is a
hand-maintained options list and the spine is a nine-row table in an 859-line spec.

## What is next here, and it depends on neither

- **The dispatch-surface census** — per peer, by source read: is there a dispatch index reachable
  after construction, or a hardcoded switch? Is there a consumer registration point? This sizes
  everything else. See `DESIGN-WHERE-THE-LINE-IS.md` §2 for why a grep will not settle it.
- **The keystone peer host contract**, drafted off that census and routed to keystone as a base
  requirement.
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
