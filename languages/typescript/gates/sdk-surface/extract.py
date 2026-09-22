"""The `typescript` arm's surface extractor.

MOVED HERE 2026-09-07 from `tools/sdk-parity.py`, where it sat beside two siblings behind
a `{target: function}` dispatch. Three extractors in a neutral file is a 3-way branch; at
46 targets it is a 46-way branch and ~2,000 lines in the one file whose job is to be
finished. `DESIGN-THE-SYSTEM-STRUCTURE` §1.2b: a per-target PROCEDURE lives under
`languages/<target>/`. Parsing a language's export syntax is as per-target as `tsc` vs
`cargo`, and it belongs in the same place.

COMMENTS ARE STRIPPED BEFORE SPLITTING, and that is a defect this gate shipped with.
A re-export block is split on commas; a `// ...` line inside one has no comma after it,
so the comment and the NEXT NAME arrive as a single item, the item fails the identifier
match, and the name silently vanishes from the measured surface.

Found on HISTORY's second port, 2026-09-06: adding two explanatory comments inside
`index.ts`'s export block dropped `TRANSITION` and `HistoryTypes` from the count. The gate
then reported `TRANSITION` as python-only -- A DIVERGENCE THAT DOES NOT EXIST, caused by
the instrument. Seventh instrument in this repo, seventh defect found by running it; and
the direction is the dangerous one for a parity gate, because an under-reported surface
reads as drift and a real drift reads as agreement.
"""

import re


def extract(text: str) -> set[str]:
    out: set[str] = set()
    # `export type { ... } from` as well as `export { ... } from`. A type-only export is
    # erased at runtime but it IS public surface: a consumer imports it to type against.
    # Missing it reported four names as python-only that both ports export (2026-09-06).
    for block in re.findall(r"export (?:type )?\{([^}]*)\}\s*from", text, re.S):
        block = re.sub(r"//[^\n]*", "", block)               # line comments
        block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)  # block comments
        for item in block.split(","):
            item = item.strip()
            if re.match(r"^(type )?[A-Za-z_]\w*$", item):
                out.add(item.replace("type ", ""))
    out |= set(re.findall(r"^export (?:function|class|interface|const|type|enum) (\w+)", text, re.M))
    return out
