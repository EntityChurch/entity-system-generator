#!/usr/bin/env python3
"""check-structure.py — the mirror rule, as a gate rather than as a convention.

## What the rule is

The layout is **target-major**: a target is a unified bundle at `languages/<target>/`,
holding its own profile, driver, extension cells, compositions, gate arms and output,
because the people who consume this arrive by language and should be able to read one
directory. What stays at the root is the language-NEUTRAL half of each axis.

**Every artifact belongs to exactly one axis, and a per-target subtree mirrors its
neutral half:**

    extension-contracts/<ext>/EXTENSION.toml   <->  languages/<t>/extensions/<ext>/
    gates/<gate>/                              <->  languages/<t>/gates/<gate>/run
    (no neutral half -- always per target)     <->  languages/<t>/compositions/<c>/SYSTEM.toml

So a cell for an extension with no contract, or a gate arm for a gate that is not in the
axis table, is a defect: it is code nobody declared, in a tree whose whole argument is
that the declaration comes first.

## Why it needs a gate at all

Under the previous extension-major layout the four axes had each independently invented
their own cell shape -- `extensions/<ext>/<lang>/` was a directory, but a gate arm was a
bare `probe.mjs` for two targets and a `rust/` subdirectory for the third, because rust
needed a manifest and nothing said what a gate cell was. At three targets that is an
irritation. At forty it is a special case in every runner.

Target-major fixes the shape by construction, and this file is what stops it drifting
back: the structure is now load-bearing (every `wildcard` in the Makefile reads it), so a
misplaced directory does not look wrong, it silently drops out of a cohort.

## D15, sharpened: a REFUSAL, not only a verdict

An instrument that can only say PASS or FAIL has no way to say *"I did not measure
anything"*, and that is the state it will be in the day it breaks -- a glob that stops
matching reports a clean tree. Five instruments written in this repo, five with a defect
found by running them; the two that caught themselves are the two that shipped with a
refusal. So: zero targets inspected, or a target with nothing under it, REFUSES.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = ROOT / "languages"
CONTRACTS = ROOT / "extension-contracts"
GATES = ROOT / "gates"

#: The per-target subtrees, and what each one mirrors in the neutral half. `compositions`
#: has no neutral half on purpose -- a composition is the third axis, it exists only as
#: (target x extension set), and giving it a root directory would create the one place
#: cross-extension patches could accumulate.
MIRRORED = {
    "extensions": CONTRACTS,
    "gates": GATES,
}


def main() -> int:
    if not LANGUAGES.is_dir():
        print(f"REFUSING: no {LANGUAGES.relative_to(ROOT)}/ -- nothing to check",
              file=sys.stderr)
        return 2

    targets = sorted(p for p in LANGUAGES.iterdir() if p.is_dir())
    if not targets:
        print("REFUSING: 0 targets found. An empty result set is never a clean verdict.",
              file=sys.stderr)
        return 2

    problems: list[str] = []
    checked = 0

    for target in targets:
        name = target.name

        # The profile is what makes a directory a TARGET rather than a directory.
        # `tools/compose.py` checks its fields; this checks that it is there at all, for
        # targets nothing has composed yet.
        if not (target / "profile.toml").exists():
            problems.append(f"{name}: no profile.toml -- a target is the tuple its profile "
                            "declares, and a directory under languages/ that declares "
                            "nothing is not a target")

        # `host-launch` is NOT in this list any more, and its absence is the point:
        # the shared harness moved to `tools/host-launch` and each target keeps only
        # `host-entry`, which says which binary to exec and which environment it
        # needs. 210 code lines of per-target harness became 45.
        for driver in ("build", "test", "host-entry"):
            if not (target / driver).exists():
                problems.append(f"{name}: no `{driver}` driver")

        for subtree, neutral in MIRRORED.items():
            d = target / subtree
            if not d.is_dir():
                continue
            for unit in sorted(p for p in d.iterdir() if p.is_dir()):
                checked += 1
                if not (neutral / unit.name).is_dir():
                    problems.append(
                        f"{name}/{subtree}/{unit.name}: no neutral half at "
                        f"{neutral.relative_to(ROOT)}/{unit.name}/ -- a per-target subtree "
                        "may only hold units the root declares"
                    )
                if subtree == "extensions" and not (neutral / unit.name / "EXTENSION.toml").exists():
                    problems.append(
                        f"{name}/extensions/{unit.name}: "
                        f"{neutral.relative_to(ROOT)}/{unit.name}/EXTENSION.toml is missing "
                        "-- a cell without a contract is code nobody declared"
                    )
                # ONE UNIFORM ENTRY POINT PER (gate x target). The rule the Makefile's
                # `wildcard` depends on: an arm with no `run` is not in the cohort, and
                # dropping out of a cohort is silent.
                if subtree == "gates" and not (unit / "run").exists():
                    problems.append(
                        f"{name}/gates/{unit.name}: no `run` entry point. `gates/README.md` "
                        "-- one runner with the matrix as data; an arm the runner cannot "
                        "call is an arm nobody measures."
                    )

        comps = target / "compositions"
        if comps.is_dir():
            for comp in sorted(p for p in comps.iterdir() if p.is_dir()):
                checked += 1
                if not (comp / "SYSTEM.toml").exists():
                    problems.append(f"{name}/compositions/{comp.name}: no SYSTEM.toml")

    # The refusal. A tree with targets but nothing under any of them means the globs
    # stopped matching, which presents as success.
    if checked == 0:
        print(f"REFUSING: {len(targets)} target(s) but 0 units inspected. That is a broken "
              "walk, not a clean tree.", file=sys.stderr)
        return 2

    print(f"structure: {len(targets)} targets ({', '.join(t.name for t in targets)}), "
          f"{checked} units checked")
    for p in problems:
        print(f"  FAIL {p}")
    if problems:
        print(f"\nSTRUCTURE: {len(problems)} problem(s)")
        return 1
    print("STRUCTURE: OK -- every per-target unit mirrors a declared neutral half")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
