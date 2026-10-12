"""Workflow engine: retries, checkpoints, resumability."""
from app.domain.states import JobStatus, ProjectStatus, Stage
from app.persistence.db import session_scope
from app.persistence.models import Project, Scene, WorkflowJob
from app.providers.errors import ProviderError
from app.workflow import engine
from app.workflow.context import StageFailed
from app.workflow.runner import drain


def _project(client, approved_story):
    return client.post("/api/projects", json={"source_id": approved_story["id"]}).json()


def test_transient_failures_retry_then_succeed(client, settings, approved_story):
    pid = _project(client, approved_story)["id"]
    calls = {"n": 0}

    def flaky(ctx):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ProviderError("ollama restarting", transient=True)
        return {"ok": True}

    job_id = client.post(f"/api/projects/{pid}/generate-script").json()["id"]
    handlers = {Stage.SCRIPT: flaky}
    assert engine.run_job(job_id, settings, handlers) == JobStatus.RETRY_PENDING.value
    assert engine.run_job(job_id, settings, handlers) == JobStatus.RETRY_PENDING.value
    assert engine.run_job(job_id, settings, handlers) == JobStatus.SUCCEEDED.value
    with session_scope() as db:
        assert db.get(WorkflowJob, job_id).attempts == 3
        p = db.get(Project, pid)
        assert p.status == ProjectStatus.SCRIPT_READY.value
        assert p.pending_checkpoint == "story_adaptation"


def test_deterministic_failure_stops_and_manual_retry_works(client, settings, approved_story):
    pid = _project(client, approved_story)["id"]
    job_id = client.post(f"/api/projects/{pid}/generate-script").json()["id"]

    def broken(ctx):
        raise StageFailed("schema invalid")

    assert engine.run_job(job_id, settings, {Stage.SCRIPT: broken}) == JobStatus.FAILED.value
    r = client.post(f"/api/jobs/{job_id}/retry")
    assert r.status_code == 200 and r.json()["status"] == "QUEUED"
    assert engine.run_job(job_id, settings, {Stage.SCRIPT: lambda ctx: {}}) == JobStatus.SUCCEEDED.value


def test_one_active_job_per_project_and_checkpoint_gate(client, settings, approved_story):
    pid = _project(client, approved_story)["id"]
    assert client.post(f"/api/projects/{pid}/run").status_code == 200
    assert client.post(f"/api/projects/{pid}/run").status_code == 409   # already queued
    drain(settings)
    p = client.get(f"/api/projects/{pid}").json()
    assert p["status"] == "SCRIPT_READY" and p["pending_checkpoint"] == "story_adaptation"
    assert client.post(f"/api/projects/{pid}/generate-characters").status_code == 409  # gate holds
    r = client.post(f"/api/projects/{pid}/checkpoints/story_adaptation/approve", json={"note": "good"})
    assert r.status_code == 200 and r.json()["job"]["stage"] == "characters"


def test_scene_stage_resumes_without_redrawing_finished_scenes(client, settings, approved_story):
    pid = _project(client, approved_story)["id"]
    client.post(f"/api/projects/{pid}/run")
    drain(settings)
    client.post(f"/api/projects/{pid}/checkpoints/story_adaptation/approve")
    drain(settings)
    client.post(f"/api/projects/{pid}/checkpoints/character_generation/approve", json={"continue_pipeline": False})
    first = client.post(f"/api/projects/{pid}/generate-scenes").json()["id"]
    drain(settings)
    with session_scope() as db:
        out = db.get(WorkflowJob, first).output
        n = out["scenes"]
        assert out["generated"] == n and out["reused"] == 0
        # simulate a crash that lost one scene's image
        victim = db.query(Scene).filter(Scene.project_id == pid).order_by(Scene.sequence).all()[-1]
        victim.image_asset_id = None
    second = client.post(f"/api/projects/{pid}/generate-scenes").json()["id"]
    drain(settings)
    with session_scope() as db:
        out = db.get(WorkflowJob, second).output
        assert out["generated"] == 1 and out["reused"] == n - 1


def test_regenerating_one_scene_redraws_only_that_scene(client, settings, approved_story):
    pid = _project(client, approved_story)["id"]
    client.post(f"/api/projects/{pid}/run")
    drain(settings)
    client.post(f"/api/projects/{pid}/checkpoints/story_adaptation/approve")
    drain(settings)
    client.post(f"/api/projects/{pid}/checkpoints/character_generation/approve")
    drain(settings)  # runs on to the final_render checkpoint
    assert client.get(f"/api/projects/{pid}").json()["pending_checkpoint"] == "final_render"
    r = client.post(f"/api/projects/{pid}/scenes/scene_002/regenerate")
    assert r.status_code == 200, r.text
    drain(settings)
    with session_scope() as db:
        out = db.get(WorkflowJob, r.json()["id"]).output
        assert out["generated"] == 1 and out["reused"] == out["scenes"] - 1
        assert db.get(Project, pid).status == ProjectStatus.SCENES_READY.value
