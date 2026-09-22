#!/usr/bin/env python3
"""compare.py — diff the chunking-parity probe outputs across ports.

**Why this gate exists.** `EXTENSION-CONTENT` §3.7 classifies §3.2 and §3.6 as
**Conformance** algorithms: two implementations that follow them produce byte-identical
chunk boundaries for the same input. **Divergence does not fail loudly** — every blob
still reassembles correctly, and the peers simply stop deduplicating with each other.
There is no error, no status code, and no check anywhere that would notice.

**And nothing upstream measures it.** `validate-peer`'s `content` category is 13 checks
and not one of them chunks anything (read at `ed9b547`); §3.6.5's cross-impl vectors are
named in the spec as a Stage-4 byproduct that does not exist yet. So this is the first
instrument in the ecosystem that puts one corpus through more than one transcription of
FastCDC and compares the bytes.

**What a green result is and is not.** It is three of OUR transcriptions agreeing, from
one reading of one snapshot, in a shared generation lineage — cohort-consistent, not
independent convergence (L18). It is worth having anyway, for one specific reason: the
three were transcribed from the pseudocode separately rather than translated from each
other, and §3.6.3's inner loop has a different arithmetic failure mode in each language.
A translation would have agreed by construction.

Three levels, checked in order, because they fail differently:

  boundary_count   coarse. A mismatch here is a gross error -- a wrong mask, a wrong
                   min_size, a degenerate stream.
  boundary_digest  the offsets. A count can match while the cuts differ.
  blob_hash        the §2.1 entity. This is the DEDUP IDENTITY. It can differ even when
                   the boundaries agree -- a wrong `chunking` id, a wrong `chunk_size`,
                   a field-map difference -- and that failure is invisible to the two
                   above.

  ./gates/chunking-parity/compare.py output/chunking-parity/*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: Compared in this order. Each is a strictly finer question than the one before it.
FIELDS = ("boundary_count", "boundary_digest", "blob_hash", "chunk_count",
          "first_chunk_hash", "last_chunk_hash")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("reports", nargs="+", help="one JSON line per port")
    ap.add_argument("--min-ports", type=int, default=2,
                    help="refuse to report parity below this many ports")
    args = ap.parse_args()

    results = []
    for path in args.reports:
        text = Path(path).read_text(encoding="utf-8").strip()
        if not text:
            raise SystemExit(f"{path}: empty -- the probe produced no output. REFUSING.")
        results.append(json.loads(text.splitlines()[-1]))

    # D15 / the diff-arms rule: an empty or one-sided result set is never reported as a
    # clean verdict. "All ports agree" over one port is true and worthless, and it is the
    # most comfortable wrong answer available here -- a probe that failed to build would
    # otherwise leave two arms agreeing and read as green.
    if len(results) < args.min_ports:
        raise SystemExit(
            f"compare: {len(results)} port(s) reported, need at least {args.min_ports}. "
            "'They all agree' over fewer arms than that is not a parity result. REFUSING."
        )

    ports = [r["port"] for r in results]
    if len(set(ports)) != len(ports):
        raise SystemExit(f"compare: duplicate ports in {ports} -- one arm ran twice. REFUSING.")

    # The corpus must be the same bytes for every arm, or nothing below means anything.
    for field in ("corpus_bytes", "target_size"):
        values = {r["port"]: r[field] for r in results}
        if len(set(values.values())) != 1:
            raise SystemExit(
                f"compare: the arms did not read the same input -- {field} = {values}. "
                "A parity verdict over different corpora is meaningless. REFUSING."
            )

    print(f"corpus: {results[0]['corpus_bytes']} bytes, "
          f"target_size {results[0]['target_size']}, ports: {', '.join(sorted(ports))}\n")

    divergent = []
    for field in FIELDS:
        values = {r["port"]: r[field] for r in results}
        distinct = set(values.values())
        if len(distinct) == 1:
            shown = str(next(iter(distinct)))
            shown = shown if len(shown) <= 20 else shown[:16] + "..."
            print(f"  AGREE     {field:18} {shown}")
        else:
            divergent.append(field)
            print(f"  DIVERGE   {field:18}")
            for port in sorted(values):
                print(f"              {port:12} {values[port]}")

    print()
    if divergent:
        print(f"CHUNKING PARITY: DIVERGENT on {len(divergent)} field(s): {', '.join(divergent)}")
        print("§3.7 makes §3.2/§3.6 Conformance algorithms. A divergence here is a")
        print("cross-peer DEDUPLICATION failure that raises no error anywhere.")
        return 1

    print(f"CHUNKING PARITY: {len(results)} ports agree on all {len(FIELDS)} fields.")
    print("Cohort-consistent, NOT independent convergence (L18): three transcriptions of")
    print("one snapshot in one generation lineage. What it does establish is that §3.6.3's")
    print("inner loop was got right three times in three different arithmetic regimes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
