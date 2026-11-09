from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from contract_intel.domain.ids import DocumentId


@dataclass(frozen=True, slots=True)
class IngestionReport:
    """Outcome of an ingestion run."""

    ingested: tuple[DocumentId, ...] = field(default_factory=tuple)
    failed: tuple[DocumentId, ...] = field(default_factory=tuple)


@runtime_checkable
class IngestDocuments(Protocol):
    """Bring new documents from a source into storage and mark them ready."""

    async def execute(self) -> IngestionReport:
        """Ingest every document not yet stored."""
        ...
