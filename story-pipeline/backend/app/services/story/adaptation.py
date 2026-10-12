"""Script stage: source text -> story bible + character registry + scene specification.

Flow:
  1. LLM call #1: StoryAnalysis (bible + characters), schema-constrained, Pydantic-validated.
  2. LLM call #2: Script (scenes), given the bible.
  3. Deterministic checks. Errors -> one repair round with the issues fed back.
  4. Still failing, or no LLM -> deterministic heuristic, but ONLY if the license allows verbatim use.
  5. Persist as a new immutable StoryVersion; upsert Character/Scene rows (keeping seeds + assets
     so unchanged scenes are not regenerated downstream).
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select

from app.persistence.models import Character, Project, Scene, StorySource, StoryVersion
from app.prompts import render_prompt
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.llm.base import generate_model
from app.providers.registry import build_llm
from app.schemas.story import Issue, Script, StoryAnalysis
from app.services.rights.service import assert_usable, requires_transformation
from app.services.story import heuristic
from app.services.story.checks import check_script, has_errors
from app.workflow.context import StageContext, StageFailed

SYSTEM = "You are a careful story-adaptation assistant. Answer with JSON only."


def _seed(project_id: str, key: str) -> int:
    return int(hashlib.sha256(f"{project_id}:{key}".encode()).hexdigest()[:8], 16) % 2_000_000_000


async def _llm_adapt(ctx: StageContext, src: StorySource) -> tuple[StoryAnalysis, Script, list[Issue], str]:
    s = ctx.settings
    llm = build_llm(s)
    p = s.pipeline
    transform = requires_transformation(src)
    rights_note = ("The license REQUIRES an original adaptation: do not reuse sentences from the source."
                   if transform else "The source is cleared for close adaptation.")
    analysis = await generate_model(llm, render_prompt(
        s, "story_analysis", title=src.title, author=src.author or "unknown", rights_note=rights_note,
        source_text=src.text[: s.models.llm.max_source_chars]), StoryAnalysis, system_prompt=SYSTEM,
        repair_attempts=s.models.llm.json_repair_attempts)
    ctx.progress(0.45, "story bible ready; writing scenes")
    originality = ("Write ORIGINAL narration and dialogue in your own words; never copy source sentences."
                   if transform else "You may keep memorable lines from the source where they work well.")
    repair_note = ""
    script: Script | None = None
    issues: list[Issue] = []
    for _ in range(2):  # first draft + one repair round driven by deterministic checks
        script = await generate_model(llm, render_prompt(
            s, "script", target_scenes=p.target_scene_count, min_seconds=p.min_scene_seconds,
            max_seconds=p.max_scene_seconds, originality_rule=originality,
            bible_json=analysis.bible.model_dump_json(indent=1),
            characters_json=json.dumps([c.model_dump() for c in analysis.characters], indent=1),
            repair_note=repair_note), Script, system_prompt=SYSTEM,
            repair_attempts=s.models.llm.json_repair_attempts)
        issues = check_script(analysis, script, source_text=src.text, min_s=p.min_scene_seconds,
                              max_s=p.max_scene_seconds, require_transformation=transform,
                              max_similarity=s.quality.max_source_similarity)
        if not has_errors(issues):
            break
        repair_note = "\nFIX THESE PROBLEMS FROM YOUR LAST DRAFT:\n" + "\n".join(
            f"- [{i.code}] {i.scene_id or ''} {i.message}" for i in issues if i.severity == "error")
    assert script is not None
    return analysis, script, issues, llm.name


def run_script_stage(ctx: StageContext) -> dict:
    s = ctx.settings
    with ctx.db() as db:
        project = db.get(Project, ctx.project_id)
        src = db.get(StorySource, project.source_id)
        assert_usable(src)
        db.expunge(src)
    ctx.progress(0.05, "analysing story")

    analysis = script = None
    issues: list[Issue] = []
    generated_by = ""
    try:
        analysis, script, issues, generated_by = ctx.run_async(_llm_adapt(ctx, src))
        if has_errors(issues):
            ctx.warn("LLM script still had errors after repair: " + "; ".join(i.message for i in issues if i.severity == "error"))
            analysis = script = None
    except ProviderUnavailable:
        pass  # offline mode
    except ProviderError as exc:
        if exc.transient:
            raise  # let the engine retry (e.g. Ollama restarting)
        ctx.warn(f"LLM adaptation failed: {exc}")

    if analysis is None or script is None:
        if requires_transformation(src):
            raise StageFailed("No valid LLM adaptation, and this source's license requires an original "
                              "adaptation, so the verbatim heuristic fallback is not allowed. "
                              "Configure an LLM (models.llm) and retry.")
        p = s.pipeline
        analysis, script = heuristic.adapt(src.title, src.author, src.text, target_scenes=p.target_scene_count,
                                           min_s=p.min_scene_seconds, max_s=p.max_scene_seconds,
                                           style=s.models.image.style)
        issues = check_script(analysis, script, source_text=src.text, min_s=p.min_scene_seconds,
                              max_s=p.max_scene_seconds, require_transformation=False,
                              max_similarity=s.quality.max_source_similarity)
        generated_by = "heuristic"
        if has_errors(issues):
            raise StageFailed("heuristic script failed checks: " + "; ".join(i.message for i in issues))

    ctx.check_cancelled()
    ctx.progress(0.85, "saving story version")
    with ctx.db() as db:
        project = db.get(Project, ctx.project_id)
        prev = db.scalars(select(StoryVersion).where(StoryVersion.project_id == project.id)
                          .order_by(StoryVersion.version.desc())).first()
        sv = StoryVersion(project_id=project.id, version=(prev.version + 1) if prev else 1,
                          bible=analysis.bible.model_dump(), script=script.model_dump(),
                          issues=[i.model_dump() for i in issues], generated_by=generated_by)
        db.add(sv)
        db.flush()
        project.current_story_version_id = sv.id

        existing_c = {c.character_id: c for c in db.scalars(select(Character).where(Character.project_id == project.id))}
        keep = set()
        for prof in analysis.characters:
            keep.add(prof.character_id)
            row = existing_c.get(prof.character_id)
            if row is None:
                db.add(Character(project_id=project.id, character_id=prof.character_id, name=prof.name,
                                 profile=prof.model_dump(), seed=_seed(project.id, prof.character_id)))
            else:
                row.name, row.profile, row.approved = prof.name, prof.model_dump(), False
        for cid, row in existing_c.items():
            if cid not in keep:
                db.delete(row)

        existing_s = {x.scene_id: x for x in db.scalars(select(Scene).where(Scene.project_id == project.id))}
        keep = set()
        for spec in script.scenes:
            keep.add(spec.scene_id)
            row = existing_s.get(spec.scene_id)
            if row is None:
                db.add(Scene(project_id=project.id, scene_id=spec.scene_id, sequence=spec.sequence,
                             spec=spec.model_dump(), seed=_seed(project.id, spec.scene_id)))
            else:
                row.sequence, row.spec, row.status = spec.sequence, spec.model_dump(), "pending"
        for sid, row in existing_s.items():
            if sid not in keep:
                db.delete(row)

        store = ctx.assets
        for name, payload in (("story_bible", analysis.bible.model_dump()),
                              ("characters", [c.model_dump() for c in analysis.characters]),
                              ("scenes", [sc.model_dump() for sc in script.scenes]),
                              (f"script_{s.languages.source}", script.model_dump())):
            store.write_bytes(db, "story_json", f"story/v{sv.version}/{name}.json",
                              json.dumps(payload, indent=2, ensure_ascii=False).encode(),
                              provider=generated_by, meta={"story_version": sv.version})
    return {"story_version": sv.version, "generated_by": generated_by, "scenes": len(script.scenes),
            "characters": len(analysis.characters), "issues": len(issues)}
