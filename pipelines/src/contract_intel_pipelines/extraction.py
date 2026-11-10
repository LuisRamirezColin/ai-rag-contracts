"""Writer-side clause extraction asset: typed clauses of an ingested document."""

import asyncio
from collections import Counter

from dagster import AssetExecutionContext, MaterializeResult, ResourceParam, asset

from contract_intel.application.ports.inbound.extract_clauses import ExtractClauses
from contract_intel.bootstrap.writer import WriterContainer
from contract_intel.domain.ids import DocumentId
from contract_intel_pipelines.ingestion import documents_partitions, ingested_document


@asset(partitions_def=documents_partitions, deps=[ingested_document])
def extracted_clauses(
    context: AssetExecutionContext, container: ResourceParam[WriterContainer]
) -> MaterializeResult:  # type: ignore[type-arg]
    """Typed clauses found in the document, stored in its contract."""
    use_case: ExtractClauses = container.extract_clauses()
    clauses = asyncio.run(use_case.execute(DocumentId(context.partition_key)))
    by_type = Counter(clause.clause_type.value for clause in clauses)
    return MaterializeResult(
        metadata={"clause_count": len(clauses), "clause_types": dict(by_type)}
    )
