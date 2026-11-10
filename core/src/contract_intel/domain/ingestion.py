from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from contract_intel.domain.errors import InconsistentIngestionRecordError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import Page
from contract_intel.domain.text import ensure_not_blank

NO_EXTRACTABLE_TEXT_REASON = "no extractable text"
MIN_INGESTED_PAGES = 1


class IngestionStatus(StrEnum):
    """Outcome of ingesting a document."""

    INGESTED = "ingested"
    FAILED = "failed"


def has_extractable_text(pages: Iterable[Page]) -> bool:
    """Tell whether at least one page carries visible text."""
    return any(page.text.strip() for page in pages)


@dataclass(frozen=True, slots=True)
class IngestionRecord:
    """Ingestion state of one document.

    An ingested document has pages and no failure reason; a failed one has a
    reason and no pages.
    """

    document_id: DocumentId
    status: IngestionStatus
    page_count: int
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status is IngestionStatus.INGESTED:
            self._ensure_consistent_ingested()
        else:
            self._ensure_consistent_failed()

    def _ensure_consistent_ingested(self) -> None:
        if self.failure_reason is not None:
            raise InconsistentIngestionRecordError("ingested with a failure reason")
        if self.page_count < MIN_INGESTED_PAGES:
            raise InconsistentIngestionRecordError("ingested without pages")

    def _ensure_consistent_failed(self) -> None:
        if self.failure_reason is None:
            raise InconsistentIngestionRecordError("failed without a reason")
        ensure_not_blank(self.failure_reason, "failure_reason")
        if self.page_count != 0:
            raise InconsistentIngestionRecordError("failed with pages")

    @classmethod
    def ingested(cls, document_id: DocumentId, page_count: int) -> "IngestionRecord":
        """Build the record of a successfully ingested document."""
        return cls(document_id, IngestionStatus.INGESTED, page_count)

    @classmethod
    def failed(cls, document_id: DocumentId, reason: str) -> "IngestionRecord":
        """Build the record of a document whose ingestion failed."""
        return cls(document_id, IngestionStatus.FAILED, 0, reason)
