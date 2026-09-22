# Substrates, ports and why the tier is CORE

<!-- Moved out of AGENTS.md on 2026-09-17 under the 2026-09 doc standard. The text is
     VERBATIM: this was a move, not a rewrite. Superseded, not appended — when one of
     these stops being true, rewrite the entry; git holds the history. -->

**Open this when starting a port to a new substrate, and when deciding whether this repo's methodology tier should move.**

It is the running record of what each of the nine compositions did to the substrate model — which rows changed value, which changed KIND, and which port was the first to change nothing. The revisit criterion for the tier is stated at the end and is not met today.

---

## How we work here — tier: **CORE** *(settled at the third port, see below)*

The methodology framework is `METHODOLOGY.md` (injected, identical everywhere). This repo runs the
**Audit doctrine** and the ratchet from day one.

**Three substrates are in, and the tier is settled: CORE, deliberately, not provisionally.**
`CONTENT` × `typescript` shipped 2026-09-05, × `python` 2026-09-06, × `rust` 2026-09-06.
`extension-contracts/content/arch/AUTHORING-NOTES.md` §2 is a measured comparison across five axes now, and
§2.5 records what the third column did to the other four: **three rows inverted or gained a third
value, two were demoted from "the invasive difference" to "the common case", and one row was added
that is not a difference between languages at all.**

**The third port was the one that tested the model, and the model did not survive intact.** The
prediction was that `rust` — AOT, no post-construction install — would add a column. What it added
was a **dimension**: on that peer an extension's four faces do not get the same answer. Types and
emit install; the handler body cannot be installed at any visibility; the SDK is a library with no
gated path reaching it. A per-peer host state was never the right granularity — it is per
**(peer × face)** — and no composition where all four faces installed could have shown that.

**So CORE stays, and now for a reason rather than for caution.** Full tier rests on a substrate
model that generalises, and the honest reading of three samples is that the model is still learning
what its own rows *mean*: the §3.4 MUST turned out to be two clauses that invert between substrates,
and "registration surface: none" turned out to be two different facts wearing one word. That is a
model being corrected, not a model being confirmed. **Revisit when a port stops changing the shape
of the table** — the next candidate is a substrate with no linker at all (`wasm`, `sql`, one of the
asm peers), where "compose" may not name an operation.

**And the second extension's third port (2026-09-07) is the argument for staying, not for moving.**
`HISTORY` × all three targets completes the first batch. It did not add a column; **it added two
more rows and a new KIND of row.** The rows are `[substrate.handler_grant]` — §2.1's autonomous
`capability` is *"the handler grant"* and on one peer there is no mint and nothing to grant for —
and `[substrate.oracle_read_path]`, which is **not a limit on the extension at all**. It records
that the write face installs, the read face cannot, and every instrument that could see the
difference goes through the face that cannot. A substrate model whose row *kinds* are still being
discovered at the sixth composition is not a model that has generalised. Revisit criterion
unchanged.

**And the EIGHTH composition (2026-09-12, `python × COMPUTE`) discovered a THIRD row kind, so the
criterion is not met and CORE stands.** The first kind records what a peer CANNOT DO — a missing
seam, an unrenderable constraint, a narrower ergonomic layer. The second (`oracle_read_path`)
records a limit on what can be MEASURED rather than on the extension. The new one records what a
**RUNTIME DOES BY ITSELF**: `%` that floors where §4.1 truncates, a float `/` that raises where
IEEE returns `±Inf`, a `bool` that is an `int` subclass, a tree `put` that suppresses an identical
bind. **Nothing is missing in any of them.** The peer is not narrower and the spec is not silent;
the LANGUAGE has an opinion and §4.1 has a different one, and the row exists so the next port
does not adopt the host's answer by reflex. Seven of them are enumerated in
`[substrate.native_value_model]`, all seven pre-registered before the composed run, and all seven
cost zero checks — which is the result, not the list.

**The port also produced the first face-level asymmetry on a peer that hosts everything else.**
`rust × CONTENT` showed four faces getting different answers; there the un-installable handler
meant the extension did nothing. Here `python` hosted `types`, `handler`, `emit_consumer` and `sdk`,
did not host the fifth (`Peer.setExpressionEvaluator`, keystone's H7, present on 1 of the 46), and
**the extension worked completely and scored identically to the port that has it** — because the one
oracle check touching the entity-native path already fails on that port for the K-5 reason. A face
can be absent, correctly reported, and cost nothing; the score is still not a statement about it.

> ⚠ **THE FIFTH FACE LANDED ON `python` ON 2026-09-14, AND THE PARAGRAPH ABOVE IS KEPT IN THE PAST
> TENSE RATHER THAN REWRITTEN** — the reading it records is what the eighth composition taught, and
> the correction is worth more beside it than in place of it. Keystone's S3 bring-up shipped
> `Peer.set_expression_evaluator`; installing against it moved `entity_native` **3 → 9 of 13** and
> exposed **two defects of ours** that had been unreachable for nine days (§3.2 E1's scope never
> pre-populated, §4.1's reads never narrowed under the handler grant). That is D23's second incident
> and the one that promoted it.
>
> **And the declaration lagged the measurement by three days, in three places** — the composition's
> `[system.faces]`, the contract's `[substrate.evaluator_seam]`, and this paragraph — while the
> re-bless note recording the 3 → 9 move sat 430 lines below the stale value **in the same file**.
> Corrected 2026-09-17. Two things follow, and the second is the one to carry:
>
> - **The true state was not in the vocabulary.** `install_compute`'s detector is three-valued and
>   this peer is the middle one: the setter accepts the evaluator and there is **no read-back** to
>   confirm it took. `compose.py`'s `FACE_STATES` had no word for *installed and unconfirmable*, so
>   the value stayed at `not-installable` — the most confident wrong answer available, because it
>   reads as a substrate LIMIT. `unverifiable` is a state now. **A missing term in an enumeration
>   holds a stale value in place**, and that is a different failure from nobody updating it.
> - **W-11 predicted this exactly and is still open.** `make probe` is in neither `check` nor
>   `check-all`, so `[system.faces]` is maintained by hand and has now gone stale the first time it
>   could. The gate is the fix; until it exists, a face value is a claim with a date on it.

**And the NINTH composition (2026-09-12, `rust × COMPUTE`) is the first port that added no new row
KIND.** Its new rows — `[substrate.handler_face]`, `[substrate.path_permission_predicate]`, and five
things the runtime does by itself (a saturating cast, a `mul` that overflows `i128`, a stack overflow
and an allocation failure that abort the process, a recursive `RwLock` read) — all fit kinds already
named. One port not changing the table's shape is the first data point toward the revisit criterion,
not a verdict on it. CORE stands.

**And the same day the table's most-cited asymmetry dissolved (2026-09-12, keystone H1 on `rust`).**
`rust`'s handler and evaluator faces went from `not-installable` to `installed`; all three rust
compositions were re-predicted and matched exactly (compute 7 → 125 → 128 with handler mode, history
7 → 32, content 7 → 12). **Rows changed VALUE, not kind** — no new row kind, and the per-(peer × face)
granularity D13's amendment introduced is what let the change be one line per face. Second data point
toward the revisit criterion. CORE stands.

**Disciplines start at D13** — D1–D12 are the ecosystem's and are reserved. **Do not copy another
repo's substrate disciplines.** In particular: **`entity-system-architecture`'s L-series is theirs,
earned on their own bugs.** Read it for the failure *shapes* — it is the best catalog in the
ecosystem — but this repo earns its own numbers on its own incidents.

**The four that transfer as read-only context, because this repo will meet them immediately:**

- **D12 / L8** — *an artifact is not a conclusion about the thing it names.* Its nineteenth form was
  found auditing keystone **to open this repo**: a generated cohort's uniform absence of a property
  is a fact about the **generator's input set**, not about the specification. This repo produces
  cohorts; it will produce that error. **And we did, in the plainest form available (AP-34,
  2026-09-10):** a `[substrate]`-shaped assumption in `extension-contracts/compute/EXTENSION.toml`
  claimed the peer exposed no path-scope capability predicate — **while our own
  `TRACKER-entity-core-keystone.md` carried that predicate as H9, landed, CLOSED, routed by this
  seat.** One tree, two answers, and nothing joins a tracker row to an assumption block. The rule
  that follows is cheap: **an assumption whose subject is a sibling repo's API names the packet that
  established it**, so the reader lands on the ledger row rather than on a sentence.
- **L7** — *check the toolkit before you build.* `validate-peer` is 66,651 lines and already covers
  52 extension categories. Before building any conformance instrument, run what exists.
- **L18** — *a cohort implementation is not evidence that a cohort ruling is right.* This repo will
  generate N implementations of one extension. **N agreeing is N agreeing.** Derive from the spec.
- **L17** — *a MUST naming a value or capability needs a declared site and a check that reads it.*
  Profile fields are declarations; absence is not a value.
