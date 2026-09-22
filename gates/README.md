# `gates/` — the axis table

**Every gate this repo runs is listed here with the authority its checks derive from.** A gate that
cannot name an authority is not conformance and MUST NOT be reported as though it were.

This rule is not ours. `entity-core-keystone` ratified it 2026-09-03 on a measured incident, and it is
the single most useful thing to inherit from that repo: **of their four verification axes, the only
one with no external authority — 17 of 18 hand-written assertions with no oracle behind them — is the
only one whose checks went stale**, drifting against the code they existed to check while every peer
stayed `756 · 0F`. An assertion with an oracle behind it moves when the oracle is re-pinned. An
assertion we wrote ourselves has nothing watching it.

**So: before authoring a check here, look for the instrument that already drives that surface.**

## The axes

| Axis | Authority | Instrument | Cohort runner | State |
|---|---|---|---|---|
| **`extension-conformance`** | **`entity-core-go`'s `validate-peer`** — the oracle, because it is not the thing under test. The 52 extension categories | `validate-peer -category <ext>` against a running composed peer | owed | not yet run |
| **`core-regression`** | same oracle, `--profile core` — keystone's 16 | `validate-peer --profile core`, re-run after installing | owed | not yet run |
| **`host-seam`** | `GUIDE-CONFORMANCE` §7d (arch, proposed) + the keystone peer host contract **H1–H7** | `languages/<t>/gates/host-seam/run` — one uniform entry point per arm | `make probe`, a `wildcard` over every target that has an arm | **1 peer measured, both probes; H1/H2/H6/H7 green there, 45 `unknown`** |
| **`sdk-surface`** | **OURS, and deliberately so.** arch does not mandate the SDK surface and that is correct — conformance lives on the wire. But we generate N ports of one extension and want them to be the same extension | `tools/sdk-parity.py` against `EXTENSION.toml [sdk_surface]` | n/a — per extension, language-neutral | **built 2026-09-06, in `make check`.** First run: 24 required · 9 substrate · **18 drift** · 0 undeclared |
| **`chunking-parity`** | `EXTENSION-CONTENT` §3.7 — §3.2/§3.6 are **Conformance** algorithms. **Nothing upstream measures it**: no oracle check chunks anything (`ed9b547`), and §3.6.5's vectors do not exist yet | one corpus → `languages/<t>/gates/chunking-parity/run` → the neutral `gates/chunking-parity/compare.py` | `make parity`, a `wildcard` over every arm; the count is echoed before the run | **built 2026-09-06.** 3 ports agree on all 6 fields |
| **`drivers`** | **OURS, and it is a LINT rather than a proof** — see below. D17: a driver literal that differs across targets is an undeclared profile field | `tools/check-drivers.py` | `make drivers`, in `make check` | **built 2026-09-06.** Both controls + refusal executed; its own first draft was AP-8 and could not go red |
| **`structure`** | **OURS.** The mirror rule (`DESIGN-THE-SYSTEM-STRUCTURE` §1.2): a per-target subtree may only hold units the neutral half declares. No upstream authority and none possible — nothing outside this repo has this layout | `tools/check-structure.py` | `make structure`, in `make check` | **built 2026-09-06.** 3 targets, 12 units. Both controls + the vacuity refusal executed |
| **`error-codes`** | **OURS, and the axis that LOOKED covered.** The `system/content` handler puts **7** distinct codes on the wire and the oracle's `content` category asserts **2** of them (`get_path_required`, `ingest_path_required`). Nothing anywhere checks the rest. D16's third instance | `tools/check-error-codes.py` against `EXTENSION.toml [error_surface]` | `make error-codes`, in `make check`; `make error-codes-control` runs D15's planted-code control | **built 2026-09-06 at the v3.7 re-pin**, which is the event that produced the failure it catches (AP-11). First run: 4 `spec` · 2 `core` · **1 `unresolved`** (`path_required`, routed) · 0 undeclared |
| **`type-parity`** | **OURS, and the gap is measured rather than assumed.** The oracle spends six `history` checks and seven `content` checks on `client.TreeGet(path)` — it asserts the type path **RESOLVES** and never reads what is at it. Routed as **G-3** (`ROUTING-2026-09-07-core-go-*`); the consistency half is ours (D16) | each arm's `<ext>_type_entities()` through the packaging boundary → the neutral `gates/type-parity/compare.py`. **Two independent measurements**: the peer's own content hash, and our normalisation of the field map | `make type-parity`, a double `wildcard` over arms × `extension-contracts/*`; both counts echoed before each verdict | **built 2026-09-07.** HISTORY: 3 ports agree on all 6. CONTENT: 2 ports agree on all 7, `typescript` **`unknown`** (exit 3 — its stage cannot be rebuilt while keystone is mid-edit on the peer). Negative control executed |
| **`glue`** | **OURS, and the only axis here whose authority is an OPERATOR REQUIREMENT rather than an incident** — *"the glue code should be pretty stable; we don't want big if blocks of oh, if it's this container and this extension."* D20 | `tools/check-glue.py` — identity leakage, not mass: `make scale` cannot see a 46-way branch because it is still one file in the `neutral` column | `make glue`, in `make check`; `make glue-control` runs both planted directions | **built 2026-09-07.** First run found `tools/sdk-parity.py` holding three per-target extractors behind a `{target: fn}` dispatch. Factored; output verified identical. Per-target→extension is a printed CENSUS, not a verdict — see D20 |
| **`req-coverage`** | **the SPEC's own conformance section** — `EXTENSION-HISTORY` §9.1, `EXTENSION-CONTENT` §11.1–§11.4. The only axis here whose authority is the requirement inventory itself rather than a check somebody wrote | `tools/req-coverage.py` — the spec's rows × the oracle's executed check set, joined through `EXTENSION.toml [conformance]` | `make req-coverage`, in `make check`; `make req-coverage-control` runs the 15 planted-defect and refusal controls | **built 2026-09-07.** 38 rows, 24 binding: **0 fully oracle-measured · 11 partial · 2 ours · 11 nothing.** Its first real run failed on a §11.4 row missed while transcribing the inventory by hand |
| **`ext-checks`** | **OURS, authored from the SPEC** — Kind C. `EXTENSION-CONTENT` §5.2/§6.2/§6.3, `EXTENSION-HISTORY` §3.2 and §6.2's two REQUIRED vectors, each a MUST `req-coverage` reports as measured by nothing in a 764-check corpus. **Never a conformance verdict** | definitions are language-neutral TOML under `extension-contracts/<ext>/checks/`, validated once and emitted as JSON; `languages/<t>/gates/ext-checks/run` is a transport binding that names no extension; `gates/ext-checks/compare.py` decides | `make ext-checks`, a `wildcard` over arms × BOTH ARMS, with `--expect-arms` so a dead arm REFUSES; `make ext-checks-control` | **built 2026-09-07.** 5 checks × 2 arms (`python`, `typescript`), **10 admitted** — composed pass, bare fail. **`rust` is now worth an arm**: the two §6.2 checks drive the emit-consumer face, and the gate says so itself |
| **`isolation`** | **ours, and that is the warning** — see below | owed | owed | unbuilt |
| **`composition-ordering`** | `SYSTEM-COMPOSITION` §2.2 / §2.10 — normative, but **no oracle category tests consumer ordering** (68 of them, none) | **routed to `entity-core-go`, not authored here** | n/a | routed |

## What KIND each of these is, and what it may conclude

**Adopted, not invented.** `entity-core-keystone` ratified `docs/VERIFICATION-ARCHITECTURE.md` on
2026-09-07 after a standalone probe drove implementation across 46 peers while belonging to no
declared category, no axis and no README. Its rule is the one worth having: **a verification
artifact declares its kind before it is written, and its kind decides what it may conclude.**
Three kinds — **A probe** (censuses a cohort, produces a finding, never gates, expires when the
oracle ships a vector on its surface) · **B transcription** (one pinned reading of a normative
rule so that fixing N ports yields one reading instead of N) · **C independent check** (authored
from the spec at the oracle's own target; a second *measurement*, never a second *authority*).

The operator's ruling there is a standing condition, and it binds identically here: **an official
green requires the suite we do not author.** Nothing in this directory is a conformance verdict.

**Two of our axes do not fit those three, and naming them is this repo's contribution to that
standard rather than a local exception:**

| Kind | What it concludes | What it may NOT do | Here |
|---|---|---|---|
| **A · probe** | a finding about a cohort, with per-peer evidence | gate; enter a published number | `host-seam` |
| **B · transcription** | that a port agrees with one pinned reading | that the reading is right | — none yet |
| **C · independent check** | that our ports satisfy our reading of the spec | override the oracle; be published | `ext-checks` — 5 authored, on four MUSTs nothing upstream reaches |
| **D · cross-port coherence** | that N of **our own** ports agree with each other | **anything about correctness** — N agreeing is N agreeing (L18) | `chunking-parity` · `type-parity` · `sdk-parity` |
| **E · instrument coverage** | what the measuring apparatus does and does not reach | that an unmeasured requirement is unmet | `req-coverage` |

**The second arm corrected the FORMAT, not the arm, which is this repo's pattern arriving on
schedule.** `ext-checks` was designed at one target and three of its decisions were wrong in
ways only a second language could show: the definitions were TOML that `node` cannot parse
offline (so the neutral half now validates once and emits JSON, and the arms consume one
artifact instead of each re-deriving the corpus); the URI is a bare pattern on one peer's
client and a full `entity://<peer>/…` on the other (so the definition names the PATTERN and
each arm renders — D17's procedure/value split); and an entity embedded in another entity's
data must travel in its `{type, data, content_hash}` wire form, which **both** arms got wrong
on their first run, in different languages, which is what makes it a property of the format
rather than one arm's slip. *The third port changed the model, not the column* — same
sentence, second axis.

**Kind C carries the heaviest gate obligation here, not the lightest**, and the rule that
discharges it is the arm rule: **an authored check is admitted only once it has been seen
producing a DIFFERENT answer against a peer with the extension not installed.** That is not a
style preference. Four of the thirteen checks in the oracle's own `content` category pass in the
bare arm — they measure `entity-core-go`'s in-process library while `summary.self_checks` reads
`0` (AP-19) — and a check that cannot tell those apart is worse than a missing one, because a
vacuous check occupies the `[conformance]` row that would otherwise honestly read `none`.
`gates/ext-checks/compare.py` enforces it; `EXTENSION.toml [conformance]` is where the claim
lands; and the three constraints that keep Kind C from becoming a second authority are keystone's
and are adopted verbatim: authored from the SPEC and never from the oracle's source, the oracle is
the measurement wherever it has a vector, and divergence is ROUTED rather than carried privately.

**D is the one keystone's taxonomy has no room for, and the gap is real rather than a naming
quibble.** Their Kind A explicitly may not gate; ours *do* gate, and correctly — because what
they gate is **us**, not a peer, and their authority is internal consistency rather than a
normative target. A cross-port comparison that failed to gate would be a report nobody reads, and
one that claimed conformance would be L18 in a costume. The distinction that makes it safe is the
subject: **a coherence gate's red means our ports disagree, and never means anyone is wrong.**

**E is stranger and is worth stating out loud: it measures the instrument, not the subject.**
`req-coverage`'s output is a fact about `validate-peer`'s reach, and its most dangerous possible
misreading is *"11 binding requirements unmeasured"* → *"11 requirements unmet."* Several of those
rows have no wire form at all. The number is an assignment of work between three seats, not a
score.

**The lint axes — `structure` `drivers` `error-codes` `citations` `glue` `scale`** — are none of
the five. They check *this tree's* declarations against *this tree's* rules and conclude nothing
about any implementation. Filed here so that the absence of a kind is deliberate rather than an
omission.

## The three entries that need explaining

**`sdk-surface` is ours and it arrived two ports late, which is D16.** The rule at the top of
this file — *the axis with no external authority is the one whose checks go stale* — was
written here, applied to `isolation`, and then **not applied to the SDK face**. Three ports
shipped before anything looked, and 18 undeclared differences had accumulated. No existing
instrument could have caught them: each port passes its own suite, the oracle is a wire client
that never sees an in-process surface, and the host-seam probes measure the peer rather than
us. `DESIGN-THE-SDK-LAYER.md` §1.1a's *"the extension is the instrument"* is true about
**conformance** and we let it stand in for **consistency**; the handler's gated path does run
through the SDK face, and that says nothing about whether three ports expose the same names.
**D16 is the rule that earns: an axis with no upstream authority gets its gate at the SECOND
implementation, not when someone notices.**

Its `drift` class is not a blessing. It ships green with all 18 named and dated, and
`--strict-drift` turns every entry into an error the moment they are resolved — a gate that
ships red gets disabled (AP-4), and one that ships green by blessing everything measures
nothing.

**`chunking-parity` is the one axis here whose authority is upstream but whose instrument
does not exist upstream.** §3.7 makes §3.2/§3.6 Conformance algorithms and a divergence
between two of them **does not fail loudly** — every blob still reassembles and the peers
simply stop deduplicating, with no error and no status code. Checked at `ed9b547`: not one of
the oracle's 13 `content` checks chunks anything, and §3.6.5's cross-impl vectors are named in
the spec as a Stage-4 byproduct that does not exist. So this is not a second scorer competing
with the oracle (which `composition-ordering` correctly refuses to be) — it is an instrument
for a surface the oracle does not cover at all, and its output is the shape §3.6.5 would need.
**Offered to arch as a head start, not proposed as a spec change.**

**`drivers` is a lint, and the structural fix is the real answer.** It compares shell
scripts with a regex, which is the same instrument keystone's stale axis was built from and
is not, on its own, a reason for confidence. It earns its place on two narrow grounds: it
found a real divergence on its first run, and it costs nothing. But **a gate that polices
drift between N copies of a protocol is treating the symptom.** The cure is that there is
almost nothing per-target left to drift — `tools/host-launch` is the shared protocol in one
copy and `languages/<t>/host-entry` is 10-23 lines of *which binary, which environment*. The
honest reading of this row: it is a tripwire on the residue, and if it ever starts finding
things regularly that means per-target code has grown back, not that the lint got better.
Measured mass and the rule it enforces: `DESIGN-THE-SYSTEM-STRUCTURE` §1.2b.

## The other two entries that need explaining

**`isolation` is ours and has no upstream instrument**, which by the rule above makes it the axis most
likely to rot. It is unavoidable: nothing outside this repo can check that a generated module stayed
inside its declared namespaces, because nothing outside this repo generates modules. Two mitigations,
both required before the axis reports anything:

1. **Its assertions derive from citable normative text, not from taste.** Every isolation check names
   the clause it enforces (`GUIDE-EXTENSION-DEVELOPMENT` §3.2/§3.3/§4.3/§4.4, `SYSTEM-COMPOSITION`
   §2.7A, `SDK-OPERATIONS` §11.6.7). A check with no citation is a preference and does not ship.
2. **It is a generation-time gate over declared data**, not a hand-written per-target assertion —
   the input is the `Owned namespaces` header every one of the 26 specs already publishes, so the
   check moves when the corpus moves. That is the closest thing to an oracle available for this
   surface.

**`composition-ordering` is deliberately not ours.** Consumer ordering is protocol-observable —
§2.2 says reversing positions 7 and 8 produces *"subscribers seeing a change without a version
entry"* — so it belongs in the oracle, and authoring it here would be building a second scorer.
Routed. What we do own is **refusing an invalid composition at generation time** (§2.10: *"the peer
builder MUST reject the configuration with an error at build time"*), which is a different obligation
and is the loader's, not a gate's.

## Rules for anything added here

Inherited from keystone's ratchet, each earned on one of their measured incidents:

- **Name the axis, its authority, and its cohort runner in this table, or it does not exist.** An axis
  with a per-target harness and no cohort runner is one nobody is measuring.
- **No per-target scripts.** One runner with the matrix as data. 31 of keystone's peers carry a
  `run-origination-core.sh` and 15 do not, for no reason anyone declared — and the whole axis turned
  out to be one oracle flag nobody had passed. *A separate harness that exists because a flag was
  never passed is not an axis, it is a workaround with a directory.*
- **And the matrix is read off the tree, never maintained as a list** (2026-09-06). We broke the rule
  above while stating it: `make probe` was three hand-written invocations with **three different
  calling conventions** — node ran a script, python needed a `cd` plus a `--peer-root`, rust needed
  `sh` and a wrapper — and `make parity` was three more, plus a hardcoded `COMPOSITIONS ?= ts-content
  py-content rs-content`. At three targets that reads as configuration. At forty it is keystone's
  31-and-15 exactly. **Every gate now has one uniform entry point per arm** —
  `languages/<target>/gates/<gate>/run` — the target-specific incantation lives inside the arm where
  it is one target's business, and every list in the Makefile is a `wildcard` over the tree. A new
  target is a directory, never a Makefile edit. `tools/check-structure.py` fails an arm with no
  `run`, because an arm the cohort runner cannot call is an arm nobody measures **and its absence is
  silent**.
- **Delete derived state before measuring.** A gate that assumes a `node_modules/`, a `dist/`, or a
  `target/` is a gate on somebody's machine. Keystone found a peer whose gate died `rc=127` from
  clean while reporting green for weeks.
- **A gate that imports a build artifact must check the artifact's age, and report `unknown` rather
  than a verdict when it is stale.** Second shape of the row above and worth its own line, because it
  fails in the opposite direction: not a gate that dies, a gate that **answers confidently about code
  nobody built**. Keystone's own instrument reported H7 unsatisfied against source that satisfied it,
  after a planted-defect run left a mutated `dist/` behind. Ours now compare `src/` and `dist/` mtimes
  and exit 2. **Exit 2 is not a verdict.**
- **Resolve the thing under test the way a consumer resolves it.** Read the manifest
  (`package.json` `exports`, `Cargo.toml`, `pyproject.toml`), do not guess a path into the build
  output. A path guess reaches around the packaging boundary, which is the boundary D13 is about, and
  turns an H4 failure into a passing probe.
- **Both controls or it measures nothing.** The positive must carry a witness the wrong
  implementation cannot produce; the negative must go RED.
- **And a REFUSAL as well as a control** (D15, sharpened 2026-09-06). A control proves the
  instrument *can* go red on a planted defect. A refusal fires when it **cannot answer at
  all** — a parse yielding zero units, a comparison with fewer arms than the verdict needs, a
  missing input it would otherwise skip. That is a different failure and it is the one that
  presents as success. Five instruments written in this repo, five with a defect found by
  running them; **the two that caught themselves are the two that shipped with a refusal.**
- **A normaliser preserves every distinction its sources can express** (AP-8). `sdk-parity`
  compares `(kind, snake_case)` because lowercasing collapsed `Blob` and `BLOB` into one key
  and reported agreement across three ports that was not there. A lossy key moves the answer
  in the *agreeing* direction, and agreement is what gets published.
- **An instrument does not read a quantity its own execution writes** (D19, 2026-09-07). The
  counter-snapshot rule below is one shape of this; the second shape is a **file mtime**.
  `gates/type-parity`'s typescript arm must run from inside the stage (ESM resolves a bare
  specifier relative to the importing file), so it copies its probe in — and that copy is then
  the newest file in the stage, which is exactly what `tools/gate-stage`'s staleness check
  reads. Its first run passed a staleness check over a six-hour-old stage. **Anything a gate
  lands in a stage is named `gate-probe-*`**, which `tools/gate-stage` excludes and
  `tools/check-structure.py` requires. That check found a second, pre-existing instance in
  `chunking-parity` on the day it was written.
- **When the claim is that an installed thing gets consulted, "absent" is not the only alternative
  to "works."** The third state is *installed, live, and never asked*, and only a fourth control
  separates it: call the installed thing **directly** and require it to answer. Earned on
  `probe-entity-native.mjs`, whose first iteration counted that direct call as evidence of the
  delegation it was supposed to disprove — **snapshot the counter before the control that
  contaminates it.**
- **A single sample is not a rate.** Do not bank a number that moved the right way once.
- **A skip is a failure.** Report it with its cause named, never as a smaller denominator.
