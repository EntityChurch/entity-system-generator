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

It lives in `tools/` rather than in a per-target driver for the reason
`languages/<target>/` exists at all: a build driver in the (extension x target) cell
would be 26 x 46 = 1,196 copies of one script. Keystone reached 46 copies of
`run-s4.sh` and one defect reproduced in 36 of them. Nothing that can be shared is
copied into a cell.

**The layout is TARGET-MAJOR** (2026-09-06). A target is a unified bundle -- its
driver, its profile, its extension cells, its compositions, its gate arms and its
output all live under `languages/<target>/`, because the people who consume this
arrive by language and should be able to read one directory. What stays at the root
is the language-NEUTRAL half of each axis: `extension-contracts/<ext>/EXTENSION.toml`
(the contract and the cross-port comparison tables, which cannot be sharded per port
without ceasing to be comparisons), `gates/` (the axis table and the neutral
instruments), `tools/`, `shared/spec-data/`.

  extension-contracts/content/EXTENSION.toml      the contract   (neutral)
  languages/rust/extensions/content/              the cell       (per target)
  languages/rust/compositions/content/            the composition
  languages/rust/gates/host-seam/                 the gate arm
  languages/rust/output/content/PLAN.json         the plan       (gitignored)

The plan is an OUTPUT. Never edited by hand; regenerating it must be byte-identical
or the generator is non-deterministic (which `--check` asserts).

  ./tools/compose.py languages/rust/compositions/content
  ./tools/compose.py languages/rust/compositions/content --check   # regenerate and diff
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


def contract_dir(name: str) -> Path:
    """`CONTENT` -> `extension-contracts/content/`. The directory name is the lowercased
    extension name, always -- one rule, no table to drift.

    The CONTRACT is language-neutral and stays at the root. Its per-target code lives at
    `languages/<target>/extensions/<name>/` -- see `cell_dir`. The two halves are named
    differently on purpose: `extension-contracts/` holds what we transcribed from a spec
    we do not own, and calling it `extension-specs/` would claim the authority AGENTS.md
    L0 says is arch's.
    """
    return ROOT / "extension-contracts" / name.lower()


def cell_dir(target: str, name: str) -> Path:
    """`(rust, CONTENT)` -> `languages/rust/extensions/content/`. The (extension x target)
    intersection, under the target because a target is a unified bundle."""
    return ROOT / "languages" / target / "extensions" / name.lower()


#: Fields a profile MUST carry, because something executes each one. Enforced rather than
#: documented: until 2026-09-06 `profile.toml` was parsed by NOTHING -- twenty greps for
#: the filename across the tree returned twenty docs, comments and the profiles themselves
#: -- so every fact in it was restated where it ran (the image in the Makefile, `host_entry`
#: inside each host-launch) and the executing copy silently won. That is AP-2's mechanism:
#: computed correctly, then copied into a document that outlived it. It is also D16's shape
#: -- an axis with no upstream authority and no gate -- applied to the file that now names
#: the repo's top-level organizing unit.
REQUIRED_PROFILE_FIELDS = [
    ("language", "name"),
    ("language", "packaging"),
    ("language", "compilation"),
    # D13's Access layer in one field. `typescript` carried this only as a comment while
    # the other two declared it, which is exactly the drift an unparsed schema permits.
    ("language", "boundary"),
    ("toolchain", "image"),
    ("gate", "host_entry"),
    ("gate", "oracle_bin"),
    # Added 2026-09-06 on AP-10. It was a literal in each `host-launch` and had already
    # drifted -- 100 on the port written first, 150 on the two written after, no comment
    # on any of the three. A per-target fact that lives in a driver cannot be compared
    # across targets, which is the whole failure.
    ("gate", "startup_ticks"),
]


def load_profile(target: str) -> dict:
    """Read and CHECK `languages/<target>/profile.toml`.

    Refuses rather than defaulting. A missing profile field used to mean "the Makefile's
    copy wins"; now it means the composition does not resolve, which is the only way a
    declaration stays true.
    """
    path = ROOT / "languages" / target / "profile.toml"
    if not path.exists():
        raise Refusal(
            f"target {target!r} has no {path.relative_to(ROOT)} -- a target is the "
            "(language, runtime, packaging, toolchain) tuple its profile declares, and "
            "an undeclared target cannot be built"
        )
    profile = load_toml(path)

    declared = profile.get("language", {}).get("name")
    if declared != target:
        raise Refusal(
            f"{path.relative_to(ROOT)} declares [language].name = {declared!r} but lives "
            f"at the directory for {target!r}"
        )

    missing = [f"[{s}].{k}" for s, k in REQUIRED_PROFILE_FIELDS
               if profile.get(s, {}).get(k) is None]
    if missing:
        raise Refusal(
            f"{path.relative_to(ROOT)} is missing {', '.join(missing)} -- every one of "
            "these is read by something, and a profile field nobody reads is prose"
        )
    return profile


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
        manifest_path = contract_dir(name) / "EXTENSION.toml"
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
#:
#: **`evaluator` IS THE FIFTH, ADDED 2026-09-09 AT THE FIRST COMPUTE COMPOSITION, and it
#: is an addition to the VOCABULARY rather than a relaxation of the check.** The four came
#: from `DESIGN-THE-SDK-LAYER` §1, written before this repo had met an extension that
#: installs anywhere else. COMPUTE does: `Peer.setExpressionEvaluator` (keystone's H7, which
#: this repo routed on 2026-09-03) is a seam of its own, reached by its own method, answered
#: independently of the other four.
#:
#: It qualifies by D13's own test and not by analogy. A face is a thing a peer answers
#: SEPARATELY -- that is the whole content of the face amendment, earned on `rust`, where
#: types and emit install and the handler body cannot. Here `handler` and `evaluator` are two
#: seams into the same dispatch path and a peer can host either without the other: every peer
#: in the cohort hosts a handler, and `setExpressionEvaluator` exists on ONE of the 46. Folding
#: the evaluator into `handler` would report `installed` for a peer that refused it, which is
#: precisely the category error the amendment exists to stop.
#:
#: **Routed as a vocabulary question, not settled unilaterally**, because
#: `DESIGN-THE-SDK-LAYER` §1's four-face model is cited by two other documents and by the
#: `[substrate.faces]` block in every `EXTENSION.toml`. Adding the value here is the smaller
#: half; whether the SDK-layer design should say "the faces are open-ended, enumerated per
#: extension" is the real question and it belongs in that document.
FACES = {"types", "handler", "emit_consumer", "sdk", "evaluator"}

#: `not-installable` is the load-bearing one. It is NOT `not-installed`: the difference is
#: between a choice and a substrate fact, and only the first is revisitable.
FACE_STATES = {
    "installed",
    "not-installed",
    "not-installable",
    "available-unused",
    "library-only",
}


def _check_face_map(faces: dict, comp_name: str, where: str) -> dict:
    """Validate one `{face: state}` map."""
    unknown = set(faces) - FACES
    if unknown:
        raise Refusal(
            f"{comp_name}: {where} names {sorted(unknown)}, which are not faces. "
            f"The four are {sorted(FACES)} (DESIGN-THE-SDK-LAYER §1)."
        )
    for face, state in faces.items():
        if state not in FACE_STATES:
            raise Refusal(
                f"{comp_name}: {where}.{face} = {state!r} is not a declared state. "
                f"One of {sorted(FACE_STATES)}."
            )
    return dict(faces)


def check_faces(sys_block: dict, comp_name: str, extensions: list[str]) -> dict:
    """Validate `[system.faces]` and return `{extension: {face: state}}`.

    TWO FORMS, AND THE SECOND ARRIVED WITH THE SECOND EXTENSION.

    The flat form -- `[system.faces]` as a bare `{face: state}` map -- was written when a
    composition held exactly one extension, so "the composition's handler face" named one
    thing. It is still accepted and the three cycle-1 compositions still use it; it means
    "these states apply to every extension in this composition", which is TRUE when there
    is one of them and an assumption the moment there are two.

    The per-extension form is `[system.faces.<EXTENSION>]`. It exists because
    `content-history` is the first composition where the flat form is a category error in
    exactly the way D13's amendment describes one level down: CONTENT registers no emit
    consumer and HISTORY registers one, so `emit_consumer = "installed"` is true of the
    composition and false of half of it. **A face is per (peer x extension x face)**, and
    the middle coordinate is the one this repo only just earned the right to see.

    Refuses a per-extension block naming an extension the composition does not install --
    a face declared for something absent is a claim about nothing, and it is the shape a
    stale block takes after an extension is removed.
    """
    faces = sys_block.get("faces")
    if faces is None:
        return {}

    per_extension = {k: v for k, v in faces.items() if isinstance(v, dict)}
    flat = {k: v for k, v in faces.items() if not isinstance(v, dict)}

    if per_extension and flat:
        raise Refusal(
            f"{comp_name}: [system.faces] mixes the flat form ({sorted(flat)}) with the "
            f"per-extension form ({sorted(per_extension)}). Pick one -- a half-qualified "
            "face table is read as whichever the reader expected."
        )

    if not per_extension:
        shared = _check_face_map(flat, comp_name, "[system.faces]")
        if len(extensions) > 1 and shared:
            raise Refusal(
                f"{comp_name}: [system.faces] is the flat form but the composition installs "
                f"{len(extensions)} extensions {sorted(extensions)}. The flat form asserts "
                "one face state for all of them, which is a claim about the composition "
                "that is false of its parts as soon as they differ (D13, amended). Use "
                "[system.faces.<EXTENSION>]."
            )
        return {ext: dict(shared) for ext in extensions}

    unknown_ext = set(per_extension) - set(extensions)
    if unknown_ext:
        raise Refusal(
            f"{comp_name}: [system.faces] declares faces for {sorted(unknown_ext)}, which "
            f"the composition does not install ({sorted(extensions)})."
        )
    return {
        ext: _check_face_map(per_extension.get(ext, {}), comp_name, f"[system.faces.{ext}]")
        for ext in extensions
    }


def build_plan(comp_dir: Path) -> dict:
    system = load_toml(comp_dir / "SYSTEM.toml")
    sys_block = system.get("system", {})
    names = sys_block.get("extensions", [])
    if not names:
        raise Refusal(f"{comp_dir.name}: [system].extensions is empty -- nothing to compose")

    resolved = resolve_closure(list(names))
    check_disjoint(resolved)
    snapshots = check_snapshots(resolved)

    # THE TARGET IS THE DIRECTORY THE COMPOSITION LIVES IN, not a field.
    #
    # It used to be `[system.peer].language`, and the Makefile derived LANGUAGE back out of
    # the resolved plan so the two could not be passed separately -- a real hazard then,
    # because `make check COMPOSITION=py-content LANGUAGE=typescript` was a spellable
    # mismatch. Under target-major the pair is a PATH: `languages/rust/compositions/content`
    # either exists or it does not, and a mismatched (target, composition) has no filesystem
    # location. The derivation hack is deleted rather than moved.
    try:
        target = comp_dir.relative_to(ROOT / "languages").parts[0]
    except ValueError:
        raise Refusal(
            f"{comp_dir} is not under languages/<target>/compositions/ -- a composition "
            "lives inside the target it composes for"
        ) from None

    peer = sys_block.get("peer", {})
    if peer.get("language") not in (None, target):
        raise Refusal(
            f"{comp_dir.name}: [system.peer].language = {peer['language']!r} contradicts "
            f"its location under languages/{target}/. The path is the authority; drop the field."
        )

    profile = load_profile(target)
    faces = check_faces(sys_block, comp_dir.name, [item["name"] for item in resolved])

    installs = []
    for item in resolved:
        manifest = item["manifest"]
        cell = cell_dir(target, item["name"])
        if not cell.is_dir():
            raise Refusal(
                f"{item['name']} has no {target} port at {cell.relative_to(ROOT)} -- "
                "a composition names an (extension x target) cell that must exist"
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
        ext_faces = faces.get(item["name"], {})
        if surfaces.get("handler") and ext_faces.get("handler") == "not-installable":
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
        # `language` is kept as an alias of `target` for the drivers that read it. The two
        # are the same string by construction; `target` is the name that survives, because
        # the unit is a (language, runtime, packaging, toolchain) tuple and only one of
        # those four is a language -- see DESIGN-THE-SYSTEM-STRUCTURE §1.
        "target": target,
        "language": target,
        "composition_dir": str(comp_dir.relative_to(ROOT)),
        # THE PROFILE, RESOLVED. Every field here used to be restated wherever it executed.
        # A driver reads it out of the plan now, so there is one copy and the gate above
        # proves it exists.
        "profile": {
            "packaging": profile["language"]["packaging"],
            "compilation": profile["language"]["compilation"],
            "boundary": profile["language"]["boundary"],
            "image": profile["toolchain"]["image"],
            "host_entry": profile["gate"]["host_entry"],
            "oracle_bin": profile["gate"]["oracle_bin"],
            "startup_ticks": profile["gate"]["startup_ticks"],
            # The rust driver generated `edition = "2021"` into the composition host's
            # Cargo.toml while the profile declared the same value four lines from a
            # comment explaining that an edition skew "changes name resolution and closure
            # capture, and neither should differ between a peer and a module compiled into
            # the same binary". The fact whose purpose is *do not skew* was in two places
            # with nothing comparing them. Optional: only compiled targets have one.
            "edition": profile.get("toolchain", {}).get("edition"),
        },
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
    ap.add_argument("composition",
                    help="path to a languages/<target>/compositions/<name>/ directory")
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

    # Output lives under the target too, so `languages/rust/` is readable as one bundle
    # and `make clean` on a target touches nothing another target owns.
    out = (Path(args.out) if args.out
           else ROOT / "languages" / plan["target"] / "output" / plan["composition"] / "PLAN.json")
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
