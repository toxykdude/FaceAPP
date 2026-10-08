"""add wifi_sessions table (captive portal accounting)

Revision ID: a3f8c2d91e47
Revises: 8d7e6f5a4b3c
Create Date: 2026-10-07 01:00:00.000000

New capability: wifi-captive-portal (see openspec/changes/wifi-captive-portal).
Stores RADIUS accounting sessions opened by the pfSense captive portal via
the radius_service.

RLS note (trap 20 family): new tables do not inherit RLS. This table carries
no member-scoped secrets (it is service-written, staff-read), but it is
enabled for row-level security with a permissive policy scoped to the app
role so the member_portal role can never read it. The policy creation is
GUARDED by a pg_roles existence check: `backend_app` exists on production
but not in dev/CI, and an unconditional `CREATE POLICY ... TO backend_app`
aborts the migration everywhere else.

Deploy reminder: run as the migration owner role (MIGRATE_DATABASE_URL per
scripts/migrations/002_migration_role.sql) and ALWAYS confirm with
`alembic current` afterwards.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a3f8c2d91e47"
down_revision = "8d7e6f5a4b3c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wifi_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("nas_ip", sa.String(length=64), nullable=False),
        sa.Column("acct_session_id", sa.String(length=128), nullable=False),
        sa.Column("framed_ip", sa.String(length=64), nullable=True),
        sa.Column("calling_station_id", sa.String(length=32), nullable=True),
        sa.Column("acct_input_octets", sa.BigInteger(), nullable=False),
        sa.Column("acct_output_octets", sa.BigInteger(), nullable=False),
        sa.Column("acct_session_time", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_update_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("terminate_cause", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "nas_ip", "acct_session_id", name="uq_wifi_sessions_nas_acct_id"
        ),
    )
    op.create_index(
        op.f("ix_wifi_sessions_member_id"), "wifi_sessions", ["member_id"], unique=False
    )
    op.create_index(
        op.f("ix_wifi_sessions_username"), "wifi_sessions", ["username"], unique=False
    )
    op.create_index(
        op.f("ix_wifi_sessions_ended_at"), "wifi_sessions", ["ended_at"], unique=False
    )

    # RLS: enable unconditionally (the table owner — the migrator role —
    # bypasses it in dev/CI), and grant the app role full row access only
    # when that role exists. The member_portal role gets NO policy and is
    # therefore denied by RLS.
    op.execute("ALTER TABLE wifi_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'backend_app') THEN
                EXECUTE 'CREATE POLICY wifi_sessions_app_all ON wifi_sessions '
                    || 'FOR ALL TO backend_app USING (true) WITH CHECK (true)';
                EXECUTE 'GRANT SELECT, INSERT, UPDATE ON wifi_sessions '
                    || 'TO backend_app';
            END IF;
        END
        $$
        """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'wifi_sessions'
                  AND policyname = 'wifi_sessions_app_all'
            ) THEN
                EXECUTE 'DROP POLICY wifi_sessions_app_all ON wifi_sessions';
            END IF;
        END
        $$
        """)
    op.execute("ALTER TABLE wifi_sessions DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f("ix_wifi_sessions_ended_at"), table_name="wifi_sessions")
    op.drop_index(op.f("ix_wifi_sessions_username"), table_name="wifi_sessions")
    op.drop_index(op.f("ix_wifi_sessions_member_id"), table_name="wifi_sessions")
    op.drop_table("wifi_sessions")
