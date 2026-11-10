"""Writer-side ingestion asset: one dynamic partition per source document."""

import asyncio

from dagster import (
    AssetExecutionContext,
    DynamicPartitionsDefinition,
    Failure,
    MaterializeResult,
    ResourceParam,
    asset,
)

from contract_intel.application.ports.inbound.ingest_document import IngestDocument
from contract_intel.bootstrap.writer import WriterContainer
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.ingestion import IngestionStatus

DOCUMENTS_PARTITIONS_NAME = "documents"

documents_partitions = DynamicPartitionsDefinition(name=DOCUMENTS_PARTITIONS_NAME)


@asset(partitions_def=documents_partitions)
def ingested_document(
    context: AssetExecutionContext, container: ResourceParam[WriterContainer]
) -> MaterializeResult:  # type: ignore[type-arg]
    """Original file stored, page text extracted and ingestion state recorded."""
    use_case: IngestDocument = container.ingest_document()
    record = asyncio.run(use_case.execute(DocumentId(context.partition_key)))
    metadata = {"status": record.status.value, "page_count": record.page_count}
    if record.status is IngestionStatus.FAILED:
        raise Failure(description=record.failure_reason, metadata=metadata)
    return MaterializeResult(metadata=metadata)
