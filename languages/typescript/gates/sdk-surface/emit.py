#!/usr/bin/env python3
"""Read this target's `[sdk_surface] entry_point` from its profile, extract the public
names with the sibling `extract.py`, emit JSON. Shared shape; the per-target part is
`extract.py` and the per-target VALUE is in the profile (D17)."""

import json
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract as extractor  # noqa: E402


def main() -> int:
    target_dir, ext = Path(sys.argv[1]), sys.argv[2]
    with open(target_dir / "profile.toml", "rb") as fh:
        entry = tomllib.load(fh).get("sdk_surface", {}).get("entry_point")
    if not entry:
        print(f"REFUSING: {target_dir.name}/profile.toml declares no "
              "`[sdk_surface] entry_point`. The gate will not guess a filename: guessing "
              "is how a parser ends up pointed at `src/**`, reporting every internal "
              "symbol and erasing the §3.4 boundary.", file=sys.stderr)
        return 2
    path = target_dir / "extensions" / ext / entry
    if not path.exists():
        print(f"REFUSING: no public entry point at {path}", file=sys.stderr)
        return 2
    names = sorted(extractor.extract(path.read_text(encoding="utf-8")))
    # The zero-parse refusal lives HERE as well as in the neutral half, on purpose: this
    # is where the parse happened, so this is where the cause is known. It has fired for
    # real -- the python extractor once split on the wrong `__all__` and returned an empty
    # set, which the first run reported as "python exports nothing" rather than as a
    # broken parse.
    if not names:
        print(f"REFUSING: {path} parsed 0 public names. That is a broken extractor, not "
              "an empty surface.", file=sys.stderr)
        return 2
    print(json.dumps({"port": target_dir.name, "extension": ext,
                      "entry_point": entry, "names": names}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
