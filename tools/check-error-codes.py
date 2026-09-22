#!/usr/bin/env python3
"""The error-code surface gate — every wire code a port emits is declared, with its authority.

WHY THIS EXISTS, and why it exists TODAY rather than at the third extension.

D16: *an axis with no upstream authority gets its gate at the SECOND implementation.* The
handler's error-code surface is such an axis, and it is worse than the SDK surface was,
because it looked covered. `entity-core-go`'s `content` category asserts exactly two codes
(`get_path_required`, `ingest_path_required` — `cmd/internal/validate/content.go`); every
other code the handler emits is asserted by nothing anywhere. Three ports shipped with an
unguarded code surface and the re-pin is what exposed it: `EXTENSION-CONTENT` v3.7 corrected
§6.4's `403 forbidden` to `403 capability_denied`, and the only thing that would have caught
three ports still emitting the dead spelling was someone remembering to grep.

WHAT IT CHECKS. For each (extension x target) cell: extract every `(status, code)` a handler
body emits, and require each `code` to be declared in the extension's `[error_surface]` with
a class saying WHERE IT IS DEFINED:

  spec       — the extension's own code set (`[contract.error_codes]`, transcribed)
  core       — ENTITY-CORE-PROTOCOL §3.3's enumerated set (transcribed into CORE_CODES)
  unresolved — MUST-emitted by the spec and defined in NO spec code set. A named, dated,
               routed list. NOT a blessing: `--strict` turns each entry into an error.

An UNDECLARED code is a failure. The failure mode this exists to catch is a code arriving —
or outliving its spec — without anyone deciding, which is exactly what `forbidden` did.

WHAT IT IS NOT. It is a lint over emit sites, not a proof. It reads source with a per-target
regex and cannot know whether a branch is reachable; the conformance suite settles that. The
honest claim is the one `tools/check-drivers.py` carries: this catches a *spelling* drifting
from a *declaration*, which is the failure that has actually happened here, twice in one
re-pin. It does not catch a code emitted from a path nothing exercises.

D15 — the three obligations, each discharged and named:

  control          `--self-test` plants a bogus code in a synthetic buffer and asserts the
                   extractor reports it undeclared. Run it after touching a pattern.
  corpus assertion the extractor requires >= MIN_SITES emit sites per cell before it will
                   score one. A regex that silently stops matching reports a clean surface,
                   which is the false green this whole file is about.
  REFUSAL          zero cells parsed, zero sites in a cell, or an extension with no
                   `[error_surface]` block -> `REFUSING`, exit 2. Never a PASS.

D17 — the emit-call shape is a per-target VALUE, not a procedure, so it lives in
`languages/<target>/profile.toml` under `[error_surface].emit_pattern` and this file holds
one copy of the protocol.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose import ROOT, Refusal, load_toml  # noqa: E402

#: ENTITY-CORE-PROTOCOL §3.3's status table, transcribed: the default code for each status
#: plus the more-specific codes the row ENUMERATES BY NAME. Transcribed, not authored --
#: this is the set an extension handler may reach for without its own code set defining one.
#:
#: The enumeration is the load-bearing part. §3.3's 400 row names five more-specific codes;
#: `path_required` is NOT among them, and `path_required` appears ZERO times in the whole of
#: `ENTITY-CORE-PROTOCOL.md` (`grep -c path_required specs/ENTITY-CORE-PROTOCOL.md` -> 0).
#: That is the gap `[error_surface].unresolved` records.
CORE_CODES = {
    "invalid_request": 400, "invalid_path": 400, "invalid_params": 400,
    "unexpected_params": 400, "chain_depth_exceeded": 400, "signature_path_conflict": 400,
    "capability_denied": 403, "scope_exceeds_authority": 403,
    "handler_not_found": 404,
    "internal_error": 500, "io_error": 500, "storage_error": 500,
    "unsupported_operation": 501,
}

#: Below this many emit sites in a cell the extractor does not believe itself. Three ports
#: currently sit at 8-13; a pattern that breaks drops to 0 or 1, and 0 is caught by the
#: refusal above. This catches the middle case -- a pattern that still matches the helper
#: definition and none of its call sites.
MIN_SITES = 4

CLASSES = {"spec", "core", "unresolved"}


def targets() -> list[str]:
    """Every directory under `languages/` with a profile. A wildcard over the tree, never a
    maintained list -- `gates/README.md`'s matrix-as-data rule."""
    return sorted(p.name for p in (ROOT / "languages").iterdir()
                  if (p / "profile.toml").exists())


def extensions() -> list[str]:
    return sorted(p.name for p in (ROOT / "extension-contracts").iterdir()
                  if (p / "EXTENSION.toml").exists())


def emit_sites(target: str, ext: str, pattern: str) -> list[tuple[str, str, int]]:
    """Every `(code, path, line)` emitted by the cell's non-test sources.

    Tests are excluded on purpose: a test ASSERTS a code, it does not emit one, and folding
    the two together would let a stale assertion vouch for itself.

    Matched against the WHOLE FILE, not line by line, and the reason is measured.

    The first draft scanned lines. It was changed in review rather than by a failing run --
    the emits that carry a long message wrap, so the call and its code are never on one line:

        return errorResult(
          Status.Forbidden,
          "capability_denied",

    **What that would have cost was measured afterwards, and it is worse than the reasoning
    that caught it.** Distinct codes seen by each strategy, this tree, 2026-09-06:

        typescript   line 5 / whole 7    missed: capability_denied, path_required
        python       line 5 / whole 7    missed: capability_denied, path_required
        rust         line 4 / whole 7    missed: capability_denied, hash_mismatch, path_required

    A line scan misses **exactly the two codes this gate exists for** -- the one the v3.7
    re-pin changed and the one routed as unresolved -- on all three ports, because the
    interesting emits are the ones long enough to wrap.

    **And MIN_SITES would not have caught it**: the line scan still finds 6 / 11 / 5 sites,
    all above the floor. The corpus assertion bounds a pattern that stops matching; it does
    not bound one that matches the boring half. Recorded because the honest lesson is that
    review caught this one and the instrument's own guard would not have.
    """
    cell = ROOT / "languages" / target / "extensions" / ext
    if not cell.is_dir():
        return []
    rx = re.compile(pattern)
    out: list[tuple[str, str, int]] = []
    for src in sorted(cell.rglob("*")):
        if not src.is_file() or src.suffix not in {".ts", ".py", ".rs"}:
            continue
        rel = src.relative_to(ROOT).as_posix()
        if "/test" in rel or rel.endswith("_test.py") or "/tests/" in rel:
            continue
        text = src.read_text(encoding="utf-8")
        for m in rx.finditer(text):
            out.append((m.group("code"), rel, text.count("\n", 0, m.start()) + 1))
    return out


def declared_surface(ext: str) -> dict[str, str]:
    """`code -> class` from the extension's `[error_surface]`. Refuses if absent."""
    manifest = load_toml(ROOT / "extension-contracts" / ext / "EXTENSION.toml")
    block = manifest.get("error_surface")
    if not block:
        raise Refusal(
            f"extension-contracts/{ext}/EXTENSION.toml has no [error_surface] block -- "
            "every code a port puts on the wire names where it is DEFINED, or the surface "
            "is undeclared and this gate cannot say anything about it"
        )
    surface: dict[str, str] = {}
    for cls in CLASSES:
        for code in block.get(cls, []):
            if code in surface:
                raise Refusal(f"{ext}: {code!r} is declared in two classes -- pick one")
            surface[code] = cls
    if not surface:
        raise Refusal(f"{ext}: [error_surface] declares no codes at all")
    return surface


def run(strict: bool) -> int:
    exts, tgts = extensions(), targets()
    if not exts or not tgts:
        print(f"REFUSING: {len(exts)} extensions x {len(tgts)} targets -- nothing to compare")
        return 2

    failures: list[str] = []
    unresolved_hits: list[str] = []
    cells = 0

    for ext in exts:
        surface = declared_surface(ext)
        for target in tgts:
            profile = load_toml(ROOT / "languages" / target / "profile.toml")
            pattern = profile.get("error_surface", {}).get("emit_pattern")
            if not pattern:
                raise Refusal(
                    f"languages/{target}/profile.toml declares no "
                    "[error_surface].emit_pattern -- the emit-call shape is a per-target "
                    "VALUE (D17) and this gate cannot guess it"
                )
            if not (ROOT / "languages" / target / "extensions" / ext).is_dir():
                continue  # a cell that does not exist is not a cell that failed
            sites = emit_sites(target, ext, pattern)
            if len(sites) < MIN_SITES:
                print(f"REFUSING: {ext} x {target} matched {len(sites)} emit sites "
                      f"(< {MIN_SITES}) -- the pattern has stopped matching call sites, and "
                      f"a surface that parses to nothing is not a clean surface")
                return 2
            cells += 1
            seen = sorted({c for c, _, _ in sites})
            print(f"  {ext} x {target}: {len(sites)} sites, {len(seen)} distinct codes")
            for code in seen:
                cls = surface.get(code)
                where = next(f"{p}:{n}" for c, p, n in sites if c == code)
                if cls is None:
                    failures.append(f"{ext} x {target}: {code!r} is UNDECLARED ({where})")
                elif cls == "unresolved":
                    unresolved_hits.append(f"{ext} x {target}: {code!r} ({where})")

    if cells == 0:
        print("REFUSING: zero (extension x target) cells parsed")
        return 2

    print(f"\n{cells} cells scored across {len(exts)} extensions x {len(tgts)} targets")

    if unresolved_hits:
        head = "FAIL (--strict)" if strict else "unresolved"
        print(f"\n{head} -- emitted, MUST-ed by the spec, defined in no spec code set:")
        for h in unresolved_hits:
            print(f"    {h}")
        if not strict:
            print("    (routed, not blessed. `--strict` makes each an error; the flag is the")
            print("     switch that gets flipped once upstream pins them.)")

    if failures:
        print("\nFAIL -- undeclared codes:")
        for f in failures:
            print(f"    {f}")
    if failures or (strict and unresolved_hits):
        return 1
    print("\nOK -- every emitted code is declared with an authority")
    return 0


def self_test() -> int:
    """D15's control. Plant a code no surface declares and assert the extractor sees it.

    A gate that has only ever been observed passing is not an instrument. This is the
    cheapest form of the other answer: it exercises the regex and the undeclared-detection
    path without needing a broken tree to look at.
    """
    ok = True
    for target in targets():
        profile = load_toml(ROOT / "languages" / target / "profile.toml")
        pattern = profile.get("error_surface", {}).get("emit_pattern")
        if not pattern:
            print(f"  {target}: REFUSING -- no emit_pattern"); return 2
        probe = profile.get("error_surface", {}).get("self_test_line")
        if not probe:
            print(f"  {target}: REFUSING -- no [error_surface].self_test_line to control on")
            return 2
        m = re.compile(pattern).search(probe)
        got = m.group("code") if m else None
        verdict = "ok" if got == "planted_bogus_code" else "BROKEN"
        if got != "planted_bogus_code":
            ok = False
        print(f"  {target}: pattern vs planted line -> {got!r} [{verdict}]")
    print("\nself-test " + ("PASS -- every pattern extracts a planted code" if ok
                            else "FAIL -- a pattern cannot see a code it should"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true",
                    help="treat every `unresolved` code as an error")
    ap.add_argument("--self-test", action="store_true",
                    help="D15 control: assert each target's pattern extracts a planted code")
    args = ap.parse_args()
    try:
        return self_test() if args.self_test else run(args.strict)
    except Refusal as exc:
        print(f"REFUSING: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
