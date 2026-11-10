from typing import Protocol, runtime_checkable

from contract_intel.domain.document import Document
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.ingestion import IngestionRecord
from contract_intel.domain.page import Page


@runtime_checkable
class DocumentRepository(Protocol):
    """Ingestion state and page text of documents."""

    async def save_ingested(self, document: Document, pages: tuple[Page, ...]) -> None:
        """Mark ``document`` ingested, replacing any previous state and pages."""
        ...

    async def save_failed(self, document: Document, reason: str) -> None:
        """Mark ``document`` failed, dropping any previously stored pages."""
        ...

    async def get_document(self, document_id: DocumentId) -> Document:
        """Return the stored document.

        Raises:
            DocumentNotAvailableError: If no document is stored under the id.
        """
        ...

    async def get_record(self, document_id: DocumentId) -> IngestionRecord | None:
        """Return the ingestion record, or ``None`` if never ingested."""
        ...

    async def ingested_ids(self) -> frozenset[DocumentId]:
        """Return the ids of every successfully ingested document."""
        ...

    async def get_pages(self, document_id: DocumentId) -> tuple[Page, ...]:
        """Return the pages of an ingested document in ascending order.

        Raises:
            DocumentNotAvailableError: If the document is missing or failed.
        """
        ...
