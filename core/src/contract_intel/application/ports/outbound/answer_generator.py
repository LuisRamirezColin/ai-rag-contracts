from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from contract_intel.domain.answer import Answer
from contract_intel.domain.chunk import ScoredChunk


@runtime_checkable
class AnswerGenerator(Protocol):
    """Produce a grounded answer from a question and retrieved context."""

    async def generate(self, question: str, context: Sequence[ScoredChunk]) -> Answer:
        """Answer ``question`` using only ``context``, citing its sources."""
        ...
