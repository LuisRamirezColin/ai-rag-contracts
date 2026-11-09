from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contract_intel.adapters.outbound.persistence.models import ChunkRow
from contract_intel.domain.chunk import Chunk, Embedding, ScoredChunk
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.ids import ChunkId, DocumentId
from contract_intel.domain.page import PageRange

MAX_COSINE_SIMILARITY = 1.0


class PgVectorSearch:
    """Read side of the vector index: cosine similarity over pgvector (HNSW)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search(
        self,
        query: Embedding,
        limit: int,
        clause_types: frozenset[ClauseType] = frozenset(),
    ) -> tuple[ScoredChunk, ...]:
        """Return up to ``limit`` chunks most similar to ``query``, best first.

        The score is the cosine similarity; an empty ``clause_types`` means no
        clause-type filter.
        """
        distance = ChunkRow.embedding.cosine_distance(list(query.values)).label(
            "distance"
        )
        statement = select(ChunkRow, distance).order_by(distance).limit(limit)
        if clause_types:
            statement = statement.where(
                ChunkRow.clause_type.in_(sorted(t.value for t in clause_types))
            )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return tuple(
            ScoredChunk(_chunk(row), MAX_COSINE_SIMILARITY - float(dist))
            for row, dist in rows
        )


def _chunk(row: ChunkRow) -> Chunk:
    return Chunk(
        id=ChunkId(row.id),
        document_id=DocumentId(row.document_id),
        text=row.text,
        pages=PageRange(first=row.first_page, last=row.last_page),
        clause_type=None if row.clause_type is None else ClauseType(row.clause_type),
    )
