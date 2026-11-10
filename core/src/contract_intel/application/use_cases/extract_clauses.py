from dataclasses import replace

from contract_intel.application.ports.outbound.clause_extractor import ClauseExtractor
from contract_intel.application.ports.outbound.contract_repository import (
    ContractRepository,
)
from contract_intel.application.ports.outbound.document_repository import (
    DocumentRepository,
)
from contract_intel.application.ports.outbound.usage_tracker import UsageTracker
from contract_intel.domain.clause import Clause
from contract_intel.domain.contract import Contract
from contract_intel.domain.document import Document
from contract_intel.domain.errors import DocumentNotAvailableError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.ingestion import IngestionStatus
from contract_intel.domain.usage import TokenPricing, UsageRecord

EXTRACT_CLAUSES_OPERATION = "extract_clauses"


class ExtractClausesUseCase:
    """Extract the typed clauses of an ingested document and store them."""

    def __init__(
        self,
        documents: DocumentRepository,
        extractor: ClauseExtractor,
        contracts: ContractRepository,
        usage_tracker: UsageTracker,
        pricing: TokenPricing,
    ) -> None:
        self._documents = documents
        self._extractor = extractor
        self._contracts = contracts
        self._usage_tracker = usage_tracker
        self._pricing = pricing

    async def execute(self, document_id: DocumentId) -> tuple[Clause, ...]:
        """Extract, store and return the clauses of ``document_id``.

        Raises:
            DocumentNotAvailableError: If the document is missing or not ingested.
        """
        record = await self._documents.get_record(document_id)
        if record is None or record.status is not IngestionStatus.INGESTED:
            raise DocumentNotAvailableError(document_id)
        document = await self._documents.get_document(document_id)
        pages = await self._documents.get_pages(document_id)
        extraction = await self._extractor.extract(document, pages)
        await self._store(document, extraction.clauses)
        await self._usage_tracker.record(
            UsageRecord(
                operation=EXTRACT_CLAUSES_OPERATION,
                model=extraction.model,
                input_tokens=extraction.input_tokens,
                output_tokens=extraction.output_tokens,
                cost_usd=self._pricing.cost_usd(
                    extraction.input_tokens, extraction.output_tokens
                ),
                document_id=document_id,
            )
        )
        return extraction.clauses

    async def _store(self, document: Document, clauses: tuple[Clause, ...]) -> None:
        existing = await self._contracts.get(document.contract_id)
        if existing is None:
            existing = Contract(id=document.contract_id, title=document.title)
        others = tuple(c for c in existing.clauses if c.document_id != document.id)
        document_ids = existing.document_ids
        if document.id not in document_ids:
            document_ids = (*document_ids, document.id)
        await self._contracts.save(
            replace(existing, document_ids=document_ids, clauses=(*others, *clauses))
        )
