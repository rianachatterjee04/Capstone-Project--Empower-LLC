"""
AI Resume Screening Logic (#114)
Compares resumes against job descriptions and returns a structured screening result.
"""
from __future__ import annotations
import re
from typing import Optional

SKILL_KEYWORDS = [
    "python", "javascript", "typescript", "react", "node", "sql", "postgresql",
    "fastapi", "django", "flask", "aws", "docker", "kubernetes", "git",
    "machine learning", "data analysis", "project management", "agile", "scrum",
    "communication", "leadership", "teamwork", "problem solving", "java", "c++",
    "excel", "tableau", "salesforce", "marketing", "accounting", "finance",
    "hr", "recruiting", "onboarding", "payroll", "benefits", "compliance"
]

def extract_keywords(text: str) -> set[str]:
    text = text.lower()
    keywords = set()
    for kw in SKILL_KEYWORDS:
        if kw in text:
            keywords.add(kw)
    words = set(re.findall(r'\b[a-z]{3,}\b', text))
    keywords.update(words)
    return keywords

def calculate_score(resume: str, criteria: str) -> dict:
    resume_keywords = extract_keywords(resume)
    criteria_keywords = extract_keywords(criteria)

    if not criteria_keywords:
        return {"score": 0, "reason": "No criteria provided", "match_percent": 0, "matched": [], "missing": []}

    matched = resume_keywords & criteria_keywords
    missing = criteria_keywords - resume_keywords
    match_percent = round((len(matched) / len(criteria_keywords)) * 100, 1)

    # Score out of 10
    score = min(10, round((len(matched) / max(len(criteria_keywords), 1)) * 10))

    # Build explanation
    matched_skills = [k for k in matched if k in SKILL_KEYWORDS][:5]
    missing_skills = [k for k in missing if k in SKILL_KEYWORDS][:5]

    if score >= 8:
        summary = f"Strong match. Resume aligns well with job requirements ({match_percent}% match)."
    elif score >= 5:
        summary = f"Moderate match. Candidate meets some requirements ({match_percent}% match)."
    else:
        summary = f"Weak match. Resume does not sufficiently match job requirements ({match_percent}% match)."

    reason = summary
    if matched_skills:
        reason += f" Key matching skills: {', '.join(matched_skills)}."
    if missing_skills:
        reason += f" Missing skills: {', '.join(missing_skills)}."

    return {
        "score": score,
        "match_percent": match_percent,
        "reason": reason,
        "matched_keywords": list(matched)[:20],
        "missing_keywords": list(missing)[:20],
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
    }

def screen(resume: str, criteria: str) -> dict:
    if not resume or not criteria:
        return {"score": 0, "reason": "Missing resume or criteria", "match_percent": 0}
    return calculate_score(resume, criteria)
