# Status

The rolling log. One file, not dated — the dated snapshots under `docs/status/` are internal.

---

## Where this is

**The requirement map exists, and the answer it gives is an assignment of work rather than a
score.** `tools/req-coverage.py` joins two inventories that both already existed — each
extension spec's own conformance section (`EXTENSION-HISTORY` §9.1, `EXTENSION-CONTENT`
§11.1–§11.4) and the executed check set in the oracle's own JSON reports — through a mapping
declared per row in `EXTENSION.toml [conformance]`. Run it; do not quote this table:

```
$ ./tools/req-coverage.py
    level         total  oracle  partial  ours  none
    MUST             14       0        6     1     7
    SHOULD           10       0        5     1     4
```

**Two extensions, 38 declared requirements, 24 of them binding: zero fully measured by the
oracle, 11 partial, 2 by our own cross-port gates, 11 by nothing.** That is not an indictment
of the oracle and must not be published as one — several of these rows have no wire form at
all, and both specs carry the *"stored in the content store, not the entity tree"* clause with
the identical absence, which makes it a property of the corpus rather than an oversight. **The
product is the assignment**: which rows a wire client could reach and does not, which need a
different instrument, and which are MAY and need none.

**`partial` is the column that matters.** A row with an oracle check *and* a declared gap is
never counted as covered, because *"a check is named after this requirement"* and *"this
requirement is measured"* are two sentences. Four of the thirteen `content` checks **pass in
the bare arm** — a peer with no content extension installed at all, on all three targets — so
they measure the oracle's own in-process library, and the report says `self_checks: 0`. That is
a check name read as a check (AP-19), caught by execution rather than by reading.

**Three packets routed, all from this repo's own build:** `G-4/G-5/G-6` to `entity-core-go`
(the four unlabelled self-checks; two HISTORY MUSTs and five CONTENT MUSTs with no check
anywhere in a 764-check corpus; and the ask for a `-list-checks`, so a *declared* check set
exists as data alongside the executed one). A structural packet to arch: the conformance
inventory has **two shapes in two specs and no stable row ids**, so nothing can cite a
requirement and every consumer writes its own parser. And one to keystone: H8's execution
context omits `capability`, which `SYSTEM-COMPOSITION` §1.4 declares and `EXTENSION-HISTORY`
§5.1 tells the extension to record *"without interpretation — it does not select between
caller capability and handler grant."*

**That last one arrived as a live FAIL of ours, not as a reading.** `history/w6_caller_cap_absent`
went `PASS → FAIL` on `typescript` and `python` during the §9.1 work and **every gate reported
green** — because the bare arm has always failed it, so `bare FAIL vs composed FAIL` reads as
*no difference* rather than as the improvement we lost. **A differential gate whose only
baseline is the other arm is structurally blind to "we stopped doing something we used to
do"** (AP-18). Not patched: inverting our precedence turns the check green and is still the
interpretation §5.1 forbids, decided by us, on a seam question that is not ours.

---

**§9.1 is satisfied, on all three ports, measured.** It was this extension's headline
unsatisfied MUST since 2026-09-06 — *no port records a real `author` or `capability`,
because no peer delivers an execution context.* Keystone landed H8 on all three peers;
all three ports now consume it, and the composed hosts report it after the traffic rather
than before:

```
python      COMPOSED-FINAL context_available=yes contexts=9  fallbacks=30 observed=51 recorded=12
typescript  COMPOSED-FINAL context_available=yes contexts=9  fallbacks=29 observed=50 recorded=12
rust        COMPOSED-FINAL context_available=yes contexts=1  fallbacks=14 observed=18 recorded=3
```

0 core regressions, 6 improvements, 0 flaky on both targets measured.

**And the oracle cannot tell.** Its four `context_*` checks are `IsZero()` / `== ""` —
presence, not provenance. They passed identically before and after, so the behaviour they
exist to verify changed completely and the score did not move. A peer that attributes every
remote caller's write to itself scores the same as one that carries real provenance. Routed
as `ROUTING-2026-09-07-b-core-go-*`; the oracle already holds the ground truth, because it
is the caller.

**The value that said `measured` was a constant.** `context_available` was a hardcoded
`false` in all three ports, commented "measured", and **asserted by all three test suites** —
a claim about another team's peer, frozen in our source and checked by our own checks. When
the substrate moved, nothing could notice. It is now observed at runtime and three-valued:
`unknown` before any event, then `yes` or **`not-observed`** — never `"no"`, because "no" is
a claim about the peer and what the counter knows is a fact about these events. That
conflation is the one the boolean was making.

**One tripwire fired as designed.** The python and typescript recorder tests asserted the
fallback path with a docstring reading *"if this ever fails because fallbackContexts is 0,
the peer started supplying a context… that is the good failure, and it is why this is
asserted rather than commented."* It failed. Writing an assertion whose failure you have
described in advance is the cheapest early warning here.

---

**Latest: the cost model exists, and it says the refactor we were deferring is not the
expensive one.** `tools/scale-report.py` classifies every tracked path by what it
multiplies by — 1, E, E's contracts, T's targets, or E·T — because in this layout a file's
*location* decides its multiplier. Run `make scale`; the shape of the answer is that the
**per-cell quadrant is 54% of today's code and 96% of the projection at 26 extensions ×
46 targets**, and that adding either a language or an extension is ~98% cells either way.
The per-target duplication three handoffs have flagged as urgent is worth ~1.4% of that.
It is still worth fixing; it is not the scaling problem, and it had been written up as
though it were.

**`gates/type-parity` is built** — every port's type entities compared by the peer's own
content hash *and* by a normalisation of the field map, so that a bug in the normaliser
surfaces as a contradiction between the two rather than as a divergence blamed on a port.
It closes the consistency half of G-3: the oracle's `type_*` checks assert that a type path
**resolves** and never read what is at it, so a subtly wrong field map produces a
well-formed entity that silently stops deduplicating with every other peer while every
check stays green. HISTORY: 3 ports agree on all 6. CONTENT: 2 agree on all 7, one
`unknown`. Negative control executed.

**Its first run cashed a `drift` entry**, which is the first evidence that an unresolved
one costs something: `typescript` had no `contentTypeEntities`, the difference had been
declared and undecided since 2026-09-06 with a note reading *"a consumer cannot write one
call that works on all three"* — and the new gate was that consumer. Resolved rather than
worked around.

**And the substrate moved under us.** `entity-core-keystone` is implementing **H8**, the
execution context on the emit event, which this repo routed on 2026-09-06. It has landed on
`typescript` and `rust` and is in progress on `python`. Two live consequences: `typescript`
cannot currently be built here at all (the peer's `dist/` is behind its `src/` and the
staleness gate refuses — *exit 3 is not a verdict*), and HISTORY's `rust` test fixtures no
longer compile because `TreeChangeEvent` gained a field. **Deliberately not patched with
`context: None`** — §9.1's MUST on `author`/`capability` is the one requirement this
extension has never satisfied *because no peer delivered a context*, and that is now false
on two peers. Details: `docs/status/HANDOFF-2026-09-07-b-*`.

---

**The first batch is complete. `HISTORY` v1.7 is built, composed and measured on all three
targets** — `typescript` and `python` at 33 PASS · 1 WARN of 34 in the oracle's `history`
category, and `rust` at **7 PASS · 23 FAIL · 4 SKIP** against a recorder that is working
correctly. Both extensions now exist on every substrate the repo has: six compositions,
0 core regressions anywhere.

**The `rust` number is the finding, and it is not a score.** Every check in that category
that reads a transition reads it through `system/history:query`, and on that peer the
handler face cannot be installed at any visibility. Meanwhile the **emit consumer installs
and runs**: the peer accumulates a real, correct, content-addressed audit chain at
`system/history/head/*` from the moment it serves, measured over real loopback TCP with a
witness derived from both a request field and registration-time state, and a negative
control that separates *"not installed"* from *"installed and never asked"*
(`languages/rust/gates/host-seam` scenario 4, arms H/I).

**So one extension's WRITE face installs and its READ face cannot.** `rust × CONTENT`
established that four faces get different answers on one peer; there the un-installable
handler meant the extension did nothing at runtime. This is sharper — the extension works
and nothing outside it can see that it does. A category score is a statement about the
oracle's access path, and on the other two targets that sentence and *"a statement about
the extension"* happen to be the same one.

**The composition pre-registered all four numbers and the split before the run, and matched
exactly** — the first expectation block in this repo to do so. `rs-content`'s was wrong in
both categories and the miss was worth more than the prediction; this one had a measured
basis the earlier ones lacked, because the BARE arm was taken from the `typescript` and
`python` runs in the same session rather than guessed.

**And the bare arm carried a finding of its own.** `history` bare is 29 FAIL · **1 PASS** ·
4 SKIP on every target, and the 1 PASS is `rollback_invalid_hash_rejected` — §7.5's
exfiltration-prevention check, satisfied on a peer with no history handler because
`404 handler_not_found` is not 200. Routed to `entity-core-go`
(`ROUTING-2026-09-07-core-go-*` G-1) along with the missing S1 gate that turns 23 skips into
23 failures, and the absence of any HISTORY analogue of `type_system_*_match`.

**D18 is new, and it is the fourth instance of the same shape.** D13's enforcement point is
a citation and D14's is a citation, and **nothing checked that the cited path was real**.
`tools/check-citations.py` found three on its first run, including a `probe =` field on the
block recording the most consequential substrate fact this repo has measured — naming a gate
that has never existed. *The thing we own is the thing nothing watches*, now with the
citation itself as the object.

---

### The `typescript` / `python` result, unchanged

**33 PASS · 1 WARN of 34 in the oracle's `history` category on both, `content`
unchanged at 12P/1S, 0 core regressions.** The composition `content-history` is the first
with two extensions in it, and the first that installs an **emit consumer** — the fourth
face `DESIGN-THE-SDK-LAYER` §1 named and nothing had exercised.

**The headline finding is what the emit face measured: the peer delivers no execution
context, on any target.** `typescript` declares an `EmitContext` carrying almost exactly
SYSTEM-COMPOSITION §1.4's inventory and constructs it at **zero sites**; `python` and
`rust` have no context field on the tree-change event at all. HISTORY §2.1 makes `author`
and `capability` non-optional and §9.1 MUSTs them, so every transition records §2.1's
**autonomous-case** values — the local peer and our own grant — for writes that arrived
over the wire from a remote caller.

**And the four oracle checks that read those fields PASS.** They are presence checks and
the values whose presence they confirm are ours. So the module records a `provenance` field
outside the spec-declared entity, the composition prints `context_available=false`, and the
unit test asserts the fallback FIRES rather than asserting the fields are non-empty.
**33/34 is a count of checks passed and not a claim that §9.1's MUST is satisfied** — the
D13 distinction, one level up. Routed as `ROUTING-2026-09-06-d-keystone-*` H8.

**Four defects in `EXTENSION-HISTORY`, all found by emitting rather than by reading**
(`ROUTING-2026-09-06-c-arch-*`): a REQUIRED conformance vector that cannot be constructed
(§6.2's worked pair needs a mid-path wildcard core §5.4's grammar does not have, and the
scalar-vs-tuple tie it defends against is unreachable under that grammar — a parity
argument); §2.2's pattern table contradicting §2.2's pseudocode, with the pseudocode's
reading matching nothing at all and failing silently; §3.3's pruning algorithm describing an
in-place mutation of immutable content-addressed entities; and no error-code table, so
`not_in_history` — the §7.5 refusal that stops `rollback` being an unrestricted write — is
defined nowhere.

**The §3.3 header gap did not block anything.** HISTORY is one of the 24 specs without
GUIDE §3.3's declaration header, so `[contract]` is **derived** with a
`[contract.derived_from]` block naming the section for every field, and the two fields that
are readings of *absence* say so. §9.2 is an explicit six-type list; §9.3 is the manifest.
The filled-in header went to arch as a draft rather than as a request.

**D16 paid for itself twice in one build.** `make error-codes` REFUSED the new extension
until it declared an `[error_surface]`; and `sdk-parity` caught the second port starting
down CONTENT's exact drift — bundled constants in `typescript`, flat in `python` — at
**22 names in both, 20 differing**. Because the gate existed the decision got made instead
of accumulating: the flat names are the contract in every port, the grouped objects survive
as aliases, and the surface is now **39 in both, 3 differing**. D16's promotion criterion was
"if it survives a second extension"; it did not survive, so the upstream proposal still
lacks its second incident.


**Three substrates. `CONTENT` v3.7 runs on `typescript`, on `python` and on `rust`, composed onto
keystone peers and gated by the same oracle. The first two are identical check for check. The third
is not, and the difference is the result.**

**Re-pinned v3.6 → v3.7 on 2026-09-06, and every number below was re-measured after it rather than
carried across.** `make check-all` exit 0: three targets, four category runs, `content` 8/8/3
improvements, `type_system` 6, core-profile 6 improvements and **0 regressions** on all three,
`chunking-parity` 3 ports agreeing on all 6 fields. The snapshot is
`shared/spec-data/content-v3.7/` (`2a40b22b…`); `content-v3.6/` is retained because the three
cycle-1 reports were measured against it.

**The re-pin is the whole story of this session, and its 38-line diff carried one behaviour
change into three ports.** §6.4's `403 forbidden` became `403 capability_denied` — `forbidden` was
`ENTITY-CORE-PROTOCOL` §3.3's *fallback* for the status and a code defined in no code set — and
**nothing in this tree or upstream could have said so.** The oracle's `content` category asserts
two of the seven codes the handler emits and the 403 is not one of them. That is **AP-11**, and
it is **D16's third instance**: an axis with no upstream authority, and the first one that had
*camouflage* rather than lateness, because a category named `content` reads like it covers the
content handler. Gate: `tools/check-error-codes.py`, in `make check`.

**And its first run found something we then routed rather than fixed.** `path_required` is
MUST-ed twice by CONTENT §6.2/§6.3, asserted by two live oracle checks, emitted by all three of
our ports and by the references — and defined in **neither** code set a handler may draw on
(`grep -c path_required specs/ENTITY-CORE-PROTOCOL.md` → `0`; absent from v3.7's Appendix A,
which declares itself closed). Two readings of core §3.3 are in the corpus at once: GUIDE §4.1
reads the 400 row as an open category and calls itself the authority; Appendix A reads it as a
closed set. **We did not pick** — the ports still emit `400 path_required`, and the contradiction
is `ROUTING-2026-09-06-b-arch-*` A-1 plus `SPEC-AMBIGUITIES` C-3, with
`[error_surface].unresolved` carrying it locally and `--strict` ready to fail the build the day
it is pinned.

**A third way to find a spec ambiguity, and it retires half of what cycle 1 concluded.** C-3 came
from neither a new port nor a new extension: it came from **a new kind of artifact appearing in a
snapshot we already had three ports against**. Appendix A did not change §6.2's MUST — it supplied
a *second document* to check that MUST against, and the gap had been in the corpus the whole time.
So the list is three long: a new **extension** forces a different part of the corpus to a value; a
new **snapshot** supplies something to check an existing reading against; a new **language port**
finds substrate facts and essentially no spec ambiguities.

| | `ts-content` | `py-content` | `rs-content` |
|---|---|---|---|
| `content` category | **12 PASS · 0 FAIL · 1 SKIP** of 13 | **identical, check for check** | **7 PASS · 2 FAIL · 4 SKIP** of 13 |
| of which measure our module | **8 of 8 PASS** | **8 of 8 PASS** | **3 of 8** — the types face only |
| `type_system` category | not run | not run | **6 checks FAIL → PASS**, all ours |
| core-profile regressions | **0** (756 checks, 3 rounds) | **0** (756 checks, 2 rounds) | **0** (756 checks, 2 rounds) |
| core-profile improvements | 6 | 6 | 6 |
| unit tests | 31 | 38 | 40 + a compile that must fail |
| wire error codes | 7, all declared | identical | identical |

**The `rs-content` row is not a worse result. It is a different measurement, and the composition
is built so it cannot pretend otherwise.** On that peer an extension's four faces do not all
install: types and emit do, the handler body cannot at any visibility, and the SDK is a library
nothing gated reaches. So three of the eight checks pass — exactly the three that measure type
publication — and the three handler checks SKIP.

**And that experiment corrects a number we had already published.** Both prior compositions report
*"8 of 8 measure our handler"*. The 8 is right about how many checks measure our **module** and
wrong about which **face**: it is **5 handler + 3 types**. Nothing distinguished them while both
faces installed. `rs-content` is the first composition where they got different answers, and
exactly the 3 pass while exactly the 5 do not. Corrected in place at every site; no number changed.

**The 8/4/1 split was written into each `SYSTEM.toml` before its run and both of those runs matched
it. `rs-content`'s prediction did not, and the miss is recorded rather than corrected away** — it
predicted zero movement in `content` and three checks moved, which is what produced the `8 = 5 + 3`
correction above. Never `13P·0F`, never a percentage: 4 of the 12 passes never contact the peer (two
build an in-memory store, two call `ValidateDescriptor` in-process), and the skip is
`frame-limit-respected`, so **the Amendment 1 frame-budget MUST is unexercised, not passing** on any
of the three. Reports: `compositions/{ts,py,rs}-content/status/`.

**The retarget was a profile change, not a rewrite — measured rather than asserted.**
`languages/python/compositions/content/SYSTEM.toml` differs from `ts-content`'s in two fields.
`languages/python/` is the same four files as `languages/typescript/` with different contents and
the same interface. `tools/compose.py` and `tools/diff-arms.py` needed no change at all.

**And the second substrate paid for itself immediately, in four places a one-language template
would have been wrong:** `python`'s peer has **no registration surface**, so its install adapter is
six steps against the other's two; its `DispatchCtx` carries **no peer**, which changes function
*signatures* and not bodies; it has **no compile step**, so the build driver's only build-time
signal is an import check; and **the §3.4 security MUST is satisfied at two materially different
strengths** — enforced by node's `exports` map in one language, convention in the other. The
substrate model is `extension-contracts/content/arch/AUTHORING-NOTES.md` §2, **and the third port revised
three of those four rows**: §3.4 turned out to be two clauses that invert (`rust` strongest on one,
weakest on the other), "no registration surface" turned out to be two different facts wearing one
word, and "no peer in the context" went from *the* invasive difference to the common case at 2 of 3.

**The biggest live risk paid off.** `python` has no public type-definition builder to reuse — its
equivalents are all leading-underscore — so its seven type field maps are hand-built dicts, on
exactly the surface where a mistake is silent: the entity would simply hash differently from
everyone else's and dedup would stop, with no error anywhere. `entity-core-go`'s own independent
transcription of §2.1/§2.2/§2.4 reports **`content hash match`** against all **three** ports —
`rust` has no public builder either, and there it is `error[E0603]` rather than a convention. That
is three of ours agreeing with one that is not. **Still not independent convergence**: one reading
of one snapshot, three transcriptions in a shared generation lineage, and no chunker ran.

**All three findings we routed to keystone are closed, re-verified here by our own instruments, and
two came back bigger than we sent them.** The frame budget is now readable on `python`
(`ctx.frame_budget()`); `Handler.operations` takes the §3.7 mapped form, so our interface-rewrite
workaround is **deleted**; and the dropped `included` map was **three sites, not the one we named**
— including the §6.13(b) outbound path a handler uses to originate, which is the one that would
have bitten a composed system rather than a test. That last one is **AP-5**: a routed packet naming
a call site says *"at least here"* unless the search for others was run and can be cited.

**Re-verifying K-1 forced an upgrade to our own probe, and that is the part worth keeping.** The
frame-budget check searched for an attribute whose *name* matched `frame` and `max|limit|budget`.
It went green the day the fix landed — correctly — and **could not have gone red** for a peer that
stamped the 16 MiB constant onto every connection and named the field `max_frame_bytes`. It now
configures the peer to enforce 3,145,749 and asserts the body reads 3,145,749, with a
negative-control arm that builds the peer unconfigured, reads 16,777,216, and is rejected. D15,
applied to our own instrument the session after ratifying it.

## Cycle 1 is closed, and the review is the deliverable of equal weight

**Three ports of one extension, and the most useful thing they measured is where findings come
from.** Full close-out:
`docs/status/REVIEW-CYCLE-1-2026-09-06-content-across-three-ports.md`.

| | port 1 `typescript` | port 2 `python` | port 3 `rust` |
|---|---|---|---|
| **spec** findings routed to arch | **2** (both landed) | 0 | 0 |
| spec ambiguities logged | **2** | 0 | 0 |
| **peer/substrate** findings routed | 0 | **3** (closed) | **2** (open) |

**Every spec finding came from the first port.** Reading a spec closely enough to emit code
forces every ambiguity to a value on the first pass; later ports re-read the same document with
the same questions already answered. **So a new language port is not how you find spec
ambiguities — a new extension is.** That retires an assumption the build order rested on, and
it is why the next move is `CONTENT` + `HISTORY` rather than a fourth language.

**Three gates now, all on axes nobody upstream owns, and every one of them found something on
its first run.**

- **`tools/sdk-parity.py`** — the SDK surface standard. **Ours to set, and that is the
  operator's call rather than a gap in arch:** arch enforces what has to be enforced,
  conformance lives on the wire, and a cross-impl surface oracle would enforce what
  `GUIDE-EXTENSION-DEVELOPMENT` explicitly disclaims. We generate N ports of one extension and
  want them to be the same extension. First run: **24 required · 9 substrate · 18 drift · 0
  undeclared** of 51 names. **The operation inventory held** — all 15 functions in all three
  ports — and 18 constants and types had drifted, almost all of it one decision made once in
  `typescript` and never made again. Nothing could have caught it: each port passes its own
  suite, and the oracle is a wire client that never sees an in-process surface. **That is
  D16.**
- **`gates/chunking-parity/`** — one corpus, three transcriptions of §3.6, compared byte for
  byte. **3 ports agree on all 6 fields**, and the corpus generator's own fourth transcription
  agrees with them. §3.7 makes chunking a Conformance algorithm whose divergence *does not fail
  loudly*, and **nothing upstream measures it**: no oracle check chunks anything (`ed9b547`),
  and §3.6.5's cross-impl vectors do not exist yet.

- **`tools/check-error-codes.py`** — the wire error-code surface, added at the v3.7 re-pin
  (2026-09-06) because the re-pin is what produced the failure it catches. **The axis that
  looked covered**: the handler emits **7** distinct codes and `entity-core-go`'s `content`
  category asserts **2** of them, so a category named `content` was standing in for coverage it
  never had. First run: **4 `spec` · 2 `core` · 1 `unresolved` · 0 undeclared** across 36 emit
  sites in three ports — and unlike the SDK surface, **the codes agree across all three ports**.
  The one `unresolved` is `path_required` (above). **That is D16 for the third time**, and the
  gate's own first draft would have missed the two codes it exists for: it scanned line by line,
  and the emits long enough to wrap are exactly `capability_denied` and `path_required`. Measured
  after the fact — a line scan sees 5/5/4 distinct codes where there are 7 — and `MIN_SITES`
  would not have caught it either. AP-11.

**Is FastCDC standard to implement? Measured, and the answer is "yes, unsafely".** Four
transcriptions agree byte for byte — but §3.6.3's inner loop `fp = (fp << 1) + gear[b]` fails
three different ways in three substrates, **silently in two of them and as a debug-build panic
in the third**, and the gear table's `uint64_le` is a second silent trap. It is implementable
consistently; it is not safely implementable without a cross-impl corpus. We now have one.

**And the process finding we least enjoyed writing down.** `gates/README.md` opens with an
inherited rule — *the axis with no external authority is the one whose checks go stale* — which
we wrote, applied to `isolation`, and then did not apply to the SDK face. Three ports shipped
before anything looked. **D16: an axis with no upstream authority gets its gate at the second
implementation, not when someone notices.**

**Five instruments written in this repo; five with a defect found by RUNNING them and none by
reading them.** Three would have reported green-or-agreeing, and two of those three would have
reported agreement across three ports — the most convincing wrong answer available. **The two
that caught themselves are the two that shipped with a refusal**, which is now D15's sharpened
form: every instrument carries an explicit refusal on its own vacuity, not only a control.

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
- ✅ **`typescript` × `CONTENT` and `python` × `CONTENT` — BUILT, COMPOSED, MEASURED.** See
  *Where this is*. The structural results, which are the deliverable of equal weight to the code:

  **The layout held across the retarget, and the toolchain split is the load-bearing part.**
  `languages/<lang>/` is four files per language — `profile.toml`, `build`, `test`, `host-entry` —
  and not one of them is extension-aware. The build-driver count stays at 46 and never multiplies by
  the extension corpus.

  **`sdk-native` is forced, not chosen, and it generalises.** The wire `register` op refuses
  `system/*` patterns (core §6.2) on both peers, and CONTENT's pattern IS `system/content`. **Most of
  the 26 inherit this**: a composition is a build-time artifact, and there is no remote-install story
  for the standard corpus.

  **The composition resolver refuses before it emits.** `tools/compose.py` enforces I6 (pattern
  collision), I7 (namespace overlap) and I9 (unmet dependency) plus a pinned-snapshot check, and
  emits `output/<comp>/PLAN.json` with a `--check` mode asserting the resolve is deterministic. It
  needed **no change** for the second language, and none for the third — but the third did
  need a new *concept*, `[system.faces]`, because a composition on that peer cannot promise a
  handler. The resolver's refusals did not change; what it refuses grew by one.

  **What retargeting actually costs is now measured, not guessed** —
  `extension-contracts/content/arch/AUTHORING-NOTES.md` §2, now **five axes across three peers**, with §2.5
  recording which two-column rows survived the third column and which did not. The two rows that
  would have broken a naive template at two peers: the dispatch context carrying no peer (it
  changes signatures — and the third port demoted this to the common case, 2 of 3),
  and the packaging boundary being enforced in one language and a promise in the other (it changes
  how strongly a security MUST is satisfied).

  **Neither port is a translation of the other.** Both are transcriptions of the same pinned
  snapshot. A translation of our own first port would agree with it by construction and tell us
  nothing — which is what makes the `content hash match` result worth anything.

- ✅ **`rust` × `CONTENT` — BUILT, COMPOSED, MEASURED, and it changed the model rather than
  confirming it.** Planned as "tier B: generate, compile, unit-test, no install, no conformance
  claim". **All three of those turned out to be wrong in the same direction**: there IS an install
  (types), there IS a third-party conformance claim (`type_system`, six checks), and the reason
  both exist is the finding.

  **The four faces of one extension get four different answers on one peer.** Types install
  (`Store::bind` is public). The emit consumer installs (`Store::register_tree_consumer`, measured
  live with two negatives). The SDK is a library nothing gated reaches. **The handler body cannot
  be installed at any visibility** — measured over real loopback TCP with both arms, and by
  `rustc` for the three layers a running program cannot ask about:

  ```
  A. nothing bound at system/content        404  handler_not_found
  B. all four §11.6.1 tree writes bound     501  no_handler_body
  C. the same body called DIRECTLY          200  invocations 0 -> 1
  error[E0624] register_handler is private · [E0609] no field `handlers` · [E0603] `Outcome` is private
  ```

  **So D13 was amended: a seam claim names a FACE or it names nothing.** `<peer> is a host` is not
  a proposition; `<peer> hosts <face>` is. A per-peer `[host]` column was always the wrong
  granularity and no composition where all four faces installed could have shown it.

  **The composition's most important line is the one it does not write.** Binding those four tree
  writes is possible and would move the peer from `404 handler_not_found` — true — to
  `501 no_handler_body`, which says a handler exists and is broken. `tools/compose.py` drops the
  pattern from the resolved plan when `[system.faces].handler = "not-installable"`, so the wiring
  program that would do it **cannot be generated**.

  **The riskiest part paid off a third time, and this is the one number worth quoting.** `rust` has
  no public type-definition builder either — `FSpec` / `TypeDef` carry no `pub`, so it is
  `error[E0603]` where `python` had a convention — so its seven field maps are hand-built too.
  `entity-core-go`'s independent transcription reports **`content hash match`** for `blob` /
  `chunk` / `descriptor` against all three ports. **Still three of ours agreeing with one that is
  not**, still one reading of one snapshot, and still no chunker ran.

  **§3.4 turned out to be two clauses that invert.** `rust` is the *strongest* of the three ports
  on "do not expose it" — `mod internal;` with no `pub`, refused by the compiler, no dynamic route
  around it — and the *weakest* on "put a capability-checking wrapper in front", because there is
  no dispatcher-built value to demand. Recorded as two blocks in `EXTENSION.toml`, because
  reporting one verdict for two requirements that invert between substrates is the D13 error one
  level up.

  **And the pre-registered expectation was wrong, which is recorded rather than corrected away.**
  `type_system` predicted 3 checks moving and 6 moved (each type has a `_fetch` and a `_match` —
  AP-1's shape again). `content` predicted zero movement and 3 moved. The second miss is what
  produced the `8 = 5 + 3` correction above.

- **Next: factor the generator.** Three working modules is the input a template should be derived
  from, and `AUTHORING-NOTES.md` §2.5 is the brief: of the rows that had two values before the
  third port, **three inverted or gained a third value and two were demoted from "the invasive
  difference" to "the common case"**. A template derived from the two-column table would have been
  wrong in five places.

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
4. ✅ A second language, then a third. Done: `python` 2026-09-06, `rust` 2026-09-06 — and the
   third is the one that changed the substrate model rather than adding a column to it.

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
