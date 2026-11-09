from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Protocol

from voyageai.client_async import AsyncClient

from contract_intel.domain.chunk import Embedding, EmbeddingBatch
from contract_intel.domain.errors import EmbeddingDimensionMismatchError

DOCUMENT_INPUT = "document"
QUERY_INPUT = "query"
# Conservative per-request limits; Voyage allows 1,000 texts and 120K tokens
# per request for voyage-law-2.
MAX_TEXTS_PER_REQUEST = 128
MAX_CHARS_PER_REQUEST = 300_000


class EmbeddingsResponse(Protocol):
    """The part of Voyage's embeddings response this adapter reads."""

    embeddings: list[list[float]] | list[list[int]]
    total_tokens: int


class VoyageEmbedClient(Protocol):
    """The part of ``voyageai.AsyncClient`` this adapter uses."""

    async def embed(
        self,
        texts: list[str],
        model: str | None = None,
        input_type: str | None = None,
        truncation: bool = True,
    ) -> EmbeddingsResponse:
        """Embed ``texts`` with ``model``."""
        ...


@dataclass(frozen=True, slots=True)
class VoyageConfig:
    """Model, expected dimension and credentials for Voyage AI."""

    api_key: str
    model: str
    dimensions: int
    max_retries: int


class VoyageEmbedder:
    """Embeddings from Voyage AI; documents and queries use their own input type."""

    def __init__(
        self, config: VoyageConfig, client: VoyageEmbedClient | None = None
    ) -> None:
        self._config = config
        self._injected_client = client

    @cached_property
    def _client(self) -> VoyageEmbedClient:
        if self._injected_client is not None:
            return self._injected_client
        client: VoyageEmbedClient = AsyncClient(
            api_key=self._config.api_key, max_retries=self._config.max_retries
        )
        return client

    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Embed ``texts`` as documents, batching requests within API limits.

        Raises:
            EmbeddingDimensionMismatchError: If a vector has the wrong dimension.
        """
        embeddings: list[Embedding] = []
        tokens = 0
        for batch in _batches(texts):
            response = await self._embed(batch, DOCUMENT_INPUT)
            embeddings.extend(self._to_embedding(v) for v in response.embeddings)
            tokens += response.total_tokens
        return EmbeddingBatch(tuple(embeddings), tokens, self._config.model)

    async def embed_query(self, text: str) -> Embedding:
        """Embed a search query.

        Raises:
            EmbeddingDimensionMismatchError: If the vector has the wrong dimension.
        """
        response = await self._embed([text], QUERY_INPUT)
        (vector,) = response.embeddings
        return self._to_embedding(vector)

    async def _embed(self, texts: list[str], input_type: str) -> EmbeddingsResponse:
        # truncation=False: an over-long text is an error, never silently cut.
        return await self._client.embed(
            texts, model=self._config.model, input_type=input_type, truncation=False
        )

    def _to_embedding(self, vector: Sequence[float]) -> Embedding:
        if len(vector) != self._config.dimensions:
            raise EmbeddingDimensionMismatchError(self._config.dimensions, len(vector))
        return Embedding(values=tuple(float(value) for value in vector))


def _batches(texts: Sequence[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for text in texts:
        too_many = len(current) >= MAX_TEXTS_PER_REQUEST
        too_long = current_chars + len(text) > MAX_CHARS_PER_REQUEST
        if current and (too_many or too_long):
            batches.append(current)
            current, current_chars = [], 0
        current.append(text)
        current_chars += len(text)
    if current:
        batches.append(current)
    return batches
