"""The `python` arm's surface extractor. See the `typescript` sibling for why it lives here.

TWO DEFECTS SO FAR, BOTH FOUND BY RUNNING IT, AND BOTH IN THE SAME SIX LINES.

 1. **`__all__ = [...]`, not the first mention of `__all__`.** The module docstring discusses
    the name, and splitting on the token landed inside the prose. That defect cost a
    measurement pass: the port parsed to zero names and the run reported it as drift.

 2. **A `]` INSIDE A COMMENT TRUNCATED THE LIST** (2026-09-12, COMPUTE's port). The regex
    was ``^__all__\\s*=\\s*\\[(.*?)\\]`` — non-greedy, so it stopped at the FIRST `]` in the
    region. ``entity_compute/__init__.py``'s ``__all__`` carries an explanatory comment
    containing the literal ``[sdk_surface]``, so the capture ended there and the extractor
    returned **3 names of 75**.

    The direction is the dangerous one for a parity gate: an under-reported surface reads as
    DRIFT. The neutral half would have reported 75 names as typescript-only — seventy-five
    fabricated divergences on the second port's first run — and a false red costs the
    instrument (AP-4). The zero-parse refusal in `emit.py` could not catch it, because three
    names is not zero: **a vacuity refusal bounds a parse that returns NOTHING and does
    nothing about one that returns the boring third of it.** That is D15's clause-2 gap in
    its own family again (AP-28), now in an extractor rather than in a corpus assertion.

    And the `typescript` sibling had ALREADY FIXED THIS, for the same cause, six days
    earlier: *"COMMENTS ARE STRIPPED BEFORE SPLITTING, and that is a defect this gate
    shipped with … adding two explanatory comments inside `index.ts`'s export block dropped
    `TRANSITION` and `HistoryTypes` from the count."* One arm learned it; the arm one
    directory over did not. AP-10's shape on a gate arm rather than on a build driver — a
    correction lands in the file it was found in and nowhere else, because the arms are
    per-target by design and nothing compares them.

The fix is a BALANCED SCAN rather than a longer regex, because the next thing inside that
list will be a nested container or a `]` inside a string literal, and a regex that handles
comments still mis-parses those. :func:`_balanced_block` tracks string state and bracket
depth, which is the property — *find the matching bracket* — instead of another pattern that
happens to work on today's file (D15: a corpus assertion names the PROPERTY, not a count).
"""

import re


class NoSurface(Exception):
    """The entry point does not declare a surface. A REFUSAL, never a verdict of zero."""


def _balanced_block(text: str, open_index: int) -> str:
    """The text between the bracket at ``open_index`` and its match, exclusive.

    Tracks single/double quotes (including triple quotes) and `#` comments so a bracket
    inside a string or a comment does not close the block. Raises :class:`NoSurface` on an
    unterminated list — which is a syntax error in the source, and reporting it as a refusal
    beats returning a truncated set.
    """
    depth = 0
    i = open_index
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if ch in ("'", '"'):
            quote = text[i:i + 3] if text[i:i + 3] in ("'''", '"""') else ch
            i += len(quote)
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text.startswith(quote, i):
                    i += len(quote)
                    break
                i += 1
            continue
        if ch in "[({":
            depth += 1
        elif ch in "])}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:i]
        i += 1
    raise NoSurface("`__all__` list is not terminated")


def extract(text: str) -> set[str]:
    match = re.search(r"^__all__\s*=\s*\[", text, re.M)
    if not match:
        raise NoSurface("no `__all__` assignment found")
    body = _balanced_block(text, match.end() - 1)
    # Comments are skipped by the scan for BRACKET purposes but are still in the returned
    # slice, and a comment can legitimately quote a name (`# "Entity" is not surface`). Strip
    # them before harvesting string literals, exactly as the `typescript` arm does.
    body = re.sub(r"#[^\n]*", "", body)
    return set(re.findall(r'"(\w+)"', body))
