from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from contract_intel.domain.chunk import EmbeddedChunk
from contract_intel.domain.ids import DocumentId


@runtime_checkable
class VectorIndexWriter(Protocol):
    """Write side of the vector index; used only by the ingestion pipelines."""

    async def replace_document(
        self, document_id: DocumentId, chunks: Sequence[EmbeddedChunk]
    ) -> None:
        """Atomically replace every chunk of ``document_id`` with ``chunks``.

        Raises:
            ChunkDocumentMismatchError: If a chunk belongs to another document.
        """
        ...

    async def delete_document(self, document_id: DocumentId) -> None:
        """Remove every chunk of ``document_id`` from the index."""
        ...
