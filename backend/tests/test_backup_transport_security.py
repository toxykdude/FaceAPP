"""
Security tests for backup-transport input validation (WS-10b).

The remote-push transports (sftp/ftp/rsync/smb) interpolate the saved
username/path/host into command lines and (for sftp) a batch file. validate()
now rejects control characters in any field and restricts usernames to a safe
charset, so OpenSSH option injection (CWE-88) and sftp-batch/command injection
(CWE-78) are blocked at config-save time -- before anything reaches a shell.
"""

import pytest

from services.backup_config import BackupConfigError, validate


def _cfg(**over):
    base = {
        "type": "sftp",
        "host": "nas.local",
        "username": "backup-user",
        "password_enc": "enc",
        "path": "backups",
    }
    base.update(over)
    return base


class TestUsernameInjection:
    def test_openssh_option_in_username_rejected(self):
        # "-oProxyCommand=..." would be parsed as an sftp option (CWE-88).
        with pytest.raises(BackupConfigError, match="username"):
            validate(_cfg(username="-oProxyCommand=evil"))

    def test_username_with_spaces_rejected(self):
        with pytest.raises(BackupConfigError, match="username"):
            validate(_cfg(username="bad user"))

    def test_valid_username_accepted(self):
        cfg = validate(_cfg(username="backup_user.1-2"))
        assert cfg["username"] == "backup_user.1-2"

    def test_username_guard_applies_to_all_shell_transports(self):
        for t in ("sftp", "ftp", "rsync", "smb"):
            payload = {"type": t, "host": "h", "path": "p", "username": "-x=bad"}
            if t == "smb":
                payload["share"] = "srv/share"
            payload["password_enc"] = "enc"
            with pytest.raises(BackupConfigError, match="username"):
                validate(payload)


class TestControlCharInjection:
    def test_newline_in_path_rejected(self):
        # A newline in the sftp path breaks the batch file (CWE-78).
        with pytest.raises(BackupConfigError, match="control characters"):
            validate(_cfg(type="rsync", path="data\nput /etc/passwd"))

    def test_carriage_return_in_path_rejected(self):
        with pytest.raises(BackupConfigError, match="control characters"):
            validate(_cfg(type="rsync", path="data\rmalicious"))

    def test_control_char_in_host_rejected(self):
        with pytest.raises(BackupConfigError, match="control characters"):
            validate(_cfg(host="evi\nlhost"))

    def test_clean_path_accepted(self):
        cfg = validate(_cfg(type="rsync", path="/data/backups/subdir"))
        assert cfg["path"] == "/data/backups/subdir"


class TestFtpCleartextWarning:
    def test_ftp_logs_cleartext_warning(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="services.backup_config"):
            validate(
                {
                    "type": "ftp",
                    "host": "ftp.example.com",
                    "username": "user",
                    "password_enc": "enc",
                }
            )
        assert any("cleartext" in r.message for r in caplog.records), caplog.records
