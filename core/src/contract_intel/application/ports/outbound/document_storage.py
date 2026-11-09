from typing import Protocol, runtime_checkable

from contract_intel.domain.ids import DocumentId


@runtime_checkable
class DocumentStorage(Protocol):
    """Durable storage for raw document files."""

    async def save(self, document_id: DocumentId, content: bytes) -> None:
        """Store ``content`` under ``document_id``, replacing any previous file."""
        ...

    async def load(self, document_id: DocumentId) -> bytes:
        """Return the stored content of ``document_id``."""
        ...

    async def exists(self, document_id: DocumentId) -> bool:
        """Tell whether a non-empty file is stored for ``document_id``."""
        ...
