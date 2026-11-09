import socket

import pytest

from contract_intel.adapters.outbound.in_memory.document_source import (
    InMemoryDocumentSource,
)
from contract_intel.application.ports.inbound.discover_documents import (
    DiscoverDocuments,
)
from contract_intel.application.ports.inbound.ingest_document import IngestDocument
from contract_intel.application.ports.outbound.document_repository import (
    DocumentRepository,
)
from contract_intel.application.ports.outbound.document_source import DocumentSource
from contract_intel.application.ports.outbound.document_storage import DocumentStorage
from contract_intel.application.ports.outbound.text_extractor import TextExtractor
from contract_intel.application.ports.outbound.vector_index_writer import (
    VectorIndexWriter,
)
from contract_intel.application.ports.outbound.vector_search import VectorSearch
from contract_intel.bootstrap.containers import (
    ReaderContainer,
    RealAdaptersUnavailableError,
    WriterContainer,
    build_reader_container,
    build_writer_container,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.ids import ContractId, DocumentId
from contract_intel.domain.ingestion import IngestionStatus

INGESTION_PORTS = {
    "document_source": DocumentSource,
    "document_storage": DocumentStorage,
    "text_extractor": TextExtractor,
    "document_repository": DocumentRepository,
}
NOT_YET_REAL_WRITER_PORTS = ["clause_extractor", "vector_index_writer"]
NOT_YET_REAL_READER_PORTS = ["vector_search", "answer_generator"]


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def fake_settings():
    return AppSettings(_env_file=None, use_fakes=True)


@pytest.fixture
def real_settings():
    return AppSettings(_env_file=None, use_fakes=False)


def _resolve_all(container):
    resolved = []
    for name, provider in container.providers.items():
        if name == "core":
            resolved.extend(_resolve_all(container.core))
        elif name not in {"settings", "mode"}:
            resolved.append(provider())
    return resolved


def test_writer_container_builds_without_network(no_network, fake_settings):
    instances = _resolve_all(build_writer_container(fake_settings))
    assert any(isinstance(i, VectorIndexWriter) for i in instances)


def test_reader_container_builds_without_network(no_network, fake_settings):
    instances = _resolve_all(build_reader_container(fake_settings))
    assert any(isinstance(i, VectorSearch) for i in instances)


def test_reader_container_resolves_no_index_writer(fake_settings):
    instances = _resolve_all(build_reader_container(fake_settings))
    assert not any(isinstance(i, VectorIndexWriter) for i in instances)


def test_only_the_writer_container_declares_an_index_writer():
    assert "vector_index_writer" in WriterContainer.providers
    assert "vector_index_writer" not in ReaderContainer.providers


def test_reader_container_exposes_no_ingestion():
    for name in [*INGESTION_PORTS, "discover_documents", "ingest_document"]:
        assert name not in ReaderContainer.providers


def test_writer_exposes_ingestion_use_cases(fake_settings):
    container = build_writer_container(fake_settings)
    assert isinstance(container.discover_documents(), DiscoverDocuments)
    assert isinstance(container.ingest_document(), IngestDocument)


def test_real_ingestion_adapters_resolve_without_network(no_network, real_settings):
    container = build_writer_container(real_settings)

    for name, port in INGESTION_PORTS.items():
        adapter = getattr(container, name)()
        assert isinstance(adapter, port)
        assert "InMemory" not in type(adapter).__name__
    assert isinstance(container.ingest_document(), IngestDocument)


@pytest.mark.parametrize("port_name", NOT_YET_REAL_WRITER_PORTS)
def test_writer_ports_without_real_adapter_fail_on_resolution(real_settings, port_name):
    container = build_writer_container(real_settings)
    with pytest.raises(RealAdaptersUnavailableError, match=port_name):
        getattr(container, port_name)()


@pytest.mark.parametrize("port_name", NOT_YET_REAL_READER_PORTS)
def test_reader_ports_without_real_adapter_fail_on_resolution(real_settings, port_name):
    container = build_reader_container(real_settings)
    with pytest.raises(RealAdaptersUnavailableError, match=port_name):
        getattr(container, port_name)()


async def test_discover_and_ingest_end_to_end_with_fakes(no_network, fake_settings):
    document_id = DocumentId("contract-1")
    document = Document(
        document_id, ContractId("contract-1"), "Contract", DocumentType.OTHER
    )
    container = build_writer_container(fake_settings)
    container.document_source.override(
        InMemoryDocumentSource({document_id: (document, b"Governing law")})
    )

    pending = await container.discover_documents().execute()
    record = await container.ingest_document().execute(pending[0])

    assert pending == (document_id,)
    assert record.status is IngestionStatus.INGESTED
    assert await container.discover_documents().execute() == ()
