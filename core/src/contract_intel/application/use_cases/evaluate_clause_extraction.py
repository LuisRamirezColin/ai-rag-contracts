from contract_intel.application.ports.outbound.contract_repository import (
    ContractRepository,
)
from contract_intel.application.ports.outbound.document_repository import (
    DocumentRepository,
)
from contract_intel.application.ports.outbound.ground_truth_source import (
    GroundTruthSource,
)
from contract_intel.domain.clause import Clause
from contract_intel.domain.evaluation import EvaluationReport, evaluate


class EvaluateClauseExtractionUseCase:
    """Compare stored clauses with expert labels; never calls the extractor.

    A document counts as processed once its contract records it, which happens
    on every extraction, even one that found no clauses.
    """

    def __init__(
        self,
        documents: DocumentRepository,
        contracts: ContractRepository,
        ground_truth: GroundTruthSource,
    ) -> None:
        self._documents = documents
        self._contracts = contracts
        self._ground_truth = ground_truth

    async def execute(self) -> EvaluationReport:
        """Evaluate every processed document that has expert labels."""
        predictions = await self._predictions_by_title()
        labels = await self._ground_truth.labels()
        return evaluate(predictions, labels)

    async def _predictions_by_title(self) -> dict[str, tuple[Clause, ...]]:
        predictions: dict[str, tuple[Clause, ...]] = {}
        for document_id in sorted(await self._documents.ingested_ids()):
            document = await self._documents.get_document(document_id)
            contract = await self._contracts.get(document.contract_id)
            if contract is None or document_id not in contract.document_ids:
                continue
            predictions[document.title] = await self._contracts.clauses_of_document(
                document_id
            )
        return predictions
