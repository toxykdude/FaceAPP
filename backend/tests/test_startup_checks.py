"""
Startup secret validation (S3).

assert_production_secrets() must be a no-op outside production, enforce strong
secrets in production, raise on weak JWT_SECRET / ADMIN_PASSWORD, and only WARN
(not raise) on a weak ENCRYPTION_KEY.
"""

import base64
import logging

import pytest

from core import startup_checks
from core.config import settings

STRONG = {
    "JWT_SECRET": "x" * 32,
    "INTERNAL_API_SECRET": "i" * 32,
    "WOMPI_INTEGRITY_SECRET": "w" * 32,
    "ADMIN_PASSWORD": "a" * 10,
    "CV_API_KEY": "k" * 24,
    "ENCRYPTION_KEY": base64.b64encode(b"e" * 32).decode(),
}


@pytest.fixture
def strong_secrets(monkeypatch):
    for name, value in STRONG.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.delenv("REQUIRE_PROD_SECRETS", raising=False)


def test_noop_when_not_production(strong_secrets, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    startup_checks.assert_production_secrets()


def test_passes_in_production_with_strong_secrets(strong_secrets, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    startup_checks.assert_production_secrets()


def test_raises_on_placeholder_jwt_secret(strong_secrets, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "JWT_SECRET", "dev-jwt-secret-change-in-production")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        startup_checks.assert_production_secrets()


def test_raises_on_admin123_password(strong_secrets, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "admin123")
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        startup_checks.assert_production_secrets()


def test_short_encryption_key_only_warns(strong_secrets, monkeypatch, caplog):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "short")
    with caplog.at_level(logging.WARNING, logger="core.startup_checks"):
        startup_checks.assert_production_secrets()  # must NOT raise
    assert any("ENCRYPTION_KEY" in rec.message for rec in caplog.records)


def test_require_prod_secrets_env_forces_enforcement(strong_secrets, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setenv("REQUIRE_PROD_SECRETS", "1")
    monkeypatch.setattr(settings, "JWT_SECRET", "weak")
    with pytest.raises(RuntimeError):
        startup_checks.assert_production_secrets()
