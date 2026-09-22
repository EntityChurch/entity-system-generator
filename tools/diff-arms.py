#!/usr/bin/env python3
"""diff-arms.py — bare peer vs composed peer, check by check, over N rounds.

**The instrument for our own second failure mode**, which is one keystone never has:
*the peer was right and we broke it.* An extension installs into a live peer, writes
its tree, and shares its dispatch table; a regression it causes shows up as a CORE
check failing, in a category that has nothing to do with the extension.

It also settles "pre-existing", which is a claim and not an excuse. ADR-0012 forbids
labelling a failure pre-existing without bisecting. Two arms, same oracle, same flags,
same container, one variable, and the answer is a diff rather than an assertion.

**WHY ROUNDS.** The first version compared one report per arm and, on its second
execution, reported `concurrency.t1_1_concurrent_demux` as a REGRESSION. It was not.
That check suppresses its parallel-speedup signal when the sequential baseline lands
under a 50 ms floor; the bare arm measured 49.80 ms and got the free pass, the composed
arm measured 50.85 ms and got the signal evaluated. **One millisecond of wall clock,
and the arms had swapped sides since the previous run.** A single-round diff cannot
tell a flaky check from a regression, and the failure mode is the expensive direction:
it manufactures a regression that is not there, and the next person learns to ignore
the tool.

So a check is a REGRESSION only when it is PASS on bare in EVERY round and non-PASS on
composed in EVERY round. A check whose own verdict moves between rounds *within* an arm
is FLAKY and is reported as such — never as clean, and never as ours.

**AND A SET OF ROUNDS MUST BE ONE RUN** (AP-22). A round is identified by its FILENAME,
and the driver overwrites `<arm>-<cat>-<r>.json` in place — so a `ROUNDS=1` run leaves the
previous run's `-2.json` untouched and the next `ROUNDS=2` diff reads a report hours older
than round 1 as *"round 2 of this run"*. When the two runs straddle a real change, the
flakiness rule above — written to absorb a one-millisecond timing straddle — absorbs the
regression instead and files it as belonging to neither arm. That is how
`history/w6_caller_cap_absent` presented: `composed=FAIL/PASS`, printed as `FLAKY: 1`,
which reads as noise.

The refusal is exact and needs no threshold. A run writes round 1 before round 2, so
**an arm's report timestamps are non-decreasing in round order**; a decrease means at least
one of the files was written by a different run. Twelve of the tree's thirty-four round-sets
were in that state when the check was written.

  ./tools/diff-arms.py --bare r1-bare.json r2-bare.json \\
                       --composed r1-composed.json r2-composed.json
  ./tools/diff-arms.py --self-test          # the control
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: Path) -> dict[str, str]:
    """Flatten a validate-peer JSON report to `category.check -> severity`.

    The report is a FLAT `checks` list, each entry carrying its own `category` and
    `severity` — not a nested categories tree, and not a `status` key. Written against
    the nested shape first, and the refusal below is what caught it on the first run
    rather than letting it print a clean diff over zero checks. That is the whole
    reason the refusal exists: an empty diff reads as "no regressions".
    """
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for check in doc.get("checks", []) or []:
        key = f"{check.get('category', '?')}.{check.get('name', '?')}"
        out[key] = str(check.get("severity", check.get("status", "?"))).upper()
    if not out:
        raise SystemExit(
            f"{path}: parsed 0 checks -- report shape not recognised, "
            "refusing to report a clean diff"
        )
    return out


def messages(paths: list[str], keys: set[str]) -> dict[str, list[str]]:
    """`category.check -> [message per round]`, for the named keys only.

    Kept separate from `load()` on purpose: `load()` produces the quantity the VERDICT is
    computed from and stays a severity map, so nothing in the decision path can start
    depending on another team's message strings. This is for putting numbers in front of a
    reader, never for deciding.
    """
    out: dict[str, list[str]] = {k: [] for k in keys}
    for p in paths:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        found = {f"{c.get('category', '?')}.{c.get('name', '?')}": c.get("message", "")
                 for c in doc.get("checks", []) or []}
        for k in keys:
            out[k].append(found.get(k, "(absent)"))
    return out


def declared_straddles(system_toml: str | None) -> dict[str, dict]:
    """`[[gate.straddle]]` — checks whose VERDICT is decided by a threshold the two arms
    straddle, declared per composition.

    WHY THIS IS NOT A SUPPRESSION FLAG. The rounds rule above handles NOISE: a check whose
    verdict moves between rounds belongs to neither arm. It does nothing about BIAS. A
    composed peer is genuinely a little slower than a bare one — it has more installed — and
    when the oracle's verdict turns on a fixed floor that the two arms land on either side
    of, the difference is real, stable across every round, and says nothing about the
    property the check is named for. More rounds cannot separate them; only the floor can.

    Measured, not argued: `concurrency.t1_1_concurrent_demux` suppresses its speedup signal
    when the sequential baseline lands under a 50 ms floor. On `typescript` the baseline is
    49.2 ms bare and 52.8 ms composed, and the verdict is PASS vs WARN in every round. On
    `python`, the SAME composition and the same two extensions, the baseline is 9.0 ms bare
    and 10.9 ms composed — the same ~3 ms — and both arms PASS. The verdict is a function of
    the target's absolute speed against a fixed constant.

    So a declaration is narrow and it is loud: it names ONE check, it carries the routing
    packet that sends the finding to whoever owns the floor (which `make citations` then
    forces to exist, D18), and BOTH ARMS' MESSAGES ARE PRINTED ON EVERY RUN so the numbers
    stay in front of a reader instead of behind a flag. `--strict-straddle` promotes them
    back to regressions, and it is the switch that gets flipped when the floor is fixed.
    """
    if not system_toml:
        return {}
    import tomllib
    doc = tomllib.loads(Path(system_toml).read_text(encoding="utf-8"))
    out = {}
    for entry in doc.get("gate", {}).get("straddle", []) or []:
        if "check" not in entry or "routed" not in entry:
            raise SystemExit(
                f"{system_toml}: a [[gate.straddle]] entry needs both `check` and `routed`. "
                "A declaration with no destination is a suppression."
            )
        out[entry["check"]] = entry
    return out


def stamps(paths: list[str]) -> list[str]:
    """Each report's own `timestamp`, in the round order it was handed to us.

    Missing is `""` and sorts before everything, so an older report format cannot make
    `provenance()` red — a false red costs the instrument (D15/AP-4).
    """
    out = []
    for p in paths:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        out.append(str(doc.get("timestamp", "")))
    return out


def provenance(arm: str, paths: list[str], ts: list[str]) -> str | None:
    """The AP-22 refusal: these rounds are not one run.

    Module-level and returning the message rather than printing it, so `--self-test`
    drives THIS function and not a re-implementation of it. A control that exercises a
    copy proves the copy can go red (D19, and the habit named in
    `HANDOFF-2026-09-07-c` §A4).

    The invariant is threshold-free: a run writes round 1 before round 2, so an arm's
    timestamps are non-decreasing in round order. A decrease means one of these files was
    written by a different run, and a diff across two runs is not a diff across two arms.
    """
    for i in range(1, len(ts)):
        if ts[i] and ts[i - 1] and ts[i] < ts[i - 1]:
            return (
                f"{arm}: round {i + 1} is OLDER than round {i} "
                f"({ts[i]} < {ts[i - 1]}).\n"
                f"    round {i}:   {paths[i - 1]}\n"
                f"    round {i + 1}: {paths[i]}\n"
                f"  These rounds are not one run. The driver overwrites a report in place, so a "
                f"ROUNDS=1 run leaves the previous run's later rounds on disk and this diff "
                f"would read one of them as a round of this one. The flakiness rule would then "
                f"absorb a real regression and report it as belonging to neither arm (AP-22). "
                f"Re-run `make conformance` / `make regression` for this composition."
            )
    return None


def collect(paths: list[str]) -> dict[str, list[str]]:
    """`category.check -> [severity per round]`."""
    rounds = [load(Path(p)) for p in paths]
    keys = set().union(*(set(r) for r in rounds))
    return {k: [r.get(k, "-") for r in rounds] for k in keys}


def stable(values: list[str]) -> str | None:
    """The one severity this check reported in every round, or None if it moved."""
    return values[0] if len(set(values)) == 1 else None


def tally(arm: dict[str, list[str]], index: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for values in arm.values():
        counts[values[index]] = counts.get(values[index], 0) + 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bare", nargs="+", default=[], help="one report per round")
    ap.add_argument("--composed", nargs="+", default=[], help="one report per round")
    ap.add_argument("--self-test", action="store_true", help="the control (AP-22)")
    ap.add_argument("--straddle", default=None,
                    help="the composition's SYSTEM.toml, for [[gate.straddle]] (AP-23)")
    ap.add_argument("--strict-straddle", action="store_true",
                    help="promote every declared straddle back to a regression")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.bare or not args.composed:
        raise SystemExit("--bare and --composed are required (or --self-test)")

    if len(args.bare) != len(args.composed):
        raise SystemExit("--bare and --composed need the same number of rounds")
    rounds = len(args.bare)

    # BEFORE any verdict. A diff computed over two runs is not a diff, and printing the
    # tally first would put a number in front of a reader that the next line retracts.
    bare_ts, composed_ts = stamps(args.bare), stamps(args.composed)
    stale = [m for m in (provenance("bare", args.bare, bare_ts),
                         provenance("composed", args.composed, composed_ts)) if m]
    if stale:
        print("REFUSING — the rounds are not one run:", file=sys.stderr)
        for m in stale:
            print(f"  {m}", file=sys.stderr)
        return 3

    bare = collect(args.bare)
    composed = collect(args.composed)

    # The timestamp is printed on every round line, not only when the refusal fires. The
    # refusal catches an out-of-ORDER run; two rounds that are merely stale together are
    # in order and only a reader can notice.
    for r in range(rounds):
        print(f"round {r + 1}  bare     {json.dumps(tally(bare, r), sort_keys=True)}  "
              f"checks={len(bare)}  {bare_ts[r] or '(no timestamp)'}")
        print(f"round {r + 1}  composed {json.dumps(tally(composed, r), sort_keys=True)}  "
              f"checks={len(composed)}  {composed_ts[r] or '(no timestamp)'}")
    print()

    straddles = declared_straddles(args.straddle)
    regressions: list[str] = []
    straddled: list[str] = []
    flaky: list[str] = []
    improvements: list[str] = []

    for key in sorted(set(bare) & set(composed)):
        b, c = stable(bare[key]), stable(composed[key])
        if b is None or c is None:
            if b != c or b is None:
                flaky.append(key)
            continue
        if b == c:
            continue
        if b == "PASS":
            if key in straddles and not args.strict_straddle:
                straddled.append(key)
                print(f"STRADDLE   {key}: bare={b} composed={c}  (DECLARED, not counted "
                      f"as a regression -- {straddles[key]['routed']})")
            else:
                regressions.append(key)
                print(f"REGRESSION {key}: bare={b} composed={c}  (every round)")
        else:
            improvements.append(key)
            print(f"improved   {key}: bare={b} composed={c}")

    for key in sorted(set(composed) - set(bare)):
        print(f"new        {key}: composed={composed[key]}  (exists only with the extension installed)")
    lost = sorted(set(bare) - set(composed))
    for key in lost:
        print(f"lost       {key}: bare={bare[key]}  (check disappeared under composition -- investigate)")

    if flaky:
        print()
        print(f"{len(flaky)} check(s) MOVED BETWEEN ROUNDS -- flaky, not attributable to either arm:")
        for key in flaky:
            print(f"  {key}: bare={'/'.join(bare[key])} composed={'/'.join(composed[key])}")

    # Anything the bare peer already fails is the PEER'S, measured rather than assumed.
    pre_existing = sorted(k for k, v in bare.items() if stable(v) not in ("PASS", "SKIP", None))
    if pre_existing:
        print()
        print(f"{len(pre_existing)} check(s) non-PASS on the BARE peer in every round -- not ours, and now measured:")
        for key in pre_existing:
            print(f"  {bare[key][0]:5} {key}")

    # THE NUMBERS, EVERY RUN, not behind a flag. A declared straddle that stops printing
    # its own evidence is a suppression however it was justified when it was written.
    if straddled or (straddles and not args.strict_straddle):
        print()
        msgs_b = messages(args.bare, set(straddles))
        msgs_c = messages(args.composed, set(straddles))
        for key in sorted(straddles):
            if key not in straddled:
                print(f"DECLARED STRADDLE NOT OBSERVED: {key} — the arms agreed this run. "
                      f"The declaration may be stale; it is not failed, because the "
                      f"condition is load-dependent and a false red costs the instrument.")
                continue
            print(f"DECLARED STRADDLE {key}")
            print(f"  why:    {straddles[key].get('why', '(none given)')}")
            print(f"  routed: {straddles[key]['routed']}")
            for r in range(rounds):
                print(f"  r{r + 1} bare     {msgs_b[key][r]}")
                print(f"  r{r + 1} composed {msgs_c[key][r]}")

    print()
    print(f"ROUNDS: {rounds}")
    print(f"REGRESSIONS ATTRIBUTABLE TO THE COMPOSITION: {len(regressions)}")
    print(f"IMPROVEMENTS: {len(improvements)}   FLAKY: {len(flaky)}   "
          f"DECLARED STRADDLES: {len(straddled)}")
    return 1 if regressions or lost else 0


def self_test() -> int:
    """Both directions on `provenance()`, plus the shape the live tree was actually in.

    The negative control is not synthetic in origin: `composed-history-1.json` at 17:41 and
    `composed-history-2.json` at 13:05 is the pair that was on disk on 2026-09-07, and the
    diff over it printed `IMPROVEMENTS: 32   FLAKY: 1` with the 1 being a real regression.
    """
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {label}")
        ok = ok and cond

    ordered = ["2026-09-07T13:05:13Z", "2026-09-07T13:05:15Z"]
    reversed_ = ["2026-09-07T17:41:26Z", "2026-09-07T13:05:15Z"]

    expect("rounds in order          -> no refusal",
           provenance("composed", ["r1", "r2"], ordered) is None)
    expect("round 2 older than 1     -> REFUSES (the live 17:41/13:05 pair)",
           provenance("composed", ["r1", "r2"], reversed_) is not None)
    expect("the refusal names the round and both files",
           "round 2" in (provenance("composed", ["a.json", "b.json"], reversed_) or "")
           and "b.json" in (provenance("composed", ["a.json", "b.json"], reversed_) or ""))
    expect("one round                -> nothing to compare, no refusal",
           provenance("bare", ["r1"], ["2026-09-07T13:05:13Z"]) is None)
    expect("a missing timestamp does NOT go red (a false red costs the instrument)",
           provenance("bare", ["r1", "r2"], ["", "2026-09-07T13:05:13Z"]) is None)
    expect("equal timestamps         -> no refusal (a fast target inside one second)",
           provenance("bare", ["r1", "r2"], ordered[:1] * 2) is None)

    # The corpus assertion (D15 clause 2): `load()`'s own refusal is what caught this
    # instrument's first defect, and a self-test that never drives it would leave the
    # tool's oldest guard unexercised.
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write('{"checks": []}')
        empty = fh.name
    try:
        load(Path(empty))
        expect("a report parsing to zero checks REFUSES", False)
    except SystemExit:
        expect("a report parsing to zero checks REFUSES", True)

    # ── the straddle declaration (AP-23), both directions.
    with tempfile.TemporaryDirectory() as d:
        good = Path(d) / "good.toml"
        good.write_text('[[gate.straddle]]\ncheck = "c.k"\nwhy = "w"\nrouted = "r.md"\n')
        expect("a well-formed [[gate.straddle]] parses",
               set(declared_straddles(str(good))) == {"c.k"})
        bad = Path(d) / "bad.toml"
        bad.write_text('[[gate.straddle]]\ncheck = "c.k"\nwhy = "w"\n')
        try:
            declared_straddles(str(bad))
            expect("a straddle with no `routed` REFUSES (a declaration with no "
                   "destination is a suppression)", False)
        except SystemExit:
            expect("a straddle with no `routed` REFUSES (a declaration with no "
                   "destination is a suppression)", True)
        expect("no --straddle argument -> no declarations, and no crash",
               declared_straddles(None) == {})

    print()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
