"""Localized YouTube metadata: LLM-written title/description/tags + deterministic chapters, attribution, disclosure.

The parts that carry legal or policy weight (attribution, AI disclosure,
chapters) are appended by code, never left to the model.
"""
from __future__ import annotations

import re

from app.config import Settings
from app.prompts import render_prompt
from app.providers.errors import ProviderError
from app.providers.registry import build_llm
from app.persistence.models import StorySource
from app.providers.llm.base import generate_model
from app.schemas.story import StoryBible, VideoMetadata
from app.services.rendering.timeline import Timeline, chapters, fmt_chapter

DISCLOSURE = "This video uses AI-generated narration and illustrations."


def _clean(text: str) -> str:
    return re.sub(r"[<>]", "", text).strip()  # YouTube rejects angle brackets in titles/descriptions


async def _llm_metadata(settings: Settings, bible: StoryBible, language: str) -> VideoMetadata:
    llm = build_llm(settings)
    prompt = render_prompt(settings, "metadata", language=settings.languages.languages[language].name,
                           title=bible.title, synopsis=bible.synopsis, genre=bible.genre, audience=bible.audience)
    return await generate_model(llm, prompt, VideoMetadata, repair_attempts=settings.models.llm.json_repair_attempts)


def build_metadata(settings: Settings, bible: StoryBible, source: StorySource, timeline: Timeline, language: str,
                   run_async) -> dict:
    generated_by = "template"
    try:
        meta = run_async(_llm_metadata(settings, bible, language))
        generated_by = build_llm(settings).name
    except ProviderError:
        genre = f" | {bible.genre.title()}" if bible.genre else ""
        meta = VideoMetadata(title=f"{bible.title}{genre} | Illustrated Story"[:100],
                             description=f"{bible.synopsis}\n\n{('Moral: ' + bible.moral) if bible.moral else ''}".strip(),
                             tags=[t for t in {bible.genre, "story", "illustrated story", "narrated story",
                                               bible.title.lower()} if t])
    parts = [_clean(meta.description)]
    ch = chapters(timeline.scenes)
    if ch:
        parts.append("Chapters:\n" + "\n".join(f"{fmt_chapter(t)} {_clean(title)}" for t, title in ch))
    src_line = f"Based on: {source.attribution or source.title}"
    if source.source_url:
        src_line += f"\nSource: {source.source_url}"
    if source.license_type:
        src_line += f"\nLicense: {source.license_type}"
    parts.append(src_line)
    if settings.publishing.synthetic_content_disclosure:
        parts.append(DISCLOSURE + (f" {settings.publishing.channel_attribution}" if settings.publishing.channel_attribution else ""))
    tags, total = [], 0
    for t in meta.tags:
        t = _clean(t)[:60]
        if t and total + len(t) <= 450:
            tags.append(t)
            total += len(t)
    return {
        "title": _clean(meta.title)[:100] or bible.title[:100],
        "description": "\n\n".join(p for p in parts if p)[:5000],
        "tags": tags,
        "language": language,
        "category_id": settings.publishing.category_id,
        "visibility": settings.publishing.default_visibility,
        "synthetic": settings.publishing.synthetic_content_disclosure,
        "chapters": [{"start": t, "title": title} for t, title in ch],
        "generated_by": generated_by,
    }
