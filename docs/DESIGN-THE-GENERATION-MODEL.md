# The generation model

How this repo builds core peers with core extensions on them: what the unit of generation is, what
an extension actually consists of, how the pieces get wired together, and what has to land first.

---

> **Companions.** `DESIGN-WHERE-THE-LINE-IS.md` — the four-way responsibility split (core protocol ·
> arch · keystone · here · the profile), the consumption modes, and the routing test for gaps. Read
> that one first if the question is *"whose requirement is this."*
> `DESIGN-THE-SYSTEM-STRUCTURE.md` — where things live across the three axes, and the ten isolation
> invariants with their enforcement points. `DESIGN-THE-COMPOSITION-LOADER.md` — what S3.5′ actually
> emits: the resolve/refuse algorithm, the init program's exact order, and its failure semantics.

## 1. What we generate is a **system**, not an extension

The unit is a **composition**: one core peer, in one language, with a declared set of extensions
installed and wired. That is what "entity system" means here, and it is the thing that gets built,
gets a conformance number, and ships.

```
system manifest                      →  entity-system-generator  →  a running system
  core: peer(lang=go, spec=0.8.2.3)                                    │
  extensions: [CONTENT, HISTORY]                                       ├─ per-extension modules
  profile: <language + host capability>                                └─ ONE COMPOSITION ENTRY POINT
```

**The core peer is pulled in as a package, never regenerated.** Keystone's S5 already emits real
package metadata — `entity-core-protocol-rust` `0.1.0-pre` (`Cargo.toml`),
`entity-core-protocol-typescript` `0.1.0` (`package.json`, full `exports` map),
`entity-core-protocol-go` (Go module, versioned by tag) — so an extension module simply declares a
dependency on it: a path/workspace dep in development, a registry dep at release. Additive, in the
ordinary sense every language already has a word for.

The composition entry point is the output that matters and the one that is easy to miss. It exists because of
`SYSTEM-COMPOSITION` §1.2:

> *"Ordering is by registration order. The peer initialization code registers consumers in the order
> specified by §2.2. No runtime priority dispatch is needed — static ordering at init time is
> sufficient. **The peer builder/wiring code is responsible for registering consumers in the correct
> order.**"*

**Composition is decided at init time, statically.** So a system is not "a peer plus some modules you
can load"; it is a peer plus a *program* that installs them in one normatively-fixed order. That
program is generated, and generating it correctly is the core problem this repo solves.

## 2. An extension has three surfaces, and all three have a mechanism

This is the fact that shapes everything else.

| # | Surface | What it is | How it is installed |
|---|---|---|---|
| 1 | **Handler** | an EXECUTE dispatch target at `system/{ext}`, with operations | `SDK-OPERATIONS` §11.6 `register_handler`; in `entity-core-go`, `peer.WithHandler(pattern, h)` |
| 2 | **Emit consumer** | a processing function on the tree-change and/or content-store pathway | **the implementer's own registration mechanism.** In `entity-core-go`: `AddNamedSyncHook(name, fn)` / `AddNamedSyncHookWithPattern`, surfaced as `peer.WithNamedSyncHook` / `WithNamedContentHook` / `WithBindingHook` |
| 3 | **Entity types** | definitions at `system/type/*` | `HandlerSpec.types` (§11.6.1) |

**Surface 2 is built, not missing.** `emit` is the primitive — `SYSTEM-COMPOSITION` §1.1 — and the
registration API around it is implementation-defined, which is exactly what §1.2 means by *"the peer
builder/wiring code is responsible for registering consumers in the correct order."* Measured at
`entity-core-go` `7262f17`: `core/store/notifying.go` wraps the location index and fires consumers on
every `Set`/`Remove`, with `AddNamedSyncHook` at `:105`, the pattern-filtered variant at `:115`,
the content-event equivalent in `notifying_content.go:39`, cascade-halt on a non-200 consumer result,
and `SetMaxCascadeDepth` / `SetEmitSuppressed`. The builder options are
`core/peer/builder.go:291–350`; `core/peer/peer.go:216–231` installs them.

**So the generator does not need a new spec primitive for surface 2.** It needs to know each peer's
registration API — which is a **profile fact**, exactly like the codec strategy or the concurrency
idiom, and belongs in `profile.toml` next to them.

The consequences that made surface 2 look like a gap are all real and all already handled:

- **§2.7 consumer-only extensions** (persistence — *"there is no `system/persistence` handler"*) are
  a `WithNamedSyncHook` with no `WithHandler`. Nothing special.
- **§2.6 both-surface extensions** — QUERY's handler serves explicit EXECUTEs while a separate sync
  hook maintains the indexes — are two registrations from one module. `entity-peer` does exactly
  this today.
- **Position is a composition property** (§2.4), and it is expressed as *registration order in the
  options list*. That is the whole mechanism, and §3 is why getting it right is the generator's job.

## 3. The composition spine — normative, global, fixed

`SYSTEM-COMPOSITION` §2.2 fixes the tree-change consumer order for every peer:

```
0. Entity persistence     transparent          (conditional — absent if memory-only)
1. Query indexes          transparent
2. Clock context          transparent
3. Clock persistence      bounded reactive     self-guarded
4. History                bounded reactive     self-guarded
5. Compute                unbounded reactive   convergence-checked
6. Structural summaries   bounded reactive     self-guarded
7. Auto-version           bounded reactive     self-guarded via `exclude` (REVISION)
8. Subscription           unbounded reactive   delivers via inbox
```

plus a separate content-store event list: `0. Persistence · 1. Query content indexes`.

**Three consequences for the generator, all load-bearing:**

1. **Position is a property of the composition, not of the extension.** §2.4: *"the ordering applies
   to whichever consumers are present — absent consumers are simply not in the list."* So the
   generator resolves positions from the declared extension set, and the same extension gets a
   different concrete slot in different systems.
2. **Ordering has normative constraints beyond the list.** `EXTENSION-REVISION`: *"Implementations
   MUST NOT register auto-version at positions ≤ 6 or at the same position as subscription."*
   Auto-version MUST fire before subscription, because a subscriber must not see a change without
   its version entry. **These are checkable at generation time** and are the first thing the wiring
   generator validates.
3. **Third-party consumers slot by classification, not by number** (§2.3) — state maintenance before
   history, audit before compute, reactive before summaries, notification last. That table is the
   rule the generator applies when an extension's position is not one of the nine.

**Composing is therefore not "install N independent things."** It is threading N consumers into one
ordered pipeline that shares a cascade counter, has convergence rules, and where a wrong order is an
observable inconsistency rather than a crash. **That is the interesting problem, and it is already
specified — we implement it, we do not design it.**

### 3.1 The hand-written wiring already diverges, and nothing catches it

The reference composition is `entity-core-go`'s `cmd/entity-peer/main.go:423–429` — a functional
options list. Registration order is execution order (`core/store/notifying.go:275`, no sort
anywhere), so the wired order at `7262f17` is:

| Wired | Hook | §2.2 says |
|---|---|---|
| 1 · 2 · 3 | `query/index-maintainer` · `clock/advancement` · `history/recorder` | 1 · 2–3 · 4 ✓ |
| 4 | `tree/root-tracker` | **6** — structural summaries |
| 5 | `revision/auto-version` | **7** |
| 6 | `compute/reactive` | **5** |
| 7 | `subscription/notification` | 8 ✓ |

**Compute runs after summaries and auto-version; §2.2 puts it before both**, and gives the reason
directly: *"running compute before structural summaries and subscription ensures derived state has
settled before summaries and notifications reflect it"*, and *"auto-version reads the tracked root
maintained by structural summaries at position 6 — the summary MUST have settled before auto-version
reads it."*

Stated carefully: compute's writes cascade recursively and fire the full list at their own depth, so
summaries and version entries do eventually reflect derived state. What the wired order changes is
the **outermost** pass — a summary and a version entry produced from a root that does not yet include
the writes compute is about to make. §2.2 asserts that intermediate state is the thing the ordering
exists to prevent being observed.

**This is `entity-core-go`'s tree; the finding is routed, not ruled.** They may have a reason. What
is not in doubt is that **no conformance category tests consumer ordering** — 68 of them, none — and
this has sat in the reference peer unnoticed.

> **It is also the clearest statement of why this repo exists.** The composition is a hand-maintained
> options list; the spine it must match is a nine-row table inside an 859-line spec, with constraints
> stated in prose three sections away. **A generated wiring program cannot get that wrong. A
> hand-written one already has.**

## 4. The dependency closure — computed, not guessed

Every extension declares its prerequisites in a machine-readable `**Depends**:` line. Parsed across
all 26 (mandatory deps only; ENCRYPTION's tiered deps are optional and excluded):

| Extension | Required closure | Cost |
|---|---|---|
| `ATTESTATION` `CLOCK` `COMPUTE` **`CONTENT`** `CONTINUATION` `DISCOVERY` `DURABILITY` `ENCRYPTION` **`HISTORY`** `INBOX` `RELAY` `ROLE` `ROUTE` **`TREE`** `TYPE` | — | **0** |
| `QUORUM` · `REGISTRY` | ATTESTATION | 1 |
| `SUBSCRIPTION` | INBOX | 1 |
| `SUBSTITUTE` | CONTENT | 1 |
| `REVISION` · `TRANSACTION` | TREE | 1 |
| `IDENTITY` | ATTESTATION, QUORUM | 2 |
| **`QUERY`** | INBOX, SUBSCRIPTION | 2 |
| `NETWORK` | CONTINUATION, INBOX, SUBSCRIPTION | 3 |
| `GROUP` | ATTESTATION, IDENTITY, QUORUM, ROLE | 4 |
| `SIGNALING` | CONTINUATION, INBOX, NETWORK, SUBSCRIPTION | 4 |

**The graph is shallow — 15 of 26 have no extension prerequisite at all.** So "which extension
first" is not constrained much by dependencies, and the ordering below is derived from *seams*
instead.

## 5. Any extension, on its own — modularity is the point

**Extensions are modular and independently installable. Core protocol plus TREE alone is a system.
Core plus CONTENT alone is a system. Core plus HISTORY alone is a system.** There is no prescribed
order and this document does not have an opinion about which one gets built first — that is a call
made per build, not a property of the design.

The only thing the design owes is that **a declared dependency is honoured**, and §4 is that table:
15 of 26 have none at all, and the deepest closure is four. So the resolver's job is small — take the
requested set, pull in whatever the `**Depends**:` lines mandate, and refuse a composition that
cannot be satisfied.

Two facts a build should know going in, neither of them an ordering:

- **`TREE` and `TYPE` extend an already-bootstrapped core handler** rather than owning a fresh
  pattern — TREE's §9 adds operations to core's `system/tree`. That collides at `409` under
  §11.6.1's rule, so building TREE means resolving that first (arch-owed, proposal-first); it is not
  a reason to build something else instead.
- **`NETWORK` · `SIGNALING` · `REGISTRY` are service-owning** and need §11.6.9's start/stop
  lifecycle. That is extra machinery, not a blocker.

## 6. What is already built — measured, not assumed

At `entity-core-keystone` `5a53b75`:

- **Peers are constructible in-process.** `go` exports `NewPeer(seed, opts...) (*Peer, error)`;
  `rust` has `pub struct Peer`; `typescript` `export class Peer`. `ruby`, `dart`, `elixir`, `swift`,
  `prolog` ship real packaging manifests. The library half is done incidentally, because S1 makes
  each pod idiomatic and idiomatic means *a package*.
- **The dispatch fork exists.** `go/src/peer/peer.go:413–420` prefers the native dispatch index and
  falls through to an `expression_path` body. Same in `rust` `core.rs:1117` and `typescript`.
- **Three of §11.6.1's four mutations are implemented and gated.** `handlers.go:499` writes the
  handler entity, `system/type/*` entries, the self-issued grant plus signature, and the interface
  entity. An eleven-check `core_register_*` family — with a mutation-tested negative half — passes in
  all 46 peers' `CONFORMANCE-REPORT.json`.

**What is missing is narrow and specific:** §11.6.1 step 4 (bind the *language-native* body), and
all of surface 2. The existing `core_register_body_binding` check binds an **entity-native**
`compute/literal` body, because that is the only body kind a wire oracle can install — and a
`compute/literal` cannot be a CONTENT handler.

## 7. The pipeline

| Keystone | Here | Notes |
|---|---|---|
| — | **S0′ Resolve** | read the system manifest; compute the transitive dependency closure; assign consumer positions from §2.2; **validate the ordering constraints**; reject an invalid composition here rather than at runtime |
| S1 Profile | **S1′ Profile** | language *and host capability* — does this peer support runtime registration, or is it `declined`? |
| S2 Codec | **— dropped** | the peer owns the canonical encoder. An extension needing its own encoding is a spec defect, not a phase |
| S3 Peer | **S3′ Modules** | per (extension × language): handler body, consumer functions, type definitions |
| — | **S3.5′ Wire** | emit the composition program — construct, register handlers, register consumers **in resolved order**, start |
| S4 Conformance | **S4′ Conformance** | the extension categories for the declared set, **plus a re-run of the core 16 to prove nothing regressed** |
| S5 Publish | **S5′ Publish** | same |

**S2 dropping is the single biggest economy.** Roughly a third of keystone's per-language difficulty
is the canonical CBOR encoder — length-then-lex map ordering, shortest-float including f16,
decode-side minimality, recursive tag rejection. **An extension inherits all of it free.**

**S4′'s second clause is the failure mode keystone never has.** Keystone's is *the peer is wrong*.
Ours is *the peer was right and we broke it* — a regression in the core 16 caused by installing
something. Every run re-measures both halves.

## 8. The matrix — 26 × 46 is not a plan

1,196 targets is not a number anyone runs, and pretending otherwise is how this becomes a
treadmill. **Two independent axes, and only one of them scales by generation:**

- **Extensions** grow the *specification* surface: 30,795 lines and 1,338 MUST tokens versus core's
  8,467 / 336. Each new extension is genuine new reading, and it is where the spec defects surface.
- **Languages** grow the *mechanical* surface. Once an extension is expressed against the host API,
  a further language is a port of a known thing.

**The two axes cost different things, so a build picks a point on each rather than sweeping both.**
Whichever extensions are wanted, in whatever language set is wanted — the constraint is that widening
both at once turns a spec defect found in language 1 into 45 regenerations before it is understood. A
language whose profile declares `registration = "declined"` is out of scope for hosted extensions by
declaration, not by failure.

## 9. Conformance

`validate-peer` (`entity-core-go`, 66,651 lines, 68 categories) already splits the right way: **16
are `--profile core`** — keystone's gate — and **52 are the extension surface**. Our gate is the
complement of theirs, not a blank page.

Two known defects block automating it, both already arch's own written recommendation in
`GUIDE-CONFORMANCE` §8: skips key on grant-coverage rather than **extension presence**, and there is
no per-extension profile scoping (§7 already requires scoping *"to the declared level + extension
set"*). **Do not extract the suite as an opening move** — it is the oracle *because* it is not the
thing under test, both fixes are internal to it either way, and 66k lines should not move on a
hypothesis. Make one extension category presence-keyed and scoped, run a generated system against it,
and let that measurement decide.

**And the composition needs its own checks, which nothing has today.** Consumer *ordering* is
observable — `SYSTEM-COMPOSITION` §2.2 says reversing positions 7 and 8 produces *"subscribers seeing
a change without a version entry"* — so it is testable over the wire, and no category tests it.

## 10. What is owed before the first system

| # | Item | Owner |
|---|---|---|
| 1 | The §11.6 handler seam: scope §6.2's reservation to the dispatch path, name the extension installer, make a decline declared | `entity-system-architecture` — **DRAFTED**, `PROPOSAL-EXTENSION-HOST-INSTALL-SEAM` |
| 2 | Phase contract + a `[host]` profile block carrying **both** registration APIs (handler and consumer) + the host-seam harness, then regenerate | `entity-core-keystone` |
| 3 | The host-seam conformance transport, with both controls | `entity-core-go` |
| 4 | One extension category made presence-keyed and profile-scoped | `entity-core-go` |
| 5 | **A consumer-ordering conformance check**, and a look at `entity-peer`'s wiring (§3.1) | `entity-core-go`; spec side is D12 here |
| 6 | **The keystone peer host contract** — what a peer must expose to be an extension foundation (`DESIGN-WHERE-THE-LINE-IS.md` §4) | drafted **here** off the census, routed to `entity-core-keystone` |
| 7 | The S0′ resolver — dependency closure, position assignment, constraint validation | **here** |

**There is no owed item for consumer registration.** That was drafted as D11 and withdrawn: `emit` is
the primitive and the registration API is the implementer's, which `entity-core-go` has built. What
the generator needs is to *know* each peer's API, and that is a profile fact — item 2.

Item 7 is buildable now and depends on nothing above — the dependency graph is already
machine-readable in the corpus (§4 was computed from it). Item 6 needs the dispatch-surface census
first, which is a source read across the peers and is the next thing to do.

**The specs are read out of `entity-system-architecture` in this checkout.** Copy them if a copy is
convenient. There is no snapshot ceremony here and it blocks nothing.

---

## 11. The cycle, traced end to end

`CONTENT` onto keystone's `go` peer, walked step by step against real artifacts, to find where the
process breaks before anyone builds it. **Three steps are blocked and all three have owners.**

| Step | What happens | State |
|---|---|---|
| **S0′ Resolve** | Read the requested set `[CONTENT]`. Parse `**Depends**:` — `ENTITY-CORE-PROTOCOL v7.51+`, `ENTITY-CBOR-ENCODING v1.4+`, **no extension prerequisite**. Assign consumer positions: CONTENT registers none. Validate ordering constraints: none apply | ✅ **runs today.** The graph is machine-readable; this is the one component with no external dependency |
| **S1′ Profile** | Language `go`; host bindings — handler registration call, body shape, module unit | ⚠️ **the `[host]` block does not exist.** H5. Mechanical once the contract lands |
| **S2 Codec** | — | ✅ **dropped.** CONTENT inherits the peer's canonical ECF encoder. This is where a third of keystone's per-language cost went |
| **S3′ Modules** | Author the `system/content` handler from `EXTENSION-CONTENT` v3.6 §4.2 + §10.3 — `get` over `system/content/*`, the blob/chunk entity types, FastCDC chunking (§3.6), `reassemble_content` (§4) | ✅ **nothing blocks authoring.** This is ordinary spec-reading work, the same loop keystone runs |
| **S3.5′ Wire** | Emit the composition entry point: construct the peer, install the handler, start | ❌ **blocked twice.** The peer's dispatch index is unexported (H1 is satisfied in `go` but not *exposed*, H3), and installing at `system/content` is refused by §6.2's unscoped reservation (D1) |
| **S4′ Conformance** | Run `validate-peer`'s `content.go` category against the composed peer, then re-run the core 16 to prove nothing regressed | ⚠️ **the category exists** — one of 103 files under `cmd/internal/validate/` — but presence-keyed skips and per-extension profile scoping are open defects in the harness |
| **S5′ Publish** | Package metadata, README, conformance badge | ✅ **inherited from keystone's S5 unchanged** |

### 11.1 What the trace establishes

**The pipeline is sound and the blockers are all at one seam.** S0′ runs today, S2 is free, S3′ is
ordinary work, S5′ is inherited. Everything that blocks sits at **S3.5′ — installation** — and it is
the same two items already filed: the host contract (H1/H3/H5) and D1's authorization scoping.

**Nothing in the trace required inventing a mechanism.** That is the useful result. The earlier
instinct — that composition needed new spec surface — was wrong twice over; what it needs is one
scoping fix to an existing MUST and one exposure requirement on the peers.

### 11.2 What the trace does not prove

- **CONTENT has no emit consumer**, so the trace never exercises `SYSTEM-COMPOSITION`'s ordering —
  the part with the most design risk and the part where the reference peer already diverges (§3.1).
  A second cycle with `HISTORY` (one consumer, position 4) is what tests it.
- **`go` already has an index.** The trace does not test the H1 change; `rust` is the peer that does.
- **CONTENT's spec is thinner-tested than most** — its own header reads *"Conformance grade: Draft.
  No cross-impl validation pass yet. Reference impls pending."* Generating it would be the first
  cross-impl validation the extension has ever had. **That is the generator doing its job**, and it
  means spec defects should be expected rather than treated as pipeline failures.
