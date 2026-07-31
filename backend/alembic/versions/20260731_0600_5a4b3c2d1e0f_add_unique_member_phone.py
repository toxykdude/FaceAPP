"""add_unique_member_phone

Revision ID: 5a4b3c2d1e0f
Revises: e1f2a3b4c5d6
Create Date: 2026-07-31 06:00:00.000000

Adds a partial unique index on members.phone (WS-9). The column stays
nullable (multiple NULLs allowed); only non-NULL phones must be unique so a
member can be uniquely identified by phone for the portal PIN login.

NOTE: this migration FAILS LOUDLY if duplicate non-NULL phones already exist
in the members table. The operator MUST dedupe them first — biometric
accounts are legally sensitive (Ley 1581/2012) and cannot be merged silently.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "5a4b3c2d1e0f"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_members_phone_unique",
        "members",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_members_phone_unique", table_name="members")
