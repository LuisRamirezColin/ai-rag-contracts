from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contract_intel.adapters.outbound.persistence.models import (
    ClauseRow,
    ContractDocumentRow,
    ContractRow,
)
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.contract import Contract
from contract_intel.domain.ids import ClauseId, ContractId, DocumentId
from contract_intel.domain.page import PageRange


class SqlAlchemyContractRepository:
    """Contracts, their documents and clauses persisted in Postgres.

    Documents are returned sorted by id and clauses by first page and id.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, contract_id: ContractId) -> Contract | None:
        """Return the contract with its documents and clauses, if stored."""
        async with self._session_factory() as session:
            row = await session.get(ContractRow, contract_id)
            if row is None:
                return None
            document_ids = (
                await session.scalars(
                    select(ContractDocumentRow.document_id)
                    .where(ContractDocumentRow.contract_id == contract_id)
                    .order_by(ContractDocumentRow.document_id)
                )
            ).all()
            clauses = await self._clauses(session, ClauseRow.contract_id == contract_id)
        return Contract(
            id=ContractId(row.id),
            title=row.title,
            document_ids=tuple(DocumentId(d) for d in document_ids),
            clauses=clauses,
        )

    async def save(self, contract: Contract) -> None:
        """Upsert the contract and replace its documents and clauses atomically."""
        async with self._session_factory.begin() as session:
            statement = pg_insert(ContractRow).values(
                id=contract.id, title=contract.title
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[ContractRow.id], set_={"title": contract.title}
                )
            )
            await session.execute(
                delete(ContractDocumentRow).where(
                    ContractDocumentRow.contract_id == contract.id
                )
            )
            await session.execute(
                delete(ClauseRow).where(ClauseRow.contract_id == contract.id)
            )
            if contract.document_ids:
                await session.execute(
                    insert(ContractDocumentRow),
                    [
                        {"contract_id": contract.id, "document_id": document_id}
                        for document_id in contract.document_ids
                    ],
                )
            if contract.clauses:
                await session.execute(
                    insert(ClauseRow),
                    [_clause_values(contract.id, c) for c in contract.clauses],
                )

    async def clauses_of_document(self, document_id: DocumentId) -> tuple[Clause, ...]:
        """Return the stored clauses of ``document_id``."""
        async with self._session_factory() as session:
            return await self._clauses(session, ClauseRow.document_id == document_id)

    @staticmethod
    async def _clauses(session: AsyncSession, condition: object) -> tuple[Clause, ...]:
        rows = (
            await session.scalars(
                select(ClauseRow)
                .where(condition)  # type: ignore[arg-type]
                .order_by(ClauseRow.first_page, ClauseRow.id)
            )
        ).all()
        return tuple(_clause(row) for row in rows)


def _clause_values(contract_id: ContractId, clause: Clause) -> dict[str, object]:
    return {
        "id": clause.id,
        "contract_id": contract_id,
        "document_id": clause.document_id,
        "clause_type": clause.clause_type.value,
        "text": clause.text,
        "first_page": clause.pages.first,
        "last_page": clause.pages.last,
    }


def _clause(row: ClauseRow) -> Clause:
    return Clause(
        id=ClauseId(row.id),
        document_id=DocumentId(row.document_id),
        clause_type=ClauseType(row.clause_type),
        text=row.text,
        pages=PageRange(first=row.first_page, last=row.last_page),
    )
