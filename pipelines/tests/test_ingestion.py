import asyncio

import pytest
from dagster import DagsterInstance, build_sensor_context, materialize

from contract_intel.adapters.outbound.in_memory.document_source import (
    InMemoryDocumentSource,
)
from contract_intel.bootstrap.containers import build_writer_container
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.ids import ContractId, DocumentId
from contract_intel.domain.ingestion import IngestionStatus
from contract_intel_pipelines.definitions import CONTAINER_RESOURCE_KEY
from contract_intel_pipelines.ingestion import (
    DOCUMENTS_PARTITIONS_NAME,
    ingested_document,
    pending_documents_sensor,
)

WITH_TEXT = DocumentId("with-text")
BLANK = DocumentId("blank")
CONTENTS = {WITH_TEXT: b"Governing law", BLANK: b""}


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
        yield instance


def _evaluate_sensor(instance, container):
    context = build_sensor_context(
        instance=instance, resources={CONTAINER_RESOURCE_KEY: container}
    )
    return pending_documents_sensor(context)


def _materialize(instance, container, document_id):
    instance.add_dynamic_partitions(DOCUMENTS_PARTITIONS_NAME, [document_id])
    return materialize(
        [ingested_document],
        partition_key=document_id,
        instance=instance,
        resources={CONTAINER_RESOURCE_KEY: container},
        raise_on_error=False,
    )


def test_sensor_registers_and_schedules_new_documents(instance, container):
    result = _evaluate_sensor(instance, container)

    assert sorted(r.partition_key for r in result.run_requests) == [BLANK, WITH_TEXT]
    (add_request,) = result.dynamic_partitions_requests
    assert sorted(add_request.partition_keys) == [BLANK, WITH_TEXT]


def test_sensor_skips_existing_partitions_even_if_failed(instance, container):
    failed = _materialize(instance, container, BLANK)
    assert not failed.success

    result = _evaluate_sensor(instance, container)

    assert [r.partition_key for r in result.run_requests] == [WITH_TEXT]


def test_sensor_requests_nothing_when_all_are_known(instance, container):
    instance.add_dynamic_partitions(DOCUMENTS_PARTITIONS_NAME, [WITH_TEXT, BLANK])

    result = _evaluate_sensor(instance, container)

    assert result.run_requests == []
    assert result.dynamic_partitions_requests == []


def test_asset_ingests_and_reports_metadata(instance, container):
    result = _materialize(instance, container, WITH_TEXT)

    assert result.success
    (materialization,) = result.asset_materializations_for_node("ingested_document")
    assert materialization.metadata["status"].value == "ingested"
    assert materialization.metadata["page_count"].value == 1


def test_asset_fails_visibly_after_recording_failure(instance, container):
    result = _materialize(instance, container, BLANK)

    assert not result.success
    record = asyncio.run(container.document_repository().get_record(BLANK))
    assert record.status is IngestionStatus.FAILED
