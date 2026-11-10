import socket
from pathlib import Path

import pytest
from sqlalchemy.pool import NullPool

import contract_intel.application.ports.outbound as outbound_ports
from contract_intel.adapters.outbound.in_memory.clause_extractor import (
    InMemoryClauseExtractor,
)
from contract_intel.adapters.outbound.in_memory.document_source import (
    InMemoryDocumentSource,
)
from contract_intel.application.ports.inbound.answer_question import AnswerQuestion
from contract_intel.application.ports.inbound.discover_documents import (
    DiscoverDocuments,
)
from contract_intel.application.ports.inbound.ingest_document import IngestDocument
from contract_intel.application.ports.inbound.vectorize_document import (
    VectorizeDocument,
)
from contract_intel.application.ports.outbound.answer_generator import AnswerGenerator
from contract_intel.application.ports.outbound.clause_extractor import ClauseExtractor
from contract_intel.application.ports.outbound.contract_repository import (
    ContractRepository,
)
from contract_intel.application.ports.outbound.document_repository import (
    DocumentRepository,
)
from contract_intel.application.ports.outbound.document_source import DocumentSource
from contract_intel.application.ports.outbound.document_storage import DocumentStorage
from contract_intel.application.ports.outbound.embedder import Embedder
from contract_intel.application.ports.outbound.ground_truth_source import (
    GroundTruthSource,
)
from contract_intel.application.ports.outbound.text_extractor import TextExtractor
from contract_intel.application.ports.outbound.usage_tracker import UsageTracker
from contract_intel.application.ports.outbound.vector_index_writer import (
    VectorIndexWriter,
)
from contract_intel.application.ports.outbound.vector_search import VectorSearch
from contract_intel.bootstrap.reader import ReaderContainer, build_reader_container
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.bootstrap.writer import WriterContainer, build_writer_container
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.ids import ClauseId, ContractId, DocumentId
from contract_intel.domain.ingestion import IngestionStatus
from contract_intel.domain.page import PageRange

INGESTION_PORTS = {
    "document_source": DocumentSource,
    "document_storage": DocumentStorage,
    "text_extractor": TextExtractor,
    "document_repository": DocumentRepository,
}
REAL_WRITER_PORTS = {
    **INGESTION_PORTS,
    "vector_index_writer": VectorIndexWriter,
    "clause_extractor": ClauseExtractor,
    "ground_truth_source": GroundTruthSource,
}
REAL_CORE_PORTS = {
    "embedder": Embedder,
    "usage_tracker": UsageTracker,
    "contract_repository": ContractRepository,
}
REAL_READER_PORTS = {
    "vector_search": VectorSearch,
    "answer_generator": AnswerGenerator,
}


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
        elif name not in {"settings", "mode", "use_null_pool"}:
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


def test_reader_container_exposes_no_ingestion_or_index_writes():
    writer_only = [
        *REAL_WRITER_PORTS,
        "discover_documents",
        "ingest_document",
        "vectorize_document",
        "extract_clauses",
        "evaluate_clause_extraction",
    ]
    for name in writer_only:
        assert name not in ReaderContainer.providers


def test_writer_exposes_ingestion_use_cases(fake_settings):
    container = build_writer_container(fake_settings)
    assert isinstance(container.discover_documents(), DiscoverDocuments)
    assert isinstance(container.ingest_document(), IngestDocument)


def test_real_adapters_resolve_without_network(no_network, real_settings):
    container = build_writer_container(real_settings)

    for name, port in REAL_WRITER_PORTS.items():
        adapter = getattr(container, name)()
        assert isinstance(adapter, port)
        assert "InMemory" not in type(adapter).__name__
    for name, port in REAL_CORE_PORTS.items():
        adapter = getattr(container.core, name)()
        assert isinstance(adapter, port)
        assert "InMemory" not in type(adapter).__name__
    assert isinstance(container.ingest_document(), IngestDocument)
    assert isinstance(container.vectorize_document(), VectorizeDocument)


def test_writer_engine_uses_null_pool_and_reader_a_pool(real_settings):
    writer_engine = build_writer_container(real_settings).core.database_engine()
    reader_engine = build_reader_container(real_settings).core.database_engine()

    assert isinstance(writer_engine.pool, NullPool)
    assert not isinstance(reader_engine.pool, NullPool)


def test_every_outbound_port_has_a_real_adapter(no_network, real_settings):
    writer = build_writer_container(real_settings)
    reader = build_reader_container(real_settings)
    wired = {**REAL_CORE_PORTS, **REAL_WRITER_PORTS, **REAL_READER_PORTS}
    outbound = [
        *(getattr(writer.core, name)() for name in REAL_CORE_PORTS),
        *(getattr(writer, name)() for name in REAL_WRITER_PORTS),
        *(getattr(reader, name)() for name in REAL_READER_PORTS),
    ]

    port_modules = {
        p.stem
        for p in Path(outbound_ports.__path__[0]).glob("*.py")
        if p.stem != "__init__"
    }
    assert set(wired) == port_modules
    assert not any("InMemory" in type(adapter).__name__ for adapter in outbound)


async def test_ingest_extract_and_vectorize_label_chunks_with_fakes(
    no_network, fake_settings
):
    document_id = DocumentId("contract-1")
    document = Document(
        document_id, ContractId("contract-1"), "Contract", DocumentType.OTHER
    )
    law_text = "This Agreement shall be governed by the laws of the State of Delaware."
    law = Clause(
        ClauseId("contract-1:governing_law:000"),
        document_id,
        ClauseType.GOVERNING_LAW,
        law_text,
        PageRange(1, 1),
    )
    container = build_writer_container(fake_settings)
    container.document_source.override(
        InMemoryDocumentSource({document_id: (document, law_text.encode())})
    )
    container.clause_extractor.override(InMemoryClauseExtractor({document_id: (law,)}))

    await container.ingest_document().execute(document_id)
    clauses = await container.extract_clauses().execute(document_id)
    await container.vectorize_document().execute(document_id)

    assert clauses == (law,)
    (entry,) = container.core.vector_store().entries.values()
    assert entry.chunk.clause_types == {ClauseType.GOVERNING_LAW}
    report = await container.evaluate_clause_extraction().execute()
    assert report.excluded_documents == ("Contract",)


def test_real_reader_adapters_resolve_without_network(no_network, real_settings):
    container = build_reader_container(real_settings)

    for name, port in REAL_READER_PORTS.items():
        adapter = getattr(container, name)()
        assert isinstance(adapter, port)
        assert "InMemory" not in type(adapter).__name__
    assert isinstance(container.answer_question(), AnswerQuestion)


async def test_question_end_to_end_with_fakes(no_network, fake_settings):
    document_id = DocumentId("contract-1")
    document = Document(
        document_id, ContractId("contract-1"), "Contract", DocumentType.OTHER
    )
    writer = build_writer_container(fake_settings)
    writer.document_source.override(
        InMemoryDocumentSource(
            {document_id: (document, b"Governed by the laws of Delaware.")}
        )
    )
    await writer.ingest_document().execute(document_id)
    await writer.vectorize_document().execute(document_id)
    reader = build_reader_container(fake_settings)
    reader.core.vector_store.override(writer.core.vector_store())

    answer = await reader.answer_question().execute("Which law governs?")

    assert [c.document_id for c in answer.citations] == [document_id]
    assert "Delaware" in answer.text


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

    chunk_count = await container.vectorize_document().execute(document_id)

    assert pending == (document_id,)
    assert record.status is IngestionStatus.INGESTED
    assert await container.discover_documents().execute() == ()
    assert chunk_count == 1
    assert len(container.core.vector_store().entries) == 1
    (usage,) = container.core.usage_tracker().records
    assert usage.document_id == document_id
