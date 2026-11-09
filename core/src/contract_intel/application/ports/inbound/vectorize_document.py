from typing import Protocol, runtime_checkable

from contract_intel.domain.ids import DocumentId


@runtime_checkable
class VectorizeDocument(Protocol):
    """Chunk, embed and index a stored document in the vector index."""

    async def execute(self, document_id: DocumentId) -> int:
        """Index ``document_id`` and return the number of chunks written."""
        ...
