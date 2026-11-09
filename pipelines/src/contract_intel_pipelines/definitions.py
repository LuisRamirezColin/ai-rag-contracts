"""Dagster entry point: the writer side of the RAG.

Ops and assets obtain use cases from the writer container exposed as the
``container`` resource; they never import outbound adapters directly.
"""

from dagster import Definitions

from contract_intel.bootstrap.containers import build_writer_container

CONTAINER_RESOURCE_KEY = "container"

defs = Definitions(resources={CONTAINER_RESOURCE_KEY: build_writer_container()})
