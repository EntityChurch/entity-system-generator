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

  ./tools/sdk-parity.py extensions/content
  ./tools/sdk-parity.py extensions/content --strict-drift
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Where each port publishes its public surface. One entry per language, and the file
#: named here is the PUBLIC ENTRY POINT -- not the source tree. A parser pointed at
#: `src/**` would report every internal symbol and the §3.4 boundary would vanish.
ENTRY_POINTS = {
    "typescript": "index.ts",
    "python": "__init__.py",
    "rust": "src/lib.rs",
}


class Refusal(Exception):
    """The gate could not run. Never reported as a verdict about the ports."""


def key(name: str) -> tuple[str, str]:
    """`(kind, snake_case)`. See the module doc: collapsing the kind manufactured
    agreement between `Blob` and `BLOB` on this script's first run."""
    if name.upper() == name and len(name) > 1:
        return ("const", name.lower())
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return ("type" if name[0].isupper() else "fn", snake)


def extract_typescript(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    out: set[str] = set()
    for block in re.findall(r"export \{([^}]*)\} from", text, re.S):
        for item in block.split(","):
            item = item.strip()
            if re.match(r"^(type )?[A-Za-z_]\w*$", item):
                out.add(item.replace("type ", ""))
    out |= set(re.findall(r"^export (?:function|class|interface|const|type|enum) (\w+)", text, re.M))
    return out


def extract_python(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    # `__all__ = [...]`, not the first mention of `__all__` -- the module docstring
    # discusses it, and splitting on the token landed inside the prose. That defect cost
    # a measurement pass: the port parsed to zero names and the run reported it as drift.
    match = re.search(r"^__all__\s*=\s*\[(.*?)\]", text, re.S | re.M)
    if not match:
        raise Refusal(f"{path}: no `__all__` assignment found")
    return set(re.findall(r'"(\w+)"', match.group(1)))


def extract_rust(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    out: set[str] = set()
    for block in re.findall(r"pub use [\w:]+::\{([^}]*)\};", text, re.S):
        for item in block.split(","):
            item = item.strip()
            if re.match(r"^[A-Za-z_]\w*$", item):
                out.add(item)
    out |= set(re.findall(r"^pub (?:fn|struct|enum|const) (\w+)", text, re.M))
    return out


EXTRACTORS = {
    "typescript": extract_typescript,
    "python": extract_python,
    "rust": extract_rust,
}


def surfaces(ext_dir: Path) -> dict[str, dict[tuple[str, str], str]]:
    """`port -> {key: original name}` for every port that has a cell."""
    out: dict[str, dict[tuple[str, str], str]] = {}
    for lang, entry in ENTRY_POINTS.items():
        cell = ext_dir / lang
        if not cell.is_dir():
            continue
        path = cell / entry
        if not path.exists():
            raise Refusal(f"{cell.relative_to(ROOT)} has no public entry point at {entry}")
        names = EXTRACTORS[lang](path)
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


def declared(manifest: dict) -> tuple[dict, dict, dict]:
    block = manifest.get("sdk_surface", {})
    req = {tuple(k.split(":", 1)) for k in block.get("required", [])}
    sub = block.get("substrate", {})
    dri = block.get("drift", {})
    return {tuple(k.split(":", 1)): None for k in block.get("required", [])}, sub, dri


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("extension", help="path to an extensions/<name>/ directory")
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

    required, substrate, drift = declared(manifest)
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
        print("\n  unresolved drift -- measured, NOT blessed:")
        for k in drift_present:
            where = "".join("x" if k in ports[p] else "." for p in ("typescript", "python", "rust")
                            if p in ports)
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
