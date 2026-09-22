#!/usr/bin/env python3
"""check-routing.py — our outbox is readable by the seat it is addressed to.

## The axis, and why it had no gate

`AGENTS-STANDARD.md` §*Routing packets* pins the shape of a routing packet: an addressee
block of three fields, each on its own line, opening the document. The enforcement point
named there is **arch's `spec inbound`**, and that is the whole problem this gate exists
for — **the only instrument that reads our outbox lives in another repo, and nothing in
this tree had ever run it against us.**

Measured 2026-09-09, one variable, same tool state, `scanned 410` in both arms:

    before:  OURS  owed 2   unaddressed 11
    after:   OURS  owed 3   unaddressed 0

**Eleven of our twenty-two packets could not be routed mechanically.** Every one of them
named its recipient in its own H1, so a human reading the directory found them — and two
were in fact found that way. That is the failure mode exactly: it works until nobody
happens to look, and there is no reading of the sending tree that reveals it.

D16's sentence, sixth instance and a new shape: *the thing we own is the thing nothing
watches.* The previous five were axes with no upstream authority. **This one HAS an
upstream authority and a live instrument — in someone else's tree.** An enforcement point
you never execute is a wish with a citation attached.

## Why `owed` going UP is this gate working

The backfill moved `ROUTING-2026-09-03-b-keystone-h7-*` from `unaddressed` to `owed`: it
names `entity-system-architecture` as a co-recipient and arch has no ledger row for it.
It had been sitting in the UNKNOWN bucket, which reads as *nobody's* and is never *"not
theirs"*. A number that gets worse when a defect is fixed is the number that was lying.

## What is a FAILURE here, and what is only counted

FAIL — the shape arch's reader parses, which is the thing that determines delivery:

  R1  the three fields open the document, each on its own line, in order
  R2  `To:` names at least one repo; `From:` is this repo; `cc:` is repos or an em dash
  R3  the filename's recipient token agrees with a `To:` entry
  R4  no `<date>-<letter>` id is reused inside this tree

COUNTED, never failed — citation form (`--strict-citations` promotes it). A citation of the
form `ROUTING-<date>-<letter>` with no recipient token cannot be resolved by a reader, and
the sharp case is cross-repo: our handoffs cite `ROUTING-2026-09-08-c` meaning **arch's**
packet while this tree numbers `2026-09-08` too. It is counted rather than failed because
fixing it is a prose sweep over documents that are committed record, and **a false red
costs the instrument** (AP-4) — the census names every instance so the sweep is a decision
rather than a discovery.

## R5 is a report, not a rule, and that is deliberate

Whether a `To:` repo exists as a sibling directory depends on how the operator's machine is
laid out. `check-citations.py` learned this the expensive way: a gate that goes red on a
clean checkout is a gate somebody turns off. Absent peers root -> `unknown`, never a
failure.

## D15: control and refusal

- **Control** (`--self-test`): a synthetic corpus with one planted defect per FAIL rule,
  each required to be caught, plus a clean packet required NOT to be flagged. The planted
  corpus is driven through the same `collect()`/`check()` the real run uses — not a copy.
- **Refusal:** zero packets parsed, or zero `To:` fields extracted across the corpus. The
  parse is the fragile part, and a clean verdict over an empty corpus is the false green
  this class of instrument keeps producing (D15's sharpening).

    ./tools/check-routing.py
    ./tools/check-routing.py --self-test
    ./tools/check-routing.py --strict-citations
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATUS = ROOT / "docs" / "status"
SELF = "entity-system-generator"

# A packet whose recipient token is not a suffix of the repo it names. One entry, and it
# is a naming fact about another seat rather than a member of anything of ours (D20).
ALIASES = {"arch": "entity-system-architecture"}

# Declared 2026-09-09. Six packets share two ids because the no-letter slot was used three
# times on each of two days -- exactly the collision AGENTS-STANDARD warns about. They are
# NOT renamed: arch cites five of our packets by full stem already, and renaming committed
# record to satisfy a gate breaks the reader it was written for. Full stems disambiguate
# all six. This list is dated and does not grow; a new collision is R4 and fails.
LEGACY_COLLISIONS = {("2026-09-03", None), ("2026-09-07", None)}

BLOCK = ("To", "From", "cc")
FIELD_RE = re.compile(r"^\*\*(To|From|cc):\*\*\s*(.*)$")
REPO_RE = re.compile(r"`([a-z][a-z0-9-]+)`")
STEM_RE = re.compile(r"ROUTING-(\d{4}-\d{2}-\d{2})(?:-([a-z]))?-(.+)$")


def tokens_for(repo: str) -> set[str]:
    """The filename recipient tokens that legitimately stand for `repo`.

    Every trailing hyphen-segment suffix, plus any alias. Derived rather than tabulated:
    the first draft of R3 split the token off POSITIONALLY with a non-greedy group, which
    read `core-go` as `core` and put five false reds in front of a reader on run one. A
    token is a name for a repo, so ask the repo (D15 -- and the arrow points at the field,
    not at a second copy of the naming convention).
    """
    parts = repo.split("-")
    out = {"-".join(parts[i:]) for i in range(len(parts))}
    out |= {a for a, r in ALIASES.items() if r == repo}
    return out

# A packet citation that is not a full stem. Group 1 is the id it stops at.
BARE_CITE_RE = re.compile(r"ROUTING-(\d{4}-\d{2}-\d{2}(?:-[a-z])?)(?![-\w])")
GLOB_CITE_RE = re.compile(r"ROUTING-(\d{4}-\d{2}-\d{2}(?:-[a-z])?-[a-z0-9-]*)\*")


class Packet:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.name = path.name
        self.stem = path.stem
        self.lines = path.read_text().split("\n")
        self.fields: dict[str, str] = {}
        self.field_lines: dict[str, int] = {}
        for i, line in enumerate(self.lines[:10]):
            m = FIELD_RE.match(line)
            if m and m.group(1) not in self.fields:
                self.fields[m.group(1)] = m.group(2).strip()
                self.field_lines[m.group(1)] = i

    @property
    def to(self) -> list[str]:
        return REPO_RE.findall(self.fields.get("To", ""))

    @property
    def id(self) -> tuple[str, str | None]:
        m = STEM_RE.match(self.stem)
        return (m.group(1), m.group(2)) if m else ("", None)


def collect(directory: pathlib.Path) -> list[Packet]:
    return [Packet(p) for p in sorted(directory.glob("ROUTING-*.md"))]


def check(packets: list[Packet], legacy: set) -> list[str]:
    """Every FAIL rule. Returns one string per violation."""
    bad: list[str] = []
    seen: dict[tuple, str] = {}

    for p in packets:
        # R1 -- the three fields open the document, each on its own line, in order.
        missing = [f for f in BLOCK if f not in p.fields]
        if missing:
            bad.append(f"{p.name}: R1 no addressee block -- missing {', '.join(missing)}")
            continue
        order = [p.field_lines[f] for f in BLOCK]
        if order != sorted(order) or len(set(order)) != 3:
            bad.append(f"{p.name}: R1 the three fields are not in order on their own lines")
        if max(order) - min(order) != 2:
            bad.append(f"{p.name}: R1 the block is not contiguous (lines {order})")

        # R2 -- the fields say something a reader can act on.
        if not p.to:
            bad.append(f"{p.name}: R2 To: names no repository")
        if SELF in p.to:
            # Also the tell for a To:/From: collapsed onto one line -- the field value runs
            # to the end of the line and swallows the sender. Caught here rather than as
            # mystery fallout in T1, which is where it first showed up.
            bad.append(f"{p.name}: R2 To: names this repo -- a packet addressed to its own sender")
        if p.fields["From"].strip("`. ") != SELF:
            bad.append(f"{p.name}: R2 From: is {p.fields['From']!r}, expected `{SELF}`")
        cc = p.fields["cc"]
        if cc not in ("—", "-") and not REPO_RE.findall(cc):
            bad.append(f"{p.name}: R2 cc: is neither an em dash nor a repository list")

        # R3 -- the filename agrees with the field. A packet filed under one seat's token
        # and addressed to another is findable by neither.
        m = STEM_RE.match(p.stem)
        if not m:
            bad.append(f"{p.name}: R3 filename is not ROUTING-<date>[-<letter>]-<recipient>-<slug>")
        else:
            rest = m.group(3)
            ok = any(
                rest.startswith(tok + "-") for r in p.to for tok in tokens_for(r)
            )
            if not ok and p.to:
                bad.append(
                    f"{p.name}: R3 filename recipient in {rest!r} names none of To: "
                    f"{', '.join(p.to)}"
                )

        # R4 -- an id reused inside one tree is a defect in the sender's tree.
        pid = p.id
        if pid[0] and pid in seen and pid not in legacy:
            bad.append(f"{p.name}: R4 id {pid[0]}{'-' + pid[1] if pid[1] else ''} already used by {seen[pid]}")
        seen.setdefault(pid, p.name)

    return bad


TRACKER_SECTIONS = (
    "## Open — asks",
    "## Corrections we owe them",
    "## Filed, nothing owed back to us",
    "## Closed",
)
ASK_ID_RE = re.compile(r"\*\*([A-Z]{1,2}-\d+)\*\*")


def check_trackers(packets: list[Packet], directory: pathlib.Path) -> list[str]:
    """One tracker per counterpart, and every packet accounted for in one.

    `entity-system-architecture`'s cleanup standard of 2026-09-09: arch reconciles against
    the tracker, NOT against the directory. That inverts what has to be complete -- a packet
    missing from a tracker is now invisible in a way that a packet sitting in `docs/status/`
    was not, because the directory at least had an `ls`. **T3 is the whole point of this
    block**: the failure it catches is routing a new packet and forgetting the row.
    """
    bad: list[str] = []
    recipients = {r for p in packets for r in p.to}
    if not recipients:
        return ["REFUSING-INPUT: no recipients extracted"]

    for repo in sorted(recipients):
        t = directory / f"TRACKER-{repo}.md"
        if not t.is_file():
            bad.append(f"T1 no tracker for `{repo}` -- expected {t.name}")
            continue
        text = t.read_text()

        # T2 -- the four sections, so a reader knows an empty one is empty on purpose.
        for section in TRACKER_SECTIONS:
            if section not in text:
                bad.append(f"{t.name}: T2 missing section {section!r}")

        # T4 -- ids unique inside one tracker. Never renumbered is a rule we cannot check;
        # reused-right-now is one we can, and it is the way renumbering shows up.
        ids = ASK_ID_RE.findall(text)
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            bad.append(f"{t.name}: T4 ask id(s) used more than once: {', '.join(sorted(dupes))}")

    # T3 -- every packet cited in the tracker of every repo it is addressed to.
    for p in packets:
        for repo in p.to:
            t = directory / f"TRACKER-{repo}.md"
            if t.is_file() and p.stem not in t.read_text():
                bad.append(f"T3 {p.name} is addressed to `{repo}` and is in no row of {t.name}")
    return bad


def peer_report(packets: list[Packet]) -> list[str]:
    """R5 -- a report. Absent peers root is `unknown`, never a failure."""
    peers = ROOT.parent
    if not peers.is_dir():
        return ["peers root not present -- every recipient reads `unknown`"]
    out = []
    for p in packets:
        for repo in p.to:
            if not (peers / repo).is_dir():
                out.append(f"{p.name}: To: `{repo}` is not a sibling directory here")
    return out


def citation_census(packets: list[Packet]) -> tuple[list[str], list[str]]:
    """Citations that are not full stems. Counted, not failed."""
    ours = {p.stem for p in packets}
    ids = {}
    for p in packets:
        pid, letter = p.id
        ids.setdefault(pid + ("-" + letter if letter else ""), []).append(p.stem)

    bare, glob = [], []
    files = sorted(ROOT.glob("docs/**/*.md")) + sorted(ROOT.glob("*.md"))
    for f in files:
        try:
            text = f.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        rel = f.relative_to(ROOT)
        for m in BARE_CITE_RE.finditer(text):
            cid = m.group(1)
            where = "resolves here" if cid in ids else "NOT one of ours -- another repo's id"
            bare.append(f"{rel}: ROUTING-{cid}  ({where})")
        for m in GLOB_CITE_RE.finditer(text):
            frag = m.group(1)
            hits = [s for s in ours if s.startswith("ROUTING-" + frag)]
            glob.append(f"{rel}: ROUTING-{frag}*  ({len(hits)} match)")
    return bare, glob


def run(directory: pathlib.Path, legacy: set, strict: bool, quiet: bool = False) -> int:
    packets = collect(directory)
    if not packets:
        print(
            f"REFUSING: no ROUTING-*.md under {directory}. A clean verdict over an empty "
            "corpus is not a clean verdict.",
            file=sys.stderr,
        )
        return 2
    if not any(p.to for p in packets):
        print(
            f"REFUSING: parsed {len(packets)} packet(s) and extracted zero To: fields. "
            "The parse is the fragile part; that is a broken extractor, not a clean inbox.",
            file=sys.stderr,
        )
        return 2

    if not quiet:
        print(f"corpus: {len(packets)} packet(s) under {directory.relative_to(ROOT) if directory.is_relative_to(ROOT) else directory}")

    bad = check(packets, legacy) + check_trackers(packets, directory)

    if not quiet:
        for line in peer_report(packets):
            print(f"  note   {line}")
        bare, glob = citation_census(packets)
        print(f"\ncitation form: {len(bare)} bare-id, {len(glob)} glob-suffix (counted, not failed)")
        for b in bare:
            print(f"  bare   {b}")
        for g in glob:
            print(f"  glob   {g}")
        if strict:
            bad += [f"--strict-citations: {b}" for b in bare + glob]

    if bad:
        print()
        for b in bad:
            print(f"  FAIL   {b}")
        print(f"\nROUTING: {len(bad)} violation(s).")
        print(
            "A packet nobody can enumerate is a packet nobody receives. The reader is "
            "arch's `spec inbound`, and it files an unparseable recipient as UNKNOWN -- "
            "never as 'not mine'."
        )
        return 1

    if not quiet:
        print(f"\nROUTING: OK -- {len(packets)} packet(s), every addressee block parses.")
    return 0


PLANTS = {
    "ROUTING-2026-01-01-keystone-clean-packet.md": (
        "# ROUTING -> `entity-core-keystone` -- clean\n\n"
        "**To:** `entity-core-keystone`\n**From:** `entity-system-generator`\n**cc:** —\n\nbody\n"
    ),
    "ROUTING-2026-01-02-keystone-no-block-at-all.md": (
        "# ROUTING -> `entity-core-keystone` -- the recipient is only in the title\n\nbody\n"
    ),
    "ROUTING-2026-01-03-keystone-fields-on-one-line.md": (
        "# ROUTING -> `entity-core-keystone`\n\n"
        "**To:** `entity-core-keystone` · **From:** `entity-system-generator`\n**cc:** —\n\nbody\n"
    ),
    "ROUTING-2026-01-01-keystone-duplicate-id.md": (
        "# ROUTING -> `entity-core-keystone` -- same id as the clean one\n\n"
        "**To:** `entity-core-keystone`\n**From:** `entity-system-generator`\n**cc:** —\n\nbody\n"
    ),
    "ROUTING-2026-01-04-arch-token-disagrees-with-field.md": (
        "# ROUTING -> filed under arch, addressed to keystone\n\n"
        "**To:** `entity-core-keystone`\n**From:** `entity-system-generator`\n**cc:** —\n\nbody\n"
    ),
    # T1's actual subject: a well-formed packet to a repo with no tracker at all. Without
    # this the T1 assertion passed on fallout from the one-line plant leaking the SENDER
    # into `To:` -- a planted case that never exercised the branch it claimed (D15 cl. 2).
    "ROUTING-2026-01-05-arch-recipient-has-no-tracker.md": (
        "# ROUTING -> `entity-system-architecture` -- well-formed, untracked\n\n"
        "**To:** `entity-system-architecture`\n**From:** `entity-system-generator`\n**cc:** —\n\nbody\n"
    ),
    # R2's own plant. It cannot ride on the one-line packet: that one is missing `From:`, so
    # R1 `continue`s and R2 is never reached. An assertion about a branch the plant cannot
    # enter is the same false green as a corpus that cannot exercise it.
    "ROUTING-2026-01-06-keystone-addressed-to-its-own-sender.md": (
        "# ROUTING -> keystone, and to ourselves by mistake\n\n"
        "**To:** `entity-core-keystone`, `entity-system-generator`\n"
        "**From:** `entity-system-generator`\n**cc:** —\n\nbody\n"
    ),
}
# A LIST of pairs, not a dict keyed by filename: one plant legitimately trips two rules, and
# a dict silently kept the last one. The first draft of this line did exactly that.
EXPECT = [
    ("ROUTING-2026-01-02-keystone-no-block-at-all.md", "R1"),
    ("ROUTING-2026-01-03-keystone-fields-on-one-line.md", "R1"),
    ("ROUTING-2026-01-06-keystone-addressed-to-its-own-sender.md", "R2"),
    ("ROUTING-2026-01-01-keystone-duplicate-id.md", "R4"),
    ("ROUTING-2026-01-04-arch-token-disagrees-with-field.md", "R3"),
]

# A tracker missing exactly one section, carrying a reused id, and citing only one of the
# packets addressed to its repo -- so T2, T3 and T4 each have a planted case, and T1 is
# planted by the absence of a tracker for `entity-system-architecture` entirely.
TRACKER_PLANT = """# `entity-core-keystone` tracker

## Open — asks
| # | Ask | Packet | Kind |
| **A-1** | a thing | `ROUTING-2026-01-01-keystone-clean-packet.md` | ruling |
| **A-1** | a second thing wearing the same id | `x` | ruling |

## Corrections we owe them

## Closed
"""


def self_test() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="check-routing-selftest-"))
    try:
        for name, body in PLANTS.items():
            (tmp / name).write_text(body)
        packets = collect(tmp)
        if len(packets) != len(PLANTS):
            print(f"self-test FAILED: collected {len(packets)} of {len(PLANTS)}", file=sys.stderr)
            return 1
        # legacy is empty here on purpose: the duplicate must be CAUGHT, which also proves
        # the exemption set is what suppresses it in the real corpus rather than luck.
        bad = check(packets, legacy=set())
        print(f"self-test: {len(packets)} planted packet(s), {len(bad)} violation(s)")
        for b in bad:
            print(f"  caught  {b}")

        failures = []
        for name, rule in EXPECT:
            if not any(v.startswith(name + ":") and rule in v for v in bad):
                failures.append(f"planted {rule} in {name} was NOT caught")
        clean = "ROUTING-2026-01-01-keystone-clean-packet.md"
        if any(v.startswith(clean + ":") for v in bad):
            failures.append(f"the clean packet {clean} was flagged")

        # the tracker half, driven through the same check_trackers()
        (tmp / "TRACKER-entity-core-keystone.md").write_text(TRACKER_PLANT)
        tbad = check_trackers(packets, tmp)
        for line in tbad:
            print(f"  caught  {line}")
        # Each pair names the SUBJECT the message must mention, not just the rule tag --
        # `any("T1" in v)` passed on unrelated fallout once already.
        for rule, subject, why in (
            ("T1", "entity-system-architecture", "a recipient with no tracker at all"),
            ("T2", "Filed, nothing owed back to us", "the missing section"),
            ("T3", "ROUTING-2026-01-04-arch-token-disagrees-with-field", "a packet in no row"),
            ("T4", "A-1", "the reused ask id"),
        ):
            if not any(rule in v and subject in v for v in tbad):
                failures.append(f"planted {rule} ({why}, {subject!r}) was NOT caught")
        # and the clean direction: the one packet the tracker DOES cite must not be flagged
        if any("T3" in v and clean in v for v in tbad):
            failures.append(f"T3 flagged {clean}, which the planted tracker does cite")
        bad += tbad

        # the refusals, both of them, driven through run()
        empty = tmp / "empty"
        empty.mkdir()
        if run(empty, set(), False, quiet=True) != 2:
            failures.append("the empty-corpus refusal did not fire")
        novo = tmp / "novo"
        novo.mkdir()
        (novo / "ROUTING-2026-01-05-keystone-no-to-field.md").write_text(
            "# ROUTING\n\n**To:**\n**From:** `entity-system-generator`\n**cc:** —\n"
        )
        if run(novo, set(), False, quiet=True) != 2:
            failures.append("the zero-To: refusal did not fire")

        if failures:
            print()
            for f in failures:
                print(f"  self-test FAILED: {f}", file=sys.stderr)
            return 1
        print(
            f"\nself-test OK -- {len(EXPECT)} planted defects each caught, the clean packet "
            "not flagged, both refusals fired"
        )
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true", help="planted defects, one per FAIL rule")
    ap.add_argument(
        "--strict-citations",
        action="store_true",
        help="promote the citation-form census to failures",
    )
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    return run(STATUS, LEGACY_COLLISIONS, args.strict_citations)


if __name__ == "__main__":
    sys.exit(main())
