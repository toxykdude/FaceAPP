"""price_check + wompi_reference idempotency

Revision ID: 8d7e6f5a4b3c
Revises: 7c6d5e4f3a2b
Create Date: 2026-08-18 10:00:00.000000

Two structural guarantees for payment integrity (spec payment-integrity):

1. ``membership_plans`` gains ``CHECK (price > 0)`` — a zero-price plan is
   rejected by the database no matter which code path inserts it. The
   constraint is preceded by a fail-loud pre-check that LISTS violating rows
   (name + price) and aborts, so an operator fixes the data instead of
   discovering a broken migration half-way through.
2. ``sales_transactions`` gains ``wompi_reference VARCHAR(100) NULL`` with a
   UNIQUE index — the exact idempotency key the webhook commits against
   (design D1/D6), replacing fuzzy ``notes LIKE`` matching. Existing rows are
   backfilled from the ``Wompi ref: <ref> | Wompi tx:`` notes format; rows
   without Wompi notes stay NULL (multiple NULLs are allowed by Postgres
   unique indexes).

Trap-20 mechanics (runbook): migrations run as the DEDICATED migrator role,
never as the app role — ``backend_app`` owns nothing on purpose, and making
it an owner would hand the internet-facing credential RLS-bypassing DDL
authority. Deploy sequence:

    cd backend
    set -a; . ./.env; . /etc/faceapp/migrate-db.env; set +a
    ./venv/bin/alembic upgrade head
    ./venv/bin/alembic current   # ALWAYS confirm the head actually moved

``alembic/env.py`` prefers ``MIGRATE_DATABASE_URL`` over ``DATABASE_URL``
(``core.config.resolve_migration_database_url``); local dev, CI and the
in-process migration tests fall back to ``DATABASE_URL`` where the connecting
role already owns the schema.

Downgrade drops ONLY the CHECK constraint and the unique index; the
``wompi_reference`` column and its backfilled data are retained (rollback
must not destroy payment records). Un-consumed Redis pending keys expire
within 24h.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "8d7e6f5a4b3c"
down_revision = "7c6d5e4f3a2b"
branch_labels = None
depends_on = None

CHECK_NAME = "ck_membership_plans_price_positive"
INDEX_NAME = "ix_sales_transactions_wompi_reference"


def upgrade() -> None:
    bind = op.get_bind()

    # Fail-loud pre-check: list every violating row before the CHECK exists,
    # so the fix is an operator decision rather than a mid-migration error.
    violating = bind.execute(
        sa.text(
            "SELECT id, name, price FROM membership_plans "
            "WHERE price <= 0 ORDER BY price"
        )
    ).fetchall()
    if violating:
        rows = ", ".join(f"{row.name} (price={row.price})" for row in violating)
        raise RuntimeError(
            "membership_plans contains rows with price <= 0; the "
            "CHECK (price > 0) constraint cannot be applied until they are "
            f"corrected or removed: {rows}"
        )

    op.create_check_constraint(CHECK_NAME, "membership_plans", "price > 0")

    # IF NOT EXISTS: the downgrade deliberately RETAINS this column (see
    # docstring), so a later re-upgrade must not collide with it. Same
    # idempotent-DDL precedent as 6b5c4d3e2f1a's DROP INDEX IF EXISTS.
    op.execute(
        "ALTER TABLE sales_transactions "
        "ADD COLUMN IF NOT EXISTS wompi_reference VARCHAR(100)"
    )
    # Backfill from the historical notes format. btrim guards against a
    # trailing space before the "|" separator.
    op.execute(
        "UPDATE sales_transactions SET wompi_reference = "
        "btrim(substring(notes FROM 'Wompi ref:\\s*([A-Za-z0-9._-]+)')) "
        "WHERE wompi_reference IS NULL AND notes IS NOT NULL "
        "AND notes ~ 'Wompi ref:'"
    )
    op.create_index(INDEX_NAME, "sales_transactions", ["wompi_reference"], unique=True)


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="sales_transactions")
    op.drop_constraint(CHECK_NAME, "membership_plans", type_="check")
    # wompi_reference column intentionally retained — see docstring.
