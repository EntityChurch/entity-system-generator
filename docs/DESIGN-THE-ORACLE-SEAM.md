# DESIGN — the oracle seam, and what "plug-and-play" would have to mean

**Status: analysis, not a proposal we own.** Whether a dedicated conformance seat exists is the
operator's call and architecture's ruling. What is ours is the seam: this repo is the most
oracle-coupled consumer in the ecosystem, and if the oracle becomes swappable we are the tree that
pays for it. This document measures the coupling and names what a second oracle would have to
provide for the swap to be real rather than nominal.

Written 2026-09-12, after `entity-core-keystone` measured what happens when the posture changes.

---

## 1. What we are actually coupled to — measured, not asserted

```
$ python3 -c "
import tomllib,glob
t=0
for f in glob.glob('languages/*/compositions/*/SYSTEM.toml'):
    d=tomllib.load(open(f,'rb'))
    for v in d.get('gate',{}).get('baseline',{}).values():
        if isinstance(v,dict): t+=len(v.get('improved',[]))
print(t)"
344
```

**344 oracle check NAMES are pinned in this tree**, across seven compositions, as the D21 baseline
sets — every one a string that says *"this named check improved, and losing it is a failure."*
Plus **87 distinct check names** in the `[conformance].oracle` maps across three contracts
(`content` 7 · `history` 10 · `compute` 70). Plus:

| Coupling | Where | What breaks on a swap |
|---|---|---|
| **check names** (344 + 87) | `SYSTEM.toml [gate.baseline.*]`, `EXTENSION.toml [conformance]` | every D21 baseline and every coverage row |
| **category names** | `Makefile $(CATEGORIES)`, `-category <ext>` | the per-extension loop |
| **report schema** | `tools/diff-arms.py` — `checks[]` · `check` · `severity` · `status` · `message` · `timestamp` | both differentials |
| **CLI contract** | `tools/host-launch:267` — `-addr` · `-category` · `-json-out` · `-reference-peer` · `-profile core` | the launcher |
| **a go REFERENCE PEER as an oracle INPUT** | `tools/host-launch:220` — `entity-peer -open-access` | the whole `origination` category |
| **the fixture posture** | `tools/host-launch:137` — `--debug-open-grants` | see §2 |

**The reference-peer row is the one that surprises people.** `validate-peer` is not only a scorer;
for `origination/{reference_connect,reference_ready,dispatch_outbound_reentry}` it dials a
**second go peer** that we also launch. A "second oracle" that scores without supplying that input
does not replace the first one — it replaces half of it.

---

## 2. The requirement nobody has written down: **an oracle declares its fixture posture**

This is the design contribution this repo can make, and it comes from a measurement that is not
ours. `entity-core-keystone` ran go's peer through its own harness with one flag removed
(`--debug-open-grants` → the §6.9a floor default), against the pinned oracle, `-profile core`:

```
committed (--debug-open-grants):  778 · 335P/336W/  0F/107S
floor-launched (§6.9a default):   717 · 251P/342W/  6F/118S
```

**54 severities moved, every one downward** — 41 PASS→SKIP, 7 PASS→WARN, 6 PASS→FAIL. Under
[ADR-0012] a skip counts as a failure, so that is **47 failures**. Lost: all 8
`universal_address_space` checks, all 9 `core_register_*` checks (the §6.2 five-write contract,
itself a floor MUST), 5 `concurrency`, 2 `peer_canonicalization`, most of `capability`.

**Their caveat, carried verbatim because it is theirs to weaken or strengthen: one peer, one run.**
It is structural rather than timing-dependent, but it is n=1 and they want three more peers before
it leaves their tree.

We confirmed the mechanism independently in the oracle's own source, which is the part that
generalises:

```
$ grep -rliE "open.grants|open.access|debug_open" cmd/validate-peer/ cmd/internal/validate/ | wc -l
19                                               # files, entity-core-go @ c3eaa82
$ grep -rniE "SkipCheck.*(open.access|open.grants)" cmd/internal/validate/ | wc -l
13                                               # checks written to skip without the posture
```

and `universal_address_space.go` is a **core** category (`profile.go:33
catUniversalAddressSpace: true`), whose skip text reads *"connection grants do not cover … — needs
open-access or wildcard."*

**So the posture is not a launcher detail. It is an undeclared input to the check set**, spread
across nineteen files, and it decides which checks exist. Every number in
`CONFORMANCE-MATRIX.md` — 46 peers at `778 · 0F` — was produced in it, and nothing anywhere says
so.

> **An oracle that does not declare its fixture posture cannot be audited, cannot be compared to a
> second oracle, and cannot have its own coverage questioned.** This is D16's shape at ecosystem
> scale: the axis with the most upstream coverage is the one nobody asked about, *because* the
> coverage is what stops the asking.

A pluggable-oracle contract must therefore carry, per check: **the preconditions the check assumes**
— grants, identities, installed handlers — as data, not as English inside a `SkipCheck` string.

---

## 3. The corollary: key to REQUIREMENTS, not to check names

**This is the single change that makes a swap possible, and we are already half-way through it.**

Today our `[conformance]` maps say *"requirement X is covered by go check `v314_foo`."* If a second
oracle names the same assertion `compute_store_roundtrip`, all 431 of our pinned names are wrong
and every baseline goes red — which is a false red across the whole tree, and **a false red costs
the instrument** (AP-4). Nobody would migrate; they would delete the baselines.

The fix is the seam `tools/req-coverage.py` already uses. Arch's `SPECIFICATION-FORMAT` §8.5a
allocates `<PREFIX>-R<n>` once, never renumbered, contiguous from 1. So:

```
        today                          pluggable
   us  ->  go check name          us  ->  REQUIREMENT id  <-  each oracle declares
           (431 strings)                  (COMP-R7, ...)      its own check -> requirement map
```

Three consequences, and the third is the operator's actual question answered:

1. **Our tree stops naming any oracle's checks.** A baseline pins *"requirement `COMP-R7` is
   measured and passing"*, and which check established that is the oracle's business.
2. **Coverage becomes comparable.** *"Oracle A reaches 24 of 38 binding rows, oracle B reaches
   19, together 31"* is a sentence that can be written. Today it cannot be.
3. **A disagreement is localized to a requirement, which makes it adjudicable.** The operator's
   question — *"one passes, one fails: is it the spec, the implementation, or the test?"* — is
   unanswerable when the two oracles share no vocabulary, and is a well-posed question for
   architecture when both say *"we disagree about `COMP-R7`."* **Requirement-keying is what turns a
   second oracle from a source of noise into a source of findings.**

---

## 4. The cheaper mechanism, which is already ruled on and which we should price first

`GUIDE-CONFORMANCE` §373 (arch, landed):

> *"A `[cross-peer seam — MUST]` with no peer-observable surface MUST be gated by a pinned-input
> vector, in the same change that lands the MUST. … The vector is a shared row file of authored
> inputs and expected outputs that **each implementation runs in its own suite** — the crossing is
> the shared file, not a live peer."* Shape defined by `EXTENSION-ENCRYPTION` §16.6 (coverage,
> order-independence, negative control, declared exclusions).

**That is independence without a second wire oracle, and it is aimed precisely at our weakest
rows.** Our `[conformance]` map's `ours` class — COMPUTE §7 convergence, grant validity, cascade
freeze, index rebuild, subgraph-ID derivation — is *exactly* "a MUST with no peer-observable
surface." Those are the rows where the implementer writing the test is the whole problem, and a
shared authored row-file fixes it for a fraction of a new repo.

**It does not replace a second oracle** — it cannot reach anything behavioural, and it does nothing
about §2's posture problem, which is a live-peer fixture question. It is the cheap half, it is
already normative, and we have not done it.

---

## 5. What a second seat does and does not resolve

**§7.0's ruling is narrower than it is usually quoted.** It says *"`entity-core-keystone` authors
none of these … asking keystone for a vector asks the scorer to write the exam"* — and the reason
is specific: keystone **consumes** the oracle, pins it, and publishes `CONFORMANCE-MATRIX.md`. It
is a ruling about the **scorer**, not a general grant of authorship to `entity-core-go` forever.
The same table already records the defect a second author would address: the connect/auth surface
is marked **"oracle Go-coupled — §9 roadmap."**

So a dedicated conformance seat does not overturn §7.0 — **it is the shape §7.0's reasoning
points at.** But the same reasoning binds the new seat:

- **It must not also be a subject.** The moment it ships a peer, it is writing its own exam.
- **It must not be the only scorer either**, or the audit problem returns one repo over. Two
  oracles are only worth the cost if *both* run and disagreements are adjudicated by a third seat.
  That seat is architecture, and it should be designed in, not discovered.
- **And it inherits §2's obligation from birth.** A second oracle that bakes its own undeclared
  fixture posture is a second unexaminable artifact, and we will have paid for the privilege of
  having two.

**What it resolves that nothing else does:** keystone's finding is not a bug in go's peer. It is a
decision go's oracle made implicitly and no reviewer could see. *A second author who had to make
the same decision explicitly would have surfaced it.* That is the argument, it is empirical, and
it is stronger than any argument from principle.

---

## 6. What this repo owes, in order

1. **Requirement-keying** (§3). Ours alone, needs no ruling, and it is the prerequisite for every
   other item here. It also pays for itself immediately: today a go re-pin that renames a check
   silently invalidates a baseline.
2. **Pinned-input vectors** (§4) for the `ours` rows. Landed mechanism, unbuilt by us.
3. **Declare our own posture** wherever we publish a number — done for `compute`
   (`[substrate.seed_policy_surface]`), owed everywhere else.
4. **Stay out of authoring a wire oracle** until architecture answers A-23. We asked; we should
   not pre-empt the answer by building.

**And one thing we should NOT do:** migrate off `--debug-open-grants` on our own schedule. §2 is
why — the posture is load-bearing for the check set, keystone is measuring it, and moving first
would make our numbers incomparable with the matrix for no gain.
