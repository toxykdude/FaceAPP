"""
Tests for SMTP TLS certificate validation (WS-10a, CWE-295).

SMTP_SSL and STARTTLS previously used NO SSLContext, so the SMTP server
certificate was never authenticated -- exposing SMTP credentials to MITM.
The fix passes a verified ssl.SSLContext (hostname + chain) by default, with
insecure mode opt-in only via the SMTP_INSECURE env var.
"""

import smtplib
import ssl
from unittest.mock import MagicMock


def _is_verified(ctx) -> bool:
    return (
        isinstance(ctx, ssl.SSLContext)
        and ctx.check_hostname
        and ctx.verify_mode == ssl.CERT_REQUIRED
    )


def _is_unverified(ctx) -> bool:
    return (
        isinstance(ctx, ssl.SSLContext)
        and not ctx.check_hostname
        and ctx.verify_mode == ssl.CERT_NONE
    )


def _enabled_service():
    from core.email import EmailService

    svc = EmailService()
    svc.smtp_host = "smtp.example.com"
    svc.smtp_user = "user"
    svc.smtp_password = "pw"
    svc.smtp_from = "from@example.com"
    svc.smtp_port = 465
    svc.enabled = True
    return svc


class TestSmtpTlsValidation:
    def test_smtp_ssl_passes_verified_context_by_default(self, monkeypatch):
        monkeypatch.delenv("SMTP_INSECURE", raising=False)
        captured = {}

        def fake_ssl(host, port, context=None, **kw):
            captured["context"] = context
            return MagicMock()

        monkeypatch.setattr(smtplib, "SMTP_SSL", fake_ssl)
        monkeypatch.setattr("core.config.settings.SMTP_USE_SSL", True, raising=False)

        svc = _enabled_service()
        assert svc._send_email("to@example.com", "s", "b") is True
        assert _is_verified(captured["context"]), captured["context"]

    def test_starttls_passes_verified_context_by_default(self, monkeypatch):
        monkeypatch.delenv("SMTP_INSECURE", raising=False)
        server = MagicMock()
        monkeypatch.setattr(smtplib, "SMTP", lambda *a, **kw: server)
        monkeypatch.setattr("core.config.settings.SMTP_USE_SSL", False, raising=False)

        svc = _enabled_service()
        assert svc._send_email("to@example.com", "s", "b") is True
        ctx = server.starttls.call_args.kwargs.get("context")
        assert _is_verified(ctx), ctx

    def test_insecure_env_disables_verification(self, monkeypatch):
        monkeypatch.setenv("SMTP_INSECURE", "1")
        captured = {}

        def fake_ssl(host, port, context=None, **kw):
            captured["context"] = context
            return MagicMock()

        monkeypatch.setattr(smtplib, "SMTP_SSL", fake_ssl)
        monkeypatch.setattr("core.config.settings.SMTP_USE_SSL", True, raising=False)

        svc = _enabled_service()
        assert svc._send_email("to@example.com", "s", "b") is True
        assert _is_unverified(captured["context"]), captured["context"]
