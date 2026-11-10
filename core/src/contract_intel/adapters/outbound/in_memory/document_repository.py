from contract_intel.domain.document import Document
from contract_intel.domain.errors import DocumentNotAvailableError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.ingestion import IngestionRecord, IngestionStatus
from contract_intel.domain.page import Page

NUL = "\x00"


class InMemoryDocumentRepository:
    """Document repository kept in process-local dictionaries."""

    def __init__(self) -> None:
        self._documents: dict[DocumentId, Document] = {}
        self._records: dict[DocumentId, IngestionRecord] = {}
        self._pages: dict[DocumentId, tuple[Page, ...]] = {}

    async def save_ingested(self, document: Document, pages: tuple[Page, ...]) -> None:
        """Replace the state of ``document`` with an ingested record and pages."""
        ordered = tuple(
            Page(page.document_id, page.number, page.text.replace(NUL, ""))
            for page in sorted(pages, key=lambda page: page.number)
        )
        self._documents[document.id] = document
        self._records[document.id] = IngestionRecord.ingested(document.id, len(ordered))
        self._pages[document.id] = ordered

    async def save_failed(self, document: Document, reason: str) -> None:
        """Replace the state of ``document`` with a failed record."""
        self._documents[document.id] = document
        self._records[document.id] = IngestionRecord.failed(document.id, reason)
        self._pages.pop(document.id, None)

    async def get_document(self, document_id: DocumentId) -> Document:
        """Return the stored document.

        Raises:
            DocumentNotAvailableError: If no document is stored under the id.
        """
        if document_id not in self._documents:
            raise DocumentNotAvailableError(document_id)
        return self._documents[document_id]

    async def get_record(self, document_id: DocumentId) -> IngestionRecord | None:
        """Return the stored record, if any."""
        return self._records.get(document_id)

    async def ingested_ids(self) -> frozenset[DocumentId]:
        """Return ids whose record is ingested."""
        return frozenset(
            document_id
            for document_id, record in self._records.items()
            if record.status is IngestionStatus.INGESTED
        )

    async def get_pages(self, document_id: DocumentId) -> tuple[Page, ...]:
        """Return the stored pages.

        Raises:
            DocumentNotAvailableError: If the document is missing or failed.
        """
        if document_id not in self._pages:
            raise DocumentNotAvailableError(document_id)
        return self._pages[document_id]
