import hashlib
from dataclasses import dataclass, field

import pytest
import voyageai.error as voyage_error

from contract_intel.adapters.outbound.in_memory.embedder import InMemoryEmbedder
from contract_intel.adapters.outbound.voyage import voyage_embedder as voyage
from contract_intel.adapters.outbound.voyage.voyage_embedder import (
    VoyageConfig,
    VoyageEmbedder,
)
from contract_intel.application.ports.outbound.embedder import Embedder
from contract_intel.domain.errors import (
    EmbeddingDimensionMismatchError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)

DIMENSIONS = 16
TOKENS_PER_TEXT = 3


@dataclass
class FakeResponse:
    embeddings: list[list[float]]
    total_tokens: int


@dataclass
class FakeVoyageClient:
    """Stands in for ``voyageai.AsyncClient``: deterministic vectors, call log."""

    dimensions: int = DIMENSIONS
    calls: list[dict[str, object]] = field(default_factory=list)
    error: Exception | None = None

    async def embed(self, texts, model=None, input_type=None, truncation=True):
        if self.error is not None:
            raise self.error
        self.calls.append(
            {
                "count": len(texts),
                "model": model,
                "input_type": input_type,
                "truncation": truncation,
            }
        )
        return FakeResponse(
            [self._vector(text) for text in texts], TOKENS_PER_TEXT * len(texts)
        )

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [digest[i % len(digest)] / 255 for i in range(self.dimensions)]


def _voyage(client: FakeVoyageClient) -> VoyageEmbedder:
    config = VoyageConfig(
        api_key="test", model="voyage-law-2", dimensions=DIMENSIONS, max_retries=0
    )
    return VoyageEmbedder(config, client)


@pytest.fixture(params=["in_memory", "voyage"])
def embedder(request: pytest.FixtureRequest) -> Embedder:
    if request.param == "voyage":
        return _voyage(FakeVoyageClient())
    return InMemoryEmbedder(dimensions=DIMENSIONS)


async def test_one_vector_per_text_in_order(embedder):
    batch = await embedder.embed_documents(["alpha", "beta", "alpha"])

    first, second, third = batch.embeddings
    assert first == third
    assert first != second
    assert all(e.dimensions == DIMENSIONS for e in batch.embeddings)


async def test_reports_tokens_and_model(embedder):
    batch = await embedder.embed_documents(["alpha", "beta"])

    assert batch.input_tokens > 0
    assert batch.model


async def test_query_has_the_document_dimension(embedder):
    query = await embedder.embed_query("Which law governs the agreement?")

    assert query.dimensions == DIMENSIONS


async def test_no_texts_no_vectors(embedder):
    batch = await embedder.embed_documents([])

    assert batch.embeddings == ()
    assert batch.input_tokens == 0


class TestVoyageSpecifics:
    async def test_documents_and_queries_use_their_input_type(self):
        client = FakeVoyageClient()
        embedder = _voyage(client)

        await embedder.embed_documents(["a"])
        await embedder.embed_query("q")

        assert [c["input_type"] for c in client.calls] == ["document", "query"]
        assert all(c["model"] == "voyage-law-2" for c in client.calls)
        assert all(c["truncation"] is False for c in client.calls)

    async def test_many_texts_are_split_into_requests_and_tokens_summed(self):
        client = FakeVoyageClient()
        texts = [f"text {i}" for i in range(voyage.MAX_TEXTS_PER_REQUEST * 2 + 5)]

        batch = await _voyage(client).embed_documents(texts)

        assert [c["count"] for c in client.calls] == [128, 128, 5]
        assert len(batch.embeddings) == len(texts)
        assert batch.input_tokens == TOKENS_PER_TEXT * len(texts)

    async def test_long_texts_are_split_by_characters(self):
        client = FakeVoyageClient()
        size = voyage.MAX_CHARS_PER_REQUEST // 2 + 1
        texts = ["x" * size, "y" * size, "z" * size]

        await _voyage(client).embed_documents(texts)

        assert [c["count"] for c in client.calls] == [1, 1, 1]

    async def test_wrong_dimension_is_rejected(self):
        embedder = _voyage(FakeVoyageClient(dimensions=DIMENSIONS - 1))

        with pytest.raises(EmbeddingDimensionMismatchError):
            await embedder.embed_documents(["a"])
        with pytest.raises(EmbeddingDimensionMismatchError):
            await embedder.embed_query("q")

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (voyage_error.RateLimitError("3 RPM"), ProviderRateLimitedError),
            (voyage_error.APIConnectionError("down"), ProviderUnavailableError),
            (voyage_error.ServiceUnavailableError("503"), ProviderUnavailableError),
            (voyage_error.ServerError("500"), ProviderUnavailableError),
        ],
        ids=["rate_limit", "connection", "unavailable", "server"],
    )
    async def test_sdk_errors_become_domain_errors(self, error, expected):
        embedder = _voyage(FakeVoyageClient(error=error))

        with pytest.raises(expected):
            await embedder.embed_documents(["a"])
        with pytest.raises(expected):
            await embedder.embed_query("q")
