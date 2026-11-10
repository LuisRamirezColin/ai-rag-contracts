from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contract_intel.adapters.outbound.persistence.models import DocumentRow, PageRow
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.errors import DocumentNotAvailableError
from contract_intel.domain.ids import ContractId, DocumentId
from contract_intel.domain.ingestion import IngestionRecord, IngestionStatus
from contract_intel.domain.page import Page

NUL = "\x00"


def without_nul(text: str) -> str:
    """Drop NUL characters, which Postgres rejects in text columns."""
    return text.replace(NUL, "")


class SqlAlchemyDocumentRepository:
    """Document ingestion state and pages persisted in Postgres."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_ingested(self, document: Document, pages: tuple[Page, ...]) -> None:
        """Upsert the document as ingested and replace its pages atomically."""
        record = IngestionRecord.ingested(document.id, len(pages))
        async with self._session_factory.begin() as session:
            await self._upsert(session, document, record)
            await self._delete_pages(session, document.id)
            await session.execute(insert(PageRow), [_page_values(p) for p in pages])

    async def save_failed(self, document: Document, reason: str) -> None:
        """Upsert the document as failed and drop its pages atomically."""
        record = IngestionRecord.failed(document.id, reason)
        async with self._session_factory.begin() as session:
            await self._upsert(session, document, record)
            await self._delete_pages(session, document.id)

    async def get_document(self, document_id: DocumentId) -> Document:
        """Return the stored document.

        Raises:
            DocumentNotAvailableError: If no document is stored under the id.
        """
        async with self._session_factory() as session:
            row = await session.get(DocumentRow, document_id)
        if row is None:
            raise DocumentNotAvailableError(document_id)
        return Document(
            id=DocumentId(row.id),
            contract_id=ContractId(row.contract_id),
            title=row.title,
            document_type=DocumentType(row.document_type),
        )

    async def get_record(self, document_id: DocumentId) -> IngestionRecord | None:
        """Return the stored ingestion record, if any."""
        async with self._session_factory() as session:
            row = await session.get(DocumentRow, document_id)
        return None if row is None else _record_from(row)

    async def ingested_ids(self) -> frozenset[DocumentId]:
        """Return the ids of every ingested document."""
        query = select(DocumentRow.id).where(
            DocumentRow.status == IngestionStatus.INGESTED.value
        )
        async with self._session_factory() as session:
            ids = (await session.scalars(query)).all()
        return frozenset(DocumentId(document_id) for document_id in ids)

    async def get_pages(self, document_id: DocumentId) -> tuple[Page, ...]:
        """Return the pages of an ingested document in ascending order.

        Raises:
            DocumentNotAvailableError: If the document is missing or failed.
        """
        record = await self.get_record(document_id)
        if record is None or record.status is not IngestionStatus.INGESTED:
            raise DocumentNotAvailableError(document_id)
        query = (
            select(PageRow)
            .where(PageRow.document_id == document_id)
            .order_by(PageRow.number)
        )
        async with self._session_factory() as session:
            rows = (await session.scalars(query)).all()
        return tuple(
            Page(document_id=document_id, number=row.number, text=row.text)
            for row in rows
        )

    @staticmethod
    async def _upsert(
        session: AsyncSession, document: Document, record: IngestionRecord
    ) -> None:
        values = {
            "id": document.id,
            "contract_id": document.contract_id,
            "title": without_nul(document.title),
            "document_type": document.document_type.value,
            "status": record.status.value,
            "failure_reason": record.failure_reason,
            "page_count": record.page_count,
        }
        statement = pg_insert(DocumentRow).values(values)
        update = {key: value for key, value in values.items() if key != "id"}
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[DocumentRow.id], set_=update
            )
        )

    @staticmethod
    async def _delete_pages(session: AsyncSession, document_id: DocumentId) -> None:
        await session.execute(delete(PageRow).where(PageRow.document_id == document_id))


def _page_values(page: Page) -> dict[str, object]:
    return {
        "document_id": page.document_id,
        "number": page.number,
        "text": without_nul(page.text),
    }


def _record_from(row: DocumentRow) -> IngestionRecord:
    return IngestionRecord(
        document_id=DocumentId(row.id),
        status=IngestionStatus(row.status),
        page_count=row.page_count,
        failure_reason=row.failure_reason,
    )
