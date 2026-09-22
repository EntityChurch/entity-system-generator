#!/usr/bin/env python3
"""check-spec-lists.py — the spec's own enumerations, read as data and pinned.

## The axis, and the four incidents that earned it

Four declared deviations in `EXTENSION-COMPUTE` and **one cause**: an amendment reached the
prose and the conformance corpus without reaching a LIST somewhere else in the same
document.

    A-10  §4.2 `is_compute_type` enumerates 20 · §4.7 `is_compute_expression` enumerates
          13. Both omit `compute/index`, `compute/length`, `compute/numeric-cast` — three
          types §2.2 defines and §10.1 MUSTs by name. §4.2's Tier 1 IS that list and is
          the only tier admitting an ordinary sub-expression, so transcribing it literally
          makes any graph containing one of the three UNRESOLVABLE.
    A-11  §2.5's `system/compute/subgraph` field map declares 6 fields · §3.3 Phase 3
          writes 7 · §4.2, §1.1 and §10.1 all read the seventh.
    A-12  §4.1's `evaluate_inner` has arms for the 16 expression types and **none for the
          four §2.3 VALUE types**, while §2.3's SA-1 MUSTs that a value type evaluate to
          itself. A transcription answers `unknown_type` for a stored `compute/closure`.
    A-13  §4.1's construct arm keeps ONE representation (`result_fields[name] =
          content_store.put(...)`); §2.3's option-α clause requires in-flight navigation
          to compose, which needs two.

**Three of the four are a set-membership disagreement between two places in one spec.**
That is mechanically checkable, and nothing anywhere checked it — not the spec's own
gates, not the conformance corpus (`entity-core-go` already carries the corrected form in
every case, so no vector can fail on it), and not this repo, which found all four by
transcribing and then running.

D16's sentence, and this is the eighth instance: *the thing we own is the thing nothing
watches* — here the artifact is **the pinned spec snapshot**, which every gate in this
tree cites and no gate READS. `req-coverage.py` parses §10's bullets and nothing else
opens the file.

## What it does, and why it compares parse-to-DECLARATION rather than list-to-list

The naive gate diffs the spec's lists against each other and floods a reader with
differences that are correct by design — `is_compute_expression` SHOULD be shorter than
`is_compute_type`. A false red costs the instrument (AP-4), so instead:

  * `[[spec_lists]]` in `EXTENSION.toml` declares each enumeration by section, anchor,
    and exact membership, plus what our port carries and why they differ.
  * The gate re-parses each enumeration out of the pinned snapshot and requires the parse
    to EQUAL the declaration.

So the gate's job is not to have an opinion about the spec. It is to make a re-pin that
adds, drops or re-words a member **fail loudly** instead of silently invalidating a
transcription — which is precisely the event that produced A-10 and A-12, four amendments
apart, in a document nobody re-diffed.

## FAIL rules

  R1  every declared list's parsed membership equals its declared `members`
  R2  every type the spec DEFINES (`#### <name>` heading or `<name> := {` block) appears
      in at least one declared list, or in `[spec_lists_unlisted]` with a reason
  R3  a member our port does NOT implement, or an addition our port makes, is declared —
      `implemented` plus a `deviation` naming the sites on both sides
  R4  no declared list names a type the spec does not define anywhere

## D15: controls and refusals

  * **Control** (`--self-test`): a synthetic snapshot and contract with one planted defect
    per FAIL rule, and a clean arm that must pass. Four defects, four required catches.
  * **Refusals** — the fragile part is two markdown parsers, and a clean verdict over a
    corpus the parser lost is not a clean verdict:
      - fewer than `MIN_TYPES` type definitions parsed  -> REFUSING
      - fewer than `MIN_LISTS` declared lists in total  -> REFUSING
      - a declared `anchor` not found in the snapshot   -> REFUSING (the parser has lost
        the spec; a re-worded anchor is not a membership finding)
      - an enumeration that parses to ZERO members      -> REFUSING

  The anchor case is a refusal rather than a failure on purpose. After a re-pin that
  re-words `return entity.type in [`, every list would report empty and R2 would fire on
  all 33 types — a true statement about the parser wearing the shape of a spec finding.
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Vacuity floors. Both are far below the real corpus and exist to catch a parser that
# stopped matching, never to bound a real tree.
MIN_TYPES = 5
MIN_LISTS = 1

# A compute-ecosystem type name: `compute/...` or `system/<ext>/...`. Deliberately not
# anchored to one extension — HISTORY and CONTENT own `system/history/*` and
# `system/content/*` and this gate is not compute-specific.
TYPE_NAME = re.compile(r"^(?:[a-z][a-z0-9-]*/)+[a-z][a-z0-9-]*$")


class Refusal(Exception):
    """The instrument cannot answer. Never reported as a verdict."""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


# ── parsing the snapshot ────────────────────────────────────────────────────────────


def defined_types(md: str) -> dict[str, str]:
    """Every type the spec DEFINES, mapped to how it was found.

    Two sources, because the corpus uses both and neither is complete on its own:

      * `#### compute/literal` — a markdown heading, which is how §2.1-§2.4 declare the
        core IR types.
      * `system/compute/map-args := {` — a definition block, which is how §3.5 declares
        the args types that have no section of their own.

    Reporting WHICH source found each one is not decoration: a type that appears only as
    a `:=` block has no section anchor, so a reader chasing an R2 failure needs to know it
    is looking for a fenced block rather than a heading.
    """
    found: dict[str, str] = {}
    for m in re.finditer(r"^#{2,5}\s+`?([a-z][a-z0-9/_-]*)`?\s*$", md, re.M):
        name = m.group(1)
        if TYPE_NAME.match(name) and "/" in name:
            found.setdefault(name, "heading")
    for m in re.finditer(r"^([a-z][a-z0-9/_-]*)\s*:=\s*\{", md, re.M):
        name = m.group(1)
        if TYPE_NAME.match(name):
            found.setdefault(name, "definition-block")
    return found


def parse_list(md: str, spec: Path, decl: dict) -> list[str]:
    """Re-parse one declared enumeration out of the snapshot.

    `anchor` is a literal substring that opens the list and `terminator` closes it. Both
    are declared rather than guessed, because the corpus has at least three shapes —
    `return entity.type in [`, a `match entity.type:` arm ladder, and a bullet list — and
    a regex general enough for all three matches things that are not lists at all.
    """
    anchor = decl["anchor"]
    at = md.find(anchor)
    if at < 0:
        raise Refusal(
            f"{rel(spec)}: list {decl['id']!r} declares anchor {anchor!r} and the "
            f"snapshot does not contain it. The parser has lost the spec — a re-worded "
            f"anchor is a re-pin to reconcile, not a membership finding."
        )
    if md.find(anchor, at + 1) >= 0:
        raise Refusal(
            f"{rel(spec)}: list {decl['id']!r} anchor {anchor!r} occurs more than once. "
            f"Which occurrence is the list is then a coin flip, so it is not measured."
        )

    rest = md[at + len(anchor):]
    end = rest.find(decl["terminator"])
    if end < 0:
        raise Refusal(
            f"{rel(spec)}: list {decl['id']!r} has no terminator "
            f"{decl['terminator']!r} after its anchor."
        )
    body = rest[:end]

    # `member_pattern` is declared per list, and the default is a bare quoted-token scan.
    #
    # THE DEFAULT IS NOT GOOD ENOUGH FOR AN ARM LADDER, and that is why the field exists.
    # §4.1's `evaluate_inner` body is full of quoted type names that are not arm labels —
    # `check_path_permission("get", path, ctx.capability, "system/tree", …)`,
    # `if fn_value.type != "compute/closure"`, `"primitive/uint"`,
    # `"system/compute/builtins/…"`. A quoted-token scan over that body reports a dozen
    # members that are not members, which is a false red on the one list this gate most
    # needs to read (A-12). The ladder's labels are the only quoted names alone on a line
    # and followed by a colon, so the pattern says exactly that.
    #
    # A spec comment inside the fence (`; system/compute/uninstall-request eliminated in
    # v3.12`) is UNQUOTED either way and must not count — that line is the difference
    # between §4.2's list being 20 and being 21.
    pattern = re.compile(decl.get("member_pattern", r'"([^"]+)"'), re.M)
    out: list[str] = []
    for m in pattern.finditer(body):
        name = m.group(1)
        if TYPE_NAME.match(name) and name not in out:
            out.append(name)
    if not out:
        raise Refusal(
            f"{rel(spec)}: list {decl['id']!r} parsed ZERO members between its anchor "
            f"and terminator. An empty enumeration is not a finding about the spec."
        )
    return out


# ── the gate ────────────────────────────────────────────────────────────────────────


class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.lines: list[str] = []
        self.lists = 0
        self.types = 0


def check_contract(contract: dict, spec: Path, res: Result, *, name: str) -> None:
    md = spec.read_text()

    defined = defined_types(md)
    if len(defined) < MIN_TYPES:
        raise Refusal(
            f"{rel(spec)}: parsed {len(defined)} type definitions, below the floor of "
            f"{MIN_TYPES}. Both heading and definition-block parsers have stopped "
            f"matching; every membership verdict below would read `absent` for want of a "
            f"parse rather than for want of a member."
        )
    res.types += len(defined)

    decls = contract.get("spec_lists", [])
    res.lists += len(decls)
    res.lines.append(f"  {name}: {len(defined)} types defined, {len(decls)} lists declared")

    # AN EXTENSION WHOSE SPEC ENUMERATES NOTHING, and the hole this would otherwise leave.
    #
    # R2 asks *"does every defined type reach one of the spec's own enumerations"*. With
    # zero enumerations that question is vacuous, not answered NO — CONTENT and HISTORY
    # define no membership predicate at all, because neither is an interpreter, and firing
    # R2 on all sixteen of their types would put a false red per type in front of a reader
    # (AP-4).
    #
    # But "declare no lists and R2 goes quiet" is a false-green door, so the exemption is
    # not automatic: the contract must say so in `spec_lists_none`, with the search that
    # establishes it. An omission fails; a decision passes and prints.
    if not decls:
        why = contract.get("spec_lists_none")
        if not why:
            res.failures.append(
                f"{name}: declares no `[[spec_lists]]` and no `spec_lists_none` reason. "
                f"R2 cannot run, and an instrument that goes quiet when it has nothing to "
                f"read is the false green this gate was written against. Declare the "
                f"enumerations, or declare — with the search — that the spec has none."
            )
        else:
            res.lines.append(f"    none       R2 not applicable: {why.splitlines()[0][:110]}")
        return

    seen_anywhere: set[str] = set()

    for decl in decls:
        parsed = parse_list(md, spec, decl)
        declared = list(decl["members"])
        seen_anywhere.update(parsed)
        seen_anywhere.update(declared)

        # R1 — the parse equals the declaration.
        if parsed != declared:
            added = [t for t in parsed if t not in declared]
            dropped = [t for t in declared if t not in parsed]
            detail = []
            if added:
                detail.append(f"the snapshot has {added} and the declaration does not")
            if dropped:
                detail.append(f"the declaration has {dropped} and the snapshot does not")
            if not detail:
                detail.append("same members, different ORDER — and order is declared "
                              "because a list re-ordered is a list somebody edited")
            res.failures.append(
                f"{name}: R1 list {decl['id']!r} (§{decl['section']}): " + "; ".join(detail)
            )
            continue

        # R4 — a declared member the spec never defines.
        ghosts = [t for t in declared if t not in defined]
        if ghosts:
            res.failures.append(
                f"{name}: R4 list {decl['id']!r} (§{decl['section']}) names {ghosts}, "
                f"which the snapshot defines nowhere — neither as a heading nor as a "
                f"`:=` block. Either the type was eliminated and the list was not "
                f"updated, or the name is misspelled in one of the two places."
            )

        # R3 — what our port carries, against what the list says.
        implemented = list(decl.get("implemented", declared))
        extra = [t for t in implemented if t not in declared]
        missing = [t for t in declared if t not in implemented]
        if (extra or missing) and not decl.get("deviation"):
            res.failures.append(
                f"{name}: R3 list {decl['id']!r} (§{decl['section']}) — this port "
                f"implements {implemented!r} against the spec's {declared!r} "
                f"(extra={extra}, missing={missing}) and declares no `deviation`. "
                f"A membership difference with no reason is a transcription error until "
                f"somebody writes down which it is."
            )
        elif extra or missing:
            res.lines.append(
                f"    deviation  {decl['id']}: +{len(extra)} -{len(missing)} "
                f"— {decl['deviation'].splitlines()[0][:96]}"
            )
        else:
            res.lines.append(f"    ok         {decl['id']}: {len(declared)} members, verbatim")

    # R2 — every defined type reaches at least one declared list, or is excused.
    excused = dict(contract.get("spec_lists_unlisted", {}))
    orphans = sorted(t for t in defined if t not in seen_anywhere and t not in excused)
    if orphans:
        res.failures.append(
            f"{name}: R2 the snapshot defines {orphans} and no declared list names any of "
            f"them, and `[spec_lists_unlisted]` does not excuse them. Either a list is "
            f"undeclared here or the spec defines a type none of its own predicates admit "
            f"— which is A-10 exactly, and is the case this rule exists to surface."
        )
    for t, why in sorted(excused.items()):
        if t in seen_anywhere:
            res.failures.append(
                f"{name}: R2 `[spec_lists_unlisted]` excuses {t!r} and a declared list "
                f"names it. An excuse that is not needed is an excuse that will outlive "
                f"the reason it was written for (AP-2)."
            )
        elif t not in defined:
            res.failures.append(
                f"{name}: R2 `[spec_lists_unlisted]` excuses {t!r} and the snapshot does "
                f"not define it."
            )
        else:
            res.lines.append(f"    unlisted   {t}: {why.splitlines()[0][:96]}")


def run(root: Path) -> Result:
    res = Result()
    contracts = sorted((root / "extension-contracts").glob("*/EXTENSION.toml"))
    if not contracts:
        raise Refusal(
            f"{rel(root / 'extension-contracts')}: no EXTENSION.toml found. Nothing to "
            f"measure, which is not the same as nothing wrong."
        )
    for path in contracts:
        contract = tomllib.loads(path.read_text())
        ext = contract["extension"]
        spec = root / "shared/spec-data" / ext["snapshot"] / ext["spec"]
        if not spec.exists():
            raise Refusal(f"{rel(path)}: snapshot {rel(spec)} does not exist.")
        check_contract(contract, spec, res, name=ext["name"])

    if res.lists < MIN_LISTS:
        raise Refusal(
            f"{res.lists} declared lists across {len(contracts)} extension(s), below the "
            f"floor of {MIN_LISTS}. A gate over no enumerations reports OK on every "
            f"corpus, including a broken one."
        )
    return res


# ── the control ─────────────────────────────────────────────────────────────────────

CLEAN_SPEC = """
# Fake Extension

#### fake/alpha
#### fake/beta
#### fake/gamma
#### fake/value

```
system/fake/args := {
  fields: { x: {type_ref: "system/hash"} }
}
```

### 9.1 Detection

```
is_fake_expression(entity):
  return entity.type in [
    "fake/alpha", "fake/beta",
    "fake/gamma"
    ; fake/deleted eliminated in v0.2 — must NOT be read as a member
  ]
```
"""

CLEAN_CONTRACT = {
    "extension": {"name": "FAKE", "spec": "SPEC.md", "snapshot": "fake"},
    "spec_lists": [
        {
            "id": "is_fake_expression",
            "section": "9.1",
            "anchor": "return entity.type in [",
            "terminator": "]",
            "members": ["fake/alpha", "fake/beta", "fake/gamma"],
        }
    ],
    "spec_lists_unlisted": {
        "fake/value": "a value type; no predicate admits it, and that is the point",
        "system/fake/args": "an args type, declared as a `:=` block with no predicate",
    },
}


def self_test() -> int:
    # `copy` and `tempfile` are imported at module scope rather than here, and that is
    # not style: `make toolchain` reads TWO doors, and a LAZY import is the second one --
    # the door the one real third-party dependency in this tree arrives through
    # (`__import__(decl["package"])`). It flagged this file on its first run.
    planted = [
        # R1 — the declaration is stale: the spec's list has a member it does not.
        ("R1 stale declaration",
         CLEAN_SPEC,
         lambda c: c["spec_lists"][0]["members"].remove("fake/gamma")),
        # R2 — a defined type in no list and not excused.
        ("R2 orphan type",
         CLEAN_SPEC,
         lambda c: c["spec_lists_unlisted"].pop("fake/value")),
        # R3 — the port implements more than the list and says nothing about why.
        ("R3 undeclared deviation",
         CLEAN_SPEC,
         lambda c: c["spec_lists"][0].__setitem__(
             "implemented", ["fake/alpha", "fake/beta", "fake/gamma", "fake/value"])),
        # R4 — the list names a type the spec defines nowhere.
        ("R4 ghost member",
         CLEAN_SPEC.replace('"fake/gamma"', '"fake/ghost"'),
         lambda c: c["spec_lists"][0]["members"].__setitem__(2, "fake/ghost")),
    ]

    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "extension-contracts/fake").mkdir(parents=True)
        (base / "shared/spec-data/fake").mkdir(parents=True)

        def write(spec_text: str, contract: dict) -> None:
            (base / "shared/spec-data/fake/SPEC.md").write_text(spec_text)
            (base / "extension-contracts/fake/EXTENSION.toml").write_text(
                _toml_dump(contract))

        # The clean arm. An instrument that only ever goes red is not a control.
        write(CLEAN_SPEC, CLEAN_CONTRACT)
        try:
            res = run(base)
            if res.failures:
                ok = False
                print(f"  self-test FAIL: clean corpus reported {res.failures}")
            else:
                print("  self-test ok: clean corpus passes")
        except Refusal as e:
            ok = False
            print(f"  self-test FAIL: clean corpus REFUSED — {e}")

        for label, spec_text, mutate in planted:
            contract = copy.deepcopy(CLEAN_CONTRACT)
            mutate(contract)
            write(spec_text, contract)
            try:
                res = run(base)
                caught = [f for f in res.failures if label.split()[0] in f]
                if caught:
                    print(f"  self-test ok: caught {label}")
                else:
                    ok = False
                    print(f"  self-test FAIL: {label} NOT caught "
                          f"(failures: {res.failures})")
            except Refusal as e:
                ok = False
                print(f"  self-test FAIL: {label} REFUSED instead of failing — {e}")

        # And a refusal control: a re-worded anchor must REFUSE, not report 33 findings.
        write(CLEAN_SPEC.replace("return entity.type in [", "return entity.kind in ["),
              copy.deepcopy(CLEAN_CONTRACT))
        try:
            run(base)
            ok = False
            print("  self-test FAIL: a missing anchor did not REFUSE")
        except Refusal:
            print("  self-test ok: a re-worded anchor REFUSES rather than failing")

    print("SELF-TEST: " + ("OK" if ok else "BROKEN"))
    return 0 if ok else 1


def _toml_dump(obj: dict) -> str:
    """The three shapes this control needs, and no more.

    Written out rather than reached for because `tomli_w` is a third-party package and the
    host half of this toolchain is stdlib-only (`docs/adr/0001-*`). A control that cannot
    run on a bare host is a control that stops running.
    """
    def val(v):
        if isinstance(v, str):
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if isinstance(v, list):
            return "[" + ", ".join(val(x) for x in v) + "]"
        raise TypeError(type(v))

    def key(k: str) -> str:
        # A type name is a legal TOML key only when quoted — `fake/value = "..."` is a
        # parse error, and the control's own corpus is made entirely of type names.
        return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else '"' + k + '"'

    out: list[str] = []
    for name, section in obj.items():
        if isinstance(section, list):
            for entry in section:
                out.append(f"[[{name}]]")
                out += [f"{key(k)} = {val(v)}" for k, v in entry.items()]
        else:
            out.append(f"[{name}]")
            out += [f"{key(k)} = {val(v)}" for k, v in section.items()]
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--self-test", action="store_true",
                    help="run the planted-defect control and exit")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    try:
        res = run(Path(args.root).resolve())
    except Refusal as e:
        print(f"spec-lists: REFUSING — {e}", file=sys.stderr)
        return 2

    for line in res.lines:
        print(line)
    print(f"\n{res.lists} declared enumerations over {res.types} type definitions")

    if res.failures:
        print("\nSPEC-LISTS: " + str(len(res.failures)) + " failure(s).")
        for f in res.failures:
            print(f"  {f}")
        print("\nA list in one section that disagrees with a definition in another is how "
              "A-10 and A-12 reached three ports of two extensions. The declaration is "
              "the reconciliation; a re-pin that changes a member has to move it.")
        return 1

    print("SPEC-LISTS: OK — every declared enumeration matches the pinned snapshot, and "
          "every defined type is listed or excused.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
