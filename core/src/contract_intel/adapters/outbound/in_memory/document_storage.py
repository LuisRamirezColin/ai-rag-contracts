from contract_intel.domain.errors import UnknownDocumentError
from contract_intel.domain.ids import DocumentId


class InMemoryDocumentStorage:
    """Document storage kept in a process-local dictionary."""

    def __init__(self) -> None:
        self._files: dict[DocumentId, bytes] = {}

    async def save(self, document_id: DocumentId, content: bytes) -> None:
        """Store ``content`` under ``document_id``."""
        self._files[document_id] = content

    async def load(self, document_id: DocumentId) -> bytes:
        """Return the stored content.

        Raises:
            UnknownDocumentError: If nothing is stored for ``document_id``.
        """
        if document_id not in self._files:
            raise UnknownDocumentError(document_id)
        return self._files[document_id]

    async def exists(self, document_id: DocumentId) -> bool:
        """Tell whether a non-empty file is stored for ``document_id``."""
        return bool(self._files.get(document_id))
