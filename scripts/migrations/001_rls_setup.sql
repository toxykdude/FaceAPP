-- ============================================================
-- FaceGYM RLS Migration v2
-- Row-Level Security setup for membership_db
--
-- Creates role hierarchy, enables RLS, creates policies,
-- restricted views, and hardens audit_logs immutability.
--
-- IMPORTANT: Replace <PLACEHOLDER> passwords before running.
-- ============================================================

BEGIN;

-- ============================================================
-- 1. CREATE NEW ROLES
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'backend_app') THEN
        CREATE ROLE backend_app NOINHERIT LOGIN PASSWORD '<SET_BACKEND_APP_PASSWORD>';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'backend_readonly') THEN
        CREATE ROLE backend_readonly NOINHERIT LOGIN PASSWORD '<SET_READONLY_PASSWORD>';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'member_portal') THEN
        CREATE ROLE member_portal NOINHERIT LOGIN PASSWORD '<SET_PORTAL_PASSWORD>';
    END IF;
END
$$;

-- ============================================================
-- 2. GRANT CONNECT + SCHEMA USAGE
-- ============================================================
GRANT CONNECT ON DATABASE membership_db TO backend_app;
GRANT CONNECT ON DATABASE membership_db TO backend_readonly;
GRANT CONNECT ON DATABASE membership_db TO member_portal;

GRANT USAGE ON SCHEMA public TO backend_app;
GRANT USAGE ON SCHEMA public TO backend_readonly;
GRANT USAGE ON SCHEMA public TO member_portal;

-- ============================================================
-- 3. ENABLE RLS ON ALL SENSITIVE TABLES
-- ============================================================
-- Note: Table owner ('membership') BYPASSES RLS by default,
-- so the current app continues working without policy changes.
-- Use FORCE ROW LEVEL SECURITY to enforce on owner (see audit_logs).

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE members ENABLE ROW LEVEL SECURITY;
ALTER TABLE biometric_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE fingerprint_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE access_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE cameras ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE enrollment_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE membership_plans ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- 4. POLICIES FOR 'membership' (CURRENT APP - FULL ACCESS)
-- Maintains backward compatibility while roles are migrated.
-- ============================================================
CREATE POLICY membership_full_access ON users FOR ALL TO membership USING (true) WITH CHECK (true);
CREATE POLICY membership_full_access ON members FOR ALL TO membership USING (true) WITH CHECK (true);
CREATE POLICY membership_full_access ON biometric_templates FOR ALL TO membership USING (true) WITH CHECK (true);
CREATE POLICY membership_full_access ON fingerprint_templates FOR ALL TO membership USING (true) WITH CHECK (true);
CREATE POLICY membership_full_access ON password_reset_tokens FOR ALL TO membership USING (true) WITH CHECK (true);
CREATE POLICY membership_full_access ON sales_transactions FOR ALL TO membership USING (true) WITH CHECK (true);
CREATE POLICY membership_full_access ON memberships FOR ALL TO membership USING (true) WITH CHECK (true);
CREATE POLICY membership_full_access ON access_events FOR ALL TO membership USING (true) WITH CHECK (true);
-- audit_logs: SELECT + INSERT only (NO UPDATE/DELETE)
CREATE POLICY membership_audit_read ON audit_logs FOR SELECT TO membership USING (true);
CREATE POLICY membership_audit_insert ON audit_logs FOR INSERT TO membership WITH CHECK (true);
CREATE POLICY membership_full_access ON cameras FOR ALL TO membership USING (true) WITH CHECK (true);
CREATE POLICY membership_full_access ON settings FOR ALL TO membership USING (true) WITH CHECK (true);
CREATE POLICY membership_full_access ON enrollment_requests FOR ALL TO membership USING (true) WITH CHECK (true);
CREATE POLICY membership_full_access ON membership_plans FOR ALL TO membership USING (true) WITH CHECK (true);

-- ============================================================
-- 5. GRANTS + POLICIES FOR backend_app (FUTURE PRIMARY ROLE)
-- Full CRUD on operational tables, INSERT+SELECT on audit_logs.
-- ============================================================
GRANT SELECT, INSERT, UPDATE, DELETE ON members TO backend_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON memberships TO backend_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON membership_plans TO backend_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON access_events TO backend_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON sales_transactions TO backend_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON enrollment_requests TO backend_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON cameras TO backend_app;
GRANT SELECT, INSERT, UPDATE ON settings TO backend_app;
GRANT SELECT, INSERT, UPDATE ON users TO backend_app;
GRANT SELECT, INSERT ON audit_logs TO backend_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_tokens TO backend_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON biometric_templates TO backend_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON fingerprint_templates TO backend_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO backend_app;

CREATE POLICY backend_app_users ON users FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_members ON members FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_memberships ON memberships FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_plans ON membership_plans FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_events ON access_events FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_sales ON sales_transactions FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_enrollment ON enrollment_requests FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_cameras ON cameras FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_settings ON settings FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_tokens ON password_reset_tokens FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_bio ON biometric_templates FOR ALL TO backend_app USING (true) WITH CHECK (true);
CREATE POLICY backend_app_fp ON fingerprint_templates FOR ALL TO backend_app USING (true) WITH CHECK (true);
-- Audit: INSERT + SELECT only (immutable even for backend)
CREATE POLICY backend_app_audit_read ON audit_logs FOR SELECT TO backend_app USING (true);
CREATE POLICY backend_app_audit_insert ON audit_logs FOR INSERT TO backend_app WITH CHECK (true);

-- ============================================================
-- 6. GRANTS + POLICIES FOR backend_readonly (REPORTING)
-- SELECT only on operational tables. NO access to secrets.
-- ============================================================
GRANT SELECT ON members TO backend_readonly;
GRANT SELECT ON memberships TO backend_readonly;
GRANT SELECT ON membership_plans TO backend_readonly;
GRANT SELECT ON access_events TO backend_readonly;
GRANT SELECT ON sales_transactions TO backend_readonly;
GRANT SELECT ON cameras TO backend_readonly;
GRANT SELECT ON audit_logs TO backend_readonly;
GRANT SELECT ON enrollment_requests TO backend_readonly;

CREATE POLICY readonly_members ON members FOR SELECT TO backend_readonly USING (true);
CREATE POLICY readonly_memberships ON memberships FOR SELECT TO backend_readonly USING (true);
CREATE POLICY readonly_plans ON membership_plans FOR SELECT TO backend_readonly USING (true);
CREATE POLICY readonly_events ON access_events FOR SELECT TO backend_readonly USING (true);
CREATE POLICY readonly_sales ON sales_transactions FOR SELECT TO backend_readonly USING (true);
CREATE POLICY readonly_cameras ON cameras FOR SELECT TO backend_readonly USING (true);
CREATE POLICY readonly_audit ON audit_logs FOR SELECT TO backend_readonly USING (true);
CREATE POLICY readonly_enrollment ON enrollment_requests FOR SELECT TO backend_readonly USING (true);

-- NO access to: users, password_reset_tokens, biometric_templates, fingerprint_templates

-- ============================================================
-- 7. GRANTS + POLICIES FOR member_portal (SELF-SERVICE)
-- Members can only see their own data.
-- Requires: SET app.member_id = '<uuid>' per request session.
-- ============================================================
GRANT SELECT ON members TO member_portal;
GRANT SELECT ON memberships TO member_portal;
GRANT SELECT ON sales_transactions TO member_portal;
GRANT SELECT ON membership_plans TO member_portal;
GRANT SELECT ON access_events TO member_portal;

CREATE POLICY portal_own_member ON members
    FOR SELECT TO member_portal
    USING (id::text = current_setting('app.member_id', true));

CREATE POLICY portal_own_memberships ON memberships
    FOR SELECT TO member_portal
    USING (member_id::text = current_setting('app.member_id', true));

CREATE POLICY portal_own_sales ON sales_transactions
    FOR SELECT TO member_portal
    USING (member_id::text = current_setting('app.member_id', true));

CREATE POLICY portal_plans ON membership_plans
    FOR SELECT TO member_portal
    USING (true);

CREATE POLICY portal_own_events ON access_events
    FOR SELECT TO member_portal
    USING (member_id::text = current_setting('app.member_id', true));

-- NO access to: users, biometric_templates, fingerprint_templates,
--               password_reset_tokens, cameras, settings, audit_logs

-- ============================================================
-- 8. RESTRICTED VIEWS (no template_data, no sensitive fields)
-- ============================================================

-- Biometric metadata without raw template_data
CREATE OR REPLACE VIEW biometric_metadata AS
    SELECT id, member_id, encryption_key_id, quality_score, enrolled_at, updated_at
    FROM biometric_templates;
GRANT SELECT ON biometric_metadata TO backend_app;
GRANT SELECT ON biometric_metadata TO backend_readonly;

-- Fingerprint metadata without raw template_data
CREATE OR REPLACE VIEW fingerprint_metadata AS
    SELECT id, member_id, encryption_key_id, quality_score, enrolled_at, updated_at
    FROM fingerprint_templates;
GRANT SELECT ON fingerprint_metadata TO backend_app;
GRANT SELECT ON fingerprint_metadata TO backend_readonly;

-- Member public profile without email, phone, id_number
CREATE OR REPLACE VIEW member_public_profile AS
    SELECT id, first_name, last_name, status, facial_data_enrolled,
           consent_given_at, created_at, updated_at, last_seen
    FROM members;
GRANT SELECT ON member_public_profile TO backend_readonly;

-- ============================================================
-- 9. REVOKE EXCESSIVE PRIVILEGES FROM 'membership'
-- ============================================================
REVOKE TRUNCATE ON ALL TABLES IN SCHEMA public FROM membership;
REVOKE UPDATE ON audit_logs FROM membership;
REVOKE DELETE ON audit_logs FROM membership;

-- ============================================================
-- 10. FORCE RLS ON audit_logs (even owner can't bypass)
-- Ensures audit trail immutability at the database level.
-- ============================================================
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

COMMIT;
