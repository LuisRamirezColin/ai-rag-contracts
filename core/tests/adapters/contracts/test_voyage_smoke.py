"""Calls the real Voyage AI API; runs only with ``-m voyage`` and a real key."""

import pytest

from contract_intel.adapters.outbound.voyage.voyage_embedder import (
    VoyageConfig,
    VoyageEmbedder,
)
from contract_intel.bootstrap.settings import AppSettings

PLACEHOLDER_KEYS = {"", "replace-me"}

pytestmark = pytest.mark.voyage


@pytest.fixture
def embedder() -> VoyageEmbedder:
    settings = AppSettings().embeddings
    api_key = settings.api_key.get_secret_value()
    if api_key in PLACEHOLDER_KEYS:
        pytest.skip("CONTRACT_INTEL_EMBEDDINGS__API_KEY is not set")
    return VoyageEmbedder(
        VoyageConfig(api_key, settings.model, settings.dimensions, settings.max_retries)
    )


async def test_real_document_and_query_embeddings(embedder):
    batch = await embedder.embed_documents(
        ["This Agreement shall be governed by the laws of the State of New York."]
    )
    query = await embedder.embed_query("Which law governs the agreement?")

    assert batch.input_tokens > 0
    assert batch.embeddings[0].dimensions == 1024
    assert query.dimensions == 1024
