"""
No candidate is described using another candidate's life.

WHY THIS IS A TEST
A Senior Accountant's interview page showed the summary "5 years building async
Python backends" and the skills python / fastapi / postgres, above an AI MATCH
of 78. The prep page had hard-coded one engineer's profile as literals and
rendered it for every interview, and it POSTed those same invented strings to
the plan and question generators — so the AI output a buyer judges us on was
derived from a profile belonging to nobody.

The literals are gone. This test exists so their absence is a property of the
system rather than a fact about one commit.

WHY THIS CLASS IS WORSE THAN A 500
A crash is obviously broken. A polished page describing the wrong person is
confidently wrong, and a buyer reads it as what our product believes. It is the
highest-risk failure we have: everything looks like it is working.

WHAT IS ASSERTED
Three candidates whose backgrounds cannot overlap — an accountant, a CDL
driver, a backend engineer — are driven through the real generators, and no
vocabulary from one appears in another's plan, questions or follow-ups. The
mutation control below deliberately hands one candidate another's summary and
requires the assertions to fail; without it, a generator that ignored candidate
context entirely would pass every check here.
"""
from __future__ import annotations

import pytest

from app.interview import claims as C
from app.services import interview_copilot_service as S

ORG = "11111111-1111-1111-1111-111111111111"
OTHER_ORG = "99999999-9999-9999-9999-999999999999"


# --- three lives that cannot be confused for one another ---------------------

ACCOUNTANT = {
    "name": "Dana Whitfield",
    "job": "Senior Accountant",
    "summary": (
        "Eight years in corporate accounting. Owns the monthly close, prepares "
        "balance sheet reconciliations and accrual schedules, supports the "
        "external audit, and investigates budget variances in NetSuite."
    ),
    "skills": ["reconciliations", "accruals", "close", "gaap", "netsuite"],
}

DRIVER = {
    "name": "Marcus Delgado",
    "job": "CDL Driver — Regional Reefer",
    "summary": (
        "Six years OTR and regional on a Kenworth T680 pulling reefer. Class A "
        "CDL, clean MVR, tanker endorsement. Handles dispatch communication, "
        "DOT inspections and detention at receivers."
    ),
    "skills": ["reefer", "otr", "cdl", "dot", "dispatch"],
}

ENGINEER = {
    "name": "Ada Iwuchukwu",
    "job": "Senior Platform Engineer",
    "summary": (
        "Five years building async Python backends. Reduced settlement failures "
        "by 40% during the ledger migration. Works in FastAPI and Postgres."
    ),
    "skills": ["python", "fastapi", "postgres", "asyncio"],
}

PERSONAS = [ACCOUNTANT, DRIVER, ENGINEER]

# Words that belong to exactly one of these lives. If one shows up in another's
# material, something carried context across.
VOCABULARY = {
    "accountant": ["reconciliation", "reconciliations", "accrual", "accruals",
                   "gaap", "netsuite", "close process", "balance sheet"],
    "driver": ["reefer", "otr", "cdl", "kenworth", "dot inspection", "detention",
               "dispatch", "mvr"],
    "engineer": ["python", "fastapi", "postgres", "asyncio", "async python",
                 "backend"],
}

OWNER = {"Senior Accountant": "accountant",
         "CDL Driver — Regional Reefer": "driver",
         "Senior Platform Engineer": "engineer"}


def _material(persona: dict, *, summary: str | None = None,
              skills: list[str] | None = None) -> str:
    """Everything the product would show or ask, for one candidate."""
    plan = S.generate_interview_plan(
        interview_type="onsite",
        job_title=persona["job"],
        job_description="",
        candidate_summary=summary if summary is not None else persona["summary"],
        extracted_skills=skills if skills is not None else persona["skills"],
        skill_gaps=[],
    )
    iv = S.create_interview(
        org_id=ORG,
        candidate_name=persona["name"],
        candidate_id=None,
        job_title=persona["job"],
        job_id=None,
        interview_type="onsite",
    )
    questions = S.generate_candidate_specific_questions(
        interview_id=iv.id,
        interview_type="onsite",
        job_title=persona["job"],
        candidate_summary=summary if summary is not None else persona["summary"],
        skill_gaps=[],
    )
    parts: list[str] = []
    for value in plan.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts += [str(v) for v in value]
    parts += [q.text for q in questions]
    return " ".join(parts).lower()


def _foreign_words(text: str, own: str) -> list[str]:
    """Vocabulary in `text` belonging to a life that is not `own`."""
    found = []
    for group, words in VOCABULARY.items():
        if group == own:
            continue
        found += [w for w in words if w in text]
    return sorted(set(found))


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p["job"])
def test_no_candidates_material_borrows_another_life(persona):
    own = OWNER[persona["job"]]
    text = _material(persona)
    foreign = _foreign_words(text, own)
    assert foreign == [], (
        f"{persona['name']} ({persona['job']}) was given material containing "
        f"{foreign} — vocabulary that belongs to a different candidate's "
        f"background. A page describing the wrong person is worse than one that "
        f"fails to load."
    )


def test_the_accountant_is_never_given_software_experience():
    """The specific defect, named. This is what was on screen."""
    text = _material(ACCOUNTANT)
    for claim in ("async python", "fastapi", "postgres", "5 years building"):
        assert claim not in text, (
            f"a Senior Accountant's interview material contains {claim!r}"
        )


def test_generating_for_one_candidate_does_not_alter_another():
    """CROSS-INTERVIEW STATE. interview_copilot_service keeps interviews in
    process memory, so a leak between them is a live possibility rather than a
    theoretical one."""
    accountant_before = _material(ACCOUNTANT)
    _material(ENGINEER)
    _material(DRIVER)
    accountant_after = _material(ACCOUNTANT)
    assert accountant_before == accountant_after, (
        "the accountant's material changed after interviews were generated for "
        "an engineer and a driver — state is carrying between interviews"
    )


def test_questions_stay_with_their_own_interview():
    """Each interview's stored questions belong to it alone."""
    ivs = {}
    for persona in PERSONAS:
        iv = S.create_interview(
            org_id=ORG, candidate_name=persona["name"], candidate_id=None,
            job_title=persona["job"], job_id=None, interview_type="onsite",
        )
        S.generate_candidate_specific_questions(
            interview_id=iv.id, interview_type="onsite",
            job_title=persona["job"], candidate_summary=persona["summary"],
        )
        ivs[persona["job"]] = iv.id

    for job, iv_id in ivs.items():
        own = OWNER[job]
        text = " ".join(q.text for q in S.list_questions(iv_id)).lower()
        foreign = _foreign_words(text, own)
        assert foreign == [], f"{job}'s stored questions contain {foreign}"


def test_an_interview_is_not_visible_to_another_tenant():
    """CROSS-TENANT. The store is keyed by org; prove the key is load-bearing."""
    iv = S.create_interview(
        org_id=ORG, candidate_name=ACCOUNTANT["name"], candidate_id=None,
        job_title=ACCOUNTANT["job"], job_id=None, interview_type="onsite",
    )
    assert S.get_interview(ORG, iv.id) is not None, (
        "positive control failed: the owner cannot read their own interview, so "
        "the negative below would pass for the wrong reason"
    )
    assert S.get_interview(OTHER_ORG, iv.id) is None, (
        "another organisation can read this interview by id"
    )
    assert iv.id not in {i.id for i in S.list_interviews(OTHER_ORG)}


# --- the control ------------------------------------------------------------

def test_swapping_the_candidate_context_is_detected():
    """MUTATION CONTROL.

    Hand the accountant the engineer's summary and skills — exactly the defect
    that was on screen — and require the check above to fail. Without this, a
    generator that ignored candidate context entirely would pass every
    assertion in this file while telling a buyer nothing true.
    """
    contaminated = _material(
        ACCOUNTANT,
        summary=ENGINEER["summary"],
        skills=ENGINEER["skills"],
    )
    foreign = _foreign_words(contaminated, "accountant")
    assert foreign, (
        "the accountant was given the engineer's summary and skills and NOTHING "
        "in the generated material reflects it. Either the generators ignore "
        "candidate context entirely — in which case the checks above prove "
        "nothing — or this detector cannot see contamination."
    )


# --- the claims layer -------------------------------------------------------
#
# Claims are the ground truth everything downstream questions from, so this is
# the layer where a wrong candidate does the most damage: a person asked about
# words they never wrote. Every claim is a SPAN, so the extractor cannot invent
# one -- and verify_spans() re-reads the source to confirm the span still holds
# the excerpt it says it does.

RESUMES = {
    "accountant": (
        "Dana Whitfield. Eight years in corporate accounting. Owned the monthly "
        "close and reduced close time by 30% over 2 years. Prepared balance "
        "sheet reconciliations and accrual schedules in NetSuite. Managed a "
        "team of 4 staff accountants."
    ),
    "driver": (
        "Marcus Delgado. Six years OTR and regional on a Kenworth T680 pulling "
        "reefer. Class A CDL, clean MVR. Reduced detention time by 20% across "
        "3 years. Managed a fleet of 5 owner-operators."
    ),
    "engineer": (
        "Ada Iwuchukwu. Five years building async Python backends in FastAPI "
        "and Postgres. Reduced settlement failures by 40% during the ledger "
        "migration. Led a team of 3 engineers."
    ),
}


def _claims_for(who: str):
    return C.extract_deterministic(
        RESUMES[who], source_kind="resume", source_ref=f"resume:{who}")


@pytest.mark.parametrize("who", sorted(RESUMES))
def test_claims_only_quote_their_own_resume(who):
    claims = _claims_for(who)
    assert claims, f"no claims extracted for {who}; the test proves nothing"
    problems = C.verify_spans(claims, {f"resume:{who}": RESUMES[who]})
    assert problems == [], problems
    text = " ".join(c.claim_text for c in claims).lower()
    assert _foreign_words(text, who) == [], (
        f"{who}'s claims quote another candidate's background: "
        f"{_foreign_words(text, who)}"
    )


@pytest.mark.parametrize("who,other", [
    ("accountant", "driver"), ("driver", "engineer"), ("engineer", "accountant"),
])
def test_a_claim_cannot_be_verified_against_the_wrong_resume(who, other):
    """MUTATION CONTROL for the anchoring.

    Hand one candidate's claims the WRONG document. The spans no longer hold,
    so verify_spans must object. This is the check that turns "the claim cites
    a source" into "the claim cites the RIGHT source" -- without it, a swapped
    résumé would sail through with every span still nominally present.
    """
    claims = _claims_for(who)
    problems = C.verify_spans(claims, {f"resume:{who}": RESUMES[other]})
    assert problems, (
        f"{who}'s claims verified cleanly against {other}'s résumé. A candidate "
        f"could be questioned about words from someone else's document."
    )


def test_a_claim_citing_a_document_we_were_not_given_is_refused():
    claims = _claims_for("accountant")
    problems = C.verify_spans(claims, {"resume:somebody-else": RESUMES["accountant"]})
    assert problems, "a claim citing an unsupplied document was accepted"
    assert "not among the documents supplied" in problems[0]
