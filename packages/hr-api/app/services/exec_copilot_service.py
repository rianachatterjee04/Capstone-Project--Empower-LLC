"""Executive AI Copilot.

The "CEO asks how healthy is the company" surface. Combines:
- live workforce counts from Postgres
- workforce-risk summary
- attrition top-N
- CPO command center signals
- RAG retrieval from the policy library

Produces a single conversational answer with citations + numeric backing.
"""
from __future__ import annotations

import textwrap
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cpo_service import build_report
from app.services.rag_service import retrieve
from app.services.workforce_risk_service import scan as scan_risk

try:
    from app.services.llm import llm_complete, LLMError
except Exception:  # pragma: no cover
    llm_complete = None
    LLMError = Exception


_BUSINESS_KEYWORDS = (
    "health", "attrition", "hiring", "pipeline", "payroll", "compensation",
    "performance", "compliance", "risk", "learning", "headcount", "engagement",
)


async def _gather_context(db: AsyncSession, org_id: str) -> dict:
    cpo = await build_report(db, org_id)
    risk = await scan_risk(db, org_id)
    return {
        "cpo": cpo.to_dict(),
        "risk": risk.to_dict(),
    }


def _is_business_question(q: str) -> bool:
    qlow = (q or "").lower()
    return any(k in qlow for k in _BUSINESS_KEYWORDS) or qlow.startswith(("how", "what", "why", "show", "who"))


def _fallback_answer(question: str, ctx: dict) -> str:
    cpo = ctx["cpo"]
    risk = ctx["risk"]
    pieces = [
        f"Headline: {cpo['headline']}",
        f"Risk: {risk['headline']} (score {risk['score']}/100)",
        f"Snapshot: {cpo['summary']}",
    ]
    if cpo["priorities"]:
        top = cpo["priorities"][0]
        pieces.append(f"Top priority today: {top['title']} — {top['detail']}")
    if cpo["recommendations"]:
        rec = cpo["recommendations"][0]
        pieces.append(f"Recommendation: {rec['headline']} ({rec['confidence']} confidence)")
    return " ".join(pieces)


def _llm_answer(question: str, ctx: dict, policy_excerpts: list[str]) -> Optional[str]:
    if llm_complete is None:
        return None
    try:
        prompt = textwrap.dedent(f"""
            You are the Executive AI Copilot for an SMB CEO using Foundry People.
            Answer briefly (<= 6 short sentences) using ONLY the structured facts
            and policy excerpts below. Cite source titles in square brackets when
            you reference a policy.

            CEO question:
            {question}

            Workforce facts (CPO report):
            headline: {ctx['cpo']['headline']}
            summary:  {ctx['cpo']['summary']}
            priorities: {[p['title'] for p in ctx['cpo']['priorities']]}
            recommendations: {[r['headline'] for r in ctx['cpo']['recommendations']]}

            Risk:
            headline: {ctx['risk']['headline']}
            score:    {ctx['risk']['score']}/100
            counts:   {ctx['risk']['counts']}

            Policy excerpts:
            {chr(10).join(policy_excerpts[:3])}

            Tone: calm, specific, numeric. Never invent metrics.
        """).strip()
        return llm_complete(prompt, system="You are an enterprise executive copilot. Be precise and concise.")
    except (LLMError, Exception):
        return None


async def answer(db: AsyncSession, org_id: str, question: str) -> dict:
    if not question.strip():
        return {"answer": "Ask me anything about workforce health, hiring, risk, or comp.", "citations": [], "facts": {}}

    ctx = await _gather_context(db, org_id)
    policy_docs = retrieve(org_id, question, top_k=2)
    excerpts = [f"[{d.title}] {d.body[:280]}" for d in policy_docs]

    composed = _llm_answer(question, ctx, excerpts) if _is_business_question(question) else None
    text = composed or _fallback_answer(question, ctx)

    return {
        "question": question,
        "answer": text,
        "facts": {
            "headline": ctx["cpo"]["headline"],
            "risk_score": ctx["risk"]["score"],
            "priority_count": len(ctx["cpo"]["priorities"]),
            "high_risk_alerts": sum(1 for a in ctx["risk"]["alerts"] if a["severity"] == "high"),
        },
        "citations": [{"id": d.id, "title": d.title, "category": d.category} for d in policy_docs],
        "disclaimer": (
            "Executive copilot answers are synthesised from your live HR data and "
            "policy library. They are advisory; HR/legal must validate decisions."
        ),
    }
