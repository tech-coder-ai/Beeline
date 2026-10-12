from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.persistence.db import init_engine


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SPA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SPA_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("SPA_LLM_PROVIDER", "offline")
    monkeypatch.setenv("SPA_IMAGE_PROVIDER", "placeholder")
    monkeypatch.setenv("SPA_PUBLISH_PROVIDER", "dry_run")
    monkeypatch.setenv("SPA_MODE", "approval_required")
    # tiny renders keep the end-to-end test fast
    monkeypatch.setenv("SPA_VIDEO_WIDTH", "320")
    monkeypatch.setenv("SPA_VIDEO_HEIGHT", "180")
    monkeypatch.setenv("SPA_VIDEO_FPS", "12")
    get_settings.cache_clear()
    s = get_settings()
    s.models.image.width, s.models.image.height = 448, 256
    s.pipeline.retry_backoff_seconds = 0
    init_engine(s)
    yield s
    get_settings.cache_clear()


@pytest.fixture
def client(settings):
    from app.main import app
    # no `with`: lifespan (and its background runner) is not started; tests drain jobs synchronously
    return TestClient(app)


@pytest.fixture
def approved_story(client):
    found = client.post("/api/stories/discover", json={"connector": "library", "query": "Lion"}).json()
    story = found[0]["story"]
    r = client.post(f"/api/stories/{story['id']}/approve")
    assert r.status_code == 200, r.text
    return r.json()
