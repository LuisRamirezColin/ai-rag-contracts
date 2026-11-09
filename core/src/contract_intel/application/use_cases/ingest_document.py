from contract_intel.application.ports.outbound.document_repository import (
    DocumentRepository,
)
from contract_intel.application.ports.outbound.document_source import DocumentSource
from contract_intel.application.ports.outbound.document_storage import DocumentStorage
from contract_intel.application.ports.outbound.text_extractor import TextExtractor
from contract_intel.domain.document import Document
from contract_intel.domain.errors import UnknownDocumentError, UnreadableDocumentError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.ingestion import (
    NO_EXTRACTABLE_TEXT_REASON,
    IngestionRecord,
    has_extractable_text,
)


class IngestDocumentUseCase:
    """Store a document's original file, extract its pages and record the outcome.

    Business failures (unreadable file, no extractable text) end as a failed
    record; infrastructure errors propagate to the caller.
    """

    def __init__(
        self,
        source: DocumentSource,
        storage: DocumentStorage,
        extractor: TextExtractor,
        repository: DocumentRepository,
    ) -> None:
        self._source = source
        self._storage = storage
        self._extractor = extractor
        self._repository = repository

    async def execute(self, document_id: DocumentId) -> IngestionRecord:
        """Ingest ``document_id`` and return its ingestion record.

        Raises:
            UnknownDocumentError: If the source does not have the document.
        """
        document = await self._find_document(document_id)
        content = await self._source.fetch_content(document_id)
        await self._storage.save(document_id, content)
        await self._extract_and_record(document, content)
        return await self._recorded(document_id)

    async def _find_document(self, document_id: DocumentId) -> Document:
        for document in await self._source.list_documents():
            if document.id == document_id:
                return document
        raise UnknownDocumentError(document_id)

    async def _extract_and_record(self, document: Document, content: bytes) -> None:
        try:
            pages = await self._extractor.extract_pages(document.id, content)
        except UnreadableDocumentError as error:
            await self._repository.save_failed(document, str(error))
            return
        if has_extractable_text(pages):
            await self._repository.save_ingested(document, pages)
        else:
            await self._repository.save_failed(document, NO_EXTRACTABLE_TEXT_REASON)

    async def _recorded(self, document_id: DocumentId) -> IngestionRecord:
        record = await self._repository.get_record(document_id)
        if record is None:
            raise RuntimeError(f"No ingestion record saved for '{document_id}'")
        return record
