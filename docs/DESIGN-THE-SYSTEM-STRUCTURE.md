# The structure — how 26 extensions, N languages and M compositions stay separable

**What this settles:** where things live, what a generated extension module is allowed to touch, and
which structural mistakes we are declining in advance because a sibling repo already paid for them.

**Companions:** `DESIGN-THE-GENERATION-MODEL.md` (how a build runs) · `DESIGN-THE-COMPOSITION-LOADER.md`
(what the loader is and what it emits) · `DESIGN-WHERE-THE-LINE-IS.md` (whose requirement is whose).

---

## 0. The problem keystone did not have

`entity-core-keystone` generates **one artifact kind along one axis**: 46 peers, one per language,
each self-contained in `protocol-generator/<lang>/` with its own `src/`, `profile.toml`, `status/`
and phase reports. Nothing a peer contains can collide with anything another peer contains, because
the peers never meet. That structure is right for that problem and it does not transfer.

**Ours is a three-axis problem and the axes multiply:**

```
                    26 extensions  ×  N languages  ×  M compositions
                    ─────────────     ────────────     ──────────────
   the SPEC unit     new reading      mechanical       the SHIPPED unit
   isolation unit    per extension    port             where they meet
```

The third axis is the one that does not exist in keystone at all, and it is where every interesting
failure lives. An extension alone is inert. **A composition is where two extensions can collide** —
over a dispatch pattern, over a tree namespace, over a consumer position, over a cascade. So the
structure has to make the first two axes cheap and the third one *legible*, because the third is the
one that has to be reasoned about.

**The corollary that decides the layout:** the extension is the unit of specification, of authorship,
of isolation and of routing. The language is a leaf. The composition is a distinct artifact kind that
owns nothing and references everything.

## 1. Layout

**TARGET-MAJOR as of 2026-09-06, and this section is the record of the reversal.** It was written
before anything was generated, edited in place at the first build to match `ts-content`, and
rewritten again at the cycle-1 structure review — one canonical home per fact, so the tree is the
authority and this describes it. **The previous version argued for extension-major, and that
argument is preserved below, because it was overturned by evidence rather than by preference.**

```
entity-system-generator/
├── extension-contracts/            ← the SPEC unit. LANGUAGE-NEUTRAL ONLY.
│   └── content/
│       ├── EXTENSION.toml          ← the contract + the cross-port comparison tables (§2)
│       ├── README.md               ← what it is; the spec is upstream, this is not a copy
│       └── arch/AUTHORING-NOTES.md ← readings taken, ambiguities logged, assumptions carried
│
├── gates/                          ← the axis table + the NEUTRAL instruments (gates/README.md)
│   └── chunking-parity/{corpus.py, compare.py}
├── tools/                          ← compose.py (the resolver) · sdk-parity.py · diff-arms.py
│                                      · check-structure.py (the mirror rule, §1.2)
├── shared/spec-data/<version>/     ← immutable pinned snapshot + MANIFEST.md with digests (§4)
├── output/                         ← GITIGNORED. CROSS-TARGET results only (parity)
├── docs/
│
└── languages/<target>/             ← THE UNIFIED BUNDLE. One per target. Read it whole.
    ├── profile.toml                ← the (language, runtime, packaging, toolchain) tuple. PARSED.
    ├── build · test · host-entry   ← the driver. ONE per target, never extension-aware.
    │                                  (`host-entry` is the hook the shared `tools/host-launch`
    │                                   sources — §3's 2.1 : 1 factoring, not a second launcher)
    ├── Cargo.toml                  ← the ecosystem's WORKSPACE ROOT, where one exists (§1.1)
    ├── extensions/<ext>/           ← the cell. SOURCE ONLY — no build driver, ever.
    │   ├── handler.*  types.*  chunking.*  sdk.*  index.*
    │   ├── internal/               ← module-private; absent from the public export surface
    │   └── test/                   ← per-cell unit tests
    ├── compositions/<name>/        ← axis 3, scoped to this target.
    │   ├── SYSTEM.toml             ← the manifest: peer + extension set + faces (§2)
    │   ├── host.*                  ← the wiring program (hand-written in cycle 1; emitted later)
    │   └── status/                 ← conformance reports for THIS composition
    ├── gates/<gate>/               ← this target's ARM of a gate declared in the root axis table
    │   └── run                     ← ONE uniform entry point per (gate × target)
    └── output/<name>/              ← GITIGNORED. PLAN.json, the staged build, raw oracle reports.
```

### 1.1 Why the reversal — and it is not the navigation argument

The operator's argument was consumer-facing and correct on its own terms: **people arrive by
language.** At 20 extensions × 40 targets, someone who wants "the rust set" under extension-major
reads twenty directories and gets a listing that tells them nothing about state.

But the argument that actually settles it is a **filesystem constraint**, and it is this document's
own §6 hygiene finding turning around:

> **A cargo workspace root must be a filesystem ANCESTOR of its members.** Under
> `extensions/*/rust/` there is no such ancestor short of the repo root — which in a tree that is
> mostly not rust would be a lie about the repo. So there was no workspace, and at **one**
> extension the tree already carried `3 Cargo.toml` and `3 Cargo.lock`, with `sha2 = "=0.10.9"`
> pinned **independently in two of them** and nothing checking that they agreed. The cell's own
> manifest says a second version *"would compile silently."*
>
> `languages/rust/` **is** that ancestor. The workspace is free, and the defect stops being
> produced rather than being gated.

**`languages/<lang>/` had de-duplicated the build *driver* — the loud failure — and left the
package *manifest*, which is the quiet one.** Same shape for npm workspaces and a python project
root. That is one measured defect the layout was causing, and it outweighs a navigation preference
in either direction.

**Three more things dissolve rather than needing a fix:**

| Was a defect | Under target-major |
|---|---|
| the gate cell had no declared shape — two targets inline as `probe.mjs`/`probe.py`, one as a `rust/` subdirectory, because rust needed a manifest and nothing said what a gate cell *was* | a gate arm is `languages/<t>/gates/<gate>/`, the same cell shape as everything else, checked by `tools/check-structure.py` |
| composition names carried undeclared abbreviations — `ts-`/`py-`/`rs-`, and what would `csharp` have been? | the target is the path; the name is just the extension set |
| `make` needed `LANGUAGE` derived back out of the resolved plan, so `COMPOSITION=py-content LANGUAGE=typescript` could not be spelled | the pair is a path. `languages/rust/compositions/content` exists or it does not; the mismatch has no location |

### 1.2 What extension-major was protecting, and how it is protected now

The previous version's argument, kept verbatim because it names real properties:

> - **A spec defect is found in one extension and affects every language port of it.**
>   Extension-major puts the blast radius in one directory. Language-major scatters it across N.
> - **Isolation is a property of an extension, not of a language.** `system/content/` is owned by
>   CONTENT in every language simultaneously.
> - **Routing is per-extension.** A finding goes upstream against `EXTENSION-CONTENT`, not against
>   "CONTENT-in-Rust".

All three are properties of the **contract**, not of the code — and the contract did not move.
`extension-contracts/<ext>/EXTENSION.toml` is still one file, one home, one routing target, and it
still carries `[substrate.*]` and `[sdk_surface]`. **That is the line, and it is the one place this
layout declines to replicate per target:** those blocks are *comparison tables*
(`[substrate.export_boundary]` is "the same clause, three boundaries, three strengths";
`[substrate.capability_wrapper]` inverts against the row above it; `tools/sdk-parity.py` needs every
port in one place or the D16 gate stops existing). **A cross-port comparison sharded per port ceases
to be a comparison.** Per-target *code* moves; per-target *measured claims about the cross-port
contract* stay.

What is genuinely lost is adjacency: "this extension across all targets" is now a glob. It is the
rarer operation, and the replacement is better than a directory listing was — a **cohort runner per
axis**, which `gates/README.md` already required (*name the axis, its authority, and its cohort
runner, or it does not exist*) and which the language axis never had.

**The mirror rule, and it is a gate rather than a convention.** Every artifact splits into a
language-neutral half at its axis root and a per-target half under `languages/<target>/`:

```
extension-contracts/<ext>/EXTENSION.toml   ↔  languages/<t>/extensions/<ext>/
gates/<gate>/                              ↔  languages/<t>/gates/<gate>/run
(no neutral half — always per target)      ↔  languages/<t>/compositions/<c>/SYSTEM.toml
```

A per-target subtree may only hold units the root declares. `tools/check-structure.py` enforces it,
ships with both controls and a vacuity refusal, and runs in `make check`. This matters more than it
looks: the structure is now **load-bearing** — every `wildcard` in the Makefile reads it — so a
misplaced directory does not look wrong, it **silently drops out of a cohort**.

**Naming: `extension-contracts/`, not `extension-specs/`.** The actual specs are pinned in
`shared/spec-data/`, and `AGENTS.md` L0 is emphatic that arch owns them and this repo never mints
semantics. A directory here called `extension-specs/` would claim exactly the authority the repo
disclaims. "Contract" is already §2's word for what `EXTENSION.toml` is.

### 1.2b The mass audit — what belongs in `tools/` and what belongs under a target

**The rule, stated before the numbers because the numbers only make the case:**

> **The shared protocol lives in `tools/` — one copy, and a fix reaches every target. The
> ecosystem polish lives under `languages/<target>/` — and stays small.** A per-target file
> that grows past *"which binary, which environment, which idiom"* is a signal that something
> protocol-shaped has been written in the wrong place.

Per-target code multiplies by the number of targets; shared code does not. So the ratio is the
number that matters, and it was measured 2026-09-06 (code lines, comments and blanks stripped):

| | shared `tools/` | per-target | ratio |
|---|---|---|---|
| before | 904 | 2,325 | **2.6 : 1** |
| after the `host-launch` factoring | 996 | 2,117 | **2.1 : 1** |

**And the repo already contained the controlled experiment that settles the shape.** Two gates,
same session, same authors, one with a language-neutral half and one without:

| gate | neutral half | per-target arms |
|---|---|---|
| `chunking-parity` | `corpus.py` (makes the input) + `compare.py` (scores it) | **141 lines total** — 31 / 39 / 34, plus a 12-line `run` |
| `host-seam` | **none — only a `README.md`** | **1,478 lines total** — 539 / 538 / 381 |

A 10× difference in per-target mass, and the cause is visible rather than inferred: `typescript`
and `python` each carry their own copy of the same vocabulary — `Control A`, `Control B`,
`MEASURED PASS`, `negative control`, `VERDICT` — because there is no shared place to put the
scenario definitions, the control logic, the scoring or the reporting. An arm's job is to answer
one substrate question and emit structured data; everything around that is target-neutral.

**`host-launch` was the first correction and it is the pattern.** Three copies of ~70 code lines
whose only genuine differences were which binary to exec, which environment it needs, and where
each arm's entry point lives. Everything else — port, keypair, spawn-and-redirect, reap trap,
readiness wait, `COMPOSED` check, oracle invocation, stderr surfacing — was one protocol
transcribed three times, and it had already drifted twice (AP-10, plus two spellings of one error
message). Now: `tools/host-launch` is 92 lines once, and each target keeps a `host-entry` of
10 / 12 / 23 lines defining a single `resolve_entry()`. **210 per-target lines became 45.**

`build` is deliberately NOT factored. `tsc` × 2 versus stage-and-import versus `cargo` × 3 are
genuinely different procedures, and that is the ecosystem polish this layout exists to hold.

**The projection, which is why this is worth doing at three targets rather than at forty:**
`host-seam` at its current shape is ~490 lines per target, or **~19,600 lines at forty targets**.
At `chunking-parity`'s shape it is ~47 per target, or ~1,900. That refactor is queued and is
deliberately not rushed: those probes are the
D13 instruments that produce every measured capability claim in this tree, and a refactor that
quietly changes what they measure is worse than the duplication.

### 1.2a Two seams the move did not close, named rather than fixed

**The cell does not declare its own packaging boundary on every target.** What each cell carries
in-tree, measured:

| target | the cell declares | who authors the D13 Access boundary |
|---|---|---|
| `rust` | `Cargo.toml` | **the cell** — `mod internal;` without `pub`, enforced by rustc |
| `python` | `__init__.py` / `__all__` | **the cell** — convention, and the cell states it |
| `typescript` | *nothing* | **`languages/typescript/build`** — it generates `package.json`, including the `exports` map |

So on one of three targets the boundary that the §3.4 MUST rests on is authored by a driver shared
by every extension. It is uniform today (a template plus the extension slug) and nothing is wrong
yet. Two things follow if it stays that way: a typescript cell cannot be built or tested standalone
in-tree the way `cargo test -p entity-content` or `pytest` can, and **a per-extension packaging need
has no home** — an extension wanting its own subpath export would force the shared driver to grow
extension-awareness, which is the one thing `languages/<target>/` exists to prevent. Watch it at the
second extension; do not design for it now.

**And `EXTENSION.toml` has no dependency block.** `languages/typescript/profile.toml` used to route
the decision there — *"an extension that needed a runtime dependency would declare it in its own
EXTENSION.toml, not here"* — and no such block exists, nor any reader for one. That is AP-9's family
(a declaration nothing executes) at the level of a *routing rule*: it reads as a decision already
made. The comment now says the mechanism is unbuilt. The first extension that needs a runtime
dependency designs it, as a block in `EXTENSION.toml` resolved by `tools/compose.py` into the plan.

### 1.3 Earlier changes, kept because the reasons still hold

- **`systems/` → `compositions/`.** Naming only. "System" is already the ecosystem's word for a
  running deployment; `compositions/` says what the directory holds.
- **`<lang>/module/` → a flat cell.** The `module/` nesting bought a place to put per-cell status
  files, and per-cell status turned out to be the wrong shape: conformance is a property of a
  *composition*, not of a cell. What is genuinely per-cell is `test/`.
- **One driver per target, never per cell.** A build driver in the (extension × target) cell is
  **26 × 46 = 1,196 copies of one script.** Keystone reached 46 copies of `run-s4.sh` and one defect
  reproduced in 36 of them. `languages/typescript/` is four files and none is extension-aware. This
  is the rule target-major *extends* rather than replaces — it now covers the package manifest too.
- **`<ext>/shared/` was not built.** Reserved for language-neutral type definitions and algorithm
  vectors; CONTENT needed neither, because type definitions are rendered through each peer's own
  encoder (per-target by construction) and §3.6.5's vectors do not exist yet. Left out rather than
  created empty — an empty directory is a claim about the future.

### Why `compositions/` is separate and owns nothing

A composition is not a bigger extension. It is a **reference** — a manifest naming a peer, a language
and an extension set, plus the two things generation produces from it. It contains no extension code
and never will. If a composition ever needs to *contain* something, that something is an extension
that was not declared, and the manifest is wrong.

**This is the structural expression of the isolation rule**, and it is why the third axis gets its
own root rather than living under a language: a composition that could hold code would immediately
become the place where cross-extension patches accumulate — which is a fork of two extensions wearing
one directory's name.

### What is deliberately absent

- **No `common/` or `util/` shared between extension modules.** Two extensions sharing a helper is a
  dependency neither declared, and `GUIDE-EXTENSION-DEVELOPMENT` §3.3 requires dependencies to be
  declared and real. If two modules genuinely need the same code, it belongs to the peer (route to
  keystone) or to one extension that the other declares a dependency on.
- **No per-target run scripts.** One runner per axis, matrix as data (`gates/README.md`).
- **No vendored peer.** Ever. `AGENTS.md` L0.

## 2. Two manifests, and everything else is derived

**`EXTENSION.toml`** — per extension, and **every field is transcribed from the spec header, not
authored here.** `GUIDE-EXTENSION-DEVELOPMENT` §3.3 already requires each spec to state its depends,
owned namespaces, owned kinds, owned ops and extension points; all 26 comply. So this file is a
machine-readable projection of an existing normative declaration, and the projection is checkable
against its source.

```toml
[extension]
name        = "CONTENT"
spec        = "EXTENSION-CONTENT.md"
version     = "3.7"
grade       = "draft"              # GUIDE-EXTENSION-DEVELOPMENT §9 — draft means expect defects

[contract]                          # ALL transcribed from the spec header — §3.3
depends            = []             # mandatory extension prerequisites, closure computed
owned_namespaces   = ["system/content/"]
owned_ops          = ["system/content:get", "system/content:ingest"]
owned_types        = ["system/content/blob", "system/content/chunk", "system/content/descriptor",
                      "system/content/get-request", "system/content/content-response",
                      "system/content/ingest-request", "system/content/ingest-result"]
owned_kinds        = []
points_exposed     = []
points_consumed    = []

[surfaces]                          # which of the three an installed module actually uses
handler            = "system/content"
emit_consumers     = []             # CONTENT registers none — see §5
service_owning     = false          # §11.6.9 start/stop not required

[assumptions]                       # open upstream questions, resolved to a value, greppable
chunk_size         = { value = 1048576, cite = "§3.5", conflict = "§10.1 and §11.2 say 4 MiB" }
path_required      = { value = 400,     cite = "no spec pins it; matches the only impl" }
```

**`SYSTEM.toml`** — per composition. Names things; declares nothing new.

```toml
[system]
name       = "ts-content"
extensions = ["CONTENT"]

[system.peer]
generator = "entity-core-keystone"
language  = "typescript"
```

**Everything else is derived and regenerable**: the dependency closure, the consumer positions, the
loader program, the conformance target set. **If a fact exists in two places, one of them is wrong** —
so the resolved plan is written to `output/<name>/PLAN.json` as an *output*, never edited, and
regenerating it must be byte-identical or the generator is non-deterministic — asserted by
`tools/compose.py --check`, which `make plan-check` runs.

## 3. Isolation — what it means, and where each rule is enforced

The operator's requirement is that extensions stay isolated from each other. **Nearly all of it is
already normative**; what is missing is that nothing checks any of it, because until now nothing
generated more than one extension at a time. Our job is enforcement, not invention.

| # | Invariant | Normative source | Enforced at | How |
|---|---|---|---|---|
| **I1** | A module writes only inside its **owned namespaces** | `GUIDE-EXTENSION-DEVELOPMENT` §4.3 (closed-namespace ownership) | **generation** | every tree path a module writes is a literal or a template with a declared prefix; assert prefix ∈ `owned_namespaces` |
| **I2** | A module reads another extension's entities **only through that extension's published surface** | §3.4 (*"no cross-extension validators"*) | **generation** | a module may not reference another extension's owned namespace at all unless that extension is in its declared `depends` |
| **I3** | A module imports no other extension's module unless declared | §3.2, §3.3 | **generation** | module-graph check per language; the import edge set must be a subset of the `depends` closure |
| **I4** | Consumer names are **prefixed with the owning handler pattern** | `SYSTEM-COMPOSITION` §2.7A (*"names SHOULD be prefixed … to avoid collisions"*) | **generation** | name is derived from the pattern, never authored |
| **I5** | `properties.kind` values are **namespaced to the owning extension** | §4.4 | **generation** | transcribed from `owned_kinds`; anything else is rejected |
| **I6** | No two installed handlers claim the same **dispatch pattern** | `SDK-OPERATIONS` §11.6.1 (409 collision, *"silent overwrite is not permitted"*) | **composition** | pattern set across the resolved extension set must be pairwise disjoint — refuse before emitting |
| **I7** | No two installed extensions claim overlapping **owned namespaces** | §4.3 | **composition** | prefix-disjointness across the resolved set |
| **I8** | A module registers nothing under `system/runtime/` or another extension's namespace | `SDK-OPERATIONS` §11.6.7 | **generation** | same check as I1, different message |
| **I9** | An extension with an unmet declared dependency **does not install** | §3.3 / §3.4 (*"hard dependencies … DO refuse"*) | **composition** | closure resolution refuses; this is the loader's, §5 |
| **I10** | An extension's behaviour does not change on the silent presence of another | §3.4 (*"no silent assumptions"*) | **review** | not machine-checkable; it is a code-review question and is named as such rather than pretended |

**I1–I5 and I8 are generation-time and per-extension.** They can be checked on one module in
isolation, which means they are cheap and run on every build.

**I6, I7 and I9 are composition-time and only exist in the third axis.** They are exactly the class
of failure that cannot occur in keystone and cannot be found by testing an extension alone — which is
the argument for `compositions/` being a first-class artifact with its own gate rather than a build flag.

**I10 is honest about its own limits.** It is a property of intent, not of syntax, and claiming a
grep enforces it would be worse than admitting it does not. It goes on the review checklist.

> **Known collision, already logged, and it is I6/I7's first real instance:** `TREE` and `TYPE`
> extend an already-bootstrapped **core** handler rather than owning a fresh pattern — TREE's §9 adds
> operations to core's `system/tree`. Under §11.6.1's collision rule that is a `409` against the
> peer's own bootstrap handler. **This is arch-owed and proposal-first**; the structural point here is
> that I6 will catch it at composition time with a precise message instead of at runtime with a 409
> nobody expected.

## 4. The input snapshot, and why it is pinned

`shared/spec-data/<version>/` holds a **verbatim, SHA-256-pinned copy of the 26 extension specs plus
a `MANIFEST.md`** recording each file's digest and the arch commit it came from. Immutable once
stamped; amendments get a new directory.

This is keystone's pattern and it is worth copying exactly, for a reason their own history makes
concrete: **a generator's input scope is its output scope, and an unpinned input makes a conformance
number unreproducible.** Their `spec-data/` has only ever held the three core files, which is why
their peers have no extensions — the boundary was visible because the snapshot was explicit.

Two rules we inherit and one we add:

- **Operators never edit the snapshot.** A defect in a snapshotted spec is routed upstream and lands
  as a new snapshot, never as a local patch.
- **A conformance citation names `(spec-version, corpus-name, artifact sha256)`**, never a bare
  percentage and never a commit SHA in anything published.
- **Ours:** `EXTENSION.toml`'s `[contract]` block is **checked against the snapshot** on every build.
  It is a transcription; a transcription that drifts from its source is worse than no transcription,
  because it reads as authority. This is the enforcement point that keeps §3's whole table honest —
  every isolation check consumes `[contract]`, so `[contract]` must be provably the spec's own words.

## 5. What CONTENT-first does and does not buy — stated plainly

CONTENT was chosen for **seam** reasons, not spec reasons: it has no emit consumer, no service
lifecycle, no extension prerequisite, and a handler that is a content-store lookup. That made it the
cheapest thing that could prove the install path end to end, and it did — the seam is measured and
four upstream defects fell out of reading one spec closely.

**But it exercises none of the structure this document is about.** Specifically:

| Machinery | Exercised by CONTENT? |
|---|---|
| The install seam, §11.6.1 writes, dispatch reachability | **yes** — done |
| The conformance loop, and the *"we broke the core 16"* failure mode | **yes** |
| I1/I2/I8 — owned-namespace containment | yes, trivially (one extension, one namespace) |
| **I6/I7 — cross-extension collision** | **no.** Needs two extensions |
| **I9 + the dependency closure** | **no.** CONTENT declares no prerequisite |
| **§2.2 consumer ordering, the whole of `SYSTEM-COMPOSITION`** | **no.** CONTENT registers no consumer |
| **§11.6.9 service start/stop** | **no** |
| **Handle lifecycle / teardown** | **no** |

**So the first build validates the pipeline and not the composition**, and a second single-extension
build in a second language would validate neither — it would re-measure the seam. The sequencing that
follows from the structure rather than from convenience:

1. **`CONTENT` alone** — the pipeline. In flight.
2. **`CONTENT` + `HISTORY`** — the first *composition*. HISTORY has one consumer at position 4, so
   this is the first build where §2.2 ordering, I6, I7 and the resolver all do real work, and the
   first artifact under `compositions/` that is more than a wrapper. **This is the interesting one and it
   should not wait for a second language.**
3. **`SUBSTITUTE` or `REVISION`** — the first *declared dependency* (on CONTENT, on TREE), exercising
   I9 and the closure.
4. **A second language**, once there is something whose port is worth measuring.

**Widening the language axis before the composition axis would be the wrong economy** — it multiplies
a thing we have already proven and defers the thing nothing has ever tested.

## 6. Hygiene — the failures we are declining in advance

These are not hypotheticals. Each is a dated, measured incident from `entity-core-keystone`'s own
ratchet, and each has a structural analogue here that is cheaper to prevent than to find.

| Their incident | Ours would be | Declined by |
|---|---|---|
| **The axis with no external authority is the one whose checks went stale** — 17 of 18 hand-written S3 assertions drifted while every peer read `756 · 0F` | our `isolation` axis: nothing upstream checks it, so nothing watches it | `gates/README.md` — the axis table, and isolation's assertions derive from the spec-declared `[contract]` rather than from taste |
| **31 peers carry a script, 15 do not, and the whole axis was one oracle flag nobody passed** | a `run-<ext>.sh` per extension × language | one runner per axis, matrix as data. *"A separate harness that exists because a flag was never passed is not an axis, it is a workaround with a directory"* |
| **A gate that assumed an untracked `node_modules/` died `rc=127` from clean** while reporting green | a gate that assumes a built peer `dist/` or a warmed package cache | delete derived state before measuring; the gate installs what it needs or declares the dependency |
| **A published `0-FAIL` that carried unexercised checks** | an extension number that includes checks measuring somebody else's library | report skips and inattributable passes explicitly; a skip is a failure |
| **Build-only-if-missing left a peer measured against a week-old bundle** | a composition measured against a stale generated loader | the loader is regenerated unconditionally and byte-compared; drift is a build failure |
| **A recommendation written hours before anyone measured it, wrong in the expensive direction** | exactly this document, if none of it is executed | every rule in §3 names its enforcement point; ones that have none are marked unbuilt in `gates/README.md` rather than assumed |

**And one of theirs that is a warning about this document specifically.** Keystone ratified: *"a
requirement of that kind ships with its executable gate or it does not ship — not a census document,
not a table, not a source read."* §3's table is currently a table. **It is a design, not a
measurement, and it stays labelled that way until the checks exist.**

## 6b. The fourth axis — peer × peer — and the half of it that collapses

**Added 2026-09-07, on the operator's question:** *"there may be a cross-peer bug — maybe Python to
Rust works fine, but Python to Pascal has a weird bug. There's a whole other testing matrix of every
peer against every other peer."*

The concern is correct and the failure is not hypothetical: `entity-core-go`'s
`cmd/internal/validate/cross_peer_tcp.go` exists **because a peer's outbound TCP dispatcher was
broken in exactly this way** — the `rust` dialer did not strip the `tcp://` scheme — and the symptom
arrived buried in thirty cascading convergence failures rather than as one clean signal. So the
ecosystem has already paid for this axis once.

**But it is two axes wearing one name, and only one of them is N².**

| | reduces to | cost | why |
|---|---|---|---|
| **value agreement** — do two peers compute the **same bytes** for the same input? | one canonical corpus through N ports | **O(N)** | agreement on a canonical value is **transitive**. If every port matches the corpus, every pair matches every other pair. There is no A↔B to test |
| **interaction** — does A's dispatch actually **reach** B? | a live A and a live B | **O(N²)** — 1,035 unordered pairs at 46 peers | a handshake, a dispatcher, a URL scheme, a framing edge. Nothing is transitive: A↔B working says nothing about A↔C |

**This is why `chunking-parity` and `type-parity` are worth more than they look.** Both are
value-agreement instruments, and both cover the full pair matrix at linear cost:

```
chunking-parity   one corpus -> N ports -> identical boundaries and blob hashes
                  A cross-peer DEDUP failure, found without ever connecting two peers.
type-parity       N ports -> identical type-entity content hashes
                  Same failure class, on the §11.1/§9.2 entities instead of on chunks.
```

A divergence in either is a **silent** cross-peer failure — every blob still reassembles, every type
path still resolves, and the two peers simply stop deduplicating with each other. It raises no error
and no status code, so the N² harness would not catch it either: two peers that disagree about a
hash **interoperate perfectly** and just do more work. **The static gate is not a cheap approximation
of the interop matrix; for this failure class it is the better instrument.**

### Whose seat each half is

- **Core-protocol interaction is `entity-core-go`'s.** It has the harness, the transports and the
  incident. Not ours, and building a second one would be the same error `composition-ordering`
  already declines — a second scorer.
- **Core-protocol value agreement is keystone's cohort question**, and their `758 · 0F` across peers
  is the shape of the answer.
- **Extension-level value agreement is OURS**, by the same D16 argument that produced every other
  gate in `gates/README.md`: nothing upstream measures it because nothing upstream generates N ports
  of one extension. Two of these exist; a third is owed wherever an extension defines a
  content-addressed entity or a canonical algorithm.
- **Extension-level INTERACTION is unowned, and it is the real gap.** Three of the five load-bearing
  invariants in `AGENTS.md` are cross-peer — the universal address space with local-view authority,
  absolute paths at every layer, the two HTTP mechanisms — and `EXTENSION-CONTENT` §6.5 makes a
  content fetch across peers a normative operation. **Nothing anywhere exercises an extension
  operation from peer A against peer B.** That is a finding to route rather than a gate to write
  today: the harness is core-go's, the extension semantics are ours, and the honest first packet asks
  whether their cross-peer categories can take an extension category rather than proposing that we
  build a parallel one.

**The rule this settles, for anything added later:** before adding a pair to a matrix, ask whether
the property is **transitive through a canonical value**. If it is, the matrix is a corpus and the
cost is linear. Only genuine interaction earns N².

## 7. What is ours to decide, and what is not

Two things this document does **not** do, deliberately:

- **It does not add normative surface.** Every invariant in §3 cites an existing clause. Where the
  corpus is silent — I10's intent question, the `TREE`/`TYPE` 409 — the gap is named and routed, not
  closed here. A generator minting semantics 26 specs never authorized is the failure `AGENTS.md`'s
  L0 exists to prevent, and a structure document is exactly where that would happen quietly.
- **It does not constrain a peer.** Anything needed *from* a peer is a host-contract item and goes to
  keystone as an H-number. The structure is ours; the substrate is theirs.

What is genuinely ours: the layout, the two manifests, the derived-artifact discipline, the loader,
and the enforcement points. That is the whole of it, and it is enough.
