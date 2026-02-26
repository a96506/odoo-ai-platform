"""
Shared pytest fixtures: in-memory SQLite DB, FastAPI TestClient, mock Odoo/Claude clients.
"""

import os
import hmac
import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("AI_DATABASE_URL", "sqlite:///")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ODOO_URL", "http://localhost:8069")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("AI_SECRET_KEY", "test-api-key")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")

from app.config import get_settings, Settings
from app.models.audit import Base, get_db

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=_test_engine)


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Clear lru_cache on Settings between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db_session():
    """Create all tables in an in-memory SQLite DB and yield a session."""
    Base.metadata.create_all(_test_engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(_test_engine)


@pytest.fixture()
def settings() -> Settings:
    return get_settings()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with DB session override and Celery tasks mocked out."""
    from fastapi.testclient import TestClient

    def _override_db():
        yield db_session

    with (
        patch("app.main.init_db"),
        patch("app.main.init_automations"),
        patch("app.main.seed_default_rules"),
        patch("app.tasks.celery_tasks.process_webhook_event.delay"),
        patch("app.tasks.celery_tasks.execute_approved_action.delay"),
    ):
        from app.main import app

        app.dependency_overrides[get_db] = _override_db
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()


@pytest.fixture()
def api_key() -> str:
    return "test-api-key"


@pytest.fixture()
def auth_headers(api_key) -> dict:
    return {"X-API-Key": api_key}


@pytest.fixture()
def webhook_secret() -> str:
    return "test-webhook-secret"


def make_webhook_signature(body: bytes, secret: str = "test-webhook-secret") -> str:
    """Compute HMAC-SHA256 hex digest for a webhook body."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture()
def signed_webhook_headers(webhook_secret):
    """Factory fixture: returns a function that computes signed headers for a payload dict."""
    def _make(payload: dict) -> dict:
        body = json.dumps(payload).encode()
        sig = make_webhook_signature(body, webhook_secret)
        return {"X-Webhook-Signature": sig, "Content-Type": "application/json"}
    return _make


@pytest.fixture()
def mock_odoo():
    """A MagicMock standing in for the OdooClient."""
    m = MagicMock()
    m.version.return_value = "18.0"
    m.get_record.return_value = {"id": 1, "name": "Test"}
    m.search_read.return_value = []
    m.write.return_value = True
    m.create.return_value = 1
    return m


@pytest.fixture()
def mock_claude():
    """A MagicMock standing in for the Claude client."""
    m = MagicMock()
    m.analyze.return_value = {
        "tool_name": "test_action",
        "tool_input": {"action": "test", "confidence": 0.9, "reasoning": "mock"},
    }
    return m
