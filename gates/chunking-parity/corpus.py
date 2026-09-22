#!/usr/bin/env python3
"""corpus.py — write the deterministic corpus the three chunking probes read.

**Language-neutral on purpose.** If each port generated its own corpus from its own
PRNG, a boundary disagreement would be ambiguous: the chunkers might agree and the
generators differ. One file, three readers, and the only variable left is §3.6.

**The generator is xorshift32 and NOT an LCG, and that is AP-3.** The `typescript`
edit-stability test was first written against a textbook LCG
(`x = (x * 1103515245 + 12345) >>> 0`), whose low bits never satisfied FastCDC's
boundary mask. Every chunk ran to the forced `max_size`, the algorithm silently
degenerated to fixed-size chunking at 2x the target, and the test failed against a
CORRECT implementation. The stream had 256 distinct byte values and no short period, so
every cheap "is this random" check passed.

So this file does two things, and the second is the one that matters:

1. writes the corpus deterministically from a documented 32-bit PRNG, and
2. **asserts the corpus can exercise the branch under test** before writing it —
   the boundary mask must be satisfiable often enough that content-defined chunking is
   actually happening. A corpus that cannot is refused here rather than producing three
   identical wrong answers downstream. (D15's corpus-assertion clause.)

  ./gates/chunking-parity/corpus.py --out output/chunking-parity/corpus.bin
"""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

#: Fixed. A corpus whose bytes depend on the clock would make a parity result
#: unreproducible, and the whole point is that three ports read the SAME bytes.
SEED = 0x5EED_C0DE
LENGTH = 512 * 1024
#: 4 KiB rather than the §10.1 default of 1 MiB: at 1 MiB a 512 KiB corpus is one chunk
#: and the comparison is vacuous. The ALGORITHM is identical at any target size -- every
#: §3.6.2 parameter derives from it -- so a smaller target exercises the same code with
#: more boundaries. Stated because "we used a non-default constant" always deserves a why.
TARGET_SIZE = 4096


def xorshift32(seed: int, length: int) -> bytes:
    """Marsaglia's xorshift32. Low bits are as well-mixed as the high bits, which is
    exactly the property the LCG lacked."""
    x = seed & 0xFFFF_FFFF
    out = bytearray()
    while len(out) < length:
        x ^= (x << 13) & 0xFFFF_FFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFF_FFFF
        out += x.to_bytes(4, "little")
    return bytes(out[:length])


def gear_table() -> list[int]:
    """§3.6.1, re-derived here rather than imported from any port. A corpus assertion
    that used a port's own gear table would inherit that port's defect."""
    return [
        int.from_bytes(hashlib.sha256(b"FastCDC" + bytes([i])).digest()[:8], "little")
        for i in range(256)
    ]


def boundaries(data: bytes, target: int) -> list[int]:
    """§3.6.3, transcribed a fourth time. Deliberately: this is the corpus check, and
    it must not be able to agree with a port by sharing code with it."""
    gear = gear_table()
    bits = int(math.floor(math.log2(target)))
    nc, u64 = 2, (1 << 64) - 1
    min_size, max_size = target // 4, target * 2
    mask_s, mask_l = (1 << (bits + nc)) - 1, (1 << (bits - nc)) - 1

    out, offset = [], 0
    while offset < len(data):
        if len(data) - offset <= min_size:
            out.append(len(data))
            break
        fp = 0
        i = offset + min_size
        end = None
        limit1 = min(offset + target, len(data))
        while i < limit1:
            fp = ((fp << 1) + gear[data[i]]) & u64
            if fp & mask_s == 0:
                end = i + 1
                break
            i += 1
        if end is None:
            limit2 = min(offset + max_size, len(data))
            while i < limit2:
                fp = ((fp << 1) + gear[data[i]]) & u64
                if fp & mask_l == 0:
                    end = i + 1
                    break
                i += 1
            if end is None:
                end = i
        out.append(end)
        offset = end
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="output/chunking-parity/corpus.bin")
    args = ap.parse_args()

    data = xorshift32(SEED, LENGTH)

    # ── the corpus assertion (D15) ──────────────────────────────────────────
    bounds = boundaries(data, TARGET_SIZE)
    forced = sum(1 for a, b in zip(bounds, bounds[1:]) if b - a == TARGET_SIZE * 2)
    if len(bounds) < 32:
        raise SystemExit(
            f"corpus: only {len(bounds)} boundaries -- too few for a parity comparison "
            "to mean anything. REFUSING to write it."
        )
    if forced * 2 >= len(bounds):
        raise SystemExit(
            f"corpus: {forced} of {len(bounds)} chunks hit the forced max_size boundary. "
            "The mask is not being satisfied, FastCDC has degenerated to fixed-size "
            "chunking, and three ports would agree on an answer that measures nothing "
            "(AP-3). REFUSING to write it."
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"corpus: {len(data)} bytes -> {out}")
    print(f"corpus: sha256 {hashlib.sha256(data).hexdigest()}")
    print(f"corpus: target_size {TARGET_SIZE}, {len(bounds)} boundaries, "
          f"{forced} forced ({forced * 100 // len(bounds)}%)")
    print(f"corpus: boundary-list sha256 "
          f"{hashlib.sha256(','.join(map(str, bounds)).encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
