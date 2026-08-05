"""index_sales_transactions_membership_id

Revision ID: 7c6d5e4f3a2b
Revises: 6b5c4d3e2f1a
Create Date: 2026-08-05 17:00:00.000000

A membership's payment balance is derived by summing the sales transactions
linked to it (Membership.amount_paid), which the kiosk now reads on every
recognition and the admin list reads once per page. `member_id` was already
indexed but `membership_id` never was, so each balance lookup scanned the
whole sales table. Adds the missing index; no data is modified.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "7c6d5e4f3a2b"
down_revision = "6b5c4d3e2f1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_sales_transactions_membership_id",
        "sales_transactions",
        ["membership_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sales_transactions_membership_id", "sales_transactions")
