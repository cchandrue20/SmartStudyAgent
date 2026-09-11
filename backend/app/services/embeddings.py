from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed_texts(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    return model.encode(
        texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
    ).tolist()


def embed_query(text: str) -> List[float]:
    return embed_texts([text])[0]
