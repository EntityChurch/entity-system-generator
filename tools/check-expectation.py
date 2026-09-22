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
    total       the oracle's declared check count for that stem
    composed    the composed arm's severity tally
    bare        the bare arm's severity tally
    improved    THE NAMED SET of checks that move bare -> composed

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

def evaluate(stem: str, declared: dict, measured: dict, straddles: dict | None = None) -> list[str]:
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


def check_one(path: Path) -> tuple[list[str], list[str], dict]:
    """(failures, refusals, measured-by-stem) for one composition. No reports at all is
    neither: it is `{}`, counted by the caller and reported."""
    system = tomllib.loads(path.read_text(encoding="utf-8"))
    reports = path.parent.parent.parent / "output" / path.parent.name / "reports"
    baseline = system.get("gate", {}).get("baseline", {})
    straddles = diff_arms.declared_straddles(str(path))
    failures: list[str] = []
    refusals: list[str] = []
    out: dict[str, dict] = {}
    comp = _rel(path.parent)

    for stem in stems_of(system):
        bare_p, composed_p = rounds_for(reports, "bare", stem), rounds_for(reports, "composed", stem)
        if not bare_p and not composed_p:
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
        failures += [f"{comp}: {f}" for f in evaluate(stem, declared, m, straddles)]

    for stem in sorted(set(baseline) - set(stems_of(system))):
        failures.append(f"{comp}: [gate.baseline.{stem}] declares a stem [gate] does not "
                        f"list. A baseline for something nothing runs is never checked.")
    return failures, refusals, out


def _inline(counts: dict[str, int]) -> str:
    return "{ " + ", ".join(f"{k} = {counts[k]}" for k in SEVERITIES if counts.get(k)) + " }"


def bless(comp: str, stem: str, m: dict) -> str:
    names = "\n".join('  "%s",' % k for k in m["improved"])
    return (
        f"# ── {comp}\n"
        f"[gate.baseline.{stem}]\n"
        f'measured = "{m["timestamp"][:10]}"   # {m["rounds"]} round(s)\n'
        f"total    = {m['total']}\n"
        f"composed = {_inline(m['composed'])}\n"
        f"bare     = {_inline(m['bare'])}\n"
        f"improved = [\n{names}\n]\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--require", action="append", default=[],
                    help="a composition path that MUST have reports (no silent caps)")
    ap.add_argument("--bless", action="store_true", help="print the TOML for what is measured now")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    comps = compositions()
    if not comps:
        print("REFUSING: no compositions found. A clean verdict over an empty tree is not "
              "a clean verdict.", file=sys.stderr)
        return 3

    failures: list[str] = []
    refusals: list[str] = []
    measured_comps: list[str] = []
    blessed: list[str] = []

    for path in comps:
        comp = _rel(path.parent)
        f, r, out = check_one(path)
        failures += f
        refusals += r
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
                blessed.append(bless(comp, stem, m))

    # THE SCOPE OF EVERY CLAIM BELOW, printed before the verdict.
    print(f"\nmeasured: {len(measured_comps)} of {len(comps)} compositions")

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

    m_before = measure(*arms(bare, before))
    declared = {"total": 2, "composed": m_before["composed"], "bare": m_before["bare"],
                "improved": m_before["improved"]}
    expect("the baseline it was blessed from holds", evaluate("history", declared, m_before) == [])

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
