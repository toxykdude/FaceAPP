"""
Test configuration and fixtures for FaceGYM backend tests.
Uses the real database with transaction rollback for isolation.
"""

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from main import app
from core.database import Base

# Override api.deps.get_db since routers import from there
from api.deps import get_db
from core.security import create_access_token
from models.user import User, UserRole
from models.member import Member
from models.membership import Membership, MembershipPlan, MembershipStatus
from models.camera import Camera
from core.encryption import encrypt_string


@pytest.fixture(scope="session")
def engine():
    """Create engine using the app's database."""
    from core.config import settings

    return create_engine(settings.DATABASE_URL)


@pytest.fixture(scope="function")
def db_session(engine):
    """Create a fresh database session with transaction rollback."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI test client with DB session override."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    # Override api.deps.get_db (the one routers actually use)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session):
    """Get existing admin user for testing."""
    user = db_session.query(User).filter(User.username == "admin").first()
    if not user:
        pytest.skip("No admin user found in database")
    return user


@pytest.fixture
def admin_token(admin_user):
    """Get JWT token for admin user."""
    return create_access_token(data={"sub": str(admin_user.id)})


@pytest.fixture
def auth_headers(admin_token):
    """Headers with valid JWT token."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def auth_client(client, auth_headers):
    """FastAPI test client with authentication headers pre-set."""
    client.headers.update(auth_headers)
    return client


@pytest.fixture
def sample_member(db_session):
    """Create a sample member for testing with unique email."""
    unique_suffix = uuid.uuid4().hex[:8]
    member = Member(
        first_name="Test",
        last_name="Member",
        email=f"test{unique_suffix}@example.com",
        phone="555-0100",
        status="active",
        consent_given_at=None,
    )
    db_session.add(member)
    db_session.flush()
    return member


@pytest.fixture
def sample_camera(db_session):
    """Create a sample camera for testing."""
    unique_suffix = uuid.uuid4().hex[:8]
    camera = Camera(
        name=f"Test Camera {unique_suffix}",
        rtsp_url=encrypt_string("rtsp://admin:pass@192.168.1.100:554/stream"),
        location="Entrance",
        enabled=True,
        fps=5,
    )
    db_session.add(camera)
    db_session.flush()
    return camera
