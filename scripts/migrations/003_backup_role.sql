-- ============================================================
-- FaceGYM: dedicated backup role
--
-- Gives pg_dump a role that can actually read every row.
--
-- WHY THIS EXISTS
-- The runtime role (backend_app) is deliberately least-privileged and is
-- subject to the row-level security that 001_rls_setup.sql builds across 13
-- tables. pg_dump runs every COPY with ``row_security = off``, and PostgreSQL
-- refuses rather than silently filtering: the dump ABORTS at the first
-- RLS-enforced table with
--
--   ERROR: query would be affected by row-level security policy for table "..."
--
-- leaving a truncated archive that still carries the PGDMP magic bytes. On
-- production LXC 114 (2026-08-12) that produced a 56,941-byte file which the
-- admin UI served as a successful export while 1004 members, 2859 memberships
-- and 540 biometric templates were entirely absent from it.
--
-- The tempting fix — grant backend_app BYPASSRLS — would destroy the portal
-- isolation guarantee on the most internet-exposed credential in the system.
-- So the ability to read everything lives in a separate role used only by the
-- backup path, mirroring powerhouse_migrator in 002_migration_role.sql.
--
-- powerhouse_backup is deliberately NOT a superuser and owns nothing: it can
-- read every row and nothing else. If its credential leaks the blast radius is
-- "can read the database", not "owns the cluster" — still serious, which is why
-- the credential file is root-only 0600.
--
-- USAGE
--   1. Replace <SET_BACKUP_PASSWORD> below with a generated secret, e.g.
--        openssl rand -hex 32
--   2. Run as a superuser:
--        sudo -u postgres psql -d membership_db -f 003_backup_role.sql
--   3. Write the URL to /etc/faceapp/backup-db.env (chmod 0600, root-only):
--        BACKUP_DATABASE_URL=postgresql://powerhouse_backup:<pw>@127.0.0.1:5432/membership_db
--   4. Make both consumers see it:
--        * scripts/backup.sh sources the app .env; systemd delivers this file
--          to powerhouse-backup.service via EnvironmentFile.
--        * the admin export endpoint reads BACKUP_DATABASE_URL from its own
--          process environment (api/system.py::_resolve_pg_dump_url), so the
--          BACKEND service unit needs the same EnvironmentFile line — without
--          it, Settings -> Export DB keeps producing truncated archives even
--          though the scheduled backup is healthy.
--   5. Verify — do not assume:
--        sudo -u postgres psql -d membership_db -c '\du powerhouse_backup'
--        set -a; . /etc/faceapp/backup-db.env; set +a
--        PGPASSWORD=$(...) pg_dump ... -F c -f /tmp/verify.dump && \
--          pg_restore -l /tmp/verify.dump | grep -E 'TABLE .* (members|memberships|biometric_templates)$'
--
-- Idempotent: safe to re-run. Re-running does NOT change an existing password.
-- ============================================================

BEGIN;

-- ============================================================
-- 1. CREATE THE BACKUP ROLE
-- ============================================================
-- BYPASSRLS is the whole point of this role. NOSUPERUSER / NOCREATEDB /
-- NOCREATEROLE / NOINHERIT are explicit so the grant cannot quietly widen.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'powerhouse_backup') THEN
        CREATE ROLE powerhouse_backup
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            BYPASSRLS
            PASSWORD '<SET_BACKUP_PASSWORD>';
    ELSE
        -- Re-run on a host where the role predates this script: make sure the
        -- attribute that matters is actually set. A powerhouse_backup created
        -- by hand without BYPASSRLS produces exactly the truncated dump this
        -- script exists to prevent.
        ALTER ROLE powerhouse_backup BYPASSRLS;
    END IF;
END
$$;

-- ============================================================
-- 2. READ EVERYTHING, WRITE NOTHING
-- ============================================================
GRANT CONNECT ON DATABASE membership_db TO powerhouse_backup;
GRANT USAGE ON SCHEMA public TO powerhouse_backup;

-- pg_read_all_data (PostgreSQL 14+) covers SELECT on every table, view and
-- sequence, including ones added by FUTURE migrations. Granting per-table
-- instead would silently miss any new table and truncate a later dump — the
-- same class of failure, arriving months later.
GRANT pg_read_all_data TO powerhouse_backup;

-- No INSERT/UPDATE/DELETE, no ownership, no DDL: this role exists to read.

COMMIT;

-- ============================================================
-- 3. NOTES / DELIBERATE OMISSIONS
-- ============================================================
-- BYPASSRLS applies to the role's own queries. It does NOT make the role a
-- table owner, so it cannot DROP, TRUNCATE, or ALTER anything — including
-- ALTER TABLE ... DISABLE ROW LEVEL SECURITY. That separation is what makes
-- handing out "read everything" acceptable here.
--
-- audit_logs sets FORCE ROW LEVEL SECURITY, which subjects even the table
-- OWNER to its policies — but BYPASSRLS still exempts this role, which is what
-- lets the audit trail be backed up at all. Do not "simplify" by dropping
-- BYPASSRLS in favour of ownership; ownership would not be enough here and
-- would grant DDL besides.
--
-- The password above is a placeholder ON PURPOSE. Never commit a real one:
-- generate it at provisioning time and keep it only in /etc/faceapp/backup-db.env
-- (0600, root-only), the same handling as migrate-db.env in 002.
