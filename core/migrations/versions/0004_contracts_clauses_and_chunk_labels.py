"""Contracts with their documents and clauses; clause types per chunk.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contracts")),
    )
    op.create_table(
        "contract_documents",
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            name=op.f("fk_contract_documents_contract_id_contracts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_contract_documents_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "contract_id", "document_id", name=op.f("pk_contract_documents")
        ),
    )
    op.create_table(
        "clauses",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("clause_type", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("first_page", sa.Integer(), nullable=False),
        sa.Column("last_page", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "first_page >= 1", name=op.f("ck_clauses_first_page_positive")
        ),
        sa.CheckConstraint(
            "last_page >= first_page", name=op.f("ck_clauses_page_range_ordered")
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            name=op.f("fk_clauses_contract_id_contracts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_clauses_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clauses")),
    )
    op.create_index(op.f("ix_clauses_document_id"), "clauses", ["document_id"])
    op.create_table(
        "chunk_clause_types",
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("clause_type", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_chunk_clause_types_chunk_id_chunks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "chunk_id", "clause_type", name=op.f("pk_chunk_clause_types")
        ),
    )
    op.create_index(
        op.f("ix_chunk_clause_types_clause_type"), "chunk_clause_types", ["clause_type"]
    )
    op.drop_column("chunks", "clause_type")


def downgrade() -> None:
    op.add_column("chunks", sa.Column("clause_type", sa.Text(), nullable=True))
    op.drop_table("chunk_clause_types")
    op.drop_table("clauses")
    op.drop_table("contract_documents")
    op.drop_table("contracts")
