from typing import Protocol, runtime_checkable

from contract_intel.domain.ids import DocumentId
from contract_intel.domain.ingestion import IngestionRecord


@runtime_checkable
class IngestDocument(Protocol):
    """Store one document, extract its pages and record the outcome."""

    async def execute(self, document_id: DocumentId) -> IngestionRecord:
        """Ingest ``document_id`` and return its resulting ingestion record."""
        ...
