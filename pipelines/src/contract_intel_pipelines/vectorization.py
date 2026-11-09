"""Writer-side vectorization asset: chunks and embeddings of an ingested document."""

import asyncio

from dagster import AssetExecutionContext, MaterializeResult, ResourceParam, asset

from contract_intel.application.ports.inbound.vectorize_document import (
    VectorizeDocument,
)
from contract_intel.bootstrap.writer import WriterContainer
from contract_intel.domain.ids import DocumentId
from contract_intel_pipelines.ingestion import documents_partitions, ingested_document


@asset(partitions_def=documents_partitions, deps=[ingested_document])
def indexed_document(
    context: AssetExecutionContext, container: ResourceParam[WriterContainer]
) -> MaterializeResult:  # type: ignore[type-arg]
    """Chunks of the document with their embeddings, written to the vector index."""
    use_case: VectorizeDocument = container.vectorize_document()
    chunk_count = asyncio.run(use_case.execute(DocumentId(context.partition_key)))
    return MaterializeResult(metadata={"chunk_count": chunk_count})
