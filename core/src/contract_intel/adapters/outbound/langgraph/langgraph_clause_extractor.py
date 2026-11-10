from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Literal

from anthropic import AsyncAnthropic
from anthropic.types import ParsedMessage
from pydantic import BaseModel

from contract_intel.adapters.outbound.anthropic.errors import (
    PROVIDER,
    anthropic_errors,
    ensure_not_refused,
)
from contract_intel.adapters.outbound.langgraph.clause_extraction_graph import (
    WindowResult,
    build_graph,
    plan_windows,
)
from contract_intel.domain.clause import ClauseExtraction
from contract_intel.domain.clause_rules import ClauseCandidate, to_clauses
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.document import Document
from contract_intel.domain.errors import (
    DomainError,
    ModelRefusedError,
    ProviderUnavailableError,
)
from contract_intel.domain.page import Page, PageRange

ExtractableType = Literal[
    "governing_law",
    "termination_for_convenience",
    "cap_on_liability",
    "renewal_term",
    "exclusivity",
    "most_favored_nation",
    "non_compete",
    "ip_ownership_assignment",
    "price_restrictions",
    "volume_restriction",
]

CLAUSE_DEFINITIONS = {
    "governing_law": "which jurisdiction's law governs the contract",
    "termination_for_convenience": (
        "a party may terminate without cause, e.g. upon prior notice"
    ),
    "cap_on_liability": "a limit on the amount of liability or damages",
    "renewal_term": "automatic or optional renewal or extension of the term",
    "exclusivity": "exclusive rights or dealing, or a ban on dealing with others",
    "most_favored_nation": (
        "terms at least as favorable as those offered to third parties"
    ),
    "non_compete": "a restriction on a party competing or operating in a field",
    "ip_ownership_assignment": (
        "intellectual property created is owned by or assigned to a party"
    ),
    "price_restrictions": "a restriction on raising or lowering prices",
    "volume_restriction": (
        "volume or usage limits, or extra fees or consent above a threshold"
    ),
}

SYSTEM_PROMPT = (
    "You extract clauses from commercial contracts. Report only clauses of these "
    "types:\n"
    + "\n".join(f"- {name}: {meaning}" for name, meaning in CLAUSE_DEFINITIONS.items())
    + "\nCopy each clause's text verbatim from the pages (no paraphrasing, no "
    "ellipses) and give the first and last page number where it appears. Report "
    "nothing for types that are absent. Each page is wrapped in "
    '<page number="N"> tags.'
)


class WindowClause(BaseModel):
    """One clause proposed by the model (structured output schema)."""

    clause_type: ExtractableType
    text: str
    first_page: int
    last_page: int


class WindowClauses(BaseModel):
    """All clauses proposed by the model for one window."""

    clauses: list[WindowClause]


ParseMessage = Callable[..., Awaitable[ParsedMessage[WindowClauses]]]


@dataclass(frozen=True, slots=True)
class ExtractionConfig:
    """Model and request settings for clause extraction with Claude."""

    api_key: str | None
    model: str
    effort: str
    max_tokens: int
    window_chars: int


class LangGraphClauseExtractor:
    """Typed clauses via a map-reduce LangGraph over Claude structured outputs."""

    def __init__(
        self, config: ExtractionConfig, parse_message: ParseMessage | None = None
    ) -> None:
        self._config = config
        self._injected_parse = parse_message

    @cached_property
    def _parse(self) -> ParseMessage:
        if self._injected_parse is not None:
            return self._injected_parse
        client = AsyncAnthropic(api_key=self._config.api_key or None)
        return client.messages.parse

    async def extract(
        self, document: Document, pages: Sequence[Page]
    ) -> ClauseExtraction:
        """Extract the clauses of ``document`` from ``pages``.

        Raises:
            ModelRefusedError: If Claude declines a window.
            ProviderRateLimitedError: If Anthropic rejects a call for limits.
            ProviderUnavailableError: If Anthropic cannot be reached or fails.
        """
        windows = plan_windows(pages, self._config.window_chars)
        if not windows:
            return ClauseExtraction((), self._config.model, 0, 0)
        state = await build_graph(self._extract_window).ainvoke({"windows": windows})
        models = state.get("models") or [self._config.model]
        return ClauseExtraction(
            clauses=to_clauses(document.id, state.get("consolidated", [])),
            model=models[0],
            input_tokens=state.get("input_tokens", 0),
            output_tokens=state.get("output_tokens", 0),
        )

    async def _extract_window(self, window: Sequence[Page]) -> WindowResult:
        with anthropic_errors():
            response = await self._parse(**self._request(window))
        ensure_not_refused(
            response.stop_reason, response.stop_details, ModelRefusedError
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ProviderUnavailableError(PROVIDER, "incomplete structured output")
        return WindowResult(
            candidates=tuple(_candidates(parsed)),
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def _request(self, window: Sequence[Page]) -> dict[str, Any]:
        pages = "\n".join(
            f'<page number="{page.number}">\n{page.text}\n</page>' for page in window
        )
        return {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens,
            "system": SYSTEM_PROMPT,
            "output_config": {"effort": self._config.effort},
            "output_format": WindowClauses,
            "messages": [{"role": "user", "content": pages}],
        }


def _candidates(parsed: WindowClauses) -> list[ClauseCandidate]:
    candidates: list[ClauseCandidate] = []
    for item in parsed.clauses:
        try:
            candidates.append(
                ClauseCandidate(
                    ClauseType(item.clause_type),
                    item.text,
                    PageRange(item.first_page, item.last_page),
                )
            )
        except DomainError:
            continue  # invalid page range or blank text: not a usable candidate
    return candidates
