#!/usr/bin/env python3
"""sdk-parity.py — the SDK surface gate. **Ours, because nobody upstream owns it.**

## Why this exists at all

`entity-system-architecture` does not mandate the SDK surface, and that is correct
rather than an omission: **arch enforces what has to be enforced.** The SDK face is a
convention, the wire is where conformance lives, and a cross-impl surface oracle would
enforce the thing the corpus explicitly disclaims (`DESIGN-THE-SDK-LAYER.md` §1.1a).

**But "not required by the spec" and "not required by us" are different sentences.** We
are the implementers. We generate N ports of one extension and we want them to be the
same extension. So the standard is ours to set, and if it later earns promotion — into
`GUIDE-EXTENSION-DEVELOPMENT`, or into a `validate-peer` category — it goes upstream as
a proposal with this gate's output as the evidence. Same shape as the host contract: we
found it by generating, keystone owns the document.

## What it measures, and the number that made it worth writing

Three ports of CONTENT, first measured 2026-09-06:

```
24 names in all three ports · 27 drifting · union 51
```

**The operation inventory held** — all 15 SDK/algorithm functions are in every port. What
drifted is the *constant and type* surface, and almost all of it is one decision made
once and never made again: `typescript` bundles the type-name constants into
`ContentTypes` and `Chunking` objects; `python` and `rust` export them flat. Same
information, two shapes, and **nothing anywhere declared which was intended.**

That is the class of difference no test catches. Every port passes its own suite, the
oracle never looks at an in-process surface, and a consumer writing against two of our
ports finds the third one has renamed half its vocabulary.

## The rule

**Every public name in every port is declared in exactly one class.** Not "should be" —
an undeclared name is a gate failure, because the whole failure mode is a name arriving
without anyone deciding.

| class | meaning | gate |
|---|---|---|
| `required` | the extension's contract. Every port exports it. | **missing from any port = FAIL** |
| `substrate` | present only where the substrate allows, with the ports and the reason | present in a port not listed = FAIL |
| `drift` | measured, unresolved, **not blessed** | reported; FAIL under `--strict-drift` |
| *(undeclared)* | nobody decided | **FAIL** |

`drift` exists so the gate is honest on the day it is written rather than green because
it was scoped around what already passes. A gate that ships red is a gate the next
person disables (AP-4). A gate that ships green by blessing everything measures nothing.
This one ships green, names all 27, and `--strict-drift` is the switch that makes them
errors the moment they are resolved — after which the class can never quietly refill.

## Names are compared as `(kind, snake_case)`, and the kind is load-bearing

`Blob` is a type and `BLOB` is a constant. A normaliser that lowercases both maps them to
one key and **reports agreement where there is none** — which is exactly what the first
version of this script did, hiding that `typescript` exports no `BLOB` at all. Caught by
re-running with the kind preserved, and it is the reason `key()` looks the way it does.
D15: an instrument is not trusted until it has been seen producing the other answer, and
this one produced the *wrong* answer first.

  ./tools/sdk-parity.py extension-contracts/content
  ./tools/sdk-parity.py extension-contracts/content --strict-drift
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: NO `ENTRY_POINTS` DICT AND NO `EXTRACTORS` DICT, and their absence is the point.
#:
#: This file used to carry both: `{target: entry_point_filename}` and
#: `{target: extractor_function}`, with the three extractors defined above them -- ~120
#: lines of per-language parsing in the LANGUAGE-NEUTRAL half. At three targets that reads
#: as a small table. At forty-six it is a forty-six-way dispatch over forty-six hand-written
#: functions, in the one file whose whole job is to be finished.
#:
#: Both halves moved 2026-09-07, each to the home an existing rule already named:
#:
#:   the VALUE      -> `languages/<t>/profile.toml [sdk_surface] entry_point`   (D17)
#:   the PROCEDURE  -> `languages/<t>/gates/sdk-surface/extract.py`             (§1.2b)
#:
#: What is left here is the protocol: collect every arm, normalise, compare, decide. The
#: arm list is a `wildcard` over the tree, so **adding a target is adding a directory** and
#: never an edit to this file. Found by `tools/check-glue.py` on its first run.


def run_arm(target: str, extension: str) -> dict | None:
    """Execute the target's arm and return its report, or None if it has no arm.

    EXECUTED, not imported. An imported extractor would have to be Python, which is a
    neutral-half constraint reaching into a target: the point of `languages/<t>/` is that a
    target holds its own idiom. A `run` emitting JSON lets a future target read its surface
    with its own toolchain (`tsc`'s API, `rustdoc --output-format json`) without this file
    learning anything about it.
    """
    arm = ROOT / "languages" / target / "gates" / "sdk-surface" / "run"
    if not arm.exists():
        return None
    proc = subprocess.run([str(arm), extension], capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        # The arm's own refusal, surfaced verbatim. It knows the cause; this does not.
        raise Refusal(f"languages/{target}/gates/sdk-surface/run: "
                      f"{proc.stderr.strip() or f'exit {proc.returncode}'}")
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise Refusal(
            f"languages/{target}/gates/sdk-surface/run exited 0 but produced no parsable "
            f"report. Exit 0 with no output is the shape that reads as an empty surface."
        )


class Refusal(Exception):
    """The gate could not run. Never reported as a verdict about the ports."""


def key(name: str) -> tuple[str, str]:
    """`(kind, snake_case)`. See the module doc: collapsing the kind manufactured
    agreement between `Blob` and `BLOB` on this script's first run."""
    if name.upper() == name and len(name) > 1:
        return ("const", name.lower())
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return ("type" if name[0].isupper() else "fn", snake)


def surfaces(ext_dir: Path) -> dict[str, dict[tuple[str, str], str]]:
    """`port -> {key: original name}` for every port that has a cell.

    Under target-major the cells are NOT under `ext_dir` -- the contract is neutral and
    lives at `extension-contracts/<name>/`, while each port lives under its own target at
    `languages/<target>/extensions/<name>/`. This gate is the reason the contract stayed
    whole and at the root: `[sdk_surface]` is the cross-port contract, and a comparison
    table sharded per port stops being a comparison.
    """
    name = ext_dir.name
    out: dict[str, dict[tuple[str, str], str]] = {}
    langs = sorted(p.name for p in (ROOT / "languages").iterdir() if p.is_dir())
    for lang in langs:
        cell = ROOT / "languages" / lang / "extensions" / name
        if not cell.is_dir():
            continue
        report = run_arm(lang, name)
        if report is None:
            raise Refusal(
                f"languages/{lang}/ has a `{name}` cell but no gates/sdk-surface/run. "
                "A port with a surface and no arm drops OUT of the comparison silently, "
                "which is the one direction a parity gate must never fail in."
            )
        names = set(report["names"])
        # D15's zero-parse refusal, and this one has fired for real: the python
        # extractor split on the wrong `__all__` and returned an empty set, which the
        # first run reported as "python exports nothing" rather than as a broken parse.
        # An empty result set is never a verdict about the port.
        if not names:
            raise Refusal(
                f"{path.relative_to(ROOT)}: parsed 0 public names. That is a broken "
                "extractor, not an empty surface. REFUSING to report parity."
            )
        out[lang] = {key(n): n for n in names}
    return out


#: The three kinds `key()` can produce, and therefore the only prefixes a declaration may
#: carry. Named rather than inlined so the refusal below can print the set.
KINDS = ("const", "fn", "type")


def _declared_key(spelled: str, where: str) -> tuple[str, str]:
    """Parse one `[sdk_surface]` entry into the `(kind, snake_case)` key `key()` produces.

    REFUSES on a malformed entry rather than returning something comparable, and that
    refusal is D15's vacuity clause applied to this gate's own INPUT rather than to the
    ports'.

    ** IT WAS ADDED ON AN INCIDENT, 2026-09-12, AND THE INCIDENT IS THE ARGUMENT. **
    `extension-contracts/compute/EXTENSION.toml` shipped `[sdk_surface].required` as 67
    RAW typescript names -- `"LITERAL"`, `"isComputeExpression"` -- with no `kind:` prefix,
    because COMPUTE had one port and this gate REFUSES below two. So the block was written,
    reviewed, cited in a handoff, and parsed by nothing for three days. The moment the
    second port landed, `tuple("LITERAL".split(":", 1))` produced a ONE-tuple and
    `failures.append(f"... {k[1]} ...")` died with `IndexError: tuple index out of range` --
    a traceback in the middle of `make check`, which is neither a verdict nor a refusal.
    D16's shape in this gate's own declaration file: *the thing we own is the thing nothing
    watches*, and a refusal that only fires above two ports leaves the one-port case
    unread.

    Had the crash not happened the answer would have been WORSE: a one-tuple matches no
    port key, so all 67 would have been reported as `REQUIRED ... missing from python,
    typescript` -- sixty-seven false reds in front of a reader on day one, and a false red
    costs the instrument (AP-4).
    """
    parts = spelled.split(":", 1)
    if len(parts) != 2 or parts[0] not in KINDS or not parts[1]:
        raise Refusal(
            f"{where} entry {spelled!r} is not a `kind:snake_case` key. Every entry must be "
            f"one of {list(KINDS)} followed by a colon and the normalised name (see `key()`). "
            "REFUSING rather than comparing: an unparsable declaration compares equal to "
            "nothing, so every required name would read as missing from every port."
        )
    return (parts[0], parts[1])


def declared(manifest: dict) -> tuple[dict, dict, dict]:
    block = manifest.get("sdk_surface", {})
    sub = block.get("substrate", {})
    dri = block.get("drift", {})
    req = {_declared_key(k, "[sdk_surface].required"): None
           for k in block.get("required", [])}
    # The other two blocks are keyed by the same spelling and are parsed at their use sites;
    # validate them HERE so a malformed key in either is one refusal rather than three
    # separate surprises further down.
    for spelled in sub:
        _declared_key(spelled, "[sdk_surface.substrate]")
    for spelled in dri:
        _declared_key(spelled, "[sdk_surface.drift]")
    return req, sub, dri


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("extension", help="path to an extension-contracts/<name>/ directory")
    ap.add_argument("--strict-drift", action="store_true",
                    help="treat every `drift` entry as a failure (flip this once they are resolved)")
    args = ap.parse_args()

    ext_dir = Path(args.extension).resolve()
    try:
        manifest = tomllib.loads((ext_dir / "EXTENSION.toml").read_text(encoding="utf-8"))
        ports = surfaces(ext_dir)
    except Refusal as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2

    if len(ports) < 2:
        print(f"REFUSED: {len(ports)} port(s) with a cell. Parity over one port is not a "
              "result.", file=sys.stderr)
        return 2

    # Parsed AFTER the port check and inside its own guard: a malformed declaration is a
    # refusal about this gate's input, not a verdict about the ports (see `_declared_key`).
    try:
        required, substrate, drift = declared(manifest)
    except Refusal as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2

    name_of = {k: v for p in ports.values() for k, v in p.items()}
    union = set(name_of)

    print(f"{ext_dir.name}: {len(ports)} ports ({', '.join(sorted(ports))}), "
          f"{len(union)} distinct public names\n")

    failures: list[str] = []

    # 1. every `required` name is in every port.
    for k in sorted(required):
        missing = [p for p in ports if k not in ports[p]]
        if missing:
            failures.append(f"REQUIRED {k[0]}:{k[1]} missing from {', '.join(sorted(missing))}")

    # 2. every `substrate` name appears only in the ports that declare it.
    for spelled, entry in substrate.items():
        k = tuple(spelled.split(":", 1))
        allowed = set(entry.get("ports", []))
        actual = {p for p in ports if k in ports[p]}
        if actual - allowed:
            failures.append(
                f"SUBSTRATE {spelled} declared for {sorted(allowed)} but also exported by "
                f"{sorted(actual - allowed)} -- if the substrate does not force it, it is "
                "not substrate-conditional"
            )
        if not actual:
            failures.append(f"SUBSTRATE {spelled} is declared but exported by no port")

    # 3. NOTHING UNDECLARED. The whole failure mode is a name arriving without a decision.
    known = set(required) | {tuple(s.split(":", 1)) for s in substrate} \
                          | {tuple(s.split(":", 1)) for s in drift}
    undeclared = sorted(union - known)
    for k in undeclared:
        where = sorted(p for p in ports if k in ports[p])
        failures.append(
            f"UNDECLARED {k[0]}:{k[1]} (exported by {', '.join(where)}) -- add it to "
            "[sdk_surface] as required, substrate or drift"
        )

    # 4. drift: reported always, fatal only under --strict-drift.
    drift_present = sorted(k for k in {tuple(s.split(":", 1)) for s in drift} if k in union)
    stale_drift = sorted(k for k in {tuple(s.split(":", 1)) for s in drift} if k not in union)

    in_all = sorted(k for k in union if all(k in p for p in ports.values()))
    print(f"  required declared : {len(required):3}")
    print(f"  in every port     : {len(in_all):3}")
    print(f"  substrate         : {len(substrate):3}")
    print(f"  drift             : {len(drift_present):3}"
          + ("  (FATAL under --strict-drift)" if args.strict_drift else "  (reported, not fatal)"))
    print(f"  undeclared        : {len(undeclared):3}")

    if drift_present:
        # THE COLUMN IS LABELLED, and it was not always. The marker used to be built from
        # a hardcoded `("typescript", "python", "rust")` -- a fourth per-target literal in
        # this neutral file, and the last one removed. It is now `sorted(ports)`, which is
        # correct and also means the columns MOVED: a reader holding an older report would
        # map `[.xx]` onto the wrong two ports. An unlabelled positional column is a
        # quantity with no units.
        print(f"\n  unresolved drift -- measured, NOT blessed"
              f"   [{'|'.join(sorted(ports))}]:")
        for k in drift_present:
            where = "".join("x" if k in ports[p] else "." for p in sorted(ports))
            note = drift.get(f"{k[0]}:{k[1]}", {}).get("note", "")
            print(f"    [{where}] {k[0]:5} {k[1]:28} {note}")

    for k in stale_drift:
        failures.append(
            f"STALE {k[0]}:{k[1]} is declared as drift but no port exports it -- resolved "
            "drift is deleted from the block, not left as a tombstone"
        )

    if args.strict_drift and drift_present:
        failures.extend(f"DRIFT {k[0]}:{k[1]} (--strict-drift)" for k in drift_present)

    if failures:
        print(f"\nSDK PARITY: {len(failures)} failure(s)")
        for f in failures:
            print(f"  {f}")
        return 1

    print("\nSDK PARITY: OK -- every public name is declared, and every required name is "
          "in every port.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
