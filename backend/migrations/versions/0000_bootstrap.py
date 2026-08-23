"""bootstrap migration framework

Revision ID: 0000_bootstrap
Revises:
"""

from collections.abc import Sequence

revision: str = "0000_bootstrap"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
