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
from app.llm.trace import complete_json_traced
from app.models.semantic import Abbreviation, GlossaryTerm, Synonym
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
        abbrev_rows = (
            await db.execute(select(Abbreviation).where(Abbreviation.status == "approved"))
        ).scalars().all()

        lines = [f"{syn} => {term}" for syn, term in synonym_rows[:200]]
        lines.extend(
            f"{a.abbreviation} => entity {a.entity}, value {a.value}" for a in abbrev_rows[:200]
        )
        hint_block = "\n".join(lines)

        try:
            user_message = f"Synonym and abbreviation mappings:\n{hint_block or '(none)'}\n\nUser message:\n{ctx.prompt}"
            parsed, _ = await complete_json_traced(ctx, "refine", prompts.REFINER_SYSTEM, user_message)
            refined = (parsed.get("refined") or parsed.get("refined_prompt") or "").strip()
            if refined and refined.lower() != ctx.prompt.strip().lower():
                ctx.refined_prompt = refined
                ctx.refinement_notes = [str(n) for n in parsed.get("notes", [])][:5]
        except Exception as exc:  # noqa: BLE001 - refinement is best-effort
            logger.debug("refinement skipped: %s", exc)
