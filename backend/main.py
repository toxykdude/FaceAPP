"""
FastAPI main application.
"""
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from api import auth, members, health, memberships, sales, events, cameras, enrollment, membership_plans, settings as api_settings, users, cv_internal, audit, import_export, password_reset, reports_email

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Membership Management with Facial Recognition",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Rate limiting (global fallback — Nginx handles per-endpoint limits)
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(members.router, prefix=settings.API_V1_PREFIX)
app.include_router(memberships.router, prefix=settings.API_V1_PREFIX)
app.include_router(sales.router, prefix=settings.API_V1_PREFIX)
app.include_router(events.router, prefix=settings.API_V1_PREFIX)
app.include_router(cameras.router, prefix=settings.API_V1_PREFIX)
app.include_router(enrollment.router, prefix=settings.API_V1_PREFIX)
app.include_router(membership_plans.router, prefix=settings.API_V1_PREFIX)
app.include_router(api_settings.router, prefix=settings.API_V1_PREFIX)
app.include_router(cv_internal.router, prefix=settings.API_V1_PREFIX)
app.include_router(audit.router, prefix=settings.API_V1_PREFIX)
app.include_router(import_export.router, prefix=settings.API_V1_PREFIX)
app.include_router(password_reset.router, prefix=settings.API_V1_PREFIX)
app.include_router(reports_email.router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
def start_scheduler():
    """Start the background scheduler for email reports."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from api.reports_email import send_scheduled_report
    from core.database import SessionLocal
    
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            send_scheduled_report,
            "interval",
            hours=2,
            args=[SessionLocal],
            id="email_report",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Email report scheduler started (every 2 hours)")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
