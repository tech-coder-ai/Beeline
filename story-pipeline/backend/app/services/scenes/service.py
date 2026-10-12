"""Scene stage: one illustration per scene, conditioned on the character reference sheets.

Resumability in practice: each scene has a fingerprint of (provider, model,
prompt, seed, size, reference checksums). Scenes whose fingerprint matches an
intact asset are skipped. If scene 18 of 30 fails, the retry draws scene 18
onward and reuses 1-17.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sqlalchemy import select

from app.media import fingerprint
from app.persistence.models import Asset, Character, Project, Scene, StoryVersion
from app.providers.errors import ProviderError
from app.providers.images.base import ImageRequest
from app.providers.registry import build_image
from app.schemas.story import CharacterProfile, SceneSpec, StoryBible
from app.services.visual_prompts import scene_prompt
from app.workflow.context import StageContext, StageFailed


def run_scenes_stage(ctx: StageContext) -> dict:
    s = ctx.settings
    image = build_image(s)
    w, h = s.models.image.width, s.models.image.height
    with ctx.db() as db:
        project = db.get(Project, ctx.project_id)
        bible = StoryBible.model_validate(db.get(StoryVersion, project.current_story_version_id).bible)
        locations = {l.location_id: l.name for l in bible.locations}
        chars: dict[str, tuple[CharacterProfile, str | None, str | None]] = {}
        for c in db.scalars(select(Character).where(Character.project_id == ctx.project_id)):
            asset = db.get(Asset, c.reference_asset_id) if c.reference_asset_id else None
            chars[c.character_id] = (CharacterProfile.model_validate(c.profile),
                                     str(ctx.assets.path_of(asset)) if asset else None,
                                     asset.checksum if asset else None)
        missing = [cid for cid, (_, path, _) in chars.items() if path is None]
        if missing:
            raise StageFailed(f"characters without reference sheets: {missing} - run the characters stage")
        todo = []
        reused = 0
        for sc in db.scalars(select(Scene).where(Scene.project_id == ctx.project_id).order_by(Scene.sequence)):
            spec = SceneSpec.model_validate(sc.spec)
            cast = [chars[c][0] for c in spec.characters if c in chars]
            refs = [chars[c][1] for c in spec.characters if c in chars]
            ref_sums = [chars[c][2] for c in spec.characters if c in chars]
            prompt = scene_prompt(s.models.image.style, spec.visual_prompt, cast,
                                  locations.get(spec.location_id, ""), spec.camera.shot_type, spec.mood,
                                  spec.continuity_requirements)
            fp = fingerprint("scene", image.name, image.model, prompt, s.models.image.negative_prompt, sc.seed, w, h, ref_sums)
            if sc.fingerprint == fp and ctx.assets.is_valid(db, sc.image_asset_id):
                reused += 1
                continue
            req = ImageRequest(
                kind="scene", prompt=prompt, negative_prompt=s.models.image.negative_prompt, seed=sc.seed,
                width=w, height=h, reference_images=[Path(r) for r in refs if r],
                hints={"title": spec.title, "mood": spec.mood, "location": locations.get(spec.location_id, ""),
                       "shot_type": spec.camera.shot_type, "sequence": spec.sequence,
                       "characters": [{"name": c.name, "palette": c.appearance.palette, "species": c.appearance.species}
                                      for c in cast]})
            todo.append((sc.id, spec.scene_id, sc.seed, fp, prompt, req))

    total = len(todo) + reused
    done = reused
    failures: list[tuple[str, ProviderError]] = []

    def work(item):
        try:
            return item, image.generate(item[5]), None
        except ProviderError as exc:
            return item, None, exc

    with ThreadPoolExecutor(max_workers=s.pipeline.max_parallel_scenes) as pool:
        futures = [pool.submit(work, item) for item in todo]
        for fut in as_completed(futures):
            (row_id, scene_id, seed, fp, prompt, _), png, exc = fut.result()
            if exc is not None:
                failures.append((scene_id, exc))
                with ctx.db() as db:
                    row = db.get(Scene, row_id)
                    row.status, row.error = "failed", str(exc)[:1000]
                continue
            # results are written from this thread only - one writer keeps SQLite happy
            with ctx.db() as db:
                asset = ctx.assets.write_bytes(db, "scene_image", f"assets/scenes/{scene_id}_{seed}.png", png,
                                               provider=image.name, model=image.model, prompt=prompt, seed=seed,
                                               meta={"scene_id": scene_id})
                row = db.get(Scene, row_id)
                row.image_asset_id, row.fingerprint, row.status, row.error = asset.id, fp, "generated", None
            done += 1
            ctx.progress(done / max(1, total), f"illustrated {scene_id} ({done}/{total})")
            ctx.check_cancelled()

    if failures:
        transient = all(e.transient for _, e in failures)
        raise ProviderError(f"{len(failures)} scene image(s) failed ({', '.join(f for f, _ in failures)}); "
                            f"completed scenes are kept: {failures[0][1]}",
                            transient=transient)
    return {"scenes": total, "generated": len(todo), "reused": reused}
