# Gates, and what reads them

<!-- Moved out of AGENTS.md on 2026-09-17 under the 2026-09 doc standard. The text is
     VERBATIM: this was a move, not a rewrite. Superseded, not appended — when one of
     these stops being true, rewrite the entry; git holds the history. -->

**Open this when adding any new KIND of artifact to this tree** — a declaration block, a config file, a manifest, a per-target profile field — and when adding a second implementation of anything.

It holds **D16**, the longest-running thread in this repo (ten instances, each one a different answer to *what reads this artifact*), and **D24**, which is about a gate reading state an earlier run left behind.

The three questions D16 has produced, in order of how cheap they are to ask: **what reads this artifact · which direction does it read in · what does the gate itself read, and would that be read if the gate could not run today.**

---

### D16 — an axis with no upstream authority gets its gate at the SECOND implementation

**Ratified 2026-09-06 on one incident, and it is ratified rather than held as a candidate
because the incident is a rule we had already written down and then did not apply.**

`gates/README.md` opens with a rule inherited from keystone: *of their four verification
axes, the only one with no external authority — 17 of 18 hand-written assertions with no
oracle behind them — is the only one whose checks went stale.* We wrote that, named
`isolation` as the axis most at risk, and then shipped **three ports** of an extension whose
SDK surface had no gate at all.

It cost 18 undeclared differences across those three ports (`tools/sdk-parity.py`, first run:
`24 required · 9 substrate · 18 drift · 51 union`). Almost all of it is one decision made
once in `typescript` and never made again — the type-name constants bundled into an object
in one port and exported flat in the other two. **No existing instrument could have caught
it**: each port passes its own suite, the oracle is a wire client that never sees an
in-process surface, and the host-seam probes measure the peer rather than us.

**Why the charter did not protect us.** `DESIGN-THE-SDK-LAYER.md` §1.1a says the SDK face is
ungated by design and *the extension is the instrument*. That is true about **conformance**
and we let it stand in for **consistency**. The handler's gated path does run through the SDK
face; that says nothing about whether three ports expose the same names.

**And it is not "arch should have specified it".** Arch enforces what has to be enforced;
conformance lives on the wire, and a cross-impl surface oracle would enforce the thing
`GUIDE-EXTENSION-DEVELOPMENT` explicitly disclaims. **Where arch declines to standardise, the
standard is ours to set** — the same position we were in with the peer host contract. If it
survives a second extension, that is two incidents in two shapes and it goes upstream as a
proposal with the gate's output as evidence. Promoting it on one extension's data would be
L18 in a new costume.

**D16's second instance, found the day after it was ratified, and it is the same lateness.**
The *structure* is an axis with no upstream authority — nothing outside this repo has this
layout, so nothing outside it can check that a per-target subtree holds only units the root
declares. It got its gate at the **third** target (`tools/check-structure.py`, 2026-09-06),
which by D16's own rule is one target late. And the file the whole layout now rests on —
`languages/<target>/profile.toml` — was **parsed by nothing at all** for three ports while
declaring the toolchain image, the packaging boundary and the `[extension_host]` block, with
every one of those facts silently restated wherever it actually executed (AP-9). Two axes,
same shape: *the thing we own is the thing nothing watches.* **When a new kind of artifact
appears in this tree, the question is not whether it works — it is what reads it.**

**Enforcement point** — an extension with more than one language cell declares
`[sdk_surface]` in its `EXTENSION.toml` (`required` · `substrate` · `drift`), and
`make check` runs `./tools/sdk-parity.py`. **An undeclared public name is a failure**, because
the failure mode is a name arriving without anyone deciding. `drift` is a named,
dated list of undecided differences and **not a blessing**: `--strict-drift` turns every entry
into an error, and the flag is the switch that gets flipped once they are resolved so the
class cannot quietly refill. A second cell added to any extension without an `[sdk_surface]`
block fails the gate on its first run.

**D16's third instance, and it is the one that had CAMOUFLAGE rather than lateness.** The
`system/content` handler's **error-code surface**: seven distinct codes on the wire across
three ports, and **two of them asserted by anything anywhere** — `entity-core-go`'s `content`
category checks `get_path_required` and `ingest_path_required` and nothing else about a code.
The other two axes were *visibly* unowned; this one was not. A category named `content`, 13
checks deep, reads like it measures the content handler, and reaching for a code no oracle
looks at feels covered.

It cost the CONTENT v3.6 → v3.7 re-pin. §6.4's `403 forbidden` became `403 capability_denied` —
`forbidden` was `ENTITY-CORE-PROTOCOL` §3.3's *fallback* for the status and a code in no code
set — and **all three ports carried the dead spelling with nothing in this tree or upstream
able to say so** (AP-11). Enforcement point: `tools/check-error-codes.py`, in `make check` —
every code a port emits is declared in `[error_surface]` with the authority that defines it
(`spec` · `core` · `unresolved`), an undeclared code is a failure, and `--strict` promotes the
`unresolved` class. Its first run found **`path_required`**: MUST-ed twice by CONTENT §6.2/§6.3,
asserted by two live oracle checks, and defined in **neither** code set the handler may draw on
(`grep -c path_required specs/ENTITY-CORE-PROTOCOL.md` → `0`; absent from v3.7's Appendix A,
which declares itself closed). Raised with the specification authority; **not resolved locally**,
because two readings of core §3.3 are in the corpus at once and picking one is arch's call.

**Three instances, one sentence: the thing we own is the thing nothing watches — and an axis
that has *some* upstream coverage is more dangerous than one with none**, because the coverage
is what stops anyone asking. The question to ask of a new artifact is never *does it work*; it
is **what reads it, and what would it say if this were wrong**.

**D16's fourth instance, 2026-09-07, and it is the corollary taken to its limit: the axis with
the MOST upstream coverage.** Our conformance axis is `validate-peer`, and it is the oracle
because it is not the thing under test — settled, unchanged. What nobody had asked, because 34
checks citing `HISTORY §x.y` read exactly like coverage of EXTENSION-HISTORY, is **how many of
the spec's own §9.1 rows those 34 checks reach.** `tools/req-coverage.py` joins the spec's
conformance inventory to the oracle's executed check set through a mapping we now declare:
**38 rows, 24 binding — 0 fully oracle-measured, 11 partial, 2 ours, 11 nothing.**

Two things make this D16 rather than a new number. The mechanism is identical — a real
instrument's presence is what stops the coverage question being asked — and the fix is
identical: a declaration block in `EXTENSION.toml` where an undeclared row is a failure, exactly
as `[sdk_surface]` and `[error_surface]` are. **And the tally has a fourth column, `partial`,
because the failure this axis actually has is not absence.** A row with an oracle check *and* a
declared `gap` is never counted covered: *"a check is named after this requirement"* and *"this
requirement is measured"* are two sentences, and four `content` checks pass in the **bare arm**
— against a peer with the extension not installed — which is that error caught by execution
(AP-19).

**Do not read the number as a score.** Several rows have no wire form at all, and both specs
carry the *"stored in the content store, not the entity tree"* clause with the identical
absence. **The map's product is an assignment of work between three seats, not a verdict on
anyone's suite** — which rows a wire oracle could reach and does not (core-go's), which need a
different instrument (ours), and which are MAY and need none.

**Enforcement point** — `[conformance]` in every `EXTENSION.toml`: the spec's conformance
section by shape and digest, and every requirement row declared with `oracle` / `ours` / `gap` /
`note`. `tools/req-coverage.py` in `make check`; **an undeclared or a stale row is a failure**,
so a re-pin cannot add or re-word a requirement unnoticed. Its first real run failed on a §11.4
row dropped while transcribing a 28-row inventory by hand. 15 controls, all driving the gate
function rather than a copy of it; two vacuity refusals; the executed corpus and its digest are
printed before any verdict, and that line is the scope of every negative claim it makes.

**D16's fifth and sixth, and they are one sentence with two subjects: a gate asks its question in
ONE direction until something makes it ask the other.**

- **Fifth (2026-09-08, the HISTORY v1.8 re-pin).** `tools/check-error-codes.py` walked every
  **emit site** and asked whether that code was declared. A code the SPEC names and **no port
  emits** was outside its corpus entirely — so Appendix A's `403 access_denied`, in §4.2/§4.3.2
  pseudocode since v1.7, was an undeclared deviation in all three ports through the whole CONTENT
  re-pin that earned the gate. The gate now checks both directions and shipped a false red on the
  first run of the new half (`internal_predicate_on_wire`, the entry whose whole content is *"these
  are not wire codes"*); the fixed rule then found two more in CONTENT, both genuinely unreachable
  and both now declared with reasons. Not fixed by switching three ports: two landed specs spell
  one path's 403 two ways, and that is arch's call (routed).
- **Sixth (2026-09-08, authoring H-R13's checks).** The **type names our own authored checks put
  on the wire.** `history/local_namespace_excluded` had been sending `system/tree/put-params`,
  which no registry defines, carrying a `path` field the real type does not have — and **nothing
  anywhere could say so**, because no peer validates a params entity's type against §9.5 (§6.3
  structural admission never checks `data` against the type it names). The wrong name behaves
  identically to the right one: both arms pass and the check reads as evidence. Enforcement point:
  `[check.types]` in every check definition, one entry per wire type, each naming an authority
  (`core` · `spec` · `ours` · `unresolved`) and citing the document; `gates/ext-checks/schema.py`
  refuses an undeclared type **and** a declaration no step sends. Four planted defects in
  `--self-test`, in `make ext-checks-control`. AP-24.

**The question to ask of any gate in this tree, alongside D16's other one:** not only *what reads
this artifact*, but **which direction does it read in, and what lives in the direction it does
not**.

**D16's seventh, 2026-09-09, and it is the arc's end point: the axis with a landed standard, a
live instrument, and full coverage — in a tree we never run.** Our **outbox**. `AGENTS-STANDARD.md`
§*Routing packets* pins the shape of a routing packet and names its enforcement point: arch's
`spec inbound`. Both existed. Neither had ever been pointed at us.

Measured, one variable, same tool state, `scanned 410` in both arms:

| | owed | unaddressed |
|---|---|---|
| before | 2 | **11** |
| after | 3 | **0** |

**Eleven of our twenty-two packets could not be routed mechanically** — filed as UNKNOWN, which
is never *"not theirs"*. Every one named its recipient in its own H1, so a human reading the
directory found them, and two were in fact found that way. **There is no reading of the sending
tree that reveals this**; only the receiving tree's instrument can, and it is the one instrument
a sender never runs.

**`owed` going UP from 2 to 3 is the gate working, not a regression.**
One of our findings about the evaluator seam names a second project as a co-recipient, and that
project has no ledger row for it; it had been sitting in the UNKNOWN bucket. **A number that gets worse when a defect is fixed
is the number that was lying** — D14's asymmetry again, and again in the understating direction.

The first six instances were *nothing watches this*. This one is *something watches this, in
somebody else's tree*, which is worse in exactly D16's established way: the coverage is what
stops anyone asking. **An enforcement point you never execute is a wish with a citation
attached.** Enforcement point: `tools/check-routing.py`, `make routing`, in `make check` — four
FAIL rules (block shape · fields · filename-agrees-with-field · id uniqueness), a citation-form
census that is counted and not failed, four planted defects in `--self-test`, and two vacuity
refusals. AP-30.

**Its own first draft shipped the defect too** — a non-greedy group split `core-go` into `core`
and put five false reds in front of a reader on run one. Instrument eighteen, and the streak
holds: found by running it, not by reading it. The fix is the D15 shape — R3 asks the `To:` field
what tokens name it, instead of keeping a second copy of the naming convention.

**And the same day, arch inverted what has to be complete.** Their
`SEAT-CLEANUP-INSTRUCTIONS-2026-09-09` asks every seat for **one tracker per counterpart** at
`docs/status/TRACKER-<counterpart-repo>.md`, and states the consequence plainly: **arch reconciles
against the tracker, not against the directory.** That is a bigger change than a file format. A
packet missing from a tracker is now invisible in a way a packet sitting in `docs/status/` never
was — the directory at least had an `ls`. So the completeness obligation moved off the filesystem
and onto a document somebody has to remember to edit, which is the most reliable thing in this
ecosystem to forget.

Four trackers here, one per project we have something open with — the specification authority,
the peer generator, the owner of the conformance oracle, and the project that maintains the
shared working conventions. **T1–T4 in `tools/check-routing.py` hold them**: a tracker exists for every
repo any packet names, the four sections are present, ask ids are unique, and — **T3, the one that
matters** — every packet is cited in the tracker of every repo it is addressed to. **T3 failed on
its first run against our own four trackers**, because they cited packets by `ROUTING-<date>-<recipient>-*`
shorthand rather than by full stem, which is the very rule arch's item 3 pins. Written and gated
in the same hour, and the gate caught the author.

**Two rules from arch's document that are not ours to soften.** *"Filed, nothing owed back"* is a
real section and most documents belong in it — treating a for-information review as an open ask is
what put a 44 on their board where the truth was eleven. And **archived is not delivered**: a row
closes on the recipient's receipt, never on our own completion. Our record for the project that
owns the conformance oracle has an empty Closed section for exactly that reason, and it should
stay empty until they reply.

**D16's eighth, 2026-09-10, and the unread artifact is THE PINNED SPEC SNAPSHOT — the thing every
gate in this tree cites and no gate opened.** Four declared deviations in `EXTENSION-COMPUTE`, one
cause: an amendment reached the prose and the conformance corpus without reaching a **list**
somewhere else in the same document. **Three of the four are a set-membership disagreement between
two places in one spec**, which is mechanically checkable, and nothing checked it — not the spec's
own gates, not the corpus (`entity-core-go` already carries the corrected form in every case, so
no vector *can* fail on it), and not us: all four were found by transcribing and then running.

`req-coverage.py` parses §10's bullets. That was the whole of this tree's spec-reading, and it is
why the question *"do the spec's own enumerations agree with each other"* had never been asked
about a file we re-pin, digest and cite in seventeen places.

**Enforcement point** — `[[spec_lists]]` in `EXTENSION.toml` declares each enumeration by section,
anchor and exact membership plus what our port carries and why they differ;
`tools/check-spec-lists.py`, `make spec-lists`, in `make check` re-parses each one out of the
snapshot and requires the parse to EQUAL the declaration. Four FAIL rules (membership · every
defined type listed or excused · an undeclared port-vs-spec difference · a member the spec defines
nowhere), four planted defects in `--self-test` plus a clean arm, four vacuity refusals.
**Compare-to-declaration, never list-to-list**: `is_compute_expression` *should* be shorter than
`is_compute_type`, so a gate diffing the spec against itself would put correct-by-design
differences in front of a reader on day one, and a false red costs the instrument (AP-4). The gate
holds no opinion about the spec; the **declaration** carries our reading and the gate holds the
declaration to the bytes — so a re-pin that moves a member fails instead of silently invalidating
a transcription.

**Its first run strengthened a finding already routed, which is the argument for having built
it.** A-10 was filed as *"§4.2's and §4.7's predicates omit `compute/index`, `compute/length` and
`compute/numeric-cast`"* — two sites, a RESOLUTION failure. The parse says **§4.1's
`evaluate_inner` arm ladder has thirteen arms and omits the same three**, which is an EVALUATION
failure: three types §10.1 MUSTs by name, absent from the switch that runs them. Three sites, one
amendment, and the third is the one nobody had counted. **An instrument that finds something the
day it is written is the kind worth keeping** — D14 said that about its own gate, and it holds
twice now.

**And the honest limit, declared rather than quiet.** `spec_lists_none` exists because CONTENT and
HISTORY enumerate nothing — neither is an interpreter — and firing R2 on all sixteen of their
types would be a false red per type. But *declare no lists and the gate goes quiet* is a
false-green door, so the exemption is **not automatic**: the contract must carry the reason and
the grep that establishes it, and an omission fails.

**D16's NINTH, 2026-09-12, and it turns the arc inward: the unread artifact is A GATE'S OWN
CONFIGURATION.** The first six were *nothing watches this*; the seventh was *something watches
this, in a tree we never run*; the eighth was *the spec snapshot every gate cites and none opens*.
This one is two instances of one shape found in one hour, both on the second COMPUTE port's first
gate run, and in both the unwatched artifact belongs to a gate that was otherwise working.

- **A DECLARATION WRITTEN FOR A GATE THAT CANNOT RUN YET IS PARSED BY NOTHING** (AP-37).
  `extension-contracts/compute/EXTENSION.toml [sdk_surface]` was authored at port ONE, deliberately,
  citing D16 by name — *"written NOW rather than at the second port precisely because that is
  D16"*. The intent was right and `tools/sdk-parity.py` refuses below two ports, so the block was
  authored, reviewed, cited in a handoff and **never once read**. It was in the wrong FORM
  throughout — 67 raw identifiers where the key is `kind:snake_case` — and the second port's first
  run died with `IndexError`, which is neither a verdict nor a refusal. **The crash was the lucky
  outcome**: without it, all 67 would have read as `missing from python, typescript`, and
  sixty-seven false reds is how a gate stops being believed (AP-4). *A gate whose refusal
  threshold is N leaves every declaration below N unread*, so authoring early buys documentation
  and not enforcement.
- **A GATE WITH THREE AXES CAN BE DATA IN TWO OF THEM AND A LITERAL IN THE THIRD** (AP-39).
  `gates/type-parity`'s extension axis is a wildcard *"so a new contract directory joins the
  cohort without a Makefile edit"*; its three arms each opened
  `COMPOSITION="${COMPOSITION:-content-history}"`. From the day COMPUTE's contract landed the gate
  could not measure it on any target — that stage holds `extension-content` and
  `extension-history` and nothing else — and it said so honestly (`UNKNOWN`, exit 3) for three
  days while sitting inside `make check`. **The newest extension's type layer went unmeasured by
  the one instrument built to compare it across ports, at the exact moment a second port made the
  comparison possible.**

**The question this adds to D16's other two.** Alongside *what reads this artifact* and *which
direction does it read in*: **what does the gate itself read, and would that be read if the gate
could not run today?** Enforcement points: `_declared_key()` in `tools/sdk-parity.py` refuses a
malformed declaration by name (observed firing on the real defect and not firing on the two
correct contracts); `tools/gate-composition` resolves the composition from the extension, one
shared copy, verified across all nine (target × extension) pairs to leave every existing mapping
unmoved before the arms were switched over.

**D16's TENTH, 2026-09-16, and it is the arc's last room: the unread artifact is A GATE'S OWN
PROSE** (AP-47). `tools/check-expectation.py`'s `stems_of()` docstring states the rule — *"a stem
that stopped being produced has to be visible as a refusal, and a glob over what exists can only
ever report what exists"* — and **fourteen lines below it the loop over those stems said
`continue`.** A composition measured for 2 of its 3 declared stems printed two measurement lines and
nothing about the third: AP-19's shape in the file whose own module docstring cites AP-19 twice.

**This is not a stale comment and the distinction is the finding.** A stale comment describes a past
behaviour. This described a behaviour that **never existed**, in the present tense, beside the code
that was supposed to have it — written down by the same author on the same day it was not
implemented. It is `unknown` wearing the costume of a specification.

**And the cost landed on the MAINTENANCE command.** `--bless` emitted paste blocks for the stems
that ran and nothing for the ones that did not; the output looks complete because absence has no
representation in a paste block, and pasting it **deletes the baseline for every unmeasured stem** —
the command that maintains the temporal reference removing it. Found by running `--bless` for the
first time since it changed, against a subject the tree produced on its own (a concurrent
`make check` had correctly `rm -f`'d its own round set).

**The question this adds, and it is the cheapest of the four:** *a tool's prose is an undeclared
assertion* — it states the author's requirement, it is written exactly where an implementer will
read it, and **it is the one claim in the file that nothing executes.** When a docstring says *has
to*, *never silently*, *always refuses* — **run it.** Enforcement point: `check_one()` returns its
declared-but-unmeasured stems, they print beside the measured ones, and `--bless` REFUSES a partial
paste block; three controls on a fixture tree, because the defect was in the WALK and no control
over the comparison functions could reach it.

### D24 — a gate's verdict does not depend on what an earlier run left in the tree

> ⚠ **RATIFIED AS `D23` ON 2026-09-12 AND RENUMBERED TO `D24` ON 2026-09-17.** Two disciplines
> were ratified as D23 two days apart — this one, and *a face reported ABSENT is a face whose
> contents are UNMEASURED* (2026-09-14, now in `THE-SEAM-AND-THE-FOUR-FACES.md`). **Nothing in
> this tree could see the collision**: our own numbering has no enforcement point, both lived
> under one `## Our own disciplines` heading in a 1,493-line file, and `D13`'s own amendment
> history had trained the reader to expect two headings sharing a number.
>
> **The face one keeps `D23` because every live citation means it** — `tools/check-expectation.py`,
> three `EXTENSION.toml` contracts, one `SYSTEM.toml`, the ledger and `docs/ANTI-PATTERNS.md`.
> This one had exactly one citation, and it is in a dated internal note that is immutable once
> written — so that citation is left standing and resolves through this entry. **A discipline number with no enforcement point is
> the thing D16 spends ten instances on**, in our own charter this time.

**Ratified 2026-09-12 on three instances in two shapes, all found by one accidental clean run**
(`docs/ANTI-PATTERNS.md` **AP-40**). The build environment was wiped and `make check-all` re-run from
nothing: `make structure` had been passing on a `gates/sdk-surface/` directory git never tracked, and
`req-coverage` and `seed-policy` inside `make check` had been passing on reports and stages that
*other* compositions' earlier runs left in `output/`.

**The two shapes:** an untracked artifact standing in for a declaration, and a per-composition gate
reading cross-composition or cross-target state. Both pass honestly on the checkout that runs them;
neither is a fact about the tree.

**Enforcement points** — `tools/check-structure.py` counts a neutral half only when `git ls-files`
lists a file in it, and REFUSES when git cannot answer. `make check` runs
`req-coverage-composition`, scoped to the plan's extensions and REFUSING on none; `make check-all` runs
`req-coverage` and `seed-policy` in its cross-target section, after every composition. **The rule for a
new gate: if it reads another composition's or another target's output, it goes in `check-all`'s
cross-target section, never in `check`.**

**The honest limit.** No gate runs from a clean checkout; the instrument that found all three was a
wipe nobody scheduled. A `make clean && make check-all` before a release is the cheap form, and it is
a practice, not an enforcement point.
