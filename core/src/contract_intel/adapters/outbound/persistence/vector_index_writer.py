from collections.abc import Sequence

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contract_intel.adapters.outbound.persistence.models import (
    EMBEDDING_DIMENSIONS,
    ChunkRow,
)
from contract_intel.domain.chunk import EmbeddedChunk
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.index_rules import ensure_writable


class PgVectorIndexWriter:
    """Write side of the vector index, stored in Postgres with pgvector."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], model: str
    ) -> None:
        self._session_factory = session_factory
        self._model = model

    async def replace_document(
        self, document_id: DocumentId, chunks: Sequence[EmbeddedChunk]
    ) -> None:
        """Delete the document's chunks and insert ``chunks`` in one transaction.

        Raises:
            ChunkDocumentMismatchError: If a chunk belongs to another document.
            EmbeddingDimensionMismatchError: If a vector does not fit the index.
        """
        ensure_writable(document_id, chunks, EMBEDDING_DIMENSIONS)
        async with self._session_factory.begin() as session:
            await self._delete(session, document_id)
            if chunks:
                await session.execute(
                    insert(ChunkRow),
                    [self._row(ordinal, c) for ordinal, c in enumerate(chunks)],
                )

    async def delete_document(self, document_id: DocumentId) -> None:
        """Remove every chunk of ``document_id``."""
        async with self._session_factory.begin() as session:
            await self._delete(session, document_id)

    @staticmethod
    async def _delete(session: AsyncSession, document_id: DocumentId) -> None:
        await session.execute(
            delete(ChunkRow).where(ChunkRow.document_id == document_id)
        )

    def _row(self, ordinal: int, embedded: EmbeddedChunk) -> dict[str, object]:
        chunk = embedded.chunk
        return {
            "id": chunk.id,
            "document_id": chunk.document_id,
            "ordinal": ordinal,
            "text": chunk.text,
            "first_page": chunk.pages.first,
            "last_page": chunk.pages.last,
            "clause_type": None
            if chunk.clause_type is None
            else chunk.clause_type.value,
            "embedding": list(embedded.embedding.values),
            "model": self._model,
        }
