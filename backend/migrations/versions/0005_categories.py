"""add managed transaction categories

Revision ID: 0005_categories
Revises: 0004_reporting_journeys
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0005_categories"
down_revision: str | None = "0004_reporting_journeys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_CATEGORIES = (
    ("EXPENSE", "Food"),
    ("EXPENSE", "Grocery"),
    ("EXPENSE", "Utilities"),
    ("EXPENSE", "Transport"),
    ("EXPENSE", "Shopping"),
    ("EXPENSE", "Subscription"),
    ("EXPENSE", "Entertainment"),
    ("EXPENSE", "Travel"),
    ("EXPENSE", "Healthcare"),
    ("EXPENSE", "Other Expense"),
    ("INCOME", "Salary"),
    ("INCOME", "Bonus"),
    ("INCOME", "Cashback"),
    ("INCOME", "Crypto Reward"),
    ("INCOME", "Other Income"),
)


def clean_name(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_name(value: str) -> str:
    return clean_name(value).casefold()


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("normalized_name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("kind IN ('INCOME','EXPENSE')", name="category_kind_valid"),
        sa.UniqueConstraint("kind", "normalized_name", name="uq_category_kind_name"),
    )
    op.create_index("ix_categories_kind", "categories", ["kind"])
    op.create_index("ix_categories_kind_active_name", "categories", ["kind", "active", "name"])

    op.execute("DROP TRIGGER IF EXISTS ledger_entries_immutable_update")
    op.execute("DROP TRIGGER IF EXISTS ledger_entries_immutable_delete")
    with op.batch_alter_table("transaction_events") as batch_op:
        batch_op.add_column(
            sa.Column(
                "category_id",
                sa.String(32),
                sa.ForeignKey("categories.id", name="fk_transaction_events_category_id_categories"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_transaction_events_category_id", ["category_id"])
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

    connection = op.get_bind()
    categories = sa.table(
        "categories",
        sa.column("id", sa.String(32)),
        sa.column("name", sa.String(100)),
        sa.column("normalized_name", sa.String(100)),
        sa.column("kind", sa.String(16)),
        sa.column("active", sa.Boolean()),
        sa.column("created_at", sa.String(40)),
        sa.column("updated_at", sa.String(40)),
    )
    events = sa.table(
        "transaction_events",
        sa.column("id", sa.String(32)),
        sa.column("category", sa.String(100)),
        sa.column("category_id", sa.String(32)),
    )
    entries = sa.table("ledger_entries", sa.column("event_id", sa.String(32)), sa.column("account_id", sa.String(32)))
    accounts = sa.table(
        "accounts", sa.column("id", sa.String(32)), sa.column("account_type", sa.String(32))
    )
    now = datetime.now(UTC).isoformat()
    connection.execute(
        categories.insert(),
        [
            {
                "id": uuid4().hex,
                "name": name,
                "normalized_name": normalize_name(name),
                "kind": kind,
                "active": True,
                "created_at": now,
                "updated_at": now,
            }
            for kind, name in DEFAULT_CATEGORIES
        ],
    )

    event_kinds: dict[str, set[str]] = defaultdict(set)
    for event_id, account_type in connection.execute(
        sa.select(entries.c.event_id, accounts.c.account_type).join(accounts, accounts.c.id == entries.c.account_id)
    ):
        if account_type in {"INCOME", "EXPENSE"}:
            event_kinds[event_id].add(account_type)

    for event_id, old_name in connection.execute(
        sa.select(events.c.id, events.c.category).where(events.c.category.is_not(None))
    ):
        kinds = event_kinds.get(event_id, set())
        kind = next(iter(kinds)) if len(kinds) == 1 else None
        name = clean_name(old_name or "")
        if kind is None or not name:
            continue
        normalized = normalize_name(name)
        category_id = connection.execute(
            sa.select(categories.c.id).where(
                categories.c.kind == kind,
                categories.c.normalized_name == normalized,
            )
        ).scalar_one_or_none()
        if category_id is None:
            category_id = uuid4().hex
            connection.execute(
                categories.insert().values(
                    id=category_id,
                    name=name,
                    normalized_name=normalized,
                    kind=kind,
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        connection.execute(events.update().where(events.c.id == event_id).values(category_id=category_id))


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ledger_entries_immutable_update")
    op.execute("DROP TRIGGER IF EXISTS ledger_entries_immutable_delete")
    with op.batch_alter_table("transaction_events") as batch_op:
        batch_op.drop_index("ix_transaction_events_category_id")
        batch_op.drop_column("category_id")
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
    op.drop_index("ix_categories_kind_active_name", table_name="categories")
    op.drop_index("ix_categories_kind", table_name="categories")
    op.drop_table("categories")
