import asyncio

import pytest
from fastapi.testclient import TestClient

from contract_intel.adapters.outbound.in_memory.answer_generator import (
    InMemoryAnswerGenerator,
)
from contract_intel.adapters.outbound.in_memory.document_source import (
    InMemoryDocumentSource,
)
from contract_intel.adapters.outbound.in_memory.embedder import InMemoryEmbedder
from contract_intel.bootstrap.reader import build_reader_container
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.bootstrap.writer import build_writer_container
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.errors import (
    AnswerRefusedError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from contract_intel.domain.ids import ContractId, DocumentId
from contract_intel_api.ask import MAX_QUESTION_CHARS, RETRY_AFTER_SECONDS
from contract_intel_api.main import create_app

DOC = DocumentId("ability-agreement")
SETTINGS = AppSettings(_env_file=None, use_fakes=True)


class RateLimitedEmbedder(InMemoryEmbedder):
    async def embed_query(self, text):
        raise ProviderRateLimitedError("voyage", "3 RPM")


class DownGenerator(InMemoryAnswerGenerator):
    async def generate(self, question, context):
        raise ProviderUnavailableError("anthropic", "overloaded")


class RefusingGenerator(InMemoryAnswerGenerator):
    async def generate(self, question, context):
        raise AnswerRefusedError("cyber")


def _indexed_store():
    writer = build_writer_container(SETTINGS)
    document = Document(DOC, ContractId(DOC), "Ability", DocumentType.OTHER)
    writer.document_source.override(
        InMemoryDocumentSource({DOC: (document, b"Governed by the laws of Israel.")})
    )

    async def index() -> None:
        await writer.ingest_document().execute(DOC)
        await writer.vectorize_document().execute(DOC)

    asyncio.run(index())
    return writer.core.vector_store()


@pytest.fixture
def reader():
    return build_reader_container(SETTINGS)


@pytest.fixture
def indexed_reader(reader):
    reader.core.vector_store.override(_indexed_store())
    return reader


def _ask(reader, payload):
    with TestClient(create_app(reader)) as client:
        return client.post("/ask", json=payload)


def test_answer_with_citations(indexed_reader):
    response = _ask(indexed_reader, {"question": "Which law governs?"})

    assert response.status_code == 200
    body = response.json()
    assert "Israel" in body["answer"]
    assert body["citations"] == [
        {
            "document_id": DOC,
            "first_page": 1,
            "last_page": 1,
            "excerpt": "Governed by the laws of Israel.",
        }
    ]


def test_empty_index_answers_no_information(reader):
    response = _ask(reader, {"question": "Which law governs?"})

    assert response.status_code == 200
    assert response.json()["citations"] == []
    assert "No relevant information" in response.json()["answer"]


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": "   "},
        {"question": "x" * (MAX_QUESTION_CHARS + 1)},
        {"question": "Which law?", "clause_types": ["not_a_clause_type"]},
        {},
    ],
    ids=["empty", "blank", "too_long", "unknown_clause_type", "missing"],
)
def test_invalid_requests_are_rejected(reader, payload):
    assert _ask(reader, payload).status_code == 422


def test_rate_limited_provider_returns_503_with_retry_after(indexed_reader):
    indexed_reader.core.embedder.override(RateLimitedEmbedder())

    response = _ask(indexed_reader, {"question": "Which law governs?"})

    assert response.status_code == 503
    assert response.headers["retry-after"] == str(RETRY_AFTER_SECONDS)


def test_unavailable_provider_returns_503(indexed_reader):
    indexed_reader.answer_generator.override(DownGenerator())

    response = _ask(indexed_reader, {"question": "Which law governs?"})

    assert response.status_code == 503
    assert "retry-after" not in response.headers


def test_refused_answer_returns_422(indexed_reader):
    indexed_reader.answer_generator.override(RefusingGenerator())

    response = _ask(indexed_reader, {"question": "Which law governs?"})

    assert response.status_code == 422
    assert "declined" in response.json()["detail"]


def test_openapi_documents_the_endpoint(reader):
    with TestClient(create_app(reader)) as client:
        assert "/ask" in client.get("/openapi.json").json()["paths"]
