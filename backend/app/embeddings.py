"""
Local embeddings via sentence-transformers. Runs entirely on-device (CPU is
fine for this scale) so there's no embedding API to pay for or rate-limit
against. Model is downloaded once from Hugging Face on first use (~90MB)
and cached locally.
"""
from functools import lru_cache

EMBEDDING_DIM = 384  # must match the `vector(384)` column in phase3_schema.sql


@lru_cache(maxsize=1)
def _get_model():
    # Imported lazily so the rest of the app can start even before the
    # (fairly heavy) sentence-transformers/torch import finishes.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
