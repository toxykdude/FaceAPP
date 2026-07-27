"""add_enrollment_requests_table

Revision ID: f0786144f6c0
Revises: c3d4e5f6a7b8
Create Date: 2026-04-16 13:17:21.112282

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f0786144f6c0"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrollment_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("result_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_enrollment_requests_device_id"),
        "enrollment_requests",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_enrollment_requests_member_id"),
        "enrollment_requests",
        ["member_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_enrollment_requests_status"),
        "enrollment_requests",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_enrollment_requests_status"), table_name="enrollment_requests"
    )
    op.drop_index(
        op.f("ix_enrollment_requests_member_id"), table_name="enrollment_requests"
    )
    op.drop_index(
        op.f("ix_enrollment_requests_device_id"), table_name="enrollment_requests"
    )
    op.drop_table("enrollment_requests")
