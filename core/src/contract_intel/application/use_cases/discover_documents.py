from contract_intel.application.ports.outbound.document_repository import (
    DocumentRepository,
)
from contract_intel.application.ports.outbound.document_source import DocumentSource
from contract_intel.domain.ids import DocumentId

MIN_DOCUMENTS = 1


class DiscoverDocumentsUseCase:
    """List the source documents that are not ingested yet.

    The source is ordered by document id and capped at ``max_documents`` before
    ingested documents are removed, so the system converges on a fixed subset.
    """

    def __init__(
        self,
        source: DocumentSource,
        repository: DocumentRepository,
        max_documents: int,
    ) -> None:
        if max_documents < MIN_DOCUMENTS:
            raise ValueError(f"max_documents must be >= {MIN_DOCUMENTS}")
        self._source = source
        self._repository = repository
        self._max_documents = max_documents

    async def execute(self) -> tuple[DocumentId, ...]:
        """Return pending document ids in ascending id order."""
        documents = await self._source.list_documents()
        considered = sorted(document.id for document in documents)
        considered = considered[: self._max_documents]
        ingested = await self._repository.ingested_ids()
        return tuple(
            document_id for document_id in considered if document_id not in ingested
        )
