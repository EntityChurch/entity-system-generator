#!/usr/bin/env python3
"""req-coverage.py — every requirement the spec DECLARES is mapped to the instrument that
measures it, or to a gap that says so.

WHY THIS EXISTS
---------------
Our conformance axis is `entity-core-go`'s `validate-peer`, and it is the oracle BECAUSE it is
not the thing under test. That is settled and this tool does not change it. What was never
established is the other direction: **what fraction of an extension's declared requirements does
the oracle's category actually assert?**

Nothing anywhere answers that. `-list-categories` prints the 68 category names; there is no
`-list-checks`, and the executed check set is only observable by running the suite. So a category
named `history` reads like coverage of EXTENSION-HISTORY, and the question of how much of §9.1 it
reaches has been answered here three times, by hand, in prose, in three separate routing packets.

D16, four instances deep: *the thing we own is the thing nothing watches — and an axis with SOME
upstream coverage is more dangerous than one with none, because the coverage is what stops anyone
asking.* This is that axis at full size. The oracle is real, it is good, and it is the measurement;
the failure it cannot catch is a requirement it never had a check for, because a requirement with
no check produces no FAIL.

WHAT IT MEASURES, AND WHAT IT IS NOT
------------------------------------
It is NOT a second scorer and it never produces a conformance verdict. It compares two
inventories, both of which already exist:

    the SPEC's own conformance section   ->  §9.1 (HISTORY) / §11.1-11.4 (CONTENT)
    the ORACLE's executed check set      ->  the `checks[]` of the JSON reports we already produce

and requires `extension-contracts/<ext>/EXTENSION.toml [conformance]` to declare, for every
requirement row, which checks measure it — an oracle check name, one of ours, or `none` with a
reason. **An undeclared requirement is a failure**, in the same shape and for the same reason as
`[sdk_surface]` (D16) and `[error_surface]`: the failure mode is a row arriving, or changing at a
re-pin, without anyone deciding what measures it. CONTENT v3.6 -> v3.7 is the paid-for instance.

THE CORPUS IS THE REPORTS, NOT THE ORACLE'S SOURCE
--------------------------------------------------
Two reasons, and the second is the one that matters.

1. `../entity-core-go` is another team's tree and read-only. Static extraction of its `Declare`
   sites is a second reading of an artifact we already hold the output of.
2. **A source read and an executed report can disagree**, and only one of them produced the
   numbers we publish. The reports are the artifact beside the bytes (D14). If the binary we ran
   never declared a check, that check does not measure us however clearly the source declares it.

So the corpus is `languages/*/output/*/reports/*.json`, unioned, with the categories and counts
PRINTED before any verdict. Two consequences that are stated rather than implied:

  * A check in a category we have never run is invisible here, and a requirement covered only by
    such a check will read `uncovered`. The printed corpus is the scope of every negative claim
    this tool makes — that is the "prove a negative" rule (AGENTS.md) discharged by construction
    rather than by a promise.
  * The synthetic `<category>/skipped` entry a `--profile core` run emits for every category it
    carves out is EXCLUDED from the corpus, and the count of exclusions is printed. It is a
    zero-information entry that would otherwise make every category look present. Keystone's
    `check-set-gate.py` exists because that same entry is indistinguishable, in `summary`, from
    "we never got to this".

REFUSALS (D15, sharpened) — this tool says "I did not measure anything" out loud
--------------------------------------------------------------------------------
  * no reports at all, or zero checks after exclusions        -> REFUSING, rc 3
  * a declared shape whose parser yields zero requirements    -> REFUSING, rc 3
  * a declared `oracle_category` absent from the corpus       -> REFUSING for that extension, rc 3

rc 3 is not a verdict. A clean verdict over an empty corpus is not a clean verdict, and this
instrument's fragile part is the two markdown parsers — a spec re-pin that re-words a heading
turns "0 requirements" into "0 problems" unless the refusal fires first.

CONTROL: `--self-test` drives all four gate rules and both refusals over synthetic inputs and
requires each to fire. An instrument observed only passing is not an instrument.

USAGE
    ./tools/req-coverage.py                  # every extension-contracts/<ext>
    ./tools/req-coverage.py --ext history    # one
    ./tools/req-coverage.py --verbose        # print every requirement, not only the gaps
    ./tools/req-coverage.py --self-test      # the control
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The floor is a corpus assertion, not a style rule. The fragile part of this instrument is the
# markdown parsing, and its failure mode is a clean run over nothing. Two extensions with ten and
# twenty-seven rows are in the tree today; a run that parses fewer than this has lost a parser.
MIN_REQUIREMENTS = 8

# Levels a requirement row may carry. `IMPL-DEFINED` is CONTENT §11.4 and is a real level: it
# says the spec declines to constrain the row, which is a different fact from "nothing checks it"
# and must not be reported as a gap.
LEVELS = ("MUST", "SHOULD", "MAY", "IMPL-DEFINED")

# A requirement at these levels is expected to have an instrument. The rest are reported and
# never failed: `MAY` and `IMPL-DEFINED` rows are, by the spec's own words, not requirements on
# an implementation, so an "uncovered MAY" is a category error rather than a finding.
BINDING = ("MUST", "SHOULD")


# ── the spec side ───────────────────────────────────────────────────────────────────────

def _rel(p: Path) -> str:
    """Repo-relative when it is in the tree, absolute otherwise — the self-test's synthetic
    snapshot lives in a temp dir, and a formatter that raises there would make the control
    unrunnable against the real code path it exists to drive."""
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line); line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def _norm(text: str) -> str:
    """Normalise a requirement row for matching.

    Markdown emphasis and code fences are presentation; the words are the row. Section refs are
    NOT stripped — two CONTENT rows differ only by the section they cite, and a normaliser that
    collapsed them would report agreement that is not there (AP-8: a normaliser preserves every
    distinction its sources can express).
    """
    t = text.replace("**", "").replace("`", "")
    t = t.replace("—", "-").replace("–", "-").replace("’", "'")
    return re.sub(r"\s+", " ", t).strip().lower()


def _sections_cited(text: str) -> list[str]:
    """Every `§x.y` a row names. Reporting only — the join is by the DECLARED mapping, because
    HISTORY §9.1's rows cite no section at all and a section-based join would silently produce
    ten uncovered rows on a spec whose oracle category has thirty-four checks."""
    return re.findall(r"§\s*([0-9]+(?:\.[0-9]+)*)", text)


def parse_level_table(md: str, section: str) -> list[dict]:
    """Shape `level-table`: a heading, then a markdown table with a `Level` column.

    HISTORY §9.1. Rows are `| Requirement | Level |`.
    """
    m = re.search(rf"^#+\s+{re.escape(section)}\s+.*$", md, re.M)
    if not m:
        return []
    body = md[m.end():]
    nxt = re.search(r"^#+\s", body, re.M)
    if nxt:
        body = body[: nxt.start()]

    rows: list[dict] = []
    header_seen = False
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if not header_seen:
            # The header row, then the `|---|---|` rule. Both are skipped, and the header is
            # ASSERTED rather than assumed: a table whose second column is not the level is a
            # different table and must not be read as this one.
            if cells[1].lower().startswith("level"):
                header_seen = True
            continue
        if set(cells[0]) <= set("-: "):
            continue
        level = cells[1].upper().strip()
        if level not in LEVELS:
            continue
        rows.append({"text": cells[0], "level": level})
    return rows


def parse_level_sections(md: str, section: str, level_map: dict[str, str]) -> list[dict]:
    """Shape `level-sections`: `### <section>.<n> <title>` subsections, each a bullet list.

    CONTENT §11.1 MUST Implement / §11.2 SHOULD / §11.3 MAY / §11.4 Implementation-Defined.

    `level_map` is DECLARED in the contract rather than inferred from the heading. Inferring it
    would mean guessing that a heading containing the word "MUST" is a MUST section, which is one
    re-worded heading away from silently dropping eight requirements.
    """
    rows: list[dict] = []
    for m in re.finditer(rf"^#+\s+{re.escape(section)}\.([0-9]+)\s+(.+)$", md, re.M):
        title = m.group(2).strip()
        level = level_map.get(title)
        if level is None:
            continue
        body = md[m.end():]
        nxt = re.search(r"^#+\s", body, re.M)
        if nxt:
            body = body[: nxt.start()]
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                rows.append({"text": line[2:].strip(), "level": level})
    return rows


def load_requirements(contract: dict, snapshot_dir: Path) -> tuple[list[dict], Path]:
    conf = contract["conformance"]
    spec_file = snapshot_dir / conf["spec_file"]
    md = spec_file.read_text()
    shape = conf["shape"]
    if shape == "level-table":
        rows = parse_level_table(md, conf["section"])
    elif shape == "level-sections":
        rows = parse_level_sections(md, conf["section"], conf.get("levels", {}))
    else:
        raise SystemExit(f"req-coverage: unknown [conformance].shape {shape!r}")
    return rows, spec_file


# ── the oracle side ─────────────────────────────────────────────────────────────────────

def load_corpus() -> dict:
    """The executed check set, unioned over every report in the tree.

    Returns categories -> {check name -> set of severities seen}, plus the bookkeeping every
    negative claim below is scoped by.
    """
    files = sorted(glob.glob(str(ROOT / "languages/*/output/*/reports/*.json")))
    cats: dict[str, dict[str, set]] = {}
    synthetic = 0
    parsed = 0
    for f in files:
        try:
            doc = json.loads(Path(f).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        parsed += 1
        for c in doc.get("checks", []):
            name = c.get("name", "")
            # The `--profile core` carve-out entry: one SKIP per category, no spec ref, no
            # information. Counted and dropped; see the module docstring.
            if name == "skipped" and not c.get("spec_ref"):
                synthetic += 1
                continue
            cats.setdefault(c.get("category", "?"), {}).setdefault(name, set()).add(
                c.get("severity", "?")
            )
    names = sorted(f"{cat}/{n}" for cat, ns in cats.items() for n in ns)
    digest = hashlib.sha256("\n".join(names).encode()).hexdigest()
    return {
        "categories": cats,
        "reports": parsed,
        "files": len(files),
        "synthetic_dropped": synthetic,
        "checks": len(names),
        "digest": digest,
    }


# ── the gate ────────────────────────────────────────────────────────────────────────────

class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.refusals: list[str] = []


def check_extension(ext_dir: Path, corpus: dict, res: Result, verbose: bool) -> dict | None:
    contract = tomllib.loads((ext_dir / "EXTENSION.toml").read_text())
    name = contract["extension"]["name"]
    if "conformance" not in contract:
        res.failures.append(
            f"{name}: EXTENSION.toml has no [conformance] block. Every extension in this tree "
            f"declares one; an extension without it is a requirement inventory nobody mapped."
        )
        return None
    snapshot = ROOT / "shared/spec-data" / contract["extension"]["snapshot"]
    return evaluate(contract, snapshot, corpus, res)


def evaluate(contract: dict, snapshot: Path, corpus: dict, res: Result) -> dict | None:
    """The four gate rules and the two per-extension refusals.

    Split out from `check_extension` so `--self-test` drives THIS function rather than a
    re-implementation of it. A control that exercises a copy of the rules proves the copy can go
    red; the first draft of this file did exactly that, which is the same shape as an instrument
    reading a quantity its own execution wrote (D19) — the thing under test was not the thing
    that runs.
    """
    name = contract["extension"]["name"]
    conf = contract["conformance"]

    rows, spec_file = load_requirements(contract, snapshot)
    if not rows:
        res.refusals.append(
            f"{name}: shape {conf['shape']!r} parsed ZERO requirements out of "
            f"{spec_file} §{conf['section']}. The parser has lost its "
            f"anchor; a clean verdict here would be a verdict over nothing."
        )
        return None

    cat = conf["oracle_category"]
    if cat not in corpus["categories"]:
        res.refusals.append(
            f"{name}: oracle_category {cat!r} is absent from the executed corpus "
            f"({corpus['checks']} checks over {len(corpus['categories'])} categories). "
            f"Run `make conformance` for a composition that declares it; every coverage verdict "
            f"below it would read `uncovered` for want of a report rather than for want of a check."
        )
        return None

    declared = {_norm(r["text"]): r for r in conf.get("requirement", [])}
    seen_spec = {_norm(r["text"]) for r in rows}

    # Rule 1 — every row the spec declares is declared here.
    for r in rows:
        k = _norm(r["text"])
        if k not in declared:
            res.failures.append(
                f"{name}: UNDECLARED requirement ({r['level']}) — {r['text']!r}\n"
                f"    {_rel(spec_file)} §{conf['section']} declares it and "
                f"[conformance] does not. Add a [[conformance.requirement]] naming what measures "
                f"it, or `covered_by = []` with a `note` saying nothing does."
            )

    # Rule 2 — every row declared here is still in the spec. This is the re-pin direction, and it
    # is the one that fails silently: a row deleted or re-worded upstream leaves a mapping in this
    # file that reads as coverage of a requirement that no longer exists (AP-2's mechanism).
    for k, r in declared.items():
        if k not in seen_spec:
            res.failures.append(
                f"{name}: STALE requirement — {r['text']!r}\n"
                f"    declared in [conformance] and absent from {_rel(spec_file)} "
                f"§{conf['section']} at snapshot {contract['extension']['snapshot']}. The spec "
                f"moved; the mapping did not."
            )

    # Rules 3 and 4 — the mapping resolves, and a gap says why.
    tally = {lv: {"total": 0, "oracle": 0, "partial": 0, "ours": 0, "none": 0}
             for lv in LEVELS}
    detail = []
    for r in rows:
        d = declared.get(_norm(r["text"]))
        if d is None:
            continue
        lv = r["level"]
        tally[lv]["total"] += 1
        oracle = list(d.get("oracle", []))
        ours = list(d.get("ours", []))

        for check in oracle:
            # A check name is a citation, and D18 is the rule that a citation resolves or it is
            # not a citation. Here the referent is a check in an executed report rather than a
            # path, and the failure is identical: a mapping to a check that never ran reads as
            # the strongest evidence this file can carry.
            #
            # A bare name is in the extension's own category; a `category/name` is elsewhere.
            # The qualified form is load-bearing rather than a convenience: CONTENT's three type
            # entities are hash-compared in `type_system`, not in `content`, and a mapping that
            # could only cite its own category would have to report them uncovered — which is
            # the false negative that makes a coverage instrument worth suppressing.
            ccat, _, cname = check.rpartition("/")
            ccat = ccat or cat
            if cname not in corpus["categories"].get(ccat, {}):
                res.failures.append(
                    f"{name}: requirement {d.get('id','?')} maps to oracle check "
                    f"{ccat}/{cname!r}, which is not in the executed corpus. Either the name is "
                    f"wrong or the oracle stopped declaring it."
                )

        # `gap` is the fourth state and it is the one this instrument exists for. A row with an
        # oracle check and a declared gap is PARTIAL, never `oracle` — because "there is a check
        # named after this requirement" and "the requirement is measured" are two sentences, and
        # collapsing them is the exact error the four `context_*` presence checks made. A tally
        # that counted partials as covered would report HISTORY's §9.1 as 8-of-10 measured while
        # three of those eight assert only that a field is non-empty.
        gap = d.get("gap", "")
        if oracle and gap:
            tally[lv]["partial"] += 1
            state = "partial"
        elif oracle:
            tally[lv]["oracle"] += 1
            state = "oracle"
        elif ours:
            tally[lv]["ours"] += 1
            state = "ours"
        else:
            tally[lv]["none"] += 1
            state = "none"
            # The note is required at BINDING levels only. It exists to force a decision about a
            # requirement, and by the spec's own word a `MAY` and an `Implementation-Defined` row
            # are not requirements — demanding a sentence for each would make the gate a ritual,
            # and a ritual gate is one that gets satisfied rather than read. Those rows must still
            # be DECLARED (rule 1), which is the half that catches a re-pin.
            if lv in BINDING and not d.get("note"):
                res.failures.append(
                    f"{name}: requirement {d.get('id','?')} ({lv}) has no instrument and no "
                    f"`note`. An uncovered requirement is allowed and is often the finding; an "
                    f"uncovered requirement nobody wrote a sentence about is an omission."
                )
        detail.append((d.get("id", "?"), lv, state, r["text"], oracle, ours,
                       gap or d.get("note", "")))

    return {"name": name, "category": cat, "tally": tally, "detail": detail,
            "spec_file": spec_file, "section": conf["section"], "rows": len(rows)}


def report(summary: dict, verbose: bool) -> None:
    print(f"\n=== {summary['name']}  (oracle category `{summary['category']}`) ===")
    print(f"    {summary['rows']} requirements declared by "
          f"{_rel(summary['spec_file'])} §{summary['section']}")
    print(f"    {'level':<13} {'total':>5} {'oracle':>7} {'partial':>8} {'ours':>5} {'none':>5}")
    for lv in LEVELS:
        t = summary["tally"][lv]
        if not t["total"]:
            continue
        mark = "  <-- binding" if lv in BINDING and (t["none"] or t["partial"]) else ""
        print(f"    {lv:<13} {t['total']:>5} {t['oracle']:>7} {t['partial']:>8} "
              f"{t['ours']:>5} {t['none']:>5}{mark}")
    for rid, lv, state, text, oracle, ours, note in summary["detail"]:
        if not verbose and not (state in ("none", "partial") and lv in BINDING):
            continue
        src = ", ".join(oracle) or ", ".join(f"ours:{o}" for o in ours) or "NOTHING"
        print(f"      {rid:<7} {lv:<9} {state:<8} {text[:70]}")
        print(f"              {src}")
        if note:
            for chunk in _wrap(note, 92):
                print(f"              {chunk}")


# ── the control ─────────────────────────────────────────────────────────────────────────

SELF_TEST_SPEC = """# Fake Extension

## 9. Conformance

### 9.1 Requirements

| Requirement | Level |
|-------------|-------|
| Alpha the widget | MUST |
| Beta the widget | MUST |
| Gamma the widget | SHOULD |
| Delta the widget | MAY |
"""


def self_test() -> int:
    """Every gate rule and both refusals, driven over synthetic inputs and observed firing.

    D15: a control proves the instrument CAN go red. The refusals are separate and prove it can
    say "I did not measure anything" — which is the state it will actually be in the day a spec
    re-pin moves a heading, and the state that otherwise presents as success.
    """
    import tempfile

    ok = True

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {label}")
        ok = ok and cond

    # Parser, clean.
    rows = parse_level_table(SELF_TEST_SPEC, "9.1")
    expect("level-table parses 4 rows", len(rows) == 4)
    expect("level-table reads the levels", [r["level"] for r in rows] ==
           ["MUST", "MUST", "SHOULD", "MAY"])

    # Parser refusal: the heading moved.
    expect("level-table REFUSES a missing section", parse_level_table(SELF_TEST_SPEC, "9.7") == [])

    # Parser corpus assertion: a table whose second column is not a level is not this table.
    wrong = SELF_TEST_SPEC.replace("| Requirement | Level |", "| Requirement | Owner |")
    expect("level-table REFUSES a table with no Level column", parse_level_table(wrong, "9.1") == [])

    # level-sections, and its declared level map.
    sect = ("## 11. Conformance\n\n### 11.1 MUST Implement\n\n- One thing (§2.1)\n"
            "- Two thing (§2.2)\n\n### 11.2 SHOULD Implement\n\n- Three thing (§3.1)\n")
    rs = parse_level_sections(sect, "11", {"MUST Implement": "MUST", "SHOULD Implement": "SHOULD"})
    expect("level-sections parses 3 rows", len(rs) == 3)
    expect("level-sections REFUSES an undeclared heading",
           parse_level_sections(sect, "11", {"MUST Implement": "MUST"}) == rs[:2])
    expect("sections are extracted for reporting", _sections_cited("One thing (§2.1)") == ["2.1"])

    # The four gate rules, over a synthetic tree.
    with tempfile.TemporaryDirectory() as td:
        snap = Path(td) / "snap"
        snap.mkdir()
        (snap / "EXTENSION-FAKE.md").write_text(SELF_TEST_SPEC)

        def run(reqs, corpus_checks, section="9.1", category="fake"):
            """Drives `evaluate()` — the function `check_extension` calls — not a copy of it."""
            contract = {
                "extension": {"name": "FAKE", "snapshot": "snap"},
                "conformance": {"spec_file": "EXTENSION-FAKE.md", "section": section,
                                "shape": "level-table", "oracle_category": category,
                                "requirement": reqs},
            }
            corpus = {"categories": {"fake": {c: {"PASS"} for c in corpus_checks}},
                      "checks": len(corpus_checks), "reports": 1, "files": 1,
                      "synthetic_dropped": 0, "digest": ""}
            res = Result()
            evaluate(contract, snap, corpus, res)
            return res

        def failed(res, needle):
            return any(needle in f for f in res.failures)

        full = [
            {"id": "A", "text": "Alpha the widget", "oracle": ["alpha_check"]},
            {"id": "B", "text": "Beta the widget", "oracle": ["beta_check"]},
            {"id": "C", "text": "Gamma the widget", "ours": ["gates/fake"]},
            {"id": "D", "text": "Delta the widget", "note": "nothing measures it"},
        ]
        r = run(full, ["alpha_check", "beta_check"])
        expect("clean mapping passes", not r.failures)

        r = run(full[:-1], ["alpha_check", "beta_check"])
        expect("rule 1: an undeclared spec row FAILS", failed(r, "UNDECLARED requirement"))

        r = run(full + [{"id": "Z", "text": "Epsilon the widget", "note": "x"}],
                ["alpha_check", "beta_check"])
        expect("rule 2: a row not in the spec FAILS", failed(r, "STALE requirement"))

        r = run(full, ["beta_check"])
        expect("rule 3: an oracle check not in the corpus FAILS",
               failed(r, "not in the executed corpus"))

        # Gamma is the SHOULD row: the note is required at BINDING levels only, so stripping
        # the MAY row's note would (correctly) not fire and the control would prove nothing.
        bad = [dict(x) for x in full]
        bad[2] = {"id": "C", "text": "Gamma the widget"}
        r = run(bad, ["alpha_check", "beta_check"])
        expect("rule 4: an uncovered BINDING row with no note FAILS", failed(r, "no `note`"))

        bad2 = [dict(x) for x in full]
        bad2[3] = {"id": "D", "text": "Delta the widget"}
        r = run(bad2, ["alpha_check", "beta_check"])
        expect("rule 4 does NOT fire on an uncovered MAY row", not failed(r, "no `note`"))

        # The two per-extension REFUSALS, which are a different failure from any of the four
        # rules above: they fire when the instrument cannot answer at all, and that is the state
        # that otherwise presents as success (D15 sharpened).
        r = run(full, ["alpha_check", "beta_check"], section="9.7")
        expect("refusal: a section the parser cannot find REFUSES",
               any("parsed ZERO requirements" in x for x in r.refusals) and not r.failures)

        r = run(full, ["alpha_check", "beta_check"], category="absent_category")
        expect("refusal: an oracle_category absent from the corpus REFUSES",
               any("absent from the executed corpus" in x for x in r.refusals))

    print()
    return 0 if ok else 1


# ── main ────────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ext", help="one extension slug (default: every extension-contracts/*)")
    ap.add_argument("--verbose", action="store_true", help="print every requirement, not only gaps")
    ap.add_argument("--self-test", action="store_true", help="the control (D15)")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    corpus = load_corpus()
    # The corpus is ECHOED before any verdict. Every `uncovered` below is scoped by exactly this
    # line, and a run over a narrower corpus prints a narrower line rather than a quieter verdict.
    print(f"executed corpus: {corpus['checks']} checks over "
          f"{len(corpus['categories'])} categories, from {corpus['reports']} reports "
          f"({corpus['synthetic_dropped']} synthetic core-profile carve-outs dropped)")
    print(f"corpus digest:   {corpus['digest'][:16]}")

    if not corpus["checks"]:
        print("\nREFUSING: the executed corpus is empty. Run `make conformance` first — a "
              "coverage verdict over zero checks would report every requirement as uncovered "
              "and would be describing this tree's build state, not the oracle.", file=sys.stderr)
        return 3

    ext_dirs = sorted((ROOT / "extension-contracts").glob("*"))
    if args.ext:
        ext_dirs = [d for d in ext_dirs if d.name == args.ext]
        if not ext_dirs:
            print(f"REFUSING: no extension-contracts/{args.ext}", file=sys.stderr)
            return 3
    ext_dirs = [d for d in ext_dirs if (d / "EXTENSION.toml").exists()]

    res = Result()
    summaries = []
    for d in ext_dirs:
        s = check_extension(d, corpus, res, args.verbose)
        if s:
            summaries.append(s)

    total_rows = sum(s["rows"] for s in summaries)
    if summaries and total_rows < MIN_REQUIREMENTS:
        res.refusals.append(
            f"the whole run parsed {total_rows} requirements across {len(summaries)} "
            f"extensions, below MIN_REQUIREMENTS={MIN_REQUIREMENTS}. That is a parser that has "
            f"stopped matching, not a corpus that has shrunk."
        )

    for s in summaries:
        report(s, args.verbose)

    if summaries:
        agg = {lv: [0, 0, 0, 0, 0] for lv in LEVELS}
        for s in summaries:
            for lv in LEVELS:
                t = s["tally"][lv]
                agg[lv][0] += t["total"];   agg[lv][1] += t["oracle"]
                agg[lv][2] += t["partial"]; agg[lv][3] += t["ours"]
                agg[lv][4] += t["none"]
        print("\n=== all extensions ===")
        print(f"    {'level':<13} {'total':>5} {'oracle':>7} {'partial':>8} {'ours':>5} {'none':>5}")
        for lv in LEVELS:
            if agg[lv][0]:
                print(f"    {lv:<13} {agg[lv][0]:>5} {agg[lv][1]:>7} {agg[lv][2]:>8} "
                      f"{agg[lv][3]:>5} {agg[lv][4]:>5}")

    if res.refusals:
        print("\nREFUSING:", file=sys.stderr)
        for r in res.refusals:
            print(f"  {r}", file=sys.stderr)
        return 3
    if res.failures:
        print(f"\nFAIL ({len(res.failures)}):", file=sys.stderr)
        for f in res.failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("\nOK — every declared requirement is mapped to an instrument or to a stated gap.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
