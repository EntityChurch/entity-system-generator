# Status

The rolling log. One file, not dated — the dated snapshots under `docs/status/` are internal.

---

## Where this is

**The first extension is generated, composed onto a peer, and measured. `ts-content` exists.**

`CONTENT` v3.6 in `typescript`: handler, types, chunking and SDK surface, installed into a
keystone-generated peer through a wiring program, gated by `entity-core-go`'s `validate-peer`.

**The number, with its breakdown, and never as a percentage.** Of the oracle's 13 `content` checks:
**8 measure this handler and 8 pass**; 4 more pass without contacting the peer at all (two build an
in-memory store, two call `ValidateDescriptor` in-process); 1 skips for want of a `local/files` root
to seed >16 MiB of content, so **the Amendment 1 frame-budget MUST is unexercised**. The 8/4/1
split was predicted in `SYSTEM.toml [gate.expectation]` before the run and the run matched it.
Report: `compositions/ts-content/status/CONFORMANCE-2026-09-05.md`.

**The regression guard is 0, measured rather than asserted.** Two arms — the peer's own host and the
composed host, same oracle, same flags, same container, same staged `dist/`, one variable — over the
full 756-check `--profile core`. No check went `PASS → non-PASS`. Six went the other way:
`type_system.type_system_content_{blob,chunk,descriptor}_{fetch,match}`, `WARN → PASS`, with the
`_match` half reporting `content hash match` — the Go oracle's own transcription of §2.1/§2.2/§2.4
rendered byte-identically to ours. **Two independent readings agreeing, not N**, and it says nothing
about chunking convergence. And 336 core checks are already non-PASS on the bare peer; that is now a
diff rather than the word "pre-existing", which [ADR-0012] does not accept without a bisect.

**`python` is tier A, measured, before a line was generated.** `gates/host-seam/probe-seam.py` runs
four controls, not two: install + reach with a witness derived from a request field *and*
registration-time state; nothing installed → RED; tree bound but the dict unset → `501`, proving
which container dispatch consults; and the dict set with the tree unbound → `404` with the body's
invocation counter at zero, then the same body answering `200` when called directly. That last one
distinguishes *installed and never asked* from *not installed*, which is the failure this repo
shipped once already.

**Three things the build turned up and routed, one line each.** CONTENT's Amendment 1 §6.2 MUST is
**unimplementable on the `python` peer** — nothing on the connection, context, peer or store carries
a frame budget, and `wire.MAX_FRAME` is a module constant equal to the exact 16 MiB literal the
amendment names as the wrong answer. keystone's `Handler.operations` is `readonly string[]`, so
**§6.1's manifest cannot be published through `registerHandler`** (we re-write the interface entity
afterwards). And the `typescript` **client** API discards `envelope.included` from a response, so a
consumer written against this peer's own client surface cannot receive content — the server side is
correct and conformance is unaffected.

**The two seam probes that preceded all of this still stand**, and they were the first measurements
of the extension host seam anywhere in this ecosystem. `gates/host-seam/probe-seam.mjs` installs a
language-native handler into the generated `typescript` peer through that peer's public registration
surface, then reaches it with a real EXECUTE over TCP — asserting a response value derived from a
request field *and* registration-time state, so a peer that merely wrote the right tree entities
cannot pass. The negative control goes RED. **That peer's model-2 host obligations are green by
execution; every other peer reads `unknown`, and will until something executes.**

`gates/host-seam/probe-entity-native.mjs` measures the **other** execution model on the same peer.
It first measured a limit — the entity-native path evaluated `compute/literal` and answered `501` to
anything richer, with an installed evaluator live, directly callable, and never consulted. That was
**H7**, and it retracted a claim of ours that had already been routed. **Keystone closed it the same
day**, and the re-measurement is the good half: an evaluator installed through the new seam answers a
`compute/arithmetic` body **`200 value=5`, computed from operands read out of the tree**, while the
`compute/literal` floor still answers first and the evaluator is never consulted for it. **H6 closed
in the same round** — our *unmodified* `probe-seam.mjs` flipped `frame_budget_reachable` to `true`
without our touching it, which is the strongest kind of corroboration available: their fix, our
instrument, no coordination.

**Both probes now resolve the peer through its `package.json` `exports` map and refuse to run against
a stale `dist/`**, reporting `unknown` (exit 2) rather than a verdict — adopted from keystone, who
caught their own instrument measuring a build nobody asked for. The guard has its own control.

## What is established

- **The unit of generation is a *system*** — one core peer, one language, a declared extension set,
  and a generated **wiring program** that installs them in the normative order. Composition is
  static at init time (`SYSTEM-COMPOSITION` §1.2: *"the peer builder/wiring code is responsible for
  registering consumers in the correct order"*), so the wiring is a build artifact, not a runtime
  loader.
- **An extension has three surfaces and all three have a mechanism.** Handler (`SDK-OPERATIONS`
  §11.6) · **emit consumer** — `emit` is the primitive (`SYSTEM-COMPOSITION` §1.1) and the
  registration API is the implementer's, which is what §1.2 means; `entity-core-go` built it as
  `AddNamedSyncHook` / `WithNamedSyncHook` · entity types (`HandlerSpec.types`). **The
  generator needs to know each peer's registration API — a profile fact, not a spec gap.**
- **The composition spine is already normative** — §2.2's nine ordered consumer positions with their
  classes, a separate content-event list, and ordering *constraints* (auto-version MUST precede
  subscription, or subscribers see a change with no version entry). **We implement it; we do not
  design it.**
- **The dependency graph is machine-readable and shallow.** Every extension declares a `**Depends**:`
  line; parsed across all 26, **14 name no other extension at all** and a 15th names them only as
  optional, with the deepest closure at four. So the resolver's job is small: honour what is declared,
  refuse what cannot be satisfied — and **distinguish required from optional**, because `ROLE`'s
  attestation and identity dependencies are explicitly tier-conditional and a closure that treats them
  as mandatory pulls two extensions into every composition that contains ROLE.
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
- **The host contract is H1–H7, and it is keystone's document.** H1/H2/H6/H7 are satisfied on
  `typescript` **by execution**, measured independently by both seats' instruments. The other 45 read
  `unknown`. **A packaging fact is not a capability and a source read is not a measurement** — four
  control nominations across this ecosystem were made from source and three were wrong.
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

**The `typescript` peer can host everything build 1 needs, measured by execution:** a handler
installed after construction and reached by dispatch, an emit consumer, the connection's frame budget
readable from a body (`ctx.frameBudget()`), and a delegable expression evaluator
(`Peer.setExpressionEvaluator`). **Every other peer reads `unknown`.**

**Nothing on our critical path waits on anyone.** Build 1 and build 3 are unblocked.

**The decision that was gating the first build is made, by measurement rather than by choice.** The
bar is `SDK-OPERATIONS` §11.6, not a raw map write: dispatch resolves a pattern by walking the tree
for a `system/handler` entity, so a handler with no §11.6.1 entities returns `404` whatever the index
holds. The registration surface owns the writes; **the generated composition does not perform them.**

**And the peer that decision was framed around does not host anything.** `julia`'s exported
`register_handler!` writes a container **nothing reads** — S3 residue orphaned by S4's rewrite to
store-based dispatch. It was arch's own nominated control and it is retracted.

**`csharp` is retracted too, 2026-09-03, and that one was ours.** `Peer.cs:23` is
`internal sealed class Peer`; the `public RegisterHandler` we cited is a public member of an
inaccessible class, and **every type in the assembly is `internal`** except ten exception classes and
`PeerId` — so the body type cannot be named either. It fails H1, H1's body half, and H4, while
shipping as `PackageId = entity-core-protocol-csharp`. Four control nominations, three wrong, each
wrong at a **different packaging boundary** (class in C++, read site in Julia, assembly in C#). That
is now **D13** in `AGENTS.md`, with an enforcement point.

**`typescript` is the only control, and the only peer measured by execution.** §11.6.1 steps 1–3 are
measured bound in the tree, `types` measured absent; `409` and the handle lifecycle remain the rest of
the delta. **We are not nominating a second control from a source read** — the §7d harness picks it.

## What is next here, and it depends on neither

- ✅ **The dispatch-surface census** — `CENSUS-DISPATCH-SURFACE.md`, 12 peers; keystone has since
  measured all 26 M1/M2/M3 and is carrying the rest as `[host]` profile values rather than a table.
  **Roster reads `unknown` for all 46 until a harness executes** — their rule and the right one.
- ✅ **The host contract** — `DRAFT-KEYSTONE-PEER-HOST-CONTRACT.md`, H1–H5, routed and **accepted**,
  with three corrections from keystone and two back to them (`cpp`'s `register_handler` is private;
  `julia`'s writes a dead map). **It is keystone's document** — a requirement on keystone peers,
  settled between keystone and here, with arch not a party. What stays arch's is `SDK-OPERATIONS`
  §11.6 and `GUIDE-CONFORMANCE` §7d, which bind every SDK rather than only keystone's peers.
- ✅ **The seam, executed** — `poc/ts-content-seam/`. H1 and H2 measured in the `typescript` peer,
  both controls. It also answered the open S3′ authoring question: the peer's entity tree and content
  store do carry the operations `EXTENSION-CONTENT` needs, and the peer's hash-hex encoding already
  includes the format-code byte that §6.4.2 requires rather than the digest-only form — which would
  have been a silent cross-peer break.
- ✅ **The structure** — `DESIGN-THE-SYSTEM-STRUCTURE.md` and `DESIGN-THE-COMPOSITION-LOADER.md`.
  This is a **three-axis** problem where the first generator had one: 26 extensions × N languages ×
  **M compositions**, and the third axis is where two extensions can collide over a dispatch pattern,
  a namespace, or a consumer position. Ten isolation invariants, each citing the clause it enforces
  and naming where it is checked; the loader's resolve/refuse algorithm and the exact order of the
  program it emits. **Nine of the ten invariants were already normative** — nothing checked them,
  because nothing had yet generated more than one extension.
- ✅ **The SDK layer** — `DESIGN-THE-SDK-LAYER.md`. An extension is not a handler; it has **four
  faces** — the handler, the in-process **SDK surface** an application calls, the emit consumer, and
  its types — and this repo generates all four. There are **three handler execution models**, not
  one, and model choice is now a declared per-extension property rather than an assumption.
  **The SDK face has no direct instrument, and per the operator that is correct rather than a
  defect** (§1.1a): the SDK is a convention, not an API mandate, so a cross-impl surface oracle would
  enforce the thing the corpus explicitly disclaims. The instrument is the extension — face 2 is
  built so the extension's own wire-gated conformance path runs **through** it, not beside it — and
  where we want a harder guarantee we set it ourselves, as a fixed per-extension operation inventory
  with spec citations that generation refuses to omit. What is still unmeasured by anything is
  **consumer ordering**: normative in `SYSTEM-COMPOSITION` §2.2, and no oracle category tests it.
- ✅ **The compute track** — `DESIGN-THE-COMPUTE-TRACK.md`. The operator's structural theory is that
  COMPUTE is ported per language and then the other 25 extensions are written **once**, as compute
  expressions, collapsing `26 × N` to `N + 25`. **Its host precondition was measured, found missing,
  routed, fixed by keystone the same day, and re-measured green** — that whole loop is the document.
  **Two bounds remain, and they are different in kind.** *(1)* The expression language:
  `EXTENSION-COMPUTE` has **no bitwise operations**, so any extension whose surface is a digest is
  model-3-infeasible — the real reason CONTENT cannot be entity-native, and the FastCDC reason we
  published was wrong. That is a specification fact and no implementation closes it. *(2)* Budget
  admissibility under §5's step charging is **unmeasured**; nothing has run.
  **The denominator is 26, not 46** — twenty peers have no `compute/literal` ladder to hang an
  evaluator off, so the collapse ratio has to carry that number explicitly.
  **What the theory gets right**: COMPUTE's bootstrap is forced by construction, and model 3 is the
  only one of the three that can ever support *"pull the extensions into a peer you didn't build."*
  COMPUTE is also the **best-instrumented extension in the corpus** — Stage A / M5 / 🟢 stable at
  v3.27, a portable §7c corpus whose own tooling refuses to treat its builder as the oracle, and a
  4,755-line `validate-peer` category. **That instrument claim was overstated once and is corrected in
  place**: the "three-way byte-identical LOCK" figure we cited is the pin `EXTENSION-COMPUTE`'s own
  header marks *historical*; the corpus is now at 362 vectors and locks **go-on-go only**, with the
  three-way bless owed. **A conformance claim cites the MANIFEST beside the bytes, never a spec
  header** — their rule, and we broke it. **COMPUTE moves up to build 3.**
- ✅ **`typescript` × `CONTENT` — BUILT, COMPOSED, MEASURED.** See *Where this is*. What the build
  changed about the plan, beyond the numbers:

  **The layout held, and the toolchain split earned itself immediately.** `extensions/<EXT>/<lang>/`
  for source, `languages/<lang>/` for the toolchain, `compositions/<name>/` for the wiring.
  `languages/typescript/` is four files — `profile.toml`, `build`, `test`, `host-launch` — and none
  of them is extension-aware. That is the whole point: the number of build drivers stays at 46 and
  never multiplies by the extension corpus.

  **The composition resolver is real and it refuses.** `tools/compose.py` reads `SYSTEM.toml` plus
  each `EXTENSION.toml`, resolves the closure, and enforces the three composition-time invariants
  before anything is staged — **I6** pattern collision, **I7** namespace overlap, **I9** unmet
  dependency — plus the rule that an extension's pinned spec snapshot must exist. It emits
  `output/<comp>/PLAN.json` as an output with a `--check` mode that fails if a fresh resolve differs.

  **`sdk-native` is forced, not chosen.** The peer's wire `register` op refuses `system/*` patterns
  (core §6.2), and CONTENT's pattern *is* `system/content`. **Every extension owning a `system/*`
  pattern inherits this** — which is most of the 26 — so a composition is a build-time artifact and
  there is no remote-install story for the standard corpus.

  **The per-language adapter is bigger than "call registerHandler", and now measured on two peers.**
  `typescript` has a registration method that writes three of the §11.6.1 entities and no type
  entities, cannot express operation input/output types, and gives the body `ctx.peer` and
  `ctx.frameBudget()`. `python` has **no registration surface at all** — every write is the caller's
  — and its `DispatchCtx` carries no peer, no suffix and no budget. A template written against
  `typescript` alone would not have retargeted. The table is in
  `extensions/content/arch/AUTHORING-NOTES.md` §2.

  **The §3.4 MUST is enforced by the module resolver, not by review.** `reassemble_content` is
  module-private and absent from the package's `exports` map; the only public route takes a handler
  context a consumer cannot manufacture. The test imports the package **by name** and asserts on
  what node lets through — including that a deep import into `internal/` is refused.

- **Next: `python` × `CONTENT`.** The retarget test, and the first place a template meets a
  different module system, a different error convention, and an install surface that is a public
  attribute rather than a method. Then `rust` — compile and unit-test only, tier B, never
  conformance evidence.

- **The S0′ resolver** — dependency closure, consumer-position assignment, ordering-constraint
  validation. The graph is already machine-readable in the corpus.

**Build order, with reasons.** 1. `typescript` × `CONTENT` — complete extension, all four faces,
model 2, zero peer changes. 2. `CONTENT` + `HISTORY` — the first composition, and the first build
where the resolver, the isolation invariants, §2.2 ordering and the emit question all do real work.
3. **`COMPUTE`** — moved up from later, and it displaces `SUBSTITUTE`/`REVISION`: it is the only
extension with an instrument that is neither ours nor keystone's, it is the precondition for every
model-3 question, and the collapse argument turns on a per-language port cost nobody has measured.
**It now has a destination as well as a gate** — H7 means a generated evaluator installs into a real
peer, so build 3 ends with an entity-native body running rather than with an argument.
4. A second language, after there is something whose port is worth measuring.

### What the first read-for-generation found, before a line was generated

Reading one extension spec closely enough to emit code from it, and reading the oracle that measures
it, surfaced nine findings. All are routed upstream to the document or repo that owns them; none is
closed by a local decision, and none blocks the first build.

- ✅ **CLOSED by arch, 2026-09-03.** *`EXTENSION-CONTENT`'s default chunk size was 1 MiB in §3.5 and
  §3.6.2, and 4 MiB in §10.1 and §11.2.* The pair (`chunking`, `chunk_size`) *is* the deduplication
  identity by §2.1, and chunk parameters are self-describing per blob — so two implementations
  reading different sections both conform, both pass every check, and **silently fail to deduplicate
  with each other.** It was invisible to prose review. **`DEFAULT_CHUNK_SIZE` now reads 1 MiB at
  every site** — `EXTENSION-CONTENT` v3.6, with Amendments 2 and 4 reconciled into §10; the
  `[assumptions]` entry is dropped and nothing we planned changes.
- ✅ **CLOSED by arch, 2026-09-03 — pinned to `400`.** *`path_required` was a MUST in four extension
  specs with no document pinning the status code.* It turned out to be **eight** sites, and arch
  derived `400` from the landed text rather than from what `go` does, pinning it once at
  `GUIDE-EXTENSION-DEVELOPMENT` §171 with each restatement naming that authority — which is what we
  asked for, and it makes the next sweep a grep. Our assumed constant was already `400`, so **no
  generated code changes.**
- **`CONTENT` §6.2's frame-budget MUST is not implementable on the peer we measured** — the budget is
  private to the transport and absent from everything a handler body receives. That is a
  host-contract gap rather than a spec or generator gap, and it is the kind of requirement only
  generation finds.
- **Four of the twelve checks in the oracle's `content` category exercise the oracle's own library
  rather than the peer under test**, so four twelfths of that number would say nothing about a
  generated system. Two more findings concern the same category's handling of an absent extension.
- **The `404` code string for an unresolved handler is asserted by no check anywhere**, and the one
  peer measured emits a different string from the one the protocol's status table names. One peer is
  one peer; the cohort state is unknown.
- **Installing a handler emits tree-change events, and nothing says whether it should.** A handler
  install is four ordinary tree writes, so any emit consumer already registered observes them — which
  means a peer with history installed records every subsequent installation as a transition, and a
  peer with subscription installed **notifies remote peers about its own start-up**. The reference
  implementation suppresses exactly this during its own bootstrap, with the principle stated in a
  source comment (*"seed writes are not application events"*) and in no specification — and that
  window closes before the post-construction install path this repo exists to use. Composition
  orders its own steps to make the exposure window empty; the general question is routed. **This is
  the first finding that required thinking about two extensions at once**, and it is why the second
  build is a composition rather than a second language.

**This is the repo doing the job it exists for.** A generated extension is the first consumer that has
to resolve every ambiguity in a spec to a single value, and the first thing that notices when two
sections resolve differently.

Specs are read out of `entity-system-architecture` in this checkout; copy them if convenient.

## What this repo will not do

- **Fork a peer.** If a generated peer cannot host what we generate, that is a finding about the seam
  or the phase contract, and it is routed. A patched peer ends the property that makes the cohort
  worth anything.
- **Close a spec gap locally.** `entity-system-architecture` is the spec authority. Ambiguities route
  there as spec issues.
- **Treat its own output as evidence.** N generated implementations of one extension are N copies of
  one reading — generation lineage, not convergence.
