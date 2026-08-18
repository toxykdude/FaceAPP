"""
Provision the ``member_portal`` RLS role in the TEST database.

Imported by ``tests/conftest.py`` BEFORE ``main`` (and therefore
``core.database``) is imported: ``PortalSessionLocal`` is created at import
time from ``MEMBER_PORTAL_DATABASE_URL``, so the env var must exist by then.

What this mirrors from ``scripts/migrations/001_rls_setup.sql`` (section 7):

- role ``member_portal`` (NOINHERIT LOGIN) with a deterministic TEST password,
- GRANT CONNECT + schema USAGE + SELECT on the five portal tables,
- ENABLE ROW LEVEL SECURITY on those tables,
- the five ``portal_*`` SELECT policies scoped to ``current_setting(
  'app.member_id', true)``.

Role CREATION needs CREATEROLE/superuser. CI's DATABASE_URL user is the
service-container superuser, so the direct path works there. On a dev box the
connecting role is usually just the DB/table owner (no CREATEROLE), so we fall
back to the local cluster superuser via ``su postgres`` peer auth. Everything
else (grants, RLS, policies) is done on the app's own connection because the
dev role owns the database and the tables.

Everything is best-effort: on any failure the env var stays unset and the RLS
tests skip with the recorded reason. Already-enabled RLS and existing policies
are idempotent no-ops (DROP POLICY IF EXISTS + CREATE).

Security note: the password below is a TEST-only credential for a role whose
read access is confined to its own rows by RLS. It is never a production
secret and grants no write access anywhere.
"""

import logging
import os
import subprocess
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

log = logging.getLogger(__name__)

PORTAL_ROLE = "member_portal"
PORTAL_TEST_PASSWORD = "member_portal_localtest"

# The five tables 001_rls_setup.sql grants member_portal SELECT on.
PORTAL_TABLES = (
    "members",
    "memberships",
    "sales_transactions",
    "membership_plans",
    "access_events",
)

_last_error: str = ""


def provisioning_error() -> str:
    """Why the last provisioning attempt failed ("" when it did not)."""
    return _last_error


def portal_role_exists(engine) -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
                {"role": PORTAL_ROLE},
            ).scalar()
        )


def _create_or_alter_role_sql(exists: bool) -> str:
    verb = "ALTER ROLE" if exists else "CREATE ROLE"
    return f"{verb} {PORTAL_ROLE} NOINHERIT LOGIN " f"PASSWORD '{PORTAL_TEST_PASSWORD}'"


def _ensure_role_via_cluster_superuser(database: str, exists: bool) -> bool:
    """Dev-box fallback: peer-authenticated local superuser via su postgres."""
    statement = _create_or_alter_role_sql(exists)
    cmd = f'psql -d {database} -c "{statement}"'
    try:
        proc = subprocess.run(
            ["su", "postgres", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.info("su postgres fallback unavailable: %s", exc)
        return False
    return proc.returncode == 0


def _ensure_role(engine, database: str) -> bool:
    exists = portal_role_exists(engine)
    try:
        with engine.begin() as conn:
            conn.execute(text(_create_or_alter_role_sql(exists)))
        return True
    except Exception as exc:  # insufficient privilege — try the superuser path
        log.info(
            "Direct %s failed (%s); trying local cluster superuser",
            "ALTER ROLE" if exists else "CREATE ROLE",
            exc,
        )
        return _ensure_role_via_cluster_superuser(database, exists)


def _apply_grants_and_policies(engine, database: str) -> None:
    """Grants + RLS + the five member_portal policies (001 §7, verbatim)."""
    statements = [
        f'GRANT CONNECT ON DATABASE "{database}" TO {PORTAL_ROLE}',
        f"GRANT USAGE ON SCHEMA public TO {PORTAL_ROLE}",
    ]
    statements += [f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" for t in PORTAL_TABLES]
    statements += [f"GRANT SELECT ON {t} TO {PORTAL_ROLE}" for t in PORTAL_TABLES]
    # Policies use the exact definitions from 001_rls_setup.sql:153-171.
    statements += [
        "DROP POLICY IF EXISTS portal_own_member ON members",
        (
            "CREATE POLICY portal_own_member ON members FOR SELECT TO "
            f"{PORTAL_ROLE} USING (id::text = "
            "current_setting('app.member_id', true))"
        ),
        "DROP POLICY IF EXISTS portal_own_memberships ON memberships",
        (
            "CREATE POLICY portal_own_memberships ON memberships FOR SELECT TO "
            f"{PORTAL_ROLE} USING (member_id::text = "
            "current_setting('app.member_id', true))"
        ),
        "DROP POLICY IF EXISTS portal_own_sales ON sales_transactions",
        (
            "CREATE POLICY portal_own_sales ON sales_transactions FOR SELECT "
            f"TO {PORTAL_ROLE} USING (member_id::text = "
            "current_setting('app.member_id', true))"
        ),
        "DROP POLICY IF EXISTS portal_plans ON membership_plans",
        (
            f"CREATE POLICY portal_plans ON membership_plans FOR SELECT TO "
            f"{PORTAL_ROLE} USING (true)"
        ),
        "DROP POLICY IF EXISTS portal_own_events ON access_events",
        (
            "CREATE POLICY portal_own_events ON access_events FOR SELECT TO "
            f"{PORTAL_ROLE} USING (member_id::text = "
            "current_setting('app.member_id', true))"
        ),
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def _verify_portal_login(portal_url: str) -> None:
    """The provisioning only counts if the role can actually connect."""
    probe = create_engine(portal_url, poolclass=NullPool)
    try:
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
    finally:
        probe.dispose()


def ensure_member_portal_env() -> Optional[str]:
    """Provision the portal role and set MEMBER_PORTAL_DATABASE_URL.

    Returns the URL on success, None on failure (caller tests skip with the
    recorded reason). An explicitly pre-set env var is respected as-is: the
    operator then owns provisioning and we do not touch the database.
    """
    global _last_error
    if os.environ.get("MEMBER_PORTAL_DATABASE_URL"):
        return os.environ["MEMBER_PORTAL_DATABASE_URL"]

    from core.config import settings  # deferred: cheap, no core.database side effects

    try:
        url = make_url(settings.DATABASE_URL)
        database = url.database
        if not database:
            _last_error = "DATABASE_URL has no database component"
            return None
        engine = create_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            if not _ensure_role(engine, database):
                _last_error = (
                    f"cannot create/alter role {PORTAL_ROLE} "
                    "(no CREATEROLE on the connecting role and no local "
                    "cluster superuser fallback)"
                )
                return None
            _apply_grants_and_policies(engine, database)
        finally:
            engine.dispose()

        # NOTE: str(url) masks the password as "***"; the unmasked render is
        # required for a usable connection string (SQLAlchemy 2.0 behavior).
        portal_url = url.set(username=PORTAL_ROLE, password=PORTAL_TEST_PASSWORD)
        portal_url_str = portal_url.render_as_string(hide_password=False)
        _verify_portal_login(portal_url_str)
        os.environ["MEMBER_PORTAL_DATABASE_URL"] = portal_url_str

        # Import order hazard: core/__init__.py imports core.database, and our
        # own deferred ``from core.config import settings`` above triggers it
        # BEFORE the env var is set — so core.database has already decided
        # PortalSessionLocal is None. Patch BOTH the Settings singleton (for
        # anything that reads the attribute) and core.database itself, using
        # exactly the construction core.database would have used.
        settings.MEMBER_PORTAL_DATABASE_URL = portal_url_str
        from core import database as core_database
        from sqlalchemy.orm import sessionmaker

        if core_database.PortalSessionLocal is None:
            core_database._portal_engine = create_engine(
                portal_url_str,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                connect_args={"options": "-c client_encoding=UTF8"},
            )
            core_database.PortalSessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=core_database._portal_engine,
            )
        log.info("Provisioned %s RLS role for portal security tests", PORTAL_ROLE)
        return portal_url_str
    except Exception as exc:  # best-effort by contract
        _last_error = f"{type(exc).__name__}: {exc}"
        log.warning(
            "member_portal provisioning failed (%s) — RLS tests will skip",
            _last_error,
        )
        return None
