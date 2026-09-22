# Evidence, numbers and citations

<!-- Moved out of AGENTS.md on 2026-09-17 under the 2026-09 doc standard. The text is
     VERBATIM: this was a move, not a rewrite. Superseded, not appended — when one of
     these stops being true, rewrite the entry; git holds the history. -->

**Open this before putting a number, a path or a claim about another repo into any document, routing packet or declaration file.**

It holds **D14** (a number cites the artifact that produced it, never a copy of it), **D18** (a cited path resolves, or it is not a citation) and **D22** (a claim about another seat's surface is checked against OUR tree first).

---

### D14 — a number cites the artifact that produced it, never a copy of it

**Ratified 2026-09-04 on two incidents in different shapes, both ours, both in one session.**
Evidence: `docs/ANTI-PATTERNS.md` **AP-1** (a cohort count read by eye off `column`-formatted grep
output — the command said 23, the packet said 25) and **AP-2** (a conformance figure quoted from a
spec header four lines below that header's own *"this pin is historical; cite the MANIFEST beside the
bytes, never this line"*).

The two mechanisms are different and that is why this is a discipline rather than a catalog entry:
one is **a number never computed by the thing that reported it**, the other is **a number computed
correctly, then copied into a document that outlived it**. Neither is caught by re-reading the
sentence, because the sentence looks sourced in both cases.

| Kind of number | Cite | Never cite |
|---|---|---|
| **Cohort count** (*"N of 46 peers…"*) | the command, printing **the count itself** — `\| wc -l`, not a listing | a listing you counted, a table someone maintained |
| **Conformance figure** | the **MANIFEST / digest / report beside the bytes**, with the bless state at that digest | a spec header, a summary table, a README, a prior handoff |
| **Capability count** (*"N peers can host X"*) | a probe run, per peer | a packaging fact, a filename scan, a grep for a symbol |

**Enforcement point** — in any routed packet or design document in this tree, a numeric claim about
the cohort or about conformance carries, inline or in the adjacent block, **either** the command that
prints it **or** the digest of the artifact it came from. A number with neither is rewritten as a
range or as `unknown` before the document ships. Grep gate: a line matching `[0-9]+ of [0-9]+` or
`[0-9]+/[0-9]+` in `docs/**` without a backticked command, path, or 64-hex digest within eight lines
is a defect (window: **eight lines**, which is what a blockquote carrying the command actually spans).
**On its first run this gate flagged three lines in this tree and one of them was wrong**
— `15 of 26` where the command says `14`, and the off-by-one was concealing an unmade resolver
decision (AP-1, third instance). A gate that finds something the day it is written is the kind worth
keeping.

**And the two directions fail differently, which is the part worth remembering.** A wrong conformance
number usually overstates and gets caught by the next run. **A wrong cohort number usually
*understates a capability*, and nothing re-checks in that direction** — keystone found the same
asymmetry the same day, in a survey that printed `absent` where it meant `could not look`. Five
registry-publishing peers were filed as declining, one of them an M1 peer that gates every re-pin.

#### D14's own gate checks that a number CITES a command, never that the command is RIGHT

**Recorded 2026-09-12 as a declared limit, on an incident that passed the gate cleanly** (AP-36's
correction). We routed `4` to two seats, with the command inline, in a blockquote, exactly as D14
requires — and the number was ~10× low because the **pattern under-matched**: `open.grants` does
not match `open-access`, which is the spelling the oracle uses. The true figure is 19 files and
13 skip-gates, and it argued the **opposite** of the conclusion the `4` was offered for.

**Every clause of D14 was satisfied.** The number was computed by the thing that reported it
(not AP-1), it was not copied from a document that outlived it (not AP-2), and the command was
present within the window. A grep that is *wrong* is indistinguishable from a grep that is *right*
to anything that checks for the grep's presence.

**And it is D15's clause-2 gap in a third shape — the first one outside an instrument.**
`MIN_SITES` and `req-coverage`'s `LEVELS` were both *a corpus assertion bounding a pattern that
stops matching, doing nothing about one that matches the boring half.* This was that defect in a
**grep typed into a routed packet**: no floor, no refusal, no control, and cited exactly like an
instrument that has all three.

**So the rule is about the shape of the claim, not a new gate.** A hand-run `grep | wc -l` whose
count carries an argument — especially a NEGATIVE argument about another seat's surface (D22) —
gets the treatment an instrument gets: **run the pattern's complement, or name the spellings you
searched for.** `grep -c X` proves what `X` matches; it proves nothing about the thing you are
counting unless you have enumerated how that thing is spelled. Cheapest form: `grep -rliE` for the
file count beside the hit count — nineteen files would have been visible immediately, and no
argument survives *"this appears in nineteen files"* being read as *"barely entangled."*

**Not promoted to a gate, and that is deliberate.** The check would be *"is this regex the right
regex,"* which is undecidable. Declared as a limit of D14's enforcement point instead, because
D16's lesson is that an enforcement point you never execute is a wish with a citation attached —
and a gate that cannot be written is worse than one that is merely unwritten.

### D18 — a cited path resolves, or it is not a citation

**Ratified 2026-09-07 on three incidents in three shapes, all ours, all found on one instrument's
first run** (`tools/check-citations.py`).

D13's enforcement point is a citation. D14's is a citation. Both make a **path** the unit of
evidence, and until this gate existed **nothing anywhere checked that the path was real** — so a
claim could carry a perfectly-formed citation to a file that had never been written, and it would
read as the strongest kind of evidence this repo produces.

| # | the citation | what it actually was |
|---|---|---|
| 1 | `[substrate.execution_context].probe = "languages/<t>/gates/emit-context/probe-*.{mjs,py,sh}"` (dead) | **a gate that has never existed.** On the block recording the most consequential substrate fact we have measured |
| 2 | `languages/rust/{build,test,host-launch}` (dead) | a driver set the mass audit renamed; three files cited, two exist |
| 3 | `gates/host-seam/rust/` (dead) | the extension-major path, moved to `languages/rust/gates/host-seam/` on 2026-09-06 |

**The mechanism is AP-2's, one level worse.** AP-2 is a fact copied into a document that outlived
it; this is the *citation* outliving the thing it names — and a citation is what a reader checks
**instead of** re-deriving the claim. Incident 1 is the sharp one: the claim was true and was
measured, and what it pointed at was a gate somebody intended to write.

**Enforcement point** — `tools/check-citations.py`, in `make check`. Every repo-relative path named
in `extension-contracts/**`, `languages/*/compositions/*/SYSTEM.toml` and `languages/*/profile.toml`
must resolve; placeholders (`<t>`) expand over the real targets and a braced set must resolve in
**every** expansion. Build artifacts under `output/` are reported and never failed — requiring them
would make the gate red on a clean checkout, and **a false red costs the instrument** (D15).
`--self-test` plants two unresolvable citations and requires both to be caught; a run extracting
fewer than `MIN_CITATIONS` REFUSES, because the fragile part is the regex and a clean verdict over
an empty corpus is not a clean verdict.

**`docs/**` is NOT in the corpus and that is stated rather than implied.** Prose names paths in
running sentences and in examples of paths that deliberately do not exist, and this gate has no way
to tell those from citations. That is the obvious next increment and it is where the remaining
exposure is.

### D22 — a claim about another seat's surface is checked against OUR tree first

**Ratified 2026-09-11 on two incidents in two shapes, one day apart, both ours, and neither
found by reading the sentence.** Evidence: `docs/ANTI-PATTERNS.md` **AP-34** (a contract entry
claiming keystone's peer exposed no path-scope capability predicate — **contradicted by our own
CLOSED tracker row**, H9, routed by this seat) and **AP-36** (ten sites claiming *"`validate-peer`
runs against a host launched with `--debug-open-grants`"* — **explained by our own
`tools/host-launch:137`**, which is the line that passes it; the oracle dials `-addr` and launches
nothing).

**The two mechanisms are different and that is why this is a discipline rather than a second
catalog entry.** One is a claim our tree *refutes*; the other is a claim our tree *is the cause
of*. Neither is caught by re-reading, because both sentences are well-formed, specific, and — in
AP-36's case — **true about the observable**. The numbers really were undiscriminating. Only the
mechanism was misattributed, and nothing joined the claim to the line that produced it.

| the claim is about | ask, before writing it |
|---|---|
| a sibling's API **existing** | does a tracker row, a routing packet or a closed ask in *our* `docs/status/` already answer this? (AP-34) |
| a sibling's instrument **doing or not doing** something | **what INVOKES it, and is the invocation ours?** (AP-36) |
| a sibling's instrument's **coverage** | is the gap in their check set, or in the CONFIGURATION we hand it? |

**The second row is the load-bearing one, because the answer is almost always "ours."** An
oracle, a linter and a validator are libraries until something runs them. *"Their tool cannot
see X"* is, nine times in ten, *"we did not ask it to"* — and it is the shape that survives
review, because it reads as a limit of somebody else's work and therefore as nothing we owe.

**And the expensive part is not the wrong sentence.** It is that a fact filed under another
seat's ownership is a fact nobody maintains. `--debug-open-grants` was deprecated by V7 §6.9a in
v7.74 and its removal is **stated for v7.75 — a version that has since landed without performing
it**; `entity-core-go`'s peer prints a migration warning about its
own spelling. We read past all of it for eleven sessions, because the flag was not ours to think
about. **Misattributing a fact does not merely make one sentence wrong — it moves the fact out of
your maintenance.**

**Enforcement point** — a claim in this tree about a sibling repo's behaviour cites **either** a
`(symbol, path, commit)` in *their* tree **or** the line in *ours* that produces it, and where the
claim is about an instrument's reach it cites the **invocation site**. `tools/check-citations.py`
already resolves cross-repo paths and reports them as their own class; the rule here is that the
class may not be **empty** for such a claim. Grep gate candidate, not yet written: a sentence in
`extension-contracts/**` naming a sibling binary (`validate-peer`, `entity-peer`, a
`protocol-generator/*` host) without a path citation within eight lines. **Recorded as unwritten
rather than claimed** — D16's own lesson is that an enforcement point you never execute is a wish
with a citation attached, and this one would today be a wish.

**Third instance, 2026-09-12 (AP-43), and it is the third row exactly.** A `[conformance]` row read
*"not measured here"* while `entity-core-go`'s `entity_native` category measures it; the category is
outside `--profile core` and no composition had declared it. The gap was in the categories we hand
the oracle. Declared the same day, and its first run found three defects in keystone's hosts.

**The corollary for a routed packet**, and it is why AP-36 cost an erratum rather than an edit:
**a modal claim is an argument, not a description.** *"No vector CAN fail on this"* is why we
asked arch to move a spec section instead of asking ourselves to measure better. Before writing
*cannot*, `unmeasurable`, or *in principle* about another seat's instrument, construct the
configuration that would make it false. If you cannot, say `unmeasured` — and if you can, you owe
the measurement, not the adjective. Ours took forty lines (`gates/seed-policy/`).
