"""
Application configuration using Pydantic settings.
"""

import os

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "PowerHouse Membership Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # API
    API_V1_PREFIX: str = "/api"
    API_PORT: int = 8000
    API_HOST: str = "0.0.0.0"

    # Database
    DATABASE_URL: str
    MEMBER_PORTAL_DATABASE_URL: str = ""

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str
    ENCRYPTION_KEY: str  # AES-256 key for biometric data
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Internal service authentication (shared with CV service)
    INTERNAL_API_SECRET: str = (
        ""  # Shared secret for backend ↔ CV service communication
    )

    # Admin User
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""  # REQUIRED: Set in .env with strong password

    # Facial Recognition
    FACE_CONFIDENCE_THRESHOLD: float = 0.85
    ENROLLMENT_QUALITY_THRESHOLD: float = 0.90
    MIN_FACE_SIZE: int = 80
    MAX_FACES_PER_ENROLLMENT: int = 5
    USE_GPU: bool = False
    CUDA_DEVICE: int = 0

    # File Storage
    SNAPSHOT_RETENTION_DAYS: int = 30

    # Evolution API (WhatsApp)
    EVOLUTION_API_URL: str = "https://wappbot.powerhousegym.co"
    EVOLUTION_API_KEY: str = ""  # REQUIRED: Set in .env — never use default
    EVOLUTION_INSTANCE_NAME: str = "SMS-Verification"

    # Email (optional)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_NAME: Optional[str] = "PowerHouse Gym"
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_USE_SSL: bool = False
    SMTP_SECURE: bool = False

    # Wompi Payment Integration
    WOMPI_PUBLIC_KEY: Optional[str] = None  # Public key for frontend widget
    WOMPI_INTEGRITY_SECRET: Optional[str] = None  # HMAC-SHA256 webhook verification
    WOMPI_EVENT_URL: Optional[str] = None  # Wompi events API URL

    # Frontend & CORS
    FRONTEND_URL: str = "http://localhost"
    CORS_ORIGINS: str = "http://localhost"  # Comma-separated list

    # Rate limiting — per-route slowapi limit for the public member-portal
    # auth routes (/api/auth/member-login|verify|resend). These are the only
    # internet-exposed auth endpoints (Cloudflare Tunnel allowlist), so their
    # limit is configurable without touching code.
    MEMBER_AUTH_RATE_LIMIT: str = "10/minute"

    # Monitoring
    LOG_LEVEL: str = "INFO"

    # CV Service
    CV_SERVICE_URL: str = "http://localhost:8001"
    CV_API_KEY: str = ""  # API key for authenticating with CV service

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# Global settings instance
settings = Settings()


def resolve_migration_database_url() -> str:
    """Return the connection URL Alembic should run migrations with.

    When ``MIGRATE_DATABASE_URL`` is set (a dedicated role that OWNS the tables,
    provisioned by ``scripts/migrations/002_migration_role.sql``) it takes
    precedence over the runtime ``DATABASE_URL``.

    The runtime role owns nothing on purpose. Table ownership carries DDL
    authority — ``DROP TABLE`` and, worse,
    ``ALTER TABLE ... DISABLE ROW LEVEL SECURITY`` — and a table owner also
    BYPASSES row-level security on every table that does not set FORCE ROW LEVEL
    SECURITY (only ``audit_logs`` does; the other 12 RLS tables, including both
    biometric tables, do not). Granting the internet-facing application role that
    authority permanently, to serve an operation that runs for seconds at deploy
    time, would trade a standing privilege escalation for a little convenience.

    Falls back to ``DATABASE_URL`` so local development, CI and the in-process
    migration tests — where the connecting role already owns the schema — keep
    working with no extra configuration. Read at call time, never logged;
    mirrors ``api/system.py::_resolve_pg_dump_url``.
    """
    return os.environ.get("MIGRATE_DATABASE_URL") or settings.DATABASE_URL
