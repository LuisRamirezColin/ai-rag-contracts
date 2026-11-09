from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from contract_intel.adapters.outbound.in_memory.document_repository import (
    InMemoryDocumentRepository,
)
from contract_intel.adapters.outbound.persistence.document_repository import (
    SqlAlchemyDocumentRepository,
)
from contract_intel.application.ports.outbound.document_repository import (
    DocumentRepository,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.errors import DocumentNotAvailableError
from contract_intel.domain.ids import ContractId, DocumentId
from contract_intel.domain.ingestion import IngestionRecord, IngestionStatus
from contract_intel.domain.page import Page

DOC = Document(DocumentId("doc-1"), ContractId("doc-1"), "Doc one", DocumentType.OTHER)
OTHER = Document(
    DocumentId("doc-2"), ContractId("doc-2"), "Doc two", DocumentType.OTHER
)


def pages_of(document: Document, *texts: str) -> tuple[Page, ...]:
    return tuple(
        Page(document_id=document.id, number=n, text=t)
        for n, t in enumerate(texts, start=1)
    )


@pytest.fixture
async def postgres_repository() -> AsyncIterator[SqlAlchemyDocumentRepository]:
    engine = create_async_engine(AppSettings().database.url, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE documents CASCADE"))
    yield SqlAlchemyDocumentRepository(async_sessionmaker(engine))
    await engine.dispose()


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repository(request: pytest.FixtureRequest) -> DocumentRepository:
    if request.param == "postgres":
        real: DocumentRepository = request.getfixturevalue("postgres_repository")
        return real
    return InMemoryDocumentRepository()


async def test_ingested_document_has_record_and_ordered_pages(repository):
    pages = pages_of(DOC, "one", "two", "three")
    await repository.save_ingested(DOC, tuple(reversed(pages)))

    assert await repository.get_record(DOC.id) == IngestionRecord.ingested(DOC.id, 3)
    assert await repository.get_pages(DOC.id) == pages
    assert await repository.ingested_ids() == frozenset({DOC.id})


async def test_unknown_document_has_no_record(repository):
    assert await repository.get_record(DOC.id) is None
    with pytest.raises(DocumentNotAvailableError):
        await repository.get_pages(DOC.id)


async def test_failed_document_has_reason_and_no_pages(repository):
    await repository.save_failed(DOC, "no extractable text")

    record = await repository.get_record(DOC.id)
    assert record == IngestionRecord.failed(DOC.id, "no extractable text")
    assert await repository.ingested_ids() == frozenset()
    with pytest.raises(DocumentNotAvailableError):
        await repository.get_pages(DOC.id)


async def test_reingestion_replaces_pages(repository):
    await repository.save_ingested(DOC, pages_of(DOC, "old 1", "old 2", "old 3"))
    await repository.save_ingested(DOC, pages_of(DOC, "new 1"))

    assert await repository.get_pages(DOC.id) == pages_of(DOC, "new 1")


async def test_failure_after_ingestion_drops_pages(repository):
    await repository.save_ingested(DOC, pages_of(DOC, "text"))
    await repository.save_failed(DOC, "unreadable")

    with pytest.raises(DocumentNotAvailableError):
        await repository.get_pages(DOC.id)


async def test_ingestion_after_failure_clears_reason(repository):
    await repository.save_failed(DOC, "unreadable")
    await repository.save_ingested(DOC, pages_of(DOC, "text"))

    record = await repository.get_record(DOC.id)
    assert record is not None
    assert record.status is IngestionStatus.INGESTED
    assert record.failure_reason is None


async def test_documents_are_independent(repository):
    await repository.save_ingested(DOC, pages_of(DOC, "a"))
    await repository.save_ingested(OTHER, pages_of(OTHER, "b", "c"))
    await repository.save_failed(DOC, "boom")

    assert len(await repository.get_pages(OTHER.id)) == 2
    assert await repository.ingested_ids() == frozenset({OTHER.id})


async def test_nul_characters_are_dropped(repository):
    await repository.save_ingested(DOC, pages_of(DOC, "gov\x00erning law"))

    assert (await repository.get_pages(DOC.id))[0].text == "governing law"
