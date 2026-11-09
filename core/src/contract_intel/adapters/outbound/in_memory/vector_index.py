import math
from collections.abc import Sequence

from contract_intel.domain.chunk import EmbeddedChunk, Embedding, ScoredChunk
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.ids import ChunkId, DocumentId


class InMemoryVectorStore:
    """Shared state behind the in-memory index writer and search."""

    def __init__(self) -> None:
        self.entries: dict[ChunkId, EmbeddedChunk] = {}


def _cosine_similarity(a: Embedding, b: Embedding) -> float:
    dot = sum(x * y for x, y in zip(a.values, b.values, strict=True))
    norms = math.hypot(*a.values) * math.hypot(*b.values)
    return dot / norms if norms else 0.0


class InMemoryVectorIndexWriter:
    """Write side of the in-memory vector index."""

    def __init__(self, store: InMemoryVectorStore) -> None:
        self._store = store

    async def upsert(self, chunks: Sequence[EmbeddedChunk]) -> None:
        """Insert or replace ``chunks`` by chunk id."""
        for embedded in chunks:
            self._store.entries[embedded.chunk.id] = embedded

    async def delete_document(self, document_id: DocumentId) -> None:
        """Remove every chunk that belongs to ``document_id``."""
        self._store.entries = {
            chunk_id: embedded
            for chunk_id, embedded in self._store.entries.items()
            if embedded.chunk.document_id != document_id
        }


class InMemoryVectorSearch:
    """Read side of the in-memory vector index (cosine similarity)."""

    def __init__(self, store: InMemoryVectorStore) -> None:
        self._store = store

    async def search(
        self,
        query: Embedding,
        limit: int,
        clause_types: frozenset[ClauseType] = frozenset(),
    ) -> tuple[ScoredChunk, ...]:
        """Return the ``limit`` most similar chunks, optionally type-filtered."""
        candidates = (
            embedded
            for embedded in self._store.entries.values()
            if not clause_types or embedded.chunk.clause_type in clause_types
        )
        scored = sorted(
            (
                ScoredChunk(
                    embedded.chunk, _cosine_similarity(query, embedded.embedding)
                )
                for embedded in candidates
            ),
            key=lambda item: item.score,
            reverse=True,
        )
        return tuple(scored[:limit])
