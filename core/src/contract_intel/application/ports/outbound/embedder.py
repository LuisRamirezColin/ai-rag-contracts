from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from contract_intel.domain.chunk import Embedding, EmbeddingBatch


@runtime_checkable
class Embedder(Protocol):
    """Compute dense vectors for indexed documents and for search queries.

    Retrieval models encode documents and queries differently, so each side of
    the RAG calls its own method with the same model and dimension.
    """

    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Return one document embedding per text, in order, plus token usage."""
        ...

    async def embed_query(self, text: str) -> Embedding:
        """Return the embedding of a search query."""
        ...
