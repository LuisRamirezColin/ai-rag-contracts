import hashlib
from collections.abc import Sequence

from contract_intel.domain.chunk import Embedding, EmbeddingBatch

DEFAULT_DIMENSIONS = 8
IN_MEMORY_MODEL = "in-memory-hash"
CHARS_PER_TOKEN = 4
_BYTE_MAX = 255


class InMemoryEmbedder:
    """Deterministic embeddings derived from a hash of the text.

    Equal texts get equal vectors whether embedded as documents or queries, so
    retrieval flows can be exercised without a model; calls are counted per kind.
    """

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self._dimensions = dimensions
        self.document_calls = 0
        self.query_calls = 0

    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Return hash-derived embeddings and an estimated token count."""
        self.document_calls += 1
        return EmbeddingBatch(
            embeddings=tuple(self._embed_one(text) for text in texts),
            input_tokens=sum(_estimated_tokens(text) for text in texts),
            model=IN_MEMORY_MODEL,
        )

    async def embed_query(self, text: str) -> Embedding:
        """Return the hash-derived embedding of ``text``."""
        self.query_calls += 1
        return self._embed_one(text)

    def _embed_one(self, text: str) -> Embedding:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = tuple(
            digest[i % len(digest)] / _BYTE_MAX for i in range(self._dimensions)
        )
        return Embedding(values=values)


def _estimated_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)
