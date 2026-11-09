from collections.abc import Sequence

from contract_intel.domain.answer import Answer, Citation, GeneratedAnswer
from contract_intel.domain.chunk import ScoredChunk

NO_CONTEXT_ANSWER = "No relevant information was found in the indexed contracts."
IN_MEMORY_CHAT_MODEL = "in-memory-extractive"
CHARS_PER_TOKEN = 4


class InMemoryAnswerGenerator:
    """Answer with the best-scored chunk verbatim and cite every context chunk."""

    async def generate(
        self, question: str, context: Sequence[ScoredChunk]
    ) -> GeneratedAnswer:
        """Build an extractive answer from ``context`` with estimated token usage."""
        if not context:
            answer = Answer(question=question, text=NO_CONTEXT_ANSWER)
        else:
            citations = tuple(
                Citation(
                    document_id=item.chunk.document_id,
                    pages=item.chunk.pages,
                    excerpt=item.chunk.text,
                )
                for item in context
            )
            answer = Answer(
                question=question, text=context[0].chunk.text, citations=citations
            )
        prompt_chars = len(question) + sum(len(item.chunk.text) for item in context)
        return GeneratedAnswer(
            answer=answer,
            model=IN_MEMORY_CHAT_MODEL,
            input_tokens=prompt_chars // CHARS_PER_TOKEN,
            output_tokens=len(answer.text) // CHARS_PER_TOKEN,
        )
