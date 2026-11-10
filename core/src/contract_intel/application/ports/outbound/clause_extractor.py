from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from contract_intel.domain.clause import ClauseExtraction
from contract_intel.domain.document import Document
from contract_intel.domain.page import Page


@runtime_checkable
class ClauseExtractor(Protocol):
    """Identify and classify the clauses contained in a document's pages."""

    async def extract(
        self, document: Document, pages: Sequence[Page]
    ) -> ClauseExtraction:
        """Return the clauses found in ``pages`` plus the tokens consumed.

        Raises:
            ModelRefusedError: If the model declines the request.
            ProviderRateLimitedError: If the provider rejects a call for limits.
            ProviderUnavailableError: If the provider cannot be reached or fails.
        """
        ...
