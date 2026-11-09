from typing import Protocol, runtime_checkable

from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import Page


@runtime_checkable
class TextExtractor(Protocol):
    """Turn a raw document file into per-page text."""

    async def extract_pages(
        self, document_id: DocumentId, content: bytes
    ) -> tuple[Page, ...]:
        """Return every page of the document, in order."""
        ...
