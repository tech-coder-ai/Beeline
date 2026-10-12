"""Audio stage: localize the script, then synthesize one WAV per segment per language.

One file per segment (not one long track) means a single mistranslated line
can be fixed and re-voiced without touching the rest of the soundtrack.
"""
from __future__ import annotations

from sqlalchemy import select

from app.config import LanguageCfg, Settings, VoiceCfg
from app.media import fingerprint
from app.persistence.models import AudioSegment, Character, Localization, Project, StoryVersion
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.registry import build_llm, build_tts
from app.schemas.story import CharacterProfile, Script
from app.services.localization.service import glossary_for, localization_fingerprint, source_segments, translate
from app.workflow.context import StageContext, StageFailed


def voice_for(lang: LanguageCfg, speaker: str, char_order: list[str], profiles: dict[str, CharacterProfile]) -> VoiceCfg:
    if speaker == "narrator" or not lang.character_pool:
        return lang.narrator
    prof = profiles.get(speaker)
    if prof and prof.voice_profile.voice_id:
        for v in lang.character_pool:
            if v.voice_id == prof.voice_profile.voice_id:
                return v
    idx = char_order.index(speaker) if speaker in char_order else 0
    return lang.character_pool[idx % len(lang.character_pool)]


def _localize(ctx: StageContext, script: Script, profiles: list[CharacterProfile]) -> list[str]:
    """Create/refresh Localization rows. Returns the languages that are ready for voicing."""
    s: Settings = ctx.settings
    llm = build_llm(s)
    base = source_segments(script)
    glossary = glossary_for(profiles)
    ready: list[str] = []
    codes = s.languages.all_codes()
    for li, code in enumerate(codes):
        ctx.check_cancelled()
        ctx.progress(0.05 + 0.25 * li / len(codes), f"localizing {code}")
        is_source = code == s.languages.source
        fp = localization_fingerprint(base, code, glossary, "source" if is_source else llm.name)
        with ctx.db() as db:
            loc = db.scalars(select(Localization).where(Localization.project_id == ctx.project_id,
                                                        Localization.language == code)).first()
            if loc and loc.fingerprint == fp and loc.status == "ready":
                ready.append(code)
                continue
        if is_source:
            segs, status, by, note = base, "ready", "source", None
        else:
            try:
                segs, warnings = ctx.run_async(translate(s, llm, base, code, glossary))
                status, by, note = "ready", llm.name, "; ".join(warnings) or None
                for w in warnings:
                    ctx.warn(w)
            except ProviderUnavailable:
                segs, status, by = [], "skipped", "none"
                note = "No LLM configured for translation - language skipped. Set models.llm to enable it."
                ctx.warn(f"{code}: {note}")
            except ProviderError as exc:
                if exc.transient:
                    raise
                segs, status, by, note = [], "failed", llm.name, str(exc)[:1000]
                ctx.warn(f"{code}: translation failed: {exc}")
        with ctx.db() as db:
            loc = db.scalars(select(Localization).where(Localization.project_id == ctx.project_id,
                                                        Localization.language == code)).first()
            if loc is None:
                loc = Localization(project_id=ctx.project_id, language=code, status=status, generated_by=by)
                db.add(loc)
            loc.status, loc.segments, loc.glossary, loc.generated_by, loc.note = status, segs, glossary, by, note
            loc.fingerprint = fp if status == "ready" else None
        if status == "ready":
            ready.append(code)
    return ready


def run_audio_stage(ctx: StageContext) -> dict:
    s = ctx.settings
    with ctx.db() as db:
        project = db.get(Project, ctx.project_id)
        script = Script.model_validate(db.get(StoryVersion, project.current_story_version_id).script)
        rows = db.scalars(select(Character).where(Character.project_id == ctx.project_id)
                          .order_by(Character.character_id)).all()
        profiles = {c.character_id: CharacterProfile.model_validate(c.profile) for c in rows}
        char_order = [c.character_id for c in rows]

    ready = _localize(ctx, script, list(profiles.values()))
    if s.languages.source not in ready:
        raise StageFailed("source language could not be prepared")

    stats = {"languages": ready, "generated": 0, "reused": 0, "fallback": 0}
    with ctx.db() as db:
        locs = {l.language: list(l.segments) for l in db.scalars(
            select(Localization).where(Localization.project_id == ctx.project_id, Localization.language.in_(ready)))}
    total = sum(len(v) for v in locs.values())
    done = 0
    for code in ready:
        lang = s.languages.languages[code]
        valid_ids = {seg["segment_id"] for seg in locs[code]}
        with ctx.db() as db:  # drop segments that no longer exist in the script
            for old in db.scalars(select(AudioSegment).where(AudioSegment.project_id == ctx.project_id,
                                                             AudioSegment.language == code)):
                if old.segment_id not in valid_ids:
                    db.delete(old)
        for seg in locs[code]:
            ctx.check_cancelled()
            done += 1
            voice = voice_for(lang, seg["speaker"], char_order, profiles)
            fp = fingerprint("tts", code, seg["text"], voice.model_dump())
            with ctx.db() as db:
                row = db.scalars(select(AudioSegment).where(AudioSegment.project_id == ctx.project_id,
                                                            AudioSegment.language == code,
                                                            AudioSegment.segment_id == seg["segment_id"])).first()
                if row and row.fingerprint == fp and ctx.assets.is_valid(db, row.asset_id):
                    stats["reused"] += 1
                    continue
            ctx.progress(0.3 + 0.7 * done / max(1, total), f"voicing {code} {seg['segment_id']}")
            rel = f"languages/{code}/audio/{seg['segment_id']}.wav"
            used, status, note = voice, "ok", None
            try:
                result = build_tts(s, voice).synthesize(seg["text"], voice, ctx.assets.abs(rel))
            except ProviderUnavailable as exc:
                if not lang.fallback:
                    raise StageFailed(f"{code}: TTS '{voice.provider}' unavailable ({exc}) and no fallback voice configured")
                used, status, note = lang.fallback, "fallback", f"{voice.provider} unavailable: {exc}"
                result = build_tts(s, used).synthesize(seg["text"], used, ctx.assets.abs(rel))
                stats["fallback"] += 1
            with ctx.db() as db:
                asset = ctx.assets.register(db, "audio_segment", rel, provider=used.provider, model=used.voice,
                                            prompt=seg["text"], meta={"language": code, "segment_id": seg["segment_id"]})
                row = db.scalars(select(AudioSegment).where(AudioSegment.project_id == ctx.project_id,
                                                            AudioSegment.language == code,
                                                            AudioSegment.segment_id == seg["segment_id"])).first()
                if row is None:
                    row = AudioSegment(project_id=ctx.project_id, language=code, segment_id=seg["segment_id"],
                                       scene_id=seg["scene_id"], order=seg["order"], speaker=seg["speaker"],
                                       text=seg["text"], voice_id=used.voice_id, tts_provider=used.provider)
                    db.add(row)
                row.scene_id, row.order, row.speaker, row.text = seg["scene_id"], seg["order"], seg["speaker"], seg["text"]
                row.voice_id, row.tts_provider, row.asset_id = used.voice_id, used.provider, asset.id
                row.duration_seconds, row.sample_rate = result.duration_seconds, result.sample_rate
                # fingerprint the voice actually used: a fallback segment is retried with the real
                # voice on the next run (e.g. after you install piper), a real one is reused.
                row.fingerprint = fingerprint("tts", code, seg["text"], used.model_dump())
                row.status, row.note = status, note
            stats["generated"] += 1
    if stats["fallback"]:
        ctx.warn(f"{stats['fallback']} segment(s) used a fallback voice - check the voice registry")
    return stats
