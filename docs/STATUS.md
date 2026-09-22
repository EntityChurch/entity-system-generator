# Status

The rolling log. One file, not dated.

---

## Where this is

**Three standard extensions are implemented across three languages and installed onto generated
peers: nine working compositions.** `EXTENSION-CONTENT`, `EXTENSION-HISTORY` and
`EXTENSION-COMPUTE`, each in `typescript`, `python` and `rust`. Every one builds, passes its own
unit suite, and is measured against a conformance oracle this project does not own and cannot
modify.

The three were chosen to test the generation model against different shapes rather than to cover
the corpus: **a request handler** (content — ingest, retrieve, reassemble), **an event recorder**
(history — an append-only audit chain driven by tree writes), and **an expression interpreter**
(compute — the largest extension in the corpus, and the first whose obligations are an evaluation
algorithm rather than a request/response surface).

That is three extensions of twenty-six, and three languages of forty-six.

## What is measured

Each composition is measured twice against the same peer: once **bare**, with no extension
installed, and once **composed**. The difference is the extension's contribution; the bare arm
exists because a check named after a requirement is not the same thing as a check that measures
it, and several do pass against a peer that has no extension at all.

Figures below are read from each composition's blessed baseline, which records the totals, the
per-severity breakdown and both arms. **A skip counts as a failure, not as partial credit.**

| extension | oracle category | `typescript` | `python` | `rust` | bare arm |
|---|---|---|---|---|---|
| CONTENT | `content` (13) | 12 P · 1 S | 12 P · 1 S | 12 P · 1 S | 4 P · 5 F · 4 S |
| HISTORY | `history` (34) | 32 P · 1 W · 1 F | 32 P · 1 W · 1 F | 32 P · 1 W · 1 F | 1 P · 29 F · 4 S |
| COMPUTE | `compute` (128) | 125 P · 3 F | 125 P · 3 F | **128 P** | 0 P · 128 F |
| COMPUTE | `entity_native` (13) | 9 P · 4 F | 9 P · 4 F | 10 P · 3 F | 3–4 P |

`P` pass · `W` warn · `F` fail · `S` skip. Two rounds per measurement; a difference is attributed
to the composition only when it is stable across rounds.

**The core protocol profile is re-run in both arms on every measurement** — around 780 checks —
because the failure mode that matters here is not *the extension is incomplete*, it is *the
extension broke the peer underneath it*. No composition regresses the core profile.

### What these numbers are numbers about

**A category score measures what the oracle's access path can reach on that peer.** On most
targets that sentence and *"what the extension does"* are the same one, which is why the
distinction is easy to miss — but they come apart, and when they do this project reports them
apart rather than averaging them.

The clearest case is `rust` × HISTORY. The extension's **write** face installs and runs: it
records every tree write the peer accepts, correctly, verified over the wire. Its **read** face
cannot be installed on that peer, and the read face is the only route by which any external
instrument can see what the write face recorded. The peer accumulates a correct, content-addressed
audit chain that the conformance suite cannot observe. The score is a fact about the access path.

Similarly, the three `compute` checks outstanding on `typescript` and `python` need a re-entrant
dispatch to a local handler that those peers do not expose. That is a property of the peer, and it
is filed with the peer generator rather than carried as a defect here.

### The one thing a score never covers

**A capability that cannot be installed hides every defect behind it.** When a peer cannot host
one of an extension's faces, nothing can test the code for that face — no unit test reaches it, no
oracle check scores it, and the honest report *"this peer does not host X"* reads as an account of
the gap when it is really an absence of measurement.

This is not hypothetical: when one peer gained an evaluator seam it had previously lacked,
installing against it immediately exposed two real defects in this project's own implementation
that had been unreachable, and therefore invisible, for nine days. The number moved from 3 to 9 of
13, and neither defect could have been found by reading.

## How correctness is held

- **The contract is language-neutral and the ports are checked against it.** One
  `EXTENSION.toml` per extension holds the requirement map, the public SDK surface, every wire
  error code with the authority that defines it, the specification's own enumerations, and the
  substrate differences that turned out to be real. A port that drifts from it fails a gate.
- **Specification snapshots are pinned by digest** and copied in, never edited. An extension names
  the snapshot it was written against, so an upstream revision becomes a re-pin with a number on
  it rather than a silent change of meaning. Currently `EXTENSION-CONTENT` v3.7,
  `EXTENSION-HISTORY` v1.10, `EXTENSION-COMPUTE` v3.29.
- **Every gate ships an executed control and an explicit refusal.** A control proves the gate can
  produce the opposite verdict; a refusal fires when it cannot measure anything at all. The second
  is the one that matters, because an instrument that can only say PASS or FAIL has no way to
  report the state it will actually be in the day it breaks — and in this project's experience
  most instrument defects present as a *green* result, not a red one.
- **Baselines name obligations, not test names.** A conformance suite is free to rename its
  checks; a baseline pinned to those names cannot tell a rename from a lost capability and reports
  the second. Each measurement is keyed to the requirement the suite itself cites.

## What is open

- **Three extensions of twenty-six, three languages of forty-six.** The remaining corpus is the
  bulk of the work.
- **Published figures are not yet dual-anchored.** A conformance number should be reproducible
  from the oracle build *and* a digest over the exact set of assertions in the run. Both are
  recorded today, but by hand rather than emitted, and a dual anchor that is dual because someone
  typed the second half is one anchor and a habit. This is the next correctness item on the
  measurement side.
- **Several extension requirements have no wire form**, so no network-based suite can reach them
  whatever it asserts. Those are measured by this project's own tests where possible and reported
  as unmeasured where not. The requirement map states which is which per row rather than reporting
  a single coverage percentage.
- **Some specification questions are open upstream.** Where generating an implementation forced a
  gap or a contradiction in a spec to a single value, that is routed to the specification owner
  rather than settled locally — a generator that quietly decides what a spec left open produces
  N copies of one reading and calls it agreement. Open items are listed in
  [`SPEC-AMBIGUITIES.md`](SPEC-AMBIGUITIES.md).

## What this project does not claim

**Ports agreeing with each other is not independent convergence.** Three implementations written
by one team from one reading of one pinned snapshot will agree, and their agreement is evidence
about the team's reading rather than about the specification. Where cross-port agreement is cited
here it is narrow and mechanical — for example, type entities compared by content hash against a
third codebase's independent transcription, which is a comparison against something this project
did not write.

**Conformance-green is not correct if the test asserts the wrong thing.** The oracle is the
oracle because it is not the thing under test; that is the whole of its authority, and it does not
extend to requirements it has no vector for.
