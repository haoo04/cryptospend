"""create core ledger tables

Revision ID: 0001_core_ledger
Revises: 0000_bootstrap
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_core_ledger"
down_revision: str | None = "0000_bootstrap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("reporting_currency", sa.String(16), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("cost_method", sa.String(32), nullable=False),
        sa.Column("reconciliation_tolerance_micros", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("decimals", sa.Integer(), nullable=False),
        sa.Column("chain", sa.String(64)),
        sa.Column("contract_address", sa.String(160)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("decimals >= 0 AND decimals <= 30", name="asset_decimals_range"),
    )
    op.create_index("ix_assets_symbol", "assets", ["symbol"])
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("account_type", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(80)),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "account_type IN ('ASSET','LIABILITY','INCOME','EXPENSE','EQUITY','GAIN_LOSS','CLEARING')",
            name="account_type_valid",
        ),
        sa.UniqueConstraint("name", "account_type", "provider", name="uq_account_identity"),
    )
    op.create_index("ix_accounts_account_type", "accounts", ["account_type"])
    op.create_table(
        "transaction_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.Column("time_precision", sa.String(16), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(200)),
        sa.Column("transaction_value_myr", sa.Integer()),
        sa.Column("reference_value_myr", sa.Integer()),
        sa.Column("reverses_event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), unique=True),
        sa.Column("reversed_by_event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), unique=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("posted_at", sa.String(40)),
        sa.CheckConstraint("status IN ('DRAFT','POSTED','REVERSED')", name="event_status_valid"),
        sa.CheckConstraint("time_precision IN ('EXACT','DATE_ONLY')", name="event_time_precision_valid"),
    )
    op.create_index("ix_transaction_events_event_type", "transaction_events", ["event_type"])
    op.create_index("ix_transaction_events_status", "transaction_events", ["status"])
    op.create_index("ix_transaction_events_occurred_at", "transaction_events", ["occurred_at"])
    op.create_index("ix_events_status_occurred", "transaction_events", ["status", "occurred_at"])
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "event_id", sa.String(32), sa.ForeignKey("transaction_events.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("book_amount_myr", sa.Integer(), nullable=False),
        sa.Column("transaction_value_myr", sa.Integer()),
        sa.Column("reference_value_myr", sa.Integer()),
        sa.Column("valuation_rate", sa.Text()),
        sa.Column("valuation_source", sa.String(120)),
        sa.CheckConstraint("direction IN ('DEBIT','CREDIT')", name="entry_direction_valid"),
        sa.CheckConstraint("book_amount_myr >= 0", name="entry_book_amount_nonnegative"),
    )
    op.create_index("ix_ledger_entries_event_id", "ledger_entries", ["event_id"])
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])
    op.create_index("ix_ledger_entries_asset_id", "ledger_entries", ["asset_id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_audit_logs_event_id", "audit_logs", ["event_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.execute(
        "CREATE TRIGGER ledger_entries_immutable_update BEFORE UPDATE ON ledger_entries "
        "WHEN (SELECT status FROM transaction_events WHERE id = OLD.event_id) <> 'DRAFT' "
        "BEGIN SELECT RAISE(ABORT, 'posted ledger entries are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER ledger_entries_immutable_delete BEFORE DELETE ON ledger_entries "
        "WHEN (SELECT status FROM transaction_events WHERE id = OLD.event_id) <> 'DRAFT' "
        "BEGIN SELECT RAISE(ABORT, 'posted ledger entries are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER audit_logs_append_only_update BEFORE UPDATE ON audit_logs "
        "BEGIN SELECT RAISE(ABORT, 'audit logs are append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER audit_logs_append_only_delete BEFORE DELETE ON audit_logs "
        "BEGIN SELECT RAISE(ABORT, 'audit logs are append-only'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only_delete")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only_update")
    op.execute("DROP TRIGGER IF EXISTS ledger_entries_immutable_delete")
    op.execute("DROP TRIGGER IF EXISTS ledger_entries_immutable_update")
    op.drop_table("audit_logs")
    op.drop_table("ledger_entries")
    op.drop_table("transaction_events")
    op.drop_table("accounts")
    op.drop_table("assets")
    op.drop_table("settings")
