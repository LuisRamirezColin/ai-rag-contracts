from typing import Protocol, runtime_checkable

from contract_intel.domain.answer import Answer
from contract_intel.domain.clause_type import ClauseType


@runtime_checkable
class AnswerQuestion(Protocol):
    """Answer a natural-language question over the indexed contracts."""

    async def execute(
        self,
        question: str,
        clause_types: frozenset[ClauseType] = frozenset(),
    ) -> Answer:
        """Answer ``question``, optionally restricted to ``clause_types``."""
        ...
