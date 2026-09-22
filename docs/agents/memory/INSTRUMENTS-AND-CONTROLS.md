# Instruments, controls and refusals

<!-- Moved out of AGENTS.md on 2026-09-17 under the 2026-09 doc standard. The text is
     VERBATIM: this was a move, not a rewrite. Superseded, not appended — when one of
     these stops being true, rewrite the entry; git holds the history. -->

**Open this before writing or changing any check, gate, probe, resolver or differential in this tree** — and before believing a green one.

It holds **D15** (an instrument is not trusted until it has been seen producing the other answer, and its four sharpenings), **D19** (an instrument does not read a quantity its own execution writes) and **D21** (a differential names its reference, and the reference is checked).

The standing number behind all of it: **nineteen instruments written in this repo, nineteen with a defect — and all but two were found by RUNNING them, not by reading them.**

---

### D15 — an instrument is not trusted until it has been seen producing the other answer

**Ratified 2026-09-05 on five incidents in one session, in two mechanisms and four shapes, every one
of them ours and every one found by *running* the instrument rather than reading it.** Evidence:
`docs/ANTI-PATTERNS.md` **AP-3** (a chunker test whose *corpus* was the defect — an LCG whose low
bits never satisfied the boundary mask, so FastCDC degenerated to fixed-size and the test could not
have passed; an export-surface check whose literal deep-import specifier made `tsc` kill the build
before the assertion ran; an arms diff that parsed zero checks and would have printed *"no
regressions"*) and **AP-4** (a staleness gate comparing against a *directory's* mtime, red-flagging a
`dist/` ten minutes newer than its `src/`; a single-round A/B diff attributing a flaky check to the
composition on a **one-millisecond** difference across a 50 ms floor).

D13 already requires **both controls** on a *capability probe*. D15 is the same demand generalised to
every instrument in this tree — test, gate, linter, resolver, diff — on the evidence that the
instruments failed five times in one session and **three of the five reported green**.

**The two directions fail differently, and the second is the expensive one.**

| | Mechanism | How it presents | Why review misses it |
|---|---|---|---|
| **False green** | the check cannot reach its assertion, or its input cannot exercise the branch | *passing*, or *the build broke for an unrelated reason* | a defective instrument does not report itself |
| **False red** | the comparison is against the wrong quantity, or the quantity is noisy | *a defect*, plausibly located | the finding looks like work; and the natural next edit is `\|\| true` |

A false green costs one missed defect. **A false red costs the instrument**: the next person's
locally-reasonable fix is to suppress it, and then it gates nothing forever.

**Enforcement point** — every check, gate, probe or resolver added or changed in this tree carries,
at the point it is added, one of:

1. **an executed negative control** — the same instrument run in the state that should produce the
   opposite verdict, and observed producing it; **or**
2. **a corpus assertion, which names the PROPERTY the input must have, not a COUNT of units**
   (sharpened 2026-09-09, AP-28 — see below) — the input is checked to exercise the branch under
   test, not merely to be well-formed (an LCG stream with 256 distinct values and no short period
   is well-formed and exercises nothing); **or**
3. **an inline note naming the exact condition that would flip the verdict**, and why that condition
   cannot be constructed here.

And two specific consequences, both paid for:

- **A parse that yields zero units REFUSES.** An empty result set is never reported as a clean
  verdict. (`tools/diff-arms.py` is the model; its own guard caught its own defect on run one.)
- **A difference between two arms is attributed only when it is stable across rounds.** Anything that
  moves within an arm is FLAKY and belongs to neither. `make regression` defaults to `ROUNDS=2`.

Grep gate: a file under `gates/`, `tools/` or `**/test/` that asserts a verdict without a negative
control, a corpus assertion, or a named flip-condition in the same file is a defect.

#### D15, sharpened 2026-09-06: every instrument ships a REFUSAL, not only a control

**Ratified on a rate rather than on an incident, and the rate is the argument. Five
instruments written in this repo, five with a defect found by RUNNING them and none by
reading them:**

| instrument | the defect | which direction it moved the answer |
|---|---|---|
| `tools/diff-arms.py` | written against a nested report shape; the real one is flat | **clean diff** over zero checks |
| `languages/python/gates/host-seam/probe-seam.py` | matched the frame budget by attribute *name*, not by value | **green on cue**, and could not have gone red |
| `languages/rust/*` | `${CARGO_HOME:-…}` lost to the image's own `ENV` (AP-6) | a misleading error about a missing crate |
| `tools/sdk-parity.py` | **two**: `Blob`/`BLOB` collapsed to one key (AP-8); `__all__` parsed out of the docstring | **agreement across three ports** that was not there |
| `gates/chunking-parity/` | reached for `.hash` where `typescript` has `.contentHash` | would have hexed `undefined` to `""` on all three arms |

**Three of the five would have reported a green or agreeing result, and two of those three
would have reported agreement across three ports** — the most convincing wrong answer
available, and the one nothing downstream re-derives.

**The two that caught themselves are the two that shipped with a refusal.** `diff-arms.py`
refuses a diff over zero parsed checks; `compare.py` refuses a parity verdict below
`--min-ports`. Neither is a control — a control proves the instrument *can* go red on a
planted defect. A refusal fires when the instrument **cannot answer at all**, which is a
different failure and the one that presents as success.

**Enforcement point** — every instrument added to this tree carries, in addition to D15's
control/corpus-assertion/flip-condition, an explicit refusal on its own **vacuity**: a parse
that yields zero units, a comparison with fewer arms than the verdict needs, a missing input
it would otherwise silently skip. It says `REFUSING` and exits non-zero. An instrument that
can only report PASS or FAIL has no way to say *"I did not measure anything"*, and that is
the state it will actually be in the day it breaks.

**Instrument seven broke the run, and the exception is more useful than the streak.**
`tools/check-error-codes.py` (2026-09-06) also shipped with a defect — a line-based extractor
that would have missed **exactly the two codes the gate exists for**, `capability_denied` and
`path_required`, on all three ports, because the emits long enough to wrap are the interesting
ones. **It was caught in review, before the first run**, which is the first time in seven that
has happened here.

Two things follow, and the second is the one worth keeping:

- **The rate is not a law, it is a warning about a habit.** Seven instruments, seven defects;
  six found by running. Review can catch these — it just has not been what caught them.
  **Still holding at seventeen (2026-09-07).** `tools/check-expectation.py`'s was small and
  exactly in the family: a composition whose every stem had REFUSED printed
  `not measured (no reports on disk)` — a line that reads like a measurement over a state
  that produced none. AP-19's shape in an instrument's own output.
  **NINETEEN NOW (2026-09-10), and instrument nineteen is the one where a REFUSAL caught the
  defect the control could not.** `tools/check-spec-lists.py` shipped two: its own
  `--self-test` corpus writer emitted a TOML file with unquoted keys (`fake/value = "…"` is a
  parse error, and the control's whole corpus is type names), and its `member_pattern` reached
  the regex engine as `\s` doubled — a pattern matching nothing. **The second is the
  interesting one: a pattern that matches nothing makes the list parse to ZERO members, which
  the instrument's own vacuity refusal reports as `REFUSING` rather than as a clean verdict
  over an empty enumeration.** D15's sharpened clause — *every instrument ships a refusal, not
  only a control* — caught the author on run one. A third defect was caught by a DIFFERENT
  gate: `make toolchain` flagged a lazy `import copy` inside the self-test, which is the second
  of its two doors doing its job on a file written the same hour.
- **The instrument's own corpus assertion would NOT have caught it, and that is the finding.**
  `MIN_SITES` still saw 6 / 11 / 5 emit sites, all above its floor of 4. **A corpus assertion
  bounds a pattern that STOPS matching; it does nothing about one that matches the boring
  half.** That is a real gap in D15's clause 2 as written, recorded rather than patched: a
  second instance in a different shape promotes it to *"a corpus assertion names the property
  the input must have, not a count of units"*. One incident is not two.

**IT IS TWO NOW, AND CLAUSE 2 IS SHARPENED ABOVE `[2026-09-09, AP-28]`.** The second instance
is `tools/req-coverage.py` at the `HISTORY` v1.10 re-pin: `LEVELS` was written before
`SPECIFICATION-FORMAT` §8.5a existed and omitted the two NEGATIVE levels, so §9.1's sixteen rows
parsed and then `if level not in LEVELS: continue` **threw away `HIST-R8`** — the `MUST NOT`
recursion guard, the one row in that inventory this repo authored its own wire check for. The
tally printed fifteen, was internally consistent, and reported no gap. **A missing prohibition
reads as "the spec forbids nothing here"**, which is indistinguishable from a spec that does not.

**Different mechanism, same outcome, which is why it promotes rather than repeats.** `MIN_SITES`
was a regex that under-matched under a floor too low to notice; this was a *complete* parse with
a filter applied afterwards. A count cannot see either. **The property could:** §8.5a allocates
`<PREFIX>-R<n>` once, never renumbered, contiguous from 1 — so a hole in the parsed sequence
means the parser dropped a row, full stop. `assert_contiguous_ids` asserts that and nothing else;
it arrives with the data and needs no second place to update at a re-pin. The longer `LEVELS`
tuple fixes today, and the next value arch adds would be dropped exactly the same way — **which
is the whole difference between fixing an instance and naming the property.**

**A FOURTH SHAPE, 2026-09-12 (AP-38), and it is the clause-2 gap arriving at a REFUSAL rather than
at a corpus assertion.** `languages/python/gates/sdk-surface/extract.py` matched `__all__` with a
non-greedy `(.*?)\]`, so a `]` inside an explanatory comment truncated the list and the extractor
returned **3 names of 75**. `emit.py` carries the vacuity refusal this repo's sharpened clause
demands — *a parse that yields zero units REFUSES* — and it has fired for real, on this same
extractor, in an earlier defect. **Three is not zero.**

So the gap generalises past clause 2's wording: **a floor catches a pattern that STOPS matching
and misses one that matches the wrong part, and that is as true of a refusal threshold as it is of
`MIN_SITES`.** The direction was the expensive one for a parity gate — an under-reported surface
reads as DRIFT, so the run would have fabricated seventy-five divergences — and the sibling arm had
already been fixed for the identical cause six days earlier, which is AP-10's shape on a gate arm.
The fix is the property again: a balanced scan that tracks quote state and bracket depth, because
*find the matching bracket* is what the parse means and the next `]` will be inside a string.
Verified name-for-name across all three cells before the arms were trusted.

#### D15, sharpened 2026-09-10: the control is the ABSENCE OF THE SUBJECT, and a control that stays GREEN is a finding

**Clause 1 said *"the same instrument run in the state that should produce the opposite
verdict"* and did not say what makes that state.** Two incidents in two shapes say it is
the absence of the SUBJECT, not merely a different input — and that when the control
stays green, the instrument is fine and the PROPERTY belongs to someone else.

| | the assertion | what actually satisfied it |
|---|---|---|
| **AP-19** | four `content` oracle checks | the BARE peer — they pass with the extension not installed |
| **AP-33** | COMPUTE §7.2's convergence check: *"no tree write occurs"* | `EntityTree.put`'s own `changed` guard and `ContentStore.put`'s `has` guard — the clause is REDUNDANT on this peer, and the test passed with our implementation of it **deleted** |

**Neither is D19 and neither is a defect in the instrument.** D19 is *an instrument does
not read a quantity its own execution writes* — there the reading is perturbed. Here the
reading is correct and something **underneath the subject** produces it. One is another
team's check in a differential; one is our own unit test against a peer primitive.

**Enforcement point** — the control an instrument ships is run against the tree with the
**code under test removed**, not with a different input, and the removal is recorded
beside the assertion. When the verdict does not move:

1. **Do not delete the assertion.** The layer that owns the property today is not the
   layer the spec addresses — §7.2 pins no delivery mode (§9.4 leaves it impl-defined),
   so a peer whose `put` emits unconditionally cascades forever on a converged subgraph.
2. **Add one that only the subject can satisfy** — for AP-33 that is `#reEvaluate`'s own
   return value, `null` on convergence, which nothing in the substrate can produce on our
   behalf. That is the assertion the planted defect reddens.
3. **Record which layer owns it**, as a `[substrate]` row. *"Our clause is redundant
   here"* is a fact about the peer, and it is exactly the kind that stops being true at
   the next port.

**The question to ask of any green control:** not *"is the instrument broken"* — it
usually is not — but **"what else in this stack could make this assertion pass, and is it
the thing the spec is addressing?"**

#### D15's controls assert on the VERDICT; nothing asserted on the REMEDY the verdict ships with

**Recorded 2026-09-16 on one incident (AP-48), caught before it shipped, and the enforcement point
is cheap enough that it is added rather than deferred.**

`req-coverage.py`'s new §5b split was correct in every arm — `RE-PINNED (not lost)` when the corpus
still carries a vanished pin's obligation, `MEASUREMENT LOST` when nothing does, both observed on
the real corpus with the real event planted. **The defect was the paragraph under the correct
verdict:** every `RE-PINNED` failure closed with *"the measurement did not go away; the NAME did"*,
which is true for an obligation with one carrier and **unsupportable for one with 222** — and the
spread caveat was printed *above* it, so the sentence a reader acts on was the one the join could
not justify.

**No control could have caught it, and that is the finding rather than the fix.** D15 clause 1
asks for the instrument observed producing the opposite verdict; the verdicts were right, so every
control was green and stayed green. An instrument's output is **prose plus a verdict, and only the
verdict is ever asserted on** — while the prose is the part that edits the tree. A correct verdict
with a misdirecting remedy is worse than a false red: a false red gets argued with, and a **remedy
gets followed**.

This is AP-47's question moved one file over — *a tool's prose is an undeclared assertion* — from
the docstring an implementer reads to **the message a reader acts on**, which is executed every run
and asserted on by nothing.

**Enforcement point** — where a gate's failure message tells the reader what to fix, the control
asserts on **that sentence**, in both directions. In `req-coverage.py --self-test` the wide arm
asserts the reassurance is ABSENT (`not failed(r, "the NAME did")`) and the narrow arm asserts it is
present; the caveat gets the same treatment. **The negative is the load-bearing half**: a caveat
that fires on every rename is not information, and a reassurance that fires on every rename is a
defect.

### D19 — an instrument does not read a quantity its own execution writes

**Ratified 2026-09-07 on two incidents in two shapes, both ours, both found by running the
instrument.** The first was already written down as a bullet in `gates/README.md` rather than as a
discipline; the second is what showed it generalises past the thing it was written about.

| # | the quantity | what wrote it | how it presented |
|---|---|---|---|
| 1 | an **invocation counter** — evidence that an installed body was consulted | the probe's own *direct call* to that body, made as a control | the delegation appeared to work. `probe-entity-native.mjs` |
| 2 | a stage's **newest-file mtime** — evidence that the artifact under test is current | the arm's own `cp` of its probe *into that stage* | `gates/type-parity`'s typescript arm passed a staleness check over a **six-hour-old** stage on its first run |

**Different quantities, different mechanisms — a method call and a file write — and the same
sentence.** The instrument perturbs the thing it is reading, and because the perturbation always
moves the reading in the *reassuring* direction, nothing downstream re-derives it. Neither is
caught by a control: a control proves the instrument can go red on a planted defect, and both of
these went green on a real one.

**And it is not fixed by a smarter check.** #2's honest fix is a *reserved name*: an arm that must
run from inside the stage genuinely has no alternative (ESM resolves a bare specifier relative to
the importing file), so the write is legitimate and what has to change is that the reader can tell
it apart. `gate-probe-*` is that name.

**Enforcement point** — anything a gate writes into a stage is named `gate-probe-*`.
`tools/gate-stage` excludes the prefix from its staleness scan; `tools/check-structure.py` fails any
file under `languages/*/gates/**` that writes a non-`gate-probe-*` destination into `"$STAGE/"`, and
ships an executed negative control. **On its first run it found a second, pre-existing instance** —
`chunking-parity`'s typescript arm, which had been leaving `parity-probe.mjs` in every stage since
2026-09-06. That arm has no staleness check today, so the bug was latent rather than active; adding
one would have activated it silently, which is the whole argument for gating the write rather than
the read.

**The generalisation, for anything added to this tree:** before trusting a number, ask what wrote
it. If the answer includes *"this instrument, a moment ago"*, the number is not evidence.

### D21 — a differential names its reference, and the reference is CHECKED

**Ratified 2026-09-07 on three incidents in three shapes, all ours, all in one session, and
all found by *running* an instrument rather than reading one.** Evidence:
`docs/ANTI-PATTERNS.md` **AP-18** (the baseline is in the arm and never in time), **AP-22**
(a round set that is not one run), **AP-23** (a verdict decided by a threshold the two arms
straddle).

This repo's two most load-bearing gates are differentials — `make conformance` and
`make regression`, bare peer versus composed peer, one variable. A differential is only ever
as good as **what it is measured against**, and the reference had never been checked. All
three incidents are that one sentence, in three places:

| | the reference | how it failed | how it presented |
|---|---|---|---|
| **AP-18** | the OTHER ARM | it is the wrong AXIS. An improvement lost is `bare FAIL vs composed FAIL` — no difference | a smaller improvement count, in a column nobody asserts on |
| **AP-22** | round *r* of this run | the file was **from a different run**; a slot is not a fact about which execution filled it | `FLAKY: 1` — the noise rule ate the signal |
| **AP-23** | the other arm, again | the difference is REAL, STABLE and **not attributable** — bias, not noise | `REGRESSION`, the strongest verdict the gate has, for a 3 ms cost against a 50 ms floor |

**The three fail in the same direction and it is the expensive one.** AP-18 and AP-22
present as *reassuring* — a smaller number, a check filed as nobody's — and nothing
downstream re-derives either. AP-23 presents as a **false red**, and the locally-reasonable
response to a gate that reports a regression nobody can fix is to stop believing it
(AP-4). One class of bug, two ways to lose the instrument.

**And ROUNDS is not the answer to any of them.** The rounds rule was earned on AP-4 and it
is a good rule; it separates a verdict that MOVES from one that HOLDS, which is **noise**.
AP-22 is contamination — a stale file looks exactly like a round that disagreed, so more
rounds make it more convincing. AP-23 is **bias** — stable in every round, in the same
direction, for a real reason, so more rounds change nothing. *"Run it twice"* answers one
of the three questions a differential has to answer.

**Enforcement point** — three, one per shape, and each ships an executed control:

1. **A reference in TIME.** `[gate.baseline.<stem>]` in every composition's `SYSTEM.toml`,
   checked by `tools/check-expectation.py` in `make check`. It declares `improved` as a set
   of **NAMES**, never a count (D14: a count that shrinks by one understates a capability,
   and nothing re-checks in that direction). An undeclared stem is a failure; a lost
   improvement is a failure; an undeclared *gain* is a failure, because a gain nobody wrote
   down is a baseline nobody re-read.
   **And the baseline is NOT the pre-registration.** `[gate.expectation]` is written before
   the run and kept wrong on purpose; asserting against it would go permanently red on a
   preserved miss, and the locally-reasonable fix for that is to edit the prediction —
   which destroys the artifact. Two quantities were living in one block.
2. **A reference that is ONE RUN.** `make conformance` / `make regression` `rm -f` their own
   round set before writing it, and `tools/diff-arms.py` refuses when an arm's report
   timestamps **decrease** in round order. Threshold-free, so it is not a false-red source.
3. **A class for a difference that cannot be ATTRIBUTED.** `[[gate.straddle]]`, per check,
   consumed by `diff-arms.py` and `check-expectation.py` through the same function. It must
   name where the finding was routed — `make citations` then forces that path to resolve
   (D18) — both arms' full evidence prints on every run, and `--strict-straddle` promotes
   them all back to regressions. **A declaration with no destination is a suppression**, and
   the schema refuses one.

**The question to ask of any differential in this tree**: not *is the comparison right*, but
**what is it measured against, what could contaminate that, and what would it say if the
answer were "I cannot tell"**.
