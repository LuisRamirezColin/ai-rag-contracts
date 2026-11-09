from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from contract_intel.domain.chunk import Embedding


@runtime_checkable
class Embedder(Protocol):
    """Compute dense vector representations of text."""

    async def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        """Return one embedding per input text, in the same order."""
        ...
