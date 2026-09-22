# The compute track — the collapse theory, measured

**Why this document exists.** The operator put a structural theory on the table: build the COMPUTE
extension first, in each language; then write **the other twenty-five extensions once**, as compute
expressions; then let every peer's entity-native dispatch path run them. The language axis collapses
from `26 × N` ports to `N + 25`. And past that, the closure: keystone builds a peer *on* a
compute-capable peer, so the substrate for an entity-native peer is itself entity-native.

The operator's own framing was *"we're not sure if that works."* This document works out what is
already settled, what is bounded by the specification, and what a probe measured this session.

**Nothing here is routed except where it says so.** Internal analysis.

---

> **UPDATE 2026-09-09 — re-read at v3.29, PINNED, and the bare arm is measured. Two versions had
> landed under this document and one of them closes §6 item 6.**
>
> This document was written against `EXTENSION-COMPUTE` **v3.27** and there has never been a
> snapshot of it in this tree — so `AP-27` applied to a *reading* rather than to a copy, and nothing
> here could have noticed. There is one now: `shared/spec-data/compute-v3.29/`
> (`d1de1942…`), with `SYSTEM-COMPOSITION.md` and `GUIDE-EXTENSION-DEVELOPMENT.md` beside it, both
> byte-identical to `history-v1.10`'s.
>
> **What moved, and it is one thing that lands on us:**
>
> - **v3.29 makes §6 item 6 real, by a bigger move than the one that row predicted.** That row said
>   the builtins override guard *"may become ours to emit **if** D1 lands and §3.5's delegation to
>   §6.2 stops holding."* D1 asked arch to **narrow** core's `system/*` reservation.
>   `ENTITY-CORE-PROTOCOL` **0.8.2.13 withdrew it entirely**, so v3.29 restates the prohibition on
>   its own basis — it binds **every installation path** because it is a *cross-peer determinism*
>   requirement rather than a namespace policy. **The condition is met and the guard is ours, from
>   port one.** Marked in §6 below.
> - **v3.27's contained-set correction is D15 clause 2 arriving in someone else's document**, the
>   same week we ratified it: *"exactly three positions"* became the **rule** that generates the
>   count, because the enumeration missed `map`/`filter`/`fold`. Nothing to route.
> - **§2's expressibility bound is UNCHANGED at v3.29 and was re-derived, not carried.**
>   `one_of: ["add","sub","mul","div","mod"]` · `one_of: ["and","or","not"]` ·
>   `grep -ciE '\bxor\b|bitwise|shl|shr' EXTENSION-COMPUTE.md` → `0`. So the digest argument in §2
>   stands and CONTENT is still model-3-infeasible.
>
> **And the bare arm is measured, which §5 needed and did not have.** Against a bare keystone
> `typescript` peer, one round, `-category compute`:
>
> ```
> $ podman run ... -e BARE=1 <node24> ./tools/host-launch typescript content \
>       -category compute -json-out output/bare-compute-probe.json
> Summary: 128 total, 0 passed, 0 warned, 128 failed, 0 skipped
> ```
>
> **128 checks, ZERO passing, zero skipped** — and that is the headline, not the 128. `content` bare
> passes **4 of 13** and `history` bare passes **1 of 34**, and in both cases the passes are checks
> that measure something other than the extension (AP-19). **Compute's bare arm has no vacuous
> passes at all**: 101 of the 128 are `blocked: depends on handler_present`, 6 on
> `handler_op_install`, 3 on `handler_manifest_decode`, 2 on `reactive_final_result`. So every check
> in this category is attributable to what we install, which makes it the cleanest differential
> instrument this repo has been handed. §3's claim that COMPUTE is the best-instrumented extension
> in the corpus is now a measurement rather than a reading of a roadmap.
>
> **This extension's contract directory under `extension-contracts/` is deliberately NOT in this
> commit** — no `compute` cell, no `EXTENSION.toml` — and the
> instrument is what decided that: `tools/req-coverage.py` REFUSES an extension whose declared
> `oracle_category` is absent from the executed report corpus, saying *"every coverage verdict below
> it would read `uncovered` for want of a report rather than for want of a check."* That refusal is
> right, and inventing a `pending` state to get around it would be a suppression. **The contract
> lands with port 1, in the session that produces the first composed report** — which is how both
> existing contracts landed. The reading it will be built from is in the snapshot's `MANIFEST.md`.
>
> **Five findings routed** (`ROUTING-2026-09-09-d-arch-*`), all in the machine-readable furniture and
> none in the normative body: the declaration header omits the emit pathway it consumes at §7.2;
> §10.1 MUSTs three behaviours of an operation §10.2 makes a SHOULD (and the oracle hard-FAILs a
> manifest that omits it); §9.2's operations table omits `install`/`uninstall`, which is the CONTENT
> §10.3 defect arch has already fixed once, without the sentence that fix added; the §3.1
> manifest block spells the pattern `system/compute/*`, which is 2 of 18 across the corpus and both
> outliers are the two extensions this repo has read for generation; and `SPECIFICATION-FORMAT`
> v1.3 §8.5a stands at **1 of 26** a week after landing, which is `GI-11`'s own resolution turned
> around — *a declared shape with no enforcement point*.
>
> **And a sixth we withdrew before sending.** The header's `Owned namespaces` says nothing about the
> top-level `compute/*` namespace where all twenty IR types live — which reads as a glaring omission
> until you read the guide clause it answers: §3.3 scopes the field to `system/<ext>/…` subtrees, so
> the header is right as written. D12/L8, caught one step before it became a packet.

> **UPDATE 2026-09-04 — §1's precondition is CLOSED on `typescript`, and §3's instrument claim is
> corrected against myself.** `entity-core-keystone` implemented H7 the day it was routed:
> `Peer.setExpressionEvaluator(e)`, consulted **after** the built-in `compute/literal` path and
> **before** the `501`. Re-measured here through the packaging boundary with a fifth control — an
> evaluator installed through the seam answers a `compute/arithmetic` body `200 value=5`, **computed
> from operands read out of the tree**, while the literal floor still answers first and the evaluator
> is never consulted for it. H6 closed in the same round and our unmodified `probe-seam.mjs` flipped
> `frame_budget_reachable` to `true` without our touching it. §1 is kept as written because the
> measurement is what produced the fix; the corrections are marked inline. **Two of my own citations
> in §3 were wrong and are fixed there.**

## 1. The theory has a precondition, and it was not met on the peer we measured *(closed 2026-09-04)*

Model 3 (`SDK-OPERATIONS` §11.3) puts the handler body in the tree as a compute expression and
reaches it through `expression_path`. `ENTITY-CORE-PROTOCOL` §6.1 specifies the five steps of
entity-native dispatch, and step 4 is the load-bearing one:

> *"**Invoke the compute evaluator** with the expression, scope, budget, and eval context. The
> mechanism (dispatch to `system/compute:eval`, direct callback) is implementation-defined."*

`DESIGN-THE-SDK-LAYER` §2 read the census's *"every hardcoded peer ends its switch with
`entity_native_dispatch`"* and wrote **"works on the cohort today: plausibly all 46."** That was a
source read of a call site, and D13 exists because a call site is not a capability.

**Measured, `languages/typescript/gates/host-seam/probe-entity-native.mjs`, against keystone's `typescript` peer, 2026-09-03, four controls:**

```
A. entity-native body = compute/literal{42}          → 200, value=42
B. entity-native body = compute/arithmetic{add,2,3}  → 501 unsupported_expression
C. same body, with a live handler at system/compute  → 501 unsupported_expression
D. that handler called directly                      → 200, witness returned
   evaluator invoked BY DISPATCH:  (none — never asked)
```

D is C's positive control and the reason C is attributable: the evaluator **was** installed, **was**
reachable, and answered when addressed directly. Dispatch never asked it.

**So on `typescript` — the cohort's only measured host — model 3 means `compute/literal` and nothing
else, and installing an evaluator does not widen it.** `Dispatcher.#runEntityNative`
(`src/dispatch/dispatcher.ts`, keystone's `typescript` peer, 2026-09-03) special-cases `compute/literal` inline and returns
`501 unsupported_expression` for every other expression type, with no injection point.

> **CLOSED 2026-09-04 on keystone's `typescript` peer.** `Peer.setExpressionEvaluator(evaluator | null)`, read at
> `Dispatcher.#runEntityNative` after the literal path and before the `501`; the evaluator returns
> `null` to decline, so evaluators compose, and a throw becomes a status rather than a hung request.
> **Re-measured here, scenario 3 of the same probe**: `E. compute/arithmetic{add,2,3} → 200 value=5`,
> and `F. compute/literal{42} → 200 value=42` with the evaluator **never consulted** for it. That
> ordering is the whole safety argument — `core_register_body_binding` drives the literal path on all
> 46 peers, so installing an evaluator cannot move a conformance result. Keystone planted four
> defects against it, including one shaped as `julia`'s (a setter writing nothing), each reddening
> only its own checks. **Scenario 2 is kept, and still reports NO**: installing a handler *at
> `system/compute`* is deliberately **not** the seam, and that distinction is now a measured negative
> rather than a gap.

### 1.1 The reference implementation already has the seam, and it is one field

`entity-core-go`, `core/protocol/execute.go`, read 2026-09-03:

```go
if res.handlerData.ExpressionPath != "" {
    if d.EvaluateExpression == nil {
        return d.makeErrorResponse(execData.RequestID, 501, "unsupported_operation",
            "compute extension not wired for entity-native dispatch")
    }
    resp, err := d.EvaluateExpression(ctx, exprPath, req)
```

A nullable function field on the dispatcher, populated when the compute extension is wired, and an
honest `501` naming the actual cause when it is not. **That is the entire ask**, and it is not a
design this repo has to invent — it exists, it is in the ecosystem, and it can be cited.

**This is `H7`, and it is routed to keystone** — `ROUTING-2026-09-03-b`. It is a host-contract
requirement, not a conformance defect: nothing in the protocol obliges a core peer to make its
evaluator replaceable, and a keystone peer answering `501` for `compute/arithmetic` is conformant
today. What it is not is *substrate*, and §6.13's own rationale says so —

> *"a community installing custom handlers via §6.13(a), **or eventually installing a compute
> extension**, MUST get identical dispatch semantics … the resolution-time branch is impl-internal
> plumbing for **which evaluator handles the body**, which the spec explicitly permits."*
> — `ENTITY-CORE-PROTOCOL` §6.6, v7.74 B3 ruling rationale

The spec permits the branch. **The keystone peers do not have one.** §6.13 pins five live hooks —
register, dispatch, emit, capability, connect — and **the evaluator seam is the sixth, unlisted, and
the substrate principle at §9's preamble (*"a community can … ship their own compute semantics"*)
is not reachable without it.** That half is arch's, and it is routed too.

### 1.2 The cohort denominator, corrected — and it is not 46

**Our published figure was wrong and the correction is keystone's.** `ROUTING-2026-09-03-b` said
*"25 of the 46 peers carry the `unsupported_expression` string; the other 21 have no `compute/literal`
handling."* Re-running our own grep gives **23**, so the published 25 was a tally error reading a
column-formatted output — not a different search. Keystone recounted for their packet, scoped to peer
source excluding `status/` and `reference/`:

| | peers |
|---|---|
| have a `compute/literal` ladder an evaluator could hang off | **26** |
| …of those, also emit `unsupported_expression` | **24** (`asm-x86_64` and `swift` handle the literal without it) |
| **have no ladder at all** | **20** — `ada apl asm-arm64 c cobol cpp datalog forth fortran nim oz pd prolog riscv64 rust-wasm rust-wasm-wasmtime smalltalk sql unison wasm-wat` |

**Take theirs; it is scoped, deliberate, and against their own tree.** And the row that matters for
planning is the third: **H7 is a one-field change on 26 peers and a substantially larger job on 20**,
several of which will legitimately decline. So the collapse theory's denominator is **26, not 46**,
until those twenty build a ladder — which changes `N + 25` versus `26 × N` by a factor that has to be
carried explicitly rather than assumed away.

## 2. The second bound: what the expression language can and cannot express

Independent of any host change, model 3 is bounded by `EXTENSION-COMPUTE`'s primitive set. Read at
`EXTENSION-COMPUTE` v3.27:

| Have | |
|---|---|
| Control / binding | `if` · `let` · `lambda` · `apply` (closure) · `literal` |
| Arithmetic | `add` `sub` `mul` `div` `mod` — **and that is the whole list** (§3.4) |
| Logic | `and` `or` `not` — **boolean, not bitwise** (§3.4) |
| Compare, navigate | `compare` · `field` · `index` · `length` · `numeric-cast` |
| Collections | `map` · `filter` · `fold` · `group-by` · `concat` · `assoc` · `range` |
| Effects | `lookup/tree` · `lookup/hash` · `lookup/scope` · `store` · **`apply` (handler dispatch)** |

**There are no bitwise operations.** `compute/logic` is boolean; `compute/arithmetic` is closed at
five ops by a `one_of` constraint. Shifts are recoverable (`mul`/`div` by powers of two, with §3.4
rule 8's wrap at 2⁶⁴), and a contiguous low-bit mask test is `mod 2^k`. **`xor`, `and`, `or`, `not`
over integers are not**, and they cannot be emulated in bounded steps.

**Consequence, sharper than the one we had.** `DESIGN-THE-SDK-LAYER` said CONTENT cannot be model 3
because FastCDC is *"a loop."* That reason was wrong in an interesting way — FastCDC's gear hash is
`fp = (fp << 1) + Gear[b]`, shift-and-add, which **is** arithmetically expressible, and its boundary
test is a low-mask compare. The thing that actually rules CONTENT out is **SHA-256**, which is
`xor`/`and`/`not`/`rotr` from end to end and has no arithmetic encoding. The conclusion is unchanged;
the citation is now correct, and it generalizes: **any extension whose conformance surface is a
digest is model-3-infeasible until compute grows a hash primitive or the peer exposes one.**

### 2.1 `compute/apply` (handler) is the escape hatch, and it changes the shape of the theory

An expression can dispatch to a handler. So the real end state is not "25 extensions in compute" but
a **two-layer split**:

- **Native primitive layer** — the small set of operations the expression language cannot express and
  a peer must supply: content hashing, chunk boundary detection, signature verification. Per language.
- **Entity-native logic layer** — sequencing, validation, tree shape, status selection, cascade
  choreography. Written once, in compute, for everybody.

That is a **better** version of the theory than "all 25 in compute," because it puts the port boundary
where the languages actually differ (crypto and byte handling) instead of where they do not
(control flow over entities). It is also the boundary the operator described from the other
direction — *"I optimize a handler in my native compute, or I recompile the entity-native compute into
more compressed handlers at the purity boundaries."* §6.1's purity classification is exactly that
boundary, already normative, already machine-checkable from the expression graph.

**What is unbounded here and needs measurement, not argument:** the budget model (§5) charges
`evaluate()` steps, and a per-byte loop over a 1 MiB chunk is ~10⁶ steps before any interpretation
overhead. The `~5×` figure in §11.3 is about interpretation, not about whether a budget admits the
program at all. **No number here is ours to assert until something runs.**

## 3. What the theory gets right, and it is more than it looked

**COMPUTE is the best-instrumented extension in the corpus.** This matters more than anything above,
because the SDK layer's instrument problem is the open question of the previous session.

- **Maturity is Stage A / M5 / 🟢 stable** (`ROADMAP-EXTENSIONS`, arch, read 2026-09-03) — the top tier, not
  the `Designed` we wrote last session. **`DESIGN-THE-SDK-LAYER` §2 is corrected.**
- **A portable conformance corpus** — `GUIDE-CONFORMANCE` §7c, built in `entity-core-go`'s
  `cmd/internal/compute-corpus`: frozen artifact + MANIFEST, per-impl **emission**, anti-vacuity
  guards, and a **cross-bless that locks only when byte-identical**. Its own header states the
  discipline we would otherwise have had to argue for: *"Go is the fixture-BUILDER, not the oracle …
  Nothing in this tool treats core-go's emission as correct."*
- **A `validate-peer` category** driven over the wire against the peer under test —
  `cmd/internal/validate/compute.go`, 4,755 lines.

> **CORRECTED 2026-09-04 — I cited the LOCK the spec itself labels historical, which is the exact
> trap that header exists to prevent.** This section originally read *"a three-way cross-impl LOCK:
> 330/330 vectors byte-identical across go/rust/py."* That is the **v3.21 blessing pin**, and
> `EXTENSION-COMPUTE`'s own header marks it *"**historical** … it records what v3.21 was blessed
> against and **does not describe the corpus today**,"* closing with the rule I broke: *"a
> conformance claim cites the MANIFEST beside the bytes, never this line."* **Current state, from
> arch's ledger (C-8/C-18):** the corpus is at **362 vectors**, SHA `8d2f55c8…`, and go reports it
> **locking 362/362 go-on-go — one implementation against itself, not a cross-bless.** The three-way
> bless at 362 is **owed by `entity-core-rust` and `entity-core-py` and has not been taken**; the
> last three-way lock was at 352.
>
> **What survives, and it is still the strongest instrument available to us**: the corpus is
> portable, frozen with its pin beside the bytes, has a re-freeze/re-bless forcing function
> (`TestFrozenCorpusSHAPinned`), and refuses on principle to privilege its builder. **What does not
> survive is "three-way byte-identical" as a statement about today.** When we consume it we cite the
> MANIFEST SHA and the bless state at that SHA, both of them, or we are repeating this error.

**An instrument that is not ours, not keystone's, and not satisfied by agreement among our own
output.** For the one extension the whole theory rests on, the L18 problem — *N implementations
agreeing is N implementations agreeing* — has an answer already built, even at one-impl lock.

**Open, and checked twice:** the frozen corpus is **not** at its specified home. §7c.5 puts it in
`entity-core-protocol/specs/test-vectors/compute-conformance/`; that directory holds `crypto-agility`
and `ecf-conformance` and nothing else, read 2026-09-03. **This is tracked upstream — under
arch's ledger row C-8, whose tail reads *"Then vendor to `entity-core-protocol`"* — not unlogged, and
our routing packet was wrong to imply otherwise.** So the answer to *"is publication owed"* is yes and
it has an owner. What remains ours is the scheduling consequence: **we would be the second consumer of
an instrument whose vendoring step has not happened and whose current SHA has a bless owed.**

**The other two things the theory gets right:**

1. **The bootstrap order is forced and correct.** COMPUTE is the one extension that *cannot* be
   entity-native — it is the evaluator. It is model 2 or model 1, necessarily, and everything else
   becomes optional afterwards. A theory whose bootstrap is forced by construction is a good sign.
2. **Model 3 delivers three properties model 2 cannot** (§11.3): the body **survives restart**, is
   **transferable** because it is content-addressed, and is **auditable by static analysis at
   install**. `EXTENSION-COMPUTE` §3.3 and §7.1 already specify the install-time subgraph audit. For
   *"pull the extensions into a peer you didn't build"* — the operator's stated end state — model 3 is
   not an optimization, it is the only one of the three that can work at all, because models 1 and 2
   both require the consumer to compile.

### 3.1 The new question H7 opens — and we found it by using the seam, not by reading it

`EXTENSION-COMPUTE` §3.5's **override prohibition** exists for one stated reason:

> *"Prohibiting overrides preserves cross-peer semantic determinism: two peers dispatching to
> `system/compute/builtins/arithmetic` cannot disagree on what `"add"` means."*

Our probe's evaluator returns `5` for `add(2,3)`. **Nothing whatsoever obliges it to.** It could
return `7`, and the peer would answer `200` with it, because the H7 seam hands an installed evaluator
every body the built-in path refuses and the built-in path refuses everything except
`compute/literal`. **So the seam reaches the determinism guarantee the override prohibition protects,
through a door the prohibition does not cover** — the prohibition is about *handler registration at
`system/compute/builtins/*` paths*, and an evaluator is not a handler.

**This is not an argument against H7 and must not be routed as one.** The seam is necessary, its
ordering is right, and "a community can ship its own compute semantics" *means* they can define what
their expressions do. Three things follow, and the third is the useful one:

1. **The floor is genuinely protected.** `compute/literal` answers first and the evaluator never sees
   it — measured, control F. So the one shape the cohort's conformance depends on is out of reach.
2. **Everything above the floor is the evaluator's to define**, and that is the point of the feature.
3. **The instrument that keeps an evaluator honest is the §7c corpus, not the prohibition.** An
   evaluator claiming `compute/*` shapes is claiming to implement `EXTENSION-COMPUTE`, and the corpus
   is exactly the thing that decides whether it does. **That is a real constraint on us**: our
   generated COMPUTE extension installs *through* this seam, so the corpus is not an optional
   validation — it is the only thing standing between a generated evaluator and a peer that quietly
   disagrees about `add`. It is also the argument for §7c's vendoring being unblocked before build 3
   rather than after.

**Routed to arch** (§6 item 7), framed as a scoping question rather than a defect: does §3.5's
determinism rationale extend to an installed evaluator, and if so what declares it — since the
prohibition's own delegation to §6.2 does not reach a seam that is not handler registration.

### 3.2 Corroborating keystone's D1 finding, from the generating side

> **SETTLED 2026-09-09, and harder than this section anticipated.** Everything below is written
> against a world where D1 *narrows* core §6.2's reservation and §3.5's *"needs no separate
> compute-specific guard"* delegation stops holding. `ENTITY-CORE-PROTOCOL` **0.8.2.13 withdrew the
> reservation outright** — both the unscoped form and the dispatch-path-scoped variant — on the
> grounds that it entered as an unexplained migration-table row, named a party the specification
> does not define, and ran ahead of the capability system rather than through it.
> `EXTENSION-COMPUTE` **v3.29** then restates §4's override prohibition on its own basis: it binds
> **every installation path** because it is a cross-peer determinism MUST, not a namespace policy.
> **So the paragraph below is right about the conclusion and understated about the cause** — the
> delegation did not stop holding, its target was deleted. The guard is ours to emit, it lands in
> port 1, and §6 item 6 is dated rather than conditional.

Keystone raised, and we confirm at `EXTENSION-COMPUTE` v3.27: §3.5's prohibition **delegates its enforcement** —
*"an implementation enforcing that general rule needs no separate compute-specific guard"* — to
`ENTITY-CORE-PROTOCOL` §6.2's `system/*` reservation. `PROPOSAL-EXTENSION-HOST-INSTALL-SEAM`'s D1
narrows §6.2 to the wire register path, and the delegation stops holding the moment it lands.

**One refinement from our side, and it matters for what we emit.** The MUST itself survives D1 —
§3.5 states it directly and calls the §6.2 sentence *"defense-in-depth,"* so the normative rule is
not load-bearing on the delegation. What breaks is the *"needs no separate guard"* claim. **And the
party that then owes the guard is us**: we generate the COMPUTE handler, so if a peer's general rule
no longer covers `system/compute/builtins/*`, the rejection has to be emitted in the generated
extension. That is a generator obligation nobody has written down, invisible from keystone's side,
and it is cheap now and expensive after 26 language ports exist.

## 4. Where the recursion bottoms out

The stated long-term goal: a peer written in entity-native compute, running on a keystone peer that
has the compute extension, so that *"you're not writing code in Lisp — you're writing code
entity-natively."*

The spiral does not descend forever, and it is worth naming the floor now so it is not discovered
late. A compute-substrate peer still needs, from underneath it, in the host language:

| Floor | Why it cannot be entity-native |
|---|---|
| **Transport** | sockets, framing, the §6.11 reentry contract. No compute primitive opens a connection |
| **Codec** | ECF/CBOR canonical encode-decode is what *makes* an expression addressable |
| **Hash** | §2 — no digest primitive, and content addressing is the substrate's own identity |
| **Signature** | Ed25519/Ed448 verification, same reason |
| **The evaluator** | it is the thing being bootstrapped |

**That floor is close to what keystone's S2 phase already produces** — the codec is exactly the phase
`DESIGN-THE-GENERATION-MODEL` §4 drops for extensions, because an extension inherits the peer's
encoder. It comes back at this tier. So the honest shape of the end state is not *"a peer in
compute"* but **a thin host kernel (transport · codec · hash · signature · evaluator) plus a peer
whose handler layer is entirely entity-native** — which is a real and reachable thing, and is a
smaller kernel than any peer in the cohort today.

**This is a direction, not a plan.** Nothing in it is scheduled and nothing in it is routed.

## 5. What changes for build order

**Build 1 does not move.** `typescript` × `CONTENT`, model 2. CONTENT is model-3-infeasible (§2), the
seam is measured, and the first cycle should produce one complete extension rather than start a
second track.

**COMPUTE moves up to build 3, and displaces `SUBSTITUTE`/`REVISION`.** The reasons are now
evidence rather than enthusiasm:

1. It is the only extension with an instrument that is neither ours nor keystone's (§3).
2. It is the precondition for every model-3 question, and those questions are unanswerable until
   something evaluates.
3. It is the extension whose port cost we most need a real number for, because the whole collapse
   argument is `N + 25` versus `26 × N` and **nobody has measured `N`'s first term.**
4. Its conformance vectors are byte-exact, so a port either agrees or does not — no judgement call,
   no cohort-consistency trap.

**And it is build 3, not build 2**, because build 2's job — `CONTENT` + `HISTORY` — is the first
composition, and composition is where the emit question, the ordering constraints and the isolation
invariants first do real work. Those do not get easier by waiting, and COMPUTE does not exercise them.

**The thing that was held open is settled, in the good direction.** *"If H7 lands in keystone before
build 3, the COMPUTE port immediately yields a measurable model-3 path and the collapse theory becomes
testable end-to-end on one peer."* **It landed the day it was routed.** So build 3 now has a
destination as well as a gate: a generated COMPUTE evaluator installs through
`Peer.setExpressionEvaluator`, and the first entity-native extension body becomes runnable on a real
peer rather than a design argument. **Two things that were not obvious before the measurement:**

- **Build 3's scope grows by one deliverable and it is small.** The evaluator has to be reachable
  through the seam's interface, not only correct — which is one adapter per language, sitting exactly
  where `[extension_host].evaluator_body_shape` already declares the shape.
- **The port target is 26 peers, not 46** (§1.2). That number belongs in the plan from the start,
  because the collapse argument is a ratio and we have been writing its denominator wrong.

## 6. What is routed, and to whom

| # | To | Item | State |
|---|---|---|---|
| 1 | **keystone** | **H7** — entity-native dispatch MUST be delegable to an installed evaluator | ✅ **CLOSED 2026-09-04** on `typescript`, `Peer.setExpressionEvaluator`. Re-measured here (§1); `unknown` on the other 45, and **20 have no ladder to hang it off** (§1.2) |
| 1b | **keystone** | H6 — the connection's frame budget readable from a handler body | ✅ **CLOSED 2026-09-04**, `ctx.frameBudget()`. Our unmodified `probe-seam.mjs` flipped to `true` without our touching it |
| 2 | **arch** | §6.13 pins five live hooks and the evaluator seam is not one of them, while §9's substrate principle promises a community can ship their own compute semantics. Which is it? | **routed, unanswered.** Not in arch's ledger as of 2026-09-03; §1v is the right home. **Keystone has now built the seam, so the question is narrower** — the spec would be describing a hook that exists |
| 3 | ~~**arch**~~ | ~~`GUIDE-CONFORMANCE` §7c's frozen corpus is not at its §7c.5 home~~ | **Half-retracted 2026-09-04.** The observation holds; *"unlogged"* did not. It is tracked as **arch's C-8**, whose tail reads *"Then vendor to `entity-core-protocol`"*. Reduced to a scheduling question we own (§3) |
| 4 | ours | `EXTENSION.toml`'s `[install]` block gains `entity_native_why` citations derived from §2's primitive inventory, not from prose | owed |
| 5 | ours | The native-primitive / entity-native-logic split (§2.1) is a per-extension declared boundary, and the purity classification (§6.1) is where it is drawn | owed, design |
| 6 | ours | **The builtins guard IS ours to emit.** The condition fired 2026-09-09 and by a bigger move than the row anticipated: D1 asked to *narrow* core's `system/*` reservation, and `ENTITY-CORE-PROTOCOL` 0.8.2.13 **withdrew it**. `EXTENSION-COMPUTE` v3.29 restates §4's override prohibition on its own basis — a cross-peer determinism MUST binding **every installation path** — so there is no core rule left to delegate to and nothing upstream refuses a registration at `system/compute/builtins/*` on our behalf | **owed, and now dated.** Lands in port 1, not after 26 |
| 7 | **arch** | **Does §3.5's determinism rationale extend to an evaluator installed through the H7 seam?** (§3.1) The prohibition covers handler registration; an evaluator is not a handler, and it defines every shape above the `compute/literal` floor. A scoping question the feature's existence creates, not a defect | **new — route with the next packet** |
| 8 | ours *(watch)* | **FB-1 sequencing.** Arch's ledger carries H6 as *"the next session's first ruling"* — where the accessor is *declared*. Keystone has already shipped `ctx.frameBudget()`. Nothing is blocked, but **the name is not normative yet**: if the ruling lands elsewhere in `SDK-OPERATIONS`, the generated CONTENT handler's call site moves | owed, watch |

## 7. What this document does not claim

- **That the collapse works.** **One of the two bounds is now closed and the other is not.** The host
  bound (H7) is satisfied on one peer, by execution. **Expressibility is unchanged and is a
  specification fact, not an implementation one** — no bitwise operations, so no digest, so no CONTENT
  and no signature-verifying extension. Budget admissibility is still unmeasured: nothing has run a
  per-byte loop under §5's step charging. What is settled is that the theory is coherent, its
  bootstrap is forced, and its host precondition is real and now met once.
- **Anything about 45 peers.** One peer is measured. The ladder census (§1.2) is a source read, and
  its own first published figure was wrong.
- **Any performance number.** §11.3's `~5×` is arch's figure for interpretation overhead and is
  quoted, not adopted. Nothing here has run.
