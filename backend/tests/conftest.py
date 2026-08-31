"""Pytest Configuration and Global Fixtures for Provenance Verification System.
Configures dedicated test database isolation (provenance_test_db).
"""

import io
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# ---------------------------------------------------------------------------
# 1. Test Database Isolation Configuration
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://provenance:provenance123@localhost:5432/provenance_test_db",
)

# Set environment variable and override settings
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.config import settings
settings.DATABASE_URL = TEST_DATABASE_URL

import app.database as app_db
from app.models.database import Base

# Create isolated test engine and session factory
test_engine = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    echo=False,
)

test_SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
    expire_on_commit=False,
)

# Overwrite engine & SessionLocal in app.database module so all app code & tests use test DB
app_db.engine = test_engine
app_db.SessionLocal = test_SessionLocal

# Import app and security utilities after test database is bound
from app.core.security import create_access_token
from app.main import app
from app.models.database import User, UserRole
from app.services.auth_service import register_admin, register_publisher


@pytest.fixture(scope="session", autouse=True)
def ensure_test_database_initialized():
    """Ensure provenance_test_db schema is created before test execution."""
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture(scope="session")
def app_instance():
    """Return the FastAPI application instance."""
    return app


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    """Database session fixture with automatic rollback/cleanup against provenance_test_db."""
    session = test_SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def publisher_user_and_token(db: Session):
    """Fixture providing an authenticated Government Publisher and Bearer token."""
    email = f"pub_test_{uuid.uuid4().hex[:6]}@pib.gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="PublisherPassword#123",
        organization_name="Press Information Bureau",
        organization_domain="gov.in",
        department="Official Press Directorate",
        designation="Chief Information Officer",
    )
    token = create_access_token(user.id, UserRole.PUBLISHER)
    return user, token


@pytest.fixture
def admin_user_and_token(db: Session):
    """Fixture providing an authenticated National Provenance Authority Admin and Bearer token."""
    email = f"admin_test_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_admin(
        db=db,
        email=email,
        password="AdminPassword#123",
        organization_name="National Provenance Authority",
        organization_domain="gov.in",
    )
    token = create_access_token(user.id, UserRole.ADMIN)
    return user, token


@pytest.fixture
def viewer_user_and_token(db: Session):
    """Fixture providing an authenticated Viewer citizen user and Bearer token."""
    from app.core.security import hash_password
    email = f"viewer_test_{uuid.uuid4().hex[:6]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("ViewerPassword#123"),
        role=UserRole.VIEWER,
        organization_name="Citizen Observer",
        organization_domain="example.com",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, UserRole.VIEWER)
    return user, token


@pytest.fixture
def viewer_headers(viewer_user_and_token):
    """Convenience fixture returning Authorization headers for a viewer."""
    _, token = viewer_user_and_token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def publisher_headers(publisher_user_and_token):
    """Convenience fixture returning Authorization headers for a publisher."""
    _, token = publisher_user_and_token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user_and_token):
    """Convenience fixture returning Authorization headers for an admin."""
    _, token = admin_user_and_token
    return {"Authorization": f"Bearer {token}"}
