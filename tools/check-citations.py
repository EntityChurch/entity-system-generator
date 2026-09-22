#!/usr/bin/env python3
"""check-citations.py — a cited path resolves, or it is not a citation.

## Why this exists

**D13's enforcement point is a citation and nothing read it.**

> a capability claim in this repo, in any document or routing packet, either cites four
> sites `(entry, read, export, reach)` each as `(symbol, path, commit)`, **or** cites an
> executed probe (`gates/*/probe-*.mjs` or the §7d harness) with both controls.

D14's is a citation too — "a number cites the artifact that produced it". Both
disciplines make a PATH the unit of evidence, and until this file existed nothing
anywhere checked that the path was real. So a claim could carry a perfectly-formed
citation to a file that had never been written, and it would read as the strongest kind
of evidence this repo produces.

**It happened, and it is what this gate found on its first run.**
`extension-contracts/history/EXTENSION.toml`'s `[substrate.execution_context]` — the
block that records the single most consequential substrate fact this repo has measured,
that the peer delivers no execution context — carried

    probe = "languages/<t>/gates/emit-context/probe-*.{mjs,py,sh}"

and there has never been a `gates/emit-context`. The claim was true and was measured;
what it cited was a gate somebody intended to write. That is AP-2's mechanism (a fact
stated in a document that outlived the thing it named) applied to the citation itself,
which is one level worse: the citation is what a reader checks INSTEAD of re-deriving.

The second finding on the same run was `gates/host-seam/rust/`, a path from the
extension-major layout that the 2026-09-06 restructure moved to
`languages/rust/gates/host-seam/`. Nothing rewrote the prose, and nothing could have
noticed.

## D16, again, and this is the fourth instance

The four so far all have the same shape — *the thing we own is the thing nothing
watches*:

    the SDK surface        no upstream authority   gated at the 3rd port  (late)
    the tree structure     no upstream authority   gated at the 3rd target (late)
    the error-code surface partial oracle coverage gated at the re-pin     (camouflaged)
    a citation             OURS ENTIRELY           gated here              (late)

And this one is the sharpest, because a citation is not a by-product of the work — it IS
the discipline. D13 and D14 are both, in the end, rules about what a sentence must point
at.

## What it checks, and what it deliberately does not

It reads the DECLARATION files — `extension-contracts/**/*.toml`,
`languages/*/compositions/*/SYSTEM.toml`, and the authoring notes beside a contract —
extracts every repo-relative path they name, and requires each to resolve.

Four classes, and only the first is a failure:

| class | example | verdict |
|---|---|---|
| **source** | `tools/compose.py`, `languages/rust/gates/host-seam` | MUST exist |
| **artifact** | `languages/*/output/**` | exists only after a run; reported, never failed |
| **placeholder** | `languages/<t>/...`, `shared/spec-data/<snapshot>/` | expanded, then treated as source |
| **dead** | a path followed by `(dead)` on the same line | a QUOTATION of a path that is gone; counted, never failed |

## The `(dead)` class, and why it exists rather than a rewording

**The gate's first run failed on its own writeup.** Fixing incident 1 meant recording what
the stale citation had been — that is the whole content of the finding — and the moment
`languages/<t>/gates/emit-context/probe-*` appeared in the correction, the extractor read
it as a citation again. A gate that cannot say *"this path is gone and naming it is the
point"* forces every post-mortem to be written around it, and a discipline whose incidents
cannot be written down stops being a discipline.

So a path followed by `(dead)` is a quotation. **It is counted and printed, never silent**
— the same stance `[sdk_surface].drift` takes, and for the same reason: an escape hatch
that leaves no trace is a way to make a red gate green. What stops it being abused is that
it is one greppable token in a reviewed diff, not that the tool prevents it.

`output/**` is excluded from the requirement on purpose. Those paths are gitignored
build products, they are legitimate things to cite as evidence, and requiring them would
make this gate go RED on a clean checkout for a reason that has nothing to do with a
stale citation. **A false red costs the instrument** — the next person's locally
reasonable fix is to suppress it, and then it gates nothing forever (D15).

## `docs/**` IS covered now, and it took two incidents to earn the design

**It was excluded when this gate was written**, with a note saying prose names paths in
running sentences and in illustrative examples of paths that SHOULD NOT exist, so a
path-shaped token is not reliably a citation — *"the obvious next increment."* **That
exposure then cashed twice in two days, both times in a design document, and the second one
cost another team a week.**

| # | the citation | what it was |
|---|---|---|
| 1 | `shared/test-vectors/ecf-conformance/` in `DESIGN-THE-CBOR-INTERCHANGE-LAYER` | the corpus is in **keystone's** tree; in *ours* `shared/` is `shared/spec-data/`, so a path resolving to nothing read as though it resolved. Two counts beside it were wrong too |
| 2 | `docs/spec/SPEC-KEYSTONE-PEER.md` in `DRAFT-KEYSTONE-PEER-HOST-CONTRACT` | a **forward-dated citation** — the header declared itself superseded, pointed at a path that did not exist yet, and told readers not to maintain the file. Nobody did, on either side |

Two incidents in two shapes, and #2 is the sharp one: a citation is what a reader checks
*instead of* re-deriving, so a citation to something that does not exist **yet** is worse
than none — it transfers confidence nothing earned.

**What made it possible is a three-way split, not a cleverer regex.** The original blocker
was real; what was missing was that the ambiguous cases fall into classes with different
truth conditions:

| class | test | verdict |
|---|---|---|
| **cross-repo** | resolves inside a sibling tree under `../` | **reported, never failed.** A real citation to a tree we may not edit; it moves on their cycle, not ours |
| **historical snapshot** | lives under `docs/status/` | **exempt, counted.** A dated handoff describes the tree *as it was*; requiring its paths to resolve forever means rewriting history |
| **durable prose** | everything else in `docs/` | **MUST resolve**, exactly like a declaration file |

`docs/status/` is the exemption that makes the rest safe, and it is principled rather than
convenient: those files are immutable once written and their value is that they say what was
true on a date. Sixteen of them name paths the 2026-09-06 restructure moved and **not one is
a defect** — rewriting them would destroy the record and break *never lose or rewrite
history*.

The escape hatch in durable prose is the one that already existed: a path followed by
`(dead)` is a quotation — counted, printed, never silent.

## D15: a control, and a refusal on vacuity

`--self-test` plants a citation to a path that cannot exist and requires the extractor to
find it and the checker to fail on it. An instrument observed only passing is not an
instrument.

And the refusal is the one that matters here, because the fragile part is the REGEX: if
the extraction pattern stops matching — a contract reformats, a key is renamed — the run
reports a clean tree over zero citations, which is the most comfortable wrong answer
available. Zero citations, or fewer than `MIN_CITATIONS`, REFUSES and exits non-zero.

    ./tools/check-citations.py
    ./tools/check-citations.py --self-test
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The declaration corpus, plus `docs/**` — see the module doc for the three-way split.
CORPUS = [
    "extension-contracts/*/EXTENSION.toml",
    "extension-contracts/*/README.md",
    "extension-contracts/*/arch/*.md",
    "languages/*/compositions/*/SYSTEM.toml",
    "languages/*/profile.toml",
    "docs/**/*.md",
]

#: Dated snapshots. Immutable once written, and their value is that they say what was true
#: on a date — so a path the tree has since moved is a RECORD, not a defect. Counted and
#: reported, never failed. Rewriting them to keep a gate green would be the thing the
#: golden rules forbid outright.
SNAPSHOT_DIRS = ("docs/status",)

#: Where a sibling repo lives, for the cross-repo class. Read-only to us by charter, so a
#: citation into one is reported and never failed: it resolves on their cycle.
CHURCH = ROOT.parent

#: The top-level directories a repo-relative citation can start with. Anchoring on these
#: is what keeps `system/history/config` (a TREE path, not a file) out of the corpus:
#: entity-core paths and filesystem paths look alike and only the first segment tells
#: them apart.
ROOTS = ("languages", "gates", "tools", "extension-contracts", "shared", "docs")

#: The lookbehind is load-bearing and was added 2026-09-09 when `docs/**` joined the corpus.
#: `\b` alone matches a ROOT sitting in the MIDDLE of a longer path: in
#: `protocol-generator/shared/evaluations/x.md` — keystone's real, correct path — `\b`
#: matches between `/` and `shared`, so the extractor pulled out `shared/evaluations/x.md`,
#: found it unresolvable here, and reported a correct citation as a defect. A false red on a
#: path that IS right is the worst kind: the obvious fix is to delete the citation.
CITATION = re.compile(
    r"(?<![\w/.-])(?:" + "|".join(ROOTS) + r")/[A-Za-z0-9_.<>{},*/-]*[A-Za-z0-9_>}*/]"
)

#: A corpus assertion (D15 clause 2) rather than a count of files: below this, the
#: extractor has stopped matching something it used to match.
#:
#: RECALIBRATED 2026-09-09 from 30 to 300 when `docs/**` joined the corpus. The old value
#: was set against a measured 40; the corpus is now 415, and a floor of 30 would have let
#: the extractor lose NINETY-THREE PERCENT of its matches and still report a clean tree.
#: A vacuity refusal that cannot fire is not a refusal — it is a comment. The margin is
#: the same fraction it was before (~75% of measured), so it tolerates a real deletion of
#: documents without tolerating a broken regex.
#:
#: Re-derive after any corpus change:
#:   ./tools/check-citations.py | head -1
MIN_CITATIONS = 300

#: Placeholder segments and what they stand for. `<t>`/`<target>`/`<lang>` expand over the
#: targets that actually exist, so a citation to a per-target file is checked in EVERY
#: target rather than in one -- which is the point of writing it with a placeholder.
TARGET_PLACEHOLDERS = ("<t>", "<target>", "<lang>", "<language>")


class Refusal(Exception):
    """The gate could not run. Never reported as a verdict about the citations."""


def targets() -> list[str]:
    return sorted(p.name for p in (ROOT / "languages").iterdir() if p.is_dir())


def expand_braces(text: str) -> list[str]:
    """`a/{b,c}/d` -> `a/b/d`, `a/c/d`. One level is all any citation here uses."""
    m = re.search(r"\{([^{}]*)\}", text)
    if m is None:
        return [text]
    out = []
    for alt in m.group(1).split(","):
        out.extend(expand_braces(text[: m.start()] + alt + text[m.end() :]))
    return out


def expand_placeholders(text: str) -> list[str]:
    """`<t>` over the real targets; any other `<...>` becomes a glob."""
    for ph in TARGET_PLACEHOLDERS:
        if ph in text:
            return [
                expanded
                for t in targets()
                for expanded in expand_placeholders(text.replace(ph, t, 1))
            ]
    return [re.sub(r"<[^<>]*>", "*", text)]


def resolves(candidate: str) -> bool:
    """Does this repo-relative path (possibly a glob) match anything?"""
    if not any(ch in candidate for ch in "*?["):
        return (ROOT / candidate).exists()
    # `Path.glob` refuses an absolute pattern and dislikes a trailing slash.
    pattern = candidate.rstrip("/")
    try:
        return next(ROOT.glob(pattern), None) is not None
    except (ValueError, IndexError):
        return False


def is_artifact(candidate: str) -> bool:
    """Build output: gitignored, exists only after a run. Reported, never failed."""
    return "/output/" in f"/{candidate}" or candidate.startswith("output/")


def is_snapshot(rel: str) -> bool:
    """A dated, immutable status doc. Its paths are a record of a past tree."""
    return any(rel.startswith(f"{d}/") for d in SNAPSHOT_DIRS)


def cross_repo(candidate: str) -> str | None:
    """The sibling tree this path resolves in, if any.

    A citation into another team's tree is a REAL citation and we cannot fix it here —
    their layout moves on their cycle and their tree is read-only to us. Reported so it is
    never silent, never failed so this gate does not go red on someone else's commit.

    Checked BEFORE the local verdict, because the two collide: `docs/spec/SPEC-KEYSTONE-
    PEER.md` is keystone's real path and would read as a broken local one.
    """
    if not CHURCH.is_dir():
        return None
    for sibling in sorted(CHURCH.iterdir()):
        if sibling.is_dir() and sibling.name != ROOT.name and (sibling / candidate).exists():
            return sibling.name
    return None


def corpus_files() -> list[Path]:
    files: list[Path] = []
    for pattern in CORPUS:
        files.extend(sorted(ROOT.glob(pattern)))
    return files


#: How far after a path the `(dead)` marker may sit. Wide enough for a closing backtick,
#: a quote and a space; narrow enough that the marker cannot be read as belonging to a
#: DIFFERENT path later on the line.
DEAD_WINDOW = 12


def extract(path: Path) -> tuple[set[str], set[str]]:
    """`(live, dead)` — the paths this file cites, and the ones it quotes as gone."""
    text = path.read_text(encoding="utf-8")
    live: set[str] = set()
    dead: set[str] = set()
    for m in CITATION.finditer(text):
        # A citation at the end of a sentence keeps the period; a citation inside a
        # backtick pair does not. Strip what punctuation can trail and nothing else --
        # over-stripping would turn a real miss into a pass.
        cited = m.group(0).rstrip(".,;:)")
        # TRUNCATE at the newline rather than rejecting a window that contains one.
        # Rejecting was a real defect, found 2026-09-09 when `docs/**` joined the corpus:
        # a marker at END OF LINE sits inside the window together with the `\n`, so
        # ``…`gates/emit-context` (dead).**\n`` was read as LIVE and reported as a defect.
        # The rule is "on the same line"; that is what truncating expresses and what the
        # rejection got wrong for every marker within DEAD_WINDOW of a line end.
        tail = text[m.end() : m.end() + DEAD_WINDOW].split("\n", 1)[0]
        if "(dead)" in tail:
            dead.add(cited)
        else:
            live.add(cited)
    # A path quoted as dead in one place and cited live in another is LIVE: the marker
    # exempts an occurrence, never a path.
    return live, dead - live


def run(
    extra_files: list[Path] | None = None,
) -> tuple[list[str], list[str], list[str], int, list[str], list[str]]:
    """Returns `(missing, artifacts, dead, total, snapshots, foreign)`."""
    files = corpus_files() + list(extra_files or [])
    if not files:
        raise Refusal(
            "REFUSING: the corpus globs matched no files at all. That is a defect in "
            "this instrument or in the tree layout, never a clean run."
        )

    missing: list[str] = []
    artifacts: list[str] = []
    dead_out: list[str] = []
    snapshots: list[str] = []
    foreign: list[str] = []
    total = 0
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        live, dead = extract(f)
        for quoted in sorted(dead):
            total += 1
            dead_out.append(f"{rel}: {quoted}")
        for cited in sorted(live):
            total += 1
            if is_artifact(cited):
                artifacts.append(f"{rel}: {cited}")
                continue
            candidates = [
                c for base in expand_placeholders(cited) for c in expand_braces(base)
            ]
            # A brace/placeholder citation resolves if EVERY expansion does. `{build,
            # test,host-entry}` names three files and a citation to three files that
            # names two is as stale as one that names none.
            unresolved = [c for c in candidates if not resolves(c)]
            if not unresolved:
                continue
            # ── the three-way split, and the ORDER matters ──────────────────────
            # Cross-repo FIRST: `docs/spec/SPEC-KEYSTONE-PEER.md` is keystone's real
            # path and would otherwise read as a broken local one. Their tree is
            # read-only to us and moves on their cycle, so this is reported, never
            # failed -- a gate that goes red on someone else's commit gets suppressed.
            if (sibling := cross_repo(cited)) is not None:
                foreign.append(f"{rel}: {cited}   ->   {sibling}")
                continue
            # Then the snapshot exemption: a dated handoff records a past tree.
            if is_snapshot(rel):
                snapshots.append(f"{rel}: {cited}")
                continue
            missing.append(f"{rel}: {cited}   ->   unresolved: {', '.join(unresolved)}")
    return missing, artifacts, dead_out, total, snapshots, foreign


def self_test() -> int:
    """D15's control: plant one defect per class and require the right verdict on each.

    Extended 2026-09-09 with the `docs/**` classes. The two that matter are the ones that
    must NOT fail — a class wrongly routed to `missing` is a false red, and a false red
    costs the instrument. So this asserts the classification, not just the failure.
    """
    planted = ROOT / "extension-contracts" / ".citation-self-test.md"
    planted.write_text(
        "A planted citation: `tools/this-file-does-not-exist.py`\n"
        "and a planted per-target one: `languages/<t>/gates/nope/run`\n"
        # must be classified DEAD, and the marker sits at END OF LINE on purpose --
        # that exact placement was broken until 2026-09-09.
        "a planted quotation: `tools/also-gone.py` (dead)\n"
        # must be classified CROSS-REPO: a real path in a sibling tree, never our failure.
        "a planted cross-repo one: `docs/spec/SPEC-KEYSTONE-PEER.md`\n",
        encoding="utf-8",
    )
    snap = ROOT / "docs" / "status" / ".citation-self-test-snapshot.md"
    # must be classified SNAPSHOT: the same unresolvable path, exempt by location alone.
    snap.write_text("a planted snapshot path: `tools/this-file-does-not-exist.py`\n",
                    encoding="utf-8")
    try:
        missing, _artifacts, dead, total, snapshots, foreign = run(
            extra_files=[planted, snap]
        )
    finally:
        planted.unlink()
        snap.unlink()

    tag = ".citation-self-test"
    checks = {
        "an unresolvable citation FAILS": len(
            [m for m in missing if f"{tag}.md" in m]
        ) == 2,
        "a `(dead)` quotation at END OF LINE is exempt, not failed": any(
            f"{tag}.md" in d and "also-gone" in d for d in dead
        ),
        "a path in a SIBLING tree is cross-repo, never our failure": any(
            f"{tag}.md" in x for x in foreign
        ),
        "the same bad path under docs/status/ is an exempt SNAPSHOT": any(
            f"{tag}-snapshot.md" in s for s in snapshots
        ),
        "...and that snapshot is NOT reported as missing": not any(
            f"{tag}-snapshot.md" in m for m in missing
        ),
    }
    print(f"self-test: {total} citations extracted")
    for label, ok in checks.items():
        print(f"  {'PASS' if ok else 'MISS'}  {label}")
    if not all(checks.values()):
        print(
            "SELF-TEST FAILED: this instrument cannot be trusted -- it either misses a "
            "real defect or manufactures a false red on an exempt class.",
            file=sys.stderr,
        )
        return 1
    print("\nself-test OK -- one planted case per class, each classified correctly")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="plant an unresolvable citation and require this gate to catch it (D15)",
    )
    ap.add_argument(
        "--strict-artifacts",
        action="store_true",
        help="also require cited build artifacts to exist (only meaningful after a full run)",
    )
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    try:
        missing, artifacts, dead, total, snapshots, foreign = run()
    except Refusal as exc:
        print(exc, file=sys.stderr)
        return 2

    if total < MIN_CITATIONS:
        print(
            f"REFUSING: extracted {total} citations, below the floor of {MIN_CITATIONS}. "
            "The extraction pattern has stopped matching something it used to match, and "
            "a clean verdict over an empty corpus is not a clean verdict.",
            file=sys.stderr,
        )
        return 2

    files = corpus_files()
    n_docs = sum(1 for f in files if f.relative_to(ROOT).as_posix().startswith("docs/"))
    print(
        f"citations: {total} in {len(files)} files "
        f"({len(files) - n_docs} declaration, {n_docs} docs)"
    )
    checked = total - len(artifacts) - len(dead) - len(snapshots) - len(foreign)
    print(f"  source citations checked : {checked}")
    print(f"  build artifacts (not required to exist): {len(artifacts)}")
    print(f"  quoted as (dead) -- a path named because it is GONE: {len(dead)}")
    # Printed, never silent. An escape hatch that leaves no trace is a way to make a red
    # gate green; the same stance `[sdk_surface].drift` takes.
    for d in dead:
        print(f"    dead  {d}")
    # Reported, never failed -- and never SILENT, which is the same rule as `(dead)`.
    # A count with no listing is how `absent` comes to mean `could not look` (D14).
    print(f"  cross-repo -- resolves in a sibling tree, theirs to move: {len(foreign)}")
    for x in foreign:
        print(f"    xrepo {x}")
    print(
        f"  historical snapshots under {'/'.join(SNAPSHOT_DIRS)}/ -- a record of a past "
        f"tree, never rewritten: {len(snapshots)}"
    )
    for s in snapshots:
        print(f"    snap  {s}")
    if args.strict_artifacts:
        for a in artifacts:
            path = a.split(": ", 1)[1]
            if not resolves(path):
                missing.append(f"{a}   ->   artifact absent (--strict-artifacts)")

    if missing:
        print()
        for m in missing:
            print(f"  MISSING  {m}")
        print(f"\nCITATIONS: {len(missing)} unresolved.")
        print(
            "A cited path that does not exist is worse than no citation: it is what a "
            "reader checks INSTEAD of re-deriving the claim."
        )
        return 1

    print("\nCITATIONS: OK -- every cited source path resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
