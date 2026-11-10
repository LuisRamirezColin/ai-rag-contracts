import pytest

from contract_intel.application.ports.inbound.ingest_document import IngestDocument
from contract_intel.application.use_cases.ingest_document import (
    IngestDocumentUseCase,
)
from contract_intel.domain.errors import UnknownDocumentError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.ingestion import NO_EXTRACTABLE_TEXT_REASON, IngestionStatus
from contract_intel.domain.page import Page

from .conftest import make_document, make_source, text_pages

WITH_TEXT = DocumentId("with-text")
BLANK = DocumentId("blank")
CORRUPT = DocumentId("corrupt")
CONTENTS: dict[str, bytes] = {
    WITH_TEXT: text_pages("Recitals", "", "Governing law"),
    BLANK: text_pages("", "   "),
    CORRUPT: b"\xff\xfe not utf-8",
}


@pytest.fixture
def source():
    return make_source(dict(CONTENTS))


@pytest.fixture
def use_case(source, storage, extractor, repository):
    return IngestDocumentUseCase(source, storage, extractor, repository)


def test_satisfies_inbound_port(use_case):
    assert isinstance(use_case, IngestDocument)


async def test_document_with_text_is_ingested(use_case, storage, repository):
    record = await use_case.execute(WITH_TEXT)

    assert record.status is IngestionStatus.INGESTED
    assert record.page_count == 3
    assert await storage.load(WITH_TEXT) == CONTENTS[WITH_TEXT]
    pages = await repository.get_pages(WITH_TEXT)
    assert [p.number for p in pages] == [1, 2, 3]
    assert pages[2].text == "Governing law"


async def test_document_without_text_fails_with_reason(use_case, storage, repository):
    record = await use_case.execute(BLANK)

    assert record.status is IngestionStatus.FAILED
    assert record.failure_reason == NO_EXTRACTABLE_TEXT_REASON
    assert await storage.exists(BLANK)
    assert await repository.ingested_ids() == frozenset()


async def test_unreadable_document_fails(use_case):
    record = await use_case.execute(CORRUPT)

    assert record.status is IngestionStatus.FAILED
    assert record.failure_reason


async def test_a_failure_does_not_stop_the_others(use_case, repository):
    await use_case.execute(BLANK)
    await use_case.execute(WITH_TEXT)

    assert await repository.ingested_ids() == frozenset({WITH_TEXT})


async def test_reingestion_keeps_a_single_set_of_pages(use_case, repository):
    await use_case.execute(WITH_TEXT)
    await use_case.execute(WITH_TEXT)

    assert len(await repository.get_pages(WITH_TEXT)) == 3


async def test_successful_reingestion_clears_previous_failure(
    storage, extractor, repository
):
    await repository.save_failed(make_document(WITH_TEXT), "earlier failure")
    use_case = IngestDocumentUseCase(
        make_source(dict(CONTENTS)), storage, extractor, repository
    )

    record = await use_case.execute(WITH_TEXT)

    assert record.status is IngestionStatus.INGESTED
    assert record.failure_reason is None


async def test_unknown_document_raises(use_case):
    with pytest.raises(UnknownDocumentError):
        await use_case.execute(DocumentId("missing"))


async def test_pages_replace_previous_content(storage, extractor, repository):
    stale = Page(document_id=WITH_TEXT, number=9, text="stale")
    await repository.save_ingested(make_document(WITH_TEXT), (stale,))
    use_case = IngestDocumentUseCase(
        make_source(dict(CONTENTS)), storage, extractor, repository
    )

    await use_case.execute(WITH_TEXT)

    assert [p.number for p in await repository.get_pages(WITH_TEXT)] == [1, 2, 3]
