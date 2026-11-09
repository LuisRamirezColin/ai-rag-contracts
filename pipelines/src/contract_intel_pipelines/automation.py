"""What runs on its own: the job per document and the sensor that triggers it.

The sensor registers each pending document as a partition and requests one run
of ``ingest_documents_job``, which ingests the document and then vectorizes it.
Only keys that are not partitions yet are scheduled, so a document whose
ingestion failed is retried only when someone re-materializes it explicitly; if
ingestion fails, Dagster skips the dependent vectorization step.
"""

import asyncio

from dagster import (
    DefaultSensorStatus,
    ResourceParam,
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    define_asset_job,
    sensor,
)

from contract_intel.application.ports.inbound.discover_documents import (
    DiscoverDocuments,
)
from contract_intel.bootstrap.writer import WriterContainer
from contract_intel_pipelines.ingestion import (
    DOCUMENTS_PARTITIONS_NAME,
    documents_partitions,
    ingested_document,
)
from contract_intel_pipelines.vectorization import indexed_document

SENSOR_INTERVAL_SECONDS = 60

ingest_documents_job = define_asset_job(
    name="ingest_documents_job",
    selection=[ingested_document, indexed_document],
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
