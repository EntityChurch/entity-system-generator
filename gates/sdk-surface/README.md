# `sdk-surface` — the neutral half is `tools/sdk-parity.py`

**This directory holds no code, and that is where the code went, not a gap.** The SDK surface gate
(D16) compares every port's public names against `[sdk_surface]` in
`extension-contracts/<ext>/EXTENSION.toml`. Its two halves:

| half | lives at | what it does |
|---|---|---|
| neutral | `tools/sdk-parity.py` | reads the declaration, runs every arm, compares, refuses below two ports |
| per target | `languages/<t>/gates/sdk-surface/{run,extract.py}` | reads that port's entry point and prints its public names as JSON |

The neutral half moved to `tools/` in the D20 refactor (the glue does not enumerate its members), so
the per-target arms outlived the directory `tools/check-structure.py` expects to mirror them.

## Why this file exists

`make structure` requires `gates/<unit>/` for every `languages/<t>/gates/<unit>/`. From 2026-09-07
until 2026-09-12 that requirement was satisfied by a `gates/sdk-surface/` directory **that git never
tracked**: `git log --all -- gates/sdk-surface` prints nothing. It existed on one machine, the gate
read `is_dir()` and passed, and when the build environment was wiped the directory went with it and
the gate went red on three targets. What the directory held is not recoverable.

This README is the tracked neutral half, the same shape `gates/host-seam/` and
`gates/seed-policy/` already use. `tools/check-structure.py` now also requires a neutral half to
contain at least one file git tracks, so an untracked directory can no longer stand in for one.
