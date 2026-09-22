# The SDK layer — what it is, how the three reference impls actually built it, and what the generator owes

**Why this document exists.** Everything this repo has written so far treats an extension as *a
handler installed into a peer*. That is one of its faces. The corpus has a whole layer above it —
`SDK-OPERATIONS`, `SDK-EXTENSION-OPERATIONS`, `SDK-IDENTITY-INFRASTRUCTURE`, ~3,400 normative lines —
which specifies what an **application** calls, and **the generator is on the hook for both.** This is
the read-in, plus an audit of the three reference implementations, plus what changes for us.

**Nothing here is routed yet.** Internal analysis, per the operator.

---

## 1. The layer, in the corpus's own terms

`SDK-OPERATIONS` §1 fixes five levels:

| Level | What | Who |
|---|---|---|
| **L0** | wire protocol — framing, envelopes, handshake | core library internals |
| **L1** | operations — tree ops, `execute`, query, watch, connect, peer lifecycle | every SDK consumer |
| **L2** | patterns — scoped handles, state management, type rendering | application developers |
| **L3** | **extension operations** — per-extension wrappers **and handler registration** | entity-native applications |
| **L4** | composition patterns — reactive pipelines, cross-peer workflows | advanced applications |

**We live at L3, on both sides of it.** The handler we install *is* an L3 registration; the wrapper
an application calls (`content.EnsureClosure`, `revision.commit`) *is* the L3 surface. The seam work
so far has been the first half only.

**The framing that governs everything below** — `ROADMAP-SDK`, arch's own words:

> *"The SDK is a **convention, not an API mandate** — your language, your idioms, but the boundary
> bytes and operation semantics agree."*

So the SDK is not a portable interface to be transcribed. It is a set of **named operations with
pinned semantics** that each language renders in its own idiom — the same shape as `[host]`, one
layer up.

### 1.1 The fact that reframes our gate

`ROADMAP-SDK`, on why the SDK specs sit at maturity **M2**:

> *"their gate is 'does the cross-impl SDK boundary agree,' validated through **workbench-go's
> reference surface and the 3-impl SDK adapters**, **not through the keystone 15-peer protocol
> gate**."*

**The SDK layer has a different gate from the wire layer, and that gate does not reach a keystone
peer.** `validate-peer` measures the wire. Nothing measures whether a generated SDK surface is
correct, present, or idiomatic — and by the discipline we adopted from keystone (`gates/README.md`:
*the only axis with no external authority is the only one whose checks went stale*), an SDK surface
generated for 46 languages with no instrument behind it is a rot risk.

### 1.1a The operator's ruling on this, 2026-09-03 — and it narrows the finding

The paragraph above originally called this *"the highest-rot-risk artifact this repo could produce."*
**The operator's reading is that it mistakes a convention for a contract, and that reading is
adopted** (L0: the operator's words are instruction, and this is a scoping call, not a spec question):

> *"The SDK is kind of a guidance for implementers — we're implementers. It's not core protocol; it
> doesn't have a suite that you pass or fail necessarily, because it's about particular language
> ecosystems and paradigms. Are they going to be 99% the same or 95% the same? Probably. Are there
> some things we do want to validate and test that architecture says? Likely. Are there going to be
> divergences based on the underlying language platform? Almost without a doubt. … The extensions
> are kind of the validation instrument for the SDK."*

Three consequences, and they change what we build rather than only how we describe it:

1. **The absence of a cross-impl byte oracle for face 2 is correct, not a defect.** A gate that
   forced 46 languages to one surface shape would be enforcing the thing `ROADMAP-SDK` explicitly
   disclaims (*"a convention, not an API mandate"*). **Do not route "the SDK has no gate" as a
   finding.** What is routed instead is the narrower, answerable question — §5 item 3.
2. **The extension is the instrument.** Face 2 is not free-floating: `EnsureClosure` sequences
   `system/content/*` EXECUTEs, and those are wire-gated by `validate-peer`. **A generated SDK
   surface that is exercised by the extension's own conformance run is measured — indirectly, over
   the wire, by an oracle that is not ours.** So the design rule is: *face 2 is built so that the
   extension's conformance path goes through it*, rather than beside it. An SDK operation no
   conformance run reaches is the thing with no instrument, and that is a much smaller set.
3. **What we *do* pin, we pin harder than arch's guidance requires.** Being implementers rather than
   the spec authority cuts both ways: we cannot loosen a normative SDK semantic, and nothing stops
   us from holding our own generated surface to a stricter standard — a fixed operation inventory
   per extension with spec citations (the `[sdk]` block, §4.2), and generation-time refusal when a
   named operation is missing. That is ours to set, it needs no upstream ruling, and it is the
   honest replacement for the gate that should not exist.

**What survives unchanged:** the *semantics* under the surface are normative and divergence there is
a defect, not idiom. The 95%-versus-5% line falls between **operation semantics and boundary bytes**
(pinned, ours to honour) and **naming, shape, error convention and placement** (idiom, per-platform,
declared in `[host]`). Every generated SDK operation is classified into one of those two columns.

## 2. Three handler execution models — and we have been building for exactly one

`SDK-OPERATIONS` §11.3 is the answer to *"compute module handler, or internal, or precompiled, or
post-compiled, or I ingest the SDK and write my own."* There are three, and the spec compares them
directly:

| Property | **1. Precompiled** | **2. SDK language-native** | **3. Entity-native (compute-backed)** |
|---|---|---|---|
| Registration | peer startup (in the binary) | `register_handler` (SDK §11.6) | `system/handler:register` (protocol) |
| Body location | compiled binary | in-memory dispatch index | **tree** (expression entity) |
| Transferable | no | no | **yes** — content-addressed |
| Inspectable | no | no | **yes** — walk the expression graph |
| Hot-swappable | no (recompile) | close handle + re-register | replace expression at the path |
| Restart survival | yes | **no** — re-register on startup | **yes** |
| Auditable | implementation trust | implementation trust | **static analysis** at install |
| Performance | native | native | **interpreted, ~5× overhead** |
| Needs a host-contract change? | no | **YES — this is H1** | **YES — this is H7. Corrected 2026-09-03** |
| Works on the cohort today? | only by patching a peer | **1 of 46 measured** | **1 of 46 measured (H7 closed 2026-09-04); `compute/literal` only on the rest** |

> **The two model-3 rows above were wrong when written, and the correction is this repo's own D13
> failure in a fifth shape.** *"Needs a host-contract change: no"* and *"plausibly all 46"* were
> derived from the census's observation that every hardcoded peer ends its dispatch switch with
> `entity_native_dispatch` — **a call site, read in source, treated as a capability.** Measured with
> four controls (`languages/typescript/gates/host-seam/probe-entity-native.mjs`, against keystone's `typescript` peer, 2026-09-03): the `typescript`
> peer's entity-native path special-cases `compute/literal` inline and returns `501
> unsupported_expression` for anything richer, **and installing a live handler at `system/compute`
> does not change that — dispatch never asks it.** `ENTITY-CORE-PROTOCOL` §6.1 step 4 leaves the
> invocation mechanism implementation-defined; `entity-core-go` implements it as one nullable
> `d.EvaluateExpression` field and the keystone peers have no equivalent. Full analysis, the
> expression-language bound, and the routing: **`DESIGN-THE-COMPUTE-TRACK.md`**.
>
> **CLOSED 2026-09-04 — keystone implemented it the day it was routed.**
> `Peer.setExpressionEvaluator(evaluator | null)`, consulted after the built-in `compute/literal`
> path and before the `501`, `null` to decline. Re-measured through the packaging boundary: an
> evaluator installed through the seam answers `compute/arithmetic{add,2,3}` with `200 value=5`
> computed from the tree, and the literal floor is untouched. **Model 3 is now a real delivery route
> on one peer** — and the cohort target for it is **26 peers, not 46**: twenty have no
> `compute/literal` ladder to hang an evaluator off at all (`DESIGN-THE-COMPUTE-TRACK` §1.2).

**Every peer in the cohort already supports model 3.** The census's own result says so: *"Every
hardcoded peer ends its switch with the same default: `_ -> entity_native_dispatch(pattern)` — the
§6.13(a) path for a dynamically-registered handler whose body is a `compute` expression in the tree.
So all of them support dynamic registration of an entity-native body and none of them has anywhere to
put a language-native one."*

We read that sentence as a limitation. **It is also a delivery route we never costed.** Model 3 needs
no H1, no H3, no H6, no keystone change at all — it needs `EXTENSION-COMPUTE` installed and the
extension's logic expressible as a compute expression.

**Why model 2 was still the right first choice, and this is not a reversal:**

- **CONTENT specifically cannot be model 3** — and the *reason* is corrected in
  `DESIGN-THE-COMPUTE-TRACK` §2. It is not "FastCDC is a loop": FastCDC's gear hash is
  `fp = (fp << 1) + Gear[b]`, which **is** expressible in `compute/arithmetic` (shifts fall out of
  `mul`/`div` under §3.4 rule 8's wrap at 2⁶⁴, and a contiguous low mask is `mod 2^k`). What rules
  CONTENT out is **SHA-256**, which is `xor`/`and`/`not`/`rotr` throughout, and
  **`EXTENSION-COMPUTE` has no bitwise operations at all** — `compute/arithmetic` is closed at
  `add sub mul div mod` and `compute/logic` is boolean. That generalizes: **any extension whose
  conformance surface is a digest is model-3-infeasible.** **Model 3's feasibility is a per-extension
  property, not a global switch.**
- Model 3 costs a ~5× interpretation penalty (arch's figure, quoted not adopted) and a hard
  dependency on COMPUTE. **Corrected 2026-09-03: COMPUTE is not `Designed`.** `ROADMAP-EXTENSIONS`
  (arch, read 2026-09-03) puts it in **Stage A / M5 / 🟢 stable** — the top tier — at v3.27, with a
  three-way byte-identical cross-impl LOCK, a portable conformance corpus (`GUIDE-CONFORMANCE` §7c)
  and a 4,755-line `validate-peer` category. It is the **best-instrumented extension in the corpus**,
  which is the opposite of the risk this line asserted.
- Model 1 is what all three reference impls actually do, and it is unavailable to us by construction:
  compiling an extension into the peer binary means editing the peer, which is the fork we do not do.

**What changes: model choice becomes a declared, per-extension, per-composition axis** rather than an
unexamined assumption. `EXTENSION.toml` gains it:

```toml
[install]
model              = "sdk-native"      # "sdk-native" | "entity-native" | "precompiled"
entity_native      = "infeasible"      # feasible | infeasible | untested
entity_native_why  = "§3.6 FastCDC gear-hash loop + SHA-256 over MiB buffers is not an expression"
```

**And it changes what an unhostable peer means.** Today a peer that fails H1 is out of scope for
hosted extensions. Under model 3 it may not be — *"declined"* is a statement about one model, and the
`[host]` block should say which. That is a question for keystone and it is a better question than
*"when will you expose `RegisterHandler`."*

## 3. The audit — three reference impls, three different answers, measured

The operator's read is right: they chose differently, and the differences are the evidence.

### 3.1 Decomposition

| | core | extensions | SDK boundary | unit granularity |
|---|---|---|---|---|
| **`entity-core-go`** | `core/` — one module | `ext/` — **one module, 28 packages** | **not in the repo.** `workbench-go` owns it | package |
| **`entity-core-rust`** | `core/` — N crates | `extensions/` — **27 crates** | `bindings/sdk` → the `entity-sdk` crate | **crate** (finest) |
| **`entity-core-py`** | `packages/entity-core` | `packages/entity-handlers` — **one package, ~30 modules** | **two**: `packages/entity-sdk` *and* `entity_core/sdk/` | module (coarsest) |

**No two agree on where the extension boundary is, or where the SDK boundary is.** Rust ships an
extension as an independently-versioned crate; Python ships all thirty in one distribution; Go ships
one module with per-extension packages and puts the SDK in a *different repository*.

### 3.2 The same affordance, placed in three different layers

`SDK-EXTENSION-OPERATIONS` §11 defines two content affordances. Where they actually live:

| | `EnsureClosure` (cap-checked sequencer) | `Reassemble` (local byte extraction) |
|---|---|---|
| **go** | **`workbench-go`'s `entitysdk`** — a different repo | `ext/content/builder.go` (verified) |
| **rust** | `extensions/content/src/closure.rs`, re-exported from the **extension crate** (verified) | `extensions/content/src/lib.rs` |
| **py** | `entity_handlers/content/sdk.py` — **inside the extension package** (verified) | `entity_handlers/content/__init__.py` |

The spec anticipated the divergence and permits it:

> *"**Placement is per-impl (descriptive, not normative)** … The wire contract + Dispatcher interface
> semantics + EnsureClosure behavior are the load-bearing surfaces; **physical placement is
> impl-detail**."*

**But the pattern is 2-of-3, and it is the one available to us: co-locate the SDK surface with the
extension.** Go is the outlier and its reason is specific and stated — *"SDK extension operations
hitting core protocol layer doesn't seem right; workbench-go owns the SDK"* — i.e. Go had somewhere
else to put it. **We do not** (§4).

> **Small drift worth noting, not yet routed:** §11's *"Reference placements"* list says Rust's lives
> in the `entitysdk` crate. It lives in the extension crate. The hedge *"(or analogous SDK
> boundary)"* makes it not-wrong, but the list reads as a record of where things are and for Rust it
> is not.

### 3.3 The one genuinely portable thing they converged on

**The `Dispatcher` interface.** §11 defines it so that both an outer caller (`AppPeer`) and a
handler-internal caller (`HandlerContext`) satisfy one contract, *"unif[ying] the closure-fetch
algorithm into one implementation per impl."* All three built it:

- **py** — `entity_core/sdk/dispatcher.py`, a `Protocol` with two adapters, and its docstring makes
  the reuse point explicitly: *"The Python answer for `ExecuteResponse` is the existing
  `ExecuteResult` — same shape, **no parallel type invented**."*
- **rust** — `&dyn Dispatcher` taken by `entity_content::ensure_closure`.
- **go** — the two adapter constructors compose existing core surfaces, per §11's own note.

**This is the shape of a good SDK primitive and it is worth copying deliberately:** it is defined by
the *set of callers that must satisfy it*, it invents no new types, and it makes one algorithm serve
both the application path and the handler-internal path. An extension SDK surface we generate should
take a Dispatcher, not a peer.

### 3.4 Rust's composition mechanism is the one we should study hardest

`bindings/sdk/Cargo.toml` mirrors the peer's extension features **1:1 as pass-through flags**:

```toml
default = ["inbox", "continuation", "subscription", "clock", "revision", "query", "history", "sqlite"]
content = ["entity-peer/content"]
role    = ["entity-peer/role"]
```

and the modules are gated to match: `#[cfg(feature = "attestation")] pub mod attestation;`

**That is `SYSTEM.toml` implemented in cargo.** A composition is a feature set; the SDK surface is
conditional on the installed extension set — exactly `SDK-EXTENSION-OPERATIONS` §15's *"when you
register the revision extension, you get `commit()`, `merge()`, `log()`… When you don't register it,
those operations don't exist."* Rust gets it checked by the compiler.

The equivalents elsewhere are weaker and it is worth being honest about the gradient:

| | mechanism | when the "extension absent" error appears |
|---|---|---|
| **rust** | cargo features | **compile time**, by the type system |
| **go** | import graph — you import `ext/content` or you do not | compile time, but nothing prevents importing an extension you did not install |
| **py** | import + runtime presence check | **runtime** |
| **typescript** | export map / bundler | build time at best |

**Consequence for the loader:** for languages with a real conditional-compilation mechanism, part of
our S3.5′ output is a **manifest fragment** (a `Cargo.toml` feature selection, a `go.mod` require, a
`package.json` dependency) — not only a program. That is a genuine addition to
`DESIGN-THE-COMPOSITION-LOADER` §4, and it is where "pre-compiled vs post-compiled" actually bites.

## 4. What this means for the generator — the part that changes our plan

### 4.1 A generated extension has four faces, not one

| Face | Consumer | Installed how | Gated by |
|---|---|---|---|
| **Handler** | remote peers, over the wire | `register_handler` (§11.6) | **`validate-peer`** — the oracle |
| **SDK surface** | the application, in-process | imported | **no direct instrument** (§1.1) — and per §1.1a that is correct; it is measured **indirectly**, by building it so the extension's own conformance path runs through it |
| **Emit consumer** | the peer's emit pathway | the peer's consumer API | `SYSTEM-COMPOSITION` §2.2 — *no oracle category tests ordering* |
| **Types** | both | `HandlerSpec.types` | `validate-peer` type checks |

We have been building face 1 and treating faces 2–4 as later. **Face 2 is half the corpus's SDK
specification and has no gate. Face 3 has a spec and no gate.** Two of the four faces of everything
we ship are unmeasured, and they are unmeasured in different ways: face 2 has no instrument anywhere,
face 3 has an instrument nobody wrote.

### 4.2 A keystone peer has no SDK package to put face 2 in

The reference impls each had somewhere: rust an `entity-sdk` crate, python an `entity-sdk`
distribution, go an entire sibling repo. **A keystone peer is one package.** Measured on the
`typescript` peer: `package.json` exports exactly `.` and `./codec`, and the tree is `src/` with no
`sdk/`. Keystone generates *peers*; the SDK layer was never in its input scope, the same way
extensions were never in its input scope.

**So face 2 has to be co-located with the extension module we generate** — which is also the 2-of-3
reference pattern (§3.2), so this is convergence rather than compromise. The extension module
exports both faces, and the module unit is the `[host]` profile fact keystone is already adding:

```
languages/typescript/extensions/content/
├── handler.ts      ← face 1 — the dispatch target
├── sdk.ts          ← face 2 — EnsureClosure / Reassemble, taking a Dispatcher
├── types.ts        ← face 4 — HandlerSpec.types
└── index.ts        ← the export map; both faces public, internals not
```

**This is why `EXTENSION.toml` needs a `[sdk]` block** naming, per extension, the operations of face
2 with their spec citations — transcribed from `SDK-EXTENSION-OPERATIONS` exactly as `[contract]` is
transcribed from the extension spec header, and checkable against the same pinned snapshot.

### 4.3 The platform-variance axis the operator named, mapped

The variance is real and it is not only "syntax differs". It falls into four bins, and only the first
is free:

| Bin | Examples | What varies | Where it is declared |
|---|---|---|---|
| **Idiom** | method vs function, `async` vs callback, error vs exception | naming, shape | `[host]` — already planned |
| **Module system** | crate · Go package · npm package · ASDF system · gem · wheel · copybook | what an extension *is* as a shipping unit | `[host].module_unit` |
| **Conditional composition** | cargo features · import graph · runtime check · bundler | **when "extension absent" is detected** — compile time vs runtime | **new** — `[host].composition_mechanism` |
| **Compilation model** | AOT (rust, go, c, haskell) · JIT/interpreted (python, js, ruby) · staged (java, csharp) · none (cobol, forth, asm) | **whether face 2 can even exist post-hoc**, and whether model 2 is reachable at all | **new** — `[host].compilation_model` |

**The fourth bin is the one that will bite.** In an interpreted runtime an application can import a
generated module at any time; in an AOT language the application must be *recompiled against* it, so
"install an extension" is a build-time act for the consumer too — which is precisely why Rust
expresses composition as cargo features and Python does not. **`SDK-EXTENSION-OPERATIONS` §16 open
question 7 is exactly this and it is unanswered:** *"Dynamic handler loading. Language-specific
mechanisms for registering handlers after peer build (Go plugins, Python modules, Rust dylibs, Godot
GDScript). The registration contract needs a runtime variant."*

We do not need it answered to proceed — a generated composition is compiled as one unit, so the
consumer-side recompile is ours and is invisible. **We need it answered before anyone installs an
extension into a peer they did not build**, which is the actual end-state the operator described:
*"I work in this language, I go to the system, I say I want a peer, I pull the extensions."*

### 4.3a The table above has a fifth bin, and keystone measured it before we hit it

**Adopted 2026-09-04 from `entity-core-keystone`'s packaging survey**
(`protocol-generator/shared/evaluations/extension-host-packaging-boundaries.md`). Two corrections and
an addition, all of which land on our four-bin table.

**Correction 1 — the survey the planning rested on was wrong in 11 of 46 rows, every one
understating the cohort.** Five peers that publish to a real registry were filed as declining:
`fortran` (fpm), **`lean` (Reservoir via Lake — an M1 peer that gates every re-pin)**, `prolog` (SWI
pack), `smalltalk` (Metacello), `unison` (unison-share). Cause: a survey keyed on **a list of manifest
filenames cannot see a language whose packaging system was not on the list, and prints `absent` rather
than `could not look`.** Keystone reproduced the mechanism three times on themselves while writing the
correction. **This is our D12/L8 shape** — an artifact is not a conclusion about the thing it names —
and it is the first instance in this ecosystem that *understates* a capability, which is the direction
nobody re-checks. **Do not build the module-system bin from a filename scan.**

**Correction 2 — `module_unit` conflates two independent axes and needs to be two fields.** An
in-process **construction surface** and a **distribution unit** are not the same question: `c` has no
registry and is the most library-shaped artifact in the tree (`.a` + `.so` + `make install` + `.pc`),
while `node-red` and `turbowarp` ship a `package.json` and are applications. A single
`host | declined` cannot express the cohort. Keystone's `[extension_host]` block already carries both;
our `[host].module_unit` should split the same way.

**Addition — a fifth bin: substrates where the contract's vocabulary has no referent.** These are not
peers that answer `no`; they are peers where the *question* does not parse, and each needs the
requirement restated for the substrate rather than a yes/no:

| Substrate | Peers | What has no analogue |
|---|---|---|
| **Live-image** | `smalltalk` | there is **no AOT binary at all** — `make` loads doits into a base image and snapshots. *"A separate compilation unit depending only on the published package"* has no referent; the honest observable is *file the extension into a fresh image built from the published baseline, and reach it* |
| **Language hosting a seam** | `datalog` and every FFI/hybrid peer | the peer's authored language is not the language a consumer links. This is why the profile block is **`[extension_host]`, not `[host]`** — `[host]` already means *the language hosting the seam* |
| **Content-addressed code** | `unison` | no file-based package; the unit is a namespace in a codebase, via UCM. *"Depends only on the published package"* becomes a namespace dependency |
| **Visual / patch** | `pd`, `turbowarp`, `node-red` | a third-party body is a patch or block graph, not a callable. **Whether it is installable at all is an open question no packaging fact answers** |
| **Hand-authored, no packaging concept** | `asm-x86_64` `asm-arm64` `riscv64` `wasm-wat` `forth` `cobol` | these legitimately **decline**, and declining is a profile value, not a defect |

**Why this belongs in our tree and not only theirs.** These five decide the *shape of the generator's
per-language templates*, not just a profile column — and the reason to carry them now is keystone's
own: it is *"the work that stops us designing the harness around npm and discovering `smalltalk` at
peer 30."* Our language axis is theirs plus a compilation model, so we inherit every one of these.

**Cross-check against the model-3 census, computed rather than asserted.** The twenty peers with no
`compute/literal` ladder (`DESIGN-THE-COMPUTE-TRACK` §1.2) and the twelve in the fifth bin **overlap
in nine**: `asm-arm64 cobol datalog forth pd riscv64 smalltalk unison wasm-wat`. The two axes are
correlated but **they are not the same list, and the residues are the interesting part**:

- **In the fifth bin, but they *do* have a ladder** — `asm-x86_64`, `node-red`, `turbowarp`. So a
  peer whose packaging vocabulary does not fit may still host model 3. **`declined` on packaging is
  not `declined` on hosting**, which is the two-axis point arriving from the other direction.
- **No ladder, but ordinary packaging** — `ada apl c cpp fortran nim oz prolog rust-wasm
  rust-wasm-wasmtime sql`. Eleven peers where H7 is a genuine build, not a vocabulary problem, and
  where the answer is *"a ladder was never written,"* not *"a ladder makes no sense here."*

**So: two lists, deliberately, and the residues are the plan.** A single "hard cohort" would have
merged eleven buildable peers into a bin labelled *"restate the requirement."*

## 5. What is owed, and to whom — for routing later, not now

| # | To | Item |
|---|---|---|
| 1 | **arch** | §16 Q7 — the runtime variant of the registration contract, per compilation model. Our four-bin table is offered as input |
| 2 | **arch** | `SDK-EXTENSION-OPERATIONS` §11's *"Reference placements"* records Rust's `EnsureClosure` in the `entitysdk` crate; it is in the extension crate |
| 3 | **arch** | **Narrowed per §1.1a — do not route this as "the SDK has no gate."** The SDK is a convention and the absence of a cross-impl surface oracle is correct. The answerable question is: **which SDK semantics does arch consider normative-and-testable, versus idiomatic and per-platform?** `ROADMAP-SDK` says *"the boundary bytes and operation semantics agree"* — that sentence names a set, and the set is not enumerated anywhere |
| 4 | **keystone** | `[host]` needs `composition_mechanism` and `compilation_model` (§4.3) |
| 5 | **keystone** | ~~*"declined"* for H1 is a statement about model 2 only; a peer that declines it may still host model 3, which every peer's `entity_native_dispatch` fallback already supports.~~ **Half-retracted 2026-09-03 — the second clause was ours to lose.** The framing stands: *"declined"* names one model and `[host]` should say which. But the escape route it offered does not exist yet — model 3 on a keystone peer is `compute/literal` only, **measured**, and installing an evaluator does not widen it. See **H7**, item 6 |
| 6 | **keystone** | **H7 — entity-native dispatch MUST be delegable to an installed evaluator.** Measured absent on `typescript` with four controls; `entity-core-go`'s `d.EvaluateExpression` (`core/protocol/execute.go`, read 2026-09-03) is the reference shape, one nullable field. Routed: `ROUTING-2026-09-03-b`. Analysis: `DESIGN-THE-COMPUTE-TRACK.md` |
| 6 | **ours** | `EXTENSION.toml` gains `[install]` (§2) and `[sdk]` (§4.2); the loader gains manifest-fragment output (§3.4) |

## 6. What did not change

**Build 1 is unaffected.** `typescript` × `CONTENT`, model 2, face 1 plus face 4 — and now
consciously also **face 2**, because `EnsureClosure` and `Reassemble` are the extension's specified
SDK surface and generating the handler without them ships half an extension. That is a small addition
to build 1's scope and it is the right one: the first cycle should produce one *complete* extension
rather than one complete face.

**Build 2 is still `CONTENT` + `HISTORY`.** Nothing in the SDK layer changes the argument for a
composition over a second language — if anything it strengthens it, because HISTORY is the first
extension whose SDK surface (`history.query`, `rollback`) sits over an emit consumer, so it exercises
faces 2 and 3 together.
