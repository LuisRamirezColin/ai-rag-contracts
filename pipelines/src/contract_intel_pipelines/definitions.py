"""Dagster entry point: the writer side of the RAG.

Ops and assets obtain use cases from the writer container exposed as the
``container`` resource; they never import outbound adapters directly.
"""

from dagster import Definitions

from contract_intel.bootstrap.containers import build_writer_container
from contract_intel_pipelines.ingestion import (
    ingest_documents_job,
    ingested_document,
    pending_documents_sensor,
)

CONTAINER_RESOURCE_KEY = "container"

defs = Definitions(
    assets=[ingested_document],
    jobs=[ingest_documents_job],
    sensors=[pending_documents_sensor],
    resources={CONTAINER_RESOURCE_KEY: build_writer_container()},
)
