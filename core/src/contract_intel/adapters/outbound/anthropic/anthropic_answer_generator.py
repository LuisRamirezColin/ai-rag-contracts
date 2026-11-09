from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from anthropic import (
    APIConnectionError,
    AsyncAnthropic,
    InternalServerError,
    RateLimitError,
)
from anthropic.types.beta import BetaCitationCharLocation, BetaMessage, BetaTextBlock

from contract_intel.domain.answer import Answer, Citation, GeneratedAnswer
from contract_intel.domain.chunk import ScoredChunk
from contract_intel.domain.errors import (
    AnswerRefusedError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)

PROVIDER = "anthropic"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
DEFAULT_FALLBACKS = "default"
REFUSAL_STOP_REASON = "refusal"
SYSTEM_PROMPT = (
    "You answer questions about commercial contracts. Use only the documents "
    "provided in the user's message; each is an excerpt of a contract with its "
    "pages. Do not use outside knowledge. If the documents do not contain the "
    "information asked for, say clearly that the retrieved contracts do not "
    "contain it. Be concise and answer in the language of the question."
)

CreateMessage = Callable[..., Awaitable[BetaMessage]]


@dataclass(frozen=True, slots=True)
class AnthropicConfig:
    """Model and request settings for answer generation with Claude."""

    api_key: str | None
    model: str
    effort: str
    max_tokens: int
    fallbacks: bool


class AnthropicAnswerGenerator:
    """Grounded answers from Claude, with citations mapped back to chunks."""

    def __init__(
        self, config: AnthropicConfig, create_message: CreateMessage | None = None
    ) -> None:
        self._config = config
        self._injected_create = create_message

    @cached_property
    def _create(self) -> CreateMessage:
        if self._injected_create is not None:
            return self._injected_create
        client = AsyncAnthropic(api_key=self._config.api_key or None)
        return client.beta.messages.create

    async def generate(
        self, question: str, context: Sequence[ScoredChunk]
    ) -> GeneratedAnswer:
        """Ask Claude to answer ``question`` from ``context`` and cite it.

        Raises:
            AnswerRefusedError: If Claude declines to answer.
            ProviderRateLimitedError: If Anthropic rejects the call for limits.
            ProviderUnavailableError: If Anthropic cannot be reached or fails.
        """
        response = await self._call(self._request(question, context))
        if response.stop_reason == REFUSAL_STOP_REASON:
            details = response.stop_details
            raise AnswerRefusedError(details.category if details else None)
        text, citations = _parse(response, context)
        if not text.strip():
            raise ProviderUnavailableError(PROVIDER, "empty answer")
        return GeneratedAnswer(
            answer=Answer(question=question, text=text, citations=citations),
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def _call(self, request: dict[str, Any]) -> BetaMessage:
        try:
            return await self._create(**request)
        except RateLimitError as error:
            raise ProviderRateLimitedError(PROVIDER, str(error)) from error
        except (APIConnectionError, InternalServerError) as error:
            raise ProviderUnavailableError(PROVIDER, str(error)) from error

    def _request(self, question: str, context: Sequence[ScoredChunk]) -> dict[str, Any]:
        documents = [_document(item) for item in context]
        request: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens,
            "system": SYSTEM_PROMPT,
            "output_config": {"effort": self._config.effort},
            "messages": [
                {
                    "role": "user",
                    "content": [*documents, {"type": "text", "text": question}],
                }
            ],
        }
        if self._config.fallbacks:
            request["betas"] = [FALLBACK_BETA]
            request["fallbacks"] = DEFAULT_FALLBACKS
        return request


def _document(item: ScoredChunk) -> dict[str, Any]:
    chunk = item.chunk
    return {
        "type": "document",
        "source": {"type": "text", "media_type": "text/plain", "data": chunk.text},
        "title": f"{chunk.document_id} (pages {chunk.pages.first}-{chunk.pages.last})",
        "citations": {"enabled": True},
    }


def _parse(
    response: BetaMessage, context: Sequence[ScoredChunk]
) -> tuple[str, tuple[Citation, ...]]:
    parts: list[str] = []
    citations: dict[Citation, None] = {}
    for block in response.content:
        if not isinstance(block, BetaTextBlock):
            continue
        parts.append(block.text)
        for cited in block.citations or []:
            citation = _to_citation(cited, context)
            if citation is not None:
                citations[citation] = None
    return "".join(parts), tuple(citations)


def _to_citation(cited: object, context: Sequence[ScoredChunk]) -> Citation | None:
    if not isinstance(cited, BetaCitationCharLocation):
        return None
    if not 0 <= cited.document_index < len(context) or not cited.cited_text.strip():
        return None
    chunk = context[cited.document_index].chunk
    return Citation(chunk.document_id, chunk.pages, cited.cited_text.strip())
