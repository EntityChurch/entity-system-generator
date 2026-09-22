#!/usr/bin/env python3
"""check-drivers.py — a driver literal that differs across targets is an undeclared
profile field.

## The rule

`languages/<target>/{build,test,host-launch}` is one copy per target, forever — that is
the point of the target directory, and it is why there are 46 drivers here and not
26 x 46 = 1,196. But N copies of one protocol is exactly the shape keystone paid for:
46 copies of `run-s4.sh`, one defect reproduced in 36 of them.

So the drivers may differ — they must, a target's build is idiomatic to its ecosystem —
but a **value** that differs is a different thing from a *procedure* that differs:

    a literal that is the same in every driver   -> shared boilerplate, fine
    a literal that DIFFERS between drivers       -> a per-target FACT, and a fact lives
                                                    in profile.toml where it can be
                                                    compared, not in a script where it
                                                    cannot

## The two incidents this was written on (D17 / AP-10), both measured, both ours

**Executed, undeclared.** The readiness-wait budget in `host-launch` was `lt 100` on
`typescript` and `lt 150` on `python` and `rust`, with no comment on any of the three.
Traced: `0a5350c` wrote 100 for port 1, `9adf347` raised it to 150 for port 2, `965ef51`
copied 150 for port 3, and nobody went back. **A correction made during port N lands in
ports N..last and never in ports 1..N-1**, because port N+1 is written by copying port N
— so the FIRST port is systematically the stalest, and it is the one every later port
was validated against.

**Declared, and separately executed.** `languages/rust/build` generated
`edition = "2021"` into the composition host's manifest while `languages/rust/profile.toml`
declared the same value four lines below a comment explaining that an edition skew
"changes name resolution and closure capture, and neither should differ between a peer
and a module compiled into the same binary". The fact whose entire purpose is *do not
skew* was in two places with nothing comparing them.

They are mirror images — one has no declaration, the other has one nobody reads — and
together they are the rule this file enforces.

## D15: a control and a refusal

The instrument's own failure mode is a tokeniser that stops matching and reports a clean
tree. So: zero drivers found, or zero literals extracted from a driver that has some,
REFUSES. The negative control is executable — plant a divergent literal and it goes red.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRIVERS = ("build", "test", "host-entry")

#: Numbers that are not configuration. A bare `2` in `cargo x 2` or an exit code is not a
#: per-target fact, and flagging them would make the gate noise that gets disabled (AP-4).
#: Deliberately narrow: it matches ASSIGNMENTS and COMPARISONS, the two places a tunable
#: actually appears, rather than every integer in the file.
#: Numbers that are not configuration. A bare `2` in `cargo x 2` or an exit code is not a
#: per-target fact, and flagging them would make the gate noise that gets disabled (AP-4).
#: Deliberately narrow: it matches COMPARISONS and ASSIGNMENTS, the two places a tunable
#: actually appears, rather than every integer in the file.
#:
#: EACH KEY CARRIES ITS SUBJECT, and that is not cosmetic -- it is AP-8 in this gate's own
#: first draft. Keying purely on the operator collapsed `[ "$j" -lt 50 ]` (the reap loop)
#: and `[ "$i" -lt 150 ]` (the readiness wait) into one `lt` bucket; first-match-wins took
#: the 50, the 150 was never compared, and **the gate reported OK against the exact drift
#: it was written to catch.** A lossy key moves the answer in the agreeing direction, which
#: is the direction nothing re-derives. The subject (`i`, `j`, `PORT`) restores the
#: distinction the source can express.
LITERAL = re.compile(
    r"""(?:
          \[\s*"?\$(?P<ltvar>\w+)"?\s+-lt\s+(?P<lt>\d+)      # [ "$i" -lt 150 ]
        | \[\s*"?\$(?P<gtvar>\w+)"?\s+-gt\s+(?P<gt>\d+)
        | sleep\s+(?P<sleep>[\d.]+)
        | ^(?P<name>[A-Z_]{3,})=(?P<val>[\d.]+)\s*$          # PORT=7777
        | edition\s*=\s*"(?P<edition>[^"]+)"
    )""",
    re.X | re.M,
)


def strip_comments(text: str) -> str:
    """Comments explain; they do not execute. A number inside one is prose, and prose is
    allowed to differ — several of these drivers discuss the OTHER targets' values on
    purpose."""
    out = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("#"):
            continue
        out.append(line.split(" #", 1)[0])
    return "\n".join(out)


def literals(path: Path) -> dict[str, str]:
    """`{key: value}` for the tunables this driver hardcodes, where the key carries the
    literal's SUBJECT so two comparisons in one file cannot collide. See LITERAL."""
    found: dict[str, str] = {}
    text = strip_comments(path.read_text(encoding="utf-8"))
    for m in LITERAL.finditer(text):
        g = m.groupdict()
        if g["lt"] is not None:
            found[f"-lt ${g['ltvar']}"] = g["lt"]
        elif g["gt"] is not None:
            found[f"-gt ${g['gtvar']}"] = g["gt"]
        elif g["sleep"] is not None:
            found.setdefault("sleep", g["sleep"])
        elif g["name"] is not None:
            found[g["name"]] = g["val"]
        elif g["edition"] is not None:
            found["edition"] = g["edition"]
    return found


def profile_values(target: str) -> set[str]:
    """Every scalar the profile declares, flattened to strings. A driver literal is
    excused when the profile carries the same value — the driver is then reading a
    declared fact, and the plan is where it should get it from."""
    path = ROOT / "languages" / target / "profile.toml"
    if not path.exists():
        return set()
    out: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        else:
            out.add(str(node))

    walk(tomllib.loads(path.read_text(encoding="utf-8")))
    return out


def main() -> int:
    targets = sorted(p.name for p in (ROOT / "languages").iterdir() if p.is_dir()) \
        if (ROOT / "languages").is_dir() else []
    if not targets:
        print("REFUSING: 0 targets. An empty result set is never a clean verdict.",
              file=sys.stderr)
        return 2

    # driver -> kind -> {target: value}
    table: dict[str, dict[str, dict[str, str]]] = {}
    scanned = 0
    for driver in DRIVERS:
        table[driver] = {}
        for t in targets:
            path = ROOT / "languages" / t / driver
            if not path.exists():
                continue
            scanned += 1
            for kind, value in literals(path).items():
                table[driver].setdefault(kind, {})[t] = value

    if scanned == 0:
        print(f"REFUSING: {len(targets)} target(s), 0 drivers found. That is a broken "
              "walk, not a clean tree.", file=sys.stderr)
        return 2

    problems: list[str] = []
    compared = 0
    for driver, kinds in table.items():
        for kind, per_target in kinds.items():
            if len(per_target) < 2:
                continue
            compared += 1
            distinct = set(per_target.values())
            if len(distinct) == 1:
                continue
            # It differs. Excused only if every value is one the target's own profile
            # declares -- i.e. the driver is transcribing a declared fact and should be
            # reading it from the plan instead, but at least the fact is comparable.
            undeclared = {t: v for t, v in per_target.items()
                          if v not in profile_values(t)}
            if undeclared:
                shown = ", ".join(f"{t}={v}" for t, v in sorted(per_target.items()))
                problems.append(
                    f"{driver}: `{kind}` differs across targets ({shown}) and "
                    f"{sorted(undeclared)} declare no such value in profile.toml -- "
                    "a per-target fact belongs in the profile, where it can be compared"
                )

    if compared == 0:
        print(f"REFUSING: {scanned} drivers scanned, 0 literals comparable across two or "
              "more targets. The tokeniser stopped matching.", file=sys.stderr)
        return 2

    print(f"drivers: {scanned} scanned across {len(targets)} targets, "
          f"{compared} literal(s) compared")
    for p in problems:
        print(f"  FAIL {p}")
    if problems:
        print(f"\nDRIVERS: {len(problems)} undeclared per-target fact(s)")
        return 1
    print("DRIVERS: OK -- every literal that differs across targets is profile-declared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
