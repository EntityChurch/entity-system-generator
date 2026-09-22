# The target-major tree, and what may name what

<!-- Moved out of AGENTS.md on 2026-09-17 under the 2026-09 doc standard. The text is
     VERBATIM: this was a move, not a rewrite. Superseded, not appended — when one of
     these stops being true, rewrite the entry; git holds the history. -->

**Open this before editing anything under `languages/<target>/`, and before putting a literal in a driver or a gate arm.**

It holds **D17** (a per-target fact lives in the profile; a literal in a driver is drift) and **D20** (the glue does not enumerate its members).

The review question both come down to: when reading a difference between two per-target files, never ask *is this difference reasonable* — ask **is this a procedure or a value.**

---

### D17 — a per-target fact lives in the profile; a literal in a driver is drift

**Ratified 2026-09-06 on two incidents in two shapes, both ours, both found by *comparing the
drivers to each other* rather than by reading any one of them** (`docs/ANTI-PATTERNS.md` **AP-10**).

`languages/<target>/{build,test,host-entry}` is one copy per target and that is deliberate — a
target's build is idiomatic to its ecosystem, and the alternative is a build driver in the
(extension × target) cell, which is 1,196 copies. But **N copies of one protocol is the shape
keystone paid for**, and the distinction the design never made explicit is:

| | | |
|---|---|---|
| a **procedure** that differs between drivers | the design working | `tsc` × 2 vs `cargo` × 2 vs a stage-and-import |
| a **value** that differs between drivers | **a fact that escaped the schema** | the readiness budget; the rust edition |

**The two shapes are mirror images, which is why this is a discipline and not a catalog entry:**

- **Executed, undeclared.** The readiness wait was `100` on the port written first and `150` on the
  two written after, with no comment anywhere. Port 1 set it → port 2 raised it → port 3 copied
  port 2 → nobody went back. **A correction made during port N lands in ports N…last and never in
  ports 1…N-1**, because port N+1 is written by copying port N. The FIRST port is systematically
  the stalest, and it is the one every later port was validated against.
- **Declared, and separately executed.** `languages/rust/build` hardcoded `edition = "2021"` while
  the profile declared it four lines below a comment explaining that an edition skew *"changes name
  resolution and closure capture"*. The fact whose purpose is *do not skew* was in two places with
  nothing comparing them. Same mechanism as AP-9's toolchain image, one file over.

**Enforcement point** — `tools/check-drivers.py`, in `make check`. It extracts comparisons and
assignments from every `languages/*/{build,test,host-entry}`; a value that differs across targets
and is not declared in that target's `profile.toml` is a failure. New per-target facts are added to
`REQUIRED_PROFILE_FIELDS` in `tools/compose.py` so the plan carries them and the driver reads one
copy. **The corollary for review: when reading a diff between two drivers, the question is never
"is this difference reasonable" — it is "is this a procedure or a value".**

**The third driver is `host-entry`, not `host-launch`, and getting that wrong here for a day is
D17's own failure in D17's own text.** The 2026-09-06 mass audit factored the launch protocol into
one shared `tools/host-launch` and left a small per-target `host-entry` hook it sources — the
`2.1 : 1` neutral-to-per-target ratio `DESIGN-THE-SYSTEM-STRUCTURE` §3 reports. **Five documents
kept the old name**, including this paragraph and `check-drivers.py`'s own docstring four lines
above the constant that spells it correctly. Found 2026-09-07 by `tools/check-citations.py` on its
first run, not by anyone reading any of the five.

#### D17's gate sees a literal that DIFFERS across targets, never one that is the SAME in all of them

**Recorded 2026-09-12 as a declared limit, on an incident the gate could not have caught** (AP-39,
and D16's ninth instance above). `gates/type-parity`'s three arms each carried
`COMPOSITION="${COMPOSITION:-content-history}"`. `check-drivers.py` was green throughout, and
correctly: it fails a value that **differs**, because AP-10's mechanism is *a correction lands in
ports N…last and never in 1…N-1*. An identical literal in all three is the other failure —
keystone's `N copies of one protocol` — and it has a different gate (`make scale`'s cost model,
`tools/check-glue.py`'s identity rule), neither of which fires on a six-character default inside
an otherwise per-target file.

**So the pair of gates has a seam between them, and the seam is exactly where this landed.** Stated
rather than patched, for D14's own declared-limit reason: the check would be *"is this repeated
constant the right constant"*, which is undecidable, and a gate that cannot be written is worse
than one that is merely unwritten.

**The usable rule, and it is a review question rather than a gate.** D17's corollary asks *"is this
a procedure or a value"* of a difference between two drivers. The complement: **when a per-target
file carries a value that is the same in every target, ask what it is keyed on and whether that key
is data anywhere else in the tree.** Here the (extension → composition) mapping was data in the
Makefile's wildcard and a literal in the arms, and the two disagreed silently for three days.

### D20 — the glue does not enumerate its members

**Ratified 2026-09-07 on an operator requirement plus two incidents found the same day by
the gate written for it.** This is the one discipline here that did not start as a bug: the
operator stated it as a design constraint — *"all the glue code should be pretty stable; we
don't want big if blocks of oh, if it's this container and this extension"* — and the gate
written to check it immediately found the tree already violating it in two places.

**Mass is the wrong instrument, which is why `make scale` could not see this.** A neutral
file that grows a 46-way branch is still **one file in the `neutral` column** — `×1` by
location and `O(T)` by edit cost. The cost model would call it stable while every new target
required a patch to it. So the invariant is about **identity**, not size:

| | |
|---|---|
| a **language-neutral** file names no specific **target** | enforced, FAILS |
| a **per-target** file names no specific **extension** | census, see below |
| a **per-extension** file may name every target | exempt — `[substrate]`/`[sdk_surface]` are cross-port comparison TABLES, and a comparison sharded per port stops being one |

**What it found, and it is the sharpest instance in the tree.** `tools/sdk-parity.py` — a
language-**neutral** gate — carried `{target: entry_point_filename}`, `{target: extractor_fn}`,
the three extractor functions themselves (~120 lines of per-language parsing), and a
hardcoded `("typescript","python","rust")` display order. At 46 targets that is a 46-way
dispatch over 46 hand-written functions, in the file whose whole job is to be finished.

**Both halves moved to homes existing rules already named**, which is the useful part —
this was not a new rule, it was two old ones nobody had applied here:

```
the VALUE      ->  languages/<t>/profile.toml [sdk_surface] entry_point        (D17)
the PROCEDURE  ->  languages/<t>/gates/sdk-surface/{run,extract.py}            (§1.2b)
```

The arm is a `run` emitting JSON rather than an imported function, and that is load-bearing
rather than stylistic: an imported extractor **must be Python**, which is a neutral-half
constraint reaching into a target. A `run` lets a future target read its own surface with
its own toolchain and the neutral half learns nothing. Adding a target is adding a
directory.

**Verified name-for-name identical across the move** — every name, verdict and count on both
extensions — because a refactor that quietly changes what an instrument measures is worse
than the duplication it removed (D15).

**And the honest limit, recorded rather than papered over.** The per-target → extension
direction is a **census, not a verdict**, because two things wear one shape and the gate
cannot yet tell them apart: a *dispatch table* (`{"content": …, "history": …}`, the thing
that becomes 1,196 rows) and a *probe subject* (`host-seam` installing a handler at
`system/content` — naming it is the probe's whole job). Failing both would put ~50 false
reds in front of a reader on day one, and **a false red costs the instrument** (AP-4). The
number is printed and tracked; it earns a threshold when the arms are parameterised.

**Enforcement point** — `tools/check-glue.py`, in `make check`, with an executed control in
both directions and a refusal when the identity lists are empty (an empty list makes every
file read as clean). It borrows `scale-report.py`'s `classify()` rather than re-deriving it:
its own first draft re-derived the classification, called `compositions/<c>/host.py`
per-target, and produced fourteen false reds on a file whose entire job is to name the
extensions in its composition.

#### D20's substrate finding: on an AOT target the table is unavoidable, so it must be GENERATED

Fixing the `type-parity` arms drove the census to **zero on `python`** and near-zero on
`typescript`: the `extension → (module, function)` mapping was never a decision, it is the
target's naming convention applied to a slug, so the arm **derives** it and refuses if the
derivation misses — strictly better than a table, because a table cannot notice that a cell
broke the convention.

**`rust` cannot do this and that is not a defect in the arm.** AOT linkage is resolved at
compile time; there is no `import(name)`. The dispatch must exist as source before the
binary does. So on every AOT target in the corpus the E-way table is **structural**, and the
only question is who writes it:

> **A per-extension table on an AOT target is emitted from the tree, never maintained by
> hand.** The generator that must emit it is the same one `DESIGN-THE-SYSTEM-STRUCTURE`
> already says must eventually emit `compositions/<c>/host.*` (*"hand-written in cycle 1;
> emitted later"*). **That step is now load-bearing for two consumers, not one**, and it is
> the thing standing between us and *"add this extension to all 46 peers"* being a
> one-command operation.

Recorded as the shape to build against. Not built; one substrate, and the honest scope is
that it lands with the wiring emitter rather than as a bespoke script for one gate.
