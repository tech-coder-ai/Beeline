"""Hybrid animation: key scenes get an image-to-video clip; the rest stay stills."""
import shutil

import pytest

from app.media import duration_of, probe
from app.persistence.db import session_scope
from app.persistence.models import Scene, WorkflowJob
from app.schemas.story import Camera, SceneSpec
from app.services.animation.service import select_scenes
from app.services.rendering.ffmpeg_render import render_clip
from app.services.rendering.timeline import TimelineScene
from app.workflow.runner import drain

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _spec(i, animate=False, mood="reflective"):
    return SceneSpec(scene_id=f"scene_{i:03d}", sequence=i, duration_seconds=5, location_id="location_001",
                     visual_prompt="x", mood=mood, animate=animate, camera=Camera())


def test_selection_respects_marks_cap_and_falls_back_to_the_hook():
    specs = [_spec(1), _spec(2, True), _spec(3, True), _spec(4, True)]
    assert select_scenes(specs, 2) == ["scene_002", "scene_003"]
    assert select_scenes([_spec(1), _spec(2)], 3) == ["scene_001"]   # nothing marked -> the hook
    assert select_scenes(specs, 0) == []


@needs_ffmpeg
def test_motion_clip_holds_last_frame_to_cover_narration(settings, tmp_path):
    from app.providers.video.base import VideoRequest
    from app.providers.video.placeholder import PlaceholderVideoProvider
    img = tmp_path / "s.png"
    from PIL import Image
    Image.new("RGB", (448, 256), "#336699").save(img)
    clip = tmp_path / "m.mp4"
    clip.write_bytes(PlaceholderVideoProvider().generate(VideoRequest(img, "p", "", 1, 320, 180, 17, 12)))
    assert abs(duration_of(clip) - 17 / 12) < 0.2
    scene = TimelineScene(scene_id="scene_001", sequence=1, title="t", image_path=str(img), image_checksum="c",
                          start=0, end=4.0, camera_movement="static", motion_path=str(clip), motion_checksum="m")
    out = tmp_path / "out.mp4"
    render_clip(scene, settings.video, out)
    assert abs(duration_of(out) - 4.0) < 0.15        # 1.4 s of motion, then the last frame is held
    v = next(s for s in probe(out)["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (320, 180)


def _to_motion(client, settings, pid):
    client.post(f"/api/projects/{pid}/run")
    drain(settings)
    client.post(f"/api/projects/{pid}/checkpoints/story_adaptation/approve")
    drain(settings)
    client.post(f"/api/projects/{pid}/checkpoints/character_generation/approve")
    drain(settings)  # scenes -> animate -> audio -> render -> qc


@needs_ffmpeg
def test_hybrid_project_animates_key_scenes_end_to_end(client, settings, approved_story):
    v = settings.models.video
    v.provider, v.width, v.height, v.frames, v.fps, v.max_animated_scenes = "placeholder", 320, 180, 17, 12, 2
    pid = client.post("/api/projects", json={"source_id": approved_story["id"],
                                             "production_style": "hybrid_animation"}).json()["id"]
    _to_motion(client, settings, pid)
    p = client.get(f"/api/projects/{pid}").json()
    assert p["pending_checkpoint"] == "final_render", [j["error"] for j in p["jobs"] if j["error"]]
    animated = [s for s in p["scenes"] if s["motion_url"]]
    assert 1 <= len(animated) <= 2 and all(s["motion_status"] == "animated" for s in animated)
    assert animated[0]["sequence"] == 1                     # the hook is always among them
    render_job = next(j for j in p["jobs"] if j["stage"] == "render")
    assert render_job["output"]["animated_scenes"] == len(animated)
    assert next(r for r in p["renders"] if r["language"] == "en")["qc_passed"] is True

    # re-running animate reuses finished clips (they are minutes of GPU each with a real model)
    client.post(f"/api/projects/{pid}/checkpoints/final_render/reject")
    client.post(f"/api/projects/{pid}/stages/animate")
    drain(settings)
    with session_scope() as db:
        job = db.query(WorkflowJob).filter_by(project_id=pid, stage="animate").order_by(WorkflowJob.created_at.desc()).first()
        assert job.output["generated"] == 0 and job.output["reused"] == len(animated)


def test_illustrated_project_skips_animation(client, settings, approved_story):
    settings.models.video.provider = "placeholder"
    pid = client.post("/api/projects", json={"source_id": approved_story["id"]}).json()["id"]
    client.post(f"/api/projects/{pid}/run")
    drain(settings)
    client.post(f"/api/projects/{pid}/checkpoints/story_adaptation/approve")
    drain(settings)
    client.post(f"/api/projects/{pid}/checkpoints/character_generation/approve", json={"continue_pipeline": False})
    client.post(f"/api/projects/{pid}/generate-scenes")
    drain(settings)
    client.post(f"/api/projects/{pid}/stages/animate")
    drain(settings)
    with session_scope() as db:
        job = db.query(WorkflowJob).filter_by(project_id=pid, stage="animate").first()
        assert "skipped" in job.output
        assert all(s.motion_asset_id is None for s in db.query(Scene).filter_by(project_id=pid))
