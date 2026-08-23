"""add trading, transfers, fees, rates and FIFO lots

Revision ID: 0002_trading_cost_basis
Revises: 0001_core_ledger
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_trading_cost_basis"
down_revision: str | None = "0001_core_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), nullable=False, unique=True),
        sa.Column("account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("sell_asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("buy_asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("sell_quantity", sa.Text(), nullable=False),
        sa.Column("buy_quantity", sa.Text(), nullable=False),
        sa.Column("execution_rate", sa.Text(), nullable=False),
        sa.Column("gross_value_myr", sa.Integer(), nullable=False),
        sa.Column("net_value_myr", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(200)),
        sa.Column("reversed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_trades_event_id", "trades", ["event_id"])
    op.create_table(
        "trade_fills",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("trade_id", sa.String(32), sa.ForeignKey("trades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filled_at", sa.String(40), nullable=False),
        sa.Column("sell_quantity", sa.Text(), nullable=False),
        sa.Column("buy_quantity", sa.Text(), nullable=False),
        sa.Column("price", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(200)),
    )
    op.create_index("ix_trade_fills_trade_id", "trade_fills", ["trade_id"])
    op.create_table(
        "transfers",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), nullable=False, unique=True),
        sa.Column("source_account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("destination_account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("sent_quantity", sa.Text(), nullable=False),
        sa.Column("received_quantity", sa.Text(), nullable=False),
        sa.Column("network", sa.String(80)),
        sa.Column("tx_hash", sa.String(200)),
        sa.Column("match_status", sa.String(32), nullable=False),
        sa.Column("reversed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_transfers_event_id", "transfers", ["event_id"])
    op.create_index("ix_transfers_tx_hash", "transfers", ["tx_hash"])
    op.create_table(
        "fee_components",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), nullable=False),
        sa.Column("component_type", sa.String(64), nullable=False),
        sa.Column("asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("amount", sa.Text(), nullable=False),
        sa.Column("value_myr", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("included_in_funding_amount", sa.Boolean(), nullable=False),
        sa.Column("accounting_treatment", sa.String(32), nullable=False),
        sa.Column("calculation_method", sa.String(160)),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.Column("reversed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_fee_components_event_id", "fee_components", ["event_id"])
    op.create_index("ix_fee_components_component_type", "fee_components", ["component_type"])
    op.create_table(
        "rate_snapshots",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id")),
        sa.Column("base_asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("quote_asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("rate", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.String(40), nullable=False),
        sa.Column("retrieved_at", sa.String(40), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("rate_type", sa.String(32), nullable=False),
        sa.Column("path", sa.Text()),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.CheckConstraint("base_asset_id <> quote_asset_id", name="rate_assets_differ"),
    )
    op.create_index("ix_rate_snapshots_event_id", "rate_snapshots", ["event_id"])
    op.create_index("ix_rate_snapshots_base_asset_id", "rate_snapshots", ["base_asset_id"])
    op.create_index("ix_rate_snapshots_quote_asset_id", "rate_snapshots", ["quote_asset_id"])
    op.create_index("ix_rate_snapshots_observed_at", "rate_snapshots", ["observed_at"])
    op.create_index(
        "ix_rates_pair_observed", "rate_snapshots", ["base_asset_id", "quote_asset_id", "observed_at"]
    )
    op.create_table(
        "cost_lots",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("source_event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), nullable=False),
        sa.Column("parent_lot_id", sa.String(32), sa.ForeignKey("cost_lots.id")),
        sa.Column("acquired_at", sa.String(40), nullable=False),
        sa.Column("original_quantity", sa.Text(), nullable=False),
        sa.Column("remaining_quantity", sa.Text(), nullable=False),
        sa.Column("basis_myr", sa.Integer(), nullable=False),
        sa.Column("remaining_basis_myr", sa.Integer(), nullable=False),
        sa.Column("basis_status", sa.String(24), nullable=False),
        sa.Column("voided", sa.Boolean(), nullable=False),
        sa.CheckConstraint("basis_myr >= 0 AND remaining_basis_myr >= 0", name="lot_basis_nonnegative"),
        sa.CheckConstraint("basis_status IN ('KNOWN','BASIS_UNKNOWN')", name="lot_basis_status_valid"),
    )
    op.create_index("ix_cost_lots_asset_id", "cost_lots", ["asset_id"])
    op.create_index("ix_cost_lots_account_id", "cost_lots", ["account_id"])
    op.create_index("ix_cost_lots_source_event_id", "cost_lots", ["source_event_id"])
    op.create_index("ix_cost_lots_acquired_at", "cost_lots", ["acquired_at"])
    op.create_index("ix_lots_fifo", "cost_lots", ["account_id", "asset_id", "acquired_at", "id"])
    op.create_table(
        "lot_disposals",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), nullable=False),
        sa.Column("cost_lot_id", sa.String(32), sa.ForeignKey("cost_lots.id"), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("basis_myr", sa.Integer(), nullable=False),
        sa.Column("proceeds_myr", sa.Integer(), nullable=False),
        sa.Column("realized_gain_loss_myr", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("reversed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_lot_disposals_event_id", "lot_disposals", ["event_id"])
    op.create_index("ix_lot_disposals_cost_lot_id", "lot_disposals", ["cost_lot_id"])
    op.create_table(
        "lot_transfers",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), nullable=False),
        sa.Column("transfer_id", sa.String(32), sa.ForeignKey("transfers.id"), nullable=False),
        sa.Column("source_lot_id", sa.String(32), sa.ForeignKey("cost_lots.id"), nullable=False),
        sa.Column("destination_lot_id", sa.String(32), sa.ForeignKey("cost_lots.id"), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("basis_myr", sa.Integer(), nullable=False),
        sa.Column("reversed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_lot_transfers_event_id", "lot_transfers", ["event_id"])
    op.create_index("ix_lot_transfers_transfer_id", "lot_transfers", ["transfer_id"])

    op.execute(
        "INSERT INTO cost_lots "
        "(id, asset_id, account_id, source_event_id, parent_lot_id, acquired_at, original_quantity, "
        "remaining_quantity, basis_myr, remaining_basis_myr, basis_status, voided) "
        "SELECT lower(hex(randomblob(16))), le.asset_id, le.account_id, e.id, NULL, e.occurred_at, le.quantity, "
        "le.quantity, le.book_amount_myr, le.book_amount_myr, "
        "CASE WHEN le.book_amount_myr = 0 THEN 'BASIS_UNKNOWN' ELSE 'KNOWN' END, 0 "
        "FROM ledger_entries le "
        "JOIN transaction_events e ON e.id = le.event_id "
        "JOIN accounts a ON a.id = le.account_id "
        "WHERE e.status = 'POSTED' AND e.event_type IN ('OPENING_BALANCE','SALARY','INCOME','REWARD') "
        "AND le.direction = 'DEBIT' AND a.account_type = 'ASSET' AND le.quantity <> '0'"
    )


def downgrade() -> None:
    op.drop_table("lot_transfers")
    op.drop_table("lot_disposals")
    op.drop_table("cost_lots")
    op.drop_table("rate_snapshots")
    op.drop_table("fee_components")
    op.drop_table("transfers")
    op.drop_table("trade_fills")
    op.drop_table("trades")
