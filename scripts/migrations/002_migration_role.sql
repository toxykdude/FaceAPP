-- ============================================================
-- FaceGYM: dedicated migration role
--
-- Separates DDL authority from the runtime application role.
--
-- WHY THIS EXISTS
-- Alembic used to be run with the runtime DATABASE_URL (backend_app), which
-- owns nothing, so EVERY DDL migration failed with "must be owner of ...".
-- The tempting fix — grant backend_app ownership — is a standing privilege
-- escalation on the most internet-exposed credential in the system:
--
--   * a table owner can DROP TABLE and TRUNCATE;
--   * a table owner can ALTER TABLE ... DISABLE ROW LEVEL SECURITY, which
--     would neuter the member_portal isolation that 001_rls_setup.sql builds;
--   * a table owner BYPASSES RLS on every table that does not set FORCE ROW
--     LEVEL SECURITY. Only audit_logs sets it — the other 12 RLS tables,
--     including biometric_templates and fingerprint_templates, do not.
--
-- So DDL authority lives in a separate role used only at deploy time, and the
-- runtime role keeps DML-only least privilege. powerhouse_migrator is
-- deliberately NOT a superuser: if its credential leaks, the blast radius is
-- "can alter these tables", not "owns the cluster".
--
-- USAGE
--   1. Replace <SET_MIGRATOR_PASSWORD> below.
--   2. Run as a superuser:
--        sudo -u postgres psql -d membership_db -f 002_migration_role.sql
--   3. Write the URL to /etc/faceapp/migrate-db.env (chmod 0600, root-only):
--        MIGRATE_DATABASE_URL=postgresql://powerhouse_migrator:<pw>@localhost:5432/membership_db
--   4. Deploys then run:
--        set -a; . /etc/faceapp/migrate-db.env; set +a
--        ./venv/bin/alembic upgrade head
--      alembic/env.py prefers MIGRATE_DATABASE_URL over DATABASE_URL
--      (see core/config.py::resolve_migration_database_url).
--
-- Idempotent: safe to re-run.
-- ============================================================

BEGIN;

-- ============================================================
-- 1. CREATE THE MIGRATION ROLE
-- ============================================================
-- NOSUPERUSER / NOCREATEDB / NOCREATEROLE / NOBYPASSRLS are all explicit: this
-- role's only elevated capability is ownership of the tables it migrates.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'powerhouse_migrator') THEN
        CREATE ROLE powerhouse_migrator
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOBYPASSRLS
            PASSWORD '<SET_MIGRATOR_PASSWORD>';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE membership_db TO powerhouse_migrator;
GRANT USAGE, CREATE ON SCHEMA public TO powerhouse_migrator;

-- ============================================================
-- 2. TRANSFER TABLE OWNERSHIP
-- ============================================================
-- Every ordinary table in public, plus alembic_version (Alembic writes its
-- revision pointer there). Views are deliberately NOT reassigned — see step 4.
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT c.relname
        FROM pg_class c
        WHERE c.relkind = 'r'
          AND c.relnamespace = 'public'::regnamespace
    LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO powerhouse_migrator', t);
    END LOOP;
END
$$;

-- ============================================================
-- 3. KEEP THE RUNTIME ROLES WORKING — NOW AND FOR FUTURE TABLES
-- ============================================================
-- Ownership transfer does not revoke existing grants, but a table created by a
-- FUTURE migration would be owned by powerhouse_migrator with no grants at all,
-- and the app would start returning 500s the moment a migration added a table.
-- Default privileges close that gap.
--
-- member_portal is intentionally excluded: its access is granted per-table
-- alongside an explicit RLS policy in 001_rls_setup.sql. Defaulting it to
-- SELECT on every future table would hand portal users a new table before
-- anyone had written a policy to scope it.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO backend_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO backend_readonly;

ALTER DEFAULT PRIVILEGES FOR ROLE powerhouse_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO backend_app;
ALTER DEFAULT PRIVILEGES FOR ROLE powerhouse_migrator IN SCHEMA public
    GRANT SELECT ON TABLES TO backend_readonly;

-- audit_logs stays append-only for the app: SELECT + INSERT, never UPDATE or
-- DELETE (001_rls_setup.sql line 96 grants exactly that, and backend_app has
-- only SELECT and INSERT policies).
--
-- This also corrects observed drift: DEV was found holding
-- SELECT,INSERT,UPDATE,DELETE for backend_app on audit_logs, contrary to 001.
-- FORCE ROW LEVEL SECURITY already blocked the extra two at the policy layer, so
-- revoking them changes no behaviour — it just stops the grants from
-- contradicting the policies. No application code updates or deletes audit rows.
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM backend_app;

COMMIT;

-- ============================================================
-- 4. NOTES / DELIBERATE OMISSIONS
-- ============================================================
-- VIEWS (biometric_metadata, fingerprint_metadata, member_public_profile) are
-- left owned by postgres. A view reads its underlying tables with the VIEW
-- OWNER's privileges, so reassigning them would silently change which rows
-- portal users can see through them. If a future migration must alter a view it
-- will fail loudly as a permission error — which is the correct prompt to make
-- that ownership decision deliberately, rather than having it happen as a side
-- effect of this script.
--
-- audit_logs has FORCE ROW LEVEL SECURITY, so even its owner is subject to RLS
-- policies. DDL against it still works (RLS governs DML/SELECT, not DDL), but a
-- data-migrating statement over audit_logs rows will be filtered. That is the
-- immutability guarantee from 001_rls_setup.sql working as designed — do not
-- "fix" it by adding a permissive policy for powerhouse_migrator.
--
-- NEW TABLES DO NOT GET RLS AUTOMATICALLY. Default privileges cover grants, not
-- row-level security. Any migration adding a table that holds member-scoped data
-- must ENABLE ROW LEVEL SECURITY and add policies explicitly.
