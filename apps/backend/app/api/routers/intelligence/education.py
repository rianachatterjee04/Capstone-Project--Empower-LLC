from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from typing import Dict, Any

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.modules.education_chatbot import EquityBot
from app.services.ai_memory import search_memory, upsert_memory

router = APIRouter(prefix="/intel/education", tags=["intelligence"])


# ---------------------------------------------------------------------------
# HR EDUCATION ASSISTANT
# ---------------------------------------------------------------------------
@router.get("/ask")
async def ask(q: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)) -> Dict[str, Any]:
    """
    Company-aware HR education assistant.

    Supports:
    - equity education
    - HR policy explanations
    - employee onboarding help
    - compensation explanations

    Example:
    /intel/education/ask?q=What is vesting
    """

    if not q or len(q.strip()) < 3:
        raise HTTPException(status_code=400, detail="Question required")

    try:

        # ---------------------------------------------------------
        # 1️⃣ Retrieve company knowledge (RAG memory)
        # ---------------------------------------------------------
        org_id = UUID(actor.org_id)

        memory_items = await search_memory(
            db,
            org_id,
            namespace="hr_knowledge",
            query=q,
            k=5
        )

        context_text = "\n".join([m.content for m in memory_items]) if memory_items else ""

        # ---------------------------------------------------------
        # 2️⃣ Role-aware system prompt
        # ---------------------------------------------------------
        role_prefix = {
            "employee": "Explain in simple employee-friendly terms.",
            "manager": "Explain in operational HR terms.",
            "hr": "Explain with compliance detail.",
            "admin": "Explain with policy precision.",
            "owner": "Explain with executive summary and risk insight."
        }.get(actor.role, "Explain clearly.")

        full_question = f"""
User role: {actor.role}

Company context:
{context_text}

Question:
{q}

Instructions:
{role_prefix}
If uncertain, say so clearly.
"""

        # ---------------------------------------------------------
        # 3️⃣ Run AI educator
        # ---------------------------------------------------------
        bot = EquityBot()
        answer = bot.answer(full_question)

        # ---------------------------------------------------------
        # 4️⃣ Store conversational memory (learning org)
        # ---------------------------------------------------------
        await upsert_memory(
            db,
            org_id,
            namespace="employee_questions",
            content=f"Q: {q}\nA: {answer}",
            metadata={"role": actor.role},
            entity_type="org",
            entity_id=None
        )

        # ---------------------------------------------------------
        # 5️⃣ Audit log (legal defensibility)
        # ---------------------------------------------------------
        db.add(AuditEvent(
            org_id=org_id,
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai.education.question_answered",
            entity_type="org",
            entity_id=None,
            payload={"question": q}
        ))

        await db.commit()

        # ---------------------------------------------------------
        # 6️⃣ Structured response
        # ---------------------------------------------------------
        return {
            "question": q,
            "answer": answer,
            "confidence": "medium" if context_text else "general_knowledge",
            "context_used": bool(context_text),
            "role_adjusted": actor.role
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

