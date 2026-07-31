"""
FastAPI main application.
"""

import logging
import uuid
import traceback
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
import os

from core.config import settings
from core.rate_limiter import limiter
from api import (
    auth,
    members,
    health,
    memberships,
    sales,
    events,
    cameras,
    enrollment,
    membership_plans,
    settings as api_settings,
    users,
    cv_internal,
    audit,
    import_export,
    password_reset,
    reports_email,
    portal_auth,
    portal,
    enrollment_requests,
    sync,
    system,
)

logger = logging.getLogger(__name__)

# Disable API documentation in production (VULN-017)
_is_production = settings.ENVIRONMENT == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate production secrets, then start the background scheduler."""
    from core.startup_checks import assert_production_secrets

    # Fail fast on missing/weak secrets in production (S3). No-op in dev/test.
    try:
        assert_production_secrets()
    except RuntimeError:
        logger.exception("Production secret validation failed — aborting startup")
        raise

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
        print(
            f"✅ Email report scheduler started (every 2 hours). SMTP enabled: {bool(settings.SMTP_HOST)}"
        )
    except Exception as e:
        print(f"❌ Failed to start scheduler: {e}")

    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Membership Management with Facial Recognition",
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",  # VULN-8 fix
    lifespan=lifespan,
)

# Rate limiting (global fallback — Nginx handles per-endpoint limits)
app.state.limiter = limiter
from slowapi import _rate_limit_exceeded_handler

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# === Security Middleware ===


class CRLFSanitizationMiddleware(BaseHTTPMiddleware):
    """Strip CR/LF characters from all request inputs (VULN-013)."""

    async def dispatch(self, request: Request, call_next):
        # Sanitize query parameters
        if request.query_params:
            sanitized = {}
            has_crlf = False
            for key, value in request.query_params.items():
                clean = value.replace("\r", "").replace("\n", "")
                if clean != value:
                    has_crlf = True
                sanitized[key] = clean
            if has_crlf:
                from urllib.parse import urlencode

                request.scope.update(
                    query_string=urlencode(sanitized).encode("latin-1")
                )
        response = await call_next(request)
        return response


class CloudflareCacheBustMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Force no-cache on all HTML and JSON root responses
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["CDN-Cache-Control"] = "no-store"
            response.headers["Cloudflare-CDN-Cache-Control"] = "no-store"
        return response


app.add_middleware(CRLFSanitizationMiddleware)
app.add_middleware(CloudflareCacheBustMiddleware)

# === Production Error Hardening (VULN-022, VULN-6) ===


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """
    VULN-6 fix: Return generic validation errors without revealing
    Pydantic/FastAPI internals (framework names, error URLs, etc).
    """
    request_id = str(uuid.uuid4())[:8]
    # Extract only field-level info, no framework URLs
    errors = []
    for err in exc.errors():
        errors.append(
            {
                "field": ".".join(str(l) for l in err.get("loc", [])),
                "message": err.get("msg", "Invalid value"),
            }
        )
    logger.warning(
        f"[{request_id}] Validation error on {request.method} {request.url.path}: {errors}"
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": errors,
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def production_error_handler(request: Request, exc: Exception):
    """
    In production, return generic error responses to prevent
    information leakage via stack traces and verbose messages.
    Full error details are logged server-side with a request ID.
    """
    request_id = str(uuid.uuid4())[:8]

    # Always log the full error server-side
    logger.error(
        f"[{request_id}] {request.method} {request.url.path}: "
        f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    )

    if _is_production:
        # Generic response — no stack traces, no internal details
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )
    else:
        # Development: include error details
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__,
                "request_id": request_id,
            },
        )


# Configure CORS — strict origin allowlist (VULN-011)
cors_origins = [
    origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
]

# In production, remove localhost origins and validate
if _is_production:
    _blocked = {"http://localhost", "http://localhost:3000", "http://localhost:8080"}
    cors_origins = [o for o in cors_origins if o not in _blocked]
    if not cors_origins:
        logger.warning(
            "CORS: No valid production origins configured — API will reject cross-origin requests"
        )

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
app.include_router(system.router, prefix=settings.API_V1_PREFIX)


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
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/api-status")
def api_status():
    """API status endpoint (moved from /)."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )
