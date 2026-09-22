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

  ./tools/diff-arms.py --bare r1-bare.json r2-bare.json \\
                       --composed r1-composed.json r2-composed.json
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
    ap.add_argument("--bare", nargs="+", required=True, help="one report per round")
    ap.add_argument("--composed", nargs="+", required=True, help="one report per round")
    args = ap.parse_args()

    if len(args.bare) != len(args.composed):
        raise SystemExit("--bare and --composed need the same number of rounds")
    rounds = len(args.bare)

    bare = collect(args.bare)
    composed = collect(args.composed)

    for r in range(rounds):
        print(f"round {r + 1}  bare     {json.dumps(tally(bare, r), sort_keys=True)}  checks={len(bare)}")
        print(f"round {r + 1}  composed {json.dumps(tally(composed, r), sort_keys=True)}  checks={len(composed)}")
    print()

    regressions: list[str] = []
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

    print()
    print(f"ROUNDS: {rounds}")
    print(f"REGRESSIONS ATTRIBUTABLE TO THE COMPOSITION: {len(regressions)}")
    print(f"IMPROVEMENTS: {len(improvements)}   FLAKY: {len(flaky)}")
    return 1 if regressions or lost else 0


if __name__ == "__main__":
    sys.exit(main())
