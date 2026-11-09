import pytest

from contract_intel.domain.errors import (
    BlankTextError,
    InconsistentIngestionRecordError,
)
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.ingestion import (
    IngestionRecord,
    IngestionStatus,
    has_extractable_text,
)
from contract_intel.domain.page import Page

DOC = DocumentId("doc-1")


def _pages(*texts: str) -> tuple[Page, ...]:
    return tuple(
        Page(document_id=DOC, number=n, text=t) for n, t in enumerate(texts, start=1)
    )


class TestHasExtractableText:
    def test_true_when_any_page_has_text(self):
        assert has_extractable_text(_pages("", "Governing law"))

    @pytest.mark.parametrize("texts", [(), ("",), ("   ", "\n\t")])
    def test_false_for_no_pages_or_blank_pages(self, texts):
        assert not has_extractable_text(_pages(*texts))


class TestIngestedRecord:
    def test_valid(self):
        record = IngestionRecord.ingested(DOC, page_count=3)
        assert record.status is IngestionStatus.INGESTED
        assert record.failure_reason is None

    def test_rejects_zero_pages(self):
        with pytest.raises(InconsistentIngestionRecordError):
            IngestionRecord.ingested(DOC, page_count=0)

    def test_rejects_failure_reason(self):
        with pytest.raises(InconsistentIngestionRecordError):
            IngestionRecord(DOC, IngestionStatus.INGESTED, 2, "boom")


class TestFailedRecord:
    def test_valid(self):
        record = IngestionRecord.failed(DOC, "no extractable text")
        assert record.status is IngestionStatus.FAILED
        assert record.page_count == 0

    def test_rejects_missing_reason(self):
        with pytest.raises(InconsistentIngestionRecordError):
            IngestionRecord(DOC, IngestionStatus.FAILED, 0)

    def test_rejects_blank_reason(self):
        with pytest.raises(BlankTextError):
            IngestionRecord.failed(DOC, "  ")

    def test_rejects_pages(self):
        with pytest.raises(InconsistentIngestionRecordError):
            IngestionRecord(DOC, IngestionStatus.FAILED, 1, "boom")
