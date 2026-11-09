import hashlib
from collections.abc import Sequence

from contract_intel.domain.chunk import Embedding

DEFAULT_DIMENSIONS = 8
_BYTE_MAX = 255


class InMemoryEmbedder:
    """Deterministic embeddings derived from a hash of the text.

    Equal texts get equal vectors, which is enough to exercise retrieval flows
    without a model.
    """

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self._dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        """Return one hash-derived embedding per text."""
        return tuple(self._embed_one(text) for text in texts)

    def _embed_one(self, text: str) -> Embedding:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = tuple(
            digest[i % len(digest)] / _BYTE_MAX for i in range(self._dimensions)
        )
        return Embedding(values=values)
