"""
Startup secret validation — fail fast in production.

``assert_production_secrets`` runs once at app startup (see ``main.lifespan``).
When production mode is active (``ENVIRONMENT == "production"`` OR the
``REQUIRE_PROD_SECRETS`` env var is truthy), it raises ``RuntimeError`` if any
required secret is missing, too short, or a known placeholder. In dev/test it is
a no-op so the suite still boots.

ENCRYPTION_KEY is WARN-ONLY: hard-rejecting it would brick decryption of the
biometric data already encrypted under the current key. Key rotation is tracked
as a separate follow-up.

NOTE on CV_API_KEY: the backend ``Settings`` class exposes ``CV_API_KEY`` (the
key the backend uses to authenticate to the CV service), not ``API_KEY``. We
validate ``CV_API_KEY`` here — validating a non-existent field would always
fail and brick production startup. The CV service's own ``API_KEY`` is enforced
at runtime by ``verify_api_key`` (S2) and is not visible to this process.
"""

import base64
import binascii
import logging
import os

from core.config import settings

logger = logging.getLogger(__name__)

# Known placeholder / default values that must never reach production.
PLACEHOLDER_BLOCKLIST = frozenset(
    {
        "",
        "changeme",
        "secret",
        "admin123",
        "dev-jwt-secret-change-in-production",
        "UJrZ7tMU93YaNX",
        "replace-me",
        "your-secret-key",
    }
)

_TRUTHY = frozenset({"1", "true", "yes"})


def _production_mode() -> bool:
    """True when production-grade secret enforcement must be active."""
    if settings.ENVIRONMENT == "production":
        return True
    return os.getenv("REQUIRE_PROD_SECRETS", "").strip().lower() in _TRUTHY


def _is_weak(value: str, min_length: int) -> bool:
    return (not value) or (value in PLACEHOLDER_BLOCKLIST) or (len(value) < min_length)


def _decoded_key_length(value: str) -> int:
    """
    Mirror core.encryption.get_encryption_key's encoding detection and return the
    TRUE decoded byte length (without the padding that get_encryption_key applies,
    so a short raw key is correctly flagged as < 32 bytes).
    """
    if len(value) == 44 and value.endswith("="):
        try:
            return len(base64.b64decode(value, validate=True))
        except (binascii.Error, ValueError):
            return 0
    if len(value) == 64:
        try:
            return len(bytes.fromhex(value))
        except ValueError:
            return 0
    return len(value.encode("utf-8"))


def assert_production_secrets() -> None:
    """
    Raise ``RuntimeError`` if any required production secret is missing/weak.

    No-op outside production mode. ENCRYPTION_KEY issues only emit a warning.
    """
    if not _production_mode():
        return

    problems = []

    def require(name: str, min_length: int) -> None:
        value = getattr(settings, name, "") or ""
        if _is_weak(value, min_length):
            problems.append(
                f"{name} must be set, at least {min_length} characters, "
                "and not a known placeholder"
            )

    # 32-char shared/JWT secrets
    for name, min_len in (
        ("JWT_SECRET", 32),
        ("INTERNAL_API_SECRET", 32),
        ("WOMPI_INTEGRITY_SECRET", 32),
    ):
        require(name, min_len)

    # Admin password — weaker floor than tokens
    require("ADMIN_PASSWORD", 10)

    # Backend's CV-service auth key (see module docstring re: CV_API_KEY)
    require("CV_API_KEY", 24)

    # ENCRYPTION_KEY — warn only (rotation is a separate follow-up)
    enc_key = getattr(settings, "ENCRYPTION_KEY", "") or ""
    enc_ok = (
        enc_key
        and enc_key not in PLACEHOLDER_BLOCKLIST
        and _decoded_key_length(enc_key) >= 32
    )
    if not enc_ok:
        logger.warning(
            "ENCRYPTION_KEY is missing, shorter than 32 bytes, or a known "
            "placeholder. Existing biometric data cannot be re-keyed "
            "automatically; rotate via the documented migration path."
        )

    if problems:
        raise RuntimeError(
            "Production secret validation failed: " + "; ".join(problems)
        )
