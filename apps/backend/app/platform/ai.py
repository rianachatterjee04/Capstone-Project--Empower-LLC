from __future__ import annotations
from typing import Dict, Any, List
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def chat(system: str, user: str) -> str:
    if not os.environ.get("OPENAI_API_KEY"):
        return "OPENAI_API_KEY not set. Add it to your environment to enable the AI copilot."
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":system},
            {"role":"user","content":user},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""

def employer_chat_context(company_snapshot: Dict[str, Any]) -> str:
    return (
        "You are Foundry Copilot for an employer (CFO/HR/Legal). "
        "Answer with concise, correct, audit-friendly guidance. "
        "If asked for numbers, compute from the provided snapshot. "
        "If data is missing, say what is missing and how to provide it."
    )

def employee_chat_context(company_snapshot: Dict[str, Any]) -> str:
    return (
        "You are Foundry Copilot for an employee. "
        "Explain equity in plain English, avoid legal advice, and show simple examples. "
        "If asked for personal grant numbers, use the snapshot. "
        "If uncertain, ask for the missing detail in one question."
    )
