from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaMessage

from contract_intel.adapters.outbound.anthropic import (
    anthropic_answer_generator as claude,
)
from contract_intel.adapters.outbound.anthropic.anthropic_answer_generator import (
    AnthropicAnswerGenerator,
    AnthropicConfig,
)
from contract_intel.adapters.outbound.in_memory.answer_generator import (
    InMemoryAnswerGenerator,
)
from contract_intel.application.ports.outbound.answer_generator import AnswerGenerator
from contract_intel.domain.chunk import Chunk, ScoredChunk
from contract_intel.domain.errors import (
    AnswerRefusedError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from contract_intel.domain.ids import ChunkId, DocumentId
from contract_intel.domain.page import PageRange

DOC_A = DocumentId("ability-agreement")
DOC_B = DocumentId("joint-venture")
QUESTION = "Which law governs the agreement?"
CONTEXT = (
    ScoredChunk(
        Chunk(
            ChunkId("ability-agreement:0007"),
            DOC_A,
            "This Agreement shall be governed by the laws of the State of Israel.",
            PageRange(8, 8),
        ),
        0.4,
    ),
    ScoredChunk(
        Chunk(
            ChunkId("joint-venture:0001"),
            DOC_B,
            "Notices shall be given in writing.",
            PageRange(2, 3),
        ),
        0.3,
    ),
)


def citation(document_index: int, cited_text: str) -> dict[str, Any]:
    return {
        "type": "char_location",
        "cited_text": cited_text,
        "document_index": document_index,
        "document_title": "title",
        "start_char_index": 0,
        "end_char_index": len(cited_text),
    }


def message(content: list[dict[str, Any]], **overrides: Any) -> BetaMessage:
    payload: dict[str, Any] = {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": content,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1200, "output_tokens": 80},
    }
    payload.update(overrides)
    return BetaMessage.model_validate(payload)


GROUNDED = message(
    [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "The agreement is governed by ", "citations": None},
        {
            "type": "text",
            "text": "the laws of the State of Israel",
            "citations": [
                citation(0, "governed by the laws of the State of Israel"),
                citation(0, "governed by the laws of the State of Israel"),
            ],
        },
        {"type": "text", "text": ".", "citations": None},
    ]
)


class FakeMessages:
    def __init__(
        self, response: BetaMessage | None = None, error: Exception | None = None
    ):
        self.response = response or GROUNDED
        self.error = error
        self.requests: list[dict[str, Any]] = []

    async def create(self, **request: Any) -> BetaMessage:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def _config(fallbacks: bool = False) -> AnthropicConfig:
    return AnthropicConfig(
        api_key="test",
        model="claude-sonnet-5-5",
        effort="medium",
        max_tokens=16000,
        fallbacks=fallbacks,
    )


def _claude(
    messages: FakeMessages, fallbacks: bool = False
) -> AnthropicAnswerGenerator:
    return AnthropicAnswerGenerator(_config(fallbacks), messages.create)


def _status_error(cls: type[anthropic.APIStatusError], status: int) -> Exception:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


@pytest.fixture(params=["in_memory", "anthropic"])
def generator(request: pytest.FixtureRequest) -> AnswerGenerator:
    if request.param == "anthropic":
        return _claude(FakeMessages())
    return InMemoryAnswerGenerator()


async def test_answer_has_text_model_and_usage(generator):
    generated = await generator.generate(QUESTION, CONTEXT)

    assert generated.answer.question == QUESTION
    assert generated.answer.text.strip()
    assert generated.model
    assert generated.input_tokens >= 0
    assert generated.output_tokens >= 0


async def test_citations_point_at_context_chunks(generator):
    generated = await generator.generate(QUESTION, CONTEXT)

    assert generated.answer.citations
    context_locations = {(i.chunk.document_id, i.chunk.pages) for i in CONTEXT}
    for cited in generated.answer.citations:
        assert (cited.document_id, cited.pages) in context_locations
        assert cited.excerpt.strip()


class TestAnthropicSpecifics:
    async def test_text_is_joined_and_citations_mapped_and_deduplicated(self):
        generated = await _claude(FakeMessages()).generate(QUESTION, CONTEXT)

        assert (
            generated.answer.text
            == "The agreement is governed by the laws of the State of Israel."
        )
        (cited,) = generated.answer.citations
        assert (cited.document_id, cited.pages) == (DOC_A, PageRange(8, 8))
        assert cited.excerpt == "governed by the laws of the State of Israel"
        assert (generated.input_tokens, generated.output_tokens) == (1200, 80)

    async def test_request_sends_documents_with_citations_then_the_question(self):
        messages = FakeMessages()

        await _claude(messages).generate(QUESTION, CONTEXT)

        (request,) = messages.requests
        assert request["model"] == "claude-sonnet-5-5"
        assert request["output_config"] == {"effort": "medium"}
        assert request["max_tokens"] == 16000
        assert "betas" not in request
        assert "fallbacks" not in request
        content = request["messages"][0]["content"]
        assert [block["type"] for block in content] == ["document", "document", "text"]
        assert content[0]["citations"] == {"enabled": True}
        assert content[0]["source"]["data"] == CONTEXT[0].chunk.text
        assert "pages 8-8" in content[0]["title"]
        assert content[-1]["text"] == QUESTION

    async def test_fallbacks_are_requested_when_enabled(self):
        messages = FakeMessages()

        await _claude(messages, fallbacks=True).generate(QUESTION, CONTEXT)

        (request,) = messages.requests
        assert request["betas"] == [claude.FALLBACK_BETA]
        assert request["fallbacks"] == "default"

    async def test_refusal_raises_with_category(self):
        refused = message(
            [],
            stop_reason="refusal",
            stop_details={"type": "refusal", "category": "cyber", "explanation": "x"},
        )

        with pytest.raises(AnswerRefusedError) as raised:
            await _claude(FakeMessages(refused)).generate(QUESTION, CONTEXT)

        assert raised.value.category == "cyber"

    async def test_citation_to_unknown_document_is_ignored(self):
        stray = message(
            [{"type": "text", "text": "Answer.", "citations": [citation(9, "x")]}]
        )

        generated = await _claude(FakeMessages(stray)).generate(QUESTION, CONTEXT)

        assert generated.answer.citations == ()

    async def test_empty_answer_is_a_provider_failure(self):
        empty = message([{"type": "thinking", "thinking": "", "signature": "s"}])

        with pytest.raises(ProviderUnavailableError):
            await _claude(FakeMessages(empty)).generate(QUESTION, CONTEXT)

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (_status_error(anthropic.RateLimitError, 429), ProviderRateLimitedError),
            (
                _status_error(anthropic.InternalServerError, 500),
                ProviderUnavailableError,
            ),
            (_status_error(anthropic.OverloadedError, 529), ProviderUnavailableError),
            (
                anthropic.APIConnectionError(
                    request=httpx2.Request("POST", "https://api.anthropic.com")
                ),
                ProviderUnavailableError,
            ),
        ],
        ids=["rate_limit", "server_error", "overloaded", "connection"],
    )
    async def test_sdk_errors_become_domain_errors(self, error, expected):
        with pytest.raises(expected):
            await _claude(FakeMessages(error=error)).generate(QUESTION, CONTEXT)

    async def test_client_errors_are_not_masked(self):
        error = _status_error(anthropic.BadRequestError, 400)

        with pytest.raises(anthropic.BadRequestError):
            await _claude(FakeMessages(error=error)).generate(QUESTION, CONTEXT)
