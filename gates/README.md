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
| **`isolation`** | **ours, and that is the warning** — see below | owed | owed | unbuilt |
| **`composition-ordering`** | `SYSTEM-COMPOSITION` §2.2 / §2.10 — normative, but **no oracle category tests consumer ordering** (68 of them, none) | **routed to `entity-core-go`, not authored here** | n/a | routed |

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
- **When the claim is that an installed thing gets consulted, "absent" is not the only alternative
  to "works."** The third state is *installed, live, and never asked*, and only a fourth control
  separates it: call the installed thing **directly** and require it to answer. Earned on
  `probe-entity-native.mjs`, whose first iteration counted that direct call as evidence of the
  delegation it was supposed to disprove — **snapshot the counter before the control that
  contaminates it.**
- **A single sample is not a rate.** Do not bank a number that moved the right way once.
- **A skip is a failure.** Report it with its cause named, never as a smaller denominator.
