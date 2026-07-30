"""Integration tests for the admin backup-config connection-test endpoint.

Spec: backup-remote-config/spec.md — "Bounded Sanitized Connection Test".
- POST /system/backup-config/test probes via a 1-byte file through the
  remote-push contract, 20s timeout, returns sanitized ``{ok,message}`` with no
  secrets or remote banners.
- Probe failure MUST NOT alter local backups (correction #3 / threat matrix).

Design D7: argv LIST ``["timeout","20","bash","remote_push.sh"]``, env-only
secret, ``shell=False``.
"""

import os
import subprocess
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from core.security import create_access_token, get_password_hash
from models.audit_log import AuditLog
from models.user import User
import services.backup_config as bcfg

CONFIG_URL = "/api/system/backup-config"
TEST_URL = "/api/system/backup-config/test"


@pytest.fixture
def env_path(tmp_path, monkeypatch):
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


def _seed_sftp(auth_client, env_path):
    """Store a complete sftp config so /test has something to probe."""
    auth_client.put(
        CONFIG_URL,
        json={
            "type": "sftp",
            "host": "probe.invalid",
            "username": "probeuser",
            "password": "PROBE-SECRET",
            "path": "/bkp",
            "port": 22,
        },
    )


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_fake(returncode=0, line=""):
    """Build a subprocess.run stub that writes a canned log line to LOG_FILE
    (mirroring remote_push.sh) and returns a controlled CompletedProcess."""

    def _fake(argv, **kwargs):
        env = kwargs.get("env") or {}
        log_file = env.get("LOG_FILE")
        if log_file and line:
            with open(log_file, "a") as fh:
                fh.write(line + "\n")
        return _FakeCompleted(returncode=returncode, stderr=line)

    return _fake


# --- authorization ----------------------------------------------------------


class TestAuthorization:
    def test_non_admin_test_returns_403(self, staff_client):
        assert staff_client.post(TEST_URL).status_code == 403

    def test_unauthenticated_returns_401(self, client):
        assert client.post(TEST_URL).status_code == 401


# --- probe outcome + sanitization ------------------------------------------


class TestProbeOutcome:
    def test_probe_ok_returns_ok_true(self, auth_client, env_path):
        _seed_sftp(auth_client, env_path)
        with patch(
            "services.backup_config.subprocess.run",
            side_effect=_make_fake(
                returncode=0, line="Remote sftp replication completed"
            ),
        ) as mocked:
            resp = auth_client.post(TEST_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

        # argv LIST, shell never True (D7).
        args, kwargs = mocked.call_args
        argv = args[0] if args else kwargs.get("args")
        assert isinstance(argv, list)
        assert argv[:2] == ["timeout", "20"]
        assert "bash" in argv
        assert kwargs.get("shell", False) is False

    def test_probe_fail_returns_ok_false_sanitized(self, auth_client, env_path):
        _seed_sftp(auth_client, env_path)
        banner = (
            "ssh: connect to host probe.invalid port 22 user probeuser "
            "pass PROBE-SECRET banner SSH-2.0-OpenSSH_8.9"
        )
        with patch(
            "services.backup_config.subprocess.run",
            side_effect=_make_fake(returncode=1, line=banner),
        ):
            resp = auth_client.post(TEST_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        msg = body["message"]
        assert len(msg) <= 200
        # No credential/host/user token survives sanitization.
        assert "PROBE-SECRET" not in msg
        assert "probe.invalid" not in msg
        assert "probeuser" not in msg

    def test_probe_timeout_returns_ok_false(self, auth_client, env_path):
        _seed_sftp(auth_client, env_path)
        # `timeout` exits 124 when the deadline is reached.
        with patch(
            "services.backup_config.subprocess.run",
            side_effect=_make_fake(returncode=124, line=""),
        ):
            resp = auth_client.post(TEST_URL)
        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_probe_smb_failure_surfaces_controlled_reason(self, auth_client, env_path):
        """An NT_STATUS_* code in the probe log maps to a controlled reason
        phrase. The raw protocol code must NOT leak into the message (spec:
        sanitized message, no remote banners)."""
        _seed_sftp(auth_client, env_path)
        with patch(
            "services.backup_config.subprocess.run",
            side_effect=_make_fake(
                returncode=1,
                line="session setup failed: NT_STATUS_LOGON_FAILURE (fa.ke)",
            ),
        ):
            resp = auth_client.post(TEST_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "authentication failed" in body["message"]
        assert "NT_STATUS_LOGON_FAILURE" not in body["message"]

    def test_probe_ssh_host_key_failure_surfaces_controlled_reason(
        self, auth_client, env_path
    ):
        """The most common first-time SFTP failure is an untrusted remote host
        key. Scrubbing the host leaves the bare warning unactionable, so a known
        SSH failure phrase maps to a controlled reason — same contract as the
        NT_STATUS_* vocabulary: no banner or raw remote text is surfaced.
        """
        _seed_sftp(auth_client, env_path)
        with patch(
            "services.backup_config.subprocess.run",
            side_effect=_make_fake(
                returncode=1,
                line="Host key verification failed.",
            ),
        ):
            resp = auth_client.post(TEST_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "known_hosts" in body["message"]
        # Nothing from the remote banner or the config leaks.
        assert "probe.invalid" not in body["message"]
        assert len(body["message"]) <= 200

    def test_probe_ssh_auth_failure_surfaces_controlled_reason(
        self, auth_client, env_path
    ):
        _seed_sftp(auth_client, env_path)
        with patch(
            "services.backup_config.subprocess.run",
            side_effect=_make_fake(
                returncode=1,
                line="probeuser@probe.invalid: Permission denied (publickey,password).",
            ),
        ):
            resp = auth_client.post(TEST_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "authentication failed" in body["message"]
        assert "probeuser" not in body["message"]

    def test_secret_travels_via_env_not_argv(self, auth_client, env_path):
        _seed_sftp(auth_client, env_path)
        with patch(
            "services.backup_config.subprocess.run",
            side_effect=_make_fake(returncode=0, line="ok"),
        ) as mocked:
            auth_client.post(TEST_URL)
        args, kwargs = mocked.call_args
        argv = args[0]
        env = kwargs.get("env", {})
        # Decrypted password reaches the child only via SSHPASS env.
        assert env.get("SSHPASS") == "PROBE-SECRET"
        for token in argv:
            assert "PROBE-SECRET" not in token, "secret leaked into probe argv"


# --- incomplete config ------------------------------------------------------


class TestIncompleteConfig:
    def test_test_without_complete_config_returns_400(self, auth_client, env_path):
        # none transport has no target -> nothing to probe.
        auth_client.put(CONFIG_URL, json={"type": "none"})
        resp = auth_client.post(TEST_URL)
        assert resp.status_code == 400


# --- audit -----------------------------------------------------------------


class TestAudit:
    def test_test_audits_safe_details(
        self, auth_client, env_path, admin_user, db_session
    ):
        _seed_sftp(auth_client, env_path)
        with patch(
            "services.backup_config.subprocess.run",
            side_effect=_make_fake(returncode=0, line="ok"),
        ):
            resp = auth_client.post(TEST_URL)
        assert resp.status_code == 200
        import json

        rows = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.action == "backup_config_test",
                AuditLog.user_id == str(admin_user.id),
            )
            .all()
        )
        assert rows, "no backup_config_test audit row written"
        details = json.loads(rows[-1].details or "{}")
        assert details.get("type") == "sftp"
        assert details.get("host") == "probe.invalid"
        assert "ok" in details
        assert "PROBE-SECRET" not in (rows[-1].details or "")


# --- local artifact preservation (correction #3) ---------------------------


class TestProbeLeavesLocalArtifactsUntouched:
    def test_probe_does_not_modify_local_backup_dir(
        self, auth_client, env_path, tmp_path, monkeypatch
    ):
        # Simulate a production BACKUP_DIR holding real artifacts.
        prod_backup = tmp_path / "prod-backups"
        prod_backup.mkdir()
        seeded = []
        for i in range(3):
            f = prod_backup / f"db_backup_2026010{i}_000000.dump"
            f.write_bytes(f"body-{i}".encode())
            seeded.append(f)
        # Point the environment at the production dir (as backup.sh would).
        monkeypatch.setenv("BACKUP_DIR", str(prod_backup))

        _seed_sftp(auth_client, env_path)

        before = {p.name: p.read_bytes() for p in seeded}
        before_count = len(list(prod_backup.iterdir()))

        with patch(
            "services.backup_config.subprocess.run",
            side_effect=_make_fake(returncode=1, line="connection refused"),
        ):
            resp = auth_client.post(TEST_URL)
        assert resp.status_code == 200
        assert resp.json()["ok"] is False

        after = {p.name: p.read_bytes() for p in prod_backup.iterdir()}
        assert before == after, "probe altered seeded local artifacts"
        assert len(after) == before_count, "probe changed local artifact count"
