"""The `rust` arm's surface extractor. See the `typescript` sibling for why it lives here.

`pub use ...::{...}` re-exports plus direct `pub fn|struct|enum|const`. A name without
`pub` is not surface -- on this target the packaging boundary IS the crate boundary and
rustc enforces it (E0603), which is why this extractor can be this short.
"""

import re


def extract(text: str) -> set[str]:
    out: set[str] = set()
    for block in re.findall(r"pub use [\w:]+::\{([^}]*)\};", text, re.S):
        for item in block.split(","):
            item = item.strip()
            if re.match(r"^[A-Za-z_]\w*$", item):
                out.add(item)
    out |= set(re.findall(r"^pub (?:fn|struct|enum|const) (\w+)", text, re.M))
    return out
