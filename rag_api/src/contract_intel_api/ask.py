"""``POST /ask``: questions over the indexed contracts, answered with citations.

The router only translates HTTP to the ``AnswerQuestion`` inbound port and
domain errors to status codes; it holds no business rules.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, StringConstraints

from contract_intel.application.ports.inbound.answer_question import AnswerQuestion
from contract_intel.domain.answer import Answer
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.errors import (
    AnswerRefusedError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)

MAX_QUESTION_CHARS = 2000
RETRY_AFTER_SECONDS = 60

router = APIRouter(tags=["questions"])

Question = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS
    ),
]


class AskRequest(BaseModel):
    """A natural-language question, optionally restricted to clause types."""

    question: Question
    clause_types: list[ClauseType] = Field(default_factory=list)


class CitationResponse(BaseModel):
    """Where a part of the answer comes from."""

    document_id: str
    first_page: int
    last_page: int
    excerpt: str


class AskResponse(BaseModel):
    """The answer and the citations that support it."""

    answer: str
    citations: list[CitationResponse]

    @classmethod
    def from_answer(cls, answer: Answer) -> "AskResponse":
        """Map a domain answer to the HTTP payload."""
        return cls(
            answer=answer.text,
            citations=[
                CitationResponse(
                    document_id=c.document_id,
                    first_page=c.pages.first,
                    last_page=c.pages.last,
                    excerpt=c.excerpt,
                )
                for c in answer.citations
            ],
        )


@router.post("/ask")
async def ask(body: AskRequest, request: Request) -> AskResponse:
    """Answer a question using only the indexed contracts, citing document and pages."""
    use_case: AnswerQuestion = request.app.state.container.answer_question()
    try:
        answer = await use_case.execute(body.question, frozenset(body.clause_types))
    except ProviderRateLimitedError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        ) from error
    except ProviderUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    except AnswerRefusedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return AskResponse.from_answer(answer)
