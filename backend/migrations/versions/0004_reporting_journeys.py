"""add reporting channels, journeys and monthly snapshots

Revision ID: 0004_reporting_journeys
Revises: 0003_card_workflows
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_reporting_journeys"
down_revision: str | None = "0003_card_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("card_holds") as batch_op:
        batch_op.alter_column(
            "card_transaction_id",
            existing_type=sa.String(32),
            nullable=False,
        )
    for table_name in ("trades", "transfers", "card_transactions", "card_holds", "rewards"):
        index_name = f"ix_{table_name}_event_id" if table_name != "card_holds" else "ix_card_holds_card_transaction_id"
        column_name = "event_id" if table_name != "card_holds" else "card_transaction_id"
        op.drop_index(index_name, table_name=table_name)
        op.create_index(index_name, table_name, [column_name], unique=True)

    op.add_column(
        "accounts",
        sa.Column("channel_type", sa.String(24), nullable=False, server_default="OTHER"),
    )
    op.create_index("ix_accounts_channel_type", "accounts", ["channel_type"])
    op.execute("UPDATE accounts SET channel_type = 'BANK' WHERE name = 'Bank'")
    op.execute("UPDATE accounts SET channel_type = 'CASH' WHERE name = 'Cash'")
    op.execute("UPDATE accounts SET channel_type = 'CRYPTO_WALLET' WHERE name = 'Crypto Wallet'")

    op.create_table(
        "journeys",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("journey_type", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("allocation_method", sa.String(160), nullable=False),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.Column("notes", sa.String(500), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("journey_type IN ('FUNDS','PAYMENT','WITHDRAWAL')", name="journey_type_valid"),
        sa.CheckConstraint("status IN ('DRAFT','CONFIRMED','COMPLETED')", name="journey_status_valid"),
        sa.CheckConstraint(
            "confidence IN ('EXACT','HIGH','ESTIMATED','MISSING_INPUT')", name="journey_confidence_valid"
        ),
    )
    op.create_index("ix_journeys_journey_type", "journeys", ["journey_type"])
    op.create_index("ix_journeys_status", "journeys", ["status"])

    op.create_table(
        "journey_event_links",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("journey_id", sa.String(32), sa.ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), nullable=False),
        sa.Column("relation_type", sa.String(40), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.UniqueConstraint("journey_id", "event_id", name="uq_journey_event"),
    )
    op.create_index("ix_journey_event_links_journey_id", "journey_event_links", ["journey_id"])
    op.create_index("ix_journey_event_links_event_id", "journey_event_links", ["event_id"])

    op.create_table(
        "journey_allocations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "event_link_id",
            sa.String(32),
            sa.ForeignKey("journey_event_links.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("allocation_role", sa.String(24), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("value_myr", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(160), nullable=False),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "allocation_role IN ('INPUT','INTERMEDIATE','OUTPUT','COST')", name="journey_allocation_role_valid"
        ),
        sa.CheckConstraint("value_myr >= 0", name="journey_allocation_value_nonnegative"),
        sa.CheckConstraint(
            "confidence IN ('EXACT','HIGH','ESTIMATED','MISSING_INPUT')",
            name="journey_allocation_confidence_valid",
        ),
    )
    op.create_index("ix_journey_allocations_event_link_id", "journey_allocations", ["event_link_id"])
    op.create_index("ix_journey_allocations_asset_id", "journey_allocations", ["asset_id"])

    op.create_table(
        "report_snapshots",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("snapshot_type", sa.String(24), nullable=False),
        sa.Column("period_key", sa.String(16), nullable=False),
        sa.Column("period_start", sa.String(40), nullable=False),
        sa.Column("as_of", sa.String(40), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("snapshot_type IN ('MONTHLY')", name="report_snapshot_type_valid"),
    )
    op.create_index("ix_report_snapshots_snapshot_type", "report_snapshots", ["snapshot_type"])
    op.create_index("ix_report_snapshots_period_key", "report_snapshots", ["period_key"])
    op.create_index("ix_report_snapshots_as_of", "report_snapshots", ["as_of"])
    op.create_index("ix_report_snapshots_checksum", "report_snapshots", ["checksum"])
    op.execute(
        "CREATE TRIGGER report_snapshots_immutable_update BEFORE UPDATE ON report_snapshots "
        "BEGIN SELECT RAISE(ABORT, 'report snapshots are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER report_snapshots_immutable_delete BEFORE DELETE ON report_snapshots "
        "BEGIN SELECT RAISE(ABORT, 'report snapshots are immutable'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS report_snapshots_immutable_delete")
    op.execute("DROP TRIGGER IF EXISTS report_snapshots_immutable_update")
    op.drop_table("report_snapshots")
    op.drop_table("journey_allocations")
    op.drop_table("journey_event_links")
    op.drop_table("journeys")
    op.drop_index("ix_accounts_channel_type", table_name="accounts")
    op.drop_column("accounts", "channel_type")
    for table_name in ("trades", "transfers", "card_transactions", "card_holds", "rewards"):
        index_name = f"ix_{table_name}_event_id" if table_name != "card_holds" else "ix_card_holds_card_transaction_id"
        column_name = "event_id" if table_name != "card_holds" else "card_transaction_id"
        op.drop_index(index_name, table_name=table_name)
        op.create_index(index_name, table_name, [column_name], unique=False)
    with op.batch_alter_table("card_holds") as batch_op:
        batch_op.alter_column(
            "card_transaction_id",
            existing_type=sa.String(32),
            nullable=True,
        )
