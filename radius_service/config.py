"""
radius_service configuration.

All settings come from the environment (12-factor, mirroring the backend's
Settings style). In production they are provided by
/etc/faceapp/radius.env (0600, root-only) via the facegym-radius systemd
unit — see docs/pfsense-captive-portal.md.
"""

import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


class Settings:
    """Environment-driven settings for the RADIUS ⇄ backend gateway."""

    def __init__(self) -> None:
        # Bind
        self.LISTEN_HOST: str = os.getenv("RADIUS_LISTEN_HOST", "0.0.0.0")
        self.AUTH_PORT: int = _int_env("RADIUS_AUTH_PORT", 1812)
        self.ACCT_PORT: int = _int_env("RADIUS_ACCT_PORT", 1813)

        # Shared secret with pfSense (RADIUS protocol secret).
        self.RADIUS_SHARED_SECRET: str = os.getenv("RADIUS_SHARED_SECRET", "")

        # Backend
        self.BACKEND_API_URL: str = os.getenv(
            "RADIUS_BACKEND_API_URL", "http://localhost:8000/api"
        ).rstrip("/")
        self.INTERNAL_API_SECRET: str = os.getenv("INTERNAL_API_SECRET", "")
        self.BACKEND_TIMEOUT_SECONDS: float = float(
            os.getenv("RADIUS_BACKEND_TIMEOUT_SECONDS", "5") or 5
        )

        # Anti-brute-force: N consecutive rejects for the same document lock
        # it for COOLDOWN seconds without hitting the backend.
        self.FAIL_THRESHOLD: int = _int_env("RADIUS_FAIL_THRESHOLD", 5)
        self.FAIL_COOLDOWN_SECONDS: int = _int_env("RADIUS_FAIL_COOLDOWN_SECONDS", 60)

        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
