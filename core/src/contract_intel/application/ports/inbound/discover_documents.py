from typing import Protocol, runtime_checkable

from contract_intel.domain.ids import DocumentId


@runtime_checkable
class DiscoverDocuments(Protocol):
    """Find the source documents that still need to be ingested."""

    async def execute(self) -> tuple[DocumentId, ...]:
        """Return the pending document ids in a deterministic order."""
        ...
