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

§5b — THE PINNED CHECK NAMES ARE JOINED THROUGH THE ORACLE'S OWN OBLIGATIONS
----------------------------------------------------------------------------
`[conformance.requirement].oracle` is 289 pins over 97 distinct `validate-peer` check names
(this tool's own `§5b:` census line, printed per extension and in the aggregate — not a figure
typed in here, which is AP-1's shape and was this docstring's first draft),
living in our tree — exactly what `PROPOSAL-CONFORMANCE-ORACLE-CONTRACT` §5b [MUST] says a
document outside an oracle's tree must not identify an obligation by. So every pinned name also
carries the obligation the ORACLE publishes for it (`spec_ref`, read from the reports, emitted
by `--bless-obligations`, never typed) in `[conformance.obligation]`, and three rules use it:

  * rule 3, split — a pin that vanishes is **RE-PINNED** when the corpus still carries its
    obligation and **MEASUREMENT LOST** only when nothing does. Before the map, this was ONE
    message offering both diagnoses, and the reading a hurried reader takes ("our contract is
    wrong") has the damaging fix: edit the mapping, deleting the record of coverage that is
    still there. At a re-pin renaming N checks that is N invitations.
  * rule 6 — the name held and the OBLIGATION MOVED under it. Rule 3 is satisfied throughout,
    because the check still resolves; nothing watched this direction.
  * rule 7 — an entry nothing pins any more. The re-pin direction that fails silently.

⚠ NOT full §5b compliance, and not to be cited as it (W-23): `spec_ref` is a SECTION CITATION,
not a `SPECIFICATION-FORMAT` §8.5a `<PREFIX>-R<n>` id. Its discriminating power is measured and
uneven — 40 pins join to exactly one candidate, four join to 222 — so the join answers *is this
obligation still measured* everywhere and *what is it called now* only where the obligation is
narrow. `SPREAD_NOISY` marks the wide case and the message refuses to reassure there.

REFUSALS (D15, sharpened) — this tool says "I did not measure anything" out loud
--------------------------------------------------------------------------------
  * no reports at all, or zero checks after exclusions        -> REFUSING, rc 3
  * a whole run parsing fewer than MIN_REQUIREMENTS rows      -> REFUSING, rc 3
  * a declared shape whose parser yields zero requirements    -> REFUSING for that extension
  * a declared `oracle_category` absent from the corpus       -> REFUSING for that extension
  * a corpus carrying no `spec_ref` for that category         -> REFUSING for that extension
  * `--bless-obligations` unable to key EVERY pinned name     -> REFUSING, emitting NOTHING

rc 3 is not a verdict. A clean verdict over an empty corpus is not a clean verdict, and this
instrument's fragile part is the two markdown parsers — a spec re-pin that re-words a heading
turns "0 requirements" into "0 problems" unless the refusal fires first.

The LAST refusal is AP-47 paid forward rather than re-learned. The sibling tool's `--bless`
emitted paste blocks for the stems that ran and nothing for the ones that did not; the output
looked complete, because absence has no representation in a paste block, and pasting it deleted
the baseline for every unmeasured stem. A partial obligation map fails the same way and worse:
the names it silently omits fall back to "no obligation declared", which rule 3 reports as the
UNDIAGNOSABLE case at exactly the re-pin that needed the diagnosis. So one unkeyable name
suppresses every block, across all extensions.

CONTROL: `--self-test` drives all seven gate rules, the rename/loss split in both directions
including the wide-obligation arm, the three per-extension refusals and the emitter's two,
over synthetic inputs, and requires each to fire. An instrument observed only passing is not an
instrument. The split was ALSO driven against the real corpus and the real CONTENT contract, by
planting the event `validate-peer` actually performs — `content/type_blob` renamed to
`content/type_blob_entity`, same obligation — which is how the wide case's first message was
found closing with a reassurance it could not support.

USAGE
    ./tools/req-coverage.py                     # every extension-contracts/<ext>
    ./tools/req-coverage.py --ext history       # one
    ./tools/req-coverage.py --verbose           # print every requirement, not only the gaps
    ./tools/req-coverage.py --bless-obligations # emit [conformance.obligation] (§5b)
    ./tools/req-coverage.py --self-test         # the control
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

# `SPECIFICATION-FORMAT` v1.3 §8.5a's CLOSED SIX, verbatim. `IMPL-DEFINED` is a real level: it
# says the spec declines to constrain the row, which is a different fact from "nothing checks it"
# and must not be reported as a gap.
#
# THE PROHIBITIONS WERE MISSING AND THAT COST US A ROW. Through the HISTORY v1.10 re-pin this
# tuple was `("MUST", "SHOULD", "MAY", "IMPL-DEFINED")` — written before §8.5a existed, from the
# levels the two specs we had happened to use. `HIST-R8` ("record the local peer's own
# `system/history/*` writes", MUST NOT, §3.2) parsed and was then DROPPED by the `level not in
# LEVELS` filter, so §9.1's sixteen rows arrived as fifteen and the missing one was a
# PROHIBITION — the recursion guard, and the row this repo authored its own wire check for.
#
# It did not refuse, because 15 of 16 matched: a vacuity refusal bounds a parser that stops
# matching and does nothing about one that matches the boring half. That gap is named in
# AGENTS.md under D15 and this is its second instance, which is why `assert_contiguous_ids`
# below exists — the levels tuple is now correct and the NEXT thing arch adds to it will be
# wrong here too, so the defence has to be structural rather than a longer list.
LEVELS = ("MUST", "MUST NOT", "SHOULD", "SHOULD NOT", "MAY", "IMPL-DEFINED")

# A requirement at these levels is expected to have an instrument. The rest are reported and
# never failed: `MAY` and `IMPL-DEFINED` rows are, by the spec's own words, not requirements on
# an implementation, so an "uncovered MAY" is a category error rather than a finding.
#
# `MUST NOT` and `SHOULD NOT` ARE BINDING. §8.5a says it in the table: a prohibition is "a
# requirement, and as checkable as a MUST". Reading a negative obligation as non-binding is how
# a recursion guard ends up in nobody's coverage tally.
BINDING = ("MUST", "MUST NOT", "SHOULD", "SHOULD NOT")


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


def parse_id_level_table(md: str, section: str) -> list[dict]:
    """Shape `id-level-table`: `SPECIFICATION-FORMAT` v1.3 §8.5a's addressable inventory.

    `| id | Requirement | Level | § |`, one row per independently failable obligation, with a
    `<PREFIX>-R<n>` id allocated once and never reused or renumbered. HISTORY §9.1 from v1.9.

    A SEPARATE SHAPE RATHER THAN A WIDENED `level-table`, and that is the point. The old shape
    is `| Requirement | Level | § |`; widening one parser to accept either would mean guessing
    which column is which from its contents, and a table that changed shape upstream would then
    parse as SOMETHING rather than refuse. The shape is declared in `[conformance].shape`, so a
    re-pin that changes it fails loudly — which is exactly what happened here: v1.9 added the id
    column and this file's `level-table` parser returned ZERO rows and REFUSED (D15), instead of
    reporting clean coverage over an empty inventory.
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
        if len(cells) < 3:
            continue
        if not header_seen:
            # ASSERTED, not assumed — same rule as `parse_level_table`. A table whose first
            # three columns are not (id, Requirement, Level) is a different table.
            if cells[0].lower() == "id" and cells[2].lower().startswith("level"):
                header_seen = True
            continue
        if set(cells[0]) <= set("-: "):
            continue
        level = cells[2].upper().strip()
        if level not in LEVELS:
            continue
        rid = cells[0].strip().strip("`")
        rows.append({
            "id": rid,
            "text": cells[1],
            "level": level,
            "section": cells[3] if len(cells) > 3 else "",
        })
    return rows


def assert_contiguous_ids(rows: list[dict], spec_file, section: str) -> None:
    """A CORPUS ASSERTION on the id sequence: `<PREFIX>-R1..RN`, no holes (D15 clause 2).

    §8.5a allocates ids "once and never reused or renumbered", starting at 1 — so a parsed set
    missing an interior number means THIS PARSER dropped a row, not that the spec skipped one.

    WHY THIS AND NOT A LONGER FILTER LIST. The tool already refuses when a parser yields zero
    rows, and that refusal is the wrong instrument for the failure it actually had: v1.9's
    `MUST NOT` row parsed correctly and was then discarded by a level filter, leaving 15 of 16 —
    a result too healthy to refuse and too small to be right. A count check would need a number
    to compare against, which is a second place to update at every re-pin; the id sequence is
    self-describing and arrives with the data. **The requirement it recovered was a prohibition,
    which is the class a coverage tally can least afford to lose**, because "nothing checks that
    we do not do X" reads identically to "X is not required".
    """
    ids = [r["id"] for r in rows if r.get("id")]
    if not ids:
        return
    nums, prefixes = [], set()
    for rid in ids:
        m = re.match(r"^(.*?-R)(\d+)$", rid)
        if not m:
            raise SystemExit(
                f"req-coverage: REFUSING — {_rel(spec_file)} §{section} row id {rid!r} is not "
                f"`<PREFIX>-R<n>` (SPECIFICATION-FORMAT v1.3 §8.5a). The id shape is the join "
                f"key; a row that does not carry one cannot be mapped."
            )
        prefixes.add(m.group(1))
        nums.append(int(m.group(2)))
    if len(prefixes) > 1:
        raise SystemExit(
            f"req-coverage: REFUSING — {_rel(spec_file)} §{section} mixes id prefixes "
            f"{sorted(prefixes)}. §8.5a declares ONE prefix per inventory."
        )
    missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
    if missing:
        pfx = prefixes.pop()
        raise SystemExit(
            f"req-coverage: REFUSING — {_rel(spec_file)} §{section} parsed "
            f"{len(nums)} rows with holes at {', '.join(pfx + str(n) for n in missing)}.\n"
            f"    §8.5a ids are contiguous from 1, so a hole is a row THIS PARSER dropped — "
            f"most likely a `Level` value not in LEVELS. Do not proceed: a coverage tally over "
            f"an inventory missing a row reads as coverage."
        )
    if len(set(nums)) != len(nums):
        raise SystemExit(
            f"req-coverage: REFUSING — {_rel(spec_file)} §{section} has duplicate row ids."
        )


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
    if shape == "id-level-table":
        rows = parse_id_level_table(md, conf["section"])
        assert_contiguous_ids(rows, spec_file, conf["section"])
    elif shape == "level-table":
        rows = parse_level_table(md, conf["section"])
    elif shape == "level-sections":
        rows = parse_level_sections(md, conf["section"], conf.get("levels", {}))
    else:
        raise SystemExit(f"req-coverage: unknown [conformance].shape {shape!r}")
    return rows, spec_file


# ── the oracle side ─────────────────────────────────────────────────────────────────────

def load_corpus() -> dict:
    """The executed check set, unioned over every report in the tree.

    Returns categories -> {check name -> set of severities seen}, the oracle's own
    check -> obligation map, plus the bookkeeping every negative claim below is scoped by.

    THE OBLIGATION IS READ, NEVER DECLARED. `entity-core-go` publishes it per check as
    `spec_ref`, and that is the map `PROPOSAL-CONFORMANCE-ORACLE-CONTRACT` §5b requires an
    oracle to publish — so we consume it rather than keeping a copy (D20, applied to a map
    instead of to code: the copy that could drift is the one we would keep). Held as a SET per
    name because two reports disagreeing about what a check is about is a real event with no
    right answer to pick, and picking one silently is how a join starts lying.
    """
    files = sorted(glob.glob(str(ROOT / "languages/*/output/*/reports/*.json")))
    cats: dict[str, dict[str, set]] = {}
    obls: dict[str, dict[str, set]] = {}
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
            cat = c.get("category", "?")
            cats.setdefault(cat, {}).setdefault(name, set()).add(
                c.get("severity", "?")
            )
            ref = c.get("spec_ref")
            if ref:
                obls.setdefault(cat, {}).setdefault(name, set()).add(ref)
    names = sorted(f"{cat}/{n}" for cat, ns in cats.items() for n in ns)
    # MEMBERSHIP, not assertions. This is a digest over `category/name` -- it identifies WHICH
    # checks the corpus below contains and says nothing about WHAT they assert. That is the
    # right quantity for the scope line it anchors, and it is the wrong quantity for a verdict:
    # `GUIDE-CONFORMANCE` §3.1 item 7 requires a published number be dual-anchored on the oracle
    # commit AND a `check_set_digest` over the exact assertions in the run, and bans by name the
    # family of "a value that tracks which checks ran rather than what they assert".
    #
    # Renamed 2026-09-15 from `digest` / "corpus digest". Nothing was wrong with the value or
    # with the one packet that quoted it as a scope; the NAME was arch's §5.1 term for the
    # sha256 of a fixture corpus artifact, and a membership value wearing that name is how the
    # substitution §3.7 bans gets made later by a reader who only sees the print line.
    membership = hashlib.sha256("\n".join(names).encode()).hexdigest()
    keyed = sum(len(ns) for ns in obls.values())
    return {
        "categories": cats,
        "obligations": obls,
        "reports": parsed,
        "files": len(files),
        "synthetic_dropped": synthetic,
        "checks": len(names),
        "keyed": keyed,
        "membership": membership,
    }


# ── the §5b seam: the oracle's check names, joined through the oracle's own obligations ──
#
# `PROPOSAL-CONFORMANCE-ORACLE-CONTRACT` §5b [MUST]: *a document, gate or baseline outside an
# oracle's own tree identifies a conformance obligation by its requirement id, never by an
# oracle's check name.* `[conformance.requirement].oracle` is 289 pins over 97 distinct check
# names across the three contracts — every one of them an oracle's internal name, in our tree.
#
# WHAT THE JOIN BUYS, AND IT IS ONE SENTENCE: a pinned name that vanishes at a re-pin is a
# RENAME if the corpus still carries its obligation, and a LOST MEASUREMENT only if nothing
# does. Before it, rule 3 said "which is not in the executed corpus. Either the name is wrong or
# the oracle stopped declaring it" — two diagnoses with opposite owners, and it could not tell
# them apart. The damaging half is the first reading: *our contract is wrong*, whose obvious fix
# is to edit our mapping, which is how coverage of a real requirement gets quietly deleted at
# somebody else's re-pin. This is `check-expectation.py`'s `requirement_keys()` one file over,
# and the same honest scope applies — `spec_ref` is a SECTION CITATION, not a `<PREFIX>-R<n>`
# id, so this is NOT full §5b compliance and must not be cited as it (W-23).
#
# ⚠ AND THE DISCRIMINATING POWER IS NOT UNIFORM, WHICH IS A MEASURED LIMIT RATHER THAN A
# CAVEAT. Measured over today's corpus, candidates sharing a pinned name's obligation:
#
#     40 pins   1 candidate    the join names the rename exactly
#     40 pins   2-6            a short list
#     13 pins   10-13          `COMPUTE §2.2, §8.1` is thirteen arithmetic/compare checks
#      4 pins   222-223        `type_system`: `Types §11.2` and `Types §12.3`, one per type
#                              entity in the whole registry
#
# So the join answers *is this obligation still measured* everywhere, and *what is it called
# now* only where the obligation is narrow. The wide case is the one that could read as
# reassurance — "something still carries it" over 223 candidates is nearly always true — so
# `SPREAD_NOISY` marks it and the failure message says the survival is weak evidence. That is
# D14's declared-limit habit, not a promise to fix it: the oracle publishes one `spec_ref` per
# check and no narrower key exists to join on.
SPREAD_NOISY = 7


def _rid(d: dict) -> str:
    """A requirement row's id for a message, falling back to its TEXT.

    COMPUTE's §10 has no `SPECIFICATION-FORMAT` §8.5a ids (arch's A-9), so a third of this
    tree's rows have no `id` at all and a message saying `requirement '?'` names nothing a
    reader can grep for. The whole point of these failures is to send somebody to one row.
    """
    rid = str(d.get("id") or "").strip()
    if rid:
        return rid
    text = _norm(str(d.get("text") or ""))
    return f"“{text[:60]}…”" if len(text) > 60 else f"“{text}”" if text else "?"


def _resolve(check: str, default_cat: str) -> tuple[str, str]:
    """`"name"` -> (the extension's own category, name); `"cat/name"` -> (cat, name).

    The qualified form is load-bearing rather than a convenience — see rule 3's comment.
    """
    ccat, _, cname = check.rpartition("/")
    return (ccat or default_cat), cname


def _obligation_of(corpus: dict, cat: str, name: str) -> tuple[str | None, set[str]]:
    """The obligation the ORACLE publishes for one check today, plus every value seen for it.

    Returns `(ref, all_refs)`. `ref` is None when the name is absent, carries no `spec_ref`, or
    carries more than one — the last being a disagreement between reports that this function
    refuses to resolve by picking.
    """
    refs = set(corpus.get("obligations", {}).get(cat, {}).get(name, set()))
    return (next(iter(refs)) if len(refs) == 1 else None), refs


def _carriers(corpus: dict, cat: str, ref: str) -> list[str]:
    """Every check in `cat` the oracle says is about `ref`, today."""
    return sorted(n for n, rs in corpus.get("obligations", {}).get(cat, {}).items() if ref in rs)


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

    # THE JOIN KEY IS THE SPEC'S ID WHERE THE SPEC HAS ONE, AND THE TEXT OTHERWISE.
    #
    # `SPECIFICATION-FORMAT` §8.5a allocates `<PREFIX>-R<n>` once and never renumbers, which
    # makes it a stabler key than the requirement's prose — and the difference is not cosmetic.
    # HISTORY's `HIST-R7` was RE-WORDED at v1.9 (v1.8's "support `max_depth` pruning" became
    # "retain at least `max_depth` entries per path", after arch's own ruling changed what §3.3
    # requires). Under a text join that is ONE STALE row plus ONE UNDECLARED row — two failures
    # describing one row that moved, and the natural fix for a reader in a hurry is to add the
    # new text and delete the old mapping, silently dropping whatever the old row declared.
    # Under an id join it is what it is: a row whose text changed, reported once.
    #
    # CONTENT's §11 has no ids and falls back to text, which is the shape that motivated the
    # original filing. When arch re-issues it under §8.5a this branch stops being reachable for
    # it, and nothing else has to change.
    spec_has_ids = all(r.get("id") for r in rows) and bool(rows)

    def _key(r: dict) -> str:
        return r["id"] if spec_has_ids and r.get("id") else _norm(r["text"])

    declared = {_key(r): r for r in conf.get("requirement", [])}
    seen_spec = {_key(r) for r in rows}

    # Rule 0 — when the spec carries ids, a declared row's TEXT must still match the spec's, or
    # the id is being used to carry a mapping onto a requirement that now says something else.
    # Reported as its own failure rather than folded into "stale": the id is right and the
    # obligation moved under it, which is the case a re-pin has to make somebody look at.
    if spec_has_ids:
        by_id = {r["id"]: r for r in rows}
        for d in conf.get("requirement", []):
            spec_row = by_id.get(d.get("id"))
            if spec_row is not None and _norm(d["text"]) != _norm(spec_row["text"]):
                res.failures.append(
                    f"{name}: RE-WORDED requirement {d['id']} — the id is unchanged and the "
                    f"obligation is not.\n"
                    f"    [conformance]: {d['text']!r}\n"
                    f"    {_rel(spec_file)} §{conf['section']}: {spec_row['text']!r}\n"
                    f"    Re-read what measures it before copying the new wording across."
                )

    # Rule 1 — every row the spec declares is declared here.
    for r in rows:
        k = _key(r)
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

    # ── Rules 5, 6 and 7 — the §5b obligation map, which is what makes rule 3 diagnosable ──
    #
    # Ordered before the tally loop because rule 3 CONSUMES this map: the same missing name is
    # either a rename or a lost measurement depending on it, and a run that reported rule 3
    # first would be answering with the worse of the two readings.
    declared_obl: dict[str, str] = conf.get("obligation", {}) or {}
    pinned: dict[str, list[str]] = {}          # `cat/name` -> the requirement ids pinning it
    for d in conf.get("requirement", []) or []:
        for check in d.get("oracle", []) or []:
            ccat, cname = _resolve(check, cat)
            pinned.setdefault(f"{ccat}/{cname}", []).append(_rid(d))

    # REFUSAL — the join key is absent from the corpus, so every verdict below it would be
    # "no obligation declared" for want of a report rather than for want of a declaration.
    # This is the state the tool is in against an oracle that stops publishing `spec_ref`, and
    # it presents as a tree full of failures pointing at our contracts (D15 sharpened).
    if pinned and not corpus.get("obligations", {}).get(cat):
        res.refusals.append(
            f"{name}: the executed corpus carries NO `spec_ref` for any check in category "
            f"{cat!r}, so the §5b obligation join has no key. {len(pinned)} pinned oracle "
            f"names cannot be told apart from renames. Either the oracle stopped publishing "
            f"its check -> requirement map, or these reports predate it."
        )
        return None

    for qual, ids in sorted(pinned.items()):
        ccat, cname = qual.split("/", 1)
        want = declared_obl.get(qual)
        have, all_refs = _obligation_of(corpus, ccat, cname)

        # Rule 5 — every pinned name declares the obligation it was pinned FOR. D16's shape: an
        # undeclared thing is a failure because the failure mode is a pin arriving without
        # anyone recording what it was about, and the record is only useful if it predates the
        # re-pin that needs it.
        if want is None:
            res.failures.append(
                f"{name}: oracle check {qual!r} (pinned by {', '.join(sorted(set(ids)))}) has "
                f"no entry in [conformance.obligation], so if it disappears at a re-pin a "
                f"RENAME cannot be told from a LOST MEASUREMENT (§5b). Run "
                f"`./tools/req-coverage.py --bless-obligations` and paste the block; every "
                f"value is read out of the oracle's own report."
            )
            continue

        # Rule 6 — THE OBLIGATION MOVED UNDER THE NAME. This is the direction nothing watched:
        # the name still resolves, so rule 3 is satisfied, and the oracle now says the check is
        # about a different clause than the one our requirement row pinned it for. A mapping
        # that survives that is coverage of one obligation being reported as coverage of
        # another — AP-2's mechanism with a check name in place of a number.
        if have is not None and have != want:
            res.failures.append(
                f"{name}: OBLIGATION MOVED — {qual!r} is pinned by "
                f"{', '.join(sorted(set(ids)))} and declared as {want!r}, and the oracle now "
                f"publishes it as {have!r}. The check kept its name and changed what it is "
                f"about. Re-read the requirement before re-blessing."
            )
        elif have is None and all_refs:
            # Two reports, two answers. There is no right one to pick, and picking silently is
            # how a join starts lying — so it is reported rather than resolved.
            res.failures.append(
                f"{name}: AMBIGUOUS OBLIGATION — {qual!r} carries "
                f"{len(all_refs)} different `spec_ref` values across the executed reports "
                f"({', '.join(sorted(all_refs))}). Two reports disagree about what one check "
                f"is about; the corpus spans more than one oracle build."
            )

    # Rule 7 — a declaration for a name nothing pins. The re-pin direction, and the one that
    # fails silently: an entry left behind after its requirement row dropped the pin reads as a
    # live part of the map and is the first thing a future join would consult.
    for qual in sorted(set(declared_obl) - set(pinned)):
        res.failures.append(
            f"{name}: STALE obligation entry — [conformance.obligation] declares {qual!r} and "
            f"no [[conformance.requirement]] pins it. The pin moved; the map did not."
        )

    # Rules 3 and 4 — the mapping resolves, and a gap says why.
    tally = {lv: {"total": 0, "oracle": 0, "partial": 0, "ours": 0, "none": 0}
             for lv in LEVELS}
    detail = []
    for r in rows:
        d = declared.get(_key(r))
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
            ccat, cname = _resolve(check, cat)
            if cname in corpus["categories"].get(ccat, {}):
                continue

            # ── §5b — A RENAME IS NOT A LOST MEASUREMENT, AND THIS IS WHERE THEY SPLIT ──────
            #
            # The old message here was one sentence offering two diagnoses — "either the name
            # is wrong or the oracle stopped declaring it" — with nothing able to choose. They
            # have opposite owners and opposite fixes, and the reading a reader in a hurry takes
            # is the damaging one: *our contract is wrong*, whose obvious remedy is to edit our
            # mapping. At a re-pin renaming N checks that is N invitations to delete coverage of
            # requirements that are still measured, in the file whose whole job is to record
            # what measures what.
            qual = f"{ccat}/{cname}"
            want = declared_obl.get(qual)
            carriers = _carriers(corpus, ccat, want) if want else []
            if want and carriers:
                shown = ", ".join(carriers[:6]) + (" …" if len(carriers) > 6 else "")
                # THE CAVEAT GETS THE LAST WORD WHERE IT APPLIES. The first draft printed the
                # spread warning and then closed with "the measurement did not go away; the NAME
                # did" — a sentence the wide case cannot support, in the most-read position.
                # Observed on the real corpus with a `type_system` pin planted missing: 222
                # candidates, and the reassurance was the line under the warning. A false
                # reassurance costs the instrument the same way a false red does.
                if len(carriers) >= SPREAD_NOISY:
                    tail = (
                        f"\n    ⚠ {len(carriers)} checks in {ccat!r} carry this obligation — it "
                        f"is a SECTION citation, not a per-check id — so its survival is WEAK "
                        f"evidence that this check's assertion survived. Join on it to find the "
                        f"new name, NOT to conclude the coverage held: read the candidates and "
                        f"decide, and if none of them asserts what the old one did, this is a "
                        f"MEASUREMENT LOST wearing a rename."
                    )
                else:
                    tail = (
                        f"\n    The measurement did not go away; the NAME did. Update the pin "
                        f"and the [conformance.obligation] entry together; do not touch "
                        f"`gap`/`note`."
                    )
                res.failures.append(
                    f"{name}: RE-PINNED (not lost) — requirement {_rid(d)} maps to "
                    f"oracle check {qual!r}, which is gone from the executed corpus, "
                    f"and the obligation it was pinned for ({want!r}) is still carried by: "
                    f"{shown}{tail}"
                )
            elif want:
                res.failures.append(
                    f"{name}: MEASUREMENT LOST — requirement {_rid(d)} maps to oracle "
                    f"check {qual!r}, which is gone from the executed corpus, and "
                    f"NOTHING in {ccat!r} carries its obligation ({want!r}) any more. This is "
                    f"the capability reading, and it is the one that has to reach a human: the "
                    f"oracle stopped measuring something our contract counted on. Re-declare "
                    f"the row as a `gap` with a note, and route it."
                )
            else:
                res.failures.append(
                    f"{name}: requirement {_rid(d)} maps to oracle check "
                    f"{qual!r}, which is not in the executed corpus — and no "
                    f"[conformance.obligation] entry exists for it, so a RENAME cannot be told "
                    f"from a LOST MEASUREMENT (§5b). Rule 5 above says the same thing about "
                    f"the declaration; fix that first and re-run for the real diagnosis."
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
            "spec_file": spec_file, "section": conf["section"], "rows": len(rows),
            # The §5b census, computed by the thing that reports it (D14: AP-1 is a number read
            # off a listing by eye, and the docstring above used to carry these two figures as
            # literals typed from a one-off script).
            "pins": sum(len(v) for v in pinned.values()), "pinned_names": len(pinned),
            "keyed_names": len([q for q in pinned if q in declared_obl])}


def report(summary: dict, verbose: bool) -> None:
    print(f"\n=== {summary['name']}  (oracle category `{summary['category']}`) ===")
    print(f"    {summary['rows']} requirements declared by "
          f"{_rel(summary['spec_file'])} §{summary['section']}")
    print(f"    §5b: {summary['pins']} oracle pins over {summary['pinned_names']} distinct "
          f"check names, {summary['keyed_names']} keyed to an obligation")
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


# ── the emitter ─────────────────────────────────────────────────────────────────────────

def _toml_key(s: str) -> str:
    """A TOML quoted key. Check names are `[a-z0-9_/]` today and hand-quoting is how the one
    that is not gets mis-parsed, so every key is quoted and every quote is escaped."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def bless_obligations(ext_dir: Path, corpus: dict) -> tuple[str, list[str]]:
    """The `[conformance.obligation]` block for one extension, read out of the oracle's reports.

    Returns `(block, refusals)`. **A NON-EMPTY REFUSAL LIST MEANS EMIT NOTHING**, and that is
    AP-47 paid forward rather than re-learned: `check-expectation.py --bless` emitted paste
    blocks for the stems that ran and nothing for the ones that did not, the output looked
    complete because absence has no representation in a paste block, and pasting it DELETED the
    baseline for every unmeasured stem — the maintenance command removing the artifact it
    maintains. A partial map here fails in the same direction and worse: the names it silently
    omits fall back to "no obligation declared", which rule 3 reports as the undiagnosable case
    at exactly the re-pin that needed the diagnosis.
    """
    contract = tomllib.loads((ext_dir / "EXTENSION.toml").read_text())
    name = contract["extension"]["name"]
    conf = contract.get("conformance") or {}
    cat = conf.get("oracle_category", "")

    pinned: dict[str, list[str]] = {}
    for d in conf.get("requirement", []) or []:
        for check in d.get("oracle", []) or []:
            ccat, cname = _resolve(check, cat)
            pinned.setdefault(f"{ccat}/{cname}", []).append(_rid(d))

    refusals: list[str] = []
    if not pinned:
        return "", [f"{name}: no [[conformance.requirement]] pins an oracle check. There is "
                    f"nothing to key, and an empty block would read as a complete map."]

    lines, unresolved = [], []
    for qual in sorted(pinned):
        ccat, cname = qual.split("/", 1)
        ref, all_refs = _obligation_of(corpus, ccat, cname)
        if ref is None:
            unresolved.append(
                f"{qual} — " + (
                    f"{len(all_refs)} conflicting `spec_ref` values ({', '.join(sorted(all_refs))})"
                    if all_refs else
                    "absent from the executed corpus, or carries no `spec_ref`"
                )
            )
            continue
        lines.append(f"{_toml_key(qual):<56} = {json.dumps(ref, ensure_ascii=False)}")

    if unresolved:
        refusals.append(
            f"{name}: REFUSING to emit a PARTIAL obligation map — {len(unresolved)} of "
            f"{len(pinned)} pinned names have no single obligation in this corpus:\n      "
            + "\n      ".join(unresolved)
            + f"\n    Emitting the other {len(lines)} would look complete and would leave every "
              f"name above undeclared (AP-47). Run `make conformance` for a composition that "
              f"exercises {cat!r}, or fix the pin first."
        )
        return "", refusals

    block = [
        "# ── §5b — the oracle's own check -> obligation map, for the pinned names ────────────────",
        "#",
        "# EMITTED, NEVER TYPED: `./tools/req-coverage.py --bless-obligations`. Every value is the",
        "# `spec_ref` `entity-core-go` publishes for that check in the reports we already hold, which",
        "# is the map `PROPOSAL-CONFORMANCE-ORACLE-CONTRACT` §5b requires an oracle to publish — so",
        "# this is a cached read of their artifact and not a second copy of their taxonomy (D20).",
        "#",
        "# It exists so that a re-pin which RENAMES a check reads as a rename: rule 3 joins a missing",
        "# pin through its obligation and says RE-PINNED when something still carries it, MEASUREMENT",
        "# LOST only when nothing does. Rule 6 fails when a name keeps its spelling and the oracle",
        "# changes what it is about, which is the direction nothing watched.",
        "#",
        "# ⚠ NOT full §5b compliance and not to be cited as it: `spec_ref` is a SECTION CITATION, not",
        "# a `SPECIFICATION-FORMAT` §8.5a `<PREFIX>-R<n>` id. Those do not exist yet (W-23, arch's A-1",
        "# and A-5). When they land, this block is re-blessed and nothing else changes.",
        "[conformance.obligation]",
        *lines,
    ]
    return "\n".join(block) + "\n", []


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

# §8.5a's shape, with a PROHIBITION in it. `FAKE-R3` is `MUST NOT` deliberately: the v1.10 re-pin
# lost exactly such a row to a levels tuple written before the closed six existed, and a fixture
# whose every level is positive could not have caught it.
SELF_TEST_SPEC_IDS = """# Fake Extension

## 9. Conformance

### 9.1 Requirements

| id | Requirement | Level | § |
|---|---|---|---|
| `FAKE-R1` | Alpha the widget | MUST | §2.1 |
| `FAKE-R2` | Beta the widget | SHOULD | §2.2 |
| `FAKE-R3` | Never widget the alpha | MUST NOT | §2.3 |
| `FAKE-R4` | Delta the widget | MAY | §2.4 |
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

    # id-level-table (§8.5a), clean — and the PROHIBITION survives.
    irows = parse_id_level_table(SELF_TEST_SPEC_IDS, "9.1")
    expect("id-level-table parses 4 rows", len(irows) == 4)
    expect("id-level-table reads the ids", [r["id"] for r in irows] ==
           ["FAKE-R1", "FAKE-R2", "FAKE-R3", "FAKE-R4"])
    expect("id-level-table keeps a MUST NOT row", [r["level"] for r in irows] ==
           ["MUST", "SHOULD", "MUST NOT", "MAY"])
    expect("MUST NOT is BINDING", "MUST NOT" in BINDING and "SHOULD NOT" in BINDING)

    # Parser corpus assertion: the id column is asserted, not assumed.
    wrong_id = SELF_TEST_SPEC_IDS.replace("| id | Requirement | Level | § |",
                                          "| ref | Requirement | Level | § |")
    expect("id-level-table REFUSES a table with no id column",
           parse_id_level_table(wrong_id, "9.1") == [])

    # The contiguity assertion — the control for the defect that motivated it. Dropping the
    # MUST NOT row is exactly what the old levels tuple did, so this plants that same hole.
    holed = [r for r in irows if r["id"] != "FAKE-R3"]
    try:
        assert_contiguous_ids(holed, Path("FAKE.md"), "9.1")
        expect("contiguity REFUSES an interior hole", False)
    except SystemExit as e:
        expect("contiguity REFUSES an interior hole", "FAKE-R3" in str(e))
    try:
        assert_contiguous_ids(irows, Path("FAKE.md"), "9.1")
        expect("contiguity does NOT fire on a complete set", True)
    except SystemExit:
        expect("contiguity does NOT fire on a complete set", False)

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
        (snap / "EXTENSION-FAKE-IDS.md").write_text(SELF_TEST_SPEC_IDS)

        def mkcorpus(corpus_checks):
            """`["a"]` -> one obligation each; `{"a": "SPEC §1"}` / `{"a": {"x","y"}}` -> stated.

            A list form defaults every check to a DISTINCT obligation rather than a shared one,
            because a fixture where every check carries the same `spec_ref` makes the rename
            join look exact when the real corpus has one obligation spread over 223 checks.
            """
            if isinstance(corpus_checks, dict):
                refs = {k: (v if isinstance(v, set) else {v}) for k, v in corpus_checks.items()}
            else:
                refs = {c: {f"SPEC §{i + 1}"} for i, c in enumerate(corpus_checks)}
            return {"categories": {"fake": {c: {"PASS"} for c in refs}},
                    "obligations": {"fake": refs},
                    "checks": len(refs), "reports": 1, "files": 1,
                    "synthetic_dropped": 0, "keyed": len(refs), "membership": ""}

        def run(reqs, corpus_checks, section="9.1", category="fake",
                shape="level-table", spec_file="EXTENSION-FAKE.md", obligation=None,
                unkeyed=False):
            """Drives `evaluate()` — the function `check_extension` calls — not a copy of it."""
            conf = {"spec_file": spec_file, "section": section,
                    "shape": shape, "oracle_category": category, "requirement": reqs}
            if obligation is not None:
                conf["obligation"] = obligation
            contract = {"extension": {"name": "FAKE", "snapshot": "snap"},
                        "conformance": conf}
            corpus = mkcorpus(corpus_checks)
            if unkeyed:
                # An oracle that publishes no check -> requirement map at all: the state this
                # tool is in against a pre-§5b report, and the one that would otherwise present
                # as "every one of your pins is undeclared".
                corpus["obligations"] = {}
                corpus["keyed"] = 0
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
        # The §5b map for `full`, matching `mkcorpus`'s list form. Every control below that is
        # NOT about the obligation join passes this, so a failure there is about its own subject.
        OBL = {"fake/alpha_check": "SPEC §1", "fake/beta_check": "SPEC §2"}

        r = run(full, ["alpha_check", "beta_check"], obligation=OBL)
        expect("clean mapping passes", not r.failures)

        r = run(full[:-1], ["alpha_check", "beta_check"], obligation=OBL)
        expect("rule 1: an undeclared spec row FAILS", failed(r, "UNDECLARED requirement"))

        r = run(full + [{"id": "Z", "text": "Epsilon the widget", "note": "x"}],
                ["alpha_check", "beta_check"], obligation=OBL)
        expect("rule 2: a row not in the spec FAILS", failed(r, "STALE requirement"))

        # Rule 0 — the id join, and the case it exists for. Same id, re-worded obligation:
        # HISTORY's `HIST-R7` at the v1.9 re-pin. Under the old TEXT join this was one STALE
        # plus one UNDECLARED — two failures for one row that moved, whose obvious fix silently
        # drops what the old row declared.
        ids_full = [
            {"id": "FAKE-R1", "text": "Alpha the widget", "oracle": ["alpha_check"]},
            {"id": "FAKE-R2", "text": "Beta the widget", "oracle": ["beta_check"]},
            {"id": "FAKE-R3", "text": "Never widget the alpha", "ours": ["gates/fake"]},
            {"id": "FAKE-R4", "text": "Delta the widget", "note": "nothing measures it"},
        ]
        kw = dict(shape="id-level-table", spec_file="EXTENSION-FAKE-IDS.md", obligation=OBL)
        r = run(ids_full, ["alpha_check", "beta_check"], **kw)
        expect("id join: a clean id-keyed mapping passes", not r.failures)

        reworded = [dict(x) for x in ids_full]
        reworded[1]["text"] = "Beta the widget, but differently now"
        r = run(reworded, ["alpha_check", "beta_check"], **kw)
        expect("rule 0: same id, re-worded obligation FAILS", failed(r, "RE-WORDED requirement"))
        expect("rule 0: and it is reported ONCE, not as stale+undeclared",
               not failed(r, "STALE requirement") and not failed(r, "UNDECLARED requirement"))

        # And the prohibition is BINDING end to end: uncovered, with no note, it must FAIL.
        bare_prohibition = [dict(x) for x in ids_full]
        bare_prohibition[2] = {"id": "FAKE-R3", "text": "Never widget the alpha"}
        r = run(bare_prohibition, ["alpha_check", "beta_check"], **kw)
        expect("rule 4: an uncovered MUST NOT with no note FAILS",
               any("FAKE-R3" in f or "Never widget" in f for f in r.failures))

        # Rule 3, with NO obligation map — the pre-§5b behaviour, kept as its own control
        # because the undiagnosable case still has to be reachable and still has to say so.
        r = run(full, ["beta_check"])
        expect("rule 3: an oracle check not in the corpus FAILS",
               failed(r, "not in the executed corpus"))
        expect("rule 3: with no obligation map it SAYS a rename cannot be told from a loss",
               failed(r, "cannot be told"))

        # ── §5b — THE SPLIT. One planted event, two corpora, two different verdicts ─────────
        #
        # This is the pair the whole map exists for, and it is planted as the thing a
        # `validate-peer` re-pin actually does: one check renamed, same obligation. Measured
        # before the map existed, the two cases were the SAME failure message offering two
        # diagnoses, and the reading a reader takes from it ("our contract is wrong") is the one
        # whose fix deletes coverage of a requirement that is still measured.
        r = run(full, {"alpha_check_v2": "SPEC §1", "beta_check": "SPEC §2"}, obligation=OBL)
        expect("§5b: a RENAMED oracle check reads as RE-PINNED, not lost",
               failed(r, "RE-PINNED (not lost)") and failed(r, "alpha_check_v2"))
        expect("§5b: and the capability framing is ABSENT from a rename",
               not failed(r, "MEASUREMENT LOST"))

        r = run(full, {"beta_check": "SPEC §2"}, obligation=OBL)
        expect("§5b: an obligation NOTHING carries reads as MEASUREMENT LOST",
               failed(r, "MEASUREMENT LOST"))
        expect("§5b: and it is NOT reported as a rename",
               not failed(r, "RE-PINNED"))

        # The spread warning, both directions. A caveat that fires on every rename is not
        # information, so the narrow arm asserting its ABSENCE is the half that makes it one.
        wide = {f"other_{i}": "SPEC §1" for i in range(SPREAD_NOISY)}
        wide["beta_check"] = "SPEC §2"
        r = run(full, wide, obligation=OBL)
        expect("§5b: a WIDE obligation warns that survival is weak evidence",
               failed(r, "WEAK evidence"))
        expect("§5b: and the WIDE case does NOT close with the reassurance",
               not failed(r, "the NAME did"))
        r = run(full, {"alpha_check_v2": "SPEC §1", "beta_check": "SPEC §2"}, obligation=OBL)
        expect("§5b: a NARROW obligation does not warn",
               not failed(r, "WEAK evidence") and failed(r, "the NAME did"))

        # Rule 5 — a pin with no entry in the map.
        r = run(full, ["alpha_check", "beta_check"],
                obligation={"fake/beta_check": "SPEC §2"})
        expect("rule 5: a pinned name with no obligation entry FAILS",
               failed(r, "has no entry in [conformance.obligation]")
               and failed(r, "alpha_check"))

        # Rule 6 — the name held and the obligation moved under it. The direction nothing
        # watched: rule 3 is satisfied throughout, because the check still resolves.
        r = run(full, {"alpha_check": "SPEC §9", "beta_check": "SPEC §2"}, obligation=OBL)
        expect("rule 6: an obligation that MOVED under a live name FAILS",
               failed(r, "OBLIGATION MOVED"))
        expect("rule 6: and rule 3 is silent, because the name still resolves",
               not failed(r, "not in the executed corpus"))

        # Two reports, two answers about one check. Reported, never resolved by picking.
        r = run(full, {"alpha_check": {"SPEC §1", "SPEC §9"}, "beta_check": "SPEC §2"},
                obligation=OBL)
        expect("a check carrying TWO `spec_ref` values FAILS as ambiguous",
               failed(r, "AMBIGUOUS OBLIGATION"))

        # Rule 7 — an entry left behind after the pin moved.
        r = run(full, ["alpha_check", "beta_check"],
                obligation={**OBL, "fake/gone_check": "SPEC §7"})
        expect("rule 7: an obligation entry nothing pins FAILS",
               failed(r, "STALE obligation entry"))

        # Gamma is the SHOULD row: the note is required at BINDING levels only, so stripping
        # the MAY row's note would (correctly) not fire and the control would prove nothing.
        bad = [dict(x) for x in full]
        bad[2] = {"id": "C", "text": "Gamma the widget"}
        r = run(bad, ["alpha_check", "beta_check"], obligation=OBL)
        expect("rule 4: an uncovered BINDING row with no note FAILS", failed(r, "no `note`"))

        bad2 = [dict(x) for x in full]
        bad2[3] = {"id": "D", "text": "Delta the widget"}
        r = run(bad2, ["alpha_check", "beta_check"], obligation=OBL)
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

        r = run(full, ["alpha_check", "beta_check"], obligation=OBL, unkeyed=True)
        expect("refusal: a corpus with NO `spec_ref` REFUSES rather than failing every pin",
               any("has no key" in x for x in r.refusals) and not r.failures)

        # ── THE EMITTER, and its refusal is the control that matters ────────────────────────
        #
        # AP-47 was found this same day in the sibling tool: `--bless` emitted paste blocks for
        # the stems that ran and nothing for the ones that did not, and pasting that output
        # DELETED the baseline for every unmeasured stem. A partial obligation map fails the
        # same way, so the emitter is all-or-nothing and this is where that is observed.
        extd = Path(td) / "ext"
        extd.mkdir()

        def write_contract(reqs):
            body = ['[extension]', 'name = "FAKE"', 'snapshot = "snap"', '',
                    '[conformance]', 'spec_file = "EXTENSION-FAKE.md"', 'section = "9.1"',
                    'shape = "level-table"', 'oracle_category = "fake"', '']
            for d in reqs:
                body += ['[[conformance.requirement]]', f'id = "{d["id"]}"',
                         f'text = "{d["text"]}"',
                         "oracle = [" + ", ".join(json.dumps(o) for o in d.get("oracle", []))
                         + "]", '']
            (extd / "EXTENSION.toml").write_text("\n".join(body))

        write_contract([{"id": "A", "text": "Alpha the widget", "oracle": ["alpha_check"]},
                        {"id": "B", "text": "Beta the widget", "oracle": ["beta_check"]}])
        block, refs = bless_obligations(extd, mkcorpus(["alpha_check", "beta_check"]))
        expect("bless: a complete corpus emits a block and no refusal", block and not refs)
        # The emitted block is PARSED back, because a paste block that does not parse is a
        # maintenance command handing a reader a broken file (and the sibling tool's own output
        # does not parse when concatenated — that is a known, stated limit there).
        parsed_back = tomllib.loads(block) if block else {}
        expect("bless: the emitted block PARSES and equals the oracle's map",
               parsed_back.get("conformance", {}).get("obligation") ==
               {"fake/alpha_check": "SPEC §1", "fake/beta_check": "SPEC §2"})

        block, refs = bless_obligations(extd, mkcorpus(["alpha_check"]))
        expect("bless: REFUSES a partial map and emits NOTHING (AP-47)",
               block == "" and any("PARTIAL" in r for r in refs))

        write_contract([{"id": "A", "text": "Alpha the widget"}])
        block, refs = bless_obligations(extd, mkcorpus(["alpha_check"]))
        expect("bless: REFUSES when nothing is pinned, rather than emitting an empty map",
               block == "" and any("nothing to key" in r for r in refs))

    print()
    return 0 if ok else 1


# ── main ────────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ext", help="one extension slug (default: every extension-contracts/*)")
    ap.add_argument("--verbose", action="store_true", help="print every requirement, not only gaps")
    ap.add_argument("--self-test", action="store_true", help="the control (D15)")
    ap.add_argument("--bless-obligations", action="store_true",
                    help="emit [conformance.obligation] from the oracle's own reports (§5b)")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    corpus = load_corpus()
    # The corpus is ECHOED before any verdict. Every `uncovered` below is scoped by exactly this
    # line, and a run over a narrower corpus prints a narrower line rather than a quieter verdict.
    print(f"executed corpus: {corpus['checks']} checks over "
          f"{len(corpus['categories'])} categories, from {corpus['reports']} reports "
          f"({corpus['synthetic_dropped']} synthetic core-profile carve-outs dropped)")
    print(f"corpus membership (sha256 over category/name -- NOT a check_set_digest, "
          f"§3.1(7)): {corpus['membership'][:16]}")

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

    if args.bless_obligations:
        print(f"obligation keys in the corpus: {corpus['keyed']} of {corpus['checks']} checks "
              f"carry a `spec_ref`\n")
        blocks, refusals = [], []
        for d in ext_dirs:
            block, refs = bless_obligations(d, corpus)
            refusals += refs
            if block:
                blocks.append((d, block))
        # ALL-OR-NOTHING ACROSS EXTENSIONS TOO. One refusal suppresses every block, because the
        # failure this guards is a reader pasting what they were given: a run that printed two
        # complete blocks and one refusal reads as "two done, one to look at", and the one to
        # look at is the one whose absence is invisible once the terminal scrolls.
        if refusals:
            print("REFUSING:", file=sys.stderr)
            for r in refusals:
                print(f"  {r}", file=sys.stderr)
            return 3
        for d, block in blocks:
            print(f"# ==> paste into extension-contracts/{d.name}/EXTENSION.toml, immediately "
                  f"after [conformance.levels]\n")
            print(block)
        return 0

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
        print(f"    §5b: {sum(s['pins'] for s in summaries)} oracle pins over "
              f"{sum(s['pinned_names'] for s in summaries)} distinct check names, "
              f"{sum(s['keyed_names'] for s in summaries)} keyed to an obligation")
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
