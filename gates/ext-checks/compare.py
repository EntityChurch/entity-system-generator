#!/usr/bin/env python3
"""gates/ext-checks/compare.py — the arm rule, applied.

Reads each arm's JSON and decides. **This is the only file that produces a verdict**; the
target arms report and never decide, exactly as `chunking-parity`'s arms print fields and
`compare.py` compares them.

THE RULE
--------
An authored check is ADMITTED only if, on the same target and composition:

    composed  ->  pass
    bare      ->  anything but pass

and REJECTED as VACUOUS otherwise. A check that reports the same verdict against a peer
with the extension not installed is measuring something other than the extension. That is
not a hypothetical: four of the thirteen checks in the oracle's own `content` category pass
in the bare arm — they measure `entity-core-go`'s in-process library, and the report's
`summary.self_checks` reads `0` (AP-19, D13's Reach layer one domain over). We found it by
running the oracle's checks against a peer with no content extension, which is the same
experiment this file automates for our own.

**Vacuous is a FAILURE, not a warning.** A vacuous check is worse than a missing one: it
occupies the row in `[conformance]` that would otherwise read `none`, so it converts a known
gap into a false claim of coverage.

WHAT THIS IS NOT
----------------
Not a conformance verdict, ever. Kind C under keystone's `VERIFICATION-ARCHITECTURE.md`,
under the operator's standing condition that **an official green requires the suite we do
not author**. A composed-arm failure here is a finding to investigate and, if it disagrees
with the oracle, to ROUTE — never a private disagreement, because a silently divergent test
set manufactures a second de-facto standard.

AND TWO OUTCOMES THAT ARE NEITHER
---------------------------------
    N/A            the check drives a FACE the composition declares `not-installable`.
                   D13, amended: `<peer> is a host` is not a proposition, `<peer> hosts
                   <face>` is. Not a skip — declared, counted, printed, and disprovable.
    CONTRADICTION  the check PASSED on a face declared impossible. A failure: one of the
                   two is wrong and the executed one is not the declaration.

A target with NO arm is printed with the count of checks an arm there WOULD measure, from
the faces its composition declares. `rust` currently reads 0 of 3, because every check
authored so far drives the handler face and that peer cannot host a handler body — which
makes it a gap in the CHECKS rather than in the arms, and says so in the gate's own output.

REFUSALS
--------
  * fewer than two arms for a (target, composition)          -> REFUSING, rc 3
  * a check drives a face the composition declares nothing about  -> REFUSING, rc 3
  * an arm reporting zero checks                             -> REFUSING, rc 3
  * arms that disagree about WHICH checks ran                -> REFUSING, rc 3
  * fewer than `--min-checks` definitions covered            -> REFUSING, rc 3

The last one is keystone's `check-set-gate` lesson in miniature: a comparison is only
meaningful over a known set, and a set that silently shrank reports a clean run.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import MIN_CHECKS, SchemaError, ecf_decoder, load_checks  # noqa: E402

# The arms report in canonical ECF, so the comparer decodes with the same declared codec the
# corpus was encoded with (`tools/tooling.toml [ecf_codec]`). LAZY, because `--self-test` and
# every schema path must keep working on a host that has no codec at all: the import pulls the
# peer's Ed25519 dependency through its package `__init__`, which is why the gate's decoding
# steps run in a container. Recorded as a finding, not worked around
# (`docs/DESIGN-THE-CBOR-INTERCHANGE-LAYER.md` §3).
_decode = None


def ecf_decode(blob: bytes):
    global _decode
    if _decode is None:
        _decode = ecf_decoder()
    return _decode(blob)


def decide(composed_verdict: str, bare_verdict: str, face_state: str | None = None) -> str:
    """THE ARM RULE, in one place.

    Module-level so `--self-test` drives THIS and not a copy. The first draft of
    `req-coverage`'s control exercised a re-implementation of its rules, which proves only
    that the copy can go red — the same shape as an instrument reading a quantity its own
    execution wrote (D19). Once is a slip; twice in one session would be a habit.

    `face_state` is the composition's declared state for the face this check drives, and it
    is D13's amendment reaching this axis: `<peer> is a host` is not a proposition,
    `<peer> hosts <face>` is. A target whose composition declares the face
    `not-installable` is not a target the check fails on — it is one the check does not
    range over, and calling that `failed` would report a substrate fact as a defect.

    **`not-applicable` is not a skip.** A skip counts as a failure (ADR-0012); this is a
    declared, counted, printed exclusion whose declaration lives in `[system.faces]`, was
    measured by an executed probe (D13), and is contradicted by the check's own evidence if
    it is wrong — see `contradiction`. A check that PASSES on a face declared impossible has
    disproved the declaration, and that is a finding rather than a pass.
    """
    if face_state == "not-installable":
        return "contradiction" if composed_verdict == "pass" else "not-applicable"
    if composed_verdict == "pass" and bare_verdict != "pass":
        return "admitted"
    if composed_verdict == "pass" and bare_verdict == "pass":
        return "vacuous"
    return "failed"


def face_state(target: str, comp: str, extension: str, face: str) -> str | None:
    """`[system.faces].<EXT>.<face>` from the composition that was run.

    Read from the COMPOSITION rather than from the check or the arm, because the face state
    is a fact about (peer × face) and the composition is the only artifact that names both.
    A path template over `languages/<t>/compositions/<c>/` names no specific target, so this
    stays in the neutral half (D20).

    Returns None when nothing is declared, which the caller turns into a REFUSAL rather than
    a default: a missing declaration read as "installed" would make every N/A silently
    become a failure the day someone forgets the block, and read as "not-installable" would
    make it silently become an exclusion. Neither guess is safe.
    """
    path = ROOT / "languages" / target / "compositions" / comp / "SYSTEM.toml"
    if not path.is_file():
        return None
    faces = tomllib.loads(path.read_text()).get("system", {}).get("faces", {})
    return (faces.get(extension.upper()) or {}).get(face)


def reachable(target: str, comp: str, defs: list[dict]) -> tuple[list[str], list[str]]:
    """(checks an arm on this target COULD measure, checks whose face is undeclared).

    Module-level so `--self-test` drives THIS and not the loop that prints it. It answers
    *"why has nobody built this arm"* from the tree rather than from prose, and it flips on
    its own the day a check is authored for a face the target hosts — which is what stops
    `an arm would measure 0` from becoming a standing excuse.
    """
    states = [(d["id"], face_state(target, comp, d["id"].split("/")[0], d["face"])) for d in defs]
    return ([i for i, st in states if st not in ("not-installable", None)],
            [i for i, st in states if st is None])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("reports", nargs="*", help="arm JSON files")
    ap.add_argument("--min-checks", type=int, default=MIN_CHECKS)
    ap.add_argument("--expect-arms", default="",
                    help="comma-separated targets that MUST have reported, both arms")
    ap.add_argument("--composition", default="content-history",
                    help="the composition a no-arm target would be measured in, for the "
                         "reachable-cell count")
    ap.add_argument("--all-targets", default="",
                    help="every target in the tree, so a target with NO arm is printed "
                         "rather than silently outside the denominator")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    # The definitions are validated BEFORE any verdict is read. An arm that ran against a
    # malformed corpus produced numbers about something we cannot describe.
    try:
        defs = load_checks()
    except SchemaError as e:
        print(f"REFUSING: {e}", file=sys.stderr)
        return 3
    print(f"ext-checks: {len(defs)} definitions "
          f"({sum(1 for d in defs if d['level'] == 'MUST')} MUST), "
          f"{len(args.reports)} arm reports")

    arms: dict[tuple[str, str], dict] = {}
    for p in args.reports:
        doc = ecf_decode(Path(p).read_bytes())
        arms[(doc["target"], doc["composition"], doc["arm"])] = doc

    pairs = sorted({(t, c) for t, c, _ in arms})
    if not pairs:
        print("REFUSING: no arm reports. A verdict over zero runs is not a verdict.",
              file=sys.stderr)
        return 3

    # NO SILENT CAPS, and this refusal was earned on this instrument's first multi-arm run.
    # The `typescript` arm died before writing anything (an unresolvable package specifier),
    # and the comparer printed `EXT-CHECKS: OK` over the one arm that survived — a narrower
    # verdict reported as a clean one, which is the exact failure `gates/README.md` names and
    # `chunking-parity` already guards with `--min-ports`. The runner knows which arms exist
    # because the Makefile globs them; passing that list is what turns a missing arm from
    # invisible into a REFUSAL.
    expected = [t for t in args.expect_arms.split(",") if t]
    reported = {t for t, _, _ in arms}
    missing = [t for t in expected if t not in reported]
    if missing:
        print(f"REFUSING: {len(missing)} of {len(expected)} expected arms produced no report: "
              f"{', '.join(missing)}. An arm that died is not an arm that passed, and a "
              f"verdict over the survivors is a narrower measurement reported as a clean one.",
              file=sys.stderr)
        return 3

    # NO SILENT CAPS, ONE LEVEL UP. `--expect-arms` catches an arm that DIED; nothing
    # caught a target that has no arm at all, and the axis has reported `6 of 6 admitted`
    # over two of the tree's three targets with the third's absence invisible. An arm is
    # work and its absence is not a failure — but a coverage number printed without its
    # denominator is the AP-20 shape, and this is that denominator.
    all_targets = [t for t in args.all_targets.split(",") if t]
    no_arm = [t for t in all_targets if t not in reported]
    buildable: list[str] = []
    if no_arm:
        print(f"\nNO ARM: {len(no_arm)} of {len(all_targets)} target(s) are not measured by "
              f"this axis at all: {', '.join(no_arm)}")
        # AND WHAT AN ARM WOULD MEASURE, which is the question "why has nobody built it"
        # answered by the tree instead of by prose. The composition already declares each
        # face's state, so the reachable cell count is computable without the arm existing.
        # It flips on its own the day a check is authored for a face the target hosts,
        # which is what keeps this from becoming a standing excuse.
        comp_of = args.composition
        for t in no_arm:
            reach, unknown = reachable(t, comp_of, defs)
            if unknown:
                print(f"  {t}: cannot say — {len(unknown)} check(s) drive a face "
                      f"{comp_of} declares nothing about")
            elif reach:
                buildable.append(t)
                print(f"  {t}: AN ARM WOULD MEASURE {len(reach)} of {len(defs)} check(s) "
                      f"({', '.join(reach)}) — this target is worth an arm now")
            else:
                by_face = sorted({d["face"] for d in defs})
                print(f"  {t}: an arm would measure 0 of {len(defs)} — every authored check "
                      f"drives a face this composition declares not-installable "
                      f"({', '.join(by_face)}). Not a gap in the arms; a gap in the CHECKS, "
                      f"and it closes when one is authored for a face this target hosts.")

    failures: list[str] = []
    refusals: list[str] = []
    admitted = 0
    not_applicable: list[str] = []

    for target, comp in pairs:
        composed = arms.get((target, comp, "composed"))
        bare = arms.get((target, comp, "bare"))
        print(f"\n=== {target} / {comp} ===")
        if composed is None or bare is None:
            refusals.append(
                f"{target}/{comp}: only the "
                f"{'composed' if bare is None else 'bare'} arm ran. The arm rule needs both, "
                f"and a one-armed run cannot tell a working check from a vacuous one."
            )
            continue

        cverd = {c["id"]: c for c in composed["checks"]}
        bverd = {c["id"]: c for c in bare["checks"]}
        if not cverd or not bverd:
            refusals.append(f"{target}/{comp}: an arm reported zero checks")
            continue
        if set(cverd) != set(bverd):
            refusals.append(
                f"{target}/{comp}: the arms ran different check sets "
                f"(composed-only {sorted(set(cverd) - set(bverd))}, "
                f"bare-only {sorted(set(bverd) - set(cverd))})"
            )
            continue
        if len(cverd) < args.min_checks:
            refusals.append(
                f"{target}/{comp}: {len(cverd)} checks, below --min-checks={args.min_checks}"
            )
            continue

        by_id = {d["id"]: d for d in defs}
        for cid in sorted(cverd):
            c, b = cverd[cid], bverd[cid]
            cv, bv = c["verdict"], b["verdict"]
            face = by_id.get(cid, {}).get("face")
            ext = cid.split("/")[0]
            fs = face_state(target, comp, ext, face) if face else None
            if face and fs is None:
                refusals.append(
                    f"{target}/{comp} {cid}: the check drives the {face!r} face and the "
                    f"composition declares no [system.faces].{ext.upper()}.{face}. Neither "
                    f"default is safe — read as installed it turns an inapplicable target "
                    f"into a failure, read as not-installable it turns a real failure into "
                    f"an exclusion."
                )
                continue
            outcome = decide(cv, bv, fs)
            if outcome == "not-applicable":
                not_applicable.append(f"{target}/{cid}")
                print(f"  N/A       {cid:42s} composed={cv:5s} bare={bv:5s} "
                      f"[{ext}.{face} = not-installable]")
            elif outcome == "contradiction":
                failures.append(
                    f"{target}/{comp} {cid}: CONTRADICTION — the composition declares "
                    f"[system.faces].{ext.upper()}.{face} = \"not-installable\" and the "
                    f"check PASSED against it. One of the two is wrong, and the executed "
                    f"one is not the declaration (D13: source reads decide what to build, "
                    f"they never decide what is true)."
                )
                print(f"  CONTRADICT{cid:42s} composed=pass on a face declared impossible")
            elif outcome == "admitted":
                admitted += 1
                print(f"  ADMITTED  {cid:42s} composed=pass  bare={bv}")
            elif outcome == "vacuous":
                failures.append(
                    f"{target}/{comp} {cid}: VACUOUS — passes with the extension NOT "
                    f"installed, so it is measuring something else. That is the shape four "
                    f"of the oracle's thirteen `content` checks have (AP-19), and it is a "
                    f"failure here rather than a note because a vacuous check occupies the "
                    f"[conformance] row that would otherwise honestly read `none`."
                )
                print(f"  VACUOUS   {cid:42s} composed=pass  bare=pass")
            else:
                detail = c.get("error") or _first_failed(c)
                failures.append(f"{target}/{comp} {cid}: composed={cv} — {detail}")
                print(f"  FAILED    {cid:42s} composed={cv}  bare={bv}")
                for a in c.get("assertions", []):
                    if not a["ok"]:
                        print(f"              {a['kind']}: {a['detail']}")
                        if a.get("why"):
                            print(f"                why: {a['why'][:100]}")

    # THE DENOMINATOR, SPELLED OUT. `admitted / (checks x pairs)` alone reads as coverage;
    # it is coverage of the targets that have an arm, minus the cells a substrate cannot
    # host. Both subtractions are printed so the number can never be read as more than it is.
    total_cells = len(defs) * len(pairs)
    print(f"\nadmitted: {admitted} of {total_cells} (check x arm-pair)"
          f"{f', {len(not_applicable)} N/A (face not installable)' if not_applicable else ''}"
          f"{f', {len(no_arm)} target(s) with no arm' if no_arm else ''}")
    if not_applicable:
        print("  N/A cells: " + ", ".join(not_applicable))

    if refusals:
        print("\nREFUSING:", file=sys.stderr)
        for r in refusals:
            print(f"  {r}", file=sys.stderr)
        return 3
    if failures:
        print(f"\nEXT-CHECKS: {len(failures)} failing.", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("EXT-CHECKS: OK — every authored check passes composed and fails bare.")
    return 0


def _first_failed(c: dict) -> str:
    for a in c.get("assertions", []):
        if not a["ok"]:
            return f"{a['kind']}: {a['detail']}"
    return "no assertion failed but the verdict is not pass"


def real_ids(defs: list[dict]) -> list[str]:
    return [d["id"] for d in defs]


def self_test() -> int:
    """The comparer's own controls. Both directions and one refusal, over synthetic arms."""
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {label}")
        ok = ok and cond

    verdicts = decide

    expect("composed=pass bare=fail  -> ADMITTED", verdicts("pass", "fail") == "admitted")
    expect("composed=pass bare=error -> ADMITTED", verdicts("pass", "error") == "admitted")
    expect("composed=pass bare=pass  -> VACUOUS (the AP-19 shape)",
           verdicts("pass", "pass") == "vacuous")
    expect("composed=fail            -> FAILED", verdicts("fail", "fail") == "failed")
    expect("composed=error           -> FAILED", verdicts("error", "fail") == "failed")

    # ── D13's face amendment on this axis, both directions.
    expect("face not-installable, composed=fail  -> N/A, not FAILED",
           verdicts("fail", "fail", "not-installable") == "not-applicable")
    expect("face not-installable, composed=pass  -> CONTRADICTION, not admitted",
           verdicts("pass", "fail", "not-installable") == "contradiction")
    expect("face installed          -> the ordinary rule still applies",
           verdicts("pass", "fail", "installed") == "admitted")
    expect("face not-INSTALLED (a composition's choice) is NOT an exclusion",
           verdicts("fail", "fail", "not-installed") == "failed")
    expect("no face state given     -> the ordinary rule (the caller REFUSES instead)",
           verdicts("fail", "fail", None) == "failed")

    # The face state is read from the real tree, and the value this axis turns on is the
    # one `rust` actually declares. A control over a synthetic string would prove the
    # string compares; this proves the composition says what the amendment says it says.
    rs = face_state("rust", "content-history", "content", "handler")
    expect(f"rust/content-history declares CONTENT.handler = {rs!r} (measured, D13)",
           rs == "not-installable")
    ts = face_state("typescript", "content-history", "content", "handler")
    expect(f"typescript/content-history declares CONTENT.handler = {ts!r}",
           ts == "installed")
    expect("an undeclared (target, composition) reads None, never a default",
           face_state("nosuchtarget", "content-history", "content", "handler") is None)

    # ── the no-arm reachability computation, over the real tree, both directions.
    #
    # THIS CONTROL ASSERTED A STATE AND HAD TO BE REWRITTEN AS A PROPERTY, on 2026-09-08, the
    # day the state changed. It read `r_reach == []` with the message "every authored check is
    # handler-face" — true when it was written and false the moment a check was authored for a
    # face `rust` hosts, which is the event the whole `NO ARM` block exists to announce. So the
    # gate's own control went red on the gate working as designed: a false red, on the newest
    # thing in the file, with an obvious-looking fix (re-bless the `0`) that would have
    # suppressed the trigger permanently. AP-23's second day, one axis over.
    #
    # The property, which does not move when the corpus does: on this peer a check is reachable
    # exactly when its face is not the one the composition declares `not-installable`.
    real = load_checks()
    r_reach, r_unknown = reachable("rust", "content-history", real)
    r_expected = [d["id"] for d in real
                  if face_state("rust", "content-history", d["id"].split("/")[0], d["face"])
                  != "not-installable"]
    expect(f"an arm on `rust` would measure {len(r_reach)} of {len(real)} — exactly the checks "
           f"whose face that composition does not declare not-installable",
           r_reach == r_expected and r_unknown == [])
    expect("…and the handler-face checks are the excluded ones, by face and not by count",
           {d["id"] for d in real if d["face"] == "handler"} == set(real_ids(real)) - set(r_reach))
    t_reach, t_unknown = reachable("typescript", "content-history", real)
    expect(f"an arm on `typescript` reaches all {len(t_reach)} — the same computation, "
           f"the other answer",
           len(t_reach) == len(real) and t_unknown == [])
    _, u = reachable("nosuchtarget", "content-history", real)
    expect("an undeclared target reads UNKNOWN, never 0-reachable",
           len(u) == len(real))

    try:
        checks = load_checks()
        expect("the real definitions validate", True)
        expect("every real definition names a face in the vocabulary",
               all(c.get("face") in ("types", "emit_consumer", "sdk", "handler")
                   for c in checks))
    except SchemaError as e:
        expect(f"the real definitions validate ({e})", False)

    print()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
