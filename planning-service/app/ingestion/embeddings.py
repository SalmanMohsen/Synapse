"""Embedding generation via nomic-embed-text.

Loaded once per process (planning-service is a long-running worker, not a
per-request process) — see Locked Decisions -> Local dev / inference environment.
"""

import os
from functools import lru_cache

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = os.environ.get(
    "EMBEDDING_MODEL_NAME", "nomic-ai/CodeRankEmbed"
)
EMBED_DIM = 256

# nomic-embed-text-v1.5's actual native context length (rotary position
# embeddings) — not a tunable safety margin. The 2048 figure that shows up in
# some docs is a llama.cpp/GGUF or Ollama serving default, not a model limit;
# loading straight from HF weights via sentence-transformers supports the
# full 8192 with no extra config.
MAX_EMBED_TOKENS = int(os.environ.get("MAX_EMBED_TOKENS", "8192"))

# nomic-embed-text uses task-instruction prefixes for asymmetric retrieval:
# indexed content gets "search_document: ", queries get "search_query: ".
_DOCUMENT_PREFIX = "search_document: "
_QUERY_PREFIX = "search_query: "


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME, trust_remote_code=True)


def count_tokens(text: str) -> int:
    """Exact token count via the embedding model's own tokenizer — no char/4 estimate."""
    tokenizer = _get_model().tokenizer
    return len(tokenizer.encode(text, add_special_tokens=False))


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embeds chunk content for indexing (search_document prefix)."""
    model = _get_model()
    prefixed = [_DOCUMENT_PREFIX + text for text in texts]
    return model.encode(prefixed, normalize_embeddings=True).tolist()


def embed_query(text: str) -> list[float]:
    """Embeds a retrieval query (search_query prefix) — used by step 8's retrieval call."""
    model = _get_model()
    return model.encode(_QUERY_PREFIX + text, normalize_embeddings=True).tolist()