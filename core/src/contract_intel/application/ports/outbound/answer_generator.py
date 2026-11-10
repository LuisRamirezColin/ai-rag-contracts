from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from contract_intel.domain.answer import GeneratedAnswer
from contract_intel.domain.chunk import ScoredChunk


@runtime_checkable
class AnswerGenerator(Protocol):
    """Produce a grounded answer from a question and retrieved context."""

    async def generate(
        self, question: str, context: Sequence[ScoredChunk]
    ) -> GeneratedAnswer:
        """Answer ``question`` using only ``context``, citing its sources.

        Raises:
            AnswerRefusedError: If the model declines to answer.
            ProviderRateLimitedError: If the provider rejects the call for limits.
            ProviderUnavailableError: If the provider cannot be reached or fails.
        """
        ...
