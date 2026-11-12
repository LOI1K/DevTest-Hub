"""Add explicit Docker Volume deletion confirmation.

Revision ID: a4e77fd8b2c1
Revises: cb93826810f7
"""

from alembic import op
import sqlalchemy as sa


revision = "a4e77fd8b2c1"
down_revision = "cb93826810f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "environments",
        sa.Column(
            "delete_volume_on_delete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "environments",
        "delete_volume_on_delete",
    )
