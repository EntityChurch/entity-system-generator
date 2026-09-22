#!/usr/bin/env python3
"""scale-report.py — what grows, and by what multiplier.

## The question this exists to answer

"Where does adding a language cost us, and where does adding an extension?"

That question has been answered three times in this repo's prose — `DESIGN-THE-SYSTEM-
STRUCTURE` §1.2b's `2.1 : 1` ratio, cycle 1's `1.0 / 0.55 / 0.75` port costs, cycle 2's
per-cell line counts — and **every one of those numbers was typed by a person into a
document.** Two of them were wrong when first written (REVIEW-CYCLE-2 §3: *"the first
draft said ~1,650 and that number was never computed by anything"*). That is AP-1's
mechanism, and D14 says a number cites the artifact that produced it. This is the
artifact.

## The model: every file multiplies by exactly one thing

The repo has three axes — extensions (E), targets (T), and compositions — and the whole
argument of the target-major layout is that a file's *location* determines what it
multiplies by. So classify every tracked path by its multiplier and the cost model falls
out:

    class              multiplier   what lives there
    ─────────────────  ───────────  ──────────────────────────────────────────────
    neutral            x1           tools/, gates/<g>/ neutral halves, root files
    per-extension      xE           extension-contracts/<ext>/
    per-target         xT           languages/<t>/{profile,build,test,host-entry},
                                    languages/<t>/gates/<g>/
    per-cell           xE*T         languages/<t>/extensions/<ext>/    <-- QUADRATIC
    per-composition    xT*C         languages/<t>/compositions/<c>/

**`per-cell` is the only quadratic quadrant, and that is the whole finding.** Everything
else is linear in one axis. A protocol-shaped thing written into a cell is paid E*T
times; the same thing in `tools/` is paid once. §1.2b states that rule
(*"the shared protocol lives in tools/, one copy"*); this measures compliance with it.

`per-target` is the second-most expensive and it is the one that looks harmless, because
at three targets a 500-line gate arm reads as a file rather than as 1,500 lines.

## What is deliberately NOT in the growth model, and is printed anyway

    input      shared/spec-data/**   a verbatim pinned upstream copy. Grows with E and
                                     is not ours to write or to shrink.
    prose      docs/**               grows with sessions, not with either axis.
    artifact   **/status/**,          measured OUTPUT. Counting a conformance report as
               Cargo.lock             maintenance mass would make a good measurement day
                                      look like a regression.

They are excluded from the projection and **reported on their own line**, because a
silently-dropped path is mass that does not appear in the total, which is exactly the
false-green D15 is about.

## D15: the control, the corpus assertion, and the refusal

- **Control** (`--self-test`): a positive table asserting one known path per class lands
  in that class, and a negative asserting a path that matches no rule returns `None` and
  drives the run to REFUSE. Both directions executed; neither is inferred.
- **Refusal — and this is the load-bearing one.** A tracked path matching no rule
  REFUSES the whole run rather than being skipped. An unclassified path is mass missing
  from the projection, and a projection over a subset of the tree presents as a smaller,
  healthier number. Also refused: zero targets, zero extensions, an empty `per-cell`.
- **The quantity is printed beside every verdict** (REVIEW-CYCLE-2 §2, AP-15). A report
  that said only "quadratic quadrant: OK" could not be debugged by the person running it.

**Flip-condition for `code` (D15 clause 3).** `code` counts non-blank lines that do not
*begin* with a line-comment marker. It does not strip `/* */` blocks or python
docstrings, both of which this tree uses for substantive design rationale that a
maintainer reads. Stripping them would understate per-target mass — the direction that
flatters us — so they are counted. `lines` (everything) is printed beside `code` so
neither can be quoted alone.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Line-comment markers by suffix. A file whose suffix is absent here has every non-blank
#: line counted as code -- correct for `.md`, `.json`, and anything we have not met yet.
COMMENT = {
    ".py": ("#",), ".toml": ("#",), ".sh": ("#",), ".cfg": ("#",), ".yml": ("#",),
    ".ts": ("//",), ".mjs": ("//",), ".js": ("//",), ".rs": ("//",),
}
#: Extensionless files in this tree are all shell drivers.
COMMENT_NOEXT = ("#",)

CLASSES = ("neutral", "per-extension", "per-target", "per-cell", "per-composition")
EXCLUDED = ("input", "prose", "artifact")

#: The roles inside an extension cell, in match order. Used only for the per-cell
#: decomposition -- the quadratic quadrant is 96% of the projection, so "what is a cell
#: made of" is the only question that moves the total.
#:
#: MATCHED ON THE BASENAME, NEVER ON THE PATH, and that is a planted-defect story rather
#: than a style note. The first draft of this decomposition was a shell pipeline matching
#: `*types*` against the full path -- and `typescript` CONTAINS `types`, so all three
#: typescript cells reported a 1,217-line type module and a handler of zero. It was a
#: plausible, self-consistent, entirely wrong table. Same family as AP-8: a key that
#: collapses a distinction its sources can express, moving the answer in the direction
#: that gets published. `self_test()` pins it.
ROLES = (
    ("test",    lambda p, b: "/test/" in f"/{p}/" or "/tests/" in f"/{p}/"),
    ("types",   lambda p, b: b.startswith(("types", "test_types"))),
    ("sdk",     lambda p, b: b.startswith("sdk")),
    ("handler", lambda p, b: b.startswith("handler")),
    ("other",   lambda p, b: True),
)


def role_of(rel: str) -> str:
    """Which role a file inside a cell plays. Basename, not path -- see ROLES."""
    base = rel.rsplit("/", 1)[-1]
    for name, pred in ROLES:
        if pred(rel, base):
            return name
    return "other"


def classify(rel: str) -> tuple[str, str] | None:
    """Return (class, bucket) for a repo-relative path, or None if no rule matches.

    `bucket` is the sub-grouping used for the hot-spot view -- for `per-target` it is the
    subtree (`gates/host-seam`, `driver`), which is what makes a 500-line arm visible as
    1,500 lines rather than as one file.

    Order matters: `status/` is checked before `compositions/`, because a conformance
    report lives inside a composition and is an artifact rather than authored mass.
    """
    parts = rel.split("/")

    # ── the excluded three, first, so nothing below can claim them ──────────────
    if "status" in parts:
        return ("artifact", "conformance report")
    if parts[-1] == "Cargo.lock":
        return ("artifact", "lockfile")
    if parts[0] == "docs":
        return ("prose", "docs")
    if parts[0] == "shared":
        return ("input", "pinned spec snapshot")

    # ── the growth model ────────────────────────────────────────────────────────
    if len(parts) == 1:
        return ("neutral", "root")
    if parts[0] == "tools":
        return ("neutral", "tools")
    if parts[0] == "gates":
        # The NEUTRAL half of a gate. `gates/<g>/compare.py` is written once and scores
        # every arm; `gates/README.md` is the axis table.
        return ("neutral", f"gates/{parts[1]}" if len(parts) > 2 else "gates")
    if parts[0] == "extension-contracts" and len(parts) >= 2:
        return ("per-extension", f"contract/{parts[1]}")

    if parts[0] == "languages" and len(parts) >= 3:
        sub = parts[2]
        if sub in ("profile.toml", "build", "test", "host-entry", "Cargo.toml"):
            return ("per-target", "driver + profile")
        if sub == "gates" and len(parts) >= 4:
            return ("per-target", f"gates/{parts[3]}")
        if sub == "extensions" and len(parts) >= 4:
            return ("per-cell", f"cell/{parts[3]}")
        if sub == "compositions" and len(parts) >= 4:
            return ("per-composition", f"composition/{parts[3]}")

    return None


def measure(path: Path) -> tuple[int, int]:
    """(lines, code) for one file. Binary or unreadable counts as 0/0, reported."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return (0, 0)
    markers = COMMENT.get(path.suffix, COMMENT_NOEXT if not path.suffix else ())
    lines = text.splitlines()
    code = 0
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if markers and s.startswith(markers):
            continue
        code += 1
    return (len(lines), code)


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def axes() -> tuple[list[str], list[str], int]:
    """(targets, extensions, max compositions on any one target) -- read off the tree."""
    langs = ROOT / "languages"
    contracts = ROOT / "extension-contracts"
    targets = sorted(p.name for p in langs.iterdir() if p.is_dir()) if langs.is_dir() else []
    exts = sorted(p.name for p in contracts.iterdir() if p.is_dir()) if contracts.is_dir() else []
    comps = 0
    for t in targets:
        d = langs / t / "compositions"
        if d.is_dir():
            comps = max(comps, sum(1 for p in d.iterdir() if p.is_dir()))
    return targets, exts, comps


def fmt(n: int) -> str:
    return f"{n:,}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", metavar="E,T",
                    help="project to E extensions x T targets (default 26,46 -- the "
                         "extension spec corpus and keystone's peer cohort)")
    ap.add_argument("--compositions", type=int, default=None,
                    help="compositions per target in the projection (default: today's max)")
    ap.add_argument("--self-test", action="store_true",
                    help="D15's control: assert the classifier lands known paths and "
                         "REFUSES an unknown one")
    ap.add_argument("--check", action="store_true",
                    help="gate mode: every tracked path is classified, and nothing else. "
                         "The one invariant here that needs no threshold")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    targets, exts, comps_today = axes()
    if not targets:
        print("REFUSING: 0 targets under languages/. An empty axis is not a cost model.",
              file=sys.stderr)
        return 2
    if not exts:
        print("REFUSING: 0 extensions under extension-contracts/. The E axis is the "
              "denominator of every per-cell number below.", file=sys.stderr)
        return 2

    files = tracked()
    if not files:
        print("REFUSING: `git ls-files` returned nothing.", file=sys.stderr)
        return 2

    # ── classify, and REFUSE on anything the model does not cover ───────────────
    unclassified: list[str] = []
    by_class: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])   # files, lines, code
    by_bucket: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    #: per-cell and per-target mass keyed by the individual unit, for the medians.
    unit_mass: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    #: role -> cell -> code, for the decomposition of the quadratic quadrant.
    cell_roles: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for rel in files:
        hit = classify(rel)
        if hit is None:
            unclassified.append(rel)
            continue
        cls, bucket = hit
        lines, code = measure(ROOT / rel)
        for agg in (by_class[cls], by_bucket[(cls, bucket)]):
            agg[0] += 1
            agg[1] += lines
            agg[2] += code
        parts = rel.split("/")
        if cls == "per-cell":
            unit_mass["cell"][f"{parts[1]}/{parts[3]}"] += code
            cell_roles[role_of(rel)][f"{parts[1]}/{parts[3]}"] += code
        elif cls == "per-target":
            unit_mass["target"][parts[1]] += code
        elif cls == "per-composition":
            unit_mass["composition"][f"{parts[1]}/{parts[3]}"] += code
        elif cls == "per-extension":
            unit_mass["extension"][parts[1]] += code

    if unclassified:
        print(f"REFUSING: {len(unclassified)} tracked path(s) match no rule in "
              f"`classify()`.\n"
              f"An unclassified path is mass that does not appear in the projection, and "
              f"a projection\nover a subset of the tree reads as a smaller, healthier "
              f"number. Add a rule or a class:", file=sys.stderr)
        for rel in unclassified[:20]:
            print(f"  {rel}", file=sys.stderr)
        if len(unclassified) > 20:
            print(f"  ... and {len(unclassified) - 20} more", file=sys.stderr)
        return 2

    if by_class["per-cell"][0] == 0:
        print("REFUSING: 0 files in the per-cell quadrant. That quadrant is the entire "
              "quadratic\nclaim of this report; measuring it as empty is a broken walk, "
              "not a lean tree.", file=sys.stderr)
        return 2

    # ── gate mode ───────────────────────────────────────────────────────────────
    #
    # The report itself is NOT a gate and deliberately is not in `make check`: a gate
    # needs a threshold, and this repo has no evidence for what a per-cell budget should
    # be. A number invented today to make a gate possible is the speculation the
    # promotion ladder refuses.
    #
    # What CAN be gated, with no threshold at all, is the refusal above: every tracked
    # path is classified. That is D16's question in executable form -- *when a new kind of
    # artifact appears in this tree, what reads it?* -- and the answer is now "this does,
    # or `make check` goes red." It is the cheapest standing watch on the tree acquiring
    # a shape nobody costed.
    if args.check:
        print(f"scale: {len(files)} tracked paths, all classified "
              f"({by_class['per-cell'][0]} per-cell, {by_class['per-target'][0]} per-target, "
              f"{by_class['neutral'][0]} neutral)")
        print("SCALE: OK -- every tracked path has a declared multiplier")
        return 0

    E, T = len(exts), len(targets)
    C = comps_today

    # The projection axes are parsed up here because the per-cell decomposition below
    # quotes them too, and two places computing `pe * pt` independently is the shape D14
    # is about.
    if args.project:
        try:
            pe, pt = (int(x) for x in args.project.split(","))
        except ValueError:
            print("REFUSING: --project wants E,T (two integers)", file=sys.stderr)
            return 2
    else:
        pe, pt = 26, 46
    pc = args.compositions if args.compositions is not None else C

    # ── today ───────────────────────────────────────────────────────────────────
    print(f"scale-report — {E} extensions x {T} targets, "
          f"{C} composition(s) per target, {fmt(len(files))} tracked files")
    print(f"  extensions: {', '.join(exts)}")
    print(f"  targets:    {', '.join(targets)}")
    print()
    print(f"{'class':<18} {'mult':>7} {'files':>7} {'lines':>9} {'code':>9}   share of code")
    print("-" * 78)
    growth_code = sum(by_class[c][2] for c in CLASSES)
    mult_label = {"neutral": "x1", "per-extension": "xE", "per-target": "xT",
                  "per-cell": "xE*T", "per-composition": "xT*C"}
    for c in CLASSES:
        f_, l_, k_ = by_class[c]
        share = (k_ / growth_code * 100) if growth_code else 0.0
        print(f"{c:<18} {mult_label[c]:>7} {f_:>7} {fmt(l_):>9} {fmt(k_):>9}   {share:5.1f}%")
    print("-" * 78)
    print(f"{'IN THE MODEL':<18} {'':>7} "
          f"{sum(by_class[c][0] for c in CLASSES):>7} "
          f"{fmt(sum(by_class[c][1] for c in CLASSES)):>9} {fmt(growth_code):>9}")
    print()
    for c in EXCLUDED:
        f_, l_, k_ = by_class[c]
        print(f"{c:<18} {'--':>7} {f_:>7} {fmt(l_):>9} {fmt(k_):>9}   (excluded, not dropped)")

    # ── the hot spots: what dominates each multiplying class ────────────────────
    print()
    print("hot spots — the largest bucket in each multiplying class")
    print("-" * 78)
    for c in ("per-cell", "per-target", "per-composition", "per-extension"):
        rows = sorted(((b, v) for (cc, b), v in by_bucket.items() if cc == c),
                      key=lambda r: -r[1][2])
        for bucket, (f_, l_, k_) in rows[:3]:
            per_unit = k_ / (T if c == "per-target" else 1)
            note = f"  ({fmt(int(per_unit))} code/target)" if c == "per-target" else ""
            print(f"  {c:<16} {bucket:<26} {f_:>4} files  {fmt(k_):>8} code{note}")

    # ── inside the quadratic quadrant ───────────────────────────────────────────
    #
    # The only decomposition that moves the projected total, because per-cell is ~96% of
    # it. The column that matters is the SPREAD: a role whose mass is nearly identical in
    # every cell is a role whose content is not actually per-(extension x target), and by
    # §1.2b's rule that is something protocol-shaped sitting in the most expensive
    # quadrant in the tree.
    print()
    print(f"inside the per-cell quadrant — {len(unit_mass['cell'])} cells, by role")
    print("-" * 78)
    print(f"{'role':<10} {'code':>8} {'share':>7} {'median/cell':>12} {'range':>14} "
          f"{'spread':>7}   at {pe}x{pt}")
    for name, _ in ROLES:
        vals = sorted(cell_roles[name].values())
        if not vals:
            continue
        tot = sum(vals)
        med = int(statistics.median(vals))
        spread_ratio = (max(vals) / min(vals)) if min(vals) else float("inf")
        share = tot / by_class["per-cell"][2] * 100
        print(f"{name:<10} {fmt(tot):>8} {share:>6.1f}% {fmt(med):>12} "
              f"{fmt(min(vals)) + '..' + fmt(max(vals)):>14} {spread_ratio:>6.1f}x   "
              f"{fmt(med * pe * pt):>10}")
    print("\n  spread is max/min across cells. A role near 1.0x is one whose mass does "
          "not\n  actually vary with (extension x target) -- protocol-shaped code in the "
          "most\n  expensive quadrant in the tree (`DESIGN-THE-SYSTEM-STRUCTURE` §1.2b).")

    # ── the marginal cost: the question the operator actually asked ─────────────
    def spread(d: dict[str, int]) -> tuple[int, int, int, int]:
        vals = sorted(d.values())
        return (len(vals), min(vals), int(statistics.median(vals)), max(vals)) if vals else (0, 0, 0, 0)

    n_cell, lo_cell, med_cell, hi_cell = spread(unit_mass["cell"])
    n_tgt, lo_tgt, med_tgt, hi_tgt = spread(unit_mass["target"])
    n_cmp, lo_cmp, med_cmp, hi_cmp = spread(unit_mass["composition"])
    n_ext, lo_ext, med_ext, hi_ext = spread(unit_mass["extension"])

    print()
    print("marginal cost — measured over what exists, with n and the range, because a "
          "median\nover three samples is not a rate (`gates/README.md`)")
    print("-" * 78)
    print(f"  one extension cell    n={n_cell:<3} median {fmt(med_cell):>7} code   "
          f"range {fmt(lo_cell)}..{fmt(hi_cell)}")
    print(f"  one target scaffold   n={n_tgt:<3} median {fmt(med_tgt):>7} code   "
          f"range {fmt(lo_tgt)}..{fmt(hi_tgt)}")
    print(f"  one composition       n={n_cmp:<3} median {fmt(med_cmp):>7} code   "
          f"range {fmt(lo_cmp)}..{fmt(hi_cmp)}")
    print(f"  one contract          n={n_ext:<3} median {fmt(med_ext):>7} code   "
          f"range {fmt(lo_ext)}..{fmt(hi_ext)}")
    print()
    add_target = med_tgt + E * med_cell + C * med_cmp
    add_ext = med_ext + T * med_cell
    print(f"  ADD ONE TARGET   at today's E={E}:  {fmt(med_tgt)} scaffold "
          f"+ {E} x {fmt(med_cell)} cells + {C} x {fmt(med_cmp)} compositions "
          f"= {fmt(add_target)} code")
    print(f"  ADD ONE EXTENSION at today's T={T}: {fmt(med_ext)} contract "
          f"+ {T} x {fmt(med_cell)} cells = {fmt(add_ext)} code")

    # ── the projection ──────────────────────────────────────────────────────────
    print()
    print(f"projection — E={pe} (the extension spec corpus) x T={pt} "
          f"(keystone's peer cohort), C={pc} per target")
    print("-" * 78)
    proj = {
        "neutral": by_class["neutral"][2],
        "per-extension": med_ext * pe,
        "per-target": med_tgt * pt,
        "per-cell": med_cell * pe * pt,
        "per-composition": med_cmp * pt * pc,
    }
    total = sum(proj.values())
    for c in CLASSES:
        share = (proj[c] / total * 100) if total else 0.0
        print(f"{c:<18} {mult_label[c]:>7} {fmt(proj[c]):>12} code   {share:5.1f}%")
    print("-" * 78)
    print(f"{'PROJECTED':<18} {'':>7} {fmt(total):>12} code   "
          f"({total / max(growth_code, 1):.0f}x today's {fmt(growth_code)})")
    print()
    print(f"  the quadratic quadrant is {proj['per-cell'] / total * 100:.0f}% of it. "
          f"Every line moved from a cell\n  into `tools/` is worth {pe * pt} lines there; "
          f"every line moved out of a per-target\n  gate arm is worth {pt}.")

    return 0


def self_test() -> int:
    """D15's control. Positive: known paths land in their class. Negative: an
    unmodelled path returns None, which is what drives the run to REFUSE."""
    positive = [
        ("tools/compose.py", "neutral"),
        ("gates/chunking-parity/compare.py", "neutral"),
        ("Makefile", "neutral"),
        ("extension-contracts/content/EXTENSION.toml", "per-extension"),
        ("languages/rust/profile.toml", "per-target"),
        ("languages/rust/gates/host-seam/src/bin/probe.rs", "per-target"),
        ("languages/rust/extensions/history/src/handler.rs", "per-cell"),
        ("languages/rust/compositions/content/host.rs", "per-composition"),
        ("languages/rust/compositions/content/status/x.json", "artifact"),
        ("shared/spec-data/history-v1.7/EXTENSION-HISTORY.md", "input"),
        ("docs/STATUS.md", "prose"),
    ]
    # Paths that MUST NOT classify. `languages/<t>/<junk>/` is the realistic one: a new
    # subtree added under a target that nothing declares is exactly what the mirror rule
    # and this report both need to see rather than skip.
    negative = [
        "languages/rust/scratch/notes.rs",
        "vendor/somebody-elses/thing.rs",
    ]

    bad = 0
    print("self-test: positive — a known path per class")
    for rel, want in positive:
        got = classify(rel)
        ok = got is not None and got[0] == want
        print(f"  {'ok  ' if ok else 'FAIL'} {rel:<52} -> "
              f"{got[0] if got else 'None':<16} (want {want})")
        bad += not ok

    print("self-test: negative — a path the model does not cover must return None,")
    print("           because that is what makes the run REFUSE rather than under-count")
    for rel in negative:
        got = classify(rel)
        ok = got is None
        print(f"  {'ok  ' if ok else 'FAIL'} {rel:<52} -> {got[0] if got else 'None'}")
        bad += not ok

    # THE SUBSTRING TRAP, pinned. `typescript` contains `types`, so a role matcher that
    # looks at the PATH puts every typescript handler, sdk and internal file into the
    # `types` bucket -- which is what the first draft of this decomposition did, and it
    # produced a table that was internally consistent and entirely wrong. The negative
    # here is the one that would have caught it.
    print("self-test: role — matched on basename, never on path (`typescript` ⊃ `types`)")
    roles_expected = [
        ("languages/typescript/extensions/history/handler.ts", "handler"),
        ("languages/typescript/extensions/history/types.ts", "types"),
        ("languages/typescript/extensions/history/sdk.ts", "sdk"),
        ("languages/typescript/extensions/history/internal/recorder.ts", "other"),
        ("languages/typescript/extensions/history/test/patterns.test.ts", "test"),
        ("languages/rust/extensions/history/tests/handler.rs", "test"),
    ]
    for rel, want in roles_expected:
        got = role_of(rel)
        ok = got == want
        print(f"  {'ok  ' if ok else 'FAIL'} {rel:<52} -> {got:<8} (want {want})")
        bad += not ok

    # And the refusal itself, observed rather than assumed: a `code` count over an
    # empty marker set must not silently be zero.
    lines, code = measure(Path(__file__))
    if code == 0:
        print("  FAIL measure() returned 0 code lines for this file")
        bad += 1
    else:
        print(f"self-test: measure() on this file -> {lines} lines, {code} code")

    print(f"\nSELF-TEST: {'OK -- both directions observed' if not bad else f'{bad} FAILURE(S)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
