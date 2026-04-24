"""
Database configuration and session management.
"""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from core.config import settings

# Create database engine (backend_app role — admin/staff operations)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,        # Connection pool size
    max_overflow=20,     # Max connections beyond pool_size
    echo=settings.DEBUG,  # Log SQL queries in debug mode
    connect_args={'options': '-c client_encoding=UTF8'}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Member portal engine (member_portal role — member self-service with RLS)
# Only created if MEMBER_PORTAL_DATABASE_URL is configured
_portal_engine = None
PortalSessionLocal = None

if settings.MEMBER_PORTAL_DATABASE_URL:
    _portal_engine = create_engine(
        settings.MEMBER_PORTAL_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=settings.DEBUG,
        connect_args={'options': '-c client_encoding=UTF8'}
    )
    PortalSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_portal_engine)


class Base(DeclarativeBase):
    pass


def get_portal_db(member_id: str = None):
    """
    Database session dependency for member portal endpoints (member_portal role).
    Sets app.member_id for RLS policies to enforce row-level filtering.
    """
    if not PortalSessionLocal:
        raise RuntimeError("MEMBER_PORTAL_DATABASE_URL not configured")

    db = PortalSessionLocal()
    try:
        if member_id:
            db.execute(text("SET LOCAL app.member_id = :mid"), {"mid": str(member_id)})
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
