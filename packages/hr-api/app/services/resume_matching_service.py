"""Enhanced semantic resume matching service.

Replaces the simple keyword overlap in app.ai.screening with a richer pipeline:
- skill extraction via curated ontology + heuristic regex
- semantic similarity via embeddings (mock or OpenAI provider)
- experience / education / certification extraction
- explainable evidence snippets
- bias-aware sensitive-attribute caution flags
- hiring recommendation summary

The service is intentionally provider-agnostic. It works in pure-Python mock mode
(no OPENAI_API_KEY) and upgrades transparently when an OpenAI key is configured
via app.services.embeddings_provider.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable

from app.services.embeddings import embedding

# ---------------------------------------------------------------------------
# Skill ontology — curated, expandable. Keys are canonical names, values are
# aliases the matcher should treat as equivalent.
# ---------------------------------------------------------------------------
SKILL_ONTOLOGY: dict[str, list[str]] = {
    "python": ["python", "py", "python3"],
    "javascript": ["javascript", "js", "ecmascript"],
    "typescript": ["typescript", "ts"],
    "react": ["react", "reactjs", "react.js"],
    "next.js": ["next.js", "nextjs", "next"],
    "node.js": ["node", "node.js", "nodejs"],
    "fastapi": ["fastapi"],
    "django": ["django"],
    "flask": ["flask"],
    "sql": ["sql", "ansi sql"],
    "postgresql": ["postgres", "postgresql", "psql"],
    "mysql": ["mysql"],
    "mongodb": ["mongo", "mongodb"],
    "redis": ["redis"],
    "aws": ["aws", "amazon web services"],
    "gcp": ["gcp", "google cloud"],
    "azure": ["azure"],
    "docker": ["docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "terraform": ["terraform"],
    "ci/cd": ["ci/cd", "ci cd", "continuous integration"],
    "machine learning": ["machine learning", "ml", "mlops"],
    "data analysis": ["data analysis", "analytics"],
    "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"],
    "llm": ["llm", "large language model", "gpt"],
    "leadership": ["leadership", "lead"],
    "communication": ["communication", "stakeholder management"],
    "project management": ["project management", "scrum", "agile", "kanban"],
    "salesforce": ["salesforce"],
    "tableau": ["tableau"],
    "looker": ["looker"],
    "snowflake": ["snowflake"],
    "java": ["java"],
    "c++": ["c++", "cpp"],
    "go": ["golang", " go "],
    "rust": ["rust"],
    "excel": ["excel", "spreadsheet"],
    "hr": ["hr", "human resources"],
    "recruiting": ["recruiting", "talent acquisition"],
    "payroll": ["payroll"],
    "benefits": ["benefits administration", "benefits"],
    "compliance": ["compliance", "soc2", "soc 2", "gdpr", "hipaa"],
}

CERT_KEYWORDS = [
    "pmp", "cfa", "cpa", "shrm-cp", "shrm-scp", "phr", "sphr",
    "aws certified", "gcp certified", "azure certified",
    "scrum master", "csm", "okrs", "six sigma",
]

EDU_LEVELS = [
    ("phd", 5), ("doctorate", 5),
    ("master", 4), ("mba", 4), ("ms ", 4), ("m.s.", 4), ("ma ", 4), ("m.a.", 4),
    ("bachelor", 3), ("bs ", 3), ("b.s.", 3), ("ba ", 3), ("b.a.", 3),
    ("associate", 2),
    ("diploma", 1),
]

# Words that, if present, warrant a caution flag for the human reviewer.
SENSITIVE_ATTRIBUTE_TERMS = [
    "age ", "born in", "date of birth", "dob ",
    "gender", "male", "female", "non-binary",
    "religion", "religious", "muslim", "christian", "hindu", "jewish",
    "married", "single ", "divorced", "pregnant",
    "nationality", "citizenship",
    "disability", "disabled",
]


@dataclass
class SkillEvidence:
    skill: str
    snippet: str

    def to_dict(self) -> dict:
        return {"skill": self.skill, "snippet": self.snippet}


@dataclass
class MatchResult:
    overall_score: int                # 0-100
    band: str                         # "strong" | "moderate" | "weak"
    recommendation: str               # "advance" | "interview" | "reject"
    semantic_similarity: float        # 0..1
    skills_score: float               # 0..1
    experience_score: float           # 0..1
    education_score: float            # 0..1
    matched_skills: list[str]
    missing_skills: list[str]
    skill_evidence: list[SkillEvidence] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    estimated_years_experience: float = 0.0
    highest_education_level: int = 0
    bias_flags: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "overall_score": self.overall_score,
            "band": self.band,
            "recommendation": self.recommendation,
            "semantic_similarity": round(self.semantic_similarity, 3),
            "subscores": {
                "skills": round(self.skills_score, 3),
                "experience": round(self.experience_score, 3),
                "education": round(self.education_score, 3),
            },
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "skill_evidence": [e.to_dict() for e in self.skill_evidence],
            "certifications": self.certifications,
            "estimated_years_experience": round(self.estimated_years_experience, 1),
            "highest_education_level": self.highest_education_level,
            "bias_flags": self.bias_flags,
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _find_snippet(text: str, term: str, window: int = 80) -> str:
    norm = text.lower()
    idx = norm.find(term.lower())
    if idx == -1:
        return ""
    start = max(0, idx - window)
    end = min(len(text), idx + len(term) + window)
    snippet = text[start:end].strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _alias_present(alias: str, norm: str) -> bool:
    """Word-boundary match so 'java' doesn't match inside 'javascript', 'sql'
    inside 'postgresql', or 'next' inside 'context'. Multi-word aliases are
    preserved (norm has whitespace collapsed to single spaces). Lookarounds
    are used instead of ``\\b`` so aliases that end in non-word characters
    (e.g. 'c++') still match correctly."""
    token = alias.strip()
    if not token:
        return False
    pattern = r"(?<!\w)" + re.escape(token) + r"(?!\w)"
    return re.search(pattern, norm) is not None


def extract_skills(text: str) -> tuple[set[str], list[SkillEvidence]]:
    """Return canonical skills present plus snippet evidence."""
    norm = _normalize(text)
    found: set[str] = set()
    evidence: list[SkillEvidence] = []
    for canonical, aliases in SKILL_ONTOLOGY.items():
        for alias in aliases:
            if _alias_present(alias, norm):
                found.add(canonical)
                snippet = _find_snippet(text, alias.strip())
                if snippet:
                    evidence.append(SkillEvidence(skill=canonical, snippet=snippet))
                break
    return found, evidence


def extract_certifications(text: str) -> list[str]:
    norm = _normalize(text)
    return [c for c in CERT_KEYWORDS if c in norm]


def extract_education(text: str) -> int:
    norm = _normalize(text)
    best = 0
    for token, level in EDU_LEVELS:
        if token in norm and level > best:
            best = level
    return best


def estimate_years_experience(text: str) -> float:
    """Heuristic: pull '7 years', '7+ years' style mentions; pick the max."""
    norm = _normalize(text)
    matches = re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", norm)
    years = [float(m) for m in matches if m.isdigit()]
    return max(years) if years else 0.0


def detect_bias_flags(text: str) -> list[str]:
    norm = _normalize(text)
    hits = sorted({t.strip() for t in SENSITIVE_ATTRIBUTE_TERMS if t in norm})
    flags: list[str] = []
    if hits:
        flags.append("sensitive_attribute_detected: " + ", ".join(hits[:5]))
        flags.append("review_recommendation: HR should redact sensitive attributes before sharing.")
    return flags


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def match_resume(
    resume_text: str,
    job_description: str,
    required_skills: Iterable[str] | None = None,
    min_years: float | None = None,
) -> MatchResult:
    """Run the full match pipeline and return a MatchResult."""
    resume_text = resume_text or ""
    job_description = job_description or ""

    resume_skills, evidence = extract_skills(resume_text)
    job_skills, _ = extract_skills(job_description)

    if required_skills:
        job_skills = job_skills | {s.lower() for s in required_skills}

    # ---- skills score
    if job_skills:
        matched = sorted(resume_skills & job_skills)
        missing = sorted(job_skills - resume_skills)
        skills_score = len(matched) / max(len(job_skills), 1)
    else:
        matched = sorted(resume_skills)
        missing = []
        # No criteria-side skills means we can't penalise; treat as neutral 0.5.
        skills_score = 0.5

    # ---- semantic similarity
    try:
        sem = _cosine(embedding(resume_text[:6000]), embedding(job_description[:6000]))
    except Exception:
        sem = 0.0

    # ---- experience score (compare to min_years if provided)
    yrs = estimate_years_experience(resume_text)
    if min_years:
        experience_score = min(1.0, yrs / max(min_years, 1.0))
    else:
        # No requirement — reward any visible experience up to 10 years.
        experience_score = min(1.0, yrs / 10.0) if yrs else 0.4

    # ---- education score
    edu_level = extract_education(resume_text)
    education_score = edu_level / 5.0 if edu_level else 0.4

    # ---- certifications
    certs = extract_certifications(resume_text)
    cert_bonus = min(0.1, 0.025 * len(certs))

    # ---- weighted overall (0..1 then scaled)
    weighted = (
        0.45 * skills_score
        + 0.30 * sem
        + 0.15 * experience_score
        + 0.10 * education_score
        + cert_bonus
    )
    weighted = max(0.0, min(1.0, weighted))
    overall = int(round(weighted * 100))

    # ---- band + recommendation
    if overall >= 75:
        band, rec = "strong", "advance"
    elif overall >= 55:
        band, rec = "moderate", "interview"
    else:
        band, rec = "weak", "reject"

    bias = detect_bias_flags(resume_text)

    # ---- explanation
    explanation_parts = [
        f"{band.capitalize()} match ({overall}/100).",
        f"Skills coverage: {int(skills_score*100)}% ({len(matched)}/{len(job_skills) or len(matched)} requirements).",
        f"Semantic alignment: {int(sem*100)}%.",
    ]
    if yrs:
        explanation_parts.append(f"Estimated experience: {yrs:.0f} year(s).")
    if certs:
        explanation_parts.append("Certifications: " + ", ".join(certs[:4]) + ".")
    if missing[:5]:
        explanation_parts.append("Missing requirements: " + ", ".join(missing[:5]) + ".")
    if bias:
        explanation_parts.append("Bias caution: sensitive attributes detected — HR review required.")

    return MatchResult(
        overall_score=overall,
        band=band,
        recommendation=rec,
        semantic_similarity=sem,
        skills_score=skills_score,
        experience_score=experience_score,
        education_score=education_score,
        matched_skills=matched,
        missing_skills=missing,
        skill_evidence=evidence[:10],
        certifications=certs,
        estimated_years_experience=yrs,
        highest_education_level=edu_level,
        bias_flags=bias,
        explanation=" ".join(explanation_parts),
    )


def rank_candidates(
    job_description: str,
    candidates: list[dict],
    required_skills: Iterable[str] | None = None,
    min_years: float | None = None,
) -> list[dict]:
    """Score every candidate dict that contains a 'resume_text' field; return them
    sorted by overall_score desc with the match payload merged in."""
    ranked = []
    for cand in candidates:
        result = match_resume(
            cand.get("resume_text") or "",
            job_description,
            required_skills=required_skills,
            min_years=min_years,
        )
        ranked.append({**cand, "match": result.to_dict()})
    ranked.sort(key=lambda c: c["match"]["overall_score"], reverse=True)
    return ranked
