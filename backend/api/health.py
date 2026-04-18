"""
Health check API endpoints.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import redis
import logging

logger = logging.getLogger(__name__)

from api.deps import get_db
from core.config import settings
from schemas.common import HealthResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
def health_check():
    """
    Basic health check.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc),
        "version": settings.APP_VERSION
    }


@router.get("/db", response_model=HealthResponse)
def health_check_database(db: Session = Depends(get_db)):
    """
    Health check with database connectivity test.
    """
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        db_status = "error"
    
    return {
        "status": "healthy" if db_status == "connected" else "unhealthy",
        "timestamp": datetime.now(timezone.utc),
        "version": settings.APP_VERSION,
        "database": db_status
    }


@router.get("/redis", response_model=HealthResponse)
def health_check_redis():
    """
    Health check with Redis connectivity test.
    """
    try:
        # Test Redis connection
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        redis_status = "connected"
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        redis_status = "error"
    
    return {
        "status": "healthy" if redis_status == "connected" else "unhealthy",
        "timestamp": datetime.now(timezone.utc),
        "version": settings.APP_VERSION,
        "redis": redis_status
    }


@router.get("/full", response_model=HealthResponse)
def health_check_full(db: Session = Depends(get_db)):
    """
    Comprehensive health check (database + Redis).
    """
    # Check database
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        db_status = "error"
    
    # Check Redis
    try:
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        redis_status = "connected"
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        redis_status = "error"
    
    overall_status = "healthy" if (db_status == "connected" and redis_status == "connected") else "unhealthy"
    
    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc),
        "version": settings.APP_VERSION,
        "database": db_status,
        "redis": redis_status
    }
