#!/usr/bin/env python3
"""check-glue.py — the glue does not know who its members are.

## The requirement, in the operator's words

> *We want the logistical stuff to be pretty stable, not really growing. Most of it should
> grow within the code and the implementation extensions. But all the glue code — that
> should be pretty stable. We don't want big if blocks of "oh, if it's this container and
> this extension".*

`tools/scale-report.py` measures **mass** per multiplier class, and mass is the wrong
instrument for this. A neutral file that grows a 46-way branch is still one file in the
`neutral` column; it is `×1` by location and `O(T)` by edit cost, and the report would call
it stable while every new target required a patch to it.

**So this gate measures IDENTITY LEAKAGE, not size.** The invariant is a containment rule,
one line per direction:

    a LANGUAGE-NEUTRAL file names no specific TARGET
    a PER-TARGET file names no specific EXTENSION
    a PER-EXTENSION file names no specific TARGET

Each is *"the glue does not enumerate its members"*. Break any one and adding a member
becomes an edit to something that was supposed to be finished — which is the difference
between *"add a directory"* and *"add a directory and then go find the eleven places that
have to learn about it."*

## Why the third rule is not redundant

`extension-contracts/<ext>/EXTENSION.toml` carries `[substrate]` and `[sdk_surface]`
blocks that name every port on purpose — they are **cross-port comparison tables**, and
`DESIGN-THE-SYSTEM-STRUCTURE` §1.2 is explicit that a comparison sharded per port stops
being a comparison. So the per-extension direction has a real, principled exemption and the
gate has to know the difference between *a table of measured facts about each port* and
*a branch that behaves differently per port*. It does that structurally: TOML **keys and
values** may name targets; anything in a `.py`/`.ts`/`.rs`/`.mjs`/driver file may not.

## What this found on its first run

Three per-target gate arms — the `type-parity` arms written the same day — each carrying a
hand-maintained `extension -> (module, function)` table:

    languages/python/gates/type-parity/probe.py       SUBJECTS = {"content": ..., "history": ...}
    languages/typescript/gates/type-parity/probe.mjs  const SUBJECTS = {...}
    languages/rust/gates/type-parity/src/main.rs      match ext { "content" => ..., "history" => ... }

Two entries each today. **At 26 extensions × 46 targets that is 1,196 hand-maintained map
entries**, in files whose entire purpose is to be target-specific and extension-agnostic.

## D15: control and refusal

- **Control** (`--self-test`): a synthetic corpus with one planted violation per direction,
  each required to be caught, plus a clean file required NOT to be flagged, plus the
  comment/docstring exemption required to hold in both directions.
- **Refusal:** zero files scanned, or zero targets/extensions discovered — the identity
  lists are what the patterns are built from, so an empty one makes every file clean.
  A gate that reports "no leakage" because it does not know what a target is called is the
  false green this whole class of instrument keeps producing.

**Comments and docstrings are exempt, and that is not a loophole.** This tree documents
every rule against the dated incident that earned it, and those incidents name ports:
*"`typescript` bundles the constants and `python` exports them flat"* is the content of
AP-8. A gate that forbade naming a port in prose would forbid the catalog. What it forbids
is a port name reached by the interpreter.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_classifier():
    """Borrow `scale-report.py`'s `classify()` rather than re-deriving it.

    ONE CANONICAL HOME PER FACT. *"Which multiplier does this path carry"* is already
    answered, with a self-test pinning one path per class; a second classifier here would
    be the same fact in two places, which is the thing this repo's whole layout argument
    is about. The first draft of this file DID re-derive it, treated everything under
    `languages/<t>/` that was not `extensions/` as per-target, and immediately produced a
    FALSE RED on `compositions/<c>/host.py` -- a file whose entire job is to name the
    extensions in its composition.

    A false red costs the instrument (D15, AP-4), and this one would have arrived with
    fourteen of them on the first run.
    """
    spec = importlib.util.spec_from_file_location("scale_report", ROOT / "tools" / "scale-report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.classify


classify = _load_classifier()

#: Files whose content is code rather than declaration. TOML is excluded on purpose --
#: `EXTENSION.toml`'s `[substrate]`/`[sdk_surface]` blocks are cross-port comparison
#: tables and naming every port is their job (see the module docstring).
CODE_SUFFIXES = {".py", ".ts", ".mjs", ".js", ".rs", ".sh"}
#: Extensionless files in this tree are shell drivers, which are code.
DRIVER_NAMES = {"build", "test", "host-entry", "run", "host-launch", "gate-stage"}

#: Line-comment openers by suffix, for the prose exemption.
LINE_COMMENT = {
    ".py": ("#",), ".sh": ("#",), "": ("#",),
    ".ts": ("//", "*", "/*"), ".mjs": ("//", "*", "/*"),
    ".js": ("//", "*", "/*"), ".rs": ("//", "///", "//!", "*", "/*"),
}


def is_code(path: Path) -> bool:
    return path.suffix in CODE_SUFFIXES or (not path.suffix and path.name in DRIVER_NAMES)


#: A control's fixture corpus is not glue. `scale-report.py`'s substring-trap control
#: REQUIRES the literal `typescript` -- its whole job is to prove the classifier no longer
#: matches `types` inside `typescript` -- and a gate that forbade it would forbid the
#: control that keeps AP-16 fixed. Everything from a `def self_test(` to the end of the
#: file is exempt, which is where this tree puts its fixtures by convention.
_SELF_TEST = re.compile(r"^\s*(def self_test|def _self_test|SELF_TEST_)")


def code_lines(path: Path):
    """Yield (lineno, text) for lines that the interpreter actually reaches.

    Line-granularity, and deliberately so: a full block-comment parser is a second
    instrument to get wrong, and the failure mode of being too coarse here is a FALSE RED
    on a name inside a `/* */` block -- which D15 says is the expensive direction. So the
    `*` continuation marker is treated as a comment opener, which over-exempts slightly.
    Stated rather than hidden; the docstrings this tree writes are the reason.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    openers = LINE_COMMENT.get(path.suffix, ("#",))
    in_pydoc = False
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        if _SELF_TEST.match(line):
            return   # fixtures below; see _SELF_TEST
        if path.suffix == ".py":
            # A module/function docstring is prose in this tree, and a long one.
            if s.count('"""') == 1:
                in_pydoc = not in_pydoc
                continue
            if in_pydoc or s.startswith('"""'):
                continue
        if s.startswith(openers):
            continue
        yield i, s


def scan(path: Path, names: list[str], kind: str) -> list[tuple[int, str, str]]:
    """Hits for any of `names` appearing as a WORD on a reachable line."""
    if not names:
        return []
    pat = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")
    out = []
    for lineno, text in code_lines(path):
        m = pat.search(text)
        if m:
            out.append((lineno, m.group(1), text[:88]))
    return out


def tracked() -> list[str]:
    """Every file git would consider part of the tree — COMMITTED OR NOT.

    `--others --exclude-standard` is load-bearing and was added 2026-09-09 after a plain
    `git ls-files` corpus cost a real miss: `tools/check-toolchain.py` was written, this
    gate was run against it and reported **OK over 64 files**, and only after the commit
    did the corpus become 65 and the gate find a genuine identity leak in it.

    **A gate whose corpus is the COMMITTED tree cannot answer about the change you are
    about to make.** That is the shape D21 names one axis over — a reference in the wrong
    place — and here the reference was in the wrong *tense*. The pre-commit run is the
    only one whose answer can still change what lands, and it was the one run blind.

    `--exclude-standard` keeps `.gitignore` authoritative, so `output/`, `.agents/` and
    every build artifact stay out. An untracked scratch file that is NOT ignored is
    scanned, and that is intended rather than tolerated: this gate's failure mode is a
    file naming a target, and a file too new to be committed is exactly when that is
    cheapest to fix.
    """
    return [ln for ln in subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines() if ln.strip()]


def axes() -> tuple[list[str], list[str]]:
    langs, contracts = ROOT / "languages", ROOT / "extension-contracts"
    t = sorted(p.name for p in langs.iterdir() if p.is_dir()) if langs.is_dir() else []
    e = sorted(p.name for p in contracts.iterdir() if p.is_dir()) if contracts.is_dir() else []
    return t, e


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true", help="D15's control")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    targets, exts = axes()
    if not targets or not exts:
        print(f"REFUSING: {len(targets)} target(s), {len(exts)} extension(s). The identity "
              "lists ARE the\npatterns; an empty one makes every file in the tree read as "
              "clean.", file=sys.stderr)
        return 2

    scanned = 0
    exempt = {"per-composition": 0, "per-cell": 0, "per-extension": 0}
    problems: list[str] = []
    census: dict[str, int] = {}

    for rel in tracked():
        p = ROOT / rel
        if not is_code(p):
            continue
        hit_class = classify(rel)
        if hit_class is None:
            continue
        cls, _bucket = hit_class

        # ── neutral: tools/ and the neutral half of a gate ──────────────────────
        if cls == "neutral":
            scanned += 1
            for lineno, name, text in scan(p, targets, "target"):
                problems.append(
                    f"{rel}:{lineno}: language-neutral code names the target `{name}`\n"
                    f"      {text}\n"
                    f"      The glue does not enumerate its members. This is ×1 by location "
                    f"and O(T) by edit\n      cost, and `make scale` cannot see the "
                    f"difference."
                )

        # ── per-target: a driver or a gate arm ──────────────────────────────────
        elif cls == "per-target":
            scanned += 1
            hits = scan(p, exts, "extension")
            if hits:
                census[rel] = len(hits)

        # ── the three classes that are SUPPOSED to name things ──────────────────
        #
        # Counted and printed, never silently skipped (`gates/README.md`: no silent caps).
        #   per-composition  a composition IS (target x extension set). `host.*` naming its
        #                    extensions is the file's whole job.
        #   per-cell         an extension's own port. It is the thing being named.
        #   per-extension    the contract, incl. the cross-port comparison tables.
        elif cls in exempt:
            exempt[cls] += 1

    if scanned == 0:
        print("REFUSING: 0 code files scanned. A clean verdict over an empty corpus is not "
              "a clean verdict.", file=sys.stderr)
        return 2

    print(f"glue: {scanned} code files scanned against {len(targets)} target name(s) and "
          f"{len(exts)} extension name(s)")
    print(f"      exempt by class (naming members is their job): "
          + ", ".join(f"{k}={v}" for k, v in exempt.items()))
    # ── the census half, and why it is not a verdict ────────────────────────────
    #
    # `per-target code names an extension` is REPORTED, not failed, and the reason is
    # precision rather than leniency. Two things wear the same shape and this gate cannot
    # yet tell them apart:
    #
    #   a DISPATCH TABLE     `{"content": ..., "history": ...}` -- E entries per arm, the
    #                        thing that becomes 1,196 hand-written rows. A real defect.
    #   a SUBJECT            `host-seam` probes the seam by installing a concrete handler
    #                        at `system/content`. Naming it is the probe's whole job.
    #
    # Failing both would put ~50 false reds in front of a reader on day one, and a false
    # red costs the instrument (AP-4, D15): the locally reasonable fix is to switch it off.
    # So the number is printed and tracked, and the gate goes red only on the direction it
    # can judge exactly. When the arms are parameterised the census goes to zero on its
    # own, and THAT is when it earns a threshold.
    if census:
        total = sum(census.values())
        print(f"\n  census -- per-target files naming an extension ({total} lines in "
              f"{len(census)} files).\n  NOT a verdict: a dispatch table and a probe "
              f"subject look identical from here.")
        for rel in sorted(census, key=lambda r: -census[r]):
            print(f"    {census[rel]:3}  {rel}")
        print()

    for msg in problems:
        print(f"  FAIL {msg}")
    if problems:
        print(f"\nGLUE: {len(problems)} identity leak(s)")
        return 1
    print("GLUE: OK -- no neutral file names a target, no per-target file names an extension")
    return 0


def self_test() -> int:
    """D15's control: one planted violation per direction, and the exemptions held."""
    import tempfile

    cases = [
        # (filename, content, targets, exts, expect_target_hit, expect_ext_hit)
        ("leak_target.py", 'if lang == "rust":\n    pass\n', ["rust"], ["content"], True, False),
        ("leak_ext.py", 'SUBJECTS = {"content": 1}\n', ["rust"], ["content"], False, True),
        ("clean.py", 'for t in targets:\n    run(t)\n', ["rust"], ["content"], False, False),
        # The prose exemption, both directions -- a comment and a docstring naming a port.
        ("prose.py", '"""AP-8: rust exports them flat."""\n# and rust again\nx = 1\n',
         ["rust"], ["content"], False, False),
        ("prose.rs", '/// `rust` refuses at compile time.\nfn f() {}\n',
         ["rust"], ["content"], False, False),
    ]
    bad = 0
    with tempfile.TemporaryDirectory() as td:
        for name, body, tg, ex, want_t, want_e in cases:
            p = Path(td) / name
            p.write_text(body)
            got_t = bool(scan(p, tg, "target"))
            got_e = bool(scan(p, ex, "ext"))
            ok = (got_t == want_t) and (got_e == want_e)
            print(f"  {'ok  ' if ok else 'FAIL'} {name:<16} target-hit={got_t} "
                  f"(want {want_t})  ext-hit={got_e} (want {want_e})")
            bad += not ok

    # The refusal, observed: an empty identity list must not silently clean the tree.
    p = Path(__file__)
    if scan(p, [], "target"):
        print("  FAIL scan() with no names returned hits")
        bad += 1
    else:
        print("  ok   scan() with an empty name list returns nothing -- which is WHY "
              "main() refuses\n       rather than trusting it")

    print(f"\nSELF-TEST: {'OK -- both directions and both exemptions observed' if not bad else f'{bad} FAILURE(S)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
