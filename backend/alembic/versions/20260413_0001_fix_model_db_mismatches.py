"""Fix model/DB type mismatches and drop orphaned column

Revision ID: a1b2c3d4e5f6
Revises: f180f7bf6d2c
Create Date: 2026-04-13 00:01:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f180f7bf6d2c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop orphaned FK and column on members table
    op.drop_constraint(
        "fk_members_biometric_template_id", "members", type_="foreignkey"
    )
    op.drop_column("members", "biometric_template_id")


def downgrade() -> None:
    op.add_column(
        "members", sa.Column("biometric_template_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_members_biometric_template_id",
        "members",
        "biometric_templates",
        ["biometric_template_id"],
        ["id"],
    )
