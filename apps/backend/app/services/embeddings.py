from __future__ import annotations
from typing import List
from app.services.embeddings_provider import embed as _embed, DIM

def embedding(text: str) -> List[float]:
    return _embed(text)

def mock_embedding(text: str, dim: int = DIM) -> List[float]:
    # Back-compat for older callers; uses EMBEDDINGS_PROVIDER=mock for deterministic embeddings
    return _embed(text)
