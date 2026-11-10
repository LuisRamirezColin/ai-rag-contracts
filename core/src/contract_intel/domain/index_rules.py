from collections.abc import Sequence

from contract_intel.domain.chunk import EmbeddedChunk
from contract_intel.domain.errors import (
    ChunkDocumentMismatchError,
    EmbeddingDimensionMismatchError,
)
from contract_intel.domain.ids import DocumentId


def ensure_writable(
    document_id: DocumentId, chunks: Sequence[EmbeddedChunk], dimensions: int | None
) -> None:
    """Check that ``chunks`` can replace the chunks of ``document_id``.

    Raises:
        ChunkDocumentMismatchError: If a chunk belongs to another document.
        EmbeddingDimensionMismatchError: If ``dimensions`` is given and a vector
            does not have it.
    """
    for embedded in chunks:
        if embedded.chunk.document_id != document_id:
            raise ChunkDocumentMismatchError(document_id, embedded.chunk.document_id)
        actual = embedded.embedding.dimensions
        if dimensions is not None and actual != dimensions:
            raise EmbeddingDimensionMismatchError(dimensions, actual)
