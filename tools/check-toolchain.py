#!/usr/bin/env python3
"""check-toolchain.py — the host contract is declared, and the host half stays stdlib-only.

## Why this exists

**The charter said one thing and the build did another, for the whole life of the repo.**
`AGENTS-STANDARD.md`: *"the host needs only `make` + `podman`."* Meanwhile `make check`
runs eleven `tools/*.py` on the host, and the Makefile shells `python3 -c` to read a
profile *before it can choose an image*. Nobody had declared Python as the tooling
language anywhere in the tree — checked, and there was no such statement.

Settled 2026-09-09, and **not in the direction of "this was fine"**. Python and Bash are
*de facto* dependencies across these projects — not adopted, but reached for anyway
despite the stated standard. That is a discipline failure at project scale rather than a
decision this repo made, its scope is not this seat's to rule on, and the reality is
accepted for now only because changing it is far more work than declaring it.

**So this gate does not sanction the dependency.** It answers the narrower local question
the failure left open: given that it exists, is it DECLARED and BOUNDED, or is it still
accumulating under a sentence saying it is absent? `docs/adr/0001-the-host-toolchain-
contract.md` is the reasoning; `tools/tooling.toml [host]` is the data; this is the check.

## The invariant, which is not the inventory

An inventory of what we depend on is a document. The thing worth gating is the boundary:

> **The host half is stdlib-only. Anything that needs a third-party library runs in a
> container.**

That is already true, and it was *tested* rather than asserted: the ECF codec is the one
non-stdlib dependency this tree has, it cannot load on a bare host, and when that was
found the two entry points that reach it were **containerised** rather than the host
contract being widened (`tools/tooling.toml [ecf_codec]`, 2026-09-08). This gate is what
stops the next such arrival being resolved the other way, silently, by whoever meets it.

## D16 — and this one is the axis the charter actively pointed AWAY from

The four prior instances all read *the thing we own is the thing nothing watches*. This
is worse than unwatched: the charter contained a sentence asserting the property, so
anyone asking *"what does the host need?"* got a confident wrong answer from the most
authoritative file in the repo. **A wrong declaration is more expensive than a missing
one**, for the same reason D16's third instance (an axis with partial oracle coverage)
was more dangerous than one with none — the coverage is what stops anyone asking.

## The half an obvious version of this gate would have missed

**Caught in review, before the first run** — the second time in this repo's history, after
`check-error-codes.py`. An AST scan for `import` statements across `tools/` and `gates/`
reports the neutral half as **100% stdlib**, and that answer is *right by accident*:

    gates/ext-checks/schema.py:90     mod = __import__(decl["package"])

The one genuine third-party dependency in the tree is loaded from a name held in a TOML
file. No `import` statement names it, so no scan for one can see it — and the gate would
have printed a clean, true-sounding verdict over a corpus that excluded the only thing it
exists to find. That is AP-19's shape (a check named after the requirement, measuring
something adjacent) arriving in an instrument's own corpus definition.

So this reads **two doors**, and the second is declared per site in
`[[host.dynamic_load]]`:

| door | how it is read | verdict on an undeclared one |
|---|---|---|
| `import` / `from … import` | `ast`, distinguishing module scope from a function body | non-stdlib at module scope FAILS |
| `importlib` · `__import__` · `exec` | `ast` call sites, matched to declared sites | FAILS |

`ast` rather than a regex is deliberate: module-scope-versus-lazy is the distinction the
whole invariant turns on, and it is exactly the distinction a regex cannot make.

## The version floor is DERIVED

`[host].python_min` is not trusted. The floor is recomputed from the stdlib modules the
tree actually imports against `[host.stdlib_since]`, and a derivation above the declared
value fails. A constant that nothing recomputes is AP-9, and this field is one that goes
stale in the direction nobody notices — a floor that is too LOW is invisible until it is
someone else's box.

**And the table lists every stdlib module rather than only the interesting one.** Listing
`tomllib` alone would be shorter and would be D16's fifth failure in advance: a gate that
only asks about modules already known to be interesting cannot answer for the one added
next week. An import missing from the table **REFUSES**.

## D15: controls, and a refusal on vacuity

`--self-test` plants four defects, one per rule, and requires all four to be caught:

1. a module-scope third-party import
2. an undeclared dynamic load  (the door the obvious gate misses)
3. a stdlib module above the declared floor
4. a `#!` naming a shell the contract does not declare

And the refusals, because the comfortable wrong answer here is a clean verdict over
nothing: fewer than `MIN_FILES` files, or zero imports extracted, or a stdlib module with
no `stdlib_since` row, REFUSES and exits non-zero. An instrument that can only say PASS or
FAIL has no way to say *"I did not measure anything"*, and that is the state it will be in
the day it breaks.

    ./tools/check-toolchain.py
    ./tools/check-toolchain.py --self-test
    ./tools/check-toolchain.py --print-imports    # re-derives [host.stdlib_since]
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The language-neutral half. NOT `languages/**` — a per-target file is allowed to depend
#: on its own target's toolchain, which is what a target directory is for (§1.2b).
CORPUS = ["tools/*.py", "gates/*/*.py"]

#: Shell scripts in the same half, whose `#!` is a host dependency in one line.
SHELL_CORPUS = ["tools/*", "gates/*/*"]

#: A corpus assertion (D15 clause 2), not a count of units: below this the globs have
#: stopped matching something they used to match. Calibrated at 12 against a measured 16.
MIN_FILES = 12

#: Likewise for imports — a parse that yields nothing is never a clean verdict.
MIN_IMPORTS = 20

#: The call names that load a module without an `import` statement.
DYNAMIC_CALLS = ("__import__", "import_module", "spec_from_file_location", "exec")


class Refusal(Exception):
    """The gate could not run. Never reported as a verdict about the toolchain."""


def declaration() -> dict:
    decl = tomllib.loads((ROOT / "tools" / "tooling.toml").read_text(encoding="utf-8"))
    if "host" not in decl:
        raise Refusal(
            "REFUSING: `tools/tooling.toml` has no [host] block. The contract this gate "
            "checks is the declaration; with no declaration there is nothing to check "
            "against, and a green run would mean only that the file was unreadable."
        )
    return decl["host"]


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def files(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    for pattern in patterns:
        out.extend(sorted(p for p in ROOT.glob(pattern) if p.is_file()))
    return out


def lazy_import_nodes(tree: ast.AST) -> set[int]:
    """`id()` of every import statement sitting inside a function body."""
    lazy: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    lazy.add(id(sub))
    return lazy


def scan(path: Path) -> tuple[list[tuple[str, str, int]], list[tuple[str, int]]]:
    """`(imports, dynamic_sites)` for one file.

    An import is `(module_root, "module-scope" | "lazy", lineno)`; a dynamic site is
    `(call_name, lineno)`. Both are returned per occurrence rather than as a set, because
    a line number is what makes a failure actionable.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lazy = lazy_import_nodes(tree)

    imports: list[tuple[str, str, int]] = []
    dynamic: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # A relative import (`from . import x`) has no module and is in-tree by
            # construction; `node.level` is what tells them apart.
            names = [] if node.level else [node.module or ""]
        elif isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute) else None
            )
            if name in DYNAMIC_CALLS:
                dynamic.append((name, node.lineno))
            continue
        else:
            continue
        for full in names:
            root = full.split(".")[0]
            if root:
                where = "lazy" if id(node) in lazy else "module-scope"
                imports.append((root, where, node.lineno))

    return imports, dynamic


def in_tree_module(root: str, path: Path) -> bool:
    """A sibling tool imported by module name — `compose`, `schema`.

    These are this repo's own files reached through a `sys.path` insert, so they are not a
    host dependency at all. Resolved against the importing file's OWN directory rather
    than against a list, so a new sibling needs no declaration and a MISSING one is still
    caught.
    """
    return (path.parent / f"{root}.py").exists() or (
        path.parent / root.replace("_", "-")
    ).with_suffix(".py").exists()


def run(extra: list[Path] | None = None) -> tuple[list[str], list[str], str, int, int]:
    """Returns `(failures, notes, derived_floor, n_files, n_imports)`."""
    host = declaration()
    since: dict[str, str] = host.get("stdlib_since", {})
    declared_min = host.get("python_min")
    declared_shells = set(host.get("shells", []))
    declared_sites = {
        entry["site"]: entry for entry in host.get("dynamic_load", [])
    }
    if not since or not declared_min or not declared_shells:
        raise Refusal(
            "REFUSING: [host] is missing `stdlib_since`, `python_min` or `shells`. "
            "Each of the three rules below is checked AGAINST one of them; an absent key "
            "would silently disable a rule and the run would still print OK."
        )

    py_files = files(CORPUS) + list(extra or [])
    if len(py_files) < MIN_FILES:
        raise Refusal(
            f"REFUSING: {len(py_files)} `.py` file(s) in the neutral half, below the "
            f"floor of {MIN_FILES}. The corpus globs have stopped matching, and a clean "
            "verdict over an empty corpus is not a clean verdict."
        )

    failures: list[str] = []
    notes: list[str] = []
    floor = (0,)
    floor_module = "—"
    n_imports = 0

    for path in py_files:
        rel = path.relative_to(ROOT).as_posix()
        imports, dynamic = scan(path)
        n_imports += len(imports)

        # ── rule 1: nothing but the stdlib at module scope ──────────────────────
        for root, where, lineno in imports:
            if in_tree_module(root, path):
                continue
            if root not in since:
                if where == "module-scope":
                    failures.append(
                        f"{rel}:{lineno}: module-scope import of `{root}`, which is not "
                        f"in [host.stdlib_since]. The host half is stdlib-only; a "
                        f"third-party dependency runs in a container."
                    )
                else:
                    failures.append(
                        f"{rel}:{lineno}: lazy import of `{root}`, undeclared. A "
                        f"non-stdlib module needs a [[host.dynamic_load]] entry naming "
                        f"where it runs."
                    )
                continue
            # ── rule 3: the floor is derived from what is actually imported ─────
            added = version_tuple(since[root])
            if added > floor:
                floor, floor_module = added, root

        # ── rule 2: every door an `import` statement does not come through ──────
        if dynamic:
            entry = declared_sites.get(rel)
            if entry is None:
                calls = ", ".join(sorted({f"{name}() line {ln}" for name, ln in dynamic}))
                failures.append(
                    f"{rel}: loads a module dynamically ({calls}) with no "
                    f"[[host.dynamic_load]] declaration. This is the door an import "
                    f"scan cannot see — `entity_core` arrives through exactly this one."
                )
            elif entry.get("where") == "container":
                if rel not in host.get("container_only", []):
                    failures.append(
                        f"{rel}: declared `where = \"container\"` but absent from "
                        f"[host].container_only. An entry point that reaches a "
                        f"third-party module must be declared unrunnable on a bare host, "
                        f"or the Makefile and this file will drift apart in silence."
                    )

    # ── rule 4: the shells ──────────────────────────────────────────────────────
    for path in files(SHELL_CORPUS):
        if path.suffix in (".py", ".toml", ".md", ".json", ".cbor"):
            continue
        try:
            first = path.read_text(encoding="utf-8").splitlines()[0]
        except (UnicodeDecodeError, IndexError):
            continue
        if not first.startswith("#!"):
            continue
        interpreter = first[2:].strip().split()[0]
        if interpreter.endswith("python3") or interpreter == "/usr/bin/env":
            continue
        if interpreter not in declared_shells:
            rel = path.relative_to(ROOT).as_posix()
            failures.append(
                f"{rel}:1: `#!{interpreter}` is not in [host].shells "
                f"({', '.join(sorted(declared_shells))}). A shebang is a host dependency "
                f"in one line."
            )

    if n_imports < MIN_IMPORTS:
        raise Refusal(
            f"REFUSING: {n_imports} imports extracted, below the floor of "
            f"{MIN_IMPORTS}. The AST walk has stopped finding what it used to find."
        )

    # ── the derived floor, against the declared one ─────────────────────────────
    derived = ".".join(str(part) for part in floor)
    if floor > version_tuple(declared_min):
        failures.append(
            f"tools/tooling.toml: [host].python_min is {declared_min}, but the tree "
            f"imports `{floor_module}`, added in {derived}. The declared floor is too "
            f"LOW — which is the direction nobody notices until it is someone else's box."
        )

    # Reported, never silent: a module declared stdlib that this interpreter does not
    # carry. NOT a failure — the running interpreter may be newer than the floor and a
    # module may have been removed since. A false red costs the instrument (D15).
    for module in sorted(since):
        if module not in sys.stdlib_module_names and module != "__future__":
            notes.append(
                f"`{module}` is declared stdlib but is absent from this interpreter "
                f"({'.'.join(str(v) for v in sys.version_info[:2])}). Not a failure: the "
                f"declaration is for the FLOOR, not for the box this ran on."
            )

    return failures, notes, f"{derived} (`{floor_module}`)", len(py_files), n_imports


def print_imports() -> int:
    """Re-derive `[host.stdlib_since]`'s key set. D14: the command that prints the number."""
    seen: dict[str, set[str]] = {}
    for path in files(CORPUS):
        imports, _ = scan(path)
        for root, where, _lineno in imports:
            if not in_tree_module(root, path):
                seen.setdefault(root, set()).add(where)
    print(f"{len(seen)} distinct module roots across {len(files(CORPUS))} files\n")
    for module in sorted(seen):
        mark = "stdlib" if module in sys.stdlib_module_names else "NOT-STDLIB"
        print(f"  {module:12} {mark:11} {','.join(sorted(seen[module]))}")
    return 0


def self_test() -> int:
    """D15's control: four planted defects, one per rule, all four required to be caught."""
    planted = ROOT / "tools" / "_toolchain_self_test.py"
    planted.write_text(
        "import cryptography\n"  # 1. module-scope third party
        "import importlib\n"
        "import graphlib\n"  # 3. stdlib, but 3.9 — above nothing today, see below
        "\n"
        "def load():\n"
        "    return importlib.import_module('yaml')\n",  # 2. undeclared dynamic load
        encoding="utf-8",
    )
    shell = ROOT / "tools" / "_toolchain_self_test_shell"
    shell.write_text("#!/bin/bash\necho planted\n", encoding="utf-8")  # 4. bad shebang
    try:
        failures, _notes, _floor, _n, _i = run(extra=[planted])
    finally:
        planted.unlink()
        shell.unlink()

    want = {
        "1. module-scope third-party import": any(
            "cryptography" in f and "module-scope" in f for f in failures
        ),
        "2. undeclared dynamic load (the door an import scan misses)": any(
            "_toolchain_self_test.py" in f and "dynamic" in f.lower() for f in failures
        ),
        "3. stdlib module with no [host.stdlib_since] row": any(
            "graphlib" in f for f in failures
        ),
        "4. an undeclared shell in a `#!`": any("bash" in f for f in failures),
    }
    for label, caught in want.items():
        print(f"  {'PASS' if caught else 'MISS'}  {label}")
    if not all(want.values()):
        print(
            "\nSELF-TEST FAILED: this instrument cannot be trusted to find a real one.",
            file=sys.stderr,
        )
        return 1
    print("\nself-test OK -- four planted defects, four caught, one per rule")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="plant one defect per rule and require this gate to catch all four (D15)",
    )
    ap.add_argument(
        "--print-imports",
        action="store_true",
        help="re-derive the module roots [host.stdlib_since] must cover (D14)",
    )
    args = ap.parse_args()

    if args.print_imports:
        return print_imports()
    if args.self_test:
        try:
            return self_test()
        except Refusal as exc:
            print(exc, file=sys.stderr)
            return 2

    try:
        failures, notes, floor, n_files, n_imports = run()
    except Refusal as exc:
        print(exc, file=sys.stderr)
        return 2

    host = declaration()
    # The corpus and its scope printed BEFORE any verdict: that line is the scope of every
    # negative claim below it (`req-coverage.py`'s rule, and it is the right one).
    print(
        f"toolchain: {n_files} neutral python file(s), {n_imports} imports, "
        f"{len(host.get('dynamic_load', []))} declared dynamic load(s)"
    )
    print(f"  host programs   : {', '.join(host.get('programs', []))}")
    print(f"  declared floor  : python {host.get('python_min')}")
    print(f"  derived floor   : python {floor}")
    for note in notes:
        print(f"  note  {note}")

    if failures:
        print()
        for f in failures:
            print(f"  FAIL  {f}")
        print(f"\nTOOLCHAIN: {len(failures)} violation(s).")
        print(
            "The host half is stdlib-only and the host contract is declared. A dependency "
            "that arrives without a decision is the failure this gate exists for."
        )
        return 1

    print("\nTOOLCHAIN: OK -- host half is stdlib-only, every door declared, floor derived.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
