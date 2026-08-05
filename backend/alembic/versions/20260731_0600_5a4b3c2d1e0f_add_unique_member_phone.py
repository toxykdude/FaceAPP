"""add_unique_member_phone

Revision ID: 5a4b3c2d1e0f
Revises: e1f2a3b4c5d6
Create Date: 2026-07-31 06:00:00.000000

Reserved no-op. Member phone numbers are nullable, non-unique contact data.
The successor revision removes the index from databases that already applied
the legacy version of this migration.
"""

# revision identifiers, used by Alembic.
revision = "5a4b3c2d1e0f"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
