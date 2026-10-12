"""Automated QC. Deterministic, measurable checks on the actual output files.

Each check returns pass / warn / fail with a human-readable detail. A single
'fail' blocks publishing for that language. Editorial judgement (is the story
any good?) is the job of the final_render human checkpoint, not this module.
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from app.config import Settings
from app.media import probe, run_ffmpeg
from app.persistence.models import Asset, AudioSegment, Project, RenderJob, StorySource
from app.services.publishing.metadata import DISCLOSURE
from app.services.rendering.timeline import parse_srt
from app.services.rights.service import RightsError, assert_usable
from app.workflow.context import StageContext, StageFailed


def _check(name: str, ok: bool, detail: str, *, warn_only: bool = False) -> dict:
    return {"name": name, "status": "pass" if ok else ("warn" if warn_only else "fail"), "detail": detail}


def check_video(path: Path, settings: Settings, expected_duration: float) -> list[dict]:
    v, q = settings.video, settings.quality
    info = probe(path)
    vs = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    aus = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    subs = [s for s in info["streams"] if s["codec_type"] == "subtitle"]
    out = []
    if vs is None:
        return [_check("video_stream", False, "no video stream")]
    num, den = (int(x) for x in vs.get("avg_frame_rate", "0/1").split("/"))
    fps = num / den if den else 0
    out.append(_check("resolution", (vs["width"], vs["height"]) == (v.width, v.height),
                      f"{vs['width']}x{vs['height']} (expected {v.width}x{v.height})"))
    out.append(_check("frame_rate", abs(fps - v.fps) < 0.5, f"{fps:.2f} fps (expected {v.fps})"))
    out.append(_check("video_codec", vs["codec_name"] == "h264" and vs.get("pix_fmt") == "yuv420p",
                      f"{vs['codec_name']} / {vs.get('pix_fmt')}"))
    dur = float(info["format"]["duration"])
    out.append(_check("duration", abs(dur - expected_duration) <= q.duration_tolerance_seconds,
                      f"{dur:.2f}s (timeline {expected_duration:.2f}s)"))
    out.append(_check("audio_stream", aus is not None and aus["codec_name"] == "aac",
                      f"{aus['codec_name']} {aus.get('sample_rate')} Hz" if aus else "missing"))
    out.append(_check("subtitle_track", bool(subs), f"{len(subs)} soft subtitle track(s)", warn_only=True))
    if aus is None:
        return out

    log = run_ffmpeg(["-i", str(path), "-af", f"volumedetect,silencedetect=noise=-50dB:d={q.max_silence_seconds}",
                      "-vf", f"blackdetect=d={q.max_black_seconds}:pix_th=0.10", "-f", "null", "-"])
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", log)
    peak = re.search(r"max_volume: (-?[\d.]+) dB", log)
    mean_db = float(mean.group(1)) if mean else -91.0
    peak_db = float(peak.group(1)) if peak else -91.0
    out.append(_check("audible_narration", mean_db > -60, f"mean volume {mean_db:.1f} dB"))
    out.append(_check("no_clipping", peak_db < q.clipping_threshold_db, f"peak {peak_db:.1f} dBFS"))
    silences = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", log)]
    out.append(_check("long_silences", not silences,
                      f"{len(silences)} silence(s) > {q.max_silence_seconds}s" if silences else "none", warn_only=True))
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)
    out.append(_check("black_frames", not blacks,
                      f"black from {', '.join(f'{float(a):.1f}-{float(b):.1f}s' for a, b in blacks)}" if blacks else "none"))
    return out


def check_subtitles(path: Path, duration: float, expected_cues: int) -> list[dict]:
    cues = parse_srt(path.read_text(encoding="utf-8"))
    overlaps = sum(1 for a, b in zip(cues, cues[1:]) if b[0] < a[1] - 0.01)
    outside = sum(1 for s, e, _ in cues if s < 0 or e > duration + 0.05 or e <= s)
    empty = sum(1 for *_, t in cues if not t.strip())
    fast = sum(1 for s, e, t in cues if e > s and len(t) / (e - s) > 25)  # chars/sec readability
    return [
        _check("subtitle_count", len(cues) == expected_cues and cues != [], f"{len(cues)} cues (expected {expected_cues})"),
        _check("subtitle_timing", overlaps == 0 and outside == 0 and empty == 0,
               f"{overlaps} overlapping, {outside} out of range, {empty} empty"),
        _check("subtitle_reading_speed", fast == 0, f"{fast} cue(s) faster than 25 chars/s", warn_only=True),
    ]


def check_thumbnail(path: Path, settings: Settings) -> list[dict]:
    q = settings.quality
    with Image.open(path) as im:
        size_ok = im.size == (q.thumbnail_width, q.thumbnail_height)
        dims = f"{im.size[0]}x{im.size[1]}"
    kb = path.stat().st_size / 1024
    return [_check("thumbnail", size_ok and kb < 2048, f"{dims}, {kb:.0f} KB (YouTube max 2 MB)")]


def check_metadata(meta: dict, source: StorySource, settings: Settings) -> list[dict]:
    title, desc, tags = meta.get("title", ""), meta.get("description", ""), meta.get("tags", [])
    out = [
        _check("title", 0 < len(title) <= 100 and "<" not in title and ">" not in title, f"{len(title)} chars"),
        _check("description", 0 < len(desc) <= 5000 and "<" not in desc and ">" not in desc, f"{len(desc)} chars"),
        _check("tags", sum(len(t) for t in tags) <= 500, f"{len(tags)} tags", warn_only=True),
    ]
    if "attribution_required" in (source.allowed_uses or []):
        out.append(_check("attribution", bool(source.attribution) and source.attribution in desc,
                          "attribution present" if source.attribution and source.attribution in desc else "attribution missing"))
    if settings.publishing.synthetic_content_disclosure:
        out.append(_check("ai_disclosure", DISCLOSURE in desc, "disclosure present" if DISCLOSURE in desc else "missing"))
    return out


def run_qc_stage(ctx: StageContext) -> dict:
    s = ctx.settings
    with ctx.db() as db:
        project = db.get(Project, ctx.project_id)
        source = db.get(StorySource, project.source_id)
        db.expunge(source)
        jobs = [(rj.id, rj.language) for rj in db.scalars(select(RenderJob).where(
            RenderJob.project_id == ctx.project_id, RenderJob.status == "rendered"))]
    if not jobs:
        raise StageFailed("nothing rendered to check")
    try:
        assert_usable(source)
        rights = _check("rights", True, f"{source.license_type}, approved by {source.rights_decided_by}")
    except RightsError as exc:
        rights = _check("rights", False, str(exc))

    summary: dict[str, dict] = {}
    for i, (rj_id, code) in enumerate(jobs):
        ctx.check_cancelled()
        ctx.progress(i / len(jobs), f"checking {code}")
        with ctx.db() as db:
            rj = db.get(RenderJob, rj_id)
            video = ctx.assets.path_of(db.get(Asset, rj.video_asset_id))
            srt = ctx.assets.path_of(db.get(Asset, rj.subtitle_asset_id))
            thumb = ctx.assets.path_of(db.get(Asset, rj.thumbnail_asset_id))
            duration, n_cues, meta = rj.timeline["duration"], len(rj.timeline["subtitles"]), dict(rj.metadata_)
            fallbacks = db.scalars(select(AudioSegment).where(AudioSegment.project_id == ctx.project_id,
                                                              AudioSegment.language == code,
                                                              AudioSegment.status == "fallback")).all()
        checks = [rights, *check_video(video, s, duration), *check_subtitles(srt, duration, n_cues),
                  *check_thumbnail(thumb, s), *check_metadata(meta, source, s),
                  _check("voices", not fallbacks, f"{len(fallbacks)} segment(s) used a fallback voice" if fallbacks
                         else "all segments use their configured voice", warn_only=True)]
        passed = not any(c["status"] == "fail" for c in checks)
        with ctx.db() as db:
            rj = db.get(RenderJob, rj_id)
            rj.qc, rj.qc_passed = {"checks": checks, "passed": passed}, passed
        summary[code] = {"passed": passed, "failed": [c["name"] for c in checks if c["status"] == "fail"],
                         "warnings": [c["name"] for c in checks if c["status"] == "warn"]}
    failed = {k: v["failed"] for k, v in summary.items() if not v["passed"]}
    if failed:
        raise StageFailed(f"QC failed: {failed}. See the QC report, fix, re-render and rerun QC.")
    return {"languages": summary}
