from __future__ import annotations
from typing import List, Optional
from app.core.config import settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

DIM = 1536

class EmbeddingError(Exception):
    pass

def _openai_client():
    if not settings.openai_api_key:
        raise EmbeddingError("OPENAI_API_KEY missing")
    if OpenAI is None:
        raise EmbeddingError("openai library missing")
    return OpenAI(api_key=settings.openai_api_key)

def embed(text: str, model: Optional[str] = None) -> List[float]:
    if settings.embeddings_provider == "mock":
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = []
        for i in range(DIM):
            vec.append(((h[i % len(h)] / 255.0) * 2.0) - 1.0)
        return vec

    if settings.embeddings_provider != "openai":
        raise EmbeddingError("Only openai/mock providers implemented")

    client = _openai_client()
    res = client.embeddings.create(model=model or settings.embeddings_model, input=text)
    return res.data[0].embedding
