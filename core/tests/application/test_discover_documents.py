import pytest

from contract_intel.application.ports.inbound.discover_documents import (
    DiscoverDocuments,
)
from contract_intel.application.use_cases.discover_documents import (
    DiscoverDocumentsUseCase,
)
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import Page

from .conftest import make_document, make_source, text_pages

SOURCE_IDS = ["doc-c", "doc-a", "doc-e", "doc-b", "doc-d"]


@pytest.fixture
def source():
    return make_source({i: text_pages("text") for i in SOURCE_IDS})


def test_satisfies_inbound_port(source, repository):
    use_case: DiscoverDocuments = DiscoverDocumentsUseCase(source, repository, 5)
    assert isinstance(use_case, DiscoverDocuments)


async def test_limit_applies_to_source_in_id_order(source, repository):
    use_case = DiscoverDocumentsUseCase(source, repository, max_documents=3)

    assert await use_case.execute() == ("doc-a", "doc-b", "doc-c")


async def test_order_is_stable_between_runs(source, repository):
    use_case = DiscoverDocumentsUseCase(source, repository, max_documents=5)

    assert await use_case.execute() == await use_case.execute()


async def test_ingested_documents_are_excluded(source, repository):
    page = Page(document_id=DocumentId("doc-a"), number=1, text="text")
    await repository.save_ingested(make_document("doc-a"), (page,))
    use_case = DiscoverDocumentsUseCase(source, repository, max_documents=2)

    assert await use_case.execute() == (DocumentId("doc-b"),)


async def test_failed_documents_stay_pending(source, repository):
    await repository.save_failed(make_document("doc-a"), "no extractable text")
    use_case = DiscoverDocumentsUseCase(source, repository, max_documents=1)

    assert await use_case.execute() == (DocumentId("doc-a"),)


def test_rejects_non_positive_limit(source, repository):
    with pytest.raises(ValueError, match="max_documents"):
        DiscoverDocumentsUseCase(source, repository, max_documents=0)
