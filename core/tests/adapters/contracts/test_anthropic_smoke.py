"""Calls the real Claude API; runs only with ``-m anthropic`` and credentials."""

import os

import pytest

from contract_intel.adapters.outbound.anthropic.anthropic_answer_generator import (
    AnthropicAnswerGenerator,
    AnthropicConfig,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.chunk import Chunk, ScoredChunk
from contract_intel.domain.ids import ChunkId, DocumentId
from contract_intel.domain.page import PageRange

PLACEHOLDER_KEYS = {"", "replace-me"}
DOC = DocumentId("smoke-agreement")
CONTEXT = (
    ScoredChunk(
        Chunk(
            ChunkId("smoke-agreement:0000"),
            DOC,
            "Section 12. Governing Law. This Agreement shall be governed by and "
            "construed in accordance with the laws of the State of Delaware.",
            PageRange(4, 4),
        ),
        0.5,
    ),
)

pytestmark = pytest.mark.anthropic


@pytest.fixture
def generator() -> AnthropicAnswerGenerator:
    llm = AppSettings().llm
    api_key = llm.api_key.get_secret_value()
    if api_key in PLACEHOLDER_KEYS and not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("No Anthropic credentials configured")
    return AnthropicAnswerGenerator(
        AnthropicConfig(
            api_key=None if api_key in PLACEHOLDER_KEYS else api_key,
            model=llm.chat_model,
            effort=llm.effort,
            max_tokens=llm.max_tokens,
            fallbacks=llm.fallbacks,
        )
    )


async def test_real_answer_cites_the_context(generator):
    generated = await generator.generate("Which law governs the agreement?", CONTEXT)

    assert "Delaware" in generated.answer.text
    assert generated.answer.citations
    assert all(c.document_id == DOC for c in generated.answer.citations)
    assert generated.answer.citations[0].pages == PageRange(4, 4)
    assert generated.input_tokens > 0
    assert generated.output_tokens > 0
