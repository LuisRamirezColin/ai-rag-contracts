from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from dataclasses import replace as replace_chunk

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorIndexWriter,
    InMemoryVectorStore,
)
from contract_intel.adapters.outbound.persistence.document_repository import (
    SqlAlchemyDocumentRepository,
)
from contract_intel.adapters.outbound.persistence.models import (
    EMBEDDING_DIMENSIONS,
    ChunkClauseTypeRow,
    ChunkRow,
)
from contract_intel.adapters.outbound.persistence.vector_index_writer import (
    PgVectorIndexWriter,
)
from contract_intel.application.ports.outbound.vector_index_writer import (
    VectorIndexWriter,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.chunk import Chunk, EmbeddedChunk, Embedding
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.errors import (
    ChunkDocumentMismatchError,
    EmbeddingDimensionMismatchError,
)
from contract_intel.domain.ids import ChunkId, ContractId, DocumentId
from contract_intel.domain.page import Page, PageRange

DOC_A = DocumentId("doc-a")
DOC_B = DocumentId("doc-b")
MODEL = "test-model"

Stored = list[tuple[str, str, int, int]]


Labels = dict[str, frozenset[ClauseType]]


@dataclass(frozen=True)
class WriterCase:
    writer: VectorIndexWriter
    read: Callable[[DocumentId], Awaitable[Stored]]
    labels: Callable[[DocumentId], Awaitable[Labels]]


def embedded(document_id, ordinal, body, pages=(1, 1), dims=EMBEDDING_DIMENSIONS):
    chunk = Chunk(
        id=ChunkId(f"{document_id}:{ordinal:04d}"),
        document_id=document_id,
        text=body,
        pages=PageRange(*pages),
    )
    return EmbeddedChunk(chunk, Embedding(values=(0.01 * (ordinal + 1),) * dims))


def _in_memory_case() -> WriterCase:
    store = InMemoryVectorStore()

    async def read(document_id: DocumentId) -> Stored:
        return sorted(
            (e.chunk.id, e.chunk.text, e.chunk.pages.first, e.chunk.pages.last)
            for e in store.entries.values()
            if e.chunk.document_id == document_id
        )

    async def labels(document_id: DocumentId) -> Labels:
        return {
            e.chunk.id: e.chunk.clause_types
            for e in store.entries.values()
            if e.chunk.document_id == document_id
        }

    return WriterCase(
        InMemoryVectorIndexWriter(store, EMBEDDING_DIMENSIONS), read, labels
    )


@pytest.fixture
async def postgres_case() -> AsyncIterator[WriterCase]:
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

    async def read(document_id: DocumentId) -> Stored:
        query = select(
            ChunkRow.id, ChunkRow.text, ChunkRow.first_page, ChunkRow.last_page
        ).where(ChunkRow.document_id == document_id)
        async with sessions() as session:
            rows = (await session.execute(query)).all()
        return sorted((r[0], r[1], r[2], r[3]) for r in rows)

    async def labels(document_id: DocumentId) -> Labels:
        found: dict[str, set[ClauseType]] = {}
        query = (
            select(ChunkRow.id, ChunkClauseTypeRow.clause_type)
            .outerjoin(ChunkClauseTypeRow, ChunkClauseTypeRow.chunk_id == ChunkRow.id)
            .where(ChunkRow.document_id == document_id)
        )
        async with sessions() as session:
            for chunk_id, clause_type in (await session.execute(query)).all():
                found.setdefault(chunk_id, set())
                if clause_type is not None:
                    found[chunk_id].add(ClauseType(clause_type))
        return {k: frozenset(v) for k, v in found.items()}

    yield WriterCase(PgVectorIndexWriter(sessions, MODEL), read, labels)
    await engine.dispose()


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def case(request: pytest.FixtureRequest) -> WriterCase:
    if request.param == "postgres":
        real: WriterCase = request.getfixturevalue("postgres_case")
        return real
    return _in_memory_case()


async def test_replace_writes_exactly_the_given_chunks(case):
    await case.writer.replace_document(
        DOC_A, [embedded(DOC_A, 0, "one"), embedded(DOC_A, 1, "two", (1, 2))]
    )

    assert await case.read(DOC_A) == [
        ("doc-a:0000", "one", 1, 1),
        ("doc-a:0001", "two", 1, 2),
    ]


async def test_replace_drops_previous_chunks(case):
    await case.writer.replace_document(
        DOC_A, [embedded(DOC_A, i, f"old {i}") for i in range(3)]
    )

    await case.writer.replace_document(DOC_A, [embedded(DOC_A, 0, "new")])

    assert await case.read(DOC_A) == [("doc-a:0000", "new", 1, 1)]


async def test_other_documents_are_isolated(case):
    await case.writer.replace_document(DOC_B, [embedded(DOC_B, 0, "b")])

    await case.writer.replace_document(DOC_A, [embedded(DOC_A, 0, "a")])
    await case.writer.delete_document(DOC_A)

    assert await case.read(DOC_A) == []
    assert await case.read(DOC_B) == [("doc-b:0000", "b", 1, 1)]


async def test_chunks_of_another_document_are_rejected(case):
    await case.writer.replace_document(DOC_A, [embedded(DOC_A, 0, "kept")])

    with pytest.raises(ChunkDocumentMismatchError):
        await case.writer.replace_document(DOC_A, [embedded(DOC_B, 0, "foreign")])

    assert await case.read(DOC_A) == [("doc-a:0000", "kept", 1, 1)]


async def test_wrong_dimension_is_rejected(case):
    await case.writer.replace_document(DOC_A, [embedded(DOC_A, 0, "kept")])

    with pytest.raises(EmbeddingDimensionMismatchError):
        await case.writer.replace_document(
            DOC_A, [embedded(DOC_A, 0, "short", dims=EMBEDDING_DIMENSIONS - 1)]
        )

    assert await case.read(DOC_A) == [("doc-a:0000", "kept", 1, 1)]


async def test_replace_with_no_chunks_empties_the_document(case):
    await case.writer.replace_document(DOC_A, [embedded(DOC_A, 0, "a")])

    await case.writer.replace_document(DOC_A, [])

    assert await case.read(DOC_A) == []


@pytest.mark.integration
async def test_postgres_failure_mid_insert_keeps_previous_chunks(postgres_case):
    await postgres_case.writer.replace_document(DOC_A, [embedded(DOC_A, 0, "kept")])
    # Postgres rejects NUL in text columns: the insert fails after the delete ran.
    broken = [embedded(DOC_A, 0, "fine"), embedded(DOC_A, 1, "bro\x00ken")]

    with pytest.raises(DBAPIError):
        await postgres_case.writer.replace_document(DOC_A, broken)

    assert await postgres_case.read(DOC_A) == [("doc-a:0000", "kept", 1, 1)]


def labelled(document_id, ordinal, body, *types):
    item = embedded(document_id, ordinal, body)
    return EmbeddedChunk(
        replace_chunk(item.chunk, clause_types=frozenset(types)), item.embedding
    )


async def test_clause_types_are_stored_and_replaced(case):
    law, cap = ClauseType.GOVERNING_LAW, ClauseType.CAP_ON_LIABILITY
    await case.writer.replace_document(
        DOC_A, [labelled(DOC_A, 0, "both", law, cap), labelled(DOC_A, 1, "none")]
    )
    assert await case.labels(DOC_A) == {
        "doc-a:0000": frozenset({law, cap}),
        "doc-a:0001": frozenset(),
    }

    await case.writer.replace_document(DOC_A, [labelled(DOC_A, 0, "law only", law)])

    assert await case.labels(DOC_A) == {"doc-a:0000": frozenset({law})}
