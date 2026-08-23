"""add card authorization, settlement, refund and rewards

Revision ID: 0003_card_workflows
Revises: 0002_trading_cost_basis
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_card_workflows"
down_revision: str | None = "0002_trading_cost_basis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_links",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("source_event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), nullable=False),
        sa.Column("target_event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), nullable=False),
        sa.Column("relation_type", sa.String(40), nullable=False),
        sa.CheckConstraint("source_event_id <> target_event_id", name="event_link_events_differ"),
        sa.UniqueConstraint("source_event_id", "target_event_id", "relation_type", name="uq_event_link"),
    )
    op.create_index("ix_event_links_source_event_id", "event_links", ["source_event_id"])
    op.create_index("ix_event_links_target_event_id", "event_links", ["target_event_id"])
    op.create_table(
        "card_transactions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), unique=True),
        sa.Column("parent_card_transaction_id", sa.String(32), sa.ForeignKey("card_transactions.id")),
        sa.Column("original_transaction_id", sa.String(32), sa.ForeignKey("card_transactions.id")),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("provider_account_id", sa.String(160), nullable=False),
        sa.Column("external_id", sa.String(200)),
        sa.Column("transaction_type", sa.String(24), nullable=False),
        sa.Column("card_account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("merchant_name", sa.String(200), nullable=False),
        sa.Column("merchant_country", sa.String(2)),
        sa.Column("merchant_asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("merchant_amount", sa.Text(), nullable=False),
        sa.Column("billing_asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("billing_amount", sa.Text(), nullable=False),
        sa.Column("merchant_value_myr", sa.Integer(), nullable=False),
        sa.Column("funding_value_myr", sa.Integer(), nullable=False),
        sa.Column("separate_fee_value_myr", sa.Integer(), nullable=False),
        sa.Column("gross_economic_cost_myr", sa.Integer(), nullable=False),
        sa.Column("net_economic_cost_myr", sa.Integer(), nullable=False),
        sa.Column("total_leakage_myr", sa.Integer(), nullable=False),
        sa.Column("actual_fx_rate", sa.Text()),
        sa.Column("reference_fx_rate", sa.Text()),
        sa.Column("fx_deviation_myr", sa.Integer()),
        sa.Column("conversion_deviation_myr", sa.Integer()),
        sa.Column("residual_myr", sa.Integer()),
        sa.Column("breakdown_confidence", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("authorized_at", sa.String(40)),
        sa.Column("settled_at", sa.String(40)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("reversed", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "status IN ('AUTHORIZED','SETTLED','PARTIALLY_SETTLED','REVERSED','PARTIALLY_REFUNDED','REFUNDED')",
            name="card_status_valid",
        ),
        sa.CheckConstraint("transaction_type IN ('AUTHORIZATION','PURCHASE','REFUND')", name="card_type_valid"),
        sa.UniqueConstraint("provider", "provider_account_id", "external_id", name="uq_card_external_record"),
    )
    op.create_index("ix_card_transactions_event_id", "card_transactions", ["event_id"])
    op.create_index(
        "ix_card_transactions_parent_card_transaction_id", "card_transactions", ["parent_card_transaction_id"]
    )
    op.create_index("ix_card_transactions_original_transaction_id", "card_transactions", ["original_transaction_id"])
    op.create_index("ix_card_transactions_provider", "card_transactions", ["provider"])
    op.create_index("ix_card_transactions_status", "card_transactions", ["status"])
    op.create_index("ix_card_transactions_settled_at", "card_transactions", ["settled_at"])
    op.create_table(
        "card_holds",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("card_transaction_id", sa.String(32), sa.ForeignKey("card_transactions.id"), unique=True),
        sa.Column("account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("amount", sa.Text(), nullable=False),
        sa.Column("value_myr", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("released_at", sa.String(40)),
        sa.CheckConstraint("status IN ('ACTIVE','RELEASED')", name="card_hold_status_valid"),
    )
    op.create_index("ix_card_holds_card_transaction_id", "card_holds", ["card_transaction_id"])
    op.create_index("ix_card_holds_account_id", "card_holds", ["account_id"])
    op.create_index("ix_card_holds_status", "card_holds", ["status"])
    op.create_table(
        "card_funding_legs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("card_transaction_id", sa.String(32), sa.ForeignKey("card_transactions.id"), nullable=False),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), nullable=False),
        sa.Column("account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("transaction_value_myr", sa.Integer(), nullable=False),
        sa.Column("reference_value_myr", sa.Integer(), nullable=False),
        sa.Column("book_basis_myr", sa.Integer(), nullable=False),
        sa.Column("actual_conversion_rate", sa.Text()),
        sa.Column("leg_type", sa.String(16), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("reversed", sa.Boolean(), nullable=False),
        sa.CheckConstraint("leg_type IN ('FUNDING','REFUND')", name="card_leg_type_valid"),
    )
    op.create_index("ix_card_funding_legs_card_transaction_id", "card_funding_legs", ["card_transaction_id"])
    op.create_index("ix_card_funding_legs_event_id", "card_funding_legs", ["event_id"])
    op.create_table(
        "card_cost_components",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("card_transaction_id", sa.String(32), sa.ForeignKey("card_transactions.id"), nullable=False),
        sa.Column("component_type", sa.String(48), nullable=False),
        sa.Column("value_myr", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("calculation_method", sa.String(240), nullable=False),
        sa.Column("confidence", sa.String(32), nullable=False),
    )
    op.create_index("ix_card_cost_components_card_transaction_id", "card_cost_components", ["card_transaction_id"])
    op.create_table(
        "rewards",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("card_transaction_id", sa.String(32), sa.ForeignKey("card_transactions.id"), nullable=False),
        sa.Column("event_id", sa.String(32), sa.ForeignKey("transaction_events.id"), unique=True),
        sa.Column("reward_type", sa.String(48), nullable=False),
        sa.Column("account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("asset_id", sa.String(32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("amount", sa.Text(), nullable=False),
        sa.Column("value_myr", sa.Integer()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("earned_at", sa.String(40), nullable=False),
        sa.Column("credited_at", sa.String(40)),
        sa.Column("reversed_at", sa.String(40)),
        sa.Column("external_id", sa.String(200)),
        sa.CheckConstraint("status IN ('PENDING','CREDITED','REVERSED','EXPIRED')", name="reward_status_valid"),
    )
    op.create_index("ix_rewards_card_transaction_id", "rewards", ["card_transaction_id"])
    op.create_index("ix_rewards_event_id", "rewards", ["event_id"])
    op.create_index("ix_rewards_status", "rewards", ["status"])


def downgrade() -> None:
    op.drop_table("rewards")
    op.drop_table("card_cost_components")
    op.drop_table("card_funding_legs")
    op.drop_table("card_holds")
    op.drop_table("card_transactions")
    op.drop_table("event_links")
