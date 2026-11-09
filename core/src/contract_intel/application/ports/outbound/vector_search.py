from typing import Protocol, runtime_checkable

from contract_intel.domain.chunk import Embedding, ScoredChunk
from contract_intel.domain.clause_type import ClauseType


@runtime_checkable
class VectorSearch(Protocol):
    """Read side of the vector index; the only index access the API gets."""

    async def search(
        self,
        query: Embedding,
        limit: int,
        clause_types: frozenset[ClauseType] = frozenset(),
    ) -> tuple[ScoredChunk, ...]:
        """Return up to ``limit`` chunks most similar to ``query``, best first.

        An empty ``clause_types`` means no clause-type filter.
        """
        ...
