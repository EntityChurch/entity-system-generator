"""The `python` arm's surface extractor. See the `typescript` sibling for why it lives here.

`__all__ = [...]`, not the first mention of `__all__` -- the module docstring discusses it,
and splitting on the token landed inside the prose. That defect cost a measurement pass:
the port parsed to zero names and the run reported it as drift.
"""

import re


class NoSurface(Exception):
    """The entry point does not declare a surface. A REFUSAL, never a verdict of zero."""


def extract(text: str) -> set[str]:
    match = re.search(r"^__all__\s*=\s*\[(.*?)\]", text, re.S | re.M)
    if not match:
        raise NoSurface("no `__all__` assignment found")
    return set(re.findall(r'"(\w+)"', match.group(1)))
