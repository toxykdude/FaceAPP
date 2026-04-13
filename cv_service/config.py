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
    DEBUG: bool = False
    
    # Backend API
    BACKEND_API_URL: str = "http://localhost:8000/api"
    API_TIMEOUT: int = 30
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL: int = 86400  # 24 hours
    
    # Face Recognition
    FACE_DETECTION_MODEL: str = "mtcnn"  # or "haar"
    FACE_RECOGNITION_MODEL: str = "facenet"  # or "arcface"
    CONFIDENCE_THRESHOLD: float = 0.85
    ENROLLMENT_QUALITY_THRESHOLD: float = 0.90
    MIN_FACE_SIZE: int = 100
    
    # GPU
    USE_GPU: bool = False
    CUDA_DEVICE: int = 0
    
    # RTSP Processing
    DEFAULT_FPS: int = 5
    FRAME_BUFFER_SIZE: int = 3
    RECONNECT_DELAY: int = 5
    MAX_RECONNECT_ATTEMPTS: int = 3
    
    # Enrollment
    ENROLLMENT_ANGLES: int = 3  # Front, left, right
    ENROLLMENT_FRAMES_PER_ANGLE: int = 2
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # CORS
    CORS_ORIGINS: str = "http://localhost"  # Comma-separated list
    
    # File Storage
    SNAPSHOT_DIR: str = "/var/lib/powerhouse/snapshots"
    SAVE_SNAPSHOTS: bool = False  # Save denied access snapshots
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars from shared .env file


# Global settings instance
settings = Settings()
