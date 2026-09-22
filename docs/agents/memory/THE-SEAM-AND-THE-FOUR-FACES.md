# The seam, and the four faces

<!-- Moved out of AGENTS.md on 2026-09-17 under the 2026-09 doc standard. The text is
     VERBATIM: this was a move, not a rewrite. Superseded, not appended — when one of
     these stops being true, rewrite the entry; git holds the history. -->

**Open this before claiming a peer can host anything** — before writing a `[host]` row, a `[system.faces]` value, a roster column, or the sentence *"this peer supports X"* in a routing packet.

It holds **D13** and **D23**, which are one subject from two directions: what a seam claim has to be checked at, and what an ABSENT face hides.

---

### D13 — a seam claim is checked at four layers, at the packaging boundary, or it reads `unknown`

**Ratified 2026-09-03 on two incidents in different shapes**, both in this repo's own routed output.
**Extended the same day to a fourth layer on a third incident, also ours.**

A claim that a peer *can host* something is a claim about four independent layers, and a claim about
one of them is not a claim about the seam:

| Layer | The question | Cheapest wrong answer |
|---|---|---|
| **Access** | is the symbol reachable **across the packaging boundary** — not the class, the *boundary*? | `cpp` (past `private:`) · **`csharp` (past `internal` on the enclosing class; the boundary is the assembly)** |
| **Read** | does anything **consult** the container on the dispatch path? | **`julia`** (public entry point onto a map nothing reads) |
| **Export** | can a third party **name the body type** it must construct? | `go` (`dispatchCtx`/`outcome` unexported) · `csharp` (`IHandler` internal) |
| **Reach** | does the code **behind** the call site do the work, or route to a stub? | **ours** — `entity_native_dispatch` present in all 46 peers, read as *"model 3 works everywhere"*; it evaluates `compute/literal` and `501`s everything else, **and an installed evaluator is never consulted** |

**The boundary is not always the class.** It is the class in C++, the **assembly** in C#, the module
in Go, the `exports` map in npm, `InternalsVisibleTo` in .NET, `__all__`/convention in Python. Reading
`public` and stopping is the error; four of this ecosystem's control nominations were made that way
and three were wrong.

**And the boundary is not always a packaging boundary.** The Reach layer's failure was inside one
module, at a **dispatch-path** boundary: the symbol was reachable, something did consult it, and the
consultation led to a branch that answers `501`. The first three layers ask *can the call be made*;
Reach asks *does making it accomplish anything*. **A call site is not a capability** — it is the
same sentence as the Read row, one level further down, and stating it in terms of symbols is why the
existing rows did not catch it. Cited: `docs/DESIGN-THE-COMPUTE-TRACK.md` §1, and the finding we
sent the peer generator's team about the evaluator seam.

**And four layers green is still not the property.** The property is *an EXECUTE to the pattern
reaches the installed body*, which only execution settles. **Source reads decide what to build; they
never decide what is true.**

**Enforcement point** — a capability claim in this repo, in any document or routing packet, either:

1. cites **four sites** `(entry, read, export, reach)` each as `(symbol, path, commit)` **and** reads
   `unknown` in every roster/profile column; or
2. cites an **executed probe** (`languages/*/gates/*/probe-*` or the §7d harness) with **both controls** — the
   positive carrying a witness derived from a request field *and* registration-time state, the
   negative going RED. **Where the claim is that an installed thing is consulted, the negative
   control must distinguish "not installed" from "installed and never asked"** — a live-and-directly-
   reachable positive alongside the dispatch attempt, with the invocation counter snapshotted before
   the direct call.

Anything else is written as `unknown`. Grep gate: no row in a `[host]`/roster table in this tree may
read better than `unknown` without a probe citation on the same line.

**A compile-fail arm names each claimed error CODE, never a count** (AP-42). Four-of-four survived one
claim turning false — `E0624` became `E0061` when keystone made the method public — and only a code
per claim, with unclaimed codes refused, can see a change of cause.

#### D13, amended 2026-09-06: a seam claim names a FACE, or it names nothing

**Extended on the third substrate, and it is a change to the shape of the claim rather than a fifth
layer.** The four layers ask *can the call be made* and *does making it accomplish anything*. They
do not ask *which of the extension's four faces you are asking about*, and until `rust` that
question had no answer worth having, because on both prior peers all four faces installed.

On `entity-core-protocol-rust`, one peer, one extension, **measured**:

| face | verdict | evidence |
|---|---|---|
| types (§11.1) | **installed** | `Store::bind` is `pub`; 6 oracle checks moved FAIL → PASS |
| emit consumer (§6.13(c)) | **available** | probe scenario 2, two negatives |
| SDK | library-only | no gated path reaches it |
| handler body (§11.6.1 step 4) | **NOT INSTALLABLE** | `501` with all four tree writes bound; `404` with none; the body 200s when called directly with the counter at 0 |

**So `<peer> is a host` is not a proposition.** `<peer> hosts <face>` is. A roster column, a
`[host]` profile value, or a routed packet that names a peer without naming a face is under-specified
in the same way `public` was under-specified before the Access row — it reads as a verdict and is a
category error.

**Enforcement point** — every capability claim in this tree names the face it is about. The four
names are `types` · `emit_consumer` · `sdk` · `handler` (`docs/DESIGN-THE-SDK-LAYER.md` §1). A
composition declares them in `[system.faces]`, `tools/compose.py` validates the vocabulary, and
**`handler = "not-installable"` drops the dispatch pattern from the resolved plan** — so a wiring
program that would bind a manifest for a body that cannot exist is not merely discouraged, it cannot
be generated. That refusal is load-bearing: binding those four writes moves the peer from
`404 handler_not_found`, which is true, to `501 no_handler_body`, which says a handler exists and is
broken. **Making a peer worse so a report looks more installed is the failure `make regression`
exists to catch**, and doing it on purpose would be worse than tripping it by accident.

#### D13's face amendment, confirmed 2026-09-07 on the second extension — and the sharper case

The amendment was earned on `rust × CONTENT`, where the un-installable handler meant the
extension **did nothing at runtime**. `rust × HISTORY` is the case that shows why the amendment is
about the *subject* rather than about a limit:

| face | verdict | and what it does |
|---|---|---|
| types (§9.2) | **installed** | six oracle checks moved FAIL → PASS |
| emit consumer (§5.1) | **installed AND RUNNING** | records every tree write the peer accepts, measured over the wire, two controls |
| handler (§4.3) | **NOT INSTALLABLE** | the only route by which anything can READ what the consumer wrote |

**One extension's WRITE face installs and its READ face cannot.** The peer accumulates a real,
correct, content-addressed audit chain that no third-party instrument can see, and the oracle's
`history` category scores **7 of 34** against a recorder that is working perfectly.

**So a category score is a statement about the oracle's ACCESS PATH.** On the other two targets
that sentence and *"a statement about the extension"* are the same one, which is why nothing had
forced the distinction. The defence is the pre-registered expectation — the composition predicted
all four numbers and the split before the run and matched exactly — and a new kind of substrate
row, `[substrate.oracle_read_path]`, which records a limit on what can be MEASURED rather than a
limit on the extension. **Recorded, not promoted: one incident**, and we did not make the error, we
predicted against it.

#### D13, and the reason the amendment was not "add a fifth layer"

The four layers held perfectly. Every one of them was answerable on `rust`, and three answered NO —
by `rustc` rather than by a running program, which is the strongest form the Access, Read and Export
rows have ever been measured in (`error[E0603]`, `error[E0609]`, `error[E0624]` ×2). **What was
missing was not a question, it was a subject.** A discipline can be complete in its predicates and
still be silent about what they range over, and that is the failure this amendment fixes.

### D23 — a face reported ABSENT is a face whose contents are UNMEASURED

**Ratified 2026-09-14 on two incidents in two shapes. We predicted against the first and walked
into the second.**

An honest report of an absence reads as an account of the gap. It is not one. *"This peer does not
host face X"* is a true sentence that says **nothing whatever** about whether our implementation of
X is correct — and because the face cannot be installed, nothing can say: no test reaches it, no
oracle check scores it, and the contract's own verdict field reports the absence rather than the
silence behind it.

| | the absence | what it hid | did we notice? |
|---|---|---|---|
| **1** — `rust × HISTORY`, 2026-09-07 | the READ face cannot install, so no instrument can see what the WRITE face records | nothing — the recorder was correct | **predicted**, pre-registered, and it produced `[substrate.oracle_read_path]` |
| **2** — `python × COMPUTE`, 2026-09-14 | no H7 evaluator seam, so `evaluator_face = "not-installable"` | **two defects of ours**: §3.2 E1's scope never pre-populated, §4.1's reads never narrowed under the handler grant | **no.** Nine days, and keystone's seam landing is what exposed them |

**The first incident produced a `[substrate]` row and the explicit note *"recorded, not promoted:
one incident, and we did not make the error, we predicted against it."* This is the second, in a
different shape, and we did make it.** That is the promotion ladder's condition exactly.

**The mechanism is what makes it a discipline rather than a caution.** Both look like a correctly
reported substrate limit and both ARE one; the defect is that the same words also stand in for
*"and therefore everything behind this is unverified."* A measurement of zero and an absence of
measurement are the same value in every artifact we keep. `improved = []` in a blessed baseline is
the sharpest instance: it is a claim that installing the extension moved nothing, and it was blessed
on `python × entity_native` precisely because that was TRUE and was the honest record of a peer with
no seam.

**Enforcement point** — `tools/check-expectation.py`, in `make expectation` and therefore in
`make check`: a `[gate.baseline.<stem>]` whose `improved` is empty **and whose diff has no regression
either** must carry `why_nothing_moved`, naming the absent face and what is consequently unmeasured
rather than known-good. The field is prose, deliberately — nothing here is machine-adjudicable, and
its whole job is that writing it forces the sentence *"and therefore I do not know about X."* Four
planted cases including both directions and a scope control; **driven against the real pre-port
`python × entity_native` reports, where it fires, and goes silent when the field is supplied.**

**Its own scope was set by a control going red.** The first draft fired on any empty `improved`,
which reddened this file's existing AP-23 straddle case — a category with a regression has moved
something, it is simply not an improvement, and demanding the field there puts the rule in front of
a reader already looking at a finding. A false red costs the instrument (AP-4).

**The review question this adds.** Not only *what reads this artifact* (D16) and *which direction*
(D16's sixth), but: **when a report says a thing is absent, what does that absence make
unobservable — and is any of it ours?**

#### D23's third shape: a function with NO CALLER, and the decision split out so it can be measured

**Recorded 2026-09-16 on the CONTENT §3.4 re-anchoring (`W-1`, `rust`). Not a new incident — the
same sentence with a function in place of a face, and the reason it is written here is the
TECHNIQUE, which the first two instances did not need.**

`reassemble_under_capability` is an SDK-face function with **no caller in this tree and no wire
route**: the oracle is a wire client and cannot reach an in-process function. Its `reached_by = []`
was therefore going to stay empty however wrong the wrapper was — and it *was* wrong, on both
clauses of a MUST with a security shape, for as long as the row existed. **The empty list was an
honest record and a cover, which is D23 exactly.**

**The technique, and it generalises past this clause.** Re-anchoring made the function
*less* testable, not more: it now demands the peer's `&HandlerContext`, which a test cannot
construct — and that impossibility **is** the security claim. Left inline, the capability check
would have been a branch nothing could execute in either direction. So the DECISION was split out
as a `pub(crate)` predicate over the five values the context carries, and the two halves are
measured by the two instruments that can reach them:

| half | instrument | why only this one |
|---|---|---|
| the ANCHOR — a consumer cannot build the context | `rustc`, a compile-fail fixture claiming `E0451` | nothing at runtime can assert about code that does not compile |
| the CHECK — the decision is right | unit tests over the extracted predicate, 5 refusals + 1 positive | the wrapper itself is uncallable by construction |

**A security check that has never been observed refusing is not a check.** When a MUST lands
somewhere nothing can call, the question is not *"is it covered"* — it is **"what is the largest
part of this decision I can move somewhere a test can reach, without moving the property?"**

**And the answer is PER PORT, which the same clause showed the same week (2026-09-16, `typescript`
and `python`).** On those two the wrapper needs no split at all: the context is caller-constructible
— which is precisely the clause-1 failure `K-24` is routed about — so the wrapper itself is reachable
through its real entry point and five cases over real contexts and real grant tokens measure the
decision where it lives. **The port that is WEAKER on clause 1 is the port on which clause 2 is
testable end to end**, and the port whose anchor is unforgeable is the one where the decision had to
be extracted to be seen at all. Neither is a choice a port made. So D23's question has one form and
three answers, and a contract column reading *"how is this measured"* would have had to pick one and
be wrong about two — which is D13's face amendment again, one level down: the predicate is right and
the **subject** is per (port × clause).

**And the enforcement point is NOT written, which is stated rather than implied** (D16's own lesson:
an enforcement point you never execute is a wish with a citation attached). The gate would be: a
`[sdk.*]` block with `reached_by = []` carries a `measured_by` naming what does measure it, or says
that nothing does. **Seven blocks across three contracts are in that state today**, and writing the
gate without first establishing all seven honestly would put seven reds in front of a reader on day
one (AP-4). Carried as `W-24`; `content`'s `[sdk.Reassemble]` note is the worked example of what
each one owes.
