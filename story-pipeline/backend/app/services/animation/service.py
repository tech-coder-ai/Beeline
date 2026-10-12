"""Animate stage (hybrid_animation): turn the key scene stills into short AI motion clips.

Why a separate stage after scene approval: image-to-video is by far the most expensive
step (minutes of GPU per clip), so it only runs on stills a person already approved, and
only for a capped number of scenes. Everything else keeps the cheap Ken Burns treatment.

Which scenes: those the script marked `animate: true` (the LLM is asked to pick the hook,
action and the emotional peak), capped at models.video.max_animated_scenes. If none are
marked, the opening scene (the hook) is animated.
"""
from __future__ import annotations

from sqlalchemy import select

from app.media import fingerprint
from app.persistence.models import Asset, Project, Scene
from app.providers.errors import ProviderError
from app.providers.registry import build_video
from app.providers.video.base import VideoRequest
from app.schemas.story import SceneSpec
from app.workflow.context import StageContext, StageFailed


def select_scenes(specs: list[SceneSpec], limit: int) -> list[str]:
    marked = [s.scene_id for s in sorted(specs, key=lambda s: s.sequence) if s.animate]
    if not marked and specs and limit:
        marked = [min(specs, key=lambda s: s.sequence).scene_id]
    return marked[:limit]


def motion_prompt(spec: SceneSpec) -> str:
    base = spec.motion_prompt or f"subtle natural motion, characters breathe and shift, {spec.camera.movement.replace('_', ' ')}"
    return f"{base}. {spec.visual_prompt[:400]}"


def run_animate_stage(ctx: StageContext) -> dict:
    s = ctx.settings
    vcfg = s.models.video
    with ctx.db() as db:
        project = db.get(Project, ctx.project_id)
        style = project.production_style
        rows = db.scalars(select(Scene).where(Scene.project_id == ctx.project_id).order_by(Scene.sequence)).all()
        specs = {r.scene_id: SceneSpec.model_validate(r.spec) for r in rows}
        chosen = set(select_scenes(list(specs.values()), vcfg.max_animated_scenes)) \
            if style == "hybrid_animation" and vcfg.provider != "none" else set()
        todo = []
        reused = 0
        provider = build_video(s)
        for r in rows:
            if r.scene_id not in chosen:
                r.motion_asset_id, r.motion_status, r.motion_error = None, None, None  # render the still
                continue
            img = db.get(Asset, r.image_asset_id) if r.image_asset_id else None
            if img is None or not ctx.assets.is_valid(db, img.id):
                raise StageFailed(f"{r.scene_id} has no valid still image - run the scenes stage")
            spec = specs[r.scene_id]
            prompt = motion_prompt(spec)
            fp = fingerprint("motion", provider.name, provider.model, img.checksum, prompt, vcfg.negative_prompt,
                             r.seed, vcfg.width, vcfg.height, vcfg.frames, vcfg.fps)
            if r.motion_fingerprint == fp and ctx.assets.is_valid(db, r.motion_asset_id):
                r.motion_status = "animated"
                reused += 1
                continue
            todo.append((r.id, r.scene_id, r.seed, fp, prompt, ctx.assets.path_of(img)))

    if style != "hybrid_animation":
        return {"skipped": "production style is illustrated_narration - every scene uses a camera move"}
    if vcfg.provider == "none":
        ctx.warn("hybrid_animation project but models.video.provider is 'none' - rendering stills only")
        return {"skipped": "no image-to-video model configured"}

    failures: list[tuple[str, ProviderError]] = []
    try:
        for i, (row_id, scene_id, seed, fp, prompt, image_path) in enumerate(todo):
            ctx.check_cancelled()
            ctx.progress(i / max(1, len(todo)), f"animating {scene_id} ({i + 1}/{len(todo)}) with {provider.name}")
            req = VideoRequest(image_path=image_path, prompt=prompt, negative_prompt=vcfg.negative_prompt, seed=seed,
                               width=vcfg.width, height=vcfg.height, frames=vcfg.frames, fps=vcfg.fps)
            try:
                data = provider.generate(req)
            except ProviderError as exc:
                failures.append((scene_id, exc))
                with ctx.db() as db:
                    row = db.get(Scene, row_id)
                    row.motion_status, row.motion_error = "failed", str(exc)[:1000]
                if exc.transient:
                    continue
                break  # a config error (missing node/model) will fail every clip - stop early
            with ctx.db() as db:
                asset = ctx.assets.write_bytes(db, "scene_motion", f"assets/motion/{scene_id}_{seed}.mp4", data,
                                               provider=provider.name, model=provider.model, prompt=prompt, seed=seed,
                                               meta={"scene_id": scene_id, "frames": vcfg.frames, "fps": vcfg.fps})
                row = db.get(Scene, row_id)
                row.motion_asset_id, row.motion_fingerprint = asset.id, fp
                row.motion_status, row.motion_error = "animated", None
    finally:
        if vcfg.free_vram_after_stage:
            provider.free()

    if failures:
        raise ProviderError(f"{len(failures)} clip(s) failed ({', '.join(f for f, _ in failures)}); finished clips are "
                            f"kept: {failures[0][1]}", transient=all(e.transient for _, e in failures))
    return {"animated": sorted(chosen), "generated": len(todo), "reused": reused,
            "seconds_per_clip": round(vcfg.frames / vcfg.fps, 1), "provider": provider.name}
