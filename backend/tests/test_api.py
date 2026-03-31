# ============================================================
# ClassifierBT Test Suite
# ============================================================
# Run with: pytest tests/test_api.py -v
#
# These tests use an in-memory SQLite database, NOT your real
# PostgreSQL. Your production data is never touched.
#
# What's tested:
#   - Health check
#   - User registration (success + validation errors)
#   - User login (success + wrong credentials)
#   - Protected endpoint access (with + without token)
# ============================================================
from unittest.mock import MagicMock
import sys

# Mock the ML model loader so it doesn't need the .keras file
sys.modules["app.services.predictor"] = MagicMock()
sys.modules["app.services.model_loader"] = MagicMock()
sys.modules["app.services.preprocessing"] = MagicMock()


# Mock the ML modules so TensorFlow doesn't need to load during tests
sys.modules["tensorflow"] = MagicMock()
sys.modules["tensorflow.keras"] = MagicMock()
sys.modules["tensorflow.keras.applications"] = MagicMock()
sys.modules["tensorflow.keras.applications.vgg16"] = MagicMock()
sys.modules["tensorflow.keras.models"] = MagicMock()


# Point database to test SQLite BEFORE importing app
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"


import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database.database import Base, get_db


# ── Test Database Setup ─────────────────────────────────────
# In-memory SQLite — created fresh, destroyed after tests
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite needs this
)

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Swap real PostgreSQL with test SQLite."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Override the database dependency
app.dependency_overrides[get_db] = override_get_db

# Disable rate limiting during tests
from app.middleware.rate_limit import limiter

limiter.enabled = False


# ── Create/drop tables for each test session ────────────────
@pytest.fixture(autouse=True)
def setup_database():
    """Create all tables before tests, drop them after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


# ── Test Client ──────────────────────────────────────────────
client = TestClient(app)


# ── Helper: register + login, return auth header ─────────────
def get_auth_header(
    email="testuser@example.com", username="testuser", password="securepassword123"
):
    """Register a user, log them in, return the Authorization header."""
    # Register
    client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    # Login
    login_response = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# HEALTH CHECK
# ============================================================


def test_health_check():
    """GET /health should return 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ============================================================
# USER REGISTRATION
# ============================================================


def test_register_success():
    """Valid registration should return 201 with user data."""
    response = client.post(
        "/api/auth/register",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["username"] == "newuser"
    assert data["is_active"] is True
    # Password should NEVER appear in the response
    assert "password" not in data
    assert "hashed_password" not in data


def test_register_duplicate_email():
    """Registering with an existing email should return 400."""
    # First registration
    client.post(
        "/api/auth/register",
        json={
            "email": "dupe@example.com",
            "username": "user1",
            "password": "securepassword123",
        },
    )
    # Same email, different username
    response = client.post(
        "/api/auth/register",
        json={
            "email": "dupe@example.com",
            "username": "user2",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]


def test_register_duplicate_username():
    """Registering with an existing username should return 400."""
    client.post(
        "/api/auth/register",
        json={
            "email": "first@example.com",
            "username": "sameuser",
            "password": "securepassword123",
        },
    )
    response = client.post(
        "/api/auth/register",
        json={
            "email": "second@example.com",
            "username": "sameuser",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 400
    assert "Username already exists" in response.json()["detail"]


def test_register_short_password():
    """Password under 8 characters should return 400."""
    response = client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "username": "shortpass", "password": "abc"},
    )
    assert response.status_code == 400
    assert "8 characters" in response.json()["detail"]


def test_register_invalid_email():
    """Invalid email format should return 422 (Pydantic validation)."""
    response = client.post(
        "/api/auth/register",
        json={
            "email": "not-an-email",
            "username": "bademail",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 422


# ============================================================
# USER LOGIN
# ============================================================


def test_login_success():
    """Valid credentials should return a JWT token."""
    # Register first
    client.post(
        "/api/auth/register",
        json={
            "email": "login@example.com",
            "username": "loginuser",
            "password": "securepassword123",
        },
    )
    # Login
    response = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "securepassword123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # Token should be a non-empty string
    assert len(data["access_token"]) > 0


def test_login_wrong_password():
    """Wrong password should return 401."""
    client.post(
        "/api/auth/register",
        json={
            "email": "wrongpass@example.com",
            "username": "wrongpass",
            "password": "securepassword123",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"email": "wrongpass@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_login_nonexistent_user():
    """Login with unregistered email should return 401."""
    response = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "doesntmatter"},
    )
    assert response.status_code == 401


# ============================================================
# PROTECTED ENDPOINTS
# ============================================================


def test_me_without_token():
    """GET /api/auth/me without a token should return 403."""
    response = client.get("/api/auth/me")
    assert response.status_code == 403


def test_me_with_fake_token():
    """GET /api/auth/me with an invalid token should return 401."""
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer fake.token.here"}
    )
    assert response.status_code == 401


def test_me_with_valid_token():
    """GET /api/auth/me with valid token should return user info."""
    headers = get_auth_header()
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert data["username"] == "testuser"
    assert "hashed_password" not in data


def test_predictions_without_token():
    """GET /api/predictions without token should return 403."""
    response = client.get("/api/predictions")
    assert response.status_code == 403


def test_predictions_with_valid_token():
    """GET /api/predictions with valid token should return empty list."""
    headers = get_auth_header()
    response = client.get("/api/predictions", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["predictions"] == []
    assert data["total"] == 0
