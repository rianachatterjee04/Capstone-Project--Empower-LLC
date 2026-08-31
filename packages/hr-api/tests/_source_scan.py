"""Read a module's CODE, without its comments or docstrings.

WHY THIS KEEPS BEING NEEDED
Structural tests here assert that a module does not reference something --
appearance, evaluative praise, a banned import. The modules in question have
long docstrings explaining precisely why they refuse to do those things, and a
naive substring scan matches the explanation and fails.

That has now happened repeatedly, so the fix lives in one place. `tokenize`
knows what a string literal and a comment are; a regex does not.
"""
from __future__ import annotations

import io
import re
import tokenize


def code_only(source: str) -> str:
    """Strip comments and string literals, keeping executable code."""
    out: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        # Fall back to the raw source rather than silently scanning nothing:
        # an empty haystack would make every "must not contain" test pass.
        return source
    return " ".join(out)


def mentions(haystack: str, word: str) -> bool:
    """Whole-word match.

    Substring matching produced a false positive on `timeframe` for the banned
    word `frame`, which would have forced a real and correct identifier to be
    renamed to satisfy a test.
    """
    return re.search(rf"\b{re.escape(word)}\b", haystack, re.IGNORECASE) is not None
