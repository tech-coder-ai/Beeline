"""Query Refinement stage (optional, config-driven).

Fixes spelling, expands abbreviations, resolves business synonyms to canonical
terms before intent analysis. Transparent: notes are surfaced in the response.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm import prompts
from app.llm.providers import get_llm
from app.models.semantic import GlossaryTerm, Synonym
from app.pipeline.types import PipelineContext

logger = get_logger(__name__)


class QueryRefiner:
    async def run(self, ctx: PipelineContext, db: AsyncSession) -> None:
        settings = get_settings()
        if not settings.get("pipeline.query_refinement.enabled", True):
            return

        synonym_rows = (
            await db.execute(
                select(Synonym.synonym, GlossaryTerm.term)
                .join(GlossaryTerm, Synonym.term_id == GlossaryTerm.id)
                .where(GlossaryTerm.status == "approved")
            )
        ).all()
        glossary_hint = "\n".join(f"{syn} => {term}" for syn, term in synonym_rows[:200])

        try:
            llm = get_llm()
            parsed, result = await llm.complete_json(
                prompts.REFINER_SYSTEM,
                f"Glossary synonym mappings:\n{glossary_hint or '(none)'}\n\nUser message:\n{ctx.prompt}",
            )
            ctx.record_llm("refine", result)
            refined = (parsed.get("refined") or "").strip()
            if refined and refined.lower() != ctx.prompt.strip().lower():
                ctx.refined_prompt = refined
                ctx.refinement_notes = [str(n) for n in parsed.get("notes", [])][:5]
        except Exception as exc:  # noqa: BLE001 - refinement is best-effort
            logger.debug("refinement skipped: %s", exc)
