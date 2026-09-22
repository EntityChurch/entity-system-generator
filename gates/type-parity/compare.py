#!/usr/bin/env python3
"""compare.py — do every port render the SAME type entities?

## Why this gate exists

`REVIEW-CYCLE-2` §4.2, routed to `entity-core-go` as **G-3**:

> Nothing anywhere checks HISTORY's type entities are RIGHT. Two of three ports
> hand-build the field maps -- the peers' own builders are private -- and a subtly wrong
> map produces a well-formed entity that hashes differently from the other ports', dedup
> stops for that type, all six checks stay green, and no error is raised anywhere.

The oracle's `history` category spends six checks on `client.TreeGet(path)` — it asserts
the type path **resolves**. It never looks at what is there. So a port that publishes six
correctly-named entities with a wrong field in one of them scores exactly the same as a
port that got them right, on every instrument that exists.

**And this is the largest transcribed-data block in the most expensive quadrant of the
tree.** `tools/scale-report.py`: the per-cell quadrant is ~96% of projected mass, and the
`types` role inside it is ~161 code lines per cell — **192,556 at 26 extensions x 46
targets**, six ports of one spec table today and 1,196 later. `DESIGN-THE-SYSTEM-
STRUCTURE` §1.2b's rule is that protocol-shaped things belong in `tools/` in one copy; a
spec's type table is the most protocol-shaped thing there is. This gate does not move it
— it makes the divergence visible so that moving it is a decision rather than a rewrite.

The consistency half is OURS (D16). We cannot make a conformance claim about type-entity
content — no upstream authority measures it, and N of our ports agreeing is N of our
ports agreeing (L18). We can make a **cross-port** claim, and `chunking-parity` is the
model this follows exactly.

## Two independent measurements, and their disagreement is itself a finding

Each arm reports, per type entity:

  hash    the PEER'S OWN content hash. `0x00 || SHA-256(ECF({type, data}))`. Computed by
          the peer's codec, not by us, and not by anything in this gate.
  data    OUR normalisation of the entity's data tree into canonical JSON.

The three ports hold that tree in three different in-memory shapes — a plain dict on
`python`, a `{kind, pairs}` tagged tree on `typescript`, a `Value` enum on `rust` — so
`data` has to pass through a normaliser, and **a normaliser that loses a distinction
reports agreement that is not there** (AP-8). The defence is that `hash` does not go
through it.

So the verdicts are not two views of one thing; they are two instruments, and this
compares them:

  hash AGREE + data AGREE      the ports render the same entity. The result we want.
  hash DIVERGE + data DIVERGE  a real divergence, and `data` says WHERE.
  hash DIVERGE + data AGREE    CONTRADICTION. Either the normaliser dropped the field
                               that differs, or the ports' codecs disagree on identical
                               input. Both are findings; this gate cannot say which.
  hash AGREE + data DIVERGE    CONTRADICTION. The normaliser is inventing a distinction
                               the codec does not see -- most likely map ordering.

**A contradiction is reported and exits non-zero.** It is the state where the instrument
knows it is unreliable, and reporting either half alone would be picking the answer.

Map keys are sorted during normalisation, deliberately: the codec re-sorts map keys
length-then-lex, so declaration order provably does not reach the bytes. That is the one
distinction dropped on purpose, and `hash` is the standing control on whether dropping it
was right.

## D15: refusals

  fewer than --min-ports arms          "they all agree" over one arm is not parity
  an arm reporting zero types          a probe that resolved nothing reads as agreement
  duplicate ports                      one arm ran twice
  arms reporting different extensions  a verdict over two different subjects

  ./gates/type-parity/compare.py --min-ports 3 output/type-parity/*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def canon(value) -> str:
    """A stable string for a normalised value, for equality and for display."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("reports", nargs="+", help="one JSON line per port")
    ap.add_argument("--min-ports", type=int, default=2,
                    help="refuse to report parity below this many arms")
    args = ap.parse_args()

    results = []
    for path in args.reports:
        text = Path(path).read_text(encoding="utf-8").strip()
        if not text:
            raise SystemExit(f"{path}: empty -- the probe produced no output. REFUSING.")
        results.append(json.loads(text.splitlines()[-1]))

    if len(results) < args.min_ports:
        raise SystemExit(
            f"compare: {len(results)} arm(s) reported, need at least {args.min_ports}. "
            "'They all agree' over fewer arms than that is not a parity result. REFUSING."
        )

    ports = [r["port"] for r in results]
    if len(set(ports)) != len(ports):
        raise SystemExit(f"compare: duplicate ports in {ports} -- one arm ran twice. REFUSING.")

    exts = {r["port"]: r["extension"] for r in results}
    if len(set(exts.values())) != 1:
        raise SystemExit(f"compare: the arms measured different extensions -- {exts}. "
                         "A parity verdict over two subjects is meaningless. REFUSING.")
    extension = next(iter(exts.values()))

    # The vacuity refusal, and it is the one that presents as success: an arm whose
    # import resolved but whose entities function returned nothing contributes an empty
    # type set, and an empty set agrees with every other empty set.
    empty = [r["port"] for r in results if not r.get("types")]
    if empty:
        raise SystemExit(
            f"compare: {', '.join(empty)} reported 0 type entities. An empty type set "
            "agrees with\nevery other empty type set, which is the most comfortable wrong "
            "answer here. REFUSING."
        )

    print(f"extension: {extension}   arms ({len(results)}): {', '.join(sorted(ports))}")

    # ── the type SET, before anything about contents ────────────────────────────
    sets = {r["port"]: {t["name"] for t in r["types"]} for r in results}
    union = sorted(set().union(*sets.values()))
    set_problems = []
    for name in union:
        missing = sorted(p for p in sets if name not in sets[p])
        if missing:
            set_problems.append((name, missing))

    counts = ", ".join(f"{p}={len(sets[p])}" for p in sorted(sets))
    print(f"type entities: {counts}   union={len(union)}\n")

    if set_problems:
        print("  TYPE SET DIVERGES")
        for name, missing in set_problems:
            print(f"    {name:44} absent from: {', '.join(missing)}")
        print()

    # ── per type: the two independent measurements ──────────────────────────────
    divergent_hash, divergent_data, contradictions = [], [], []

    for name in union:
        per_port = {}
        for r in results:
            for t in r["types"]:
                if t["name"] == name:
                    per_port[r["port"]] = t
        if len(per_port) < 2:
            continue

        hashes = {p: t["hash"] for p, t in per_port.items()}
        datas = {p: canon(t["data"]) for p, t in per_port.items()}
        hash_agree = len(set(hashes.values())) == 1
        data_agree = len(set(datas.values())) == 1

        if hash_agree and data_agree:
            print(f"  AGREE       {name:44} {next(iter(hashes.values()))[:16]}...")
            continue

        if hash_agree != data_agree:
            contradictions.append(name)
            which = ("hash AGREES, data DIVERGES -- the normaliser is inventing a "
                     "distinction the codec\n                does not see"
                     if hash_agree else
                     "hash DIVERGES, data AGREES -- the normaliser dropped the field that "
                     "differs,\n                or the codecs disagree on identical input")
            print(f"  CONTRADICT  {name:44}")
            print(f"                {which}")
        else:
            print(f"  DIVERGE     {name:44}")

        if not hash_agree:
            divergent_hash.append(name)
            for p in sorted(hashes):
                print(f"                hash {p:12} {hashes[p]}")
        if not data_agree:
            divergent_data.append(name)
            # Print the FIELD-LEVEL difference, not the whole tree. A verdict a reader
            # cannot act on is what turned "the emit face does not work" into a wrong row
            # in cycle 2 (AP-15) -- the number beside the verdict is the whole point.
            fieldsets = {p: set((t["data"].get("fields") or {}).keys())
                         for p, t in per_port.items()}
            allf = sorted(set().union(*fieldsets.values()))
            for f in allf:
                specs = {p: canon((per_port[p]["data"].get("fields") or {}).get(f))
                         for p in per_port}
                if len(set(specs.values())) == 1:
                    continue
                print(f"                field `{f}`:")
                for p in sorted(specs):
                    print(f"                  {p:12} {specs[p]}")

    print()
    if contradictions:
        print(f"TYPE PARITY: CONTRADICTION on {len(contradictions)} type(s): "
              f"{', '.join(contradictions)}")
        print("The two measurements in this gate disagree, so neither is reportable. The")
        print("normaliser and the codec cannot both be right; this gate cannot arbitrate.")
        return 1

    if set_problems or divergent_hash or divergent_data:
        print(f"TYPE PARITY: DIVERGENT — {len(set_problems)} type-set, "
              f"{len(divergent_hash)} hash, {len(divergent_data)} field-map")
        print("A type entity that hashes differently between ports is a silent cross-peer")
        print("DEDUP failure for that type. Every `type_*` oracle check stays green: they")
        print("assert the path resolves, not what is at it.")
        return 1

    print(f"TYPE PARITY: {len(results)} ports agree on all {len(union)} type entities, "
          f"by content hash AND field map.")
    print("Cohort-consistent, NOT independent convergence (L18): the ports were transcribed")
    print("from one snapshot of one spec by one team. What it does establish is that the")
    print("hand-built field maps -- which no oracle check reads -- have not drifted apart,")
    print("and that this gate's normaliser and the peers' codecs still agree with each other.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
