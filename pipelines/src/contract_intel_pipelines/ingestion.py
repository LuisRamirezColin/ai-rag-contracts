"""Writer-side ingestion: one dynamic partition per source document.

The sensor registers each pending document as a partition and requests one run
for it. Only keys that are not partitions yet are scheduled, so a document whose
ingestion failed is retried only when someone re-materializes it explicitly.
"""

import asyncio

from dagster import (
    AssetExecutionContext,
    DefaultSensorStatus,
    DynamicPartitionsDefinition,
    Failure,
    MaterializeResult,
    ResourceParam,
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    asset,
    define_asset_job,
    sensor,
)

from contract_intel.application.ports.inbound.discover_documents import (
    DiscoverDocuments,
)
from contract_intel.application.ports.inbound.ingest_document import IngestDocument
from contract_intel.bootstrap.containers import WriterContainer
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.ingestion import IngestionStatus

DOCUMENTS_PARTITIONS_NAME = "documents"
SENSOR_INTERVAL_SECONDS = 60

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


ingest_documents_job = define_asset_job(
    name="ingest_documents_job",
    selection=[ingested_document],
    partitions_def=documents_partitions,
)


@sensor(
    job=ingest_documents_job,
    minimum_interval_seconds=SENSOR_INTERVAL_SECONDS,
    default_status=DefaultSensorStatus.RUNNING,
)
def pending_documents_sensor(
    context: SensorEvaluationContext, container: ResourceParam[WriterContainer]
) -> SensorResult:
    """Register pending documents as partitions and request one run for each."""
    use_case: DiscoverDocuments = container.discover_documents()
    pending = asyncio.run(use_case.execute())
    known = set(context.instance.get_dynamic_partitions(DOCUMENTS_PARTITIONS_NAME))
    new_keys = [document_id for document_id in pending if document_id not in known]
    return SensorResult(
        run_requests=[RunRequest(partition_key=key) for key in new_keys],
        dynamic_partitions_requests=(
            [documents_partitions.build_add_request(new_keys)] if new_keys else []
        ),
    )
