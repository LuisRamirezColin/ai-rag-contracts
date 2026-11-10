"""Dagster entry point: the writer side of the RAG.

Ops and assets obtain use cases from the writer container exposed as the
``container`` resource; they never import outbound adapters directly.
"""

from dagster import Definitions

from contract_intel.bootstrap.writer import build_writer_container
from contract_intel_pipelines.automation import (
    ingest_documents_job,
    pending_documents_sensor,
)
from contract_intel_pipelines.evaluation import extraction_evaluation
from contract_intel_pipelines.extraction import extracted_clauses
from contract_intel_pipelines.ingestion import ingested_document
from contract_intel_pipelines.vectorization import indexed_document

CONTAINER_RESOURCE_KEY = "container"

defs = Definitions(
    assets=[
        ingested_document,
        extracted_clauses,
        indexed_document,
        extraction_evaluation,
    ],
    jobs=[ingest_documents_job],
    sensors=[pending_documents_sensor],
    resources={CONTAINER_RESOURCE_KEY: build_writer_container()},
)
