from contract_intel.application.ports.outbound.document_repository import (
    DocumentRepository,
)
from contract_intel.application.ports.outbound.embedder import Embedder
from contract_intel.application.ports.outbound.usage_tracker import UsageTracker
from contract_intel.application.ports.outbound.vector_index_writer import (
    VectorIndexWriter,
)
from contract_intel.domain.chunk import EmbeddedChunk
from contract_intel.domain.chunking import ChunkingPolicy, chunk_pages
from contract_intel.domain.errors import EmbeddingCountMismatchError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.usage import TokenPricing, UsageRecord

EMBED_DOCUMENTS_OPERATION = "embed_documents"


class VectorizeDocumentUseCase:
    """Chunk an ingested document, embed the chunks and replace them in the index.

    Embeddings are computed before the index is touched, so a provider failure
    leaves the previously indexed chunks intact.
    """

    def __init__(
        self,
        repository: DocumentRepository,
        embedder: Embedder,
        writer: VectorIndexWriter,
        usage_tracker: UsageTracker,
        policy: ChunkingPolicy,
        pricing: TokenPricing,
    ) -> None:
        self._repository = repository
        self._embedder = embedder
        self._writer = writer
        self._usage_tracker = usage_tracker
        self._policy = policy
        self._pricing = pricing

    async def execute(self, document_id: DocumentId) -> int:
        """Index ``document_id`` and return the number of chunks written.

        Raises:
            DocumentNotAvailableError: If the document is missing or not ingested.
        """
        pages = await self._repository.get_pages(document_id)
        chunks = chunk_pages(document_id, pages, self._policy)
        batch = await self._embedder.embed_documents([c.text for c in chunks])
        if len(batch.embeddings) != len(chunks):
            raise EmbeddingCountMismatchError(len(chunks), len(batch.embeddings))
        await self._writer.replace_document(
            document_id,
            [
                EmbeddedChunk(c, e)
                for c, e in zip(chunks, batch.embeddings, strict=True)
            ],
        )
        await self._usage_tracker.record(
            UsageRecord(
                operation=EMBED_DOCUMENTS_OPERATION,
                model=batch.model,
                input_tokens=batch.input_tokens,
                output_tokens=0,
                cost_usd=self._pricing.cost_usd(batch.input_tokens),
                document_id=document_id,
            )
        )
        return len(chunks)
