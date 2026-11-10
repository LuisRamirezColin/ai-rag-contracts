import asyncio
from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.types import ParsedMessage

from contract_intel.adapters.outbound.in_memory.clause_extractor import (
    InMemoryClauseExtractor,
)
from contract_intel.adapters.outbound.langgraph.clause_extraction_graph import (
    plan_windows,
)
from contract_intel.adapters.outbound.langgraph.langgraph_clause_extractor import (
    ExtractionConfig,
    LangGraphClauseExtractor,
    WindowClause,
    WindowClauses,
)
from contract_intel.application.ports.outbound.clause_extractor import ClauseExtractor
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.errors import (
    ModelRefusedError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from contract_intel.domain.ids import ClauseId, ContractId, DocumentId
from contract_intel.domain.page import Page, PageRange

DOC = Document(DocumentId("doc-1"), ContractId("doc-1"), "Doc", DocumentType.OTHER)
LAW_TEXT = "This Agreement shall be governed by the laws of the State of Delaware."
CAP_TEXT = "In no event shall either party's liability exceed the fees paid."
PAGES = (
    Page(DOC.id, 1, f"1. Term. The term is two years.\n{CAP_TEXT}"),
    Page(DOC.id, 2, ""),
    Page(DOC.id, 3, f"12. Governing Law. {LAW_TEXT}"),
)
WINDOW_CHARS = 80  # small enough to put pages 1 and 3 in separate windows


def parsed(
    clauses: list[WindowClause], **overrides: Any
) -> ParsedMessage[WindowClauses]:
    payload: dict[str, Any] = {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": [
            {
                "type": "text",
                "text": "{}",
                "parsed_output": WindowClauses(clauses=clauses),
            }
        ],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 500, "output_tokens": 60},
    }
    payload.update(overrides)
    return ParsedMessage[WindowClauses].model_validate(payload)


def window_clause(clause_type: str, text: str, first: int, last: int | None = None):
    return WindowClause(
        clause_type=clause_type, text=text, first_page=first, last_page=last or first
    )


class FakeParse:
    """Answers per window by the first page number it receives."""

    def __init__(
        self,
        by_first_page: dict[int, list[WindowClause]] | None = None,
        error: Exception | None = None,
        response: ParsedMessage[WindowClauses] | None = None,
    ) -> None:
        self.by_first_page = by_first_page or {}
        self.error = error
        self.response = response
        self.requests: list[dict[str, Any]] = []

    async def __call__(self, **request: Any) -> ParsedMessage[WindowClauses]:
        self.requests.append(request)
        await asyncio.sleep(0)
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return self.response
        content = request["messages"][0]["content"]
        first_page = int(content.split('number="', 1)[1].split('"', 1)[0])
        return parsed(self.by_first_page.get(first_page, []))


GOOD_ANSWERS = {
    1: [
        window_clause("cap_on_liability", CAP_TEXT, 1),
        window_clause("non_compete", "Supplier shall not compete anywhere.", 1),
    ],
    3: [
        window_clause("governing_law", LAW_TEXT, 3),
        window_clause(
            "governing_law", "governed by the laws of the State of Delaware", 3
        ),
    ],
}


def _config(window_chars: int = WINDOW_CHARS) -> ExtractionConfig:
    return ExtractionConfig(
        api_key="test",
        model="claude-sonnet-5-5",
        effort="medium",
        max_tokens=16000,
        window_chars=window_chars,
    )


def _langgraph(
    fake: FakeParse, window_chars: int = WINDOW_CHARS
) -> LangGraphClauseExtractor:
    return LangGraphClauseExtractor(_config(window_chars), fake)


EXPECTED = (
    Clause(
        ClauseId("doc-1:cap_on_liability:000"),
        DOC.id,
        ClauseType.CAP_ON_LIABILITY,
        CAP_TEXT,
        PageRange(1, 1),
    ),
    Clause(
        ClauseId("doc-1:governing_law:000"),
        DOC.id,
        ClauseType.GOVERNING_LAW,
        LAW_TEXT,
        PageRange(3, 3),
    ),
)


@pytest.fixture(params=["in_memory", "langgraph"])
def extractor(request: pytest.FixtureRequest) -> ClauseExtractor:
    if request.param == "langgraph":
        return _langgraph(FakeParse(GOOD_ANSWERS))
    return InMemoryClauseExtractor({DOC.id: EXPECTED})


async def test_returns_typed_literal_clauses_with_pages(extractor):
    extraction = await extractor.extract(DOC, PAGES)

    assert extraction.clauses == EXPECTED
    assert extraction.model
    assert extraction.input_tokens >= 0


async def test_unknown_document_text_yields_no_clauses(extractor):
    other = Document(
        DocumentId("doc-2"), ContractId("doc-2"), "Other", DocumentType.OTHER
    )
    extraction = await extractor.extract(
        other, (Page(other.id, 1, "Nothing relevant."),)
    )
    assert extraction.clauses == ()


class TestLangGraphSpecifics:
    def test_windows_keep_whole_pages_and_skip_blank_ones(self):
        windows = plan_windows(PAGES, WINDOW_CHARS)
        assert [[p.number for p in w] for w in windows] == [[1], [3]]
        assert [[p.number for p in w] for w in plan_windows(PAGES, 10_000)] == [[1, 3]]

    async def test_one_call_per_window_and_tokens_are_summed(self):
        fake = FakeParse(GOOD_ANSWERS)

        extraction = await _langgraph(fake).extract(DOC, PAGES)

        assert len(fake.requests) == 2
        assert (extraction.input_tokens, extraction.output_tokens) == (1000, 120)
        request = fake.requests[0]
        assert request["output_format"] is WindowClauses
        assert request["output_config"] == {"effort": "medium"}
        assert request["model"] == "claude-sonnet-5-5"

    async def test_paraphrased_candidates_are_dropped(self):
        extraction = await _langgraph(FakeParse(GOOD_ANSWERS)).extract(DOC, PAGES)
        assert ClauseType.NON_COMPETE not in {c.clause_type for c in extraction.clauses}

    async def test_clause_split_across_windows_is_consolidated(self):
        pages = (Page(DOC.id, 1, LAW_TEXT), Page(DOC.id, 2, LAW_TEXT))
        answers = {
            1: [window_clause("governing_law", LAW_TEXT, 1)],
            2: [window_clause("governing_law", LAW_TEXT, 2)],
        }

        extraction = await _langgraph(FakeParse(answers)).extract(DOC, pages)

        (clause,) = extraction.clauses
        assert clause.pages == PageRange(1, 2)

    async def test_invalid_page_ranges_are_ignored(self):
        answers = {1: [window_clause("cap_on_liability", CAP_TEXT, 3, 1)]}
        extraction = await _langgraph(FakeParse(answers)).extract(DOC, PAGES)
        assert extraction.clauses == ()

    async def test_no_text_means_no_calls(self):
        fake = FakeParse(GOOD_ANSWERS)
        extraction = await _langgraph(fake).extract(DOC, (Page(DOC.id, 1, "  "),))
        assert extraction.clauses == ()
        assert fake.requests == []

    async def test_refusal_raises_model_refused(self):
        refused = parsed(
            [],
            stop_reason="refusal",
            stop_details={"type": "refusal", "category": "cyber", "explanation": "x"},
        )
        with pytest.raises(ModelRefusedError):
            await _langgraph(FakeParse(response=refused)).extract(DOC, PAGES)

    async def test_missing_structured_output_is_a_provider_failure(self):
        empty = parsed([], content=[], stop_reason="max_tokens")
        with pytest.raises(ProviderUnavailableError):
            await _langgraph(FakeParse(response=empty)).extract(DOC, PAGES)

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (
                anthropic.RateLimitError(
                    "slow down",
                    response=httpx2.Response(
                        429, request=httpx2.Request("POST", "https://api.anthropic.com")
                    ),
                    body=None,
                ),
                ProviderRateLimitedError,
            ),
            (
                anthropic.APIConnectionError(
                    request=httpx2.Request("POST", "https://api.anthropic.com")
                ),
                ProviderUnavailableError,
            ),
        ],
        ids=["rate_limit", "connection"],
    )
    async def test_sdk_errors_become_domain_errors(self, error, expected):
        with pytest.raises(expected):
            await _langgraph(FakeParse(error=error)).extract(DOC, PAGES)
