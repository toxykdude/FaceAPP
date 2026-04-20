"""
Application configuration using Pydantic settings.
"""
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
    EVOLUTION_INSTANCE_NAME: str = "Powerbt"
    
    # Email (optional)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_USE_SSL: bool = False
    
    # Wompi Payment Integration
    WOMPI_PUBLIC_KEY: Optional[str] = None  # Public key for frontend widget
    WOMPI_INTEGRITY_SECRET: Optional[str] = None  # HMAC-SHA256 webhook verification
    WOMPI_EVENT_URL: Optional[str] = None  # Wompi events API URL

    # Frontend & CORS
    FRONTEND_URL: str = "http://localhost"
    CORS_ORIGINS: str = "http://localhost"  # Comma-separated list
    
    # Monitoring
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# Global settings instance
settings = Settings()
