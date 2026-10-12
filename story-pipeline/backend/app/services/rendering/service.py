"""Render stage: timeline -> clips -> narration -> final MP4 + subtitles + thumbnail + metadata, per language."""
from __future__ import annotations

import json
import time
from pathlib import Path

from sqlalchemy import select

from app.media import fingerprint, have_ffmpeg
from app.persistence.models import (
    Asset,
    AudioSegment,
    Character,
    Localization,
    Project,
    RenderJob,
    Scene,
    StorySource,
    StoryVersion,
)
from app.schemas.story import SceneSpec, StoryBible
from app.services.publishing.metadata import build_metadata
from app.services.rendering import ffmpeg_render as fr
from app.services.rendering.thumbnail import make_thumbnail
from app.services.rendering.timeline import build_timeline, to_srt, to_vtt
from app.workflow.context import StageContext, StageFailed


def run_render_stage(ctx: StageContext) -> dict:
    if not have_ffmpeg():
        raise StageFailed("ffmpeg/ffprobe not found on PATH")
    s = ctx.settings
    v = s.video
    with ctx.db() as db:
        project = db.get(Project, ctx.project_id)
        bible = StoryBible.model_validate(db.get(StoryVersion, project.current_story_version_id).bible)
        source = db.get(StorySource, project.source_id)
        db.expunge(source)
        names = {c.character_id: c.name for c in db.scalars(select(Character).where(Character.project_id == project.id))}
        scenes = []
        for sc in db.scalars(select(Scene).where(Scene.project_id == project.id).order_by(Scene.sequence)):
            asset = db.get(Asset, sc.image_asset_id) if sc.image_asset_id else None
            if asset is None or not ctx.assets.is_valid(db, asset.id):
                raise StageFailed(f"{sc.scene_id} has no valid image - run the scenes stage")
            spec = SceneSpec.model_validate(sc.spec)
            motion = db.get(Asset, sc.motion_asset_id) if sc.motion_asset_id else None
            if motion is not None and not ctx.assets.is_valid(db, motion.id):
                motion = None
                ctx.warn(f"{sc.scene_id}: motion clip missing on disk - using the still")
            scenes.append({"scene_id": sc.scene_id, "sequence": sc.sequence, "title": spec.title,
                           "image_path": str(ctx.assets.path_of(asset)), "image_checksum": asset.checksum,
                           "motion_path": str(ctx.assets.path_of(motion)) if motion else None,
                           "motion_checksum": motion.checksum if motion else None,
                           "planned": spec.duration_seconds, "camera_movement": spec.camera.movement,
                           "n_chars": len(spec.characters)})
        ready = [l.language for l in db.scalars(select(Localization).where(
            Localization.project_id == project.id, Localization.status == "ready"))]
    order = [c for c in s.languages.all_codes() if c in ready]
    if not order:
        raise StageFailed("no language is ready for rendering - run the audio stage")

    music = s.path(v.music_path) if v.music_path else None
    if music and not music.exists():
        ctx.warn(f"music file {music} not found - rendering without music")
        music = None

    results: dict[str, str] = {}
    clips_dir = ctx.assets.abs("render/clips/.keep").parent
    for li, code in enumerate(order):
        ctx.check_cancelled()
        with ctx.db() as db:
            segs = []
            for a in db.scalars(select(AudioSegment).where(AudioSegment.project_id == ctx.project_id,
                                                           AudioSegment.language == code).order_by(AudioSegment.order)):
                asset = db.get(Asset, a.asset_id) if a.asset_id else None
                if asset is None:
                    raise StageFailed(f"{code}/{a.segment_id} has no audio - rerun the audio stage")
                segs.append({"segment_id": a.segment_id, "scene_id": a.scene_id, "order": a.order,
                             "speaker": a.speaker, "text": a.text, "audio_path": str(ctx.assets.path_of(asset)),
                             "duration": a.duration_seconds, "checksum": asset.checksum})
        timeline = build_timeline(language=code, width=v.width, height=v.height, fps=v.fps, scenes=scenes,
                                  segments=segs, names=names, padding=v.scene_padding_seconds,
                                  gap=v.segment_gap_seconds, min_scene=s.pipeline.min_scene_seconds)
        fp = fingerprint("render-v1", timeline.to_dict(), [x["checksum"] for x in segs], v.model_dump(),
                         str(music) if music else None)
        with ctx.db() as db:
            rj = db.scalars(select(RenderJob).where(RenderJob.project_id == ctx.project_id,
                                                    RenderJob.language == code)).first()
            if rj and rj.fingerprint == fp and rj.status == "rendered" and ctx.assets.is_valid(db, rj.video_asset_id):
                results[code] = "reused"
                continue

        started = time.monotonic()
        base = f"languages/{code}"
        clip_paths = []
        for si, sc in enumerate(timeline.scenes):
            ctx.check_cancelled()
            ctx.progress((li + si / len(timeline.scenes) * 0.7) / len(order), f"{code}: rendering {sc.scene_id}")
            cp = clips_dir / f"{fr.clip_fingerprint(sc, v)}.mp4"
            if not cp.exists():  # identical clips are shared across languages and reruns
                tmp = cp.with_suffix(".part.mp4")
                fr.render_clip(sc, v, tmp)
                tmp.replace(cp)
            clip_paths.append(cp)
        ctx.progress((li + 0.75) / len(order), f"{code}: mixing audio")
        narration = ctx.assets.abs(f"{base}/narration.wav")
        fr.render_narration(timeline, narration)
        srt_rel, vtt_rel = f"{base}/subtitles.srt", f"{base}/subtitles.vtt"
        ctx.assets.abs(srt_rel).write_text(to_srt(timeline.subtitles), encoding="utf-8")
        ctx.assets.abs(vtt_rel).write_text(to_vtt(timeline.subtitles), encoding="utf-8")
        ctx.progress((li + 0.85) / len(order), f"{code}: final encode")
        video_rel = f"{base}/final.mp4"
        tmp_video = ctx.assets.abs(f"{base}/final.part.mp4")
        fr.render_final(timeline, clip_paths, narration, ctx.assets.abs(srt_rel), v, tmp_video, music=music,
                        workdir=ctx.assets.abs(f"{base}/.work/x").parent)
        tmp_video.replace(ctx.assets.abs(video_rel))
        narration.unlink(missing_ok=True)  # intermediate; the per-segment WAVs remain the source of truth

        metadata = build_metadata(s, bible, source, timeline, code, ctx.run_async)
        hero = max(scenes, key=lambda x: (x["n_chars"], -x["sequence"]))
        thumb = make_thumbnail(Path(hero["image_path"]), metadata["title"],
                               s.quality.thumbnail_width, s.quality.thumbnail_height)
        with ctx.db() as db:
            video_asset = ctx.assets.register(db, "video", video_rel, provider="ffmpeg",
                                              meta={"language": code, "duration": timeline.duration})
            srt_asset = ctx.assets.register(db, "subtitles", srt_rel, meta={"language": code, "format": "srt"})
            ctx.assets.register(db, "subtitles", vtt_rel, meta={"language": code, "format": "vtt"})
            thumb_asset = ctx.assets.write_bytes(db, "thumbnail", f"{base}/thumbnail.jpg", thumb,
                                                 meta={"language": code})
            ctx.assets.write_bytes(db, "timeline", f"{base}/timeline.json",
                                   json.dumps(timeline.to_dict(), indent=1, ensure_ascii=False).encode(),
                                   meta={"language": code})
            ctx.assets.write_bytes(db, "metadata", f"metadata/{code}.json",
                                   json.dumps(metadata, indent=2, ensure_ascii=False).encode(), meta={"language": code})
            rj = db.scalars(select(RenderJob).where(RenderJob.project_id == ctx.project_id,
                                                    RenderJob.language == code)).first()
            if rj is None:
                rj = RenderJob(project_id=ctx.project_id, language=code)
                db.add(rj)
            rj.timeline, rj.metadata_, rj.fingerprint, rj.status = timeline.to_dict(), metadata, fp, "rendered"
            rj.video_asset_id, rj.subtitle_asset_id, rj.thumbnail_asset_id = video_asset.id, srt_asset.id, thumb_asset.id
            rj.qc, rj.qc_passed = {}, None  # new render -> QC must run again
            rj.render_seconds = round(time.monotonic() - started, 1)
        results[code] = f"rendered in {time.monotonic() - started:.0f}s ({timeline.duration:.0f}s video)"

    with ctx.db() as db:  # languages no longer ready are not publishable
        for rj in db.scalars(select(RenderJob).where(RenderJob.project_id == ctx.project_id)):
            if rj.language not in order:
                rj.status, rj.qc_passed = "skipped", None
    return {"languages": results, "animated_scenes": sum(1 for x in scenes if x["motion_path"])}
