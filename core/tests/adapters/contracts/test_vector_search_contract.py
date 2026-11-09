from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorIndexWriter,
    InMemoryVectorSearch,
    InMemoryVectorStore,
)
from contract_intel.adapters.outbound.persistence.document_repository import (
    SqlAlchemyDocumentRepository,
)
from contract_intel.adapters.outbound.persistence.models import EMBEDDING_DIMENSIONS
from contract_intel.adapters.outbound.persistence.vector_index_writer import (
    PgVectorIndexWriter,
)
from contract_intel.adapters.outbound.persistence.vector_search import PgVectorSearch
from contract_intel.application.ports.outbound.vector_search import VectorSearch
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.chunk import Chunk, EmbeddedChunk, Embedding
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.ids import ChunkId, ContractId, DocumentId
from contract_intel.domain.page import Page, PageRange

DOC_A = DocumentId("doc-a")
DOC_B = DocumentId("doc-b")

Seed = Callable[[DocumentId, Sequence[EmbeddedChunk]], Awaitable[None]]


def axis(*weights: float) -> Embedding:
    """A vector with the given leading components and zeros elsewhere."""
    values = list(weights) + [0.0] * (EMBEDDING_DIMENSIONS - len(weights))
    return Embedding(values=tuple(values))


def embedded(document_id, ordinal, vector, clause_type=None, pages=(1, 1)):
    chunk = Chunk(
        ChunkId(f"{document_id}:{ordinal:04d}"),
        document_id,
        f"text of {document_id} #{ordinal}",
        PageRange(*pages),
        clause_type,
    )
    return EmbeddedChunk(chunk, vector)


# Similarity to the query axis(1, 0, 0): exact > close > orthogonal.
EXACT = embedded(DOC_A, 0, axis(1.0, 0.0, 0.0), ClauseType.GOVERNING_LAW, (3, 4))
CLOSE = embedded(DOC_A, 1, axis(0.8, 0.6, 0.0), ClauseType.NON_COMPETE)
ORTHOGONAL = embedded(DOC_B, 0, axis(0.0, 0.0, 1.0), None, (7, 9))
QUERY = axis(1.0, 0.0, 0.0)


@dataclass(frozen=True)
class SearchCase:
    search: VectorSearch
    seed: Seed


def _in_memory_case() -> SearchCase:
    store = InMemoryVectorStore()
    writer = InMemoryVectorIndexWriter(store)
    return SearchCase(InMemoryVectorSearch(store), writer.replace_document)


@pytest.fixture
async def postgres_case() -> AsyncIterator[SearchCase]:
    engine = create_async_engine(AppSettings().database.url, poolclass=NullPool)
    sessions = async_sessionmaker(engine)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE documents CASCADE"))
    repository = SqlAlchemyDocumentRepository(sessions)
    for document_id in (DOC_A, DOC_B):
        document = Document(
            document_id, ContractId(document_id), document_id, DocumentType.OTHER
        )
        await repository.save_ingested(document, (Page(document_id, 1, "text"),))
    writer = PgVectorIndexWriter(sessions, "test-model")
    yield SearchCase(PgVectorSearch(sessions), writer.replace_document)
    await engine.dispose()


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def case(request: pytest.FixtureRequest) -> SearchCase:
    if request.param == "postgres":
        real: SearchCase = request.getfixturevalue("postgres_case")
        return real
    return _in_memory_case()


async def _seed_all(case: SearchCase) -> None:
    await case.seed(DOC_A, [EXACT, CLOSE])
    await case.seed(DOC_B, [ORTHOGONAL])


async def test_results_are_ordered_by_similarity(case):
    await _seed_all(case)

    results = await case.search.search(QUERY, limit=3)

    assert [r.chunk.id for r in results] == [
        EXACT.chunk.id,
        CLOSE.chunk.id,
        ORTHOGONAL.chunk.id,
    ]
    assert results[0].score == pytest.approx(1.0)
    assert results[1].score == pytest.approx(0.8)
    assert results[2].score == pytest.approx(0.0, abs=1e-6)


async def test_limit_caps_the_results(case):
    await _seed_all(case)

    results = await case.search.search(QUERY, limit=1)

    assert [r.chunk.id for r in results] == [EXACT.chunk.id]


async def test_clause_type_filter(case):
    await _seed_all(case)

    results = await case.search.search(
        QUERY, limit=3, clause_types=frozenset({ClauseType.NON_COMPETE})
    )

    assert [r.chunk.id for r in results] == [CLOSE.chunk.id]


async def test_empty_index_returns_nothing(case):
    assert await case.search.search(QUERY, limit=5) == ()


async def test_chunk_fields_are_reconstructed(case):
    await _seed_all(case)

    results = await case.search.search(axis(0.0, 0.0, 1.0), limit=1)

    (best,) = results
    assert best.chunk == ORTHOGONAL.chunk
    assert best.chunk.pages == PageRange(7, 9)
