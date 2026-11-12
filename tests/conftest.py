from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="infoflow-tests-"))

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DEBUG": "false",
        "SECRET_KEY": "test-secret-key-that-is-long-enough",
        "DATABASE_URL": f"sqlite:///{(TEST_DIR / 'test.db').as_posix()}",
        "AUTO_CREATE_TABLES": "true",
        "AI_PROVIDER": "none",
        "EMBEDDING_PROVIDER": "hash",
        "VECTOR_BACKEND": "local",
        "USE_CELERY": "false",
        "CORS_ORIGINS": "*",
        "DATA_DIR": str(TEST_DIR / "data"),
        "UPLOAD_DIR": str(TEST_DIR / "uploads"),
        "CHROMA_PATH": str(TEST_DIR / "chroma"),
        "ALLOW_PRIVATE_URLS": "false",
        "TELEGRAM_BOT_TOKEN": "",
        "TRANSCRIPTION_API_KEY": "",
    }
)

import pytest
from fastapi.testclient import TestClient

from app.database import Base, get_engine, get_session_factory, init_db
from app.main import app
from app.services.vector_store import get_vector_store

init_db()

@pytest.fixture(autouse=True)
def clean_database():
    db = get_session_factory()()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()
    get_vector_store().clear()
    yield

@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client

def register_user(client: TestClient, email: str | None = None) -> dict:
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    password = "strong-password-123"
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return {
        "token": payload["access_token"],
        "user": payload["user"],
        "email": email,
        "password": password,
    }

def auth_headers(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['token']}"}

def create_note(client: TestClient, user: dict, text: str, title: str | None = None) -> dict:
    response = client.post(
        "/api/items",
        headers=auth_headers(user),
        json={"type": "note", "text": text, "title": title},
    )
    assert response.status_code == 202, response.text
    return response.json()
