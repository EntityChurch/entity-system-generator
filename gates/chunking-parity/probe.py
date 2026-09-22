#!/usr/bin/env python3
"""gates/chunking-parity/probe.py — the `python` arm of the chunking-parity gate.

The `typescript` twin, and deliberately the same shape: read the shared corpus, run
§3.6 FastCDC/NC2 through THE STAGED PACKAGE imported by name, print one JSON line.

Three numbers, each answering a different question:
  boundary_count   -- did the three ports cut the same NUMBER of chunks?
  boundary_digest  -- did they cut at the same OFFSETS? (a count can match by accident)
  blob_hash        -- do the resulting §2.1 entities hash identically? This is the one
                      that matters: it is the deduplication identity, and two peers that
                      disagree here silently fail to dedup with each other while every
                      blob still reassembles.
"""

from __future__ import annotations

import hashlib
import json
import sys

from entity_content import cdc_boundaries, create_blob_cdc


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: probe.py <corpus-path> <target-size>", file=sys.stderr)
        return 2
    corpus_path, target_size = sys.argv[1], int(sys.argv[2])

    with open(corpus_path, "rb") as fh:
        data = fh.read()

    bounds = cdc_boundaries(data, target_size)
    blob = create_blob_cdc(data, target_size)

    print(json.dumps({
        "port": "python",
        "corpus_bytes": len(data),
        "target_size": target_size,
        "boundary_count": len(bounds),
        "boundary_digest": hashlib.sha256(",".join(map(str, bounds)).encode()).hexdigest(),
        "blob_hash": bytes(blob.blob.hash).hex(),
        "chunk_count": len(blob.chunks),
        "first_chunk_hash": bytes(blob.chunks[0].hash).hex(),
        "last_chunk_hash": bytes(blob.chunks[-1].hash).hex(),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
