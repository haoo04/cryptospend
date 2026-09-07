"""add transaction event receipts

Revision ID: 0006_event_receipts
Revises: 0005_categories
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_event_receipts"
down_revision: str | None = "0005_categories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_receipts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(32),
            sa.ForeignKey("transaction_events.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("byte_size >= 1 AND byte_size <= 10485760", name="receipt_byte_size_valid"),
    )
    op.create_index("ix_event_receipts_event_id", "event_receipts", ["event_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_event_receipts_event_id", table_name="event_receipts")
    op.drop_table("event_receipts")
