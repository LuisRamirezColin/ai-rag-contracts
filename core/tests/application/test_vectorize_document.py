import pytest

from contract_intel.adapters.outbound.in_memory.embedder import (
    IN_MEMORY_MODEL,
    InMemoryEmbedder,
)
from contract_intel.adapters.outbound.in_memory.usage_tracker import (
    InMemoryUsageTracker,
)
from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorIndexWriter,
    InMemoryVectorStore,
)
from contract_intel.application.ports.inbound.vectorize_document import (
    VectorizeDocument,
)
from contract_intel.application.use_cases.vectorize_document import (
    EMBED_DOCUMENTS_OPERATION,
    VectorizeDocumentUseCase,
)
from contract_intel.domain.chunking import ChunkingPolicy
from contract_intel.domain.errors import DocumentNotAvailableError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import Page
from contract_intel.domain.usage import TokenPricing

from .conftest import make_document

DOC = DocumentId("doc-a")
OTHER = DocumentId("doc-b")
POLICY = ChunkingPolicy(max_chars=200, overlap_chars=40)
PRICING = TokenPricing(input_per_million=0.12)


def _pages(document_id: DocumentId, words: int) -> tuple[Page, ...]:
    text = " ".join(f"w{i:04d}" for i in range(words))
    return (Page(document_id=document_id, number=1, text=text),)


class FailingEmbedder(InMemoryEmbedder):
    async def embed_documents(self, texts):
        raise ConnectionError("provider down")


@pytest.fixture
def store():
    return InMemoryVectorStore()


@pytest.fixture
def tracker():
    return InMemoryUsageTracker()


def _use_case(repository, store, tracker, embedder=None):
    return VectorizeDocumentUseCase(
        repository,
        embedder or InMemoryEmbedder(),
        InMemoryVectorIndexWriter(store),
        tracker,
        POLICY,
        PRICING,
    )


def _chunks_of(store, document_id):
    return sorted(
        e.chunk.id for e in store.entries.values() if e.chunk.document_id == document_id
    )


async def _ingest(repository, document_id, words):
    await repository.save_ingested(
        make_document(document_id), _pages(document_id, words)
    )


def test_satisfies_inbound_port(repository, store, tracker):
    assert isinstance(_use_case(repository, store, tracker), VectorizeDocument)


async def test_indexes_chunks_and_returns_their_count(repository, store, tracker):
    await _ingest(repository, DOC, words=200)

    count = await _use_case(repository, store, tracker).execute(DOC)

    assert count > 1
    assert len(_chunks_of(store, DOC)) == count


async def test_records_usage_for_the_document(repository, store, tracker):
    await _ingest(repository, DOC, words=200)

    await _use_case(repository, store, tracker).execute(DOC)

    (usage,) = tracker.records
    assert usage.operation == EMBED_DOCUMENTS_OPERATION
    assert usage.model == IN_MEMORY_MODEL
    assert usage.document_id == DOC
    assert usage.input_tokens > 0
    assert usage.cost_usd == pytest.approx(PRICING.cost_usd(usage.input_tokens))


@pytest.mark.parametrize("state", ["missing", "failed"])
async def test_unavailable_document_leaves_index_untouched(
    repository, store, tracker, state
):
    if state == "failed":
        await repository.save_failed(make_document(DOC), "no extractable text")

    with pytest.raises(DocumentNotAvailableError):
        await _use_case(repository, store, tracker).execute(DOC)

    assert store.entries == {}
    assert tracker.records == []


async def test_provider_failure_keeps_previous_chunks(repository, store, tracker):
    await _ingest(repository, DOC, words=200)
    await _use_case(repository, store, tracker).execute(DOC)
    before = dict(store.entries)

    with pytest.raises(ConnectionError):
        await _use_case(repository, store, tracker, FailingEmbedder()).execute(DOC)

    assert store.entries == before


async def test_revectorization_keeps_only_the_new_chunks(repository, store, tracker):
    await _ingest(repository, DOC, words=300)
    use_case = _use_case(repository, store, tracker)
    await use_case.execute(DOC)

    await _ingest(repository, DOC, words=20)
    count = await use_case.execute(DOC)

    assert count == 1
    assert _chunks_of(store, DOC) == ["doc-a:0000"]


async def test_other_documents_are_not_touched(repository, store, tracker):
    await _ingest(repository, DOC, words=100)
    await _ingest(repository, OTHER, words=100)
    use_case = _use_case(repository, store, tracker)
    await use_case.execute(OTHER)
    other_before = _chunks_of(store, OTHER)

    await use_case.execute(DOC)

    assert _chunks_of(store, OTHER) == other_before
