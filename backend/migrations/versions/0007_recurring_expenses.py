"""add recurring fixed expense templates and occurrences

Revision ID: 0007_recurring_expenses
Revises: 0006_event_receipts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_recurring_expenses"
down_revision: str | None = "0006_event_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recurring_expenses",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("amount_myr", sa.Integer(), nullable=False),
        sa.Column("frequency", sa.String(16), nullable=False),
        sa.Column("anchor_on", sa.String(10), nullable=False),
        sa.Column("next_due_on", sa.String(10), nullable=False),
        sa.Column("asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("funding_account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("expense_account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("category_id", sa.String(32), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("amount_myr > 0", name="recurring_expense_amount_positive"),
        sa.CheckConstraint(
            "frequency IN ('WEEKLY','MONTHLY','YEARLY')", name="recurring_expense_frequency_valid"
        ),
    )
    op.create_index(
        "ix_recurring_expenses_active_due", "recurring_expenses", ["active", "next_due_on"]
    )

    op.create_table(
        "recurring_expense_occurrences",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "recurring_expense_id",
            sa.String(32),
            sa.ForeignKey("recurring_expenses.id"),
            nullable=False,
        ),
        sa.Column("due_on", sa.String(10), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("scheduled_amount_myr", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), unique=True),
        sa.Column("skip_reason", sa.String(500)),
        sa.Column("handled_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("recurring_expense_id", "due_on", name="uq_recurring_expense_occurrence_due"),
        sa.CheckConstraint(
            "action IN ('RECORDED','SKIPPED')", name="recurring_expense_occurrence_action_valid"
        ),
        sa.CheckConstraint("scheduled_amount_myr > 0", name="recurring_expense_occurrence_amount_positive"),
        sa.CheckConstraint(
            "((action = 'RECORDED' AND event_id IS NOT NULL AND skip_reason IS NULL) "
            "OR (action = 'SKIPPED' AND event_id IS NULL))",
            name="recurring_expense_occurrence_fields_valid",
        ),
    )
    op.create_index(
        "ix_recurring_expense_occurrences_expense_due",
        "recurring_expense_occurrences",
        ["recurring_expense_id", "due_on"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recurring_expense_occurrences_expense_due", table_name="recurring_expense_occurrences"
    )
    op.drop_table("recurring_expense_occurrences")
    op.drop_index("ix_recurring_expenses_active_due", table_name="recurring_expenses")
    op.drop_table("recurring_expenses")
