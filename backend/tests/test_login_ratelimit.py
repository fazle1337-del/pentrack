"""Login rate limiting (issue #6).

The limiter is in-process and keyed on the client IP (left-most X-Forwarded-For),
so each test uses a distinct fake IP to stay isolated from the global counter.
The configured limit is 10/minute, so the 11th request from one IP gets a 429.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _attempt(client, ip):
    return client.post(
        "/auth/login",
        data={"username": "nobody@example.com", "password": "wrong"},
        headers={"X-Forwarded-For": ip},
    )


def test_login_throttles_after_limit(client):
    ip = "203.0.113.10"
    # First 10 attempts are processed (401 for bad creds), not throttled.
    for _ in range(10):
        assert _attempt(client, ip).status_code == 401
    # 11th from the same IP is rate limited.
    assert _attempt(client, ip).status_code == 429


def test_limit_is_per_client_ip(client):
    # Exhaust one IP...
    spent = "203.0.113.20"
    for _ in range(11):
        _attempt(client, spent)
    assert _attempt(client, spent).status_code == 429
    # ...a different IP is unaffected.
    assert _attempt(client, "203.0.113.21").status_code == 401
