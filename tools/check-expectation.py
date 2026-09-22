#!/usr/bin/env python3
"""check-expectation.py — the composition's declared baseline, compared to the report
beside it. **The temporal baseline this repo did not have** (AP-18).

WHY THIS EXISTS
---------------
`make conformance` and `make regression` are two-arm diffs: bare peer versus composed
peer, one variable, within one run. That answers *"did the composition break the peer"* —
this repo's second failure mode, the one keystone never has — and it is what
`tools/diff-arms.py` was built for. It is **structurally blind** to the other direction:

    the baseline is in the ARM, and never in TIME.

`history/w6_caller_cap_absent` went `PASS -> FAIL` on two targets during one afternoon's
work and every gate in this tree reported green. The bare arm has always failed `w6`, so
after the change the comparison read `bare FAIL vs composed FAIL`, which is no difference,
which is not a regression. What actually happened is that the run **lost an improvement it
previously had**, and the improvement count was compared to nothing.

That is worse than a blind spot, because it is a blind spot in the reassuring direction: a
lost improvement presents as a *smaller improvement count*, in a column nobody asserts on.

THE BASELINE IS NOT THE PREDICTION, AND THAT IS THE DESIGN DECISION HERE
-----------------------------------------------------------------------
AP-18's rule says the declaration already in each `SYSTEM.toml` *is* the temporal baseline.
Reading them settled that it cannot be, and the reason generalises:

    [gate.expectation]   PRE-REGISTRATION. Written BEFORE the run, never edited afterwards.
                         `rs-content` predicted 0 and measured 3; the miss is kept on
                         purpose, because "a pre-registered expectation whose misses get
                         edited away is not a pre-registration".
    [gate.baseline]      WHAT WE LAST MEASURED. Updated deliberately, with a reason, every
                         time it legitimately changes.

Asserting against the pre-registration would make this gate permanently red on a
deliberately-preserved miss, and the locally-reasonable fix for that is to edit the
prediction — which destroys the artifact. **Two quantities were living in one block.** They
are now two blocks, and only one of them is a gate input.

WHAT IT ASSERTS, PER (composition x report stem)
------------------------------------------------
    total        the oracle's declared check count for that stem
    composed     the composed arm's severity tally
    bare         the bare arm's severity tally
    improved     THE NAMED SET of checks that move bare -> composed
    requirement  THE OBLIGATION each of those names carries  [§5b, 2026-09-16]

REQUIREMENT-KEYING (§5b) — WHY A RENAME IS NOT A LOST CAPABILITY
-----------------------------------------------------------------
`PROPOSAL-CONFORMANCE-ORACLE-CONTRACT` §5b `[MUST]`: a baseline outside an oracle's own
tree identifies an obligation by its requirement id, never by an oracle's check name. The
clause predicts that without it *"a re-pin that renames a check silently invalidates a
baseline."*

**Measured here before anything was built, and the word that is wrong is `silently`.** One
check renamed with its obligation and verdict unchanged — the thing a `validate-peer`
re-pin does — and this gate failed LOUDLY and TWICE, with both messages wrong:

    1 declared improvement(s) NO LONGER IMPROVE: content.type_blob    <- false
    1 UNDECLARED improvement(s): content.type_blob_entity             <- true, unjoined

Nothing connected the two halves of one event, and the remedy the first message offers is
the damaging one: *"re-bless WITH A REASON"* writes a re-pin into the permanent record as
a capability change, in the artifact whose only job is remembering capabilities over time.
At scale it is §5b's real argument — N renames produce 2N failures across nine
compositions, all reading like regressions, and **the reasonable response to a false red
across a whole tree is to delete the baselines.**

So `[gate.baseline.<stem>.requirement]` maps obligation -> the names currently carrying it,
grouped so a SPLIT joins an existing line. It is **emitted by `--bless` and never typed**:
every value is read out of the report by `requirement_keys()`, because a hand-kept copy of
another seat's map is what D20 exists to prevent and would be wrong at the first re-pin.

⚠ **This is not full §5b compliance and must not be cited as it.** The key is the oracle's
`spec_ref` — a SECTION CITATION, not a `SPECIFICATION-FORMAT` §8.5a `<PREFIX>-R<n>` id.
Those ids do not exist yet: core §9 has 98 obligations and 0 addressable, and the extension
sweep stands at 1 of 26. Both are arch's and both are on their board. What this buys with
no id scheme at all is §5b's consequence 1, which is the one that pays today.

`improved` is a set of NAMES and not a count, and that is D14 applied: a count that shrinks
by one understates a capability, and nothing re-checks in that direction. A name that
leaves the set is an absence with an identity. Both directions fail — a LOST improvement
because that is AP-18, and an UNDECLARED one because a gain nobody wrote down is a baseline
nobody re-read. Regressions (bare PASS, composed not) fail unconditionally and are never
declarable; `diff-arms` already owns that verdict and this file does not second-guess it.

A check whose verdict moves BETWEEN ROUNDS within an arm is flaky, belongs to neither arm,
and is excluded from `improved` — the same rule `diff-arms.py` applies, imported from it
rather than restated, because two copies of one rule is how the arms drifted (D17/D20).

REFUSALS (D15, sharpened) — this tool says "I did not measure anything" out loud
--------------------------------------------------------------------------------
  * no composition had any report at all                     -> REFUSING, rc 3
  * a `--require`d composition had none                       -> REFUSING, rc 3
  * a report stem present in one arm and not the other        -> REFUSING, rc 3
  * a report that parses to zero checks                       -> REFUSING, rc 3
  * rounds that are not one run (AP-22)                       -> REFUSING, rc 3

The first two are the AP-20 shape, which this repo paid for eight hours before this file
was written: a comparer printed `OK` over the arms that survived because it had no notion
of how many there should have been. A composition with no reports is a composition that was
not measured, and on a clean checkout that is the normal state — so it is REPORTED and
counted rather than failed, and the caller that knows what should be there says so with
`--require`. Requiring reports unconditionally would make the gate red on a fresh clone,
and a false red costs the instrument (D15/AP-4).

An undeclared stem is a FAILURE, not a refusal, in the same shape and for the same reason
as `[sdk_surface]` (D16), `[error_surface]` and `[conformance]`: the failure mode is a
category arriving without anyone deciding what it should say.

USAGE
    ./tools/check-expectation.py
    ./tools/check-expectation.py --require languages/rust/compositions/content
    ./tools/check-expectation.py --bless          # print the TOML for what is measured NOW
    ./tools/check-expectation.py --self-test      # the control
    ./tools/check-expectation.py --key-census     # do the reports carry obligation keys? (§5b)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# `diff-arms.py` is not importable by name (the hyphen is deliberate -- it is a driver, not
# a library) so it is loaded by path. It is loaded rather than re-implemented because the
# round/flaky/regression rules are ONE rule with two consumers, and a second copy is how
# `languages/*/build` drifted a readiness budget nobody went back for (D17/AP-10).
_spec = importlib.util.spec_from_file_location("diff_arms", ROOT / "tools" / "diff-arms.py")
diff_arms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diff_arms)

# The severities a tally may carry. Zero counts are dropped on both sides before comparison,
# so `{PASS = 32, WARN = 1, FAIL = 1}` and a report with `skipped: 0` agree.
SEVERITIES = ("PASS", "WARN", "FAIL", "SKIP")


class Refusal(Exception):
    """The instrument cannot answer. Distinct from a failure, which is an answer."""


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


# ── reading the reports ─────────────────────────────────────────────────────────────────

def rounds_for(reports: Path, arm: str, stem: str) -> list[Path]:
    """`<arm>-<stem>-<r>.json`, in round order, numerically.

    Sorted by the ROUND NUMBER and not by filename: `-10.json` sorts before `-2.json`
    lexically, and a round order that is wrong makes `provenance()`'s monotonicity check
    report a run that is perfectly fine. That is a false red on the very guard whose whole
    argument is that a false red costs the instrument.
    """
    found: list[tuple[int, Path]] = []
    for p in reports.glob(f"{arm}-{stem}-*.json"):
        m = re.fullmatch(rf"{re.escape(arm)}-{re.escape(stem)}-(\d+)\.json", p.name)
        if m:
            found.append((int(m.group(1)), p))
    return [p for _, p in sorted(found)]


def arm_state(paths: list[Path]) -> dict[str, list[str]]:
    """`category.check -> [severity per round]`, via diff-arms' own loader."""
    try:
        return diff_arms.collect([str(p) for p in paths])
    except SystemExit as e:      # `load()`'s zero-checks refusal, which is a refusal here too
        raise Refusal(str(e)) from None


def requirement_keys(paths: list[Path]) -> dict[str, str]:
    """`category.check -> the OBLIGATION the oracle says the check is about`.

    THE §5b SEAM, and the whole reason this function is separate from `arm_state`.

    `PROPOSAL-CONFORMANCE-ORACLE-CONTRACT` §5b `[MUST]`: *a document, gate or baseline
    outside an oracle's own tree identifies a conformance obligation by its requirement id,
    never by an oracle's check name; each oracle publishes its own check -> requirement
    map, and that map is the only place an oracle's internal names appear outside it.*

    **We do not maintain that map, and this function is the reason we do not have to.**
    `entity-core-go` publishes it per check, in the report, as `spec_ref` — measured across
    every report in this tree: **32,584 of 32,584 checks carry one, 100%, over 104 reports**
    (`./tools/check-expectation.py --key-census`, which prints exactly that line; the
    carve-out sentinels a `--profile core` run emits are dropped and not counted).
    ⚠ **An earlier draft of this sentence said 8,146, from a scope the cited command does not
    have** — the composed arm of round 1 only — which is AP-1's shape inside a docstring: a
    number not computed by the thing cited beside it. The flag was written afterwards to make
    the claim reproducible, and the first thing it did was disagree with the sentence that
    cited it. Reading the key here rather than declaring it
    in `SYSTEM.toml` is D20's rule applied to a map instead of to code: the copy that could
    drift is the one we would keep.

    ⚠ **HONEST SCOPE, because this is not yet full §5b compliance and must not be cited as
    it.** `spec_ref` is a SECTION CITATION (`CONTENT §2.1 / §11.1 MUST`), not a
    `SPECIFICATION-FORMAT` §8.5a `<PREFIX>-R<n>` requirement id. Arch's own §5b note says
    *"the core half is unblocked: core requirements are cited by the checks themselves"* —
    this citation is what that sentence refers to. Full compliance needs ids that do not
    exist yet: core §9 has 98 obligations and **0 addressable**, and the extension sweep
    stands at 1 of 26 conformance inventories. Both are arch's and both are on the board.
    What this buys today is the property §5b's consequence 1 names — **a re-pin that
    renames a check no longer reads as a lost capability** — and it buys it with no id
    scheme at all.
    """
    out: dict[str, str] = {}
    for p in paths:
        try:
            doc = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for c in doc.get("checks", []) or []:
            ref = c.get("spec_ref")
            if ref:
                out[f"{c.get('category', '?')}.{c.get('name', '?')}"] = ref
    return out


def tally(arm: dict[str, list[str]]) -> dict[str, int]:
    """The STABLE severity tally: a check that moved between rounds is counted under the
    severity it reported in round 1, because the total has to add up to the check count and
    a flaky check is still a check. It is separately named in `flaky` and excluded from
    `improved`, which is where its instability actually matters."""
    counts: dict[str, int] = {}
    for values in arm.values():
        counts[values[0]] = counts.get(values[0], 0) + 1
    return {k: v for k, v in counts.items() if v}


def measure(bare: dict[str, list[str]], composed: dict[str, list[str]],
            straddles: dict | None = None) -> dict:
    """The measured state of one (composition, stem), in the vocabulary the baseline
    declares. Module-level and pure, so `--self-test` and `--bless` drive THIS and never a
    re-derivation of it (D19; and the twice-in-one-session habit named in
    `HANDOFF-2026-09-07-c` §A4)."""
    # A DECLARED STRADDLE IS EXCLUDED FROM THE BASELINE ENTIRELY, not just from
    # `regressed` — and this is earned on the day after AP-23 was filed.
    #
    # Yesterday's blessing recorded `bare PASS=315 WARN=335` for `typescript`/`core`. Today
    # the same command on the same tree reads `314 / 336`, because
    # `concurrency.t1_1_concurrent_demux`'s verdict turns on whether a 50 ms floor is
    # crossed and the box was under different load. Nothing about the composition changed.
    #
    # So a check whose verdict is UNATTRIBUTABLE cannot be part of a temporal baseline
    # either: blessing it encodes machine load as a declared fact, and the gate then goes
    # red on the weather. That is a false red on this repo's newest gate, which is how a
    # gate gets switched off (AP-4). Excluded from BOTH arms and from `total`, listed in
    # `excluded`, and printed — never silently dropped.
    straddles = straddles or {}
    excluded = sorted(k for k in set(bare) | set(composed) if k in straddles)
    if excluded:
        bare = {k: v for k, v in bare.items() if k not in straddles}
        composed = {k: v for k, v in composed.items() if k not in straddles}

    improved, regressed, flaky = [], [], []
    for key in sorted(set(bare) & set(composed)):
        b, c = diff_arms.stable(bare[key]), diff_arms.stable(composed[key])
        if b is None or c is None:
            flaky.append(key)
            continue
        if b == c:
            continue
        (regressed if b == "PASS" else improved).append(key)
    return {
        "total": len(composed),
        "composed": tally(composed),
        "bare": tally(bare),
        "improved": improved,
        "regressed": regressed,
        "flaky": flaky,
        "composed_only": sorted(set(composed) - set(bare)),
        "bare_only": sorted(set(bare) - set(composed)),
        "excluded": excluded,
    }


# ── the gate rule ───────────────────────────────────────────────────────────────────────

def evaluate(stem: str, declared: dict, measured: dict, straddles: dict | None = None,
             measured_keys: dict[str, str] | None = None) -> list[str]:
    """Every failure this gate can produce, in one function.

    Returns a list of failure messages; empty means the baseline holds. Both set directions
    are failures and the messages say which is which, because *lost* and *undeclared* have
    different causes and the fix for one is not the fix for the other.
    """
    out: list[str] = []
    where = f"{stem}"

    if declared.get("total") != measured["total"]:
        out.append(
            f"{where}: the oracle declared {measured['total']} checks, the baseline says "
            f"{declared.get('total')}. The check SET changed -- an oracle re-pin, a profile "
            f"change, or a category that stopped running. Nothing below is comparable until "
            f"this is understood."
        )

    for arm in ("composed", "bare"):
        want = {k: v for k, v in (declared.get(arm) or {}).items() if v}
        got = {k: v for k, v in measured[arm].items() if v}
        if want != got:
            out.append(f"{where}: {arm} tally {json.dumps(got, sort_keys=True)} != "
                       f"declared {json.dumps(want, sort_keys=True)}")

    want_i = set(declared.get("improved") or [])
    got_i = set(measured["improved"])

    # ── D23 — AN EMPTY `improved` IS A CLAIM, AND IT MUST BE MADE OUT LOUD ──────────────────
    #
    # `improved = []` says: on this category, installing the extension moved NOTHING. That is
    # sometimes true and always suspicious, and it is the exact artifact that hid two of our own
    # defects for nine days. `python × entity_native` was blessed at `improved = []` because the
    # peer had no evaluator seam, the face read `not-installable`, and the empty list looked like
    # an honest record of a substrate limit. It was an honest record of a substrate limit AND a
    # cover for a wrong signature, an unpopulated §3.2 E1 scope and an unnarrowed §4.1 read path —
    # none of which any test could reach, because the face they lived behind could not be
    # installed.
    #
    # **A face reported ABSENT is a face whose contents are UNMEASURED**, and those are two
    # different words. So the empty set is allowed and must carry `why_nothing_moved`: which face
    # is absent, and what is consequently unmeasured rather than known-good. The field is prose on
    # purpose — there is nothing here a machine can adjudicate — and its whole job is that writing
    # it requires saying "and therefore I do not know about X", which is the sentence the empty
    # list was standing in for.
    #
    # SCOPE: *nothing moved at all*, so a category with a regression or a declared straddle is out
    # — something moved there, it is just not an improvement, and demanding the field anyway would
    # put the rule in front of readers who are already looking at a finding. Caught by this file's
    # own AP-23 control going red on the first draft, which is the check doing its job on the
    # check.
    if (not want_i and not got_i and not measured["regressed"]
            and not declared.get("why_nothing_moved")):
        out.append(
            f"{where}: `improved` is EMPTY and there is no `why_nothing_moved`. An empty set is "
            f"a claim that the composition moved nothing on this category; declare WHICH FACE is "
            f"absent and WHAT IS THEREFORE UNMEASURED. A face reported absent is a face whose "
            f"contents are unmeasured, and an honest report of an absence reads as an account of "
            f"the gap when it is not one (D23)."
        )

    lost = sorted(want_i - got_i)
    gained = sorted(got_i - want_i)

    # ── §5b — A RENAME IS NOT A LOST CAPABILITY, AND THIS IS WHERE THE TWO GET SEPARATED ────
    #
    # Measured before this existed, by planting the thing a `validate-peer` re-pin does — one
    # check renamed, same obligation, same severity, `content.type_blob` ->
    # `content.type_blob_entity`. The gate was NOT silent, which is worth saying because the
    # clause that asks for this predicts that it is. It failed TWICE, and both messages were
    # wrong:
    #
    #     1 declared improvement(s) NO LONGER IMPROVE: content.type_blob   <- false
    #     1 UNDECLARED improvement(s): content.type_blob_entity            <- true but unjoined
    #
    # Nothing connected the two halves of one event. The first message says the composition
    # stopped doing something it used to do; it did not. **And the remedy that message offers is
    # the damaging one** -- "re-bless WITH A REASON" launders a re-pin into the permanent record
    # as a capability change, in the one artifact whose whole job is to remember capabilities
    # over time.
    #
    # At scale it is worse and it is §5b's actual argument: a re-pin renaming N checks produces
    # 2N failures across nine compositions, every one of them reading like a regression. **The
    # reasonable response to a false red across an entire tree is to delete the baselines**, so
    # the failure mode is not a bad migration -- it is the instrument being discarded and the
    # coverage with it (AP-4, at tree scale).
    #
    # The join is the obligation the oracle itself names. A lost name whose declared requirement
    # key is carried by a gained name is one check under a new spelling: still a failure, because
    # the baseline has to be updated, but NAMED CORRECTLY and without the capability framing.
    measured_keys = measured_keys or {}
    declared_key = {n: k for k, names in (declared.get("requirement") or {}).items()
                    for n in names}
    renamed: list[tuple[str, str, str]] = []
    if declared_key:
        for l in list(lost):
            k = declared_key.get(l)
            if k is None:
                continue
            for g in list(gained):
                if measured_keys.get(g) == k:
                    renamed.append((l, g, k))
                    lost.remove(l)
                    gained.remove(g)
                    break
    elif want_i:
        # D16's shape, not a nicety: an undeclared thing is a failure, because the failure mode
        # is a baseline arriving without anyone deciding what obligation it is about. A block
        # that reaches this branch is one whose findings CANNOT be joined, and it says so
        # whether or not today's run happens to have a pair to join.
        out.append(
            f"{where}: [gate.baseline.{stem}.requirement] is missing, so a LOST name and a "
            f"GAINED name cannot be told apart from one RENAMED check (§5b). `--bless` emits "
            f"the block."
            + (" Both findings below are unjoined." if lost and gained else "")
        )
    if declared_key:
        # A PARTIAL map is the quiet version of a missing one: the names it omits fall back to
        # the pre-§5b behaviour with nothing saying which ones did. Cheap to assert, and it is
        # the assertion that keeps the map honest as `improved` grows.
        unkeyed = sorted(want_i - set(declared_key))
        if unkeyed:
            out.append(
                f"{where}: {len(unkeyed)} declared improvement(s) carry no obligation in "
                f"[gate.baseline.{stem}.requirement]: {', '.join(unkeyed)}. A partial map joins "
                f"some findings and silently does not join the rest; re-bless."
            )

    if renamed:
        out.append(
            f"{where}: {len(renamed)} check(s) RENAMED by the oracle, NOT lost -- "
            + "; ".join(f"`{l}` -> `{g}` (both are `{k}`)" for l, g, k in renamed)
            + ". The obligation is unchanged and the composition still satisfies it. Re-bless "
            "to take the new spelling; do NOT record this as a capability change."
        )
    if lost:
        out.append(
            f"{where}: {len(lost)} declared improvement(s) NO LONGER IMPROVE: "
            f"{', '.join(lost)}. This is AP-18 exactly -- the composition stopped doing "
            f"something it used to do, and the two-arm diff cannot see it because the bare "
            f"arm fails these too. Either it is a regression to fix, or the baseline is to "
            f"be re-blessed WITH A REASON."
        )
    if gained:
        out.append(
            f"{where}: {len(gained)} UNDECLARED improvement(s): {', '.join(gained)}. A gain "
            f"nobody wrote down is a baseline nobody re-read; re-bless it so the next loss "
            f"has a reference point."
        )

    # ONE declaration, two consumers, imported rather than restated: `diff-arms` owns
    # `[[gate.straddle]]` and this file reads the same block through it. Two copies of one
    # rule is how the drivers drifted a readiness budget nobody went back for (D17/AP-10).
    straddles = straddles or {}
    real = [k for k in measured["regressed"] if k not in straddles]
    if real:
        out.append(
            f"{where}: {len(real)} REGRESSION(s) attributable to the composition: "
            f"{', '.join(real)}"
        )
    for key in measured["bare_only"]:
        out.append(f"{where}: {key} exists on the bare peer and NOT under composition")
    return out


# ── walking the tree ────────────────────────────────────────────────────────────────────

def compositions() -> list[Path]:
    return sorted(p for p in ROOT.glob("languages/*/compositions/*/SYSTEM.toml"))


def stems_of(system: dict) -> list[str]:
    """The report stems a composition declares: its gate categories plus its profiles.

    Read from `[gate]` rather than from the filesystem. A stem that stopped being produced
    has to be visible as a refusal, and a glob over what exists can only ever report what
    exists."""
    gate = system.get("gate", {})
    return list(dict.fromkeys(list(gate.get("categories", [])) + list(gate.get("profiles", []))))


def check_one(path: Path) -> tuple[list[str], list[str], dict, list[str]]:
    """(failures, refusals, measured-by-stem, UNMEASURED stems) for one composition. No
    reports at all is none of them: it is `{}`, counted by the caller and reported.

    THE FOURTH ELEMENT EXISTS BECAUSE `stems_of()`'s docstring, two functions up, ALREADY
    CLAIMED IT — *"a stem that stopped being produced has to be visible as a refusal, and a
    glob over what exists can only ever report what exists"* — and the loop below said
    `continue`. The requirement was written down and not implemented, in adjacent functions,
    by the same author, on the same day.

    What it costs, found 2026-09-16 by running `--bless` for the first time since it changed:
    a composition measured for 2 of its 3 declared stems printed two measurement lines and
    nothing about the third. That is AP-19's shape — a line that reads like a measurement over
    a state that produced none — in the file whose own docstring cites AP-19. **And through
    `--bless` it is worse than cosmetic:** blessing a partially-measured composition emits a
    partial paste block, and pasting it DELETES the baseline for the unmeasured stem. The
    artifact whose whole job is remembering a capability over time, removed by the command
    meant to maintain it.
    """
    system = tomllib.loads(path.read_text(encoding="utf-8"))
    reports = path.parent.parent.parent / "output" / path.parent.name / "reports"
    baseline = system.get("gate", {}).get("baseline", {})
    straddles = diff_arms.declared_straddles(str(path))
    failures: list[str] = []
    refusals: list[str] = []
    unmeasured: list[str] = []
    out: dict[str, dict] = {}
    comp = _rel(path.parent)

    for stem in stems_of(system):
        bare_p, composed_p = rounds_for(reports, "bare", stem), rounds_for(reports, "composed", stem)
        if not bare_p and not composed_p:
            # NOT a failure and NOT a refusal: running one category (`make conformance
            # CATEGORIES=content`) is ordinary, and failing on it would be a false red on a
            # normal workflow, which is how a gate gets switched off (AP-4). It is RECORDED,
            # so the caller can print it beside the stems that WERE measured and `--bless`
            # can refuse to emit a partial paste block.
            unmeasured.append(stem)
            continue
        if not bare_p or not composed_p:
            refusals.append(
                f"{comp}/{stem}: only the "
                f"{'composed' if not bare_p else 'bare'} arm has reports. One arm cannot "
                f"produce an improvement set."
            )
            continue
        stale = [diff_arms.provenance(arm, [_rel(p) for p in paths],
                                      diff_arms.stamps([str(p) for p in paths]))
                 for arm, paths in (("bare", bare_p), ("composed", composed_p))]
        stale = [m for m in stale if m]
        if stale:
            refusals += [f"{comp}/{stem} {m.splitlines()[0]}" for m in stale]
            continue
        try:
            m = measure(arm_state(bare_p), arm_state(composed_p), straddles)
        except Refusal as e:
            refusals.append(f"{comp}/{stem}: {e}")
            continue
        m["rounds"] = min(len(bare_p), len(composed_p))
        m["timestamp"] = diff_arms.stamps([str(composed_p[0])])[0]
        # Carried on the measurement rather than re-read at bless time: `--bless` must emit
        # the keys from the SAME reports the verdict was computed over, not from whatever is
        # on disk when the emitter runs (D19 -- an instrument does not read a quantity a
        # later step could have rewritten).
        m["keys"] = requirement_keys(composed_p)
        out[stem] = m

        declared = baseline.get(stem)
        if declared is None:
            failures.append(
                f"{comp}: no [gate.baseline.{stem}] block, and the composition declares "
                f"`{stem}` in [gate]. An undeclared stem is a failure for the same reason "
                f"an undeclared SDK name is (D16): the failure mode is a category arriving "
                f"without anyone deciding what it should say. `--bless` prints the block."
            )
            continue
        failures += [f"{comp}: {f}" for f in
                     evaluate(stem, declared, m, straddles, m["keys"])]

    for stem in sorted(set(baseline) - set(stems_of(system))):
        failures.append(f"{comp}: [gate.baseline.{stem}] declares a stem [gate] does not "
                        f"list. A baseline for something nothing runs is never checked.")
    return failures, refusals, out, unmeasured


def _inline(counts: dict[str, int]) -> str:
    return "{ " + ", ".join(f"{k} = {counts[k]}" for k in SEVERITIES if counts.get(k)) + " }"


def _toml_str(s: str) -> str:
    """A TOML basic string. Hand-quoting these is how a `spec_ref` carrying a quote or a
    backslash silently produces a file that parses to something else — and the oracle's own
    refs run to free prose (`V7 §6.2 — handler MUST NOT grant scope exceeding caller's
    authorization`)."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def bless(comp: str, stem: str, m: dict, keys: dict[str, str] | None = None) -> str:
    names = "\n".join('  "%s",' % k for k in m["improved"])
    block = (
        f"# ── {comp}\n"
        f"[gate.baseline.{stem}]\n"
        f'measured = "{m["timestamp"][:10]}"   # {m["rounds"]} round(s)\n'
        f"total    = {m['total']}\n"
        f"composed = {_inline(m['composed'])}\n"
        f"bare     = {_inline(m['bare'])}\n"
        f"improved = [\n{names}\n]\n"
    )
    # §5b — the requirement key each improved check carries, GROUPED BY OBLIGATION.
    #
    # Grouped rather than one line per check for a reason that is not formatting: the
    # inverted form is the oracle's check -> requirement map with the arrow the way a reader
    # needs it, and it is what makes a SPLIT legible. When a re-pin turns one check into two
    # under the same obligation, the new spelling joins an existing line instead of adding a
    # row nobody can place. Measured across this tree: 777 improved names collapse to 297
    # obligation lines.
    #
    # Emitted, never typed. Every value here is read out of the report by
    # `requirement_keys()`; a hand-maintained copy of another seat's map is the thing D20
    # exists to prevent, and it would be wrong the first time the oracle re-pinned.
    if keys is not None:
        grouped: dict[str, list[str]] = {}
        for n in m["improved"]:
            k = keys.get(n)
            if k is None:
                continue
            grouped.setdefault(k, []).append(n)
        if grouped:
            block += f"\n[gate.baseline.{stem}.requirement]\n"
            for k in sorted(grouped):
                members = ", ".join(f'"{n}"' for n in sorted(grouped[k]))
                block += f"{_toml_str(k)} = [{members}]\n"
    return block


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--require", action="append", default=[],
                    help="a composition path that MUST have reports (no silent caps)")
    ap.add_argument("--bless", action="store_true", help="print the TOML for what is measured now")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--key-census", action="store_true",
                    help="how many checks in the reports on disk carry an obligation key (§5b)")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.key_census:
        # The command the §5b docstring cites for its 100% claim. D14: a number cites the thing
        # that produced it, and a citation to a flag that does not exist is AP-2 one level worse
        # -- the citation outliving the thing it names (D18). This flag exists because that
        # sentence was written before it did.
        total = keyed = 0
        for r in sorted(ROOT.glob("languages/*/output/*/reports/*.json")):
            try:
                doc = json.loads(r.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            for c in doc.get("checks", []) or []:
                if c.get("name") == "skipped" and not c.get("spec_ref"):
                    continue           # the --profile core carve-out sentinel, no information
                total += 1
                if c.get("spec_ref"):
                    keyed += 1
        if not total:
            print("REFUSING: no reports on disk, so `every check carries a key` would be a "
                  "claim over an empty set. Run `make conformance` first.", file=sys.stderr)
            return 3
        print(f"obligation keys (`spec_ref`): {keyed} of {total} checks "
              f"({100 * keyed // total}%), over {len(list(ROOT.glob('languages/*/output/*/reports/*.json')))} report(s)")
        return 0 if keyed == total else 1

    comps = compositions()
    if not comps:
        print("REFUSING: no compositions found. A clean verdict over an empty tree is not "
              "a clean verdict.", file=sys.stderr)
        return 3

    failures: list[str] = []
    refusals: list[str] = []
    measured_comps: list[str] = []
    blessed: list[str] = []
    partial: list[tuple[str, list[str]]] = []

    for path in comps:
        comp = _rel(path.parent)
        f, r, out, unmeasured = check_one(path)
        failures += f
        refusals += r
        if unmeasured:
            partial.append((comp, unmeasured))
        if not out:
            # `refused` and `no reports` are two different states and printing one for the
            # other is this repo's own AP-19 shape: a line that reads like a measurement.
            print(f"  not measured  {comp}  "
                  f"({'every stem REFUSED, see below' if r else 'no reports on disk'})")
            continue
        measured_comps.append(comp)
        for stem, m in out.items():
            print(f"  {comp}/{stem}: {m['rounds']} round(s) @ {m['timestamp']}  "
                  f"total={m['total']}  improved={len(m['improved'])}  "
                  f"regressed={len(m['regressed'])}  flaky={len(m['flaky'])}")
            if m["flaky"]:
                print(f"      flaky, attributable to neither arm: {', '.join(m['flaky'])}")
            if m["excluded"]:
                print(f"      excluded from the baseline as DECLARED STRADDLES (AP-23): "
                      f"{', '.join(m['excluded'])}")
            if args.bless:
                blessed.append(bless(comp, stem, m, m.get("keys")))
        # Beside the stems that WERE measured, and never instead of them: a composition that
        # measured 2 of its 3 declared stems used to print two measurement lines and nothing
        # about the third.
        for c, stems in partial:
            if c == comp:
                print(f"      NOT MEASURED, declared in [gate]: {', '.join(stems)} "
                      f"(no reports on disk -- `make conformance` has not run this stem)")

    # THE SCOPE OF EVERY CLAIM BELOW, printed before the verdict.
    print(f"\nmeasured: {len(measured_comps)} of {len(comps)} compositions")

    if args.bless and partial:
        # A PARTIAL PASTE BLOCK DELETES A BASELINE. Emitting blocks for the stems that ran and
        # nothing for the ones that did not looks complete; pasting it removes the temporal
        # reference for every stem missing from the output. So `--bless` refuses rather than
        # emits, and names what to run first. This is the refusal D15's sharpened clause asks
        # for -- the instrument saying "I did not measure everything you are about to replace".
        print("\nREFUSING to bless: "
              + "; ".join(f"{c} has no reports for {', '.join(s)}" for c, s in partial)
              + ". A paste block covering only the stems that ran would DELETE the baseline "
                "for the ones that did not. Run `make conformance` for the missing stem(s), "
                "or bless one composition at a time.", file=sys.stderr)
        return 3

    if args.bless:
        print("\n# ── paste into the composition's SYSTEM.toml, under [gate]. A CHANGED\n"
              "# ── baseline needs a REASON beside it -- a baseline re-blessed without one\n"
              "# ── is the temporal reference deleting itself.\n")
        print("\n".join(blessed))
        return 0

    if not measured_comps:
        print("REFUSING: no composition had any report. This gate compares a declaration to "
              "a report, and with no reports it measured nothing -- which is a different "
              "state from `no failures` and must never print as one.", file=sys.stderr)
        return 3

    missing = [c for c in args.require if c.rstrip("/") not in measured_comps]
    if missing:
        print(f"REFUSING: {len(missing)} required composition(s) had no reports: "
              f"{', '.join(missing)}. The caller that knows what should be there said so; "
              f"a verdict over the rest is a narrower measurement reported as a clean one "
              f"(AP-20).", file=sys.stderr)
        return 3

    if refusals:
        print("\nREFUSING:", file=sys.stderr)
        for r in refusals:
            print(f"  {r}", file=sys.stderr)
        return 3
    if failures:
        print(f"\nEXPECTATION: {len(failures)} failing.", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("EXPECTATION: OK — every measured composition matches its declared baseline.")
    return 0


# ── the control ─────────────────────────────────────────────────────────────────────────

def self_test() -> int:
    """Every rule in `evaluate()` and both of `measure()`'s directions, driven through the
    REAL functions over synthetic arms. The first scenario is AP-18 reconstructed from the
    numbers that were actually on disk."""
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {label}")
        ok = ok and cond

    def arms(bare_map, composed_map, rounds=2):
        return ({k: [v] * rounds for k, v in bare_map.items()},
                {k: [v] * rounds for k, v in composed_map.items()})

    # ── AP-18, reconstructed. `w6` passed composed, then failed; bare failed throughout.
    bare = {"history.w6_caller_cap_absent": "FAIL", "history.type_config": "FAIL"}
    before = {"history.w6_caller_cap_absent": "PASS", "history.type_config": "PASS"}
    after = {"history.w6_caller_cap_absent": "FAIL", "history.type_config": "PASS"}

    # The obligations these two checks carry, as the oracle states them in the report. Defined
    # here rather than beside the §5b cases below because every fixture in this self-test needs
    # them: after §5b a baseline with a non-empty `improved` and no obligation map is itself a
    # failure, so a fixture without one is not a valid baseline to test anything else against.
    KEY_W6 = "HISTORY §9.1 w6"
    KEY_CFG = "HISTORY §6.1"
    KEYS = {"history.w6_caller_cap_absent": KEY_W6, "history.type_config": KEY_CFG}

    m_before = measure(*arms(bare, before))
    declared = {"total": 2, "composed": m_before["composed"], "bare": m_before["bare"],
                "improved": m_before["improved"],
                "requirement": {KEY_W6: ["history.w6_caller_cap_absent"],
                                KEY_CFG: ["history.type_config"]}}
    # The pre-§5b shape, kept on purpose: it is the input the "you have no obligation map"
    # rule must fire on, and building it by DELETION from the real fixture means it cannot
    # drift away from what a real unmigrated baseline looks like.
    unkeyed = {k: v for k, v in declared.items() if k != "requirement"}
    expect("the baseline it was blessed from holds",
           evaluate("history", declared, m_before, None, KEYS) == [])

    m_after = measure(*arms(bare, after))
    fails = evaluate("history", declared, m_after)
    expect("AP-18: the lost improvement FAILS", len(fails) > 0)
    expect("AP-18: and the failure NAMES w6_caller_cap_absent",
           any("w6_caller_cap_absent" in f and "NO LONGER IMPROVE" in f for f in fails))
    expect("AP-18: and the two-arm rule alone still sees NOTHING (why this file exists)",
           m_after["regressed"] == [])

    # ── the other direction: a gain nobody declared.
    more = {"history.w6_caller_cap_absent": "PASS", "history.type_config": "PASS",
            "history.type_transition": "PASS"}
    bare3 = dict(bare, **{"history.type_transition": "FAIL"})
    m_more = measure(*arms(bare3, more))
    d3 = dict(declared, total=3, bare=m_more["bare"], composed=m_more["composed"])
    expect("an UNDECLARED improvement fails",
           any("UNDECLARED" in f for f in evaluate("history", d3, m_more)))

    # ── §5b: A RENAME IS NOT A LOSS, and the controls that matter are the ones proving the
    # ── classifier does not SWALLOW a real one.
    #
    # Five cases. Case 1 is the behaviour being added; cases 2–5 are the price of adding it,
    # because a joiner that pairs things too eagerly converts AP-18 — the failure this whole
    # file exists for — into a reassuring "renamed" line. That is the false-GREEN direction and
    # it costs a missed defect, so it gets three of the five.
    keyed = declared

    # 1. THE RENAME. Same obligation, new spelling, same verdict — exactly what a re-pin does.
    renamed_bare = {"history.w6_renamed": "FAIL", "history.type_config": "FAIL"}
    renamed_comp = {"history.w6_renamed": "PASS", "history.type_config": "PASS"}
    m_ren = measure(*arms(renamed_bare, renamed_comp))
    f_ren = evaluate("history", dict(keyed, composed=m_ren["composed"], bare=m_ren["bare"]),
                     m_ren, None, {"history.w6_renamed": KEY_W6,
                                   "history.type_config": KEY_CFG})
    expect("§5b: a rename is reported as RENAMED",
           any("RENAMED" in f and "w6_renamed" in f for f in f_ren))
    expect("§5b: ...and NOT as a lost capability",
           not any("NO LONGER IMPROVE" in f for f in f_ren))
    expect("§5b: ...and NOT as an undeclared gain either -- one event, one finding",
           not any("UNDECLARED" in f for f in f_ren))

    # 2. A REAL LOSS still fails, with the requirement block present. The classifier has a key
    #    for `w6` and there is no gained check carrying it, so nothing pairs.
    f_lost = evaluate("history", keyed, m_after, None,
                      {"history.w6_caller_cap_absent": KEY_W6, "history.type_config": KEY_CFG})
    expect("§5b: a REAL loss is still AP-18 when the block is present",
           any("NO LONGER IMPROVE" in f and "w6_caller_cap_absent" in f for f in f_lost))
    expect("§5b: ...and is not mislabelled a rename", not any("RENAMED" in f for f in f_lost))

    # 3. A LOSS AND A GAIN UNDER DIFFERENT OBLIGATIONS ARE NOT PAIRED. This is the case a
    #    joiner keyed on "one went, one came" gets wrong, and it is the likeliest real shape:
    #    a re-pin that drops one check and adds an unrelated one in the same category.
    unrel_bare = {"history.type_config": "FAIL", "history.type_transition": "FAIL"}
    unrel_comp = {"history.type_config": "PASS", "history.type_transition": "PASS"}
    m_unrel = measure(*arms(unrel_bare, unrel_comp))
    f_unrel = evaluate("history", dict(keyed, composed=m_unrel["composed"], bare=m_unrel["bare"]),
                       m_unrel, None, {"history.type_config": KEY_CFG,
                                       "history.type_transition": "HISTORY §2.2"})
    expect("§5b: a loss and a gain under DIFFERENT obligations stay two findings",
           any("NO LONGER IMPROVE" in f for f in f_unrel)
           and any("UNDECLARED" in f for f in f_unrel)
           and not any("RENAMED" in f for f in f_unrel))

    # 4. A GAINED CHECK WITH NO KEY IN THE REPORT pairs with nothing. `measured_keys` is read
    #    from the report and a check could arrive without a `spec_ref`; absent must mean
    #    "cannot join", never "joins to whatever is missing".
    f_nokey = evaluate("history", dict(keyed, composed=m_ren["composed"], bare=m_ren["bare"]),
                       m_ren, None, {"history.type_config": KEY_CFG})
    expect("§5b: a gained check carrying no obligation key is never paired",
           any("NO LONGER IMPROVE" in f for f in f_nokey)
           and not any("RENAMED" in f for f in f_nokey))

    # 5. WITHOUT the requirement block the two findings are unjoinable, and the gate SAYS SO
    #    rather than quietly behaving as it did before (D15's refusal clause: an instrument
    #    that cannot answer says which answer it could not give).
    f_noblock = evaluate("history", dict(unkeyed, composed=m_ren["composed"],
                                         bare=m_ren["bare"]), m_ren, None,
                         {"history.w6_renamed": KEY_W6, "history.type_config": KEY_CFG})
    expect("§5b: with no [.requirement] block the gate says the findings are UNJOINED",
           any("cannot be told apart" in f for f in f_noblock))
    expect("§5b: ...and it says so even on a run with nothing to join (D16: undeclared fails)",
           any("cannot be told apart" in f for f in evaluate("history", unkeyed, m_before)))
    # ...but NOT for a block whose `improved` is legitimately empty. An empty set has no
    # obligations to map, and demanding the block there would put a §5b failure in front of
    # every `not-installable` face in the tree -- a false red on a correct declaration, which
    # is how a gate stops being believed (AP-4). Same scoping lesson D23 learned on its own
    # first draft, one rule over.
    m_none = measure(*arms({"c.k": "FAIL"}, {"c.k": "FAIL"}))
    expect("§5b: ...but NOT for a block whose `improved` is legitimately empty",
           not any("cannot be told apart" in f for f in evaluate(
               "c", {"total": 1, "composed": m_none["composed"], "bare": m_none["bare"],
                     "improved": [], "why_nothing_moved": "x"}, m_none)))

    # 6. A PARTIAL map is the quiet version of a missing one.
    expect("§5b: an improvement missing from the obligation map fails by name",
           any("carry no obligation" in f and "type_config" in f for f in evaluate(
               "history", dict(declared, requirement={KEY_W6: ["history.w6_caller_cap_absent"]}),
               m_before, None, {"history.w6_caller_cap_absent": KEY_W6,
                                "history.type_config": KEY_CFG})))

    # ── A DECLARED STEM WITH NO REPORTS IS REPORTED, NOT SKIPPED.
    #
    # Driven through `check_one` on a fixture tree rather than through the pure functions,
    # because the defect was in the WALK and not in any comparison: the loop said `continue`
    # while `stems_of()`'s own docstring, two functions up, said a stem that stopped being
    # produced "has to be visible as a refusal". A control over `evaluate()` could not have
    # seen it, which is why this one builds a directory.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        lang = Path(td) / "languages" / "x"
        cdir = lang / "compositions" / "c"
        rdir = lang / "output" / "c" / "reports"
        cdir.mkdir(parents=True); rdir.mkdir(parents=True)
        (cdir / "SYSTEM.toml").write_text(
            '[gate]\ncategories = ["ran", "never_ran"]\n\n'
            '[gate.baseline.ran]\ntotal = 1\ncomposed = { PASS = 1 }\n'
            'bare = { FAIL = 1 }\nimproved = ["ran.k"]\n\n'
            '[gate.baseline.ran.requirement]\n"SPEC §1" = ["ran.k"]\n\n'
            '[gate.baseline.never_ran]\ntotal = 1\ncomposed = { PASS = 1 }\n'
            'bare = { FAIL = 1 }\nimproved = ["never_ran.k"]\n\n'
            '[gate.baseline.never_ran.requirement]\n"SPEC §2" = ["never_ran.k"]\n',
            encoding="utf-8")
        for r in (1, 2):
            for arm, sev in (("bare", "FAIL"), ("composed", "PASS")):
                (rdir / f"{arm}-ran-{r}.json").write_text(json.dumps(
                    {"timestamp": f"2026-09-16T0{r}:00:00Z",
                     "checks": [{"category": "ran", "name": "k", "severity": sev,
                                 "spec_ref": "SPEC §1"}]}))
        f_fix, r_fix, out_fix, unmeasured = check_one(cdir / "SYSTEM.toml")
        expect("a declared stem with NO reports is RECORDED, not silently skipped",
               unmeasured == ["never_ran"])
        expect("...and the stem that DID run is still measured beside it",
               list(out_fix) == ["ran"])
        expect("...and it is neither a failure nor a refusal (one-category runs are ordinary)",
               f_fix == [] and r_fix == [])

    # ── a real regression: bare PASS, composed not. Never declarable.
    m_reg = measure(*arms({"c.k": "PASS"}, {"c.k": "FAIL"}))
    expect("a regression is measured as one", m_reg["regressed"] == ["c.k"])
    reg_baseline = {"total": 1, "composed": m_reg["composed"], "bare": m_reg["bare"],
                    "improved": []}
    expect("and fails even against a baseline that declares it",
           any("REGRESSION" in f for f in evaluate("c", reg_baseline, m_reg)))
    expect("a DECLARED straddle is not counted as a regression (AP-23)",
           evaluate("c", reg_baseline, m_reg, {"c.k": {"routed": "r.md"}}) == [])
    expect("and a straddle declared for a DIFFERENT check does not cover this one",
           any("REGRESSION" in f for f in evaluate(
               "c", reg_baseline, m_reg, {"c.other": {"routed": "r.md"}})))

    # ── D23: an empty `improved` must say what is unmeasured behind it ──────────────────────
    #
    # Four cases, and the pair is the point: the rule has to fire on an UNEXPLAINED empty set and
    # stay silent on an explained one, AND it must not fire whenever the set is non-empty — a
    # version that just demanded the field everywhere would pass case 1 alone and be noise.
    nothing = {"c.k": "FAIL"}
    m_zero = measure(*arms(nothing, nothing))
    zero_baseline = {"total": 1, "composed": m_zero["composed"], "bare": m_zero["bare"],
                     "improved": []}
    expect("an unexplained empty `improved` fails",
           any("unmeasured" in f for f in evaluate("c", zero_baseline, m_zero)))
    expect("...and an explained one does not",
           evaluate("c", dict(zero_baseline, why_nothing_moved="no evaluator seam on this peer; "
                              "the four entity-native scope checks are UNMEASURED, not passing"),
                    m_zero) == [])
    expect("...and it does not fire when something DID move",
           not any("unmeasured" in f for f in evaluate("history", declared, m_before)))
    expect("...and an empty declaration against a run that gained still reports the GAIN",
           any("UNDECLARED" in f for f in evaluate(
               "history", dict(d3, improved=[], why_nothing_moved="x"), m_more)))

    # ── the check SET changing is its own failure, ahead of everything else.
    expect("a changed check total fails",
           any("check SET changed" in f for f in evaluate(
               "history", dict(declared, total=99), m_before)))

    # ── a DECLARED STRADDLE is out of the baseline entirely (AP-23, the day after).
    st_bare = {"c.k": ["PASS", "PASS"], "c.other": ["FAIL", "FAIL"]}
    st_comp = {"c.k": ["WARN", "WARN"], "c.other": ["PASS", "PASS"]}
    m_plain = measure(st_bare, st_comp)
    m_excl = measure(st_bare, st_comp, {"c.k": {"routed": "r.md"}})
    expect("without a declaration the straddle is a regression and IS in the tally",
           m_plain["regressed"] == ["c.k"] and m_plain["total"] == 2)
    expect("declared: dropped from BOTH arms, from `total`, and named in `excluded`",
           m_excl["total"] == 1 and m_excl["excluded"] == ["c.k"]
           and m_excl["regressed"] == [] and m_excl["bare"] == {"FAIL": 1})
    expect("...and the real improvement beside it still counts",
           m_excl["improved"] == ["c.other"])
    expect("a straddle for a check that is not present excludes nothing",
           measure(st_bare, st_comp, {"c.absent": {}})["total"] == 2)

    # ── flaky belongs to neither arm and is excluded from `improved`.
    flaky_bare = {"c.k": ["FAIL", "FAIL"]}
    flaky_comp = {"c.k": ["PASS", "FAIL"]}
    m_flaky = measure(flaky_bare, flaky_comp)
    expect("a check that moves between rounds is flaky, not improved",
           m_flaky["flaky"] == ["c.k"] and m_flaky["improved"] == [])
    expect("and a DECLARED improvement that turns flaky is reported as lost",
           any("NO LONGER IMPROVE" in f for f in evaluate(
               "c", {"total": 1, "composed": m_flaky["composed"], "bare": m_flaky["bare"],
                     "improved": ["c.k"]}, m_flaky)))

    # ── a tally mismatch, which is the cheap half and still has to fire.
    expect("a wrong tally fails",
           any("tally" in f for f in evaluate(
               "history", dict(declared, composed={"PASS": 99}), m_before)))

    # ── the zero-severity normalisation, in both directions.
    expect("a declared zero and an absent severity agree",
           evaluate("history", dict(declared, composed=dict(m_before["composed"], SKIP=0)),
                    m_before) == [])

    # ── REFUSALS. An instrument that can only say PASS or FAIL has no way to say
    # ── "I did not measure anything", and that is the state it will be in the day it breaks.
    try:
        arm_state([Path("/nonexistent-report.json")])
        expect("a missing report REFUSES", False)
    except (Refusal, OSError):
        expect("a missing report REFUSES", True)

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        empty = Path(d) / "bare-history-1.json"
        empty.write_text('{"checks": []}')
        try:
            arm_state([empty])
            expect("a report parsing to zero checks REFUSES", False)
        except Refusal:
            expect("a report parsing to zero checks REFUSES", True)

        # Round ORDER is numeric, not lexical: `-10` after `-2`. A wrong order makes
        # `provenance()` red on a run that is fine, which is a false red on the guard whose
        # whole argument is that a false red costs the instrument.
        for r in (1, 2, 10):
            (Path(d) / f"bare-history-{r}.json").write_text('{"checks": []}')
        expect("rounds sort numerically (-10 after -2)",
               [p.name for p in rounds_for(Path(d), "bare", "history")]
               == ["bare-history-1.json", "bare-history-2.json", "bare-history-10.json"])

    # ── the corpus assertion (D15 clause 2): the real tree must be parseable, and the
    # ── declared stems must be a set this gate could ever see.
    comps = compositions()
    expect(f"the real tree has compositions to walk ({len(comps)})", len(comps) >= 2)
    expect("every composition declares at least one gate stem",
           all(stems_of(tomllib.loads(p.read_text(encoding='utf-8'))) for p in comps))

    print()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
