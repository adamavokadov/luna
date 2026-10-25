"""luna cheer: warm-message preferences on users

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("cheer_freq", sa.String(length=8), server_default="off", nullable=False)
        )
        batch_op.add_column(
            sa.Column("cheer_asked", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column("cheer_last_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("cheer_recent", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("cheer_recent")
        batch_op.drop_column("cheer_last_at")
        batch_op.drop_column("cheer_asked")
        batch_op.drop_column("cheer_freq")
