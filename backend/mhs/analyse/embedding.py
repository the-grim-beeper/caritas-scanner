"""Local multilingual sentence embeddings (German corpus; English fields are
translations, not evidence, so they are not embedded)."""
from __future__ import annotations

from functools import lru_cache

from mhs.config import settings


@lru_cache
def _model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=settings.embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [vec.tolist() for vec in _model().embed(texts, batch_size=32)]


def signal_text(headline_de: str, summary_de: str | None) -> str:
    return f"{headline_de.strip()} {(summary_de or '').strip()}".strip()
