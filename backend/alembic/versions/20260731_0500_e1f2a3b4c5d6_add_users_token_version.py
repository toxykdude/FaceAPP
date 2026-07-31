"""add_users_token_version

Revision ID: e1f2a3b4c5d6
Revises: f0786144f6c0
Create Date: 2026-07-31 05:00:00.000000

Adds users.token_version (session-revocation epoch, S6). Default 0 keeps every
existing user + previously-issued JWT valid (a JWT without a "ver" claim is
treated as version 0); the version is bumped on password change/reset to
invalidate prior tokens (CWE-613).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "f0786144f6c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
