"""
Configuration for CV service.
"""
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """CV Service settings."""
    
    # Service
    SERVICE_NAME: str = "PowerHouse CV Service"
    SERVICE_VERSION: str = "1.0.0"
    
    # API Authentication
    API_KEY: str = ""  # Empty = no auth required (for development)
    
    # Shared secret for backend ↔ CV service internal communication
    INTERNAL_API_SECRET: str = ""  # MUST match backend's INTERNAL_API_SECRET
    
    # Backend API
    BACKEND_API_URL: str = "http://localhost:8000/api"
    API_TIMEOUT: int = 30
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL: int = 86400  # 24 hours

    # Biometric at-rest encryption (Redis template cache). AES-256 key in
    # one of three forms: 44-char base64, 64-char hex, or raw 32 bytes.
    # When set, cached face embeddings are encrypted with AES-256-GCM.
    ENCRYPTION_KEY: str = ""

    # Fail-closed production posture: when enabled, refuse to run with
    # cleartext biometric cache or cleartext (http://) backend transport.
    REQUIRE_PROD_SECRETS: bool = False
    
    # Face Recognition
    FACE_DETECTION_MODEL: str = "mtcnn"  # or "haar"
    CONFIDENCE_THRESHOLD: float = 0.85
    MIN_FACE_SIZE: int = 100
    
    # GPU
    USE_GPU: bool = False
    
    # RTSP Processing
    FRAME_BUFFER_SIZE: int = 3
    RECONNECT_DELAY: int = 5
    MAX_RECONNECT_ATTEMPTS: int = 3
    
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # CORS
    CORS_ORIGINS: str = "http://localhost"  # Comma-separated list
    
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars from shared .env file

# Global settings instance
settings = Settings()
