"""drop_legacy_unique_member_phone_index

Revision ID: 6b5c4d3e2f1a
Revises: 5a4b3c2d1e0f
Create Date: 2026-08-05 02:00:00.000000

Removes the historical DEV-only unique phone index without changing member
records. Phone remains nullable, non-unique contact data in both directions.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "6b5c4d3e2f1a"
down_revision = "5a4b3c2d1e0f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_members_phone_unique")


def downgrade() -> None:
    pass
