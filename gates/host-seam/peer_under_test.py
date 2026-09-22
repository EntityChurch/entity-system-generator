"""Shared peer resolution for this gate's Python probes — the analogue of
``peer-under-test.mjs``, and it is deliberately NOT a translation of it.

The two honesty properties are the same; the mechanisms that deliver them are not,
and the difference is itself the finding.

1. RESOLVE THE PEER THE WAY A CONSUMER DOES. In `typescript` that means reading
   ``exports["."]`` out of the peer's ``package.json``: the manifest names one entry
   point and the runtime enforces it. **Python has no enforced packaging boundary.**
   The closest declared thing is ``[tool.hatch.build.targets.wheel] packages`` in
   ``pyproject.toml`` — a statement of what the wheel *ships*, with no runtime effect.
   So we read that list and stage a copy containing ONLY what it names, then import
   from the staging directory. An import that succeeds there is an import that would
   succeed against the installed wheel; an import that reaches anything outside the
   declared package set fails here and would fail for a consumer.

   This is the strongest form available offline. It does **not** exercise a wheel
   build: `hatchling` is not in the toolchain image and the image runs
   ``--network=none``, so `pip install .` cannot run. Reported as such — the
   packaging-boundary claim is "declared-manifest staging", never "installed wheel".

2. REFUSE TO MEASURE A STALE BUILD. Python has no build artifact, so `dist/`-staleness
   has no analogue — but ``__pycache__`` is the same failure in a smaller shape, and a
   probe that imports a tree with stale bytecode next to edited source is a gate on the
   past exactly as keystone's was. The staging copy excludes ``__pycache__`` and runs
   with ``sys.dont_write_bytecode``, so what is measured is the source on disk.

Exit 2 means the probe could not run. **Exit 2 is not a verdict about the peer.**
"""

from __future__ import annotations

import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent

DEFAULT_PEER_ROOT = (
    HERE / ".." / ".." / ".." / "entity-core-keystone" / "protocol-generator" / "python"
).resolve()


@dataclass(frozen=True)
class ResolvedPeer:
    peer_root: Path
    staged_root: Path
    packages: list[str]
    how_resolved: str
    dist_name: str
    version: str


def arg_value(flag: str, fallback: str | None = None) -> str | None:
    argv = sys.argv
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return fallback


def _die(msg: str) -> "None":
    print(f"unknown: {msg}", file=sys.stderr)
    raise SystemExit(2)


def load_peer_under_test(staging: Path) -> ResolvedPeer:
    """Stage the declared wheel contents and put them on ``sys.path``.

    Returns before importing anything — the caller imports, so an ImportError is
    attributable to the probe's own import line rather than to this helper.
    """
    peer_root = Path(arg_value("--peer-root", str(DEFAULT_PEER_ROOT))).resolve()

    manifest_path = peer_root / "pyproject.toml"
    try:
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as e:
        _die(f"no pyproject.toml under {peer_root} — {e}")

    project = manifest.get("project", {})
    wheel = (
        manifest.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
    )
    packages = wheel.get("packages")
    if not isinstance(packages, list) or not packages:
        _die(
            "pyproject.toml declares no [tool.hatch.build.targets.wheel] packages — "
            "that is a real packaging failure, not a probe defect"
        )

    staging.mkdir(parents=True, exist_ok=True)
    for rel in packages:
        src = peer_root / rel
        if not src.is_dir():
            _die(f"declared wheel package {rel!r} does not exist under {peer_root}")
        shutil.copytree(
            src,
            staging / Path(rel).name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(staging))

    return ResolvedPeer(
        peer_root=peer_root,
        staged_root=staging,
        packages=list(packages),
        how_resolved=(
            "pyproject [tool.hatch.build.targets.wheel] packages -> "
            f"{', '.join(packages)} staged (wheel build NOT exercised: "
            "hatchling absent, image is --network=none)"
        ),
        dist_name=str(project.get("name", "?")),
        version=str(project.get("version", "?")),
    )
