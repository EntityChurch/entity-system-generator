# The composition loader — what it is, what it emits, and what it refuses

**The loader is the one artifact this repo produces that nobody else in the ecosystem produces**, and
until now it has been described only as *"emit the composition entry point."* This specifies it.

**Standing constraint on this document.** Every ordering rule, failure semantic and refusal below
cites an existing normative clause. Where the corpus is silent the gap is **named and routed**, not
closed here — three such gaps are marked **`OPEN →`** and the third (§6) is load-bearing enough that
the first composition cannot be built without a ruling or a stated assumption.

**Companions:** `DESIGN-THE-SYSTEM-STRUCTURE.md` (where things live, and the isolation invariants
this enforces) · `DESIGN-THE-GENERATION-MODEL.md` (the phase model).

---

## 1. What it is — and the four things it is not

**The loader is a generated program that constructs one peer, installs a declared extension set into
it in a normatively-fixed order, and starts it.** One per composition. It is `systems/<name>/generated/`
and it is the S3.5′ output.

It is **not**:

- **A runtime plugin loader.** `SYSTEM-COMPOSITION` §1.2 is explicit: *"static ordering at init time
  is sufficient. The peer builder/wiring code is responsible for registering consumers in the correct
  order."* Composition is decided when the program is generated. Nothing is discovered at runtime,
  nothing is loaded from disk, there is no registry to scan. **A composition that can change at
  runtime is a composition nobody can reproduce a conformance number against.**
- **A library.** It has no API. It is an entry point.
- **A place code lives.** It contains no extension logic, ever (`DESIGN-THE-SYSTEM-STRUCTURE` §1).
- **A writer of protocol state.** It performs none of `SDK-OPERATIONS` §11.6.1's mutations itself —
  see §4.

> **Why "static" is the load-bearing word.** §11.6.6 makes dynamic handlers ephemeral: *"the dispatch
> index is empty — no callable bodies exist"* after restart, and *"SDKs MUST NOT automatically
> re-register handlers from surviving tree entries."* So the loader program **is** the composition's
> source of truth on every start, and the tree is not. That is why it is generated and byte-compared
> rather than hand-maintained: the alternative is a peer whose installed set depends on what its tree
> happened to survive with.

## 2. Inputs

| Input | Owner | Used for |
|---|---|---|
| `systems/<name>/SYSTEM.toml` | us | the requested set, the target peer + language |
| `extension-contracts/<ext>/EXTENSION.toml` `[contract]` | **transcribed from the spec header**, checked against the pinned snapshot | closure, collisions, namespaces, surfaces |
| the peer's `[host]` profile block | **keystone** | registration call, consumer call, body shape, handle idiom, module unit, frame-budget accessor (H6) |
| `SYSTEM-COMPOSITION` §2.2 / §2.3 / §2.10 | arch | consumer positions and constraints |

**If the `[host]` block is absent or reads `declined` for a surface a declared extension needs, the
composition is refused at generation time with that fact named.** A peer that cannot host an emit
consumer cannot host `HISTORY`, and finding that out at runtime is a diagnosis problem; finding it out
at generation time is a sentence.

## 3. Resolve — everything that can be refused, refused before a line is emitted

Run in this order. **Each step is a refusal point, and a refusal is a build failure with a citation,
never a warning.**

**R1 · Closure.** Take the requested set; add the transitive closure of mandatory `depends`. Refuse
an unsatisfiable dependency — `GUIDE-EXTENSION-DEVELOPMENT` §3.3/§3.4 (*"hard dependencies … DO
refuse — but that's the contract, not a surprise"*). Measured over the corpus: 15 of 26 have no
extension prerequisite; deepest closure is 4.

**R2 · Host capability.** For each extension in the closure, check its `[surfaces]` against the
peer's `[host]` block: handler → H1, emit consumer → H2, `service_owning` → §11.6.9 lifecycle,
frame-budget accessor → H6. Refuse with the missing item named.

**R3 · Pattern disjointness (I6).** The dispatch patterns claimed across the closure must be pairwise
disjoint **and disjoint from the peer's bootstrap patterns.** `SDK-OPERATIONS` §11.6.1: the collision
check happens *"before any writes"* and returns 409; *"silent overwrite is not permitted."* Refusing
at generation time turns that runtime 409 into a build error naming both claimants.

> This is where `TREE` and `TYPE` land: both extend an already-bootstrapped **core** handler
> (TREE §9 adds operations to core's `system/tree`) rather than owning a fresh pattern, so both
> collide with the peer's own bootstrap. **Arch-owed and proposal-first** — the loader's job is to
> say so precisely, not to work around it. A generator that quietly merged operations into somebody
> else's handler manifest would be minting semantics no spec authorized.

**R4 · Namespace disjointness (I7).** `owned_namespaces` must be prefix-disjoint across the closure —
`GUIDE-EXTENSION-DEVELOPMENT` §4.3, closed-namespace ownership.

**R5 · Consumer position assignment.** For each extension declaring an emit consumer:
- one of §2.2's nine named positions → that position;
- anything else → classify per §2.3's table (state maintenance · audit · reactive · summary ·
  notification · application-callback → Phase 2).
- Content-store events are a **separate list** with its own two positions (§2.2: persistence 0, query
  content indexes 1). Both lists are resolved independently.

**R6 · Constraint satisfaction.** Build the DAG from declared `run_after` constraints —
`SYSTEM-COMPOSITION` §2.10 defines these on the handler manifest's optional `composition` field —
and topologically sort. **§2.10 is explicit that a cycle is a build-time refusal:** *"If the declared
constraints form a cycle, the peer builder MUST reject the configuration with an error at build time
— cycles in consumer ordering are a configuration error, not a runtime condition."* Tiebreak, in
order: the §2.2 canonical position, then declaration order in `SYSTEM.toml` (§2.10: *"When no
constraint applies between two consumers, registration order is the tiebreaker"*).

**R7 · Named ordering MUSTs.** Beyond the DAG, the corpus states constraints in prose that a
topological sort will not derive. Currently: `EXTENSION-REVISION` — *"Implementations MUST NOT
register auto-version at positions ≤ 6 or at the same position as subscription"*, because a
subscriber must not observe a change without its version entry (§2.2 position 7/8 rationale). These
are transcribed as explicit assertions, each citing its clause.

> **`OPEN →` arch.** §2.10's `run_after` mechanism and §2.2's fixed nine-position list are two
> encodings of the same ordering, and only §2.2's is populated for the standard extensions —
> §2.10's table documents the constraints but the extension specs do not carry a `composition` field
> declaring them. So R6 has nothing to read for the standard set and falls back to R5 + R7. That is
> workable and it means **the mechanism §2.10 exists for is untested by the only consumer it was
> written for** (*"forward compatibility with plugin systems and dynamic extension loading"* — that
> is us). Worth a ruling before a third-party extension arrives.

**R8 · Emit the plan.** A human-readable resolved plan — closure, positions, constraint derivations,
refusals considered — written to `systems/<name>/generated/`. **It is an output, never edited.**
Regeneration must be byte-identical; drift is a build failure (`DESIGN-THE-SYSTEM-STRUCTURE` §6).

## 4. The emitted program — exact order, and the one derived rule

```
1.  construct the peer                    library mode (H4); NOT listening
2.  for each extension, in declaration order:
        register_handler(spec, body)      through the peer's PUBLIC surface only (H1/H3)
                                          spec.types carries the extension's type definitions
                                          service-owning: start happens inside this call (§11.6.9)
3.  for each emit consumer, in RESOLVED POSITION ORDER:
        register_consumer(name, fn)       registration order IS execution order (§1.2)
        name = "<owning-handler-pattern>/<role>"    (§2.7A)
4.  listen / serve
```

**Step 2 before step 3 is not stylistic. It is the rule that keeps the composition's own bootstrap
out of application state — see §6.**

**What the program does NOT do, and this is H3 restated as code:**

- **It does not write §11.6.1's tree entities.** Not the interface entity, not the handler entity,
  not the grant, not the type definitions. Those are the registration surface's, because it is the
  only place that can keep the index and the tree consistent, refuse the collision and unwind on
  failure. Measured: keystone's `typescript` peer performs steps 1–3 on a public `registerHandler`
  call, and `types` is the one it does not perform yet.
- **It does not touch the dispatch index.** `SDK-OPERATIONS` §11.6: *"Direct access to the underlying
  handler dispatch index MUST NOT be part of the SDK's public API surface … the SDK primitive is the
  only public mutation path."*
- **It does not install anything undeclared.** The emitted set equals the resolved closure, exactly.

> **Precision correction, worth carrying:** §11.6.1's order is **interface entity first, then handler
> entity** (*"written first because the handler entity references it by path"*), grant third **and
> only if `internal_scope` is non-null**, dispatch index fourth, with `types` written **before** all
> of them. Several of our own documents have said "handler entity, interface entity" — the spec says
> the reverse, and the reason is a reference direction.

## 5. Failure semantics

**There is no partially-composed peer.** Any failure in step 2 or 3 aborts the program before step 4;
the peer never listens. This follows the spec's own posture at the level below: §11.6.4 requires the
*registration primitive* to compensate its own partial writes in reverse order, and §11.6.9 requires
a service start failure to be *"treated as a registration failure"* that *"MUST trigger §11.6.4
compensation"*, because *"a handler MUST NOT be dispatchable with a failed service."*

The loader inherits that posture one level up: a composition that could not install everything it
declared is not a smaller composition, it is a failed build of this one.

**Teardown**, where the language and `[host]` idiom provide it, is the reverse of construction, and
each handle's close is §11.6.2's three steps in order: **stop the owned service → dispatch index →
tree entries** (type definitions are *not* removed — §11.6.2, they have independent lifecycle). Close
must be idempotent.

> **`OPEN →` keystone.** §11.6 returns a `Handle` whose close unregisters both sides, and §11.6.2
> requires both an explicit close and the language's idiomatic scoped construct. **No peer in the
> cohort returns a handle today** — measured in `typescript`, whose `registerHandler` returns `void`.
> Until that lands, a generated composition can install and cannot uninstall, which is acceptable for
> a process-lifetime composition and is not acceptable for anything else. It is part of the H1 delta
> already named (`types`, the 409, the handle lifecycle).

## 6. The finding this document produced: registration writes emit, and the reference peer already knew

**§11.6.1's writes are ordinary tree writes.** Nothing marks them special. `SYSTEM-COMPOSITION` §2.8
is explicit that consumer writes are ordinary and inherit the full cascade; §2.7 fixes the model as
post-commit. So **installing a handler emits tree-change events**, and any consumer already
registered observes them.

**Concretely, on a composition that registered its consumers first:** `HISTORY` records the
installation of every subsequent handler as a tree transition. `REVISION` cuts version entries for
them. `QUERY` indexes them. **`SUBSCRIPTION` notifies remote peers about them** — cross-peer
observable, from a peer that has not finished starting.

**The reference implementation solved exactly this for its own bootstrap, in code, with the principle
stated in a comment and in no specification.** `entity-core-go` `core/peer/peer.go` suppresses emit
across the seed phase:

> *"Suppress emit during the seed phase. Construction does hundreds of seed writes (type entities,
> handler entities, handler grants) before any consumer of the events channel is wired. Emitting
> those would either fill the channel (with nobody draining) or return `ErrEventBufferFull` … **seed
> writes are not application events.**"*

The mechanism is `NotifyingLocationIndex.SetEmitSuppressed`, whose own doc names the downstream
consequences precisely: *"history won't record, subscriptions won't fire, query indexes won't
update."*

**But that window is inside `NewPeer` and closes before it returns.** Our loader's registrations
happen *after* construction — which is the entire point of a post-construction install seam — so they
land with emit live. **The reference peer's answer does not cover the case this repo exists to
create.**

**Two consequences, one taken and one routed:**

1. **Taken, and it is why §4 orders the steps the way it does.** Registering every handler *before*
   any consumer makes the exposure window empty by construction: at the moment a registration write
   fires, no consumer is listening. This costs nothing, requires no spec change, and is available to
   every peer. **It is a derived rule, not a cited one** — labelled as such, and it is the loader's
   own reading of §2.8 plus §11.6.1.
2. **`OPEN →` arch, and it is the load-bearing one.** The mitigation is not complete. §11.6.6
   recommends applications *"re-register dynamic handlers on startup"*, and any install after the
   composition's own init — a second phase, a runtime plugin, a re-registration after restart —
   necessarily lands with consumers live. **The question the corpus does not answer: are §11.6.1
   registration writes application events?** The reference impl says no for bootstrap, by suppressing
   them, and says nothing for the post-construction case. Three shapes of answer, and the choice is
   observable cross-peer:
   - *they are events* — then a composition's install order is externally visible and two peers with
     the same declared set but different declaration order produce different history, different
     version DAGs, and different notifications;
   - *they are not* — then §11.6.1 (or §2.x) should say so, and the suppression window has a
     specified extent rather than one implementation's constructor scope;
   - *the caller decides* — then it is a documented flag on the registration primitive, and the
     `[host]` block has to carry it.

**This is the first genuinely composition-level gap found**, and it could not have been found by
building one extension, reading one spec, or testing one peer — it needs an extension that registers
a consumer and another that registers after it. It is the argument for `CONTENT` + `HISTORY` being
build 2 (`DESIGN-THE-SYSTEM-STRUCTURE` §5).

## 7. Determinism

**Same manifests + same snapshot + same profile → byte-identical program.** Enforced by regenerating
and comparing on every build.

This is not tidiness. A composition's conformance number is a claim about an artifact; if the
artifact is not reproducible from its declared inputs, the number is a claim about one machine's
afternoon. Keystone's own ratchet has the matching incident — a peer measured against a week-old
bundle because a build step ran only if an output was missing. **The loader is regenerated
unconditionally.**

Consequences that follow, and each is a rule:

- **No timestamps, no absolute paths, no hostnames, no map iteration order** in emitted output.
- **Declaration order in `SYSTEM.toml` is significant** (it is §2.10's documented tiebreaker), so it
  is preserved verbatim rather than sorted.
- **The resolved plan is emitted alongside the program**, so a reviewer can see *why* an order was
  chosen without reading generated code in a language they may not know.

## 8. What varies by platform, and what cannot

The test from `DESIGN-WHERE-THE-LINE-IS` §3 applies unchanged: *could two peers both be correct and
answer differently?* Then it is a `[host]` profile value, never a loader assumption.

| Fixed everywhere | Free to vary — read from `[host]` |
|---|---|
| the four steps of §4 and their order | the registration call's name and shape |
| resolved consumer order (§2.2 + §2.10) | the consumer registration call |
| refusal set (§3) and its citations | the body/callable shape and its capture semantics |
| no §11.6.1 writes by the program | the handle/cleanup idiom |
| no partial composition (§5) | the module unit an extension ships as |
| byte-identical regeneration | the entry point's shape (`main`, an exported `run`, a class) |

**A loader is therefore one algorithm with N renderings**, and the renderings are mechanical. That is
the same economy `DESIGN-THE-GENERATION-MODEL` §8 claims for extensions — new language is a port,
new extension is new reading — and it is why the loader is specified once, here, rather than per
language.

## 9. Summary of what this document owes upstream

| # | To | Question |
|---|---|---|
| 1 | **arch** | **Are §11.6.1 registration writes application events?** (§6) — observable cross-peer, and the reference impl answers it only for bootstrap, in code |
| 2 | **arch** | §2.10's `run_after` is the declared mechanism for exactly our case, and no standard extension populates it (§3 R6) |
| 3 | **arch** | `TREE` / `TYPE` extend a bootstrapped core handler and collide at 409 under §11.6.1 (§3 R3) — already logged, restated here as a refusal the loader will emit |
| 4 | **keystone** | No peer returns a `Handle`; §11.6.2's lifecycle is unimplemented cohort-wide (§5) |
| 5 | **keystone** | `[host]` must carry the consumer registration call and the frame-budget accessor, or R2 cannot run (§2) |

**None of these blocks build 1**, which installs one extension with no consumer. **Items 1 and 4
block build 2**, which is the first real composition — and that is the correct time to find out.
