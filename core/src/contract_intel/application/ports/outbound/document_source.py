from typing import Protocol, runtime_checkable

from contract_intel.domain.document import Document
from contract_intel.domain.ids import DocumentId


@runtime_checkable
class DocumentSource(Protocol):
    """Origin of contract documents (dataset, file share, external system)."""

    async def list_documents(self) -> tuple[Document, ...]:
        """Return the documents currently available at the source."""
        ...

    async def fetch_content(self, document_id: DocumentId) -> bytes:
        """Return the raw file content of ``document_id``."""
        ...
