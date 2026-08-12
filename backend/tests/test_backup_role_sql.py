"""Guards on the backup-role provisioning script.

``scripts/migrations/003_backup_role.sql`` has no other automated coverage, and
both defects it has carried were silent at provisioning time: the script ran
without error, reported success, and left a role that could not read a single
row. Each was found only by dumping with the role afterwards.

These are text assertions, not database tests — there is no throwaway cluster
in this suite to provision a role against. They exist to stop a future edit
from reintroducing either failure, and each names the symptom so the next
reader knows what the line is load-bearing for.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_ROLE_SQL = REPO_ROOT / "scripts" / "migrations" / "003_backup_role.sql"
MIGRATION_ROLE_SQL = REPO_ROOT / "scripts" / "migrations" / "002_migration_role.sql"


def _strip_comments(text: str) -> str:
    """Drop ``--`` comments so assertions test statements, not prose.

    This file documents its own failure modes at length, so a naive substring
    check matches the explanation rather than the code — e.g. the comment
    warning that ``WITH INHERIT`` is PostgreSQL 16+ would itself trip a check
    forbidding ``WITH INHERIT``.
    """
    return "\n".join(re.sub(r"--.*$", "", line) for line in text.splitlines())


@pytest.fixture(scope="module")
def sql() -> str:
    assert BACKUP_ROLE_SQL.exists(), f"missing {BACKUP_ROLE_SQL}"
    return _strip_comments(BACKUP_ROLE_SQL.read_text())


@pytest.fixture(scope="module")
def sql_with_comments() -> str:
    return BACKUP_ROLE_SQL.read_text()


class TestRoleInheritsItsReadPrivilege:
    """Provisioned with NOINHERIT on production 2026-08-12, the role failed with
    ``permission denied for table access_events`` and produced a ZERO-byte dump.

    The role's read privilege comes from MEMBERSHIP in pg_read_all_data, and a
    NOINHERIT member holds nothing until it runs ``SET ROLE`` — which pg_dump
    never does.
    """

    def test_role_is_created_with_inherit(self, sql):
        create = re.search(r"CREATE ROLE powerhouse_backup(.*?);", sql, re.S)
        assert create, "CREATE ROLE powerhouse_backup block not found"
        body = create.group(1)
        assert re.search(r"\bINHERIT\b", body), (
            "powerhouse_backup must be created with INHERIT — its read privilege "
            "comes from membership in pg_read_all_data, which a NOINHERIT member "
            "cannot use without SET ROLE"
        )
        assert not re.search(r"\bNOINHERIT\b", body), (
            "NOINHERIT on powerhouse_backup produces a zero-byte dump "
            "(permission denied for table access_events)"
        )

    def test_repair_path_also_restores_inherit(self, sql):
        """Re-running must fix a role created by an earlier, broken revision."""
        alter = re.search(r"ALTER ROLE powerhouse_backup ([^;]*);", sql)
        assert alter, "no ALTER ROLE repair path for an existing role"
        assert "INHERIT" in alter.group(1), (
            "the repair path must restore INHERIT, not only BYPASSRLS — hosts "
            "provisioned by the first revision have rolinherit = false"
        )
        assert "BYPASSRLS" in alter.group(1)


class TestMembershipIsRegrantedNotJustAltered:
    """PostgreSQL 16 records a membership's inherit option AT GRANT TIME from the
    member's rolinherit; ``ALTER ROLE ... INHERIT`` afterwards does NOT update it
    (pg_auth_members.inherit_option).

    Production reached rolinherit = t with inherit_option = f and STILL failed
    with ``permission denied for table access_events``. Only re-granting fixed
    it, so the REVOKE must survive future edits.
    """

    def test_read_grant_is_revoked_before_being_granted(self, sql):
        revoke = sql.find("REVOKE pg_read_all_data FROM powerhouse_backup")
        grant = sql.find("GRANT pg_read_all_data TO powerhouse_backup")
        assert revoke != -1, (
            "REVOKE before GRANT is required: a membership first granted while "
            "the role was NOINHERIT keeps inherit_option = false forever"
        )
        assert grant != -1, "the role must be granted pg_read_all_data"
        assert revoke < grant, "REVOKE must precede GRANT to re-record the option"

    def test_alter_role_precedes_the_grant(self, sql):
        """INHERIT must be in force before the grant, or the re-grant re-records
        the wrong option again."""
        alter = sql.find("ALTER ROLE powerhouse_backup")
        grant = sql.find("GRANT pg_read_all_data TO powerhouse_backup")
        assert alter < grant, (
            "the INHERIT repair must run before the re-grant; otherwise the new "
            "membership inherits the still-false setting"
        )

    def test_no_pg16_only_syntax(self, sql):
        """`WITH INHERIT TRUE` would break PostgreSQL 14/15, which the header
        claims support for (pg_read_all_data is 14+)."""
        assert (
            "WITH INHERIT" not in sql.upper()
        ), "WITH INHERIT is PostgreSQL 16+ only; use REVOKE + GRANT instead"


class TestPrivilegeBoundary:
    """The role reads everything, so it must be able to do nothing else."""

    def test_role_is_not_a_superuser_and_cannot_create(self, sql):
        create = re.search(r"CREATE ROLE powerhouse_backup(.*?);", sql, re.S).group(1)
        for flag in ("NOSUPERUSER", "NOCREATEDB", "NOCREATEROLE"):
            assert flag in create, f"{flag} must stay explicit on powerhouse_backup"

    def test_no_write_or_ownership_grants(self, sql):
        """Only read privileges may be granted, and no table may be reassigned.

        Verified against production 2026-08-12: DELETE/INSERT/TRUNCATE denied,
        DROP and ALTER TABLE ... DISABLE ROW LEVEL SECURITY blocked by
        ownership. This keeps it that way.
        """
        granted = " ".join(re.findall(r"\bGRANT\b(.*?)\bTO\b", sql.upper(), re.S))
        for forbidden in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            assert forbidden not in granted, (
                f"{forbidden} must never be granted to the backup role — it "
                "exists to read"
            )
        assert "OWNER TO" not in sql.upper(), (
            "the backup role must own nothing; ownership would confer DDL and "
            "the ability to disable row-level security"
        )

    def test_password_placeholder_is_not_a_real_secret(self, sql_with_comments):
        assert "<SET_BACKUP_PASSWORD>" in sql_with_comments, (
            "the committed script must carry the placeholder, never a real "
            "password (SECURITY.md sec 2)"
        )
        assert not re.search(
            r"PASSWORD\s+'(?!<SET_BACKUP_PASSWORD>)[^']+'",
            _strip_comments(sql_with_comments),
            re.I,
        ), "a literal password was committed in the provisioning script"


class TestContrastWithTheMigrationRole:
    """002 uses NOINHERIT correctly and 003 must not — the difference is why the
    bug was easy to introduce by copying."""

    def test_migration_role_still_uses_noinherit(self):
        """Its authority is table OWNERSHIP, a direct attribute, not a
        membership — so NOINHERIT there is correct and must not be 'fixed' to
        match 003."""
        assert "NOINHERIT" in MIGRATION_ROLE_SQL.read_text(), (
            "002_migration_role.sql should keep NOINHERIT; if this failed "
            "because someone aligned it with 003, revert that — the two roles "
            "derive their privileges differently"
        )
