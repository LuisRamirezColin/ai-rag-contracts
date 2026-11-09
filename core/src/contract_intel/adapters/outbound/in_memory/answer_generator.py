from collections.abc import Sequence

from contract_intel.domain.answer import Answer, Citation
from contract_intel.domain.chunk import ScoredChunk

NO_CONTEXT_ANSWER = "No relevant information was found in the indexed contracts."


class InMemoryAnswerGenerator:
    """Answer with the best-scored chunk verbatim and cite every context chunk."""

    async def generate(self, question: str, context: Sequence[ScoredChunk]) -> Answer:
        """Build an extractive answer from ``context``."""
        if not context:
            return Answer(question=question, text=NO_CONTEXT_ANSWER)
        citations = tuple(
            Citation(
                document_id=item.chunk.document_id,
                pages=item.chunk.pages,
                excerpt=item.chunk.text,
            )
            for item in context
        )
        return Answer(
            question=question, text=context[0].chunk.text, citations=citations
        )
