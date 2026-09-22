# Status

The rolling log. One file, not dated — the dated snapshots under `docs/status/` are internal.

---

## Where this is

**`python` × `COMPUTE` is BUILT, COMPOSED AND MEASURED: 125 PASS · 0 WARN · 3 FAIL of 128, from a
bare arm of 0 of 128. 0 core regressions across 778 core checks, 115 unit tests. The second port
of the largest extension in the corpus, and it matched the first exactly.**

**The number that is worth more than the total is the NAME SET.** The improvement sets are
identical across the two ports — 125 of 125 in `compute` and 63 of 63 in `core`, compared as SETS
before either baseline was blessed. Two derivations of one spec, on two runtimes whose value models
disagree about what an integer is, agreeing on every check the oracle scores and on every check it
does not. **That is still not independence** (L18): both ports were written by one team from one
reading of one pinned snapshot, and a cohort agreeing is a cohort agreeing. What it does settle is
narrower and real — the 33 type entities are byte-identical to `entity-core-go`'s own transcription,
because the 63 `type_compute_*_match` checks are a hash comparison against a third codebase.

**The pre-registered band was 118–125 and the measurement is the top of it.** The seven checks of
margin were not a safety cushion; they were seven NAMED places where this runtime's own semantics
differ from §4.1's, written into `[gate.expectation]` before the run: `%` floors where §4.1
truncates; float `/` by zero raises where IEEE returns `±Inf`; `bool` is an `int` SUBCLASS so
`eq(true, 1)` must be forced false; `[-1]` is a legal read where §2.2 says `index_out_of_range`;
`bool({})` and `bool(b"")` are falsy where §4.5's list has neither; `//` floors where an exact
quotient wants truncation; `sorted()` is lex where `canonical_sorted` is length-then-lex. Every one
has a unit test with a control, and every one cost zero checks. **What the band was really pricing
is how much of a host language an implementer adopts without noticing** — and on this substrate the
answer is that they are all catchable, provided the port is written against the spec's helpers
rather than the host's operators. `evaluator.ts` carries a comment predicting the first of them,
written at port one by someone who could not check it.

**THE FIFTH FACE IS NOT INSTALLABLE HERE, AND IT COSTS NOTHING — which is a new shape.**
`Peer.setExpressionEvaluator` is keystone's H7 and exists on ONE of the 46 peers.
`Peer._entity_native_dispatch` on this one evaluates the built-in `compute/literal` shape and then
answers `501 unsupported_expression`, with no consultation step between the two at any visibility,
so the face reads `not-installable` rather than `not-installed`. **Exactly one of the 128 checks
reaches the entity-native path, and it already FAILS on the port that HAS the seam** — for the
unrelated K-5 reason. So `rust × CONTENT` showed four faces getting different answers on one peer
with the extension doing nothing; this shows a peer hosting four of five faces, missing the fifth,
and working completely. **A face can be absent, correctly reported, and cost nothing; the score is
still not a statement about it.** Not routed as an ask: requesting a seam that would not move a
number is tracking another seat's queue.

**The substrate model learned a THIRD ROW KIND, so the tier stays CORE by its own criterion.** The
existing kinds record what a peer CANNOT DO and what cannot be MEASURED. The new one records what a
**runtime does by itself** — nothing is missing, the peer is not narrower, the language simply has
an opinion and §4.1 has a different one. `AGENTS.md` says revisit *"when a port stops changing the
shape of the table"*; this port added a kind at the eighth composition.

**Three instrument defects, all found by running, all in gates that were otherwise working — and
all one shape: a GATE'S OWN CONFIGURATION is the thing nothing watches.** D16's ninth instance,
turned inward from the seventh and eighth.

- **`[sdk_surface]` was authored at port one, citing D16 by name, and parsed by nothing for two
  days** (AP-37). `sdk-parity.py` refuses below two ports, so the block sat in the wrong FORM — 67
  raw identifiers where the key is `kind:snake_case` — until the second port made it run, and then
  it died with `IndexError` mid-`make check`. **The crash was the lucky outcome**: without it all
  67 would have read as *missing from both ports*, and sixty-seven false reds is how a gate stops
  being believed. *A gate whose refusal threshold is N leaves every declaration below N unread.*
- **The `python` surface extractor returned 3 names of 75** (AP-38), because `(.*?)\]` stopped at a
  `]` inside an explanatory comment. The vacuity refusal could not catch it — **three is not
  zero** — which is D15's clause-2 gap arriving at a refusal threshold rather than at a corpus
  assertion. The `typescript` arm had been fixed for the identical cause six days earlier; the arm
  one directory over had not, because arms are per-target by design and nothing compares them.
- **`make type-parity` could not measure COMPUTE on any target, and had not been able to since the
  contract landed** (AP-39). The extension axis was a wildcard *"so a new contract directory joins
  the cohort without a Makefile edit"*; the three arms each hardcoded
  `COMPOSITION="${COMPOSITION:-content-history}"`, a stage that holds `extension-content` and
  `extension-history` and nothing else. It refused honestly (`UNKNOWN`, exit 3) for three days
  inside `make check`. **A gate with three axes can be data in two of them and a literal in the
  third**, and `check-drivers.py` cannot see it because that gate fails a value which DIFFERS
  across targets and this one was identical in all three — recorded as a declared limit of D17's
  enforcement point, not as a new gate.

After the fix: **the first full-parity result this repo has produced.** `75 required · 75 in every
port · 0 drift · 0 undeclared` on the first two-port run, against CONTENT's opening `24 required ·
9 substrate · 18 drift` and HISTORY's second port at 22 names with 20 differing. Not virtue — the
flat-constants decision was already paid for, and this port was written with `[sdk_surface]` open
beside it. **The gate earned its keep by being consulted before the port rather than after**, which
is the first time that has happened here. And `make type-parity` now reports 2 ports agreeing on
all 33 compute type entities by content hash AND field map.

**One finding routed, and the contract had pre-committed to routing it.** §3.5 pins
`count_out_of_range`'s code and its refuse-not-clamp rule and leaves the BOUND unstated;
`[assumptions].range_max_length` said at port one that *"a `python` or `rust` port will have a
different one … the second port is where it either agrees or produces a routing packet."* It
disagrees: `2**32 - 2` on V8, `sys.maxsize` on CPython, each port reading *"the maximum
representable array length"* as its own runtime's — the only reading the sentence offers. §3.5
declined to clamp **because the refusal is observable**, which makes its trigger part of the
program's meaning. Neither port was changed and no number was standardised across them: picking a
value the spec left open, on a sample of two, is L18 with a decimal point. `A-26`.

**Two divergences between our own two ports, declared rather than reconciled**, and they are a new
category in `[assumptions]` — ours-vs-ours, where the spec does not care and there is nobody to
ask. A malformed expression is a `compute/error` at 200 here and an exception out of the handler
there (§2.4/F10 makes this port right). The reserved relative forms §1.4 names — `./x`, `../x`,
`*/x` — are refused here and accepted there, **because one port called the peer's own
`canonicalize` and the other wrote three characters of it**: D12's *use the peer's primitive* is
usually argued from semantics, and here it bought a §1.4 refusal nobody had noticed was required.

**`typescript` × `COMPUTE` is BUILT, COMPOSED AND MEASURED: 125 PASS · 0 WARN · 3 FAIL of 128,
from a bare arm of 0 of 128. 125 improvements, 0 core regressions across 777 core checks, 52 unit
tests.** The largest extension in the corpus — 33 owned types against HISTORY's six, 128 oracle
checks against 34 — and the first whose MUST surface is an interpreter rather than a handler.

**§3.3's install audit and §7's reactive mode landed on 2026-09-10 and took the residue to three
checks, none of them ours.** All fourteen moved: the six-step reactive spreadsheet, both D8
walk-completeness rows including the `apply.args` discriminator, the dynamic-handler hot-swap, the
two-subgraph cascade chain, and all three CP1 install-audit checks — **and the two WARNs went with
them**, which matters because a WARN there was never partial credit, it was the check saying it
could not run. What is left is `compute/apply` handler mode, which needs a local-dispatch seam the
peer does not expose (see below).

**COMPUTE now installs a SIXTH face, and it is the first emit consumer in this corpus that WRITES
BACK.** HISTORY's records a transition and stops; §7.2's `on_tree_change` re-enters the evaluator
and binds a result, which re-enters the bus. Two peer properties become load-bearing at that point
and the spec pins neither — §9.4 leaves emit delivery implementation-defined. Delivery is
**sync-inline**, so a `tree:put` has already produced the new result when it answers; and a write
from inside a consumer re-enters the bus, which is what makes a cascade a cascade. **Measured, three
arms: with §7.3's counter disabled the peer still freezes; with our re-entrancy backstop disabled it
still freezes; with BOTH disabled it dies with `RangeError: Maximum call stack size exceeded`.** On
this substrate §7.3's *"this cascade MUST be bounded"* is the difference between a frozen subgraph
and a dead peer, and no wire oracle can see the difference between the first three.

**The first port reached 100 of 128 with the §4.1 evaluator alone, and that is the number the
compute track needed.** The pre-registered band was 40–80 and it missed high; the miss is kept, and
it is a fact about the ORACLE. The band assumed four unimplemented sections — §3.3 install, §3.5
builtins, §4.6 memoization, §7 reactive — would cost proportionally. They cost 26 checks between
them, because the `compute` category is overwhelmingly **evaluation vectors**: literals, arithmetic,
comparison, logic, control flow, closures, scope, budget, tail calls. **The §4.1 algorithm IS the
category**, and the residue was four named bounded pieces of work rather than a long tail.

**Then §3.5's builtins and two defects took it to 111, and §3.3 plus §7 took it to 125.** All
thirteen §3.5 builtins run — the five inline-equivalent aliases (§10.2 SHOULD) sharing the inline
code path, plus `map`/`filter`/`fold`, the four v3.24 primitives and `store`, which §10.1 makes
MUST. The install audit runs four phases, **pre-flight then commit**, so a re-install whose audit
fails leaves a frozen subgraph's metadata untouched — §3.3's atomicity clause, and the reason the
operation refused to ship half-built: Phase 2b SEALS `authorized_data_hashes`, which §4.2 Tier 2
then trusts without re-checking.

**Two of the four "real bugs" were fiction, and the way they were fiction is the more useful
finding.** `v319_n5_closure_field` and `v319_f11_filter_fn_arg` failed with
`expected array, got entity.Entity` and were filed as a closure-typing bug in the LAMBDA branch.
Both vectors dispatch `system/compute/builtins/filter`; the `entity.Entity` was **our own
`compute/error`**, because §3.2's F10 makes an evaluated error a value at status 200. **So the
oracle's message for "this port refused the expression" and its message for "this port mis-typed a
value" are the same string** — a property of any check asserting on a value shape in a protocol
where failure arrives as a well-formed value at the success status. Two worklist items with a
plausible file and line named, and the fix for both was a section neither mentioned. Written up as
AP-31; the generalisation is D12/L8 in a new costume — **an oracle's failure MESSAGE is an artifact,
and before it becomes a worklist item, read the check that produced it.**

**The two that were real were both a SPEC finding wearing a bug's clothes, and they share a cause
with the two already routed.** §2.3's SA-1 MUSTs that a value-type entity evaluate to itself, and
§4.1's `evaluate_inner` has no arm for any of the four — so a stored `compute/closure` answered
`unknown_type` and `load_scope` was never reached. And §2.3's v3.19c option-α clause requires
navigation to compose through an in-flight constructed entity, while §4.1's construct arm keeps no
in-flight representation at all. **Four declared deviations now, one structure: an amendment reached
the prose and the conformance corpus without reaching a list or an arm elsewhere in the same
document — and three of the four missed §4.1, the section a port is actually written from.** None is
catchable by the corpus, because `entity-core-go` carries the corrected form in all four cases.

**So the spec snapshot is now read as DATA, by a gate.** `[[spec_lists]]` declares each of the
spec's own enumerations by section, anchor and exact membership; `tools/check-spec-lists.py`
(`make spec-lists`, in `make check`) re-parses them out of the pinned bytes and fails when parse and
declaration disagree, so a re-pin that moves a member cannot silently invalidate a transcription.
**Its first run strengthened a finding already routed**: §4.1's arm ladder has thirteen arms and
omits `compute/index`, `compute/length` and `compute/numeric-cast` — the same three the two
predicates omit, in the switch that evaluates rather than in a predicate that resolves. Three sites,
one amendment, and the third had never been counted.

**`compute/apply` handler mode is the one §10.1 MUST this port cannot reach, and it is a host
gap rather than a decision.** §4.1's `ctx.dispatch_execute` needs a re-entrant dispatch to a LOCAL
handler under the caller's capability. The peer exposes none: `PeerServices` carries no dispatcher,
and `HandlerContext.outbound` is the §6.13(b) **outbound** seam — over the transport, to a URI, and
`null` without a connection. H7's shape exactly, and routed the same way. It costs 3 of 128,
including the check that reaches an entity-native handler body — which is the ceiling on the whole
collapse argument, since an expression that cannot delegate cannot reach a native primitive.

**And implementing a section made our coverage number go DOWN, which means the old one was
lying.** Seven §3.5 requirement rows cited a single oracle check that asserts the args TYPE ENTITIES
are published and never dispatches a builtin — so they read *fully measured* while the section was
absent. Re-mapped against the vectors that actually exercise it: `MUST 44 oracle / 0 partial` became
`MUST 37 oracle / 7 partial`, each `partial` naming its real gap (the four v3.24 primitives have no
oracle vector at all, and the entire consumed/contained disposition table is unmeasured in every
position). AP-32, and D14's asymmetry in a new column: **the number to distrust is the one that
improved while nothing ran.**

**Five more findings, and they are the previous mechanism in a SECOND HOME.** The §4.1 family said
*"the section a port is written from is furthest from where the amendments are ruled."* §3.3 is the
second such section, and three of the five below are its own listing disagreeing with prose in §3.3
or one section over: its `audit_walk` descends only scalar fields where §7.1's descends containers
under a v3.27 `[MUST]` — **and §3.3's walker is the one that builds the list Phase 2 capability-
checks**, so a faithful transcription authorizes a top-level tree read and skips the same read one
function-argument deep; §2.1's Q23 MUSTs install-time rejection and §3.3 has the neighbouring F5
clause and not that one; and §3.3's own SA-11 prose exempts the pure builtins from handler-target
authorization while its listing appends every one of them. The other two: **§9.1's fifteen-row error
table names none of the five codes §3.2/§3.3/§3.4 raise**, one of which §10.1 MUSTs by name; and
§5.2/§5.5 spell the compute resource limits as a field on the capability TOKEN while core §5 carries
them on each GRANT ENTRY — so a literal transcription reads nothing, falls back to peer defaults,
and produces the constraint escalation §5.5 exists to prevent.

**Two of those five are unmeasured in the posture we run the conformance suite in — and the posture
is ours, which is a correction to what this log said a day earlier.** It previously read *"invisible
to the conformance corpus in principle,"* attributed to the validator launching its host with the
degenerate `default → *` grant policy. The validator launches nothing; it dials an address. **Our
own harness** starts the peer under test that way, so every install-time capability check passes
whatever the audit collected and an under-authorizing audit scores identically to a correct one.

That distinction is not pedantic. `ENTITY-CORE-PROTOCOL` §6.9a (Peer Authority Bootstrap) deprecated
the wide-open debug grant in v7.74 and schedules its removal for v7.75, replacing it with a **declared seed
policy** — and under any policy narrower than `*` the two readings of §3.3 answer differently. So
these findings are measurable; they are simply not measured by a suite we hand a wide-open peer. The
evidence on file remains a diff of two listings plus our own tests, and it is still filed that way.

**A control that stayed GREEN with the code deleted, and it changed a discipline.** The test for
§7.2's convergence check asserted the two things a consumer can see — the result hash did not move,
no bind event fired — and passed with our implementation of the clause **removed**, because
`EntityTree.put` emits only when the bound hash changed and `ContentStore.put` only when the hash is
new. The instrument was fine; **the property was not ours.** Its prior in a different shape is AP-19
(oracle checks passing in the bare arm), so D15 gains a sharpened clause: *the control is the
absence of the SUBJECT, and a control that stays green is a finding about the PROPERTY.* Do not
delete the assertion — the layer that owns it today is not the layer the spec addresses — add one
only the subject can satisfy, and record which layer owns it.

**And a claim of ours was wrong in the plainest possible way.** A contract in this tree said the
peer exposed no path-scope capability predicate an extension could call, so §6.2 was satisfied at
the dispatch boundary and a caller reaching `system/compute:eval` could read any tree path. **The
predicate is public, and this repo is the seat that routed it — keystone H9, landed, recorded CLOSED
on our own tracker.** One tree, two answers, and nothing joins a tracker row to an assumption block.
The check is now per tree read on both capability-bearing paths, with its own negative control,
because a peer running the wide-open grant policy cannot distinguish a real check from `return true`.

**Three normative rules were got wrong and fixed by the oracle telling us, and they are the ones
worth carrying to the next port.** §2.2 rules 8/10/11: `add`/`sub`/`mul` are **sign-agnostic**
64-bit two's-complement, while **`div`/`mod`/`compare` are signed-default** — an operand whose
magnitude is ≥ 2⁶³ reads as its negative counterpart — and rule 11's unsigned intent is a property
of the **expression graph**, true only when a `numeric-cast → uint` is the *direct* operand entity.
Any indirection drops it. We read operands at raw magnitude, so `div(2⁶⁴−2, 2)` answered 2⁶³−1
where the spec says −1. Four checks caught it. Also: `length("hello")` is `type_mismatch` and we
had invented string support; `cast(-1, uint)` is 2⁶⁴−1 and not `cast_out_of_range`, because an
integer source is a bit pattern being reinterpreted while a float source is a value being converted.

**The fifth face exists, and it is the first one in this repo.** `DESIGN-THE-SDK-LAYER` §1 names
four — `types` · `handler` · `emit_consumer` · `sdk` — and D13's face amendment pins that
vocabulary. COMPUTE installs a fifth: **the expression evaluator**, through
`Peer.setExpressionEvaluator` (keystone's H7, which this repo routed on 2026-09-03 and which landed
the same day). It qualifies by D13's own test rather than by analogy — `handler` and `evaluator`
are two seams into the same dispatch path, every peer in the cohort hosts the first and
`setExpressionEvaluator` exists on **one** of the 46, so folding them together would report
`installed` for a peer that refused it. `tools/compose.py`'s `FACES` grew by one value and the
refusal did not relax; the composition **reads the evaluator back off the peer** rather than
trusting the setter, because keystone planted exactly that defect against their own H7 work.

**And the error-code gate could not see COMPUTE's error surface at all.** `[error_surface].emit_pattern`
was one regex for one mechanism — `errorResult(Status.X, "code")` — and §3.2's F10 rule makes an
evaluated `compute/error` a **value at status 200**, so thirteen of the sixteen §9.1 codes never
reach `errorResult`. The single pattern found **5 of 13 and reported the surface CLEAN**. That is
D15's false-green and the second time a corpus assertion in this gate has bounded a pattern that
matches the boring half rather than one that stops matching. `emit_pattern` is a **list** now, one
planted self-test line per pattern, and `--self-test` refuses if the two lists differ in length.

**Two findings in the normative body, and they correct what the first packet said.** The routed
packet's §0 originally read *"none is in the normative body"*, on a close read of §§1–8 that found
the algorithm, arithmetic, purity and determinism clauses sound. **That claim survived exactly as
long as it took to start emitting the type layer.** §4.2's `is_compute_type` and §4.7's
`is_compute_expression` each omit `compute/index`, `compute/length` and `compute/numeric-cast` —
three types §2.2 defines and §10.1 MUSTs — and §4.2's omission makes a valid expression graph
**unresolvable**, because Tier 1 is the only tier admitting an ordinary sub-expression. And
`system/compute/subgraph` declares six fields at §2.5 while §3.3 writes seven, the seventh being
`authorized_data_hashes`, which §4.2 reads, §1.1 names load-bearing and §10.1 MUSTs. Both have one
cause: an amendment that reached the definition sections and the conformance list but not the
predicate or the type block that also had to change. **Neither can be caught by the conformance
corpus, because `entity-core-go` already carries the corrected form in both cases.**

---

**Build 3 opened here. `EXTENSION-COMPUTE` is pinned at v3.29, the bare arm is measured, and the
first read found five things — every one of them in the machine-readable furniture.** The snapshot is `shared/spec-data/compute-v3.29/` (`d1de1942…`), with both
companions byte-identical to `history-v1.10`'s.

**`DESIGN-THE-COMPUTE-TRACK.md` was written against v3.27 and there had never been a snapshot**, so
`AP-27` applied to a *reading* rather than to a copy and no pin mechanism could have noticed. Two
versions had landed. **One of them closes that document's §6 item 6, by a bigger move than the row
predicted**: the row said the builtins override guard becomes ours *if* `PROPOSAL-EXTENSION-HOST-INSTALL-SEAM`'s
D1 narrows core §6.2's `system/*` reservation. `ENTITY-CORE-PROTOCOL` **0.8.2.13 withdrew the
reservation outright**, and `EXTENSION-COMPUTE` v3.29 restates §4's override prohibition on its own
basis — a cross-peer determinism MUST binding **every installation path**. There is no core rule left
to delegate to. **The guard lands in port 1 rather than being discovered at port 26.**

**The bare arm is the result worth quoting, and the number that matters is the zero.** Against a bare
keystone `typescript` peer, `-category compute`: **128 checks, 0 passing, 0 skipped.** 101 are
`blocked: depends on handler_present`. `content` bare passes **4 of 13** and `history` bare passes
**1 of 34**, and in both cases those passes measure something other than the extension (AP-19).
**Compute's category has no vacuous passes at all**, which makes it the cleanest differential
instrument this repo has been handed — §3 of the compute-track doc claimed COMPUTE was the
best-instrumented extension in the corpus from a roadmap tier, and it is now a measurement.

**The contract landed with port 1, which is what the instrument said would happen.** `req-coverage.py` refuses an
extension whose declared `oracle_category` is absent from the executed corpus, so the contract
could not exist before a composed report did — and adding a `pending` state to get one in early
would have been a suppression with no destination. `extension-contracts/compute/EXTENSION.toml` is
in the tree now with 84 declared requirement rows, and **the join is by SECTION** because §10 has
no §8.5a ids: 44 MUSTs measured by the oracle, 2 by our own tests, 7 by nothing and each of those
carrying a sentence saying why.

**Five findings routed** (`ROUTING-2026-09-09-d-arch-*`), and their *distribution* is the finding:
we read §§1–8 closely enough to emit an evaluator and found nothing to route. CONTENT gave four
body-level findings on the first read and HISTORY gave four; COMPUTE gave zero. What it gave instead
is drift in the header, the constants tables and §10 — the surfaces whose only consumer is a tool.
That is our own D16 arriving from the outside. The declaration header omits the emit pathway §7.2
consumes and `SYSTEM-COMPOSITION` §2.2 puts at position 5; §10.1 MUSTs three behaviours of an
operation §10.2 makes a conditional SHOULD, while the oracle hard-FAILs a manifest that omits it;
§9.2's operations table omits `install`/`uninstall`, which is CONTENT §10.3's defect arch already
fixed once **plus the sentence that fix added and this one lacks**; the §3.1 manifest spells the
pattern `system/compute/*`, 2 of 18 corpus-wide and both outliers are the two specs we have read for
generation; and `SPECIFICATION-FORMAT` v1.3 §8.5a stands at **1 of 26** a week after landing, which
is GI-11's own resolution turned around — *a declared shape with no enforcement point*.

**And one we withdrew before sending, which is worth more than the five.** The header's
`Owned namespaces` names `system/compute/` and says nothing about the top-level `compute/*` namespace
where all twenty IR types live. That reads as a serious omission until you read the guide clause it
answers: §3.3 scopes the field to *"every `system/<ext>/… subtree"*. **The header is correct as
written.** D12/L8 caught one step before it became a packet, by reading the canonical source instead
of the plausible inference.

**The re-read also caught a stale forcing claim of ours, in five live files, and it is AP-2's
mechanism on a rule rather than on a number.** Both shipped contracts said `[install] model =
"sdk-native"` was *"forced, not chosen"* by core §6.2, and that *"every extension owning a `system/*`
pattern inherits this."* 0.8.2.13 withdrew that sentence. **The value does not move** — both peers we
compose against still refuse, each quoting the withdrawn rule back to the caller — but the
generalisation is dead, and what was a permanent property of the standard is now a deployment policy
measured on 2 of 46 peers. It is a `[substrate.wire_install_refusal]` row now, reading `unknown` on
the other 44 **and `unknown` by execution on all of them**, because no gate here has ever run a wire
register at a `system/*` pattern.

---

**The outbox is machine-routable, and it had not been. `unaddressed 11 → 0`.** Cross-repo
delivery here is: commit a document to your own tree and the other party reads it. The shape that
makes that mechanical is pinned in `AGENTS-STANDARD.md` §*Routing packets* — a three-field
addressee block opening the document — and its enforcement point is the receiving seat's
instrument. **Both existed; nothing here had ever run one against us.** Eleven of our
twenty-two packets named their recipient only in the H1 and in prose, so they were filed as
UNADDRESSED, which is UNKNOWN and is never *"not ours."* All twenty-two now carry the block; not
one word of any finding was changed. The backfill moved one packet from UNKNOWN onto the
receiving seat's actual worklist, so **the owed count went up, correctly** — a number that gets
worse when a defect is fixed is the number that was lying.

**And there is now one tracker per counterpart**, on `entity-system-architecture`'s cleanup
standard of the same day: `docs/status/TRACKER-<counterpart-repo>.md`, four sections, stable ask
ids that are never renumbered. Four of them — arch, keystone, core-go, meta. **The consequence is
larger than a file format: arch reconciles against the tracker, not against the directory**, so
the completeness obligation moved off the filesystem and onto a document somebody has to remember
to edit. Gated, because that is the most forgettable kind of obligation there is: every packet
must be cited in the tracker of every repo it is addressed to, by **full stem**. That check
failed on its first run against our own four trackers, which had used shorthand.

Gated at `tools/check-routing.py` / `make routing`: block shape, field content, filename-agrees-
with-field, and id uniqueness. Citation form is **counted and never failed** — a bare
`ROUTING-<date>-<letter>` cannot be resolved by a reader, and the sharp case is cross-repo, where
our own documents cited another seat's id on a day this tree also numbered. Those are fixed; the
rest is a census, because a prose sweep over committed record should be a decision rather than a
discovery. **D16's seventh instance and the end of its arc**: the first six were *nothing watches
this*, and this one is *something watches this, in a tree we never run*.

**Re-pinned to `EXTENSION-HISTORY` v1.10, two versions in one step, and the reason it was two is
the finding.** v1.9 and v1.10 both landed 2026-09-08 and **nothing in this tree could notice.**
Every pin mechanism we have — the snapshot manifest's digests, the `[extension].snapshot` key,
`req-coverage`'s undeclared/stale rules, the citation gate — is a statement about the **copy**. A
snapshot cannot observe that the original moved, which is what makes it a snapshot, and it is why
*"the pin is green"* and *"the pin is current"* read identically in a status log. `req-coverage`
exists so that *"a re-pin cannot add or re-word a requirement unnoticed"*, and it is entirely
correct about that: it gates the re-pin, and nothing gated the **decision** to re-pin. Catalogued
as **AP-27**, recorded rather than fixed — the cheapest correct answer is to read the upstream
spec at the start of any session that touches an extension, which is a procedure, not a gate.

**Both versions are our own routed findings coming back as spec.** v1.10's `pattern_exclude` is
`ROUTING-2026-09-07-arch-*` — the measurement that §6.3's worked `pattern: "*"` makes a peer audit
its own protocol bookkeeping, one or more transitions per served request, permanently, in a store
§3.3 says cannot be pruned. **Arch reversed its own recorded lean and said why**: their reply had
leaned toward widening §3.2's self-guard to *"local, engine-written protocol paths"*; what landed
is the config field, because core §1.9 makes those paths a **convention**, so the spec does not
know the set it would have been defaulting. A lean is not a ruling.

**The normative content of `pattern_exclude` is the ORDER, not the matching** — `HIST-R16`, MUST.
Exclusion is checked after the most-specific config is selected and before the event filter, and
an excluded path **does not fall through** to a less specific one: *"an exclusion is a decision,
not a failure to match."* §2.2 says two conformant readings exist without that sentence and that
they differ on a path two configurations cover. All three ports implement the ordered form, each
with five tests, and **one of the five is the only one that discriminates** — the other four pass
under both readings. Verified by planting a defect and observing 4 of 5 go red on every port.

**v1.9 made §9.1 an addressable inventory** (`SPECIFICATION-FORMAT` v1.3 §8.5a) — stable
`HIST-R<n>` ids, which is `ROUTING-2026-09-07-d` landing. Our own `H-R1…H-R15` were a local
invention filling an upstream gap, and the moment the gap closed they became a second numbering
for one set of obligations. They are retired; every `[conformance]` row is re-keyed upstream.

**Re-keying found a defect in our own instrument, and it is the sharper half of the re-pin.**
`req-coverage`'s `LEVELS` predated §8.5a and omitted the two **negative** levels, so §9.1's
sixteen rows parsed and then a filter threw away **`HIST-R8` — the `MUST NOT` recursion guard**,
the one row in that inventory this repo authored its own wire check for. The tally printed fifteen
and was internally consistent. **A missing prohibition reads as "the spec forbids nothing here."**
The vacuity refusal fires at zero and fifteen is not zero; a count-based corpus assertion clears
any floor worth setting. **So D15's clause 2 is sharpened — a corpus assertion names the PROPERTY
the input must have, not a count of units** — this being its second instance in a different shape
(AP-28). The defence is `assert_contiguous_ids`: §8.5a ids are contiguous from 1, so a hole means
the parser dropped a row. The longer level list fixes today; the property fixes the next one.

**And `[contract]` is a transcription now, not a derivation** — GI-5's header arrived at 26 of 26.
Six of our seven derived fields matched. `points_consumed` did not: we had `emit.tree_change`
alone, and the header declares the `clock` execution-context field too. **A derivation from one
document cannot see the fields another document contributes.** We had argued the missing header
cost us presentation rather than content; measured, it was one field in seven.

**And the conformance axis grew by three checks that were always there — we had never passed the
flag.** We report the core profile as **776**; keystone reports **778**, at the **same oracle
commit**. Neither was wrong: `origination` needs a second live peer, and without one
`validate-peer` collapses the whole category into a single `origination/skipped` sentinel. Three
checks behind one entry, for the life of this repo.

**D14 was satisfied and did not help, which is the finding.** *"A number cites the artifact that
produced it"* — and `776` did: counted by command out of the report beside the bytes, never off a
maintained table. **The artifact was cited correctly and the artifact was incomplete**, because a
report is a function of the FLAGS and nothing recorded which flags produced it. *"776 checks"*
reads as a fact about the oracle; it is a fact about the oracle **as we invoke it**. And it failed
in D14's own asymmetry — a missing check makes the total *smaller*, and nothing downstream asks
whether a number should be bigger. **AP-29.**

Fixed in `tools/host-launch`: `entity-core-go`'s own `entity-peer` on `PORT+2` for the oracle path.
All three now PASS in **both** arms, so they add nothing to any differential — the value is that
the reports stop carrying a skipped category, and **a skip is a failure**. A missing reference
binary **exits 3** rather than degrading to the old behaviour, verified by pointing `REFPEER` at a
nonexistent path. `make expectation` then refused all six baselines on the changed check set —
D21 working, second event of that kind and the first we caused ourselves.

---

**`EXTENSION-HISTORY` v1.8 landed and we re-pinned to it, and three of the changes are readings
this repo routed.** All three were shipped as *declared deviations* from v1.7's own pseudocode —
a bare `*` canonicalizing to the local namespace and tested before the first-segment check;
`*/rest` corrected to `/*/rest`, the spelling core §5.4 rejects by name, so a peer configuring
cross-peer history matched nothing and reported no error; and `prune_history` walking and
reporting while mutating nothing. v1.8's §2.2 pseudocode, §2.2's corrected table and §3.3 are
those three. Not luck: generating an implementation forces a spec's table and its pseudocode to
a single value, and these two disagreed.

§6.2 was rewritten in the same direction. A v1.7 unit-test docstring here had derived that a
scalar and the §6.2 tuple cannot disagree on any pair the core grammar can express, and that
v1.7's worked pair `a/*/c/*/e` is not a pattern at all; v1.8 retracts that pair for that reason,
proves the same non-constructibility by cases, rewrites `HIST-CONFIG-SPECIFICITY-1` and adds
`-2`, where key 1 ties and only key 2 separates. Both are unit tests in all three ports now,
both insertion orders, and all three passed on the first run with no code change.

**And the re-pin found one going the other way.** Appendix A's 403 row is `access_denied`; all
three ports emit `capability_denied`, which is the core protocol's own 403 default and what its
authorization discipline names for a request-time deny. Two landed specs, two spellings, one
path — routed rather than resolved locally, because switching three ports would mint an
authorization code core declines to define. It was invisible because the code gate walked
**emit sites** and asked whether each was declared: a code the spec names and no port emits was
outside its corpus entirely. The gate now reads both directions.

---

**Latest: the oracle grew by 20 checks, we re-based on it, and the tree is green end to end.**
`entity-core-go`'s `validate-peer` core profile went 756 → 776 entries. Confirmed in their tree:
`tree_put_error_codes.go` and `connectivity_conn_errors.go`, added for `EXTENSION-TREE`
Appendix A v4.4/v4.5 and connection error handling. **The oracle got stronger**, which is what we
want from a tool that is the oracle because it is not the thing under test. The new checks pass in
*both* arms, so none of it is a statement about our compositions.

**The count is +20 ENTRIES and this log first said 19 — the correction is the reusable part.**
`category.name` is the unique key (776 entries, 776 distinct composite keys); bare `name` is not,
because `skipped` is a sentinel appearing once per category, 40 times in all, so a bare-name diff
collapses it. AP-8's mechanism in an analysis rather than in an instrument. Honest statement:
**+20 entries, 19 newly-named** (`connectivity` 13, `tree_operations` 6), **plus one a bare-name
diff cannot identify** because its name already exists in another category.

**`make expectation` REFUSED rather than compared** — *the check SET changed; nothing below is
comparable until this is understood.* D21's temporal baseline doing exactly its job on the first
event of this kind since it was ratified. A gate that had silently diffed across a changed check
set would have reported movement belonging to the oracle as though it were ours.

**All six compositions re-measured and re-blessed: 0 regressions, 0 build failures**, and 0
containers stranded across ~40 minutes of continuous peer launching. Every improvement NAME set
was verified unchanged before anything was blessed, because a total that moves for one reason must
never absorb a change that happened for another.

**One exception, and it was the finding.** `typescript/content` declared
`concurrency.t1_1_concurrent_demux` in `improved` and it stopped improving.
`typescript/content-history` had declared that same check as a `[[gate.straddle]]` the day before
with exactly this reasoning; **the composition written first never got it** — AP-10's shape on a
declaration rather than on a driver, where a correction lands in compositions N..last and never in
1..N-1 because N+1 is written by copying N. Fixed by declaring the straddle, not by dropping the
name, which is the silent version of the same thing.

---

**The host contract is declared and gated, which closes a contradiction that had been
open since the repo was opened.** The charter said the host needs `make` + `podman` and nothing
else. It has never been true here: `make check` runs eleven `tools/*.py` on the host, and the
Makefile shells `python3 -c` to read a profile *before it can choose an image*. Nobody had ever
declared Python as the tooling language — there was no such statement anywhere in the tree.

**The ruling is not that this was fine.** Python and Bash are **de facto** dependencies across
these projects — not adopted, but reached for anyway despite the stated standard. That is a
discipline failure at project scale, not a design decision this repo made, and the scope of it is
not ours to rule on. The reality is accepted for now because changing it is far more work than
declaring it. What is ours is narrower and is what landed: the dependency is now *declared* and
*bounded* rather than accumulating under a sentence saying it is absent.
`tools/tooling.toml [host]` is the data, `make toolchain` is the check, and
`docs/adr/0001-the-host-toolchain-contract.md` is the reasoning.

**The invariant is the boundary, not the inventory: the host half is stdlib-only, and anything
needing a third-party library runs in a container.** That was already true and had already been
*tested* — the canonical ECF codec cannot load on a bare host, and when that was found the two
entry points reaching it were containerised rather than the contract widened. The gate makes
that the default rather than a good call somebody made once.

**Two things it taught, and the first is the one worth carrying.** An `import`-statement scan
reports this tree as **100% stdlib** and is right *by accident*: the one genuine third-party
dependency arrives through `__import__(decl["package"])`, with its name held in a TOML file, so
no import statement names it and no scan for one can see it. The obvious gate would have printed
a clean verdict over a corpus that excluded the only thing it exists to find. Caught in review,
before the first run — the second time in this repo's history, after `check-error-codes.py`.
And the streak held anyway: **it went red on run one**, on its own declaration, where TOML bound
two bare keys to an array-of-tables entry instead of to the parent. Eight instruments, eight
that found something the day they were written.

Catalogued as **AP-26** — *a dependency that accumulated under a charter sentence saying it was
absent*. **Not promoted to a discipline**: one incident, and the ladder is explicit. The wrong
declaration is the expensive part rather than the dependency — anyone asking what the host needs
got a confident wrong answer from the most authoritative file in the repo, which is D16's third
instance one level up. `AGENTS-STANDARD.md` is injected unchanged and is not ours to edit; it
contradicts itself at L35 and L178 (the pin-hygiene check it prescribes is `python3 …`), and
that is routed to the meta seat as an observation rather than a request.

---

**The check corpus and every arm's verdict travel as canonical ECF. There is no JSON at any
hop.** The gate had been emitting JSON so a third arm could read a corpus of checks, and the
operator called it: the ecosystem's data language is CBOR in Entity Canonical Form, the peers
ship conformant codecs, and a JSON hop is a second data model with no canonical form, no byte
strings and no map-ordering rule — the three things `content_hash` is computed from. The corpus
is now encoded through a peer's own codec used as a library, both arms decode with their own,
both encode their verdicts as ECF, and the comparer decodes those. **10 of 10 still admitted:
the transport changed and the measurement did not.**

**The report side is what made it non-negotiable.** A JSON verdict needs a JSON *writer* in
every arm, and the arm queued behind this one has neither a parser nor a writer in its offline
crate closure — so keeping JSON would have put a hand-rolled serializer in the half of the tree
that multiplies by the target count.

**And the two-codec property is now exercised on every run**: one implementation encodes, two
others decode, a third encodes a verdict the first decodes. A canonical-form defect surfaces as
a cross-arm disagreement rather than as agreement — the property the locked ECF corpus was
established with.

**Three findings from doing it**, in `docs/DESIGN-THE-CBOR-INTERCHANGE-LAYER.md`:

- **The codec is not separable from the crypto.** `import entity_core` runs a package `__init__`
  that pulls Ed25519 in, so the canonical ECF codec cannot be loaded without it —
  `ModuleNotFoundError: No module named 'cryptography'` on a host that has everything else.
  *"Adopt as much or as little of the system as you want"* is not true of the data language
  today.
- **Nothing in the ecosystem can read its own human-readable form.** `ENTITY-CBOR-ENCODING` §8
  specifies diagnostic notation and Appendix E authors the ECF conformance corpus as `.diag`
  compiled to `.cbor`. The only diag parser is `entity-core-go`'s `cmd/internal/diagcodec`,
  behind Go's compiler-enforced boundary; the only view is `entity-shell cat -diag`. There is
  **one** shared copy of the corpus, referenced by **39 peer trees**, and **not one of them can
  parse the `.diag`** — so every new consumer's cheapest path is JSON, which is exactly what
  happened here. *(Both numbers corrected 2026-09-09: this first read "shipped to all 46 peers",
  taken from the cohort's size rather than from a command — AP-1. The re-deriving commands are
  inline in the design doc.)* The read-in names five operations,
  a library half and a CLI half, what is normative (the dialect) versus idiom, and a byte-exact
  oracle that already exists: the 71 locked vectors must reproduce from their own `.diag`.
- **It does not need keystone.** Correcting a claim made the same day: our composed hosts
  already bind entities in-process on all three substrates and `types` installs everywhere,
  including `rust`. Seeding a peer is something we do today.

**The `rust` ext-checks arm is built and parked, not committed.** It compiles with zero added
dependencies, decodes the ECF corpus and completes the handshake — then hangs on its first
EXECUTE, with the peer never answering and `Io::outbound` waiting on a condvar only a response
or a close will wake. `Peer::dispatch` has exactly one silent-drop path (root type ≠
`system/protocol/execute` → `None`, nothing written). Either our request is malformed in a way
that reaches it or the peer owes a status it is not sending — possibly both, and the second is
routable. It sits at `.agents/wip-rust-ext-checks/` rather than in
`languages/rust/gates/ext-checks/` (dead) **because the Makefile discovers arms by wildcard**, so
committing it would hang `make ext-checks` for everyone. Move the directory back to pick it up.

---

**§6.2's two REQUIRED conformance vectors are measured, over the wire, and they are the
first authored checks whose subject is the recorder rather than a handler.** `HIST-CONFIG-
SPECIFICITY-1` and `-2` are checks the spec wrote for an implementer and nothing upstream runs —
no check in the oracle's executed corpus configures two overlapping patterns at all. Both are
now `extension-contracts/history/checks/*.toml`, and both were **ADMITTED on `python` and
`typescript` on their first run**: `make ext-checks` reads 10 of 10 (check × arm-pair), pass
composed and fail bare.

Nothing in either check calls a history operation. Configuration is a standard tree `put` (§6.1),
selection happens inside the emit consumer (§6.2), and the outcome is read at §3.1's head
pointer — a plain tree binding — with a core `system/tree` get. So the checks measure the
extension through faces a peer that cannot host a handler body still has, and the gate's own
coverage line for that target moved from *"an arm would measure 0 of 3"* to **"an arm would
measure 2 of 5 — this target is worth an arm now."** That line is computed from the composition's
declared faces rather than written by hand, which is why it could flip on its own.

**Three things the authoring taught, none of them about the ports:**

- **"Both insertion orders" is not one lever.** The three peers do not enumerate a listing the
  same way — two sort by segment, one returns the tree index's insertion order — and both are
  conformant, because §3.9 specifies a listing's contents and not its order. A check that moved
  only write order, or only name order, would exercise a single enumeration on two of the three
  targets while reading as though it had covered both. Each check inverts the two together.
  Recorded as a substrate row, because §6.2's MUST exists precisely to make this unobservable.
- **An emptiness assertion needs an attribution control, not just a positive one.** The central
  assertion is that a path is *not* recorded, which is also what a peer produces if the pattern
  never matched. Each check therefore runs the same pattern family and path shape a third time
  with one bit flipped, and asserts the opposite outcome.
- **A check that names a type no registry defines behaves exactly like one that names the right
  type.** One of ours did, from the day it was written, and nothing anywhere could say so.
  Corrected; every check now declares each wire type it sends with the authority that defines it,
  and an undeclared one fails.

---

**The first authored extension checks are running, and the rule that admits them is the point.**
`make ext-checks`, three checks on three MUSTs the oracle reaches with nothing —
`EXTENSION-CONTENT` §5.2/§6.2 (the resolved entity travels in `included`, not just its hash),
§6.3 (`root` present in envelope mode and **absent** in entity mode, both halves), and
`EXTENSION-HISTORY` §3.2 (the recorder's own head-pointer write is not itself recorded). **All six ADMITTED — three checks × two targets** (`python`, `typescript`): pass composed,
fail bare. `rust` joins by adding a `run`.

**An authored check is not admitted until it has been seen producing a different answer against a
peer with the extension not installed.** A check that reports the same verdict either way is
measuring something else — which is not hypothetical, because four of the thirteen checks in the
oracle's own `content` category do exactly that (AP-19). A vacuous check is worse than a missing
one: it occupies the requirement row that would otherwise honestly read `none`.

**These are Kind C and they are never a conformance verdict.** Authored from the spec at the
oracle's own normative target, never from its source; where `validate-peer` has a vector,
`validate-peer` is the measurement; divergence is routed, never carried privately. The standing
condition is the one the operator set for keystone the same day and it is adopted unchanged:
**an official green requires the suite we do not author.**

**The definitions are language-neutral data.** `extension-contracts/<ext>/checks/*.toml` — seven
verbs, seven assertion kinds, one indirection — validated once by the neutral half and emitted as
JSON for the arms. `languages/*/gates/ext-checks/run` is a transport binding that names no
extension, because a wire client is per-language even though the wire is not (`entity_core.peer`
needs `cryptography`, absent from two of the three toolchain images — measured). Adding an
extension adds data; adding a target adds one arm.

**And the second arm corrected the format rather than itself**, which is this repo's pattern
arriving on a new axis: TOML is not parseable in every image, the URI form is per-peer, and an
embedded entity travels in its wire form — the last of which **both** arms got wrong on their
first run, in different languages. A design at n=1 has not been tested.

**Two instrument defects, both on the second arm's first run.** The comparer printed
`EXT-CHECKS: OK` over the one arm that survived while the other died before writing anything —
every word true, the verdict wrong, and the *"no silent caps"* rule was already written in
`gates/README.md` and implemented twice next door (AP-20). And the `typescript` arm answered
all three checks correctly and then never exited, because the peer's client holds a socket with
no exported close: **a hang after the measurement is indistinguishable from a hang before it**,
and only one of them is a real problem (AP-21).

---

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
- ✅ **The host contract** — `docs/KEYSTONE-PEER-HOST-CONTRACT.md` (a pointer), H1–H5 routed and **accepted**,
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

  **`sdk-native` is measured, not forced — corrected 2026-09-09, and the correction is the
  generalisation rather than the value.** This read *"forced, not chosen, and it generalises... most
  of the 26 inherit this."* The rule it rested on — core §6.2's *"user-installed handlers MUST NOT
  register at `system/*` paths"* — has been **withdrawn from the protocol** (0.8.2.13), together
  with the dispatch-path-scoped variant that briefly replaced it. Install authorization at any path
  is now the ordinary capability check on `resource`, and the Appendix says both answers are
  conformant. The two peers we compose against still refuse, each quoting the withdrawn sentence
  back to the caller, so **`sdk-native` is unchanged and no build moves.** What moves is what a new
  extension may assume: nothing. Recorded per peer, `unknown` on 44 of 46, in
  `extension-contracts/content/EXTENSION.toml [substrate.wire_install_refusal]` — and it is
  `unknown` on all of them by execution, because no gate here has ever run a wire register at a
  `system/*` pattern.

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
