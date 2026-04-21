"""
FastAPI main application.
"""
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from core.config import settings
from api import auth, members, health, memberships, sales, events, cameras, enrollment, membership_plans, settings as api_settings, users, cv_internal, audit, import_export, password_reset, reports_email, portal_auth, portal, enrollment_requests, sync

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

# Middleware to handle Cloudflare cached JSON responses
from starlette.middleware.base import BaseHTTPMiddleware

class CloudflareCacheBustMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Force no-cache on all HTML and JSON root responses
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["CDN-Cache-Control"] = "no-store"
            response.headers["Cloudflare-CDN-Cache-Control"] = "no-store"
        return response

app.add_middleware(CloudflareCacheBustMiddleware)

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
app.include_router(portal_auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(portal.router, prefix=settings.API_V1_PREFIX)
app.include_router(enrollment_requests.router, prefix=settings.API_V1_PREFIX)
app.include_router(sync.router, prefix=settings.API_V1_PREFIX)


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
        print(f"✅ Email report scheduler started (every 2 hours). SMTP enabled: {bool(settings.SMTP_HOST)}")
    except Exception as e:
        print(f"❌ Failed to start scheduler: {e}")


# Serve frontend static files (for when tunnel hits backend directly)
FRONTEND_DIST = "/opt/powerhouse-membership/frontend/dist"

if os.path.isdir(FRONTEND_DIST):
    # Mount assets directory
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

    # Serve other static files (favicon, logos, etc.)
    app.mount("/static", StaticFiles(directory=FRONTEND_DIST), name="static-files")

@app.get("/")
def serve_frontend_root():
    """Serve frontend index.html at root."""
    from fastapi.responses import FileResponse as FR
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        response = FR(index_path)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["CDN-Cache-Control"] = "no-store"
        return response
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION, "status": "running"}

@app.get("/api-status")
def api_status():
    """API status endpoint (moved from /)."""
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
