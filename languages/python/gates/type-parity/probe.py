#!/usr/bin/env python3
"""gates/type-parity/probe.py — the `python` arm.

Import the staged package BY NAME (through the packaging boundary, not out of the source
tree), call its `<ext>_type_entities()`, and print one JSON line: for each type entity,
the peer's own content hash and a normalisation of its data tree.

`python` holds the entity data as plain dicts already, so this arm's normaliser is the
thinnest of the three. That is exactly why it is written to REFUSE on an unexpected type
rather than to fall through to `str()`: the cheap path here is the one that would quietly
stringify something the other two arms render structurally, and produce a divergence that
is the instrument's rather than the ports'.
"""

from __future__ import annotations

import importlib
import json
import sys

#: DERIVED, NOT TABULATED, and the table it replaced is why.
#:
#: This arm shipped with `SUBJECTS = {"content": (...), "history": (...)}` -- two entries,
#: which reads as configuration. `tools/check-glue.py` counts what it becomes: one entry per
#: extension in one arm per target is **E x T = 1,196 hand-maintained rows** at the full
#: corpus, in files whose whole purpose is to be extension-AGNOSTIC.
#:
#: The mapping was never a decision. It is this target's naming convention applied to a
#: slug, and the convention is already uniform across every cell this target has. So the
#: arm derives it and REFUSES if the derivation misses -- which is strictly better than a
#: table, because a table cannot notice that a cell broke the convention.
MODULE = "entity_{ext}.types"
ENTITIES_FN = "{ext}_type_entities"


def normalise(value):
    """The port's data tree -> canonical JSON. Map keys sorted; see compare.py."""
    if isinstance(value, dict):
        return {str(k): normalise(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [normalise(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes__": bytes(value).hex()}
    if isinstance(value, bool) or value is None or isinstance(value, (int, float, str)):
        return value
    raise TypeError(
        f"REFUSING: unhandled value type {type(value).__name__!r} in a type entity. "
        "Falling through to str() here would render structurally on the other two arms "
        "and textually on this one, which is a divergence this gate would report as the "
        "PORTS' rather than its own."
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: probe.py <extension-slug>", file=sys.stderr)
        return 2
    ext = sys.argv[1]
    mod_name, fn_name = MODULE.format(ext=ext), ENTITIES_FN.format(ext=ext)

    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:
        print(f"REFUSING: cannot import `{mod_name}` for extension `{ext}` ({exc}). The "
              "arm derives the module name from this target's naming convention; a cell "
              "that breaks the convention is a finding, not a missing table entry.",
              file=sys.stderr)
        return 2
    fn = getattr(mod, fn_name, None)
    if fn is None:
        print(f"REFUSING: `{mod_name}` has no `{fn_name}`. Every cell on this target "
              "publishes its materialised type entities under that name; one that does "
              "not is drift the `sdk-surface` gate should have caught.", file=sys.stderr)
        return 2
    entities = fn()

    types = []
    for name, entity in entities:
        types.append({
            "name": name,
            "hash": bytes(entity.hash).hex(),
            "data": normalise(entity.data),
        })

    print(json.dumps({"port": "python", "extension": ext, "types": types}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
