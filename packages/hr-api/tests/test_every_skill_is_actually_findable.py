"""
Every skill in the taxonomy can actually be found in a resume.

WHY THIS IS A TEST
The skills graph computes bench depth by scanning resume text for the 58 skills
in its taxonomy. Two of those skills could not be found by the scanner at all,
and one whole class of mention was silently dropped:

  * "fp&a" was in the taxonomy, but "&" was missing from the token pattern
    (r"[a-z0-9+/.#-]+"), so the scanner split it into "fp" and "a" and could
    never match it. A finance candidate listing FP&A contributed nothing.

  * "." IS in the token pattern -- deliberately, for next.js -- so a skill that
    ends a sentence keeps its full stop. "We use aws." tokenised to "aws." and
    matched nothing. Resumes are full of sentences.

Both failures are silent: they do not error, they under-report. The page still
renders, the bench just looks thinner than it is, and no one can tell from the
output that a skill was missed rather than absent.

A taxonomy entry that cannot be matched is not a feature with a gap, it is a
line of configuration that does nothing. So this test asserts the property for
EVERY skill, not for the two we happened to find -- a new entry with awkward
punctuation fails here instead of quietly never matching.
"""
from __future__ import annotations

import re

import pytest

from app.services import skills_graph_service as S

# The shapes a skill actually appears in inside a resume or job description.
CONTEXTS = [
    "{s}",
    "we use {s}.",
    "Experience: {s}.",
    "{s}, and other tools",
    "strong {s};",
    "({s})",
    "proficient in {s}",
]


@pytest.mark.parametrize("skill", sorted(S._ALL_SKILLS))
def test_skill_is_findable_in_every_ordinary_context(skill):
    for ctx in CONTEXTS:
        text = ctx.format(s=skill)
        found = S._extract_skills_from_text(text)
        assert skill in found, (
            f"{skill!r} is in the taxonomy but the scanner cannot find it in "
            f"{text!r} (found {sorted(found)}). It will never contribute to "
            f"supply or demand, so the bench looks thinner than it is and the "
            f"taxonomy entry is dead configuration."
        )


def test_the_scanner_does_not_invent_skills():
    """CONTROL for the trimming. Widening what counts as a match must not make
    ordinary prose look like a skill inventory."""
    prose = (
        "The quick brown fox jumped over the lazy dog. She managed a team of "
        "twelve and reported to the board. References available on request."
    )
    found = S._extract_skills_from_text(prose)
    assert found == set(), f"invented skills from ordinary prose: {sorted(found)}"


def test_empty_and_missing_text_find_nothing():
    assert S._extract_skills_from_text("") == set()
    assert S._extract_skills_from_text(None) == set()  # type: ignore[arg-type]


def test_the_old_token_pattern_really_did_miss_these(monkeypatch):
    """MUTATION CONTROL. Put the original pattern back and confirm the property
    above fails -- otherwise this test would pass on the broken code too and
    prove nothing."""
    monkeypatch.setattr(S, "_TOKEN_PATTERN", re.compile(r"[a-z0-9+/.#-]+"))
    monkeypatch.setattr(S, "_EDGE_PUNCTUATION", "")

    missed = [
        skill
        for skill in sorted(S._ALL_SKILLS)
        for ctx in CONTEXTS
        if skill not in S._extract_skills_from_text(ctx.format(s=skill))
    ]
    assert missed, (
        "the original token pattern no longer misses anything, so this guard is "
        "not measuring the defect it was written for"
    )
    assert "fp&a" in missed, f"expected fp&a to be unmatchable under the old pattern; missed={sorted(set(missed))}"
    assert "aws" in missed, "expected a sentence-final skill to be missed under the old pattern"
