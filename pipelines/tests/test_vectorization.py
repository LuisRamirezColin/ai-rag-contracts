import pytest
from dagster import DagsterInstance, materialize

from contract_intel.adapters.outbound.in_memory.document_source import (
    InMemoryDocumentSource,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.bootstrap.writer import build_writer_container
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.ids import ContractId, DocumentId
from contract_intel_pipelines.definitions import CONTAINER_RESOURCE_KEY, defs
from contract_intel_pipelines.ingestion import (
    DOCUMENTS_PARTITIONS_NAME,
    ingested_document,
)
from contract_intel_pipelines.vectorization import indexed_document

WITH_TEXT = DocumentId("with-text")
BLANK = DocumentId("blank")
CONTENTS = {WITH_TEXT: b"Governing law. " * 300, BLANK: b""}


def _document(document_id: DocumentId) -> Document:
    return Document(
        document_id, ContractId(document_id), document_id, DocumentType.OTHER
    )


@pytest.fixture
def container():
    container = build_writer_container(AppSettings(_env_file=None, use_fakes=True))
    container.document_source.override(
        InMemoryDocumentSource(
            {i: (_document(i), content) for i, content in CONTENTS.items()}
        )
    )
    return container


@pytest.fixture
def instance():
    with DagsterInstance.ephemeral() as instance:
        instance.add_dynamic_partitions(DOCUMENTS_PARTITIONS_NAME, [WITH_TEXT, BLANK])
        yield instance


def _run(instance, container, assets, document_id):
    return materialize(
        assets,
        partition_key=document_id,
        instance=instance,
        resources={CONTAINER_RESOURCE_KEY: container},
        raise_on_error=False,
    )


def _chunk_ids(container, document_id):
    return sorted(
        e.chunk.id
        for e in container.core.vector_store().entries.values()
        if e.chunk.document_id == document_id
    )


def test_the_sensor_job_ingests_then_vectorizes():
    job = defs.resolve_job_def("ingest_documents_job")

    assert {"ingested_document", "indexed_document"} <= set(job.graph.node_names())


def test_ingestion_and_vectorization_run_in_order(instance, container):
    result = _run(instance, container, [ingested_document, indexed_document], WITH_TEXT)

    assert result.success
    (materialization,) = result.asset_materializations_for_node("indexed_document")
    chunk_count = materialization.metadata["chunk_count"].value
    assert chunk_count > 1
    assert len(_chunk_ids(container, WITH_TEXT)) == chunk_count


def test_failed_ingestion_skips_vectorization(instance, container):
    result = _run(instance, container, [ingested_document, indexed_document], BLANK)

    assert not result.success
    assert result.asset_materializations_for_node("indexed_document") == []
    assert _chunk_ids(container, BLANK) == []


def test_materializing_only_the_index_revectorizes(instance, container):
    _run(instance, container, [ingested_document, indexed_document], WITH_TEXT)
    calls_before = container.core.embedder().document_calls

    result = _run(instance, container, [indexed_document], WITH_TEXT)

    assert result.success
    assert container.core.embedder().document_calls == calls_before + 1
