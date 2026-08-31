"""RAG-ready knowledge service for the AI helpdesk.

Provides:
- a thin index of "knowledge documents" (policies, benefits guides, PTO rules…)
- semantic retrieval via the embeddings provider abstraction
- a synchronous `answer(question)` that returns the answer + citations

The index is in-process to keep the demo zero-dependency. A production version
would persist documents + embeddings in Postgres or a vector store. The
interfaces are stable so swapping the backend doesn't change callers.
"""
from __future__ import annotations

import math
import textwrap
import threading
from dataclasses import dataclass, field
from typing import Optional

from app.services.embeddings import embedding

try:
    from app.services.llm import llm_complete, LLMError
except Exception:  # pragma: no cover
    llm_complete = None
    LLMError = Exception


@dataclass
class KnowledgeDoc:
    id: str
    title: str
    category: str
    body: str
    embedding: list[float] = field(default_factory=list)
    source: str = "internal"


# Default seed content. Each org can append its own documents via the router.
_SEED_DOCS: list[KnowledgeDoc] = [
    KnowledgeDoc(
        id="pto-policy",
        title="PTO Policy",
        category="time_off",
        body=(
            "Full-time employees accrue 1.67 days of paid time off per month "
            "(20 days/year), starting on their first day. PTO requests must be "
            "submitted in the Foundry People app at least 5 business days in "
            "advance for vacations longer than 3 days. Sick leave is separate "
            "and uncapped within reason. Unused PTO may roll over up to 5 days "
            "to the following calendar year."
        ),
    ),
    KnowledgeDoc(
        id="parental-leave",
        title="Parental Leave",
        category="time_off",
        body=(
            "Birthing parents receive 16 weeks of paid parental leave. "
            "Non-birthing parents receive 12 weeks of paid leave. Leave must "
            "begin within 12 months of the qualifying event. Notify HR at "
            "least 30 days in advance whenever possible."
        ),
    ),
    KnowledgeDoc(
        id="benefits-medical",
        title="Medical Benefits Overview",
        category="benefits",
        body=(
            "We offer three medical plans (HMO Bronze, PPO Silver, PPO Gold). "
            "Employer contribution is 80% of the employee premium and 60% of "
            "dependent premiums. Open enrollment runs annually in November. "
            "Qualifying life events (marriage, birth, adoption, divorce, loss "
            "of coverage) allow 30 days to change elections."
        ),
    ),
    KnowledgeDoc(
        id="benefits-401k",
        title="401(k) Retirement",
        category="benefits",
        body=(
            "Foundry matches 100% of the first 4% of salary contributed to the "
            "401(k). Employees vest immediately. Maximum contribution follows "
            "IRS limits. Auto-enroll at 3% for new hires, opt-out within 30 days."
        ),
    ),
    KnowledgeDoc(
        id="onboarding-day1",
        title="Day-One Onboarding",
        category="onboarding",
        body=(
            "Before Day 1: sign offer in Dropbox Sign, complete I-9, upload "
            "direct deposit info, and elect benefits within 30 days of start. "
            "On Day 1: collect equipment from IT, complete security training, "
            "and meet your buddy. Manager assigns 30/60/90 plan."
        ),
    ),
    KnowledgeDoc(
        id="security-acceptable-use",
        title="Acceptable Use & Security",
        category="security",
        body=(
            "All company devices must run the Foundry-managed agent. Use SSO "
            "everywhere. Never share credentials. Report phishing immediately. "
            "Failure to complete annual security training will pause production "
            "access until completion."
        ),
    ),
    KnowledgeDoc(
        id="reporting-channels",
        title="How to Report a Concern",
        category="ethics",
        body=(
            "You can raise an HR concern in three ways: (1) the in-app "
            "Ombudsman, where reports can be anonymous; (2) email "
            "ombudsman@foundrypeople.example; (3) escalate via your VP/HRBP. "
            "Foundry strictly prohibits retaliation against good-faith reporters."
        ),
    ),
]


_lock = threading.RLock()
_org_docs: dict[str, list[KnowledgeDoc]] = {}


# ---------------------------------------------------------------------------
def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return max(0.0, min(1.0, dot / (na * nb))) if na and nb else 0.0


def _ensure_seeded(org_id: str) -> list[KnowledgeDoc]:
    with _lock:
        docs = _org_docs.get(org_id)
        if docs is None:
            docs = []
            for d in _SEED_DOCS:
                try:
                    emb = embedding(d.body)
                except Exception:
                    emb = []
                docs.append(KnowledgeDoc(**{**d.__dict__, "embedding": emb}))
            _org_docs[org_id] = docs
        return docs


def add_document(org_id: str, title: str, body: str, category: str = "policy", source: str = "internal") -> dict:
    docs = _ensure_seeded(org_id)
    doc_id = f"doc-{len(docs)+1}"
    try:
        emb = embedding(body)
    except Exception:
        emb = []
    doc = KnowledgeDoc(id=doc_id, title=title, category=category, body=body, embedding=emb, source=source)
    with _lock:
        docs.append(doc)
    return {"id": doc.id, "title": doc.title, "category": doc.category}


def list_documents(org_id: str) -> list[dict]:
    docs = _ensure_seeded(org_id)
    return [
        {
            "id": d.id,
            "title": d.title,
            "category": d.category,
            "source": d.source,
            "preview": d.body[:200] + ("…" if len(d.body) > 200 else ""),
        }
        for d in docs
    ]


def retrieve(org_id: str, question: str, top_k: int = 3) -> list[KnowledgeDoc]:
    docs = _ensure_seeded(org_id)
    if not question:
        return []
    try:
        qv = embedding(question)
    except Exception:
        qv = []

    scored: list[tuple[float, KnowledgeDoc]] = []
    qlow = question.lower()
    for d in docs:
        sem = _cosine(qv, d.embedding) if qv and d.embedding else 0.0
        # cheap keyword fallback so the demo still works when embeddings are weak
        kw = sum(1 for tok in qlow.split() if tok in d.body.lower()) / max(len(qlow.split()), 1)
        score = 0.7 * sem + 0.3 * kw
        scored.append((score, d))
    scored.sort(key=lambda kv: kv[0], reverse=True)
    return [d for _, d in scored[:top_k] if _ > 0]


def _llm_compose(question: str, contexts: list[KnowledgeDoc]) -> Optional[str]:
    if llm_complete is None or not contexts:
        return None
    try:
        joined = "\n\n".join(
            f"[{c.title}] {c.body}" for c in contexts
        )
        prompt = textwrap.dedent(f"""
            You are an HR helpdesk for Foundry People. Answer the employee question
            using ONLY the provided policy excerpts. If the policy does not cover
            the question, say so and recommend contacting HR.

            Question: {question}

            Policy excerpts:
            {joined[:6000]}

            Respond in <= 4 short sentences. Cite document titles in square brackets.
        """).strip()
        return llm_complete(prompt, system="You are precise, calm, and never invent facts.")
    except (LLMError, Exception):
        return None


def _fallback_answer(question: str, contexts: list[KnowledgeDoc]) -> str:
    if not contexts:
        return (
            "I couldn't find a policy that directly answers that. "
            "Please contact your HR business partner or post in #people-help."
        )
    top = contexts[0]
    return (
        f"Based on [{top.title}]: {top.body.strip()[:600]}"
        + ("…" if len(top.body) > 600 else "")
    )


def answer(org_id: str, question: str, audience: str = "employee") -> dict:
    contexts = retrieve(org_id, question, top_k=3)
    composed = _llm_compose(question, contexts)
    text = composed or _fallback_answer(question, contexts)

    return {
        "question": question,
        "answer": text,
        "audience": audience,
        "citations": [
            {"id": c.id, "title": c.title, "category": c.category}
            for c in contexts
        ],
        "needs_escalation": not contexts,
        "disclaimer": (
            "AI helpdesk is assistive. For decisions involving benefits, payroll, or "
            "legal matters, contact your HR business partner directly."
        ),
    }
