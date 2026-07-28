"""Integration tests for the admin backup-config API.

Spec: backup-remote-config/spec.md
- "Protected Masked Configuration": admin GET returns transport config plus
  ``has_password``; MUST NOT return plaintext or ciphertext; ``backup_remote``
  MUST NOT be exposed by ``/settings/public``.
- "Validated Write-Only Persistence": AES-256-GCM password; empty/keep-sentinel
  preserves current password; invalid transport -> 400 without changing
  persisted or materialized config; audited without secrets.
- "Secure Environment Materialization": atomic replace of the managed env file,
  mode 0600, root:root where possible, transport-change stale-key removal, no
  logging of file contents.

Design (design.md): D1 single JSON ``backup_remote`` row, D3 ``/system`` router,
D4 keep-sentinel = omit or "", D6 full rewrite each save.
"""

import os
import uuid

import pytest

from core.encryption import decrypt_string, encrypt_string
from core.security import create_access_token, get_password_hash
from models.audit_log import AuditLog
from models.setting import Setting
from models.user import User
import services.backup_config as bcfg  # noqa: E402  (module under test)

CONFIG_URL = "/api/system/backup-config"
PUBLIC_URL = "/api/settings/public"


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def env_path(tmp_path, monkeypatch):
    """Redirect the managed env file to a tmp path so tests never touch /etc."""
    path = tmp_path / "backup-remote.env"
    monkeypatch.setattr(bcfg, "BACKUP_REMOTE_ENV_PATH", str(path))
    return path


@pytest.fixture
def staff_user(db_session):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"staff-{suffix}",
        email=f"staff-{suffix}@example.com",
        password_hash=get_password_hash("secret123"),
        role="staff",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def staff_client(client, staff_user):
    token = create_access_token(data={"sub": str(staff_user.id)})
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _stored(db_session) -> dict:
    row = db_session.query(Setting).filter(Setting.key == "backup_remote").first()
    return row.value if row else None


# --- masking ---------------------------------------------------------------


class TestMaskedRead:
    def test_get_default_config_is_none_and_masked(self, auth_client, env_path):
        resp = auth_client.get(CONFIG_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "none"
        assert body["has_password"] is False
        # No ciphertext/plaintext password field is ever exposed.
        assert "password_enc" not in body
        assert "password" not in body

    def test_get_after_save_reports_has_password_without_ciphertext(
        self, auth_client, env_path
    ):
        resp = auth_client.put(
            CONFIG_URL,
            json={
                "type": "sftp",
                "host": " backups.invalid ",
                "username": "u",
                "password": "supersecret",
                "path": "/srv/bkp",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_password"] is True
        assert body["type"] == "sftp"
        assert body["host"] == "backups.invalid"  # trimmed
        assert body["username"] == "u"
        assert "password_enc" not in body
        assert "password" not in body

    def test_backup_remote_absent_from_public_settings(self, auth_client, env_path, client):
        # Seed the protected row directly.
        auth_client.put(
            CONFIG_URL,
            json={"type": "sftp", "host": "h", "username": "u", "password": "p"},
        )
        resp = client.get(PUBLIC_URL)
        assert resp.status_code == 200
        assert "backup_remote" not in resp.json()


# --- write-only password semantics -----------------------------------------


class TestWriteOnlyPassword:
    def test_replace_password_encrypts_with_aes_gcm(self, auth_client, env_path, db_session):
        resp = auth_client.put(
            CONFIG_URL,
            json={"type": "sftp", "host": "h", "username": "u", "password": "newsecret", "path": "/x"},
        )
        assert resp.status_code == 200
        stored = _stored(db_session)
        # Stored value is ciphertext, never plaintext.
        assert stored["password_enc"] != "newsecret"
        assert decrypt_string(stored["password_enc"]) == "newsecret"

    def test_omitted_password_keeps_existing(self, auth_client, env_path, db_session):
        auth_client.put(
            CONFIG_URL,
            json={"type": "sftp", "host": "h", "username": "u", "password": "keepme", "path": "/x"},
        )
        before = _stored(db_session)["password_enc"]
        # Omit password entirely -> sentinel "keep".
        auth_client.put(
            CONFIG_URL,
            json={"type": "sftp", "host": "h2", "username": "u", "path": "/x"},
        )
        after = _stored(db_session)
        assert after["password_enc"] == before
        assert decrypt_string(after["password_enc"]) == "keepme"
        assert after["host"] == "h2"

    def test_empty_password_keeps_existing(self, auth_client, env_path, db_session):
        auth_client.put(
            CONFIG_URL,
            json={"type": "sftp", "host": "h", "username": "u", "password": "keepme", "path": "/x"},
        )
        before = _stored(db_session)["password_enc"]
        auth_client.put(
            CONFIG_URL,
            json={"type": "sftp", "host": "h", "username": "u", "password": "", "path": "/x"},
        )
        after = _stored(db_session)
        assert after["password_enc"] == before
        assert decrypt_string(after["password_enc"]) == "keepme"


# --- per-transport validation ----------------------------------------------


class TestValidation:
    @pytest.mark.parametrize(
        "payload",
        [
            {"type": "rsync"},  # missing host/path
            {"type": "rsync", "host": "h"},  # missing path
            {"type": "sftp", "host": "h"},  # missing username/password
            {"type": "sftp", "host": "h", "username": "u", "path": "/x"},  # no password
            {"type": "ftp", "host": "h", "username": "u"},  # no password
            {"type": "smb", "share": "s"},  # missing user/password
            {"type": "nfs"},  # missing path
            {"type": "bogus"},  # unknown transport
        ],
    )
    def test_invalid_config_returns_400(self, auth_client, env_path, payload):
        resp = auth_client.put(CONFIG_URL, json=payload)
        assert resp.status_code == 400

    def test_invalid_put_does_not_persist_or_materialize(
        self, auth_client, env_path, db_session
    ):
        # Establish a valid baseline on a clean slate (none transport).
        auth_client.put(CONFIG_URL, json={"type": "none"})
        valid_stored = _stored(db_session)
        valid_file = env_path.read_text()
        # Attempt an invalid update: rsync requires host+path, which the
        # current `none` config does not carry (merge leaves them empty).
        resp = auth_client.put(CONFIG_URL, json={"type": "rsync"})
        assert resp.status_code == 400
        # Persisted config unchanged.
        assert _stored(db_session) == valid_stored
        # Materialized env file unchanged.
        assert env_path.read_text() == valid_file

    def test_none_transport_is_valid_without_fields(self, auth_client, env_path):
        resp = auth_client.put(CONFIG_URL, json={"type": "none"})
        assert resp.status_code == 200
        assert resp.json()["type"] == "none"


# --- authorization ----------------------------------------------------------


class TestAuthorization:
    def test_non_admin_get_returns_403(self, staff_client):
        assert staff_client.get(CONFIG_URL).status_code == 403

    def test_non_admin_put_returns_403(self, staff_client):
        resp = staff_client.put(CONFIG_URL, json={"type": "none"})
        assert resp.status_code == 403

    def test_non_admin_test_returns_403(self, staff_client):
        assert staff_client.post(f"{CONFIG_URL}/test").status_code == 403

    def test_unauthenticated_returns_401(self, client):
        assert client.get(CONFIG_URL).status_code == 401


# --- audit -----------------------------------------------------------------


class TestAudit:
    def test_put_audits_safe_details(self, auth_client, env_path, admin_user, db_session):
        resp = auth_client.put(
            CONFIG_URL,
            json={"type": "sftp", "host": "audit.example", "username": "u", "password": "supersecret", "path": "/x"},
        )
        assert resp.status_code == 200
        rows = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.action == "backup_config_update",
                AuditLog.user_id == str(admin_user.id),
            )
            .all()
        )
        assert rows, "no backup_config_update audit row written"
        import json

        details = json.loads(rows[-1].details or "{}")
        assert details.get("type") == "sftp"
        assert details.get("host") == "audit.example"
        # The password must never appear in the audit detail payload.
        assert "supersecret" not in (rows[-1].details or "")


# --- secure env materialization --------------------------------------------


class TestEnvMaterialization:
    def test_env_file_mode_0600(self, auth_client, env_path):
        auth_client.put(
            CONFIG_URL,
            json={"type": "sftp", "host": "h", "username": "u", "password": "p", "path": "/x"},
        )
        assert env_path.exists()
        mode = os.stat(env_path).st_mode & 0o777
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    def test_env_file_contains_transport_keys_only(self, auth_client, env_path):
        auth_client.put(
            CONFIG_URL,
            json={"type": "sftp", "host": "srv", "username": "u", "password": "p", "path": "/bkp", "port": 2222},
        )
        text = env_path.read_text()
        assert "BACKUP_REMOTE_TYPE='sftp'" in text
        assert "SFTP_HOST='srv'" in text
        assert "SFTP_USER='u'" in text
        assert "SFTP_PATH='/bkp'" in text
        assert "SFTP_PORT='2222'" in text
        assert "SSHPASS='p'" in text

    def test_transport_change_removes_stale_keys(self, auth_client, env_path):
        auth_client.put(
            CONFIG_URL,
            json={"type": "smb", "share": "//h/share", "username": "u", "password": "p", "path": "sub"},
        )
        smb_text = env_path.read_text()
        assert "SMB_SHARE" in smb_text
        assert "SSHPASS" not in smb_text
        # Switch transport.
        auth_client.put(
            CONFIG_URL,
            json={"type": "rsync", "host": "h", "path": "/x"},
        )
        rsync_text = env_path.read_text()
        assert "RSYNC_HOST" in rsync_text
        # Stale SMB keys fully removed (D6 full rewrite).
        assert "SMB_SHARE" not in rsync_text
        assert "SMB_PASS" not in rsync_text

    def test_materialize_leaves_no_temp_fragment(self, auth_client, env_path, tmp_path):
        parent = env_path.parent
        auth_client.put(
            CONFIG_URL,
            json={"type": "nfs", "path": "/mnt/nfs"},
        )
        # Only the final env file remains; no partial temp file leaked.
        siblings = [p.name for p in parent.iterdir()]
        assert "backup-remote.env" in siblings
        assert not any(s.startswith(".backup-remote") for s in siblings), siblings
