from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from contract_intel.adapters.outbound.persistence.base import Base

# Fixed by migration 0003; must match CONTRACT_INTEL_EMBEDDINGS__DIMENSIONS.
EMBEDDING_DIMENSIONS = 1024
COST_PRECISION = 12
COST_SCALE = 6


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


class ChunkRow(Base):
    """A retrievable chunk of a document with its embedding."""

    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("first_page >= 1", name="first_page_positive"),
        CheckConstraint("last_page >= first_page", name="page_range_ordered"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        Text, ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    first_page: Mapped[int] = mapped_column(Integer)
    last_page: Mapped[int] = mapped_column(Integer)
    clause_type: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    model: Mapped[str] = mapped_column(Text)


class UsageRecordRow(Base):
    """Token usage and estimated cost of one model invocation."""

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    operation: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(COST_PRECISION, COST_SCALE))
    document_id: Mapped[str | None] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
