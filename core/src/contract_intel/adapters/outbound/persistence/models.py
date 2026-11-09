from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from contract_intel.adapters.outbound.persistence.base import Base


class DocumentRow(Base):
    """A document and its ingestion state."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status IN ('ingested', 'failed')", name="status_known"),
        CheckConstraint("page_count >= 0", name="page_count_not_negative"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    contract_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PageRow(Base):
    """Text of one page of an ingested document."""

    __tablename__ = "pages"
    __table_args__ = (CheckConstraint("number >= 1", name="number_positive"),)

    document_id: Mapped[str] = mapped_column(
        Text, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
