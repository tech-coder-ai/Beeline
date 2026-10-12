"""Character stage: one reference sheet per character, generated before any scene.

The approved sheet becomes the visual source of truth: scene generation is
conditioned on it, and its checksum is part of every scene fingerprint, so
regenerating a character automatically invalidates the scenes it appears in.
"""
from __future__ import annotations

from sqlalchemy import select

from app.media import fingerprint
from app.persistence.models import Character
from app.providers.errors import ProviderError
from app.providers.images.base import ImageRequest
from app.providers.registry import build_image
from app.schemas.story import CharacterProfile
from app.services.visual_prompts import character_prompt
from app.workflow.context import StageContext


def run_characters_stage(ctx: StageContext) -> dict:
    s = ctx.settings
    image = build_image(s)
    with ctx.db() as db:
        chars = [(c.id, c.character_id, CharacterProfile.model_validate(c.profile), c.seed)
                 for c in db.scalars(select(Character).where(Character.project_id == ctx.project_id)
                                     .order_by(Character.character_id))]
    generated = reused = 0
    for i, (row_id, char_id, prof, seed) in enumerate(chars):
        ctx.check_cancelled()
        prompt = character_prompt(s.models.image.style, prof)
        w, h = s.models.image.width, s.models.image.height
        fp = fingerprint("character_sheet", image.name, image.model, prompt, s.models.image.negative_prompt, seed, w, h)
        with ctx.db() as db:
            row = db.get(Character, row_id)
            if row.fingerprint == fp and ctx.assets.is_valid(db, row.reference_asset_id):
                reused += 1
                continue
        ctx.progress(i / max(1, len(chars)), f"drawing {prof.name}")
        req = ImageRequest(kind="character_sheet", prompt=prompt, negative_prompt=s.models.image.negative_prompt,
                           seed=seed, width=w, height=h,
                           hints={"name": prof.name, "role": prof.role, "species": prof.appearance.species,
                                  "palette": prof.appearance.palette,
                                  "features": [f for f in [prof.appearance.hair, prof.appearance.clothing_style,
                                                           *prof.appearance.distinctive_features] if f]})
        try:
            png = image.generate(req)
        except ProviderError:
            raise
        with ctx.db() as db:
            asset = ctx.assets.write_bytes(db, "character_sheet", f"assets/characters/{char_id}_{seed}.png", png,
                                           provider=image.name, model=image.model, prompt=prompt, seed=seed,
                                           meta={"character_id": char_id})
            row = db.get(Character, row_id)
            row.reference_asset_id, row.fingerprint, row.approved = asset.id, fp, False
        generated += 1
    return {"characters": len(chars), "generated": generated, "reused": reused}
