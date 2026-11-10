import pytest
from dagster import AssetKey, DagsterInstance, materialize

from contract_intel.adapters.outbound.in_memory.clause_extractor import (
    InMemoryClauseExtractor,
)
from contract_intel.adapters.outbound.in_memory.document_source import (
    InMemoryDocumentSource,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.bootstrap.writer import build_writer_container
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.errors import ProviderUnavailableError
from contract_intel.domain.ids import ClauseId, ContractId, DocumentId
from contract_intel.domain.page import PageRange
from contract_intel_pipelines.definitions import CONTAINER_RESOURCE_KEY, defs
from contract_intel_pipelines.extraction import extracted_clauses
from contract_intel_pipelines.ingestion import (
    DOCUMENTS_PARTITIONS_NAME,
    ingested_document,
)
from contract_intel_pipelines.vectorization import indexed_document

DOC = DocumentId("msa")
LAW_TEXT = "This Agreement shall be governed by the laws of the State of Delaware."
LAW = Clause(
    ClauseId("msa:governing_law:000"),
    DOC,
    ClauseType.GOVERNING_LAW,
    LAW_TEXT,
    PageRange(1, 1),
)
ALL_ASSETS = [ingested_document, extracted_clauses, indexed_document]


class DownExtractor(InMemoryClauseExtractor):
    async def extract(self, document, pages):
        raise ProviderUnavailableError("anthropic", "overloaded")


@pytest.fixture
def container():
    container = build_writer_container(AppSettings(_env_file=None, use_fakes=True))
    document = Document(DOC, ContractId(DOC), "MSA", DocumentType.OTHER)
    container.document_source.override(
        InMemoryDocumentSource({DOC: (document, LAW_TEXT.encode())})
    )
    container.clause_extractor.override(InMemoryClauseExtractor({DOC: (LAW,)}))
    return container


@pytest.fixture
def instance():
    with DagsterInstance.ephemeral() as instance:
        instance.add_dynamic_partitions(DOCUMENTS_PARTITIONS_NAME, [DOC])
        yield instance


def _run(instance, container):
    return materialize(
        ALL_ASSETS,
        partition_key=DOC,
        instance=instance,
        resources={CONTAINER_RESOURCE_KEY: container},
        raise_on_error=False,
    )


def test_job_runs_ingest_then_extract_then_index():
    job = defs.resolve_job_def("ingest_documents_job")

    assert {"ingested_document", "extracted_clauses", "indexed_document"} <= set(
        job.graph.node_names()
    )
    assert AssetKey("extracted_clauses") in indexed_document.dependency_keys
    assert AssetKey("ingested_document") in extracted_clauses.dependency_keys


def test_chunks_are_born_labelled(instance, container):
    result = _run(instance, container)

    assert result.success
    (materialization,) = result.asset_materializations_for_node("extracted_clauses")
    assert materialization.metadata["clause_count"].value == 1
    (entry,) = container.core.vector_store().entries.values()
    assert entry.chunk.clause_types == {ClauseType.GOVERNING_LAW}


def test_failed_extraction_skips_vectorization(instance, container):
    container.clause_extractor.override(DownExtractor())

    result = _run(instance, container)

    assert not result.success
    assert result.asset_materializations_for_node("indexed_document") == []
    assert container.core.vector_store().entries == {}
