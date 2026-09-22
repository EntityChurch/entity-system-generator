# Anti-pattern catalog

**Named failure modes, each with the incident that produced it.** Per `METHODOLOGY.md`'s promotion
ladder: bit us once → it lands here. Bit us a **second time in a different shape** → it is promoted
to a ratified discipline in `AGENTS.md`. Between the two it is a candidate: apply it, do not claim it
generalizes.

**Only our own incidents.** Another repo's failure is read for its *shape* and cited as corroboration,
never entered here as if we had earned it. `entity-system-architecture`'s L-series and
`entity-core-keystone`'s ratchet are theirs.

---

## AP-1 — a cohort number counted by eye from formatted output

**Incident:** `ROUTING-2026-09-03-b` §1 published *"25 of the 46 peers carry the
`unsupported_expression` string; the other 21 have no `compute/literal` handling."* Both figures were
wrong. The grep behind them returned **23**; the number in the packet came from reading a
`column`-formatted terminal listing and counting the `YES` entries by sight. Nothing was re-run.

**Why it survived review:** it *looked* derived. The command was real, the output was real, and the
sentence cited the command. What was never checked is that the number in the sentence is the number
the command produced — and a two-column terminal layout is exactly the presentation that defeats
counting by eye.

**Consequence:** a routed packet told another team the cohort cost of a change, and the figure that
mattered most (*how many peers can this be done cheaply on*) was absent entirely. Keystone recounted,
scoped properly, and the real answer reframes the work: **26 peers have a ladder, 20 do not.** The
plan changes on that number, and we did not have it.

**Rule:** if a number describes the cohort, the command that produced it prints **that number**, not
a listing a human then counts. `| wc -l`, or it is not measured.

**Third instance, found by D14's own grep gate on its first run.**
`DESIGN-THE-GENERATION-MODEL` §4 said *"15 of 26 have no extension prerequisite at all."* Computed:
**14**. And the off-by-one was not arithmetic — *"no extension prerequisite"* has two defensible
readings, *names no extension* (14) and *requires no extension* (15, because `ROLE`'s attestation and
identity dependencies are marked *"optional, Tier B and above"*). **The document had silently picked
one, and the resolver has to pick too**, where the choice decides whether ROLE drags two extensions
into every composition. So the uncomputed number was also hiding a design question. **This is the
argument for the gate**: it did not merely catch a typo, it surfaced an unmade decision that a
correct-looking sentence had absorbed.

## AP-2 — a conformance figure quoted from a spec header the spec marks historical

**Incident:** `DESIGN-THE-COMPUTE-TRACK` §3 cited *"a three-way cross-impl LOCK: 330/330 vectors
byte-identical across go/rust/py"* as the current strength of the compute instrument, and rested a
build-order decision on it. That figure is `EXTENSION-COMPUTE`'s **v3.21 blessing pin**, and the
header carrying it says, four lines below the number:

> *"that pin is **historical**: it records what v3.21 was blessed against and **does not describe the
> corpus today** … A conformance claim cites the MANIFEST beside the bytes, never this line."*

**We quoted the line the sentence forbids quoting, out of the paragraph containing the sentence.**
Current state: 362 vectors, and the lock is **go-on-go — one implementation against itself** — with
the three-way bless owed.

**Why it survived review:** a spec header is an authoritative document, so a number in it reads as an
authoritative number. The distinction between *a spec* and *a conformance record that happens to be
printed in a spec* is invisible at reading speed, which is why arch wrote the warning in the first
place.

**Consequence:** the argument for moving COMPUTE up the build order was stated more strongly than the
evidence supported. The conclusion survives — the instrument is still the best available — but it
survives at "one impl locked, bless owed", not at "three-way byte-identical", and those justify
different amounts of confidence.

**Rule:** a conformance number cites the **artifact** — MANIFEST, digest, report — beside the bytes.
A spec header, a summary table, and a README are all *copies*, and a copy rots on its own schedule.

## AP-3 — an instrument that could not have reported the other answer

**Three incidents, one session, all ours, all in the first generated extension.**

*(a) The chunker test's corpus was the defect.* The §3.6 edit-stability test failed against a
**correct** FastCDC. Its byte generator was a textbook LCG, `x = (x * 1103515245 + 12345) >>> 0` —
wrong in JS, because the product exceeds 2^53 and the float multiply eats the low bits before the
truncation. The stream had 256 distinct byte values and no period under 4096, so every cheap sanity
check said *random*; but its low bits never satisfied `fp & mask_s`, every chunk ran to the forced
`max_size` boundary, and FastCDC silently degenerated into fixed-size chunking at 2× the target.
**The test could not have passed, for a reason that had nothing to do with the code under test.**

*(b) The export-surface check died before it ran.* The §3.4 MUST is enforced by asserting that a deep
import into `internal/` is refused. Written with a literal specifier, `tsc` resolves it at compile
time, fails `TS2307`, and the build dies — so the assertion never executes. **The check passing and
the check being unrunnable are indistinguishable from outside the build.**

*(c) The arms diff parsed zero checks.* `diff-arms.py` was written against a nested
`categories[].checks[]` report shape; `validate-peer` emits a flat `checks[]` list with `severity`.
It would have printed a clean diff over an empty set — *"no regressions"* — and only its own
`refusing to report a clean diff` guard caught it, on the first run.

**Why they survive review:** all three read as *green*, or as *the build is broken for an unrelated
reason*. None of them looks like a defective instrument, because a defective instrument by
construction does not report itself.

**Rule:** an instrument is not trusted until it has been observed producing the OTHER answer. For
(a) that means a corpus check — does this input actually exercise the branch? For (b), that the
assertion is reached. For (c), that a non-empty parse is a precondition and not an assumption.

## AP-4 — an instrument that reported a defect that was not there

**Two incidents, same session, and this is the expensive direction.**

*(a) The peer-staleness gate compared against a directory's mtime.* `find src -newer dist` tests
against `dist/`'s own mtime, which a directory updates only when an entry is added or removed — so a
rebuild that overwrites existing outputs in place leaves it stale by construction. It red-flagged a
peer whose `dist/` was **ten minutes newer** than its `src/`, on the first run.

*(b) A single-round A/B diff attributed a flaky check.* The bare-vs-composed regression guard flagged
`concurrency.t1_1_concurrent_demux` as a REGRESSION on its second execution. It was not: that check
suppresses its parallel-speedup signal below a **50 ms floor**, the bare arm measured 49.80 ms and got
the free pass, the composed arm measured 50.85 ms and got the signal evaluated. **One millisecond of
wall clock**, and the arms had swapped sides since the run before. Over three rounds it reads
`WARN/WARN/PASS` on *both* arms, identically.

**Why this direction costs more than a false green:** a gate that fires on a healthy build teaches
the next person to work around it. The staleness check's natural next edit is `|| true`; the arms
diff's is "ignore the concurrency ones". Both edits are locally reasonable and both destroy the
instrument.

**Rule:** before an instrument's verdict is attributed to anything, it is run in the state that
should produce the opposite verdict. For a comparison across two arms, that means **rounds**: a
difference is attributable only when it is stable within each arm.

## AP-5 — a routed finding that named one site and did not bound its extent

**Incident (2026-09-06, ours).** We routed K-3 to keystone as *"`PeerSession.execute`
discards `envelope.included`"*. True, and incomplete: the same defect sat on
**`OutboundDispatchImpl.execute`** — the §6.13(b) path a handler uses to originate an
outbound EXECUTE — and on `ExecuteResponse`'s own constructor. keystone found the other
two, and named the one that mattered: the outbound path is the one an *extension* uses, so
it is the one that would have bitten a composed system rather than a test.

**Why it survived review:** the packet was accurate. Every word of it was true, the citation
resolved, and the fix at that site was necessary. What was missing is a quantifier — the
finding was written as *"the defect is here"* when what had been established was *"the defect
is at least here"*, and the difference is invisible in a sentence that names a real site.

**How it happened, concretely:** we found the site our own test happened to touch. The test
needed `included` on a client response, that path dropped it, and the investigation stopped
at the first true statement.

**Consequence:** the receiving team did the search we should have done. That is the good
outcome and it is not the one to plan around — the same packet sent to a repo with less
appetite for verifying its own inputs closes one of three sites and leaves the worst one open.

**Rule:** a routed packet naming a call site says **"at least here"** unless the search for
other sites was run and can be cited. One grep, one line: what was searched, over what tree,
and what it returned. A finding whose extent is unbounded is routed as unbounded.

## AP-6 — a script that writes its own configuration cannot notice it is writing to the wrong place

**Incident (2026-09-06, ours.)** All three `languages/rust/` drivers carried
`export CARGO_HOME="${CARGO_HOME:-$ROOT/output/.cargo-home}"`. The toolchain image declares
`ENV CARGO_HOME=/cargo`, so the `:-` default **never fired** and every driver used the
image's path instead of the one this repo declares.

**Two of the three worked anyway, and that is the whole incident.** `build` and `test`
*write* the offline vendor-source config before reading it, so inside one container they
wrote it to `/cargo` and read it straight back. Correct behaviour, wrong location, no signal.
`host-launch` is the only driver that reads that config without writing it — and each
`podman run --rm` is a fresh container, so `/cargo` was empty. It failed as:

```
error: no matching package named `ed25519-dalek` found
location searched: crates.io index
note: offline mode (via `--offline`) can sometimes cause surprising resolution failures
```

**Why that error is the expensive part:** it names a crate, a registry and offline mode, and
points at none of them. Three plausible and wrong diagnoses are available before the real one
— a broken vendor mirror, a stale lockfile, a cargo-offline quirk — and each costs a build.

**The mechanism, stated generally:** a component that both produces and consumes a piece of
state is blind to its location. Its self-consistency is exactly what hides the error, and it
will keep working while every *other* consumer fails. Two of our three drivers were in that
position; the one that only consumes is the only one that could ever have found it.

**And the drift is D14's, arriving by a route D14 does not name.** A value this repo declares
was set in two places and the one that won was not ours — not through a stale document, but
through an inherited environment variable. `${VAR:-default}` reads as *"the default"* and
means *"whatever the environment already said"*.

**Rule:** a value this repo declares is set **unconditionally**, not with `:-`. Where an
override is genuinely wanted, it gets its own name (`GENERATOR_CARGO_TARGET_DIR`), so an
inherited variable cannot silently win a name it was never offered. And a driver that reads a
configuration it does not write **refuses when it is absent**, rather than letting the
downstream tool produce an error about something else.

## AP-7 — a test expectation that was arithmetic nobody had done

**Incident (2026-09-06, ours.)** `identical_chunks_dedup_in_the_content_store` asserted that
doubling an input re-uses every chunk of the original. It failed at *"4 of the first blob's 5
chunks"*. **The implementation was correct.** Under §3.2 fixed-size chunking a 20,000-byte
input ends in a 3,808-byte partial chunk; in the doubled input those same bytes fall inside a
full 4,096-byte chunk. Different payload, different hash, no dedup, nothing wrong.

**Not AP-3.** There the corpus could not exercise the branch under test, so the check was
unrunnable. Here the corpus exercised it perfectly and the *expectation* was wrong — a
property asserted from intuition about what dedup ought to do, against an input whose
arithmetic nobody had worked out.

**Why it is worth a catalog entry rather than a fix:** the failure mode is a **red** one, and
AP-4 already establishes that reds are the expensive direction. The locally reasonable
response to *"dedup only found 4 of 5"* is to loosen the assertion to `>= 4`, and a loosened
assertion would still pass if the chunker later stopped deduping the aligned prefix as well.
The correct response was to work out the number.

**Both outcomes kept, because both are real properties:** the dedup assertion now uses an
aligned length and asserts **all ten** chunks are shared, with a negative control that
unrelated content shares **zero**; and the unaligned case became its own named test asserting
exactly `len - 1`, because a partial tail failing to dedup is a genuine limitation of §3.2
and one of the reasons §11.2 SHOULDs FastCDC.

**Rule:** an expectation over a computed quantity is **derived before it is asserted**, and
the derivation goes in the test. Where a test's number depends on how its input divides,
the input is chosen so the division is stated rather than incidental. **A chunking test that
passes on its first run is the one to distrust** — both ports that have had one had it fail
first, for a different reason each time.

## AP-8 — a normaliser that erases a distinction manufactures agreement

**Incident (2026-09-06, ours.)** `tools/sdk-parity.py` compares public names across three
ports, so it normalises `camelCase` / `snake_case` / `SCREAMING_CASE` to one key. The first
version lowercased everything. `Blob` — a type — and `BLOB` — a type-path constant — became
the same key, and the tool reported `blob` as **present in all three ports**.

It is not. `typescript` exports the type and has no flat `BLOB` at all; it bundles the
constants into a `ContentTypes` object. The instrument had erased exactly the distinction it
was built to find, and the erasure moved the answer in the **agreeing** direction.

**Why this is not AP-3 or AP-4.** Those are an instrument that cannot reach its assertion,
and an instrument comparing the wrong quantity. This one reaches its assertion and compares
the right quantity — through a lossy projection. The comparison is sound; the *key* is not.

**Why it is the worst of the three shapes so far.** A false green loses one finding. A false
red costs the instrument. **A manufactured agreement gets published**: "24 names in all three
ports" is a sentence you write into a status doc, and nothing downstream re-derives it. The
first run of this tool produced a number that was wrong in the direction of the conclusion we
wanted, which is the direction nothing checks.

**Rule:** a comparison across heterogeneous sources normalises to a key that **preserves
every distinction the sources can express**. Where a projection is unavoidable, the projected
dimension is carried alongside — `sdk-parity` compares `(kind, snake_case)`, so a type and a
constant with the same letters can never collide. And before a parity number is reported
anywhere, the instrument is run against a source **known to differ**, to confirm it can still
see the difference after normalisation.

## AP-9 — a declaration file that nothing executes

**Incident:** `languages/<target>/profile.toml` was introduced as *"the toolchain facts for ONE
language"* and carried the container image, `host_entry`, `oracle_bin`, the packaging boundary and
the `[extension_host]` block. **Nothing parsed it.** The exhaustive search, run 2026-09-06 before
the claim was made:

> ```
> git ls-files -z | xargs -0 grep -ln 'profile\.toml'      # -> 20 files
> ```
>
> Eighteen are documents, handoffs, or the profiles themselves. The two in executable files are
> `Makefile:31` and `languages/typescript/build:12`, **both comments**. No `tomllib.loads` in the
> tree ever opened one.

So every fact the profile declared was restated where it actually ran — the image as three
`*_IMAGE` variables plus a three-way `$(if $(filter ...))` chain in the Makefile, `host_entry`
hardcoded inside each `host-launch` — and **the executing copy silently won.**

**The drift it had already permitted, which is how we know it is not a hypothetical:** the schema
had forked without anyone deciding. `python` and `rust` declared `[language].boundary`;
`typescript` carried the same fact as a comment — on the port whose boundary is the *strongest*
mechanism of the three. `python` and `rust` carried `[extension_host]`; `typescript` did not. And
`ROUTING-2026-09-06` §R-2 offered keystone a measured `[extension_host]` face row while, in this
repo, that block reached no program at all.

**Why it survived review:** a `.toml` file *reads as* a manifest. The shape is a declaration, so it
is taken for one, and *"is anything parsing this?"* is not a question a reviewer asks of a file
whose extension says it is data. It also passed every gate — by being in none of them, which is
D16's shape (an axis with no upstream authority gets no gate until someone notices).

**Consequence:** the profile could not serve as the schema for the repo's top-level organizing
unit. The open granularity question — *is `languages/` naming a language, or a (language, runtime,
packaging, toolchain) tuple?* — was **unfalsifiable while nothing executed the answer**, because a
unit with no enforced schema has no identity to test. The Makefile's three-way image branch was
also on a straight path to a forty-way one.

**Rule:** **a declaration is executed by something, or it is prose** — and prose belongs in a
comment, not in a data file. Anything this repo declares in `.toml` names the program that reads
it. Enforcement point: `tools/compose.py`'s `REQUIRED_PROFILE_FIELDS` refuses to resolve a
composition whose target profile is missing a field something consumes, and
`tools/check-structure.py` refuses a target directory with no profile at all.

## AP-10 — a correction made during port N never reaches ports 1…N-1

**Incident:** the readiness-wait budget in `host-launch` — how long the driver waits for the
composed host to print `LISTENING` before giving up. Three targets, three copies, and the values
had diverged with **no comment on any of the three**:

| | value | which port |
|---|---|---|
| `typescript` | `while [ "$i" -lt 100 ]` | **port 1** |
| `python` | `while [ "$i" -lt 150 ]` | port 2 — someone raised it |
| `rust` | `while [ "$i" -lt 150 ]` | port 3 — copied from port 2 |

**Nobody went back to port 1.** And that is the general fact, not an oversight about one number:
**port N+1 is written by copying port N**, so a correction discovered while porting lands in ports
N…last and in none of the ports written before it. **The first port is therefore systematically
the stalest — and it is the one every later port was validated against.** Here the effect was
mild (a 10-second budget where the others get 15, on the *fastest* target, which is backwards from
where a tighter budget belongs). The mechanism is not mild.

**The mirror image, found in the same file set the same hour.** `languages/rust/build` generated
`edition = "2021"` into the composition host's manifest, while `languages/rust/profile.toml`
declared the same value **four lines below a comment explaining the hazard**:

> *"an edition skew changes name resolution and closure capture, and neither should differ between
> a peer and a module compiled into the same binary"*

So the fact whose entire purpose is *do not skew* sat in two places with nothing comparing them.
One incident has no declaration; the other has one nobody reads. Same failure, opposite ends.

**Why they survived review:** a driver is *supposed* to be per-target — that is what
`languages/<target>/` is for — so a difference between two drivers reads as correct by
construction. The question nobody asks is which *kind* of difference it is. A **procedure** that
differs is the design working. A **value** that differs is a fact that has escaped the schema.

**Consequence:** none yet, which is the point of catching it at three. At forty targets it is
keystone's `run-s4.sh` exactly — 46 copies, one defect reproduced in 36 of them — and the drift
would arrive one port at a time, each instance individually reasonable.

**Rule:** **a literal that differs between drivers is an undeclared profile field.** A literal
identical in every driver is shared boilerplate and fine. Enforcement point:
`tools/check-drivers.py`, in `make check` — it extracts comparisons and assignments from every
`languages/*/{build,test,host-launch}` (dead), and any value that differs across targets without being
declared in that target's `profile.toml` is a failure.

> **And this gate's own first draft was AP-8 again.** It keyed on the operator alone, so
> `[ "$j" -lt 50 ]` (the reap loop) and `[ "$i" -lt 150 ]` (the readiness wait) collapsed into one
> `lt` bucket; first-match-wins took the 50, and **the instrument reported OK against the exact
> drift it was written to catch.** Found by running the negative control, not by reading it. The
> key now carries the literal's subject. Sixth instrument in this repo, sixth defect found by
> executing it.

## AP-11 — a re-pin is a diff against generated code, and nothing in the tree made that true

**Incident:** `EXTENSION-CONTENT` moved v3.6 → v3.7 upstream. The whole diff is **38 lines**
(`diff -u <(v3.6) <(v3.7) | grep -cE '^[<>]'` → `38`) and reads, at a glance, like a documentation
release: a version header, a changelog paragraph, and an appended Appendix A. **One of those
lines is a behaviour change in three ports.** §6.4's pseudocode `return error(403, "forbidden")`
became `return error(403, "capability_denied")`, and all three of our ports emitted the dead
spelling.

**Nothing would have said so.** Not the unit suites — each asserts what its own port emits. Not
the oracle: `entity-core-go`'s `content` category asserts exactly two codes
(`get_path_required`, `ingest_path_required`, `cmd/internal/validate/content.go`), and the 403
code is asserted by no check in that category at all. Not `sdk-parity`, which compares public
names and never looks inside a handler body. **Seven distinct codes on the wire, two of them
watched.**

**Why it survived:** a pinned snapshot makes the *input* reproducible, which is what
`shared/spec-data/` was built for and it did that job perfectly. What it does not do is make the
**projections** of that input re-derivable. `EXTENSION.toml`'s `[contract]` block is a declared
projection with a digest behind it; the *code* is an undeclared projection with nothing behind
it. So the re-pin had a checkable half and an unwatched half, and the unwatched half is where the
semantics live.

**The general shape:** **a snapshot bump is a re-transcription, not a file copy** — and every
projection of the snapshot that is not declared somewhere is a projection nobody will re-derive.
The failure is not "we forgot to grep". It is that the tree contained no artifact naming what the
handler is allowed to put on the wire, so there was nothing for the diff to be diffed *against*.

**Consequence:** caught during the re-pin, at three ports, at a cost of one edit each. At forty
targets it is forty ports emitting a code no spec defines, discovered when someone writes an
appendix.

**Rule — and it is D16's third instance rather than a new number.** *An axis with no upstream
authority gets its gate at the second implementation.* The error-code surface is exactly such an
axis, and it is the worst kind: it **looked** covered, because the oracle does assert two of the
seven codes and a category named `content` reads like it measures the content handler.
Enforcement point: `tools/check-error-codes.py`, in `make check`. Every code a port emits is
declared in `[error_surface]` with the authority that defines it — the extension's own code set,
core §3.3's enumeration, or **nothing**, which is a named, dated, routed class that `--strict`
promotes to an error.

> **And the gate's own first draft would have missed the two codes it exists for.** It scanned
> line by line; the emits that carry a long message wrap, so the call and its code are never on
> one line. Measured after the fact rather than claimed: a line scan sees 5 / 5 / 4 distinct
> codes where there are 7, and what it misses is `capability_denied` — the code the re-pin
> changed — and `path_required` — the code routed as unresolved — **on all three ports**. The
> boring emits are the short ones. **`MIN_SITES` would not have caught it either** (6 / 11 / 5
> sites, all above the floor of 4): a corpus assertion bounds a pattern that stops matching, not
> one that matches the uninteresting half. This one was caught in review, and that is worth
> writing down precisely because the other ten were not.

## AP-12 — a string replace that matched the prose before it matched the structure

**Incident:** inserting a `[substrate.path_permission]` block into
`extension-contracts/history/EXTENSION.toml`, by replacing the section header
`[substrate.accessed_event]` with *"new block + that header"*. The file contains that exact
string **twice**: once as the TOML section header, and once inside a prose note four
sections earlier — `note = "accessed is opt-in; see [substrate.accessed_event]"`.

Python's `str.replace` takes the first. The whole block landed **inside a quoted string in
the `[assumptions]` table**, which terminated the string at the block's first `"` and left
the rest of it as top-level TOML. The file stopped parsing, `compose.py` refused, and
`make error-codes` failed — and then two attempts to repair it by cutting line ranges each
mis-cut, because the damage had moved the line numbers the previous inspection reported.

**Why it survived the obvious care:** the edit *looked* anchored. A TOML section header is a
structural landmark and reads like a unique one; the duplicate was a cross-reference in
documentation — which this repo writes a great deal of, precisely because the docs cite the
structure. **The denser the cross-referencing, the more section names appear in prose, and
the less unique any structural anchor is.** That is a property of the house style, not an
accident of one file.

**Consequence:** none shipped — the gates caught it in the same minute, which is what they
are for. Three repair rounds, and the third one worked only because it stopped using line
ranges and rebuilt from line *content*.

**Rule:** **an anchored edit into a structured file anchors on structure, not on a string
that could also be prose.** Concretely, in order of preference:

1. **Parse, modify, re-emit** where a parser exists and round-trips.
2. **Anchor on a line predicate** — `line.startswith("[section]")` — not on a substring of
   the whole document. A section header is unique *at the start of a line*; the same text
   mid-line is a citation.
3. **Verify by parsing, in the same command that writes.** `tomllib.load` after the write
   costs nothing and turns a silent corruption into an immediate failure.

And the repair-specific half, which cost two of the three rounds: **line numbers from a
previous inspection are stale after any edit.** Re-derive the range from content, or delete
by predicate.

**Enforcement point:** no gate — this is a discipline about how edits are made rather than
about what lands, and inventing a linter for it would be a linter for a habit. The existing
gates are the enforcement: `tools/compose.py` refuses an unparseable contract,
`make error-codes` refuses a missing block, and both fired. **Recorded rather than
ratified**: it is one incident, and the promotion ladder says one incident is a catalog
entry. If a second lands in a different shape — a YAML anchor, a Makefile target name, a
markdown heading cited in its own document — it goes to a discipline.

---

## AP-13 — a citation to a path that was never written

**Incident (three, in one instrument's first run, 2026-09-07):**

1. `extension-contracts/history/EXTENSION.toml`'s `[substrate.execution_context]` — the
   block recording the most consequential substrate fact this repo has measured, that the
   peer delivers no execution context — carried
   `probe = "languages/<t>/gates/emit-context/probe-*.{mjs,py,sh}"` (dead). **There has never
   been a `gates/emit-context` (dead).**
2. `extension-contracts/content/arch/AUTHORING-NOTES.md` cited
   `languages/rust/{build,test,host-launch}` (dead). The 2026-09-06 mass audit factored the
   launch protocol into one shared `tools/host-launch` and left a per-target `host-entry`;
   three files cited, two exist. **Five documents kept the old name**, including `AGENTS.md`
   D17 and `check-drivers.py`'s docstring four lines above `DRIVERS = (..., "host-entry")`.
3. `languages/rust/compositions/content/SYSTEM.toml` cited `gates/host-seam/rust/` (dead), the
   extension-major path the same restructure moved.

**Why it survived:** a citation is what a reader checks **instead of** re-deriving the
claim, so a well-formed one suppresses exactly the scrutiny that would find it wrong. And
incident 1 is the sharp case — the claim was TRUE and was measured; what it pointed at was
a gate somebody intended to write. Nothing in the tree could tell the difference, because
D13 and D14 both make a path the unit of evidence and **nothing read the path.**

**Mechanism:** AP-2's, one level up. AP-2 is a *fact* copied into a document that outlived
it. This is the *citation* outliving the thing it names.

**Consequence:** none shipped. All three were prose; no gate or report was wrong. What was
wrong was the strongest-looking evidence in three documents.

**Enforcement point:** `tools/check-citations.py`, in `make check`. Promoted immediately to
**D18** — three instances in three distinct shapes (a path never written, a path renamed
by a refactor, a path moved by a restructure) is the ladder's "a second time in a different
shape" satisfied twice over, and they were found by one run of one instrument rather than
by three sessions of pain.

---

## AP-14 — a per-EXTENSION value hardcoded in a per-TARGET driver

**Incident:** `languages/rust/build` staged each extension cell and then emitted the host's
dependency line as a literal:

```sh
DEPS="$DEPS
entity-content = { path = \"../cells/$SLUG\" }"
```

The crate name is a fact about the EXTENSION; the driver is per TARGET. It was correct for
as long as `rust` had exactly one extension, and the first two-extension composition would
have emitted `entity-content` twice with two different paths.

**Why it survived:** D17 is about a value that differs across TARGETS, and this one does
not — there is one rust driver and it was internally consistent. The axis it escapes along
is the other one. `tools/check-drivers.py` compares drivers to each other and would never
have seen it.

**Consequence:** none. Found by adding HISTORY to `rust`, not by reading the driver.

**And the failure would have been LOUD**, which is the half worth recording: cargo rejects a
duplicate key, so the build would have stopped with a message about TOML rather than about
a hardcoded name. That is the opposite of AP-10's silent drift, and it is why this is a
distinct shape rather than a third instance of it — *a per-target driver can carry a value
from any axis, and only one of those axes has a gate.*

**Rule:** the D17 question — *"is this a procedure or a value"* — has a second half:
**if it is a value, which axis does it vary along?** A value that varies per target belongs
in `profile.toml`. A value that varies per extension belongs in the artifact the extension
owns, and the driver READS it. The fix reads `[package] name` out of the staged
`Cargo.toml`, scoped to that table (a bare `^name =` search finds `[lib] name`, which is the
underscored import name and resolves to nothing), and REFUSES if it is absent.

**Enforcement point:** the refusal in the driver. Not a gate — `check-drivers.py` measures
cross-target divergence and this is invisible to it by construction. **Recorded as a
candidate for widening D17** rather than as a new discipline: one incident.

---

## AP-15 — a verdict asserted on a total, when the property is a delta

**Incident (two, in one instrument, one session, 2026-09-07):** the `rust` host-seam probe's
two new emit-face arms.

- **Arm G** asserted `invocations == 1` after one `store.bind`. Measured 1 — but only
  because that arm builds its own peer and binds nothing else first.
- **Arm H**, the wire arm, asserted `invocations == 1` after one wire `system/tree:put`.
  **Measured 4.** Serving one request is not one binding: the peer also binds the caller's
  §3.5 signature into the remote namespace and its own into the local one. The arm reported
  `=> the emit face is reachable FROM THE WIRE: NO` for a face that works perfectly.

**Direction:** **false red**, which D15 names as the expensive one — the next person's
locally reasonable fix is to relax the assertion, and then it gates nothing. Here it would
have been relaxed to `>= 1`, which passes for a consumer that fires on everything and never
on the path under test.

**Why it survived the writing:** the count and the property are the same number in the
simple case, and the simple case is the one you write first. "One event for one write" is
true of `Store::fire`; "one event for one request" is a different sentence and nobody said
it.

**Consequence:** none — caught on the first run of each arm, because both PRINT the number
beside the verdict. That is the whole reason it was caught: a boolean verdict with no number
under it would have read as a substrate limit.

**Rule:** **assert on the change your action caused, not on the state afterwards.** Snapshot
before, snapshot after, assert the delta — and where the delta is over a set rather than a
counter, assert on the MEMBER (arm H now counts events whose path is the one it wrote) so
that "fired on everything" and "fired on ours" cannot both pass.

And the corollary that saved both: **print the quantity next to the verdict.** An instrument
that says only YES/NO cannot be debugged by the person who runs it, and the number is what
turned "the face does not work" into "one request is three bindings" — which became a
routed finding rather than a wrong row.

**Enforcement point:** none, and inventing one would be a linter for arithmetic. It is D15's
clause 1 working — an instrument observed producing the other answer — plus the habit of
printing the input to the verdict. **One instrument, two instances, recorded not promoted.**

---

*(AP-1 and AP-2 were promoted the same session, as `D14`. Two shapes, two mechanisms, both ours.)*
*(AP-3 and AP-4 were promoted the same session, as `D15`. Five incidents, two mechanisms, one
object — the instrument — and every one of them found by running it rather than by reading it.)*
*(AP-8 is the third instrument shape and it sharpened `D15` rather than founding a discipline:
every instrument this repo writes now ships with a **refusal**, not only a control. See
`AGENTS.md` D15; the five-for-five tally behind it is in the internal review of the first
three ports.)*

*(**AP-9 is a CANDIDATE, deliberately not promoted.** Its mechanism is D14's second one — a fact
copied into a document that outlives it, with the copy reading as authority — in a third shape:
not a number, a **declaration**. The generalisation that wants to exist is *"a declaration cites
the program that executes it, or it is prose"*, which would cover profiles, rosters and
`[host]`-style blocks as well as numbers. **One incident is not two**, and D14 already carries the
enforcement point that caught this one. Apply it; do not claim it generalises. If a second
declaration-shaped instance lands in a different shape, promote it — and the promotion should
probably widen D14 rather than found D17, because they are the same failure wearing different
data.)*

*(**AP-13 was promoted immediately, as `D18`.** Three instances in three distinct shapes,
found by one run of one instrument rather than by three sessions of pain — the ladder's
"a second time in a different shape" satisfied twice over in a single sitting. The
instrument is `tools/check-citations.py`; it went red on the day it was written, which is
the kind worth keeping.)*

*(**AP-14 and AP-15 are CANDIDATES, deliberately not promoted.** AP-14 wants to widen D17
from *"is this a procedure or a value"* to *"and if a value, along which axis"*, and AP-15
wants to widen D15 from *"seen producing the other answer"* to *"and asserting on the
quantity your action changed"*. Both are one incident each in their own shape; apply them,
do not claim they generalise. If a second lands, the promotion should widen the existing
discipline rather than found a new one — they are the same failures wearing different
data.)*

---

## AP-16 — a role classifier matched against the path when the property was the filename

**Incident (2026-09-07):** the per-cell decomposition behind `tools/scale-report.py`. Its
first draft was a shell pipeline bucketing each file in a cell by role, matching
`case "$f" in *types*) r=types;;` — **against the full path**. `typescript` contains
`types`. So every file in every `typescript` cell landed in the `types` bucket, and the
table read:

```
typescript  history  types=1217  sdk=0  handler=0  other=0  test=447
```

A port with a 1,217-line type module, no SDK and no handler. Internally consistent,
plausible if you already believed `typescript` was the port that bundles things, and
completely wrong.

**Direction:** neither green nor red — **a wrong distribution**, which is worse than
either, because the number it feeds (the projected mass of the `types` role at 26 × 46)
is exactly the number the whole report exists to produce. It would have overstated the
transcription block by ~7× on one port of three and understated `handler` to zero.

**Why it survived the writing:** the two other bucket names (`sdk`, `handler`) are not
substrings of any target name, so two thirds of the classifier were right, and the two
ports whose names contain no bucket name produced a table that looked entirely sane
beside the broken one. **Only the row that was wrong was wrong**, and it was the row
nobody had a prior expectation for.

**Caught by:** reading the output, not the code — the `sdk=0 handler=0` pair on a port
known to have both.

**Family:** AP-8. A key that collapses a distinction its sources can express, moving the
answer in the direction that gets published. AP-8's key was lossy by lowercasing;
this one is lossy by matching a *superstring* of the thing it meant.

**Rule:** **match on the narrowest thing that carries the property.** A role is a property
of the basename; matching the path silently enrols every ancestor directory name into the
pattern. And more generally: a classifier is an instrument, so the question is not whether
its rules look right but whether it has been seen putting something in the wrong bucket.

**Enforcement point:** `tools/scale-report.py --self-test` pins six `(path, role)` pairs,
of which four are `typescript` paths chosen so that the substring trap fires if the
matcher ever reads the path again.

---

## AP-17 — an instrument that read the mtime of a file it had just written

**Incident (2026-09-07):** `gates/type-parity`'s `typescript` arm, on its first run.

The arm must execute from inside the staged build — ESM resolves a bare specifier
relative to the importing file, so a probe run from outside the stage cannot see the
staged package however `cwd` is set — so it does `cp probe.mjs "$STAGE/type-parity-probe.mjs"`
and runs it there. `tools/gate-stage` then answers *"is this stage newer than the cell it
was built from?"* by taking the newest **file** mtime under the stage.

That newest file was the probe copy the **previous run of the same arm** had left behind.
So the staleness check passed over a stage built **six hours** earlier, against a cell
edited ten minutes earlier.

**Direction:** **false green**, and specifically the kind that makes a stale measurement
look fresh — the state `gates/README.md` already names as *"a gate that answers
confidently about code nobody built."*

**Why it survived the writing:** the check was written correctly and tested correctly. The
contamination is not in the comparison, it is in the *corpus* of the comparison, and it
only appears on the **second** run — the first run of a fresh arm has no leftover probe
and behaves exactly as intended.

**Caught by:** the check refusing to fire when it obviously should have, then printing the
mtimes.

**Family:** the counter-snapshot rule in `gates/README.md` — *"snapshot the counter before
the control that contaminates it"* — earned on `probe-entity-native.mjs`, where a probe's
own direct call incremented the invocation counter it was using as evidence. **Same
sentence, different quantity: a method call there, a file write here.** Two shapes,
which is what promoted it to **D19**.

**Rule:** **an instrument does not read a quantity its own execution writes.** Where the
write is unavoidable — and here it is — the fix is to make the write *distinguishable*,
not to make the read cleverer.

**Enforcement point:** `gate-probe-*` is a reserved prefix. `tools/gate-stage` excludes it
from the staleness scan; `tools/check-structure.py` fails any gate arm writing a
non-`gate-probe-*` destination into `"$STAGE/"`, with an executed negative control.
**That check found a second, pre-existing instance on the day it was written** —
`chunking-parity`'s `typescript` arm had been leaving `parity-probe.mjs` in every stage
since 2026-09-06. That arm has no staleness check today, so the defect was latent; adding
one later would have activated it silently, which is the argument for gating the **write**
rather than the read.

---

## AP-18 — a differential gate whose only baseline is the other arm

**Found:** 2026-09-07, by `tools/req-coverage.py`'s corpus scan, which reads every report in
the tree and therefore noticed two runs of the same category disagreeing.

**What happened.** `history/w6_caller_cap_absent` went `PASS → FAIL` on `typescript` and
`python` during the §9.1 execution-context work, and **every gate in this repo reported
green.**

```
composed-history  13:05  P33 W1 F0   w6=PASS
composed-history  17:41  P32 W1 F1   w6=FAIL
```

**Why nothing caught it.** `make conformance` and `make regression` are two-arm diffs: bare
versus composed, within one run. The bare arm has always failed `w6` — bare `history` is
1P/29F/4S on every target — so after the change the comparison reads `bare FAIL vs composed
FAIL`, which is **no difference**, which is not a regression. Before the change it read
`bare FAIL vs composed PASS`, an improvement. What actually happened is that the run **lost
an improvement it previously had**, and the improvement *count* is compared to nothing.

**The mechanism, stated so it transfers.** The baseline is in the **ARM** and never in
**TIME**. A differential whose reference is the other arm of the same run answers *"did the
composition break the peer"* — which is this repo's second failure mode and is exactly what
`make regression` was built for — and is **structurally blind** to *"did the composition
stop doing something it used to do."* Both are regressions; only one has a reference point.

It is worse than a gate with a blind spot, because the blind spot is in the direction of
the reassuring answer: a lost improvement shows up as a *smaller improvement count*, and a
smaller number in a column nobody asserts on is invisible.

**Predicted, three hours early.** `REVIEW-CYCLE-2` §5.2 named this shape on the same day —
*"a re-run that does not update `measured` leaves a stale number in the file that
`compose.py` parses, and nothing compares it to the report beside it… that is D14's second
mechanism with a two-day fuse."* The fuse was shorter. A prediction that lands is
corroboration and is **not** a second incident; this stays an anti-pattern.

**Caught by:** an unrelated instrument reading every report in the tree at once. Nothing
that was looking for it.

**Rule:** **a differential gate needs a baseline in time as well as in arm.** Where a
declared expectation already exists — and here it does, in each composition's `SYSTEM.toml`
— that declaration *is* the temporal baseline and the cheapest fix is to assert against it.

**Enforcement point:** owed. Named as item 2 of
`HANDOFF-2026-09-07-c-the-requirement-map-and-the-regression-nothing-compared.md`. **This
entry has no gate yet and says so** — one incident, and the fix is a new instrument rather
than a line in an existing one.

---

## AP-19 — a check name read as a check

**Found:** 2026-09-07, while mapping `EXTENSION-CONTENT` §11's requirement rows to the
oracle checks that measure them.

**What happened.** Four of the thirteen checks in the oracle's `content` category —
`inline_include_at_threshold`, `inline_include_above_threshold`, `descriptor_presence_rule`,
`descriptor_integrity_check` — have names that describe §4.3's and §2.4/§5.3's requirements
exactly. Mapping by name would have recorded four requirement rows as measured.

They do not contact the peer. They PASS in the **bare** arm — a peer with no content
extension installed at all — on all three targets, while the other nine move `FAIL`/`SKIP` →
`PASS`. They measure `entity-core-go`'s own in-process library, which is a fine thing to
measure and is a statement about the oracle. The report's `summary.self_checks` reads `0`.

**The mechanism.** A check name is a claim about what a check is *for*. Whether it measures
the thing under test is a different question, answerable only by running it in a state where
the thing under test is absent. **This is D13's Reach layer — *a call site is not a
capability* — one domain over: a check name is not a measurement.**

**What made it cheap to find, and it was luck rather than method.** This repo runs a bare
arm for an unrelated reason (our second failure mode is *"the peer was right and we broke
it"*), so the negative control was already sitting in the tree. A repo with only a composed
arm has no way to ask this question at all.

**Rule:** **before a check counts as coverage, look at what it does when the subject is
absent.** A check that passes with the extension uninstalled measures something else.

**Enforcement point:** `EXTENSION.toml [conformance]`'s `gap` field, and `req-coverage`'s
`partial` state — a row with an oracle check *and* a gap is never counted as covered. The
bare-arm evidence is quoted on the row itself (`C-R12`), so the next reader does not have to
re-derive it. Routed to `entity-core-go` as **G-4**: `DeclareSelf` already exists in their
runner for exactly this.

---

## AP-20 — a comparer that reported OK over the arms that survived

**Found:** 2026-09-07, on `gates/ext-checks/compare.py`'s **first multi-arm run**, minutes
after the file was written.

**What happened.** The `typescript` arm was added, its first invocation died before writing
anything (an unresolvable package specifier), and the gate printed:

```
=== python / content-history ===
  ADMITTED  content/get_includes_blob_entity  composed=pass  bare=fail
  ADMITTED  content/ingest_returns_root       composed=pass  bare=fail
  ADMITTED  history/local_namespace_excluded  composed=pass  bare=fail
EXT-CHECKS: OK — every authored check passes composed and fails bare.
```

**Every word of that is true and the verdict is wrong.** Half the cohort produced no data
and the sentence does not mention it.

**Why the existing refusals did not catch it.** The comparer already refused on four things
— fewer than two arms *for a pair it could see*, an arm reporting zero checks, arms
disagreeing about which checks ran, and a set below `--min-checks`. All four are questions
about **reports that exist**. A report that was never written is not a mismatch; it is an
absence, and the file had no notion of how many arms there were supposed to be.

**And the rule was already written down here.** `gates/README.md`: *"no silent caps — if a
workflow bounds coverage, log what was dropped; silent truncation reads as 'covered
everything' when it didn't."* `gates/chunking-parity` implements it as `--min-ports`, echoed
before the run. `type-parity` implements it as an echoed arm list. **The third instrument
built on that pattern did not inherit it**, because the pattern lives in two sibling files
rather than in anything shared.

**Family:** D14's understating direction — *"a wrong cohort number usually understates a
capability, and nothing re-checks in that direction."* This is the same asymmetry one level
up: the missing arm makes the verdict **narrower**, and a narrower verdict that says OK is
the one nobody re-derives.

**Rule:** **a cohort verdict names the cohort it expected, not the cohort that answered.**
The runner already knows — the Makefile globs the arms — so the expected list is free to
pass and the absence becomes a REFUSAL rather than a smaller denominator.

**Enforcement point:** `--expect-arms`, passed by `make ext-checks` from the same `wildcard`
that launches the arms, and refused with the missing targets named. Executed: the run that
found this now prints `REFUSING: 1 of 2 expected arms produced no report: typescript`.

### AP-20's second instance, one level up: an arm that never existed

**Found:** 2026-09-07, the next day, while deciding whether to build the `rust` arm.

`--expect-arms` catches an arm that **died**. It is fed by the wildcard over
`languages/*/gates/ext-checks/run`, so a target with **no arm at all** is not in the expected
list, not in the reported list, and not in the denominator. The axis printed
**`admitted: 6 of 6`** over two of the tree's three targets, and the third's absence appeared
nowhere in the output. `6 of 6` is true and reads as complete.

**Same mechanism, and the fix is the same sentence one level up: a coverage number is printed
with the population it was computed over.** `--all-targets` is the wildcard over
`languages/*`, and the run now prints `NO ARM: 1 of 3` with the target named.

**And it prints what the missing arm WOULD measure**, computed from the composition's
declared `[system.faces]` rather than asserted in prose: `rust: an arm would measure 0 of 3 —
every authored check drives a face this composition declares not-installable`. That turns
*"nobody built it"* into *"building it would measure nothing yet"*, and it flips on its own
the day a check is authored for a face that target hosts. A gap that computes itself does not
become a standing excuse.

---

## AP-21 — an arm that answered correctly and then never returned

**Found:** 2026-09-07, the same run.

**What happened.** The `typescript` arm completed all three checks, printed its verdict line,
wrote its report — and did not exit. This peer's client holds an open socket with no exported
close, so node's event loop never drained. The gate sat past a 120-second timeout with the
answer already on disk.

**Why it is worth an entry rather than a `process.exit`.** Because of what it looks like from
outside:

| | what the operator sees | what it is |
|---|---|---|
| hang **before** measuring | the gate is stuck | an infrastructure problem |
| hang **after** measuring | the gate is stuck | a finished measurement nobody read |

**They are indistinguishable at the terminal, and only one of them is a real problem.** A
gate in the second state gets treated as the first, and the locally-reasonable response to a
gate that always hangs is to stop running it — AP-4's mechanism exactly: *a false red costs
the instrument.* This is a false red made of silence.

**The asymmetry with the host is the thing to remember.** `tools/host-launch` reaps the HOST
deterministically, and it does so because keystone measured 400 ms teardown windows and a
second run that could not bind. **Nothing reaps the client**, because the client used to be
the oracle — a Go binary that exits when it is done. The first non-oracle client is where
that assumption stops holding.

**Rule:** **an instrument's last act is to exit.** Where the language will not drain on its
own, say so explicitly and name the handle that holds it open, so the next reader knows the
exit is a bounded workaround rather than a swallowed error.

**Enforcement point:** `process.exit(0)` at the tail of
`languages/typescript/gates/ext-checks/exec.mjs`, with the reason in a comment at the call
site. No gate: one incident, one language, and a lint that required every arm to exit
explicitly would fire on the arms that correctly do not need to.

---

## AP-22 — a round set that is not one run

**Found:** 2026-09-07, while building the expectation gate AP-18 owed. Not by looking for
it: by reading report timestamps to decide what a temporal baseline should be keyed on.

**What happened.** `make conformance` and `make regression` write
`<arm>-<stem>-<round>.json` and overwrite in place. A `ROUNDS=1` run therefore leaves the
**previous** run's `-2.json` untouched, and the next `ROUNDS=2` diff reads it as round 2 of
this run.

```
composed-history-1.json   2026-09-07T17:41:26Z    w6_caller_cap_absent = FAIL
composed-history-2.json   2026-09-07T13:05:15Z    w6_caller_cap_absent = PASS   <- another run
```

**Twelve of the tree's thirty-four round-sets were in that state when it was found**, across
two targets and every stem they run — including both `--profile core` sets, which is the
regression guard for our own second failure mode.

**What it cost, and this is the part that makes it an entry rather than a chore.** The
verdict was not merely computed over a wrong input. It was **laundered into the one class
this instrument reports as nobody's**:

```
history.w6_caller_cap_absent: bare=FAIL/FAIL composed=FAIL/PASS
1 check(s) MOVED BETWEEN ROUNDS -- flaky, not attributable to either arm
```

`FLAKY: 1` reads as noise. The rounds rule exists *because* of AP-4 — a concurrency check
whose verdict turned on a one-millisecond straddle of a 50 ms floor manufactured a
regression that was not there — and it is a good rule. Here **the noise suppressor absorbed
the signal**, because a report from a different run looks exactly like a round that
disagreed.

**The mechanism, stated so it transfers.** A round is identified by its **filename**, and a
filename is a slot rather than a fact about which execution filled it. Any instrument that
aggregates numbered artifacts is one interrupted run away from mixing two of them, and the
mixing presents as *variance* — which every such instrument is already built to forgive.

**Family:** D19's, one step out. D19 is *an instrument does not read a quantity its own
execution writes*; this is an instrument reading a quantity **a previous execution of the
same pipeline** wrote. Same reassuring direction, and again not catchable by a control — a
control proves the instrument can go red on a planted defect, and this went green on a real
one.

**Rule:** **a set of rounds must be one run, and the instrument must be able to say so.**

**Enforcement point:** two halves, and both are needed.

- **Structural** — `make conformance` and `make regression` `rm -f` their own round set
  before writing it. A round file this run did not write cannot exist.
- **In the instrument** — `tools/diff-arms.py` refuses when an arm's report timestamps
  **decrease** in round order. Threshold-free and therefore not a false-red source: a run
  writes round 1 before round 2, so a decrease means one of these files came from a
  different run. `--self-test` plants the live 17:41/13:05 pair and requires the refusal;
  `tools/check-expectation.py` calls the same function rather than restating it.

---

## AP-23 — a verdict decided by a threshold the two arms straddle

**Found:** 2026-09-07, minutes after AP-22's fix — the first clean two-arm `core` diff on
`typescript` reported a regression that no earlier run had, because no earlier run had two
rounds from the same execution.

**What happened.** `concurrency.t1_1_concurrent_demux` suppresses its parallel-speedup
signal when the sequential baseline lands under a fixed **50 ms** floor.

| target | arm | sequential baseline | verdict |
|---|---|---|---|
| `typescript` | bare | 49.218 / 49.680 ms | **PASS** — under the floor, signal suppressed |
| `typescript` | composed | 52.848 / 50.314 ms | **WARN** — over it, ratio 0.94 / 0.97 > 0.70 |
| `python` | bare | 9.020 / 8.511 ms | PASS |
| `python` | composed | 10.868 / 9.828 ms | PASS |

The composed peer really is slower: HISTORY records every tree write. It is **the same ~3 ms
on both targets.** What differs is only where each target's absolute baseline sits relative
to a constant — so the same composition, the same two extensions and the same delta produce
a regression on one port and nothing on the other.

**Why the rounds rule cannot help, which is the whole entry.** ROUNDS exists to separate a
verdict that moves from one that holds, and it separates **noise**. This is **bias**: stable
in every round, in the same direction, for a real reason. No number of rounds distinguishes
*"the composition broke something"* from *"the composition costs 3 ms and the oracle's floor
is at 50"*. They are the same measurement.

**And the check's own message says it is not a violation** — *"Not a §6.11 violation —
informational signal for runtimes that don't physically parallelize"* — so `PASS` here means
either *the speedup was observed* or *we declined to look*, which are the two states
keystone's `check-set-gate` exists to keep apart, one level down.

**Rule:** **a differential gate needs a third class for a difference it cannot attribute** —
distinct from a regression, distinct from flaky, and never silent. Not a suppression flag: a
per-check declaration that must name where the finding was routed, and that prints both
arms' full evidence on every run.

**Enforcement point:** `[[gate.straddle]]` in the composition's `SYSTEM.toml`, consumed by
`tools/diff-arms.py` and by `tools/check-expectation.py` **through the same function**. An
entry without `routed` is refused, because a declaration with no destination is a
suppression; `make citations` then forces that path to resolve (D18). Both arms' messages
print on every run, a declared straddle that stops being observed is reported as possibly
stale, and `--strict-straddle` promotes them all back to regressions — the switch that gets
flipped when the floor is fixed. Routed as
`ROUTING-2026-09-07-f-core-go-a-fixed-floor-makes-a-check-verdict-a-function-of-machine-speed.md`.


---

## AP-23's second day: a baseline that blessed the weather

**Found:** 2026-09-08, by `tools/check-expectation.py` going red on a tree nobody had
changed — the first time this repo's newest gate produced a finding about itself.

**What happened.** The 2026-09-07 blessing recorded `typescript`/`core` at
`bare PASS = 315 / WARN = 335` over 756 checks. The same command, on the same tree, the next
day read `314 / 336`. Nothing about the composition had moved: the difference is
`concurrency.t1_1_concurrent_demux`, whose verdict turns on whether a 50 ms floor is crossed,
under a different amount of load on the box.

**The mechanism, and it is one level up from AP-23.** AP-23 says a check whose verdict is
decided by a threshold the arms straddle cannot be **attributed** by a differential, and
`[[gate.straddle]]` handles that. It does not follow automatically that such a check cannot
be **declared** either — and that is the step that was missed. A temporal baseline that
includes an unattributable check encodes machine load as a declared fact, and then the gate
goes red on the weather.

**The direction is the expensive one.** A false red on the newest gate in the tree, arriving
the day after it landed, with an obvious-looking fix — re-bless the number — that would have
had to be repeated on every run and would have taught the next reader that this gate needs
humouring. That is how a gate gets switched off (AP-4), and the fix would have looked like
maintenance the whole way down.

**Rule:** **whatever a differential cannot attribute, a baseline cannot declare.** The two
exclusions are one decision and the declaration is the same declaration.

**Enforcement point:** `measure()` drops every `[[gate.straddle]]` check from **both arms and
from `total`**, and the run prints `excluded from the baseline as DECLARED STRADDLES` with the
names — the exclusion is counted and visible rather than a quietly smaller denominator. Four
controls, driving the real `measure()`: undeclared straddles still count as regressions and
still appear in the tally; a declared one leaves both arms, `total` and `regressed`; a real
improvement beside it is unaffected; and a declaration naming an absent check excludes
nothing.

---

## AP-24 — an authored check that addressed a type no registry defines

**Found:** 2026-09-08, while authoring the §6.2 checks — by looking up what `system/tree`'s
params type is called, which is a thing nobody had needed to do since the first check was
written.

**What happened.** `history/local_namespace_excluded` had been sending

```
params = { type = "system/tree/put-params", data = { path = "...", entity = {...} } }
```

since the day it was authored. There is no `system/tree/put-params`. `ENTITY-CORE-PROTOCOL`
§3.9 defines **`system/tree/put-request`**, whose fields are `{entity, expected_hash,
tree_id}` — no `path`, because the path travels in the resource target, which the same step
already supplied. `EXTENSION-HISTORY` §6.1's own worked example spells it correctly, four
lines from the section the check was derived from.

**Why nothing could say so, which is the entry rather than the typo.** No peer validates a
params entity's `type` against the §9.5 registry — §6.3 structural admission never checks
`data` against the type it names — so the wrong name behaves **identically** to the right
one. Both arms pass, the check is ADMITTED, and it reads as evidence. The three peers, the
oracle, five gates and a schema validator all had nothing to say about it, and none of them
was broken: a params type name is simply not a thing any of them looks at.

**And it is the axis pattern, for the sixth time.** The two `content` checks used
`system/content/ingest-request` and `system/content/get-request`, both spec-declared and both
right, so the corpus *looked* consistent. The one that was wrong is the one measuring a MUST
nothing upstream measures — which is the same sentence as D16's other five instances: **the
thing we own is the thing nothing watches**, and coverage next door is what stops the
question being asked.

**Rule:** **a check declares every wire type it sends, with the authority that defines it.**
The declaration does not prove the name is right. It forces someone to go and find the
document, which is the step that was skipped — the same mechanism that surfaced
`path_required` (MUST-ed twice, defined in no code set) when `[error_surface]` demanded an
authority for every code.

**Enforcement point:** `[check.types]` in every `extension-contracts/*/checks/*.toml`, one
entry per type name any step puts on the wire, each beginning `core` · `spec` · `ours` ·
`unresolved` and then citing the document. `gates/ext-checks/schema.py` refuses an undeclared
type **and** a declaration no step sends — a stale entry is D18's citation rot one file over.
Four planted defects in `--self-test`, each one an author could actually make, wired into
`make ext-checks-control`.

---

## AP-25 — a control that asserted a state the gate exists to change

**Found:** 2026-09-08, minutes after the §6.2 checks were admitted — `make ext-checks-control`
went red on a tree where every gate was green, for the reason the gate had just worked.

**What happened.** `gates/ext-checks/compare.py` prints a `NO ARM` block for any target this
axis does not measure, and — because *"an arm would measure 0"* must not become a standing
excuse — computes what an arm there **would** measure from the composition's declared faces.
Its own control asserted:

```
expect(f"an arm on `rust` would measure {len(r_reach)} of {len(real)} — every authored "
       f"check is handler-face and that peer hosts no handler body",
       r_reach == [] and r_unknown == [])
```

Every word was true on the day it was written. It stopped being true the moment a check was
authored for a face `rust` hosts — **which is the event the entire block exists to announce.**
The gate flipped its line from `0 of 3` to `2 of 5 — this target is worth an arm now`, and its
control called that a failure.

**Why this is worse than the same mistake in a gate.** A gate that asserts a state produces a
false red and someone investigates. A *control* that asserts a state produces a false red **on
the instrument**, and the locally-reasonable fix is to re-bless the constant — here, to write
`r_reach == []` back in, or to loosen the assertion to `>= 0`. Both suppress the trigger
permanently, and the second one looks like tidying. AP-4's cost model applied to the thing that
is supposed to be watching for AP-4.

**And it is AP-23's second day, one axis over.** *"Whatever a differential cannot attribute, a
baseline cannot declare"* has a sibling: **whatever a gate is built to change, its control
cannot assert.** Both are a measurement of today filed as a fact.

**Rule:** **a control asserts the RULE, never the current corpus.** If the control's expected
value would change when someone does the work the gate is asking for, it is not a control — it
is a snapshot with an assertion around it.

**Enforcement point:** the control now derives its expectation from the same declarations the
gate reads — reachable checks are *exactly* those whose face the composition does not declare
`not-installable` — plus a second assertion that the excluded set is the handler-face set **by
face and not by count**. Two assertions, neither of which moves when a check is added, and the
pair still fails if `reachable()` starts returning the wrong partition. The message prints the
live numbers rather than asserting them.

---

## AP-26 — a dependency that accumulated under a charter sentence saying it was absent

**Found:** 2026-09-09, by reading the charter against the build rather than either on its own.
The previous session had flagged it in a handoff as *"the charter contradiction is still
open"* and had not been able to close it, because closing it needed a ruling that is not this
project's to make.

**What happened.** `AGENTS-STANDARD.md` says *"the host needs only `make` + `podman`."*
`AGENTS.md` restates it. `Makefile` line 3 restated it. Meanwhile:

```
make check                       runs eleven tools/*.py ON THE HOST
Makefile `image_of`              shells `python3 -c "import tomllib…"`
                                   -- and it runs BEFORE an image can be chosen
tools/host-launch, gate-stage    #!/bin/sh
scale-report.py, check-glue.py   shell `git ls-files` as the tracked-file corpus
```

Five host dependencies, in eleven files, none of them declared anywhere in the tree. Searched
for a statement adopting Python as the tooling language: **there is none.** The dependency was
never chosen or argued. It accumulated.

**Why this is the catalog rather than a correction.** Three mechanisms compound, and only the
first is obvious:

- **A wrong declaration is more expensive than a missing one.** Anyone asking *"what does the
  host need?"* got a confident wrong answer from the most authoritative file in the repo.
  This is D16's third instance one level up — an axis with *partial* coverage is more
  dangerous than one with none, because the coverage is what stops anyone asking.
- **The size of a dependency is what keeps it undeclared.** Every individual `python3 -c` was
  too small to be worth an argument. Eleven of them are the tooling language.
- **The charter sentence was load-bearing in the wrong direction.** It did not merely fail to
  require a declaration — it was the reason nobody wrote one, because writing one would have
  looked like contradicting the standard.

**And the ruling was NOT that this was fine — an earlier draft of this entry said so and was
wrong.** Python and Bash are **de facto** dependencies across these projects: not adopted, but
reached for anyway despite the stated standard. **That is a discipline failure at project
scale**, the reality is accepted for now only because changing it is far more work than
declaring it, and its scope is not this repo's to rule on.

**Which sharpens the entry rather than softening it.** There are two failures here and the
second is the one this catalog is for: we do not hold our own toolchain standard, *and* the
build's real dependencies were stated nowhere while a false statement about them sat in three
places. The first is wider than this project and not ours to rule on. The second is local, is what made the
next dependency uncatchable, and is what the enforcement point below fixes.

**The near miss, on the day.** The one genuine third-party dependency in the tree is loaded
with `__import__(decl["package"])` from a name held in a TOML file. An import scan — the
obvious form of the gate — reports the neutral half as **100% stdlib** and is right by
accident, over a corpus that excludes the only thing the gate exists to find. Caught in
review, before the first run.

**Rule:** **a dependency is declared where something reads the declaration, or it is
undeclared** — and the charter asserting its absence is not a substitute for a check, it is
the thing that prevents one. When a rule in the charter is contradicted by the build, the
build is the fact; fix the rule or fix the build, but do not leave the pair standing.

**Enforcement point:** `tools/tooling.toml [host]` is the declaration and
`tools/check-toolchain.py` is the check, in `make check`. It gates the boundary rather than
the inventory — *the host half is stdlib-only; a third-party library runs in a container* —
reads both doors (`import` statements and dynamic loads, declared per site), derives the
version floor from what is actually imported rather than trusting the constant, and REFUSES
on an unlisted stdlib module so the table cannot go stale in the direction nobody notices.
Four planted defects in `--self-test`, `make toolchain-control`. Ruling and full reasoning:
`docs/adr/0001-the-host-toolchain-contract.md`.

**Not a discipline.** One incident. The ladder is explicit — the catalog now, D22 if an
undeclared host dependency arrives again in a different shape.

**And it went red on its own declaration on run one.** `container_only` was written below the
`[[host.dynamic_load]]` blocks, where TOML binds a bare key to the array-of-tables entry
rather than to the parent, so it read as absent. Eight instruments in this tree, eight that
found something the day they were written.

---

## AP-27 — a pin gate that checks its snapshot's integrity and never its currency

**Found:** 2026-09-09, by reading the upstream spec directly during a read-in, not by any
instrument in this tree.

**What happened.** We were pinned to `EXTENSION-HISTORY` **v1.8**. Arch was at **v1.10** —
two versions, both landed 2026-09-08, one of them (`v1.10`'s `pattern_exclude`) the
resolution of *our own routed finding*, and one of them (`v1.9`'s `HIST-R<n>` ids) the
resolution of *our other routed finding*. Neither reached us.

**Every pin mechanism in this tree worked exactly as designed and none of them could see it:**

| mechanism | what it asserts |
|---|---|
| `shared/spec-data/<snap>/MANIFEST.md` | the vendored bytes still hash to what we recorded |
| `[extension].snapshot` + `version` | this contract is about that directory |
| `tools/req-coverage.py` | every row **of the snapshot** is declared and mapped |
| `tools/check-citations.py` | every path we cite resolves |

**All four are statements about the copy.** A snapshot is by construction a thing that cannot
notice the original moved — that is what makes it a snapshot, and it is also why *"the pin is
green"* and *"the pin is current"* are different sentences that read identically in a status
doc.

**The near miss is the part worth keeping.** `req-coverage`'s whole reason for existing (D16's
fourth instance) is that *"a re-pin cannot add or re-word a requirement unnoticed"* — and it
is completely correct about that. **It gates the re-pin. Nothing gated the DECISION to re-pin**,
so the gate sat ready for an event that no instrument would ever announce. An instrument
positioned at a step nobody is obliged to take is not coverage of that step.

**Where it would have bitten.** `HIST-R16` is a MUST we did not implement for a day, on a
config surface that changes what a peer records — and the three ports would have kept passing
every gate in this repo, including conformance, because the oracle is pinned to its own
snapshot too and the `history` category never writes a config at all.

**What we did NOT do about it.** No currency gate was added this session. The honest options
are a network/sibling read (which makes `make check` depend on another team's working tree
being checked out and at some particular revision) or a periodic manual sweep — and the second
one is what a read-in already is. **Recorded, not fixed**, and the reason is stated rather than
elided: the cheapest correct fix is *"read the upstream spec at the start of every session that
touches an extension"*, which is a procedure and not a gate, and this catalog is where a
procedure with no enforcement point is allowed to be honest about that.

**Not a discipline. One incident.** D-numbering is earned if a second pin goes stale in a
different shape — the obvious candidate is the oracle, where keystone has already eaten it
four times and has `retired_*` fields in `tools/oracle-pin.env` precisely so a stale citation
says so instead of resolving to nothing.

---

## AP-28 — a level filter that dropped a PROHIBITION, under a parser that looked healthy

**Found:** 2026-09-09, by counting the parsed rows against the spec's table during the
HISTORY v1.10 re-pin. **This is D15 clause 2's recorded gap, second instance, and it promotes.**

**What happened.** `tools/req-coverage.py` carried

```python
LEVELS = ("MUST", "SHOULD", "MAY", "IMPL-DEFINED")
```

written before `SPECIFICATION-FORMAT` §8.5a existed, from the levels the two specs we happened
to hold used. §8.5a declares a **closed six**, and the two it adds are the negatives:
`MUST NOT` and `SHOULD NOT`. §8.5a's own table says why they matter — *"prohibited; **a
requirement, and as checkable as a MUST**."*

`EXTENSION-HISTORY` v1.9 §9.1 has sixteen rows. The parser read all sixteen, then
`if level not in LEVELS: continue` discarded **`HIST-R8`** — *"record the local peer's own
`system/history/*` writes"*, **MUST NOT**, §3.2. That is the **recursion guard**: the row this
repo cared enough about to author its own wire check for, because nothing upstream measures it.

**The tally printed fifteen requirements and was internally consistent.** Nothing was
uncovered, no rule fired, and the missing row was a prohibition — so its absence read as
*"the spec does not forbid anything here"*, which is indistinguishable from a spec that does
not.

**Why the existing defences all held and all missed it.**

- The **vacuity refusal** (D15, sharpened) fires at ZERO rows. Fifteen of sixteen is not zero.
- The **header assertion** was right: the table genuinely had a `Level` column.
- The **corpus assertion** would have been a floor — and 15 clears any floor worth setting.

**This is exactly the gap named in `AGENTS.md` under D15 and left recorded rather than
patched**, on `check-expectation.py`, where `MIN_SITES` saw 6 / 11 / 5 emit sites against a
floor of 4 while the extractor silently missed the wrapped lines: *"a corpus assertion bounds a
pattern that STOPS matching; it does nothing about one that matches the boring half."* That was
one incident. **This is the second, in a different shape** — there the loss was in a regex that
under-matched; here the parse was complete and a **filter applied afterwards** threw a row away.
Same outcome, different mechanism, which is the promotion rule.

**So D15 clause 2 is sharpened, in `AGENTS.md`:** *a corpus assertion names the property the
input must have, not a count of units.*

**The fix is the property, not a longer list.** `LEVELS` is now the closed six and `BINDING`
includes both negatives — but that only fixes today, and the next value arch adds would be
dropped the same way. So `assert_contiguous_ids` asserts the thing that is actually true of the
input: §8.5a allocates `<PREFIX>-R<n>` **once, never renumbered, contiguous from 1**, so a hole
in the parsed sequence means *this parser dropped a row*. It is self-describing, arrives with
the data, and needs no second place to update at a re-pin. Its control plants the very hole
this incident created and requires the refusal.

**And the same re-pin produced the argument for joining on those ids at all.** `HIST-R7` was
renumbered *and* re-worded in one step; under the old text join that is one `STALE` plus one
`UNDECLARED` — two failures describing one row that moved, whose quickest fix is to paste the
new wording over the old mapping and silently keep whatever the retired row claimed measured
it. Rule 0 reports it once, as a re-wording, and its control asserts that it is **not** also
reported as stale or undeclared.

---

## AP-29 — a measurement that cited its artifact and not its INVOCATION

**Found:** 2026-09-09, by diffing our executed check set against a sibling's during a read-in.
Not by any instrument here — every instrument we have agreed with itself.

**What happened.** We report the core profile as **776 checks**. `entity-core-keystone` reports
**778**, at the **same oracle build** (verified identical — 0 commits between). Two teams, one
binary, two numbers.

Neither was wrong. **They are different invocations:**

```
ours       validate-peer --profile core                          776
keystone   validate-peer --profile core -reference-peer <addr>   778
```

`origination` needs a second live peer. Without one, `validate-peer` collapses the whole category
into a single `origination/skipped` sentinel; with one, its three checks run. `3 − 1 = +2`, and
the P/S columns confirm it exactly: theirs `335P/107S`, ours `332P/108S`.

**We had never passed the flag. Not once, in the life of this repo.**

**Why D14 did not catch it, and this is the point of the entry.** D14 says *a number cites the
artifact that produced it, never a copy of it* — and we complied, fully. `776` comes from
`languages/*/output/*/reports/*.json`, the report beside the bytes, counted by a command, never
from a table anyone maintained. **The artifact was cited correctly and the artifact was
incomplete**, because a report is a function of the **flags**, and nothing on either side of the
citation recorded which flags produced it. *"776 checks"* reads as a fact about the oracle. It is
a fact about **the oracle as we invoke it**.

**And the direction is D14's own asymmetry, which is why nothing here re-derived it.** A missing
check makes the total *smaller*: fewer checks, fewer possible failures, a green run. Nothing
downstream asks *"should that number be bigger?"* — the same shape as keystone's survey printing
`absent` where it meant *could not look*, and the reason D14 says a wrong cohort number usually
**understates a capability**.

**A skip is a failure ([ADR-0012]), so this was 108 skips of which one hid three real checks.**
The sentinel is the specific hazard: one entry named `skipped` looks like one thing declined, not
like a category of three that was never asked.

**Fixed** — `tools/host-launch` starts `entity-core-go`'s own `entity-peer` on `PORT+2` for the
oracle path and passes `-reference-peer`. All three checks now PASS in **both** arms, so they add
nothing to any differential; the value is that the reports stop carrying a skipped category.
A missing reference binary **exits 3 and says so**, rather than degrading to the old behaviour —
verified by pointing `REFPEER` at a nonexistent path and observing the refusal. `make expectation`
then refused all six baselines on the changed check set, which is D21 working and is the second
event of that kind, the first one we caused ourselves.

**The general form, and it is a question to ask of every number in this tree:** not only *what
artifact produced this*, but **what invocation produced that artifact, and what would a different
one have produced**. Recorded rather than gated — one incident. **The natural second instance is
`-category`**: every conformance number here is scoped to a category list nothing outside the
Makefile declares, and that is exactly the same shape one flag over.

---

## AP-30 — an enforcement point that lives in the receiving tree, and is never run by the sender

**Found:** 2026-09-09, by running another repo's instrument against our own tree for the first
time. Not by any instrument here — this tree has fifteen gates and none of them reads our outbox.

**What happened.** `AGENTS-STANDARD.md` §*Routing packets* pins the shape of a routing packet: an
addressee block of three fields, each on its own line, opening the document. It names its own
enforcement point — arch's `spec inbound`, which scans sibling `docs/outbox/ROUTING-*` and reports
which packets addressed to you have no ledger row. **The rule existed. The instrument existed and
was maintained. Nobody had ever pointed it at us.**

One variable, same tool state, same arch HEAD, `scanned 410` in both arms:

```
git stash push                                                # before
python3 <arch-tools>/spec-tool/cli.py inbound --json           #   OURS  owed 2  unaddressed 11
git stash pop                                                  # after
python3 <arch-tools>/spec-tool/cli.py inbound --json           #   OURS  owed 3  unaddressed 0
```

**Eleven of our twenty-two packets could not be routed mechanically.** Their recipients were in
the H1 and in prose — `**From:** X. **To:** Y. **Internal.**` on one line, or nothing at all —
so the tool filed them as **UNADDRESSED**, which is UNKNOWN and is never *"not ours"*.

**Why nothing here could have caught it.** Every check in this tree reads an artifact we own
against a rule we hold. This artifact we own; the rule is upstream and the reader is downstream,
in a tree `AGENTS.md` correctly marks read-only. Reading our own packets tells you nothing —
they are perfectly clear to a human, which is exactly why eleven of them survived twenty-two
reviews. **Only the receiving instrument can see the failure, and it is the one instrument a
sender never runs.**

**And the fix made a number worse, correctly.** `owed` went 2 → 3:
`ROUTING-2026-09-03-b-keystone-h7-*` names `entity-system-architecture` as a co-recipient on a
line that also named keystone, so it had been sitting in UNKNOWN rather than on arch's worklist.
Backfilling the block moved it to `owed`, where it belongs. **A number that gets worse when a
defect is fixed is the number that was lying** — D14's asymmetry, again understating.

**Fixed** — `tools/check-routing.py`, `make routing`, in `make check`. Four FAIL rules, a
citation-form census that is counted and never failed (a prose sweep over committed record is a
decision, not a discovery — AP-4), four planted defects in `--self-test`, two vacuity refusals.
The 21 committed packets were backfilled on operator ruling; the findings themselves were not
touched.

**Its own first run was a false red, which is the streak holding.** R3 split the filename's
recipient token off positionally with a non-greedy group, read `core-go` as `core`, and failed
five packets that were correct. Instrument eighteen in this repo, eighteen with a defect, and
the seventeenth found by running rather than reading. The repair is D15's shape: ask the `To:`
field which tokens name it, rather than keeping a second copy of the naming convention in a
regex.

**The general form.** A rule that names its enforcement point feels enforced. Ask where the
instrument *runs* and who *invokes* it: **a gate in the receiving tree measures the receiver's
inbox, never the sender's outbox**, and every seat in this polyrepo is a sender. The question
for any cross-repo convention is not *is there a gate* but **whose `make check` runs it**.

---

## AP-31 — a failure message's TYPE read as the failure's CAUSE, under a protocol that makes every error a value

**Found:** 2026-09-10, by opening the oracle's source for two checks whose diagnosis had been
written down the day before. Not by re-reading the diagnosis, which is internally consistent and
wrong.

**What happened.** `typescript × COMPUTE`'s first run left 26 non-passing checks, and the
composition's reconciliation block accounted for all 26 — 14 declared absences, 3 blocked on a
seam, **4 "REAL BUGS, named and not yet fixed."** Two of the four were:

```
FAIL  v319_n5_closure_field      expected array, got entity.Entity
FAIL  v319_f11_filter_fn_arg     expected array, got entity.Entity
```

filed as *"a closure-typed value is reaching a position that wants an array. Likely the `params`
passthrough in the LAMBDA branch handing back the raw EcfValue."*

**There was no closure bug.** Both vectors dispatch `compute/apply` at
`system/compute/builtins/filter`, a §3.5 builtin this port did not implement — so the evaluator
returned `compute/error{invalid_expression}`, and §3.2's **F10** makes an evaluated
`compute/error` a **VALUE at status 200**. The oracle's `extractResultValue` decodes a 200 and
hands back what it finds, which is an `entity.Entity`. The `%T` in the message is the type of our
error object.

**So the oracle's message for *"this port refused the expression"* and its message for *"this
port mis-typed a value"* are the same string.** That is not a defect in the oracle — F10 is the
spec's design and the alternative (mapping a computed error to 4xx) is the thing this repo would
route against. It is a property of any check that asserts on a *value shape* in a protocol where
failure arrives as a well-formed value at the success status.

**The cost, and it is the shape that matters rather than the size.** Two of the four items on the
next session's worklist were fiction, with a plausible file and a plausible line named. The fix
for both was a section neither one mentioned. And the residue was mis-sized in the *reassuring*
direction: *"four real bugs plus seven builtin checks"* reads as more of our own correctness than
*"two real bugs plus nine builtin checks"* — D14's asymmetry in a new column.

**Why re-reading could not catch it.** The inference is locally valid. `got entity.Entity` in a
position expecting an array genuinely is what a mis-typed closure would produce; the branch
named even has a `params` passthrough. Nothing in the message, and nothing in our source,
distinguishes the two causes. **What distinguished them was one `grep` of the check's own body**,
which showed the word `builtins/filter` in the fixture and settled it in a line.

**The generalisation, which is D12/L8 in a new costume:** *an artifact is not a conclusion about
the thing it names* — and an oracle's failure MESSAGE is an artifact. A message reports what the
check observed at its assertion, never why the peer did it. **Before a failure message becomes a
worklist item, read the check that produced it.** The check is a few dozen lines, it is in the
tree, and it names its own fixture.

**Not fixed by an instrument, and that is deliberate.** There is nothing to gate: the message is
correct, our reading of it was not. What changed is the procedure — the reconciliation block now
carries the corrected split with the original struck through rather than deleted, because the way
it was wrong is the more useful artifact, and a future session reading *"4 real bugs"* with no
history would re-derive the same list.

---

## AP-32 — implementing a section made the coverage number go DOWN, and the old number was the lie

**Found:** 2026-09-10, by re-mapping `[conformance]` after the §3.5 builtins landed. The gate did
not fail either before or after; both states are legal declarations.

**What happened.** COMPUTE's requirement map read `MUST: 53 total, 44 oracle, 0 partial` while
§3.5's builtins were not implemented at all. Seven §3.5 rows — the collection builtins, the four
v3.24 primitives, the consumed/contained table, the limit dispositions, `group-by` key equality,
`store`, the five aliases — each cited exactly one oracle check:

```
oracle = ["compute/v314_args_types_registered"]
```

That check asserts the §3.5 **args TYPE ENTITIES are published at their tree paths**. It never
dispatches a builtin. It passed from the first run, because publishing 33 type entities is what
the type face does — so seven rows describing an unimplemented section read **fully
oracle-measured**, and the tally agreed.

After implementing the section and citing the vectors that actually exercise it:

```
MUST  53 total   44 oracle   0 partial     <- before, section NOT implemented
MUST  53 total   37 oracle   7 partial     <- after, section implemented and passing
```

**Seven MUSTs moved from `oracle` to `partial` because the work got done.** The `partial` rows
carry the real gap each time: the four v3.24 primitives have **no oracle vector at all**
(`grep -c 'builtins/range\|builtins/group-by\|builtins/concat\|builtins/assoc'
../entity-core-go/cmd/internal/validate/compute.go` → `0`), and the six passing builtin vectors
all carry integer collections and error-free closures, so **not one of them puts an error in a
contained position** — the entire disposition table is unmeasured cross-impl in both directions.

**Why the gate could not catch it.** `req-coverage.py` fails on an undeclared or a stale row and
on a citation to a check the oracle stopped declaring. It cannot know that a check named
`v314_args_types_registered` measures type publication rather than builtin behaviour — that is a
judgement about what a check *asserts*, and the whole point of the join being by section is that
no machine makes it. **The `partial` state exists for exactly this and we had not used it.**

**The generalisation, and it is the sharper half of D16's fourth instance.** That instance said
*a check named after a requirement is not a measurement of it*. This is the same sentence with
the subject moved: **a check that joins to a requirement by SECTION is not a measurement of it
either**, and a section-join is at its most flattering precisely where a section is least
implemented — because the checks that survive to pass are the shallow ones. A coverage tally that
goes UP when a section is absent and DOWN when it is built is measuring the wrong thing in the
one direction nothing re-checks.

**Fixed** — the seven rows now name their behavioural vectors and carry a `gap`; three more name
`ours` with the unit-test file. No new instrument: `partial` was already the fourth column and
already the right answer. **The number to distrust is the one that improved while nothing ran.**

---

## AP-33 — a control that stayed GREEN with the code deleted, because the substrate satisfies the clause

**Found:** 2026-09-10, by planting a defect in `§7.2`'s convergence check and watching the test for
it pass anyway. The test had been written the same hour and had never been seen going red.

**What happened.** §7.2's convergence check is normative and short:

```
old_result_hash = entity_tree.get_hash(result_path)
new_result_hash = content_hash(result)
if old_result_hash != new_result_hash:
    entity_tree.put(result_path, result, next_context)
```

*"If the new result hash equals the old result hash, the expression has converged and no tree write
occurs. This prevents unnecessary cascades."* The test asserted exactly that, in the two ways a
consumer can see it: the hash at `result_path` did not move across a trigger, and no bind event
reached the emit pipeline.

**Then the check was deleted and the test still passed.** Both observables are guaranteed one layer
down:

```
EntityTree.put:    changed = previous === null || !hashEqual(previous, entity.contentHash)
                   if (changed) { this.#emit?.emitTreeChange(...) }
ContentStore.put:  if (!this.#byHash.has(entity.contentHashHex)) { ...emit... }
```

So on this peer the clause is **redundant**, every observable in the test is the peer's answer
rather than ours, and a port that never implemented §7.2's convergence check is indistinguishable
from one that did.

**Why this is not D19 and not AP-4.** D19 is *an instrument does not read a quantity its own
execution writes* — there the instrument perturbs the reading. Here nothing is perturbed: the
reading is correct, and something **underneath the subject** is what makes it correct. The subject
under test is not the only thing that can satisfy the assertion.

**Its prior, in a different shape, is AP-19** — four `content` oracle checks passing in the BARE
arm, against a peer with the extension not installed. Same sentence: the assertion was satisfied by
the peer, and it was read as coverage of the extension. One is somebody else's check in a
differential; one is our own unit test against a peer primitive. **Two shapes, one mechanism, and
it is the reason D15 gains a sharpened clause rather than the catalog gaining another entry alone.**

**Fixed, and the fix is the useful part.** The test now asserts BOTH:

- the observable (the hash did not move, no event fired) — which is what a consumer sees, and what
  would go red on a peer whose `put` emits unconditionally, which §7.2 permits since §9.4 leaves
  delivery impl-defined; and
- **`#reEvaluate`'s own return value** — `null` on convergence, the written hash otherwise. Nothing
  in the substrate can produce that `null` on our behalf.

The second is what goes red on the planted defect. Re-planted after the fix and confirmed red.

**The generalisation, which is now D15's clause 1 sharpened.** A negative control is the **absence
of the subject**, not merely a different input — and **a control that stays green is a finding about
the PROPERTY, not a clean bill for the instrument**: it says the property belongs to something else.
Record which layer owns it; do not delete the assertion, because the layer that owns it today is not
the layer the spec addresses.

---

## AP-34 — a contract entry contradicted by our own CLOSED tracker row

**Found:** 2026-09-10, while wiring §7.2's reactive authorization, by reaching for a peer primitive
a contract in this tree said did not exist.

**What happened.** `extension-contracts/compute/EXTENSION.toml [assumptions].capability_check_scope`
read:

> This port authorizes at the DISPATCH boundary … and does not narrow per tree read, because
> `HandlerContext.callerCapability` is a token and **the peer exposes no path-scope predicate over
> it that an extension can call**.

with the consequence stated plainly — *a caller who can reach `system/compute:eval` can read any
tree path* — filed as a substrate gap, marked `gap` in `[conformance]`, and named in `sdk.ts` as
`CAPABILITY_CHECK_IS_DISPATCH_SCOPED = true`.

**The predicate is public on that peer, and we are the ones who raised it.**
`Permissions.checkPathPermission(operation, path, token, handlerPattern, localPeerId)` is exported,
takes a `CapabilityToken`, and is `ENTITY-CORE-PROTOCOL` §6.3's primitive by name. We routed its
ABSENCE on the `python` peer as **H9**
(`ROUTING-2026-09-06-d-keystone-the-emit-event-carries-no-execution-context.md` §H9), watched it
land, and wrote the closure ourselves:

Our own record of what we had settled with that team already carried the row, closed:
*`check_path_permission` exists on one peer and not the other* — landed as **H9**, public.

So the tree carried, at the same time, a closed tracker row saying the primitive is public and a
contract saying it does not exist. **Nothing could compare them**: `check-citations.py` checks that
a cited PATH resolves, not that a cited FACT still holds, and a tracker row and an assumption block
are not joined by anything.

**Cost.** One extension's §6.2 requirement rows read `gap` for five days on a gap that was not
there, and the port shipped a weaker authorization model than the substrate supported. Nothing was
routed on the strength of the wrong claim, so there is nothing to withdraw upstream — which is luck,
not process.

**This is D12 / L8's nineteenth form and the plainest one yet:** *an artifact is not a conclusion
about the thing it names.* The artifact here is our own assumption block; the thing it named is a
peer that had changed underneath it, in a change **we asked for**.

**Fixed** — the check is per tree read on both capability-bearing paths (`system/compute:eval` from
`ctx.callerCapability`, §7.2 re-evaluation from the installation grant); the H7 seam stays
dispatch-scoped because `ExpressionRequest` carries no verified token, and that row is why the
constant still exists, now reading `false`. Two tests, one at the evaluator and one through a real
`HandlerContext`, because the first would pass with the handler's wiring removed.

**No new gate, and the reason is worth stating.** The obvious one — *a claim about a sibling repo's
API is re-run against that repo* — is a lint over prose, which is `check-citations.py`'s declared
limit (`docs/**` is not in its corpus, because prose names paths that deliberately do not exist).
The thing that actually caught this was **reaching for the primitive while writing code that needed
it**, which is the ratchet working as designed: a claim about a substrate is re-tested the next time
the substrate is touched. What is owed is smaller and is done: an assumption whose subject is a
SIBLING REPO'S API names the packet that established it, so a reader lands on the ledger row.

---

## AP-35 — a gate that assumed a table's SHAPE, and a floor where a property was available

**Found:** 2026-09-10, on the first and second runs of `spec_table_codes` in
`tools/check-error-codes.py`. Instrument twenty; two defects, both found by running it, and the
first is the expensive direction.

**Defect one — five FALSE REDS from a document-wide scan.** The draft matched
`^\|\s*`([a-z0-9_]+)`\s*\|` across the whole snapshot:

```
compute: spec code table 28 rows vs 15 declared `spec`     <- §9.1 has FIFTEEN rows
FAIL -- content: 'capability_denied' is declared class `spec` and the pinned snapshot's
        code table does not name it
FAIL -- content: 'hash_mismatch' ... 'ambiguous_input' ... 'missing_input'
FAIL -- history: 'not_in_history' ...
```

Two distinct shape assumptions, both wrong:

| | assumed | actual |
|---|---|---|
| COMPUTE | §9.1 is the only backticked-first-column table | §9.2's operations table and §9.3's limits table match too — **28 for 15** |
| CONTENT / HISTORY | the code is in column 1 | Appendix A is `\| Operation \| Error Code \| Status \| Description \|` — **column 2** |

The second reported `capability_denied` — *the v3.7 correction this entire axis was built to catch*
— as an undeclared deviation. **A false red costs the instrument** (AP-4): the locally-reasonable
response to a gate that fails on the code it was written for is to stop believing it.

**Defect two — `MIN_TABLE_CODES = 5`, and it refused on a table that was correct.** The floor was
written looking at COMPUTE's fifteen rows. HISTORY's Appendix A has **two**, legitimately, and the
gate answered `REFUSING` on a clean tree. That is D15's sharpened clause 2 violated in the file that
cites it: **a corpus assertion names the PROPERTY the input must have, not a COUNT of units** — and
the count was tuned to the one document in front of the author, about a document already in the tree.

**Fixed, both, and the second fix is the transferable one.**

- `[error_surface].spec_table = { heading, code_column }` per extension, parse bounded to that
  heading's section. Compare-to-**declaration**, which is `check-spec-lists.py`'s own rule, applied
  to the axis next door.
- The floor is gone. The property is exact and needs no tuning: **every DATA ROW of the declared
  table yields exactly one code.** A moved column, a code that lost its backticks, a table rewritten
  as a list — each makes `codes < rows` at any table size, and a two-row table is as well covered as
  a fifteen-row one.

**What it found once it was right, on the section it was pointed at.** COMPUTE's `[error_surface]`
declared `ambiguous_resource` class `spec` under a header reading *"Defined in this extension's own
§9.1 code set, above"*, and §9.1's fifteen rows do not include it — **while the same file's
`[contract.error_codes]` row for that code read `"NOT IN §9.1 TABLE"`.** One contract, two readings
of one code, and nothing compared them, because the gate checked our transcription against our other
transcription and never against the bytes. Four more of the same shape arrived with §3.3
(`hash_mismatch`, `no_authorization_path`, `embedded_cap_unauthorized`, `chain_unreachable`), one of
them MUST-ed by §10.1 by name. Routed as A-20.

**And a limit of the same instrument, declared rather than discovered later.** The emit-site scanner
cannot see `embedded_cap_unauthorized` or `chain_unreachable`: the install audit returns an
`AuditRefusal(status, code, message)` VALUE and the handler converts it at one generic call site, so
the codes travel as DATA. `MIN_SITES` cannot see this either — the cell matched **142** sites. Same
shape as `check-spec-lists.py`'s recorded gap: *a corpus assertion bounds a pattern that stops
matching; it does nothing about one that matches the boring half.* Second instrument, recorded not
patched.

---

## AP-36 — a claim about another seat's instrument that was a claim about our own launch flag

**Found:** 2026-09-11, by the operator, who remembered that `--debug-open-grants` had been
deprecated and asked us to check rather than accepting the sentence.

**What happened.** Ten places in this tree carried a claim of this shape, including
`docs/STATUS.md` (which publishes), a routed packet arch is holding, and the justification for two
of its five items:

> *"No conformance vector can fail on this … because `validate-peer` runs against a host launched
> with `--debug-open-grants`: every capability in the corpus is the wide-open `*` admin grant."*

**`validate-peer` launches nothing.** It dials an address:

```
$ grep -n 'flag\.String("addr"' cmd/validate-peer/main.go        # entity-core-go @ b320c1e
24:	addr := flag.String("addr", "", "remote peer address (host:port)")

$ grep -rn "open.grants" cmd/validate-peer/ cmd/internal/validate/ | wc -l
4      # two comments, one SkipCheck message, one REGISTRY check NAME. No launch flag.
```

**We pass it.** `tools/host-launch:137` to the peer under test, `tools/host-launch:220`
(`-open-access`) to the go reference peer. Our own file, two lines, in the repo making the claim.

> **CORRECTION 2026-09-12 — THAT `4` IS REPRODUCIBLE AND IT IS ALSO THE WRONG NUMBER, AND THE
> WRONG NUMBER IS THE ONE THAT CARRIED THE ARGUMENT.** `entity-core-keystone` re-ran it against
> their pinned oracle and got ~10× more. Both are right: **the pattern under-matched.**
> `open.grants` does not match `open-access`, which is the spelling the oracle actually uses.
>
> ```
> $ grep -rniE "open.grants|open.access|debug_open" cmd/validate-peer/ cmd/internal/validate/ | wc -l
> 48                                                    # entity-core-go @ c3eaa82
> $ grep -rliE "open.grants|open.access|debug_open" cmd/validate-peer/ cmd/internal/validate/ | wc -l
> 19                                                    # files, not hits
> $ grep -rniE "SkipCheck.*(open.access|open.grants)" cmd/internal/validate/ | wc -l
> 13                                                    # checks that DO NOT RUN without the posture
> ```
>
> **And one of the nineteen is a CORE category** — `universal_address_space.go`, which
> `profile.go:33` carries as `catUniversalAddressSpace: true`. Its own skip text reads
> *"connection grants do not cover … — needs open-access or wildcard."*
>
> **The `4` was doing argumentative work and it argued backwards.** It was offered as evidence
> that the oracle is barely entangled with the posture, so the silence around A-17/A-19 must be
> *our* configuration choice. The true figure says the oracle **encodes the posture as a fixture
> assumption across nineteen files**, and thirteen checks are written to skip without it. So the
> posture is not merely ours to change: **changing it costs core surface**, which is a far
> stronger finding than the one this entry was written to record.
>
> **This is D15's clause-2 gap in a third shape, and the first one outside an instrument.**
> `MIN_SITES` and `req-coverage`'s `LEVELS` were both *a corpus assertion bounding a pattern that
> stops matching, doing nothing about one that matches the boring half*. This was the same defect
> **in a grep typed into a document** — no instrument, no floor, nothing to trip. A hand-run
> `wc -l` in a routed packet is an instrument with no refusal and no control, and it gets cited
> exactly like one that has both.

**And the modal was wrong too, which is the part that mattered to a recipient.** *"No vector CAN
fail on it"* was doing real argumentative work — it is why we asked arch to move a spec section
rather than asking ourselves to measure better. The truth is *"no vector DOES fail on it, in the
posture we choose."* Measured the same day, three arms, `make seed-policy`: under a narrow §6.9a
policy the same predicate answers `permit / refuse` where the degenerate one answers
`permit / permit`. **Unmeasured, not unmeasurable.**

**Why review did not catch it.** The sentence is *true about the observable*. The numbers really are
undiscriminating, an under-authorizing audit really does score identically, and every number quoted
around the claim was correct. Only the mechanism was wrong, and nothing in this tree joins a claim
about another seat's instrument to the line of our own harness that produces the behaviour. Eleven
sessions read past it.

**The second thing it concealed, which nobody was looking for.** The flag is **deprecated** —
`ENTITY-CORE-PROTOCOL` §6.9a (v7.74), with removal stated for **v7.75** (a version that has since
landed without performing it) — so every conformance number this repo
has published was measured against a peer in a posture the spec retired two minor versions ago, and
`entity-core-go`'s peer has been printing a migration warning about its own spelling the whole time.
**Believing the flag belonged to the oracle is exactly what stopped anyone reading its
documentation.** A fact filed under someone else's ownership is a fact nobody maintains.

**Its relation to AP-34, one day earlier.** Same family, different mechanism. AP-34 was a claim
about a sibling's API **contradicted** by our own closed tracker row; this is a claim about a
sibling's instrument **explained** by our own source file. Both are negative or attributive claims
about another seat that our own tree already answered. Two shapes, two days — **promoted to D22**.

**Fixed:** corrected at all ten sites; `[substrate.seed_policy_surface]` records the posture, its
deprecation and its removal date; `gates/seed-policy/` measures that a narrow policy discriminates
(three arms, planted-defect control); erratum routed to arch as
`ROUTING-2026-09-11-arch-the-posture-we-measure-in-is-ours-and-it-is-deprecated` §1 because two
items they hold rested on it; the fixable half routed to keystone as
`ROUTING-2026-09-11-b-keystone-the-seed-policy-replacement-reaches-no-host-binary`.


## AP-37 — a declaration written for a gate that cannot run yet, and therefore parsed by nothing

**Source:** `extension-contracts/compute/EXTENSION.toml [sdk_surface]`, authored 2026-09-10,
found 2026-09-12 on the second port's first gate run.

D16 says an axis with no upstream authority gets its gate at the SECOND implementation, and its
second instance says the gate arrives one target LATE. COMPUTE's contract took that lesson
seriously and wrote `[sdk_surface]` at port ONE, with a comment saying exactly why:

> ONE language cell today, so this block is a declaration of intent rather than a live comparison
> — `tools/sdk-parity.py` needs two. It is written NOW rather than at the second port precisely
> because that is D16.

The intent was right. **What nobody checked is that a declaration nothing parses is not a
declaration.** `sdk-parity.py` refuses below two ports, so for two days the block was authored,
reviewed, cited in a handoff — and never once read by the thing it was written for. It was in the
wrong FORM throughout: 67 raw `typescript` identifiers (`"LITERAL"`, `"isComputeExpression"`)
where the gate's key is `kind:snake_case`.

**How it presented.** `python × COMPUTE` landed, the gate ran for the first time, and
`tuple("LITERAL".split(":", 1))` produced a one-tuple:

```
IndexError: tuple index out of range   # tools/sdk-parity.py:219
```

A traceback in the middle of `make check`, which is neither a verdict nor a refusal.

**And the crash was the LUCKY outcome.** A one-tuple matches no port key, so had the f-string not
indexed `k[1]`, every one of the 67 would have been reported as
`REQUIRED ... missing from python, typescript` — sixty-seven fabricated failures in front of a
reader on the second port's first run. A false red costs the instrument (AP-4), and the
locally-reasonable response to sixty-seven of them is to stop believing the gate.

**The generalisation, and it is D16's own sentence turned inward.** *The thing we own is the thing
nothing watches* — here the unwatched thing is the gate's own DECLARATION FILE. A gate whose
refusal threshold is N ports leaves every declaration below N ports unread, so writing the
declaration early buys documentation and not enforcement. **A declaration authored before its
consumer can run needs a consumer that runs anyway**, or it is a comment with TOML syntax.

**Fixed:** `_declared_key()` refuses a malformed entry by name, with the reason inline, before any
comparison; the refusal was OBSERVED firing against the real malformed block and observed NOT
firing against `content` and `history` before the block was rewritten. The block is now 75
`kind:snake_case` names and reads `75 required · 75 in every port · 0 drift · 0 undeclared`.

**And what the same run then found, which is the better half of the story.** With the declaration
parsing, `python` reported **3 names of 75**. See AP-38.


## AP-38 — a `]` inside a comment, and a vacuity refusal that bounds zero and not the boring third

**Source:** `languages/python/gates/sdk-surface/extract.py`, found `2026-09-12` by running it.

The extractor was six lines:

```python
match = re.search(r"^__all__\s*=\s*\[(.*?)\]", text, re.S | re.M)
```

**Non-greedy, so it stops at the FIRST `]` in the region.** `entity_compute/__init__.py`'s
`__all__` carries an explanatory comment containing the literal `[sdk_surface]`, so the capture
ended inside the comment and the extractor returned **3 of 75 names**.

**The direction is the dangerous one for a parity gate.** An under-reported surface reads as
DRIFT: the neutral half would have reported 75 names as `typescript`-only — seventy-five
divergences that do not exist, on the second port's first run, in the gate whose entire job is to
notice divergence. The gate's own docstring already warns about this direction, in the SIBLING
arm, for the same cause: *"adding two explanatory comments inside `index.ts`'s export block
dropped `TRANSITION` and `HistoryTypes` from the count … an under-reported surface reads as drift
and a real drift reads as agreement."*

**Three things it teaches, and the second is the one worth carrying.**

1. **AP-10's shape on a GATE ARM.** The `typescript` arm learned to strip comments on 2026-09-06.
   The arm one directory over did not, because the arms are per-target by design and nothing
   compares them. A correction lands in the file it was found in and nowhere else.

2. **THE VACUITY REFUSAL COULD NOT CATCH IT, AND THAT IS A REAL GAP.** `emit.py` refuses a parse
   that yields ZERO names — a refusal that has fired for real, on this same extractor, in an
   earlier defect. Three names is not zero. **A vacuity refusal bounds a parse that returns
   NOTHING and does nothing about one that returns the boring third of it**, which is D15's
   clause-2 gap (AP-28) arriving in an extractor rather than in a corpus assertion: a floor
   catches a pattern that STOPS matching and misses one that matches the wrong part.

3. **The fix is the PROPERTY, not a longer regex.** Stripping comments would fix today and break
   on the first `]` inside a string literal. `_balanced_block` tracks quote state and bracket
   depth — *find the matching bracket* — which is what the parse actually means.

**Fixed:** balanced scan plus comment stripping; verified name-for-name against the old extractor
on all three cells before the arms were trusted (`content` 37→37 identical, `history` 39→39
identical, `compute` 3→75 with nothing lost), because a refactor that quietly changes what an
instrument measures is worse than the duplication it removed.


## AP-39 — a gate whose extension axis was a wildcard and whose COMPOSITION axis was a literal

**Source:** `gates/type-parity`'s three arms, latent since `2026-09-09`, found `2026-09-12`.

The Makefile made the extension axis data, on purpose, with the reason written down:

> The extension axis of type-parity is a wildcard too: the gate is per (extension × arm), so a new
> contract directory joins the cohort without a Makefile edit, exactly as a new target directory
> does.

Each of the three per-target arms then opened with:

```sh
COMPOSITION="${COMPOSITION:-content-history}"
```

**Those two sentences disagree, and the disagreement is silent until an extension appears that
`content-history` does not contain.** COMPUTE appeared on 2026-09-09. From that day
`make type-parity` could not measure it on any target — `languages/typescript/output/content-history/build/node_modules/@entity-core/`
holds `extension-content` and `extension-history` and nothing else, so the arm was pointed at a
stage that could not contain its subject.

**It did not report a wrong answer, and that is the only reason this is an anti-pattern rather than
an incident.** `tools/gate-stage` refused with `UNKNOWN … exit 3` — the right refusal for the
wrong reason. But the gate is in `make check`, so **the newest extension's type layer went
unmeasured by the one instrument built to compare it across ports, at the exact moment a second
port made the comparison possible.**

**Why no existing gate could see it.** `tools/check-drivers.py` fails a literal that DIFFERS
across targets (D17/AP-10's shape: a correction lands in ports N…last and never in 1…N-1). This
literal was IDENTICAL in all three, which is the `N copies of one protocol` shape keystone paid
for — a different failure with a different gate, and neither covers the other. **Recorded as a
declared limit of D17's enforcement point rather than as a new gate**: "is this repeated constant
the right constant" is the undecidable question D14's own declared limit already names.

**The generalisation.** `gates/README.md`'s matrix-as-data rule is per AXIS, and a gate with three
axes can be data in two of them and a literal in the third. **When a gate grows an axis, ask what
the OTHER axes are keyed on** — here the (extension → composition) mapping was never a decision
anybody made; it was the value that happened to be right when there were two extensions.

**Fixed:** `tools/gate-composition` resolves the composition from the extension by reading
`[system].extensions` out of each `SYSTEM.toml` — one shared copy, all three arms call it,
`COMPOSITION` in the environment still wins. The rule is *"most extensions, ties on name"*, chosen
so every existing mapping is unchanged (`content` and `history` both still resolve to
`content-history`) and verified against all nine (target × extension) pairs before the arms were
switched over. `TYPES_MIN_PORTS` also moved from *"targets with an arm"* to *"targets with a CELL
for this extension"*, because `rust` has an arm and no `compute` cell and a per-target floor
demands a report from a port that has nothing to report. First run after the fix: **2 ports agree
on all 33 compute type entities, by content hash AND field map.**


## AP-40 — a gate whose verdict depended on something an earlier run had left behind

**2026-09-12, three instances in two shapes, found by one event nobody planned: the build environment
was wiped** (keystone's images, oracle, vendor mirror and built peers, and our own `output/`), and
`make check-all` was re-run from nothing.

| # | gate | what it had been passing on | shape |
|---|---|---|---|
| 1 | `make structure` | a `gates/sdk-surface/` directory **git never tracked** (`git log --all -- gates/sdk-surface` prints nothing) | an untracked artifact standing in for a declaration |
| 2 | `make req-coverage` inside `make check` | other compositions' reports in `output/` — `check-all` builds `python/compute` first, and on a clean tree it has no `content` or `history` report | a per-composition gate reading cross-composition state |
| 3 | `make seed-policy` inside `make check` | `typescript/output/compute/build`, which `check-all` had not built yet while on `python/compute` | a per-composition gate running every target's arm |

**None of the three was wrong about the tree it measured on the machine that ran it.** Every one
passed honestly against the files present. What no instrument could see is that the files present
were not the tree: a previous run's `output/`, and a directory nobody committed.

**The fixes are structural, not a smarter check.** `check-structure.py` requires a neutral half to
contain a file `git ls-files` lists (and REFUSES if git cannot answer); `make check` runs
`req-coverage-composition`, scoped to the plan's own extensions; `check-all` runs the unscoped
`req-coverage` and `seed-policy` after every composition, beside `parity` and `type-parity`.
Verified by the run that found them: all 8 compositions green from a wiped substrate.

**The generalisation: a gate that reads state outside its composition belongs in the cross-target
section, and "it passed here" is a claim about this checkout until it has passed on a clean one.**

## AP-41 — an ask routed to a seat whose tree already carried the work

**2026-09-12.** `ROUTING-2026-09-12-c-keystone-*` §1 asked keystone for H1 on `rust` — correctly
measured, correctly costed, and written without looking at keystone's tree beyond `dev`. An hour
later, reading their `SPEC-KEYSTONE-PEER` to verify a different claim, the sibling
`entity-core-keystone-wt-rust` worktree turned up: branch `rust-host-contract`, uncommitted,
adding `register_handler`, a `Handler` trait, `ExpressionEvaluator` and `LocalExecute`.

**The packet was not wrong — nothing had landed — but it read as a cold request for work in
flight, and it missed the most useful thing to say.** As written, that `register_handler` refuses
every `system/*` pattern, citing a §6.2 sentence core withdrew at 0.8.2.13, so H1 would land and
still host none of our extensions. That went out as a same-day addendum; it is the half of the
packet worth the most, and it was found second.

**Candidate, not a discipline: one instance.** It is D22's shape one direction over — D22 checks a
claim about another seat against OUR tree first; this is checking an ASK against THEIR tree first.
**And it does not conflict with "do not track another repo's queue".** Looking once, before
routing an ask about a surface, is due diligence on the ask. Reporting their progress back is
tracking. The first is owed; the second is not ours.

## AP-42 — a compile-fail arm that counted errors, and the count survived a change of cause

**2026-09-12, found by keystone, not by us.** `languages/rust/gates/host-seam/probe-seam-rust.sh`
required `access_absent` to fail with four distinct `error[E…]` diagnostics — one per claim. Keystone
made `register_handler` public and built our fixture against the change: still four of four. The
fixture passed two arguments to a method that now takes one, so claim 1 (`E0624 register_handler is
private`) had become `E0061 wrong argument count`. **The instrument's strongest verdict, over a claim
that was false.**

**The mechanism is D15's, at the one layer our refusals did not cover.** The arm had a positive
control (a sibling must compile) and a vacuity refusal (fewer than four errors refuses). Neither can
see an error that is present for a different reason. A count is a corpus assertion over a COUNT of
units, which D15's 2026-09-09 sharpening already says is the wrong kind: *name the property the input
must have.* The property here is the error CODE of each claim.

**Fixed:** the arm requires each claimed code (`E0616` `E0609` `E0603` `E0624`) and refuses any
unclaimed one. Candidate for D15's enforcement text, not a new discipline: it is the rule we had,
applied to an instrument written before the rule.

## AP-43 — "not measured here" was a fact about the categories we declared

**2026-09-12, found by the compute-arc review.** `extension-contracts/compute/EXTENSION.toml`
`[conformance]` carried §3.2 E1 (entity-native scope bindings) with `oracle = []` and *"Not measured
here."* `entity-core-go`'s `entity_native` category measures exactly that row — 13 checks — and sits
outside `--profile core`, so no composition in this tree had ever declared it. Declared on all three
compute compositions the same day; its first run moved 7 checks on `rust`, 5 on `typescript`, 0 on
`python` (predicted by name), and exposed three defects in keystone's hosts from the BARE arm.

**D22's third row, verbatim:** *"a sibling's instrument's coverage — is the gap in their check set, or
in the CONFIGURATION we hand it?"* Third instance of D22 in two days. No new rule; the question was
written and not asked of our own `categories` list.

## AP-44 — an entity-native body evaluated under the caller's capability, caught before any run

**2026-09-12.** The first `rust` H7 evaluator narrowed tree reads by `ctx.caller_capability()` and
passed it as `ctx.capability`, and its contract row presented that as an advantage over `typescript`.
Core 0.8.2.21 §6.1 step 3 says `ctx.capability = handler_grant` "regardless of the caller's
capability", and COMPUTE §4.1's comment says the handler grant authorizes an entity-native body. Under
the wrong reading the F2 ceiling IS the caller's capability, so `capability =
lookup/scope("caller_capability")` passes its own dual check — the escape F2 exists to block.

**Caught by a read-only cross-port review launched before the composed run, not by the run**, which
under the degenerate seed policy could not have distinguished the two readings. The oracle's
`entity_native.dual_check_handler_grant_blocks` can, and passed on the corrected code. The shape worth
keeping is small: **an authority claim written as a port's advantage over its siblings is exactly the
sentence to verify against the spec before writing it.**

## AP-45 — the port's two defects lived behind a face that could not be installed

**2026-09-14. The incident that ratified D23.** `languages/python/extensions/compute`'s H7 evaluator
carried three defects at once: the wrong signature (one argument returning a bare `Entity`, where
the certified binding is `(ExpressionRequest, HandlerContext) -> Outcome | None`), no §3.2 E1 scope
pre-population at all — `evaluate_at` had no `bindings` parameter — and no §4.1 narrowing of tree
reads under the handler grant.

**Every one was unreachable, so nothing was wrong anywhere.** Keystone's `python` peer had no
`set_expression_evaluator`, the installer correctly reported `evaluator_face = "not-installable"`,
the composition's `[gate.baseline.entity_native]` was blessed at `improved = []`, and all of that
was TRUE. The unit tests drove the detector against stand-in peers, so the detector was known-good;
what no stand-in exercised was whether the thing being installed would work if it ever were.

Keystone's S3 bring-up landed the seam. Installing against it moved the category **3 → 9 of 13** in
three steps, one per defect. **The first was theirs to predict and they did** (their 13-c §3 named
the signature and told us not to paper over it with a read-back). The other two were ours and
nobody had a way to find them.

**The catalog shape:** a face that cannot be installed hides every defect behind it, and the honest
report of the absence is what makes the hiding look like an account. Distinct from AP-19 (four
`content` checks that pass on the BARE peer — an assertion satisfied by the wrong subject); here
there is no assertion at all, and the artifact recording that says so in words that read like a
finding. Enforcement is D23's `why_nothing_moved`.

## AP-46 — a reconciliation pinned to a SHA, and two packets arrived after it

**2026-09-14.** `TRACKER-entity-core-keystone.md` recorded a reconciliation pinned to a specific
commit on `entity-core-keystone`'s `dev`, dated 2026-09-13. Keystone committed two packets addressed
to us **later the same day**, and a merge then interleaved them with an unrelated 45-language
sweep addressed to arch. Their tracker carried both as open asks from the hour they landed; ours had
no row for either, so on our side the channel read as quiet.

**Nothing was careless and the ledger was not stale in the usual sense** — it named the exact commit
it was complete as of, which is more rigour than most rows get. That is the trap: *reconciled @ SHA*
reads as *reconciled*, and a SHA from earlier the same day looks current.

**The rule:** reconcile against the counterpart's HEAD, and record the SHA you READ rather than the
SHA you last read. D16's seventh instance is the enforcement point that would catch the other
direction (our outbox); this is the inbox, and `tools/check-routing.py`'s T3 only checks packets it
can see in the sending tree — which is every packet, so pointing it at keystone's HEAD is the cheap
form and is now what the reconciliation step does.

---

## AP-47 — the function's own docstring stated the rule; the function two lines down said `continue`

**2026-09-16, found by running `--bless` for the first time since it changed** — not by reading the
file, which is the twentieth instrument in this tree and the same way nineteen of them were found.

`tools/check-expectation.py` walks the stems a composition declares in `[gate]`. `stems_of()`'s
docstring says why it reads the declaration rather than globbing the filesystem:

> *"A stem that stopped being produced has to be visible as a refusal, and a glob over what exists
> can only ever report what exists."*

**Fourteen lines below it, the loop over those stems read:**

```python
if not bare_p and not composed_p:
    continue
```

So a composition measured for 2 of its 3 declared stems printed two measurement lines and **nothing
whatever about the third** — AP-19's shape (*a line that reads like a measurement over a state that
produced none*) in the file whose own module docstring cites AP-19 twice.

**The requirement was written down, in the same file, by the same author, on the same day it was not
implemented.** Nothing in the tree could say so: a docstring is prose, no gate reads it, and the
sentence is *true about the intent* — which is what makes this different from a stale comment. A
stale comment describes a past behaviour. **This one describes a behaviour that never existed, in
the present tense, beside the code that was supposed to have it.**

### The expensive half is the maintenance command, not the report

`--bless` prints the TOML to paste into `SYSTEM.toml`. Blessing a partially-measured composition
emitted blocks for the stems that ran and **nothing for the ones that did not** — and the output
looks complete, because absence has no representation in a paste block. Pasting it **DELETES the
baseline for every unmeasured stem.**

> **The command that maintains the artifact is the one that removes it**, and the artifact is
> `[gate.baseline]` — the temporal reference whose entire job is remembering a capability over time,
> which is AP-18, which is why this file exists.

**And the subject was real rather than planted.** A concurrent `make check` had `rm -f`'d its own
round set (D21's *a reference that is ONE RUN* rule, working correctly), so `rust × content` was
genuinely missing its `core` reports at the moment `--bless` ran. The tree produced the condition on
its own.

**Fixed:** `check_one()` returns a fourth element, the declared-but-unmeasured stems; they are
PRINTED beside the stems that were measured; and `--bless` **REFUSES** rather than emitting a partial
paste block, naming what to run first. Not a failure and not a refusal in the normal path — running
one category (`make conformance CATEGORIES=content`) is ordinary and failing on it would be a false
red on a normal workflow (AP-4). Three controls on a fixture tree, because the defect was in the
WALK and no control over the comparison functions could have reached it.

**The transferable question, and it is cheap to ask:** when a docstring states a property — *"has to
be visible"*, *"is never silently"*, *"always refuses"* — **run the thing and check.** Prose in a
tool is an undeclared assertion: it is the author's requirement, it is written where the
implementer will read it, and it is the one claim in the file that nothing executes.

## AP-48 — both verdicts were right, and the sentence under one of them told the reader the wrong thing

**2026-09-16, found by planting the real event against the real corpus** — `content/type_blob`
renamed to `content/type_blob_entity`, which is what a `validate-peer` re-pin does — and then
planting it a third time in the shape nobody had thought about: a `type_system` pin, where the
obligation is carried by **222 other checks**.

`req-coverage.py` rule 3's §5b split works. A pin that vanishes reads `RE-PINNED (not lost)` when
something still carries its obligation and `MEASUREMENT LOST` when nothing does, and both arms were
observed producing exactly that. **The defect was in the paragraph the correct verdict shipped
with.** Every `RE-PINNED` failure closed on:

> *The measurement did not go away; the NAME did. Update the pin and the
> `[conformance.obligation]` entry together.*

which is true when the obligation has one carrier and **unsupportable when it has 222**. `Types
§11.2` is a section citation covering every type entity in the registry; that some check still cites
it says nothing about whether the check that asserted *this* type survived. The spread caveat was
printed — and printed **above** the reassurance, so the sentence a reader acts on was the one the
join could not justify.

### Why no control could catch it

D15's controls assert on the **verdict**. Both verdicts were correct in every arm, including the
wide one, so a control over `RE-PINNED` vs `MEASUREMENT LOST` was green throughout and stayed green.

> **An instrument's output is prose plus a verdict, and only the verdict is ever asserted on.**
> The verdict tells the reader there is a problem; **the prose tells them what to do about it**, and
> the remedy is the part that edits the tree. A correct verdict with a misdirecting remedy is worse
> than a false red: a false red gets argued with, and a remedy gets followed.

That is AP-47's question — *a tool's prose is an undeclared assertion* — moved from the docstring an
implementer reads to **the message a reader acts on**, which is executed every run and asserted on
by nothing.

**Fixed:** the closing sentence is chosen by breadth. Below `SPREAD_NOISY` carriers it says the name
moved; at or above it, the caveat **gets the last word** and says the opposite — join on the
obligation to find the candidates, *not* to conclude the coverage held, and if none of them asserts
what the old one did, this is a `MEASUREMENT LOST` wearing a rename. Both arms are controls, and the
one that matters is the **negative**: the wide arm asserts the reassurance is ABSENT (`not failed(r,
"the NAME did")`). A caveat that fires on every rename is not information; a reassurance that fires
on every rename is a defect.

**The transferable rule, and it is the cheapest half of D15 nobody was doing:** when a gate's
failure message tells the reader what to fix, **the control asserts on that sentence**, in both
directions, not only on the verdict it sits under.

## AP-49 — a blocker on ONE CLAUSE of a MUST, carried as a blocker on the MUST

**2026-09-16, found by doing the work the row said was only possible on one port.**

`LEDGER W-1` read: *"`rust`: nothing. ts/python: an unforgeable context is a keystone surface."* It
is a true sentence and it was read, for four days, as **CONTENT §3.4 is blocked on keystone for two
of three ports**. §3.4 has two clauses:

| clause | what it needs | who is blocked |
|---|---|---|
| 1 — the wrapper's anchor is not forgeable | a dispatch context a consumer cannot construct | **ts/python, on keystone** (`K-24`) |
| 2 — the wrapper **checks a capability** | a path-scope predicate | **nobody.** `H9` shipped `check_path_permission` on all three peers |

**Clause 2 is the half §3.4 actually MUSTs** — *"without an explicit capability-checking wrapper"* —
and it was implementable on every port the whole time. The blocked half is the one that makes the
check *sound*, not the one that makes it *exist*.

**The mechanism is a schema, not a misreading.** The ledger's row has one `Blocked on` column and the
requirement has two clauses, so the strongest blocker in the row fills the slot and the rest of the
requirement inherits it. Nobody wrote anything false; the row had nowhere to put *"and this other
half is ours and undone."*

> **This is D13's amendment one level up.** That one says *a seam claim names a FACE, or it names
> nothing* — the four layers were complete as predicates and silent about what they ranged over.
> Here the blocker is correct and silent about **which clause it is a blocker for**. Same defect,
> different subject: a claim whose predicates are right and whose subject is under-specified reads
> as a verdict about the whole thing.

**Recorded, not promoted.** One incident, and D13's amendment already names the shape for capability
claims; a second instance in a different shape — a blocked-on, an assumption, a substrate row — makes
it the general rule. The cheap habit meanwhile: **when a requirement has two clauses, the blocker
names one.** `[substrate.capability_wrapper]` now carries `typescript_blocked_on` and
`python_blocked_on`, both reading `"clause 1 only"`.

## AP-50 — a compile-fail fixture measures ONE refusal, because the compiler stops

**2026-09-16, and the gate caught its own author inside the hour it was written.**

§3.4's re-anchoring added a second claim to `content`'s `deep_import.rs`: alongside `E0603` (the
algorithm is not reachable), an attempt to construct the peer's `HandlerContext`, claiming `E0451`
(the anchor cannot be forged). The arm reported:

```
test: content claimed refusal(s) NOT observed: E0451
          error[E0603]: module `internal` is private
```

**`rustc` refused the file at NAME RESOLUTION and never type-checked the construction.** The second
claim was not weak, not wrong, and not unsupported — it was never *reached*. A compile-fail fixture
asserts about the first compiler phase that has something to say, and every claim behind that phase
is silently unmeasured.

**The old arm would have passed.** It hardcoded *"require `error[E0603]`"*, which was present. The
new claim would have sat in the fixture, cited in the contract and in a routing packet, asserting
nothing — AP-37's shape (*a declaration written for a gate that cannot run yet is parsed by nothing*)
with the gate running perfectly and the declaration out of its reach.

**What caught it** is the change AP-42 asked for: the fixture declares `//! CLAIMS: <codes>`, the
driver requires each and **fails on an unclaimed code too**. A count could not have seen this; a
hardcoded single code could not have seen this; only *this fixture claims exactly these codes* could.

**Fixed:** one fixture per claim (`deep_import.rs` → `E0603`, `forge_context.rs` → `E0451`), and the
driver globs `src/bin/*.rs` instead of naming `deep_import`, so a cell adds a claim by adding a file
(D20 — the driver enumerates nothing). Four controls, all executed and observed: a claimed code
absent → red; an unclaimed code present → red; **no `CLAIMS:` header → REFUSING**, because a fixture
with nothing to require would report the refusal of a broken build as a boundary; and a fixture that
**compiles** → red.

**The transferable question:** for any check that asserts a tool REFUSED, ask *which phase refuses,
and is everything I am claiming reachable in that phase?* Two claims in one artifact are two claims
only if the artifact gets far enough to make both.

---

## AP-51 — the correction landed in the file where it was noticed, and the same claim two files over went unsearched

**2026-09-16, found while implementing §3.4 clause 2 on `typescript` and `python`. Four days old, and
it survived the review that created it.**

The 2026-09-12 cross-port review found that `reassembleUnderCapability`'s claim — *a consumer cannot
manufacture a `HandlerContext`* — was **false on both dynamic ports**. It corrected the claim, in the
strongest available form, in `sdk.ts` and `sdk.py`:

> **The check is weaker than this comment used to claim.** It said a `HandlerContext` cannot be
> manufactured by a consumer. It can: the class is exported with a public constructor, and this
> repo's own `test/handler.test.ts` builds one.

**And twenty lines away, in `internal/reassemble.ts` and `_internal/reassemble.py`, the original
claim was still asserted, unannotated, in the present tense:**

> which takes a `HandlerContext` it cannot manufacture — a `HandlerContext` exists only because the
> dispatcher built one … The capability check is therefore not a check this module performs on
> trust; it is a check the caller cannot have skipped.

Both files are in the same package, both were open in the same session, and the false sentence is the
**reason the module gives for existing at all**.

**The mechanism is AP-10's, inside one port instead of across three.** There, a correction made at
port N lands in ports N…last and never in 1…N-1, because port N+1 is written by copying port N. Here
the correction was made at the SITE OF THE DEFECT and never at the site of the ASSERTION, because
what was searched for was the wrong function — not the claim.

**And the correction's own form is what makes this expensive.** A docstring that says *"this used to
claim X, and X is false"* is the most convincing artifact in the tree: it names the error, it dates
it, it reads as somebody having already done the work. **A reader who lands on the OTHER file gets
none of that signal** — they get X, stated plainly, with no marker that it is contested, in a file
whose whole purpose is to justify a §3.4 MUST. The corrected file makes the uncorrected one *more*
believable, not less.

**It is also AP-47 in a second shape.** There, a docstring stated a rule the code beneath it did not
implement. Here, a docstring states a property the peer does not have. Same class: **a tool's prose is
an undeclared assertion, and it is the one claim in a file that nothing executes.** `check-citations`
proves a cited path resolves; nothing anywhere proves a cited *property* holds.

**The rule, and it is cheap:** *when you correct a claim, grep for the CLAIM, not for the file.* One
`grep -rn "cannot manufacture\|cannot have skipped"` over the cell would have returned both sites in
2026-09-12. The search term is the sentence you just proved wrong.

**No gate, stated rather than implied** (D16's own lesson: an enforcement point you never execute is a
wish with a citation attached). The check would be *"is this English sentence true of a sibling
repo's API"*, which is undecidable, and a gate that cannot be written is worse than one that is
merely unwritten — D14's declared-limit precedent. Recorded as a review question instead, alongside
D16's other three: **what else in this tree says the thing I just disproved?**

---

## AP-52 — a dated, cited, correct-looking diagnosis that named the wrong seat, and nothing re-asks

**2026-09-16, nine days old, and it was found by asking a question nobody had asked of it.**

`extension-contracts/history/EXTENSION.toml`'s `HIST-R4` gap row read, from 2026-09-07:

> **This check is FAILING on `typescript` and `python` as of 2026-09-07T17:41 and the failure is
> ours**, introduced by the §9.1 execution-context work earlier the same day.

Every feature of a good record: a timestamp to the minute, the ports, the cause, a pointer to the
handoff. **Both halves were wrong.**

1. **It fails on `rust` too** — measured, all three `composed-history-1.json` reports, identical
   shape. The row was written before `rust` could host the handler face at all, and nothing re-read
   it after keystone's H1 landed and that port started scoring.
2. **The failure is not ours.** `EXTENSION-HISTORY` §2.1 says, in terms: *"The history extension
   records this value without interpretation — **it does not select between caller capability and
   handler grant. The handler that performed the write is responsible for providing the correct
   authorizing capability in its execution context.**"* Our `build_context` selects, on all three
   ports, because the peer's emit context carries the two operands and not §2.1's `capability` —
   dropped as *"redundant with callerCapability / handlerGrant"*, which it is not. Routed as `K-25`.

**Why nine days.** A row saying *the failure is ours* reads as **closed analysis and open work**.
Nobody re-derives a diagnosis that already blames the reader; the next session's question is *"have
we fixed it yet"*, never *"is it ours?"* — and the first question has an obvious answer that keeps
the row exactly where it is. **`D22` is the mirror of this and was earned on the same mistake
pointing the other way**: a claim about another seat's surface is checked against our tree first,
because *"their tool cannot see X"* is usually *"we did not ask it to"*. This is the same failure
with the arrow reversed, and it is the more expensive direction — **a fact misfiled as ours is a
fact nobody routes**, and it sat in the one place a reader would take as authoritative about who
owns it.

**And it was compounding.** The same row's cost estimate fed the ledger's ranking, and two handoffs
in a row closed with *"the first ledger item that moves a conformance figure is `W-2`/`W-3`"* —
also never measured, also false (the `content` category asserts no ingest error code at all;
`grep` over `entity-core-go`'s `content.go` returns nothing). **One unverified attribution and one
unverified modal claim, in the same ledger, pointing the next three sessions at work that could not
have moved a number.**

**What found it** was not a re-read. It was running the numbers the report already had and asking
*which of these can move, and whose is each one* — then reading the reference peer's source for the
one that could. `entity-core-go` does the selection **in the peer**, per write path
(`selectCapability`, `core/handler/handler.go`, read 2026-09-16), using `CheckPathPermission` — the
predicate keystone already ships as H9. Four commands and one file read, against a row that had
been believed for nine days.

**The rule, and it is a review question because a gate cannot ask it:** *a row that says "ours"
was an attribution once, and an attribution is a claim.* Give it the treatment `D22` gives the
other direction — **before the next session spends a day on it, re-ask who owns it, and cite the
clause that assigns the responsibility.** The cheapest trigger: **when a FAIL persists across a
substrate change** — a new port scoring, a peer capability landing — the attribution is stale by
default, because it was made about a different set of ports.

---

## AP-53 — the gate is scoped to the declaration, so an undeclared document is outside every gate that reads it

**2026-09-17, release prep.** Found by running the release pipeline's own filter against this tree
for the first time, not by reading anything.

**What happened.** `CANONICAL-DOCS.toml` declared **three** documents. It is not a table of
contents — it is a **keep-list**: `canon-filter` drops every root-level and `docs/**` markdown file
not named in it. Measured against a materialized tree, the cut would have deleted **104 files**,
including `AGENTS.md`, `AGENTS-STANDARD.md`, `METHODOLOGY.md`, `CLAUDE.md`, the anti-pattern
catalog, and six of the seven DESIGN documents — every one of which the rest of the fleet
publishes. Sixteen of twenty-two sibling repos declare the four root guidance files; we declared
none of them.

**That half is an omission and is not the interesting half.** The interesting half is what happened
when the omission was fixed:

| | declared docs | short-SHA citations the pin gate considered | unreachable |
|---|---|---|---|
| before | 3 | 1 | 1 |
| after | 23 | 31 | 31 |

**`spec pins` is scoped to the keep-list, because the keep-list IS the published surface** — which
is correct, and which means **a document that is not declared is outside the gate that checks
published documents.** Thirty of those thirty-one citations had been unresolvable for a public
reader since the day they were written. Nothing was broken by declaring them; declaring them is
what made them *visible*. The gate was not weaker than we thought — its **corpus** was.

**This is D16's arc arriving at the release boundary**, and it is the eleventh instance of the same
sentence. The first six were *nothing watches this*; the seventh was *something watches this, in a
tree we never run*; the eighth was *the spec snapshot every gate cites and none opens*; the ninth
was *a gate's own configuration*; the tenth was *a gate's own prose*. This one is: **a gate whose
corpus is a declaration measures exactly what you declared, and says nothing about what you
didn't** — and it reports that silence as a clean verdict, because one unreachable citation over
three documents and zero over twenty-three read identically in the summary line.

**And the direction is D14's expensive one.** A short keep-list makes the pin report *cleaner*,
not dirtier. Every number the gate printed got better the less we published, and nothing anywhere
asks whether a corpus should be bigger.

**The rule:** when a gate's corpus is defined by a declaration you maintain, **the first question
is not "does it pass" — it is "what is in the corpus, and what is the corpus missing?"** Print the
corpus size beside the verdict. `spec pins` does exactly this (`23 declared doc(s), 23 scanned`),
and that line is the only reason the change was measurable rather than asserted.

**A second finding, recorded and not yet promoted.** `canon-filter` is path-scoped to root `*.md`
and `docs/**`. This repo's layout is **target-major** — durable prose lives beside the code it
describes, under `gates/`, `extension-contracts/`, `languages/` and `shared/`. Fourteen `.md` files
there are outside the filter entirely and publish **with no gate on them at all**, carrying 34
SHA-like tokens and 76 internal ids. That is not a defect in the filter; it is an assumption in the
filter (docs live under `docs/`) meeting a layout that does not hold it. One incident, tracked as
`W-28`, and the local half is fixed before the observation is routed.

> ⚠ **`W-28` CLOSED 2026-09-17, AND THE ASSUMPTION WAS THE OTHER WAY ROUND.** The paragraph above
> reads as *the filter's scope is too narrow, so those 14 slip out of the keep-list*. Measured:
> `canon-filter`'s `underDocRoot` is `strings.HasPrefix(rel, r)` — **anchored at the start of the
> path** — so `gates/` is not a doc root and `status/` matches only a path that *begins* `status/`.
> Those 14 were never **eligible to be dropped**, which is the opposite failure and the worse one.
>
> **Undeclared did not mean withheld. It meant published, and outside every gate that reads the
> declaration** — the same sentence as AP-53's, with the sign flipped. A keep-list is feared for
> deleting things, and deletion at least shows up in a diff.
>
> **And no declaration fixes it.** The obvious one was tried first: `[[area]] path = "…/status",
> kind = "status", publishes = false`, which [ADR-0021] added for exactly this. It changed nothing.
> **`[[area]]` is read by `conform-audit`; `canon-filter` has its own manifest loader and does not
> read it** — so the two halves of one standard disagree about what a directory is, and only one of
> them decides what ships. The four dated snapshots were MOVED; the ten durable files were
> DECLARED; the observation was routed.

---

## AP-54 — the manifest grew two new tables, and the tool that read it with a regex could not tell them apart

**2026-09-17, release prep.** Found by running `spec pins --gate` immediately after declaring
`[[area]]` and `[[living]]` for the first time — the run got dramatically *worse*, which is the
only reason anyone looked.

**What happened.** [ADR-0021] added two tables to `CANONICAL-DOCS.toml` on 2026-09-17. Both carry a
`path` key and **both mean the opposite of "publish this"**: `[[area]]` says what a directory *is*,
and `[[living]] internal = true` says a doc is durable and must **never** publish.

`entity-system-arch-tools`' `spec-tool/pins.py` read the manifest with **a whole-file regex** —
`(?:path|file)\s*=\s*"([^"]+)"` — which was exactly correct while `[[doc]]` and `[[keep_tree]]`
were the only tables carrying that key, and which has no idea what table a key sits in. Declaring
`[[area]] path = "docs/outbox"` therefore added our entire routing corpus to the published surface
as far as that gate was concerned:

| | declared | scanned | considered | unreachable |
|---|---|---|---|---|
| with the regex | 86 | 86 | 72 | **72** |
| with a real parse | 39 | 39 | 8 | 8 |

**Sixty-plus of those findings were routing packets**, where citing a `dev` SHA is not merely
permitted but correct ([ADR-0012] Am. 1: *in an internal doc, cite SHAs freely*).

**The mechanism is D16's, and the shape is new: a tool's INPUT FORMAT grew, and nothing told the
tool.** Every previous instance asked *what reads this artifact*. This one is the complement — **the
reader was fine and the artifact changed under it**, and because the parse was a regex rather than a
parse, the new tables were not unreadable, they were **silently misread as their own opposite.** A
stricter reader would have failed loudly on an unknown table and been fixed in a minute.

**And the direction is the expensive one.** Not a false green — a wall of **false reds**, in a
corpus the reader was right to be surprised by. The locally-reasonable response to a gate that
reports sixty unfixable findings is to stop running it, and a gate nobody runs is the state AP-4
exists to prevent.

**Fixed in `arch-tools` the same session, not routed** — same team, and `AGENTS.md` says a gate
defect there is a same-session fix. `manifest_paths()` parses with `tomllib` and reads only
`[[doc]]` and `[[keep_tree]]`; the regex survives as the fallback for a manifest that **does not
decode**, because over-reading the scope is a false red and losing it entirely is a gate reporting
clean over nothing.

**Its own test fixtures were the other half of the incident, and that is the part to remember.**
They wrote bare top-level `path = "D.md"` keys, and the `keep_tree` fixture wrote `path = …` twice
— **which is not valid TOML at all.** It passed for months because the loader was a regex that
could not tell a table from a duplicate key. **A corpus that does not have the shape of the real
input tests the reader you have, not the reader you need** (D15 clause 2: a corpus assertion names
the PROPERTY the input must have). Rewritten in the real shape, that fixture now asserts the thing
its own comment already described.

**The control that matters is the negative one:** the old regex is run against the same corpus and
**required to produce the defect**. Without it the new test passes just as well against a loader
that scans nothing at all — which is the failure the whole fix is about.
