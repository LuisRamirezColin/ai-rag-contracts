from dataclasses import dataclass

from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.errors import EmptyEmbeddingError
from contract_intel.domain.ids import ChunkId, DocumentId
from contract_intel.domain.page import PageRange
from contract_intel.domain.text import ensure_not_blank


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable slice of document text with its location metadata."""

    id: ChunkId
    document_id: DocumentId
    text: str
    pages: PageRange
    clause_type: ClauseType | None = None

    def __post_init__(self) -> None:
        ensure_not_blank(self.text, "text")


@dataclass(frozen=True, slots=True)
class Embedding:
    """Dense vector representation of a piece of text."""

    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise EmptyEmbeddingError

    @property
    def dimensions(self) -> int:
        """Number of components of the vector."""
        return len(self.values)


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """A chunk paired with its embedding, ready to be indexed."""

    chunk: Chunk
    embedding: Embedding


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A chunk returned by a search with its relevance score (higher is better)."""

    chunk: Chunk
    score: float
