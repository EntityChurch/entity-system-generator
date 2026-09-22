#!/usr/bin/env python3
"""compose.py — resolve a SYSTEM.toml into a PLAN.json, refusing the compositions
that cannot be legal.

**Language-neutral on purpose.** This is the third axis, and it is the only place
the composition-time invariants can be checked at all: I6 (no two handlers claim
the same dispatch pattern), I7 (no two extensions claim overlapping owned
namespaces), I9 (an extension with an unmet declared dependency does not install).
Those failures cannot occur inside keystone and cannot be found by testing an
extension alone -- which is the whole argument for `compositions/` being a
first-class artifact with a gate rather than a build flag.

It lives in `tools/` rather than in a per-language driver for the reason
`languages/<lang>/` exists at all: a build driver in the (extension x language) cell
would be 26 x 46 = 1,196 copies of one script. Keystone reached 46 copies of
`run-s4.sh` and one defect reproduced in 36 of them. Nothing that can be shared is
copied into a cell.

The plan is an OUTPUT. Never edited by hand; regenerating it must be byte-identical
or the generator is non-deterministic (which `--check` asserts).

  ./tools/compose.py compositions/ts-content --out output/ts-content/PLAN.json
  ./tools/compose.py compositions/ts-content --check     # regenerate and diff
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Refusal(Exception):
    """A composition that must not be emitted. Refuse BEFORE generating, not at runtime."""


def load_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise Refusal(f"cannot read {path}: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise Refusal(f"{path} is not valid TOML: {e}") from e


def extension_dir(name: str) -> Path:
    """`CONTENT` -> `extensions/content/`. The directory name is the lowercased
    extension name, always -- one rule, no table to drift."""
    return ROOT / "extensions" / name.lower()


def resolve_closure(names: list[str]) -> list[dict]:
    """Load each extension's contract, following `depends` transitively.

    I9: an unmet declared dependency REFUSES here. `GUIDE-EXTENSION-DEVELOPMENT`
    §3.3/§3.4 -- hard dependencies DO refuse; they do not degrade.
    """
    seen: dict[str, dict] = {}
    order: list[str] = []
    stack = list(names)
    requested = set(names)

    while stack:
        name = stack.pop(0)
        if name in seen:
            continue
        manifest_path = extension_dir(name) / "EXTENSION.toml"
        if not manifest_path.exists():
            origin = "requested by SYSTEM.toml" if name in requested else "pulled in as a dependency"
            raise Refusal(
                f"I9: extension {name!r} ({origin}) has no {manifest_path.relative_to(ROOT)} -- "
                "an extension with an unmet declared dependency does not install"
            )
        manifest = load_toml(manifest_path)
        declared = manifest.get("extension", {}).get("name")
        if declared != name:
            raise Refusal(
                f"{manifest_path.relative_to(ROOT)} declares [extension].name = {declared!r} "
                f"but lives at the directory for {name!r}"
            )
        seen[name] = manifest
        order.append(name)
        stack.extend(manifest.get("contract", {}).get("depends", []))

    return [{"name": n, "manifest": seen[n]} for n in order]


def check_disjoint(resolved: list[dict]) -> None:
    """I6 + I7. Both are prefix/equality questions over the resolved set, and both
    are silent at runtime if unchecked: I6 surfaces as a 409 nobody expected
    (`SDK-OPERATIONS` §11.6.1 -- "silent overwrite is not permitted"), I7 as two
    extensions writing each other's entities with nothing to notice."""
    patterns: dict[str, str] = {}
    for item in resolved:
        pattern = item["manifest"].get("surfaces", {}).get("handler")
        if not pattern:
            continue
        if pattern in patterns:
            raise Refusal(
                f"I6: {item['name']} and {patterns[pattern]} both claim dispatch pattern "
                f"{pattern!r}. §11.6.1 makes this a 409; refusing before emitting."
            )
        patterns[pattern] = item["name"]

    namespaces: list[tuple[str, str]] = []
    for item in resolved:
        for ns in item["manifest"].get("contract", {}).get("owned_namespaces", []):
            for other_ns, other_name in namespaces:
                if ns.startswith(other_ns) or other_ns.startswith(ns):
                    raise Refusal(
                        f"I7: {item['name']}'s owned namespace {ns!r} overlaps "
                        f"{other_name}'s {other_ns!r} (§4.3 closed-namespace ownership)"
                    )
            namespaces.append((ns, item["name"]))


def check_snapshots(resolved: list[dict]) -> list[dict]:
    """Every extension names a pinned spec snapshot, and the snapshot must exist.

    D14: a number cites the artifact that produced it. The same rule applies to a
    transcription -- `[contract]` is a projection of a spec header, and a projection
    whose source is not pinned reads as authority while being unverifiable.
    """
    out = []
    for item in resolved:
        snapshot = item["manifest"].get("extension", {}).get("snapshot")
        if not snapshot:
            raise Refusal(f"{item['name']} declares no [extension].snapshot -- the input is unpinned")
        snapshot_dir = ROOT / "shared" / "spec-data" / snapshot
        manifest_md = snapshot_dir / "MANIFEST.md"
        if not manifest_md.exists():
            raise Refusal(
                f"{item['name']} names snapshot {snapshot!r} but {manifest_md.relative_to(ROOT)} "
                "does not exist -- operators never edit a snapshot, and they never invent one either"
            )
        out.append({"extension": item["name"], "snapshot": snapshot,
                    "manifest": str(manifest_md.relative_to(ROOT))})
    return out


#: The four faces of an extension (`docs/DESIGN-THE-SDK-LAYER.md` §1) and the states a
#: composition may declare for each. **Added at the third composition, and the reason is
#: a measurement rather than a design idea**: on the `rust` peer the faces do not get the
#: same answer -- types and emit install, the handler body cannot be installed at any
#: visibility (`gates/host-seam/rust/`, 501 with all four §11.6.1 tree writes bound).
#:
#: The first two compositions did not need this because on both peers all four faces were
#: available, so "the composition installs CONTENT" was unambiguous. It is not unambiguous
#: any more, and the cost of leaving it implicit is a report that reads as a full install.
FACES = {"types", "handler", "emit_consumer", "sdk"}

#: `not-installable` is the load-bearing one. It is NOT `not-installed`: the difference is
#: between a choice and a substrate fact, and only the first is revisitable.
FACE_STATES = {
    "installed",
    "not-installed",
    "not-installable",
    "available-unused",
    "library-only",
}


def check_faces(sys_block: dict, comp_name: str) -> dict:
    """Validate `[system.faces]`, and REFUSE a composition that claims a face it also
    declares unavailable.

    Optional: the two compositions that predate it declare no block and resolve exactly
    as before, which is what keeps this from being a retroactive rewrite of their plans.
    """
    faces = sys_block.get("faces")
    if faces is None:
        return {}
    unknown = set(faces) - FACES
    if unknown:
        raise Refusal(
            f"{comp_name}: [system.faces] names {sorted(unknown)}, which are not faces. "
            f"The four are {sorted(FACES)} (DESIGN-THE-SDK-LAYER §1)."
        )
    for face, state in faces.items():
        if state not in FACE_STATES:
            raise Refusal(
                f"{comp_name}: [system.faces].{face} = {state!r} is not a declared state. "
                f"One of {sorted(FACE_STATES)}."
            )
    return dict(faces)


def build_plan(comp_dir: Path) -> dict:
    system = load_toml(comp_dir / "SYSTEM.toml")
    sys_block = system.get("system", {})
    names = sys_block.get("extensions", [])
    if not names:
        raise Refusal(f"{comp_dir.name}: [system].extensions is empty -- nothing to compose")

    resolved = resolve_closure(list(names))
    check_disjoint(resolved)
    snapshots = check_snapshots(resolved)

    peer = sys_block.get("peer", {})
    language = peer.get("language")
    if not language:
        raise Refusal(f"{comp_dir.name}: [system.peer].language is required")

    faces = check_faces(sys_block, comp_dir.name)

    installs = []
    for item in resolved:
        manifest = item["manifest"]
        cell = extension_dir(item["name"]) / language
        if not cell.is_dir():
            raise Refusal(
                f"{item['name']} has no {language} port at {cell.relative_to(ROOT)} -- "
                "a composition names an (extension x language) cell that must exist"
            )
        surfaces = manifest.get("surfaces", {})

        # The refusal that makes `[system.faces]` worth having. An extension whose
        # `[surfaces].handler` names a dispatch pattern is declaring it HAS a handler
        # face; a composition declaring that face `not-installable` and then letting the
        # plan carry the pattern anyway would emit a wiring program that binds a manifest
        # for a body that does not exist -- which moves the peer from `404
        # handler_not_found` to `501 no_handler_body`. Measured, both arms:
        # `gates/host-seam/rust/`. The pattern is dropped from the plan instead, so the
        # thing that would have been generated cannot be.
        if surfaces.get("handler") and faces.get("handler") == "not-installable":
            surfaces = dict(surfaces)
            surfaces["handler"] = None
        installs.append(
            {
                "extension": item["name"],
                "version": manifest.get("extension", {}).get("version"),
                "grade": manifest.get("extension", {}).get("grade"),
                "cell": str(cell.relative_to(ROOT)),
                "pattern": surfaces.get("handler"),
                # What the EXTENSION declares, kept beside what the composition can
                # install. Dropping `pattern` without recording this would lose the
                # distinction between "this extension has no handler" (CONTENT does) and
                # "this peer cannot host one" (the actual situation).
                "pattern_declared": manifest.get("surfaces", {}).get("handler"),
                "owned_namespaces": manifest.get("contract", {}).get("owned_namespaces", []),
                "owned_types": manifest.get("contract", {}).get("owned_types", []),
                "install_model": manifest.get("install", {}).get("model"),
                "publishes_types": bool(surfaces.get("types")),
                "emit_consumers": surfaces.get("emit_consumers", []),
            }
        )

    return {
        "composition": sys_block.get("name", comp_dir.name),
        "language": language,
        "faces": faces,
        "peer": {"generator": peer.get("generator"), "path": peer.get("path")},
        # Install order IS the closure order: a dependency is installed before the
        # extension that declared it. With one extension this is trivially true and
        # states the rule anyway, because the first two-extension composition is
        # where an unstated ordering rule becomes an ordering bug.
        "install_order": [i["extension"] for i in installs],
        "installs": installs,
        "snapshots": snapshots,
        "gate": system.get("gate", {}),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("composition", help="path to a compositions/<name>/ directory")
    ap.add_argument("--out", help="write PLAN.json here (default: output/<name>/PLAN.json)")
    ap.add_argument("--check", action="store_true",
                    help="regenerate and fail if the result differs from --out")
    args = ap.parse_args()

    comp_dir = Path(args.composition).resolve()
    try:
        plan = build_plan(comp_dir)
    except Refusal as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2

    out = Path(args.out) if args.out else ROOT / "output" / plan["composition"] / "PLAN.json"
    rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not out.exists():
            print(f"--check: {out} does not exist", file=sys.stderr)
            return 1
        if out.read_text(encoding="utf-8") != rendered:
            print(f"--check: {out} differs from a fresh resolve -- the resolver is not "
                  "deterministic, or the plan was edited by hand", file=sys.stderr)
            return 1
        print(f"plan is reproducible: {out}")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding="utf-8")
    print(f"wrote {out}")
    for install in plan["installs"]:
        print(f"  {install['extension']} v{install['version']} ({install['grade']}) "
              f"-> {install['pattern']} via {install['install_model']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
