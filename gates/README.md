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
| **`host-seam`** | `GUIDE-CONFORMANCE` §7d (arch, proposed) + the keystone peer host contract **H1–H7** | `host-seam/probe-seam.mjs` (H1/H2/H6, model 2) · `host-seam/probe-entity-native.mjs` (**H7**, model 3) | owed — keystone's, `go`/`rust`/`python` first | **1 peer measured, both probes; H1/H2/H6/H7 green there, 45 `unknown`** |
| **`isolation`** | **ours, and that is the warning** — see below | owed | owed | unbuilt |
| **`composition-ordering`** | `SYSTEM-COMPOSITION` §2.2 / §2.10 — normative, but **no oracle category tests consumer ordering** (68 of them, none) | **routed to `entity-core-go`, not authored here** | n/a | routed |

## The two entries that need explaining

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
- **When the claim is that an installed thing gets consulted, "absent" is not the only alternative
  to "works."** The third state is *installed, live, and never asked*, and only a fourth control
  separates it: call the installed thing **directly** and require it to answer. Earned on
  `probe-entity-native.mjs`, whose first iteration counted that direct call as evidence of the
  delegation it was supposed to disprove — **snapshot the counter before the control that
  contaminates it.**
- **A single sample is not a rate.** Do not bank a number that moved the right way once.
- **A skip is a failure.** Report it with its cause named, never as a smaller denominator.
