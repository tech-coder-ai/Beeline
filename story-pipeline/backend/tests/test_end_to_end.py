"""The whole pipeline, offline: library story -> rights -> script -> art -> voices -> MP4 -> QC -> (dry-run) upload."""
import json
import shutil
from pathlib import Path

import pytest

from app.media import probe
from app.persistence.db import session_scope
from app.persistence.models import Publication
from app.providers.errors import ProviderError
from app.providers.youtube.dry_run import DryRunPublisher
from app.workflow.runner import drain

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _advance(client, settings, pid, checkpoint):
    drain(settings)
    p = client.get(f"/api/projects/{pid}").json()
    failed = [j for j in p["jobs"] if j["status"] == "FAILED"]
    assert not failed, failed[0]["error"]
    assert p["pending_checkpoint"] == checkpoint, (p["status"], p["pending_checkpoint"])
    r = client.post(f"/api/projects/{pid}/checkpoints/{checkpoint}/approve", json={"note": "lgtm"})
    assert r.status_code == 200, r.text


def _run_to_approved(client, settings, story_id):
    pid = client.post("/api/projects", json={"source_id": story_id}).json()["id"]
    client.post(f"/api/projects/{pid}/run")
    _advance(client, settings, pid, "story_adaptation")
    _advance(client, settings, pid, "character_generation")
    _advance(client, settings, pid, "final_render")
    return pid


def test_full_pipeline_offline(client, settings, approved_story):
    pid = _run_to_approved(client, settings, approved_story["id"])
    p = client.get(f"/api/projects/{pid}").json()
    assert p["status"] == "QC_APPROVED"

    # Hindi is a configured target but there is no LLM to translate -> skipped, not faked
    locs = {l["language"]: l for l in p["localizations"]}
    assert locs["en"]["status"] == "ready" and locs["hi"]["status"] == "skipped"

    render = next(r for r in p["renders"] if r["language"] == "en")
    assert render["qc_passed"] is True, [c for c in render["qc"]["checks"] if c["status"] == "fail"]
    root = Path(settings.data_dir) / "projects" / pid
    info = probe(root / "languages/en/final.mp4")
    kinds = {s["codec_type"] for s in info["streams"]}
    assert kinds == {"video", "audio", "subtitle"}
    assert (root / "languages/en/subtitles.srt").read_text().startswith("1\n")
    meta = json.loads((root / "metadata/en.json").read_text())
    assert "AI-generated" in meta["description"] and "Townsend" in meta["description"]

    # publish (dry run), then publish again: second run must not create a second upload
    job = client.post(f"/api/projects/{pid}/publish", json={"visibility": "private"}).json()
    drain(settings)
    p = client.get(f"/api/projects/{pid}").json()
    assert p["status"] == "UPLOADED", p["jobs"][0]
    assert p["publications"][0]["status"] == "uploaded" and p["publications"][0]["visibility"] == "private"
    client.post(f"/api/projects/{pid}/publish")
    drain(settings)
    p = client.get(f"/api/projects/{pid}").json()
    assert len(p["publications"]) == 1
    assert "already published" in p["jobs"][0]["output"]["publications"]["en"]
    assert job.get("stage") == "publish", job

    # rerunning render with nothing changed reuses the output
    ov = client.get("/api/overview").json()
    assert ov["stage_timings"]["render"]["runs"] == 1


def test_publish_timeout_is_reconciled_not_duplicated(client, settings, approved_story, monkeypatch):
    """Upload succeeded on the platform but we saw a timeout: the retry must find it, not upload again."""
    pid = _run_to_approved(client, settings, approved_story["id"])
    uploads = {"n": 0}

    class FlakyPublisher(DryRunPublisher):
        def upload(self, *a, **k):
            uploads["n"] += 1
            super().upload(*a, **k)
            raise ProviderError("read timeout", transient=True)   # created, but we never heard back

    import app.services.publishing.service as pubsvc
    monkeypatch.setattr(pubsvc, "build_publisher", lambda s, root: FlakyPublisher(root / "publishing"))
    client.post(f"/api/projects/{pid}/publish")
    drain(settings)   # attempt 1 fails (transient) -> RETRY_PENDING -> attempt 2 reconciles
    p = client.get(f"/api/projects/{pid}").json()
    assert uploads["n"] == 1
    assert p["status"] == "UPLOADED"
    with session_scope() as db:
        pubs = db.query(Publication).filter(Publication.project_id == pid).all()
        assert len(pubs) == 1 and pubs[0].retries == 1 and pubs[0].status == "uploaded"
