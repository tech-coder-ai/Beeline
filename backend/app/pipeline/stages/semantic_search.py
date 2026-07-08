"""Semantic Search stage.

Before any SQL generation, search the enriched catalog, glossary, metrics and
the SQL knowledge library. Scoring uses fuzzy token matching over names,
descriptions, tags, synonyms and sample values - dependency-light and fast.
"""
from __future__ import annotations

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.catalog import CatalogDatabase, CatalogTable
from app.models.queries import QueryLibraryEntry
from app.models.semantic import BusinessMetric, GlossaryTerm, Synonym
from app.pipeline.types import LibraryMatch, PipelineContext, ResolvedTable

MAX_TABLES = 6
MAX_COLUMNS_PER_TABLE = 40


def _tokens(text: str) -> set[str]:
    return {t for t in "".join(c if c.isalnum() else " " for c in text.lower()).split() if len(t) > 2}


def _score(question: str, question_tokens: set[str], candidate_text: str) -> float:
    """Blend token overlap with fuzzy partial matching."""
    cand_tokens = _tokens(candidate_text)
    if not cand_tokens or not question_tokens:
        return 0.0
    overlap = len(question_tokens & cand_tokens) / len(question_tokens)
    fuzzy = fuzz.partial_token_set_ratio(question.lower(), candidate_text.lower()) / 100.0
    return 0.6 * overlap + 0.4 * fuzzy


class SemanticSearch:
    async def run(self, ctx: PipelineContext, db: AsyncSession) -> None:
        question = ctx.effective_prompt
        intent = ctx.intent
        search_text = question
        if intent:
            search_text += " " + " ".join(intent.metrics + intent.dimensions + [intent.subject])
        q_tokens = _tokens(search_text)

        await self._resolve_glossary(ctx, db, question, q_tokens)
        await self._resolve_metrics(ctx, db, search_text, q_tokens)
        await self._resolve_tables(ctx, db, search_text, q_tokens)
        await self._search_library(ctx, db, question)

        ctx.confidence["metadata"] = (
            max((t.score for t in ctx.resolved_tables), default=0.0)
            if ctx.resolved_tables else 0.0
        )

    async def _resolve_glossary(self, ctx, db, question: str, q_tokens: set[str]) -> None:
        terms = (
            await db.execute(
                select(GlossaryTerm)
                .options(selectinload(GlossaryTerm.synonyms))
                .where(GlossaryTerm.status == "approved")
            )
        ).scalars().all()
        scored = []
        for term in terms:
            candidate = " ".join(
                [term.term, term.definition or ""] + [s.synonym for s in term.synonyms]
            )
            score = _score(question, q_tokens, candidate)
            if score > 0.25:
                scored.append((score, term))
        scored.sort(key=lambda pair: -pair[0])
        ctx.glossary_context = [
            {
                "term": t.term,
                "definition": t.definition,
                "synonyms": [s.synonym for s in t.synonyms],
            }
            for _, t in scored[:8]
        ]

    async def _resolve_metrics(self, ctx, db, search_text: str, q_tokens: set[str]) -> None:
        metrics = (
            await db.execute(select(BusinessMetric).where(BusinessMetric.status == "approved"))
        ).scalars().all()
        scored = [
            (score, m)
            for m in metrics
            if (score := _score(search_text, q_tokens, f"{m.name} {m.description or ''}")) > 0.3
        ]
        scored.sort(key=lambda pair: -pair[0])
        ctx.metric_context = [
            {
                "name": m.name,
                "expression": m.expression,
                "table": m.table_qualified_name,
                "aggregation": m.aggregation,
                "description": m.description,
            }
            for _, m in scored[:6]
        ]

    async def _resolve_tables(self, ctx, db, search_text: str, q_tokens: set[str]) -> None:
        tables = (
            await db.execute(
                select(CatalogTable)
                .options(selectinload(CatalogTable.columns), selectinload(CatalogTable.database))
                .where(CatalogTable.is_active.is_(True))
            )
        ).scalars().all()

        allowed = set(get_settings().get("connectors.definitions", {}).get(
            ctx.connector_id or get_settings().get("connectors.default"), {}
        ).get("allowed_schemas") or [])

        scored: list[tuple[float, CatalogTable]] = []
        for table in tables:
            if allowed and table.database.name not in allowed:
                continue
            column_text = " ".join(
                f"{c.name} {c.description or ''} {' '.join(c.tags or [])}" for c in table.columns
            )
            candidate = (
                f"{table.name} {table.description or ''} {table.technical_comment or ''} "
                f"{' '.join(table.tags or [])} {column_text}"
            )
            score = _score(search_text, q_tokens, candidate)
            # popularity boost from usage
            score += min(table.usage_count, 50) * 0.002
            if score > 0.15:
                scored.append((score, table))
        scored.sort(key=lambda pair: -pair[0])

        ctx.resolved_tables = [
            ResolvedTable(
                id=t.id,
                database=t.database.name,
                name=t.name,
                description=t.description or t.technical_comment,
                row_count=t.row_count,
                partition_columns=t.partition_columns or [],
                columns=[
                    {
                        "name": c.name,
                        "data_type": c.data_type,
                        "description": c.description or c.technical_comment,
                        "sample_values": (c.sample_values or [])[:5],
                        "is_partition": c.is_partition,
                        "is_pii": c.is_pii,
                    }
                    for c in t.columns[:MAX_COLUMNS_PER_TABLE]
                ],
                score=round(min(score, 1.0), 3),
            )
            for score, t in scored[:MAX_TABLES]
        ]

    async def _search_library(self, ctx, db, question: str) -> None:
        settings = get_settings()
        if not settings.get("pipeline.query_library.enabled", True):
            return
        entries = (
            await db.execute(
                select(QueryLibraryEntry).where(QueryLibraryEntry.is_active.is_(True)).limit(500)
            )
        ).scalars().all()
        best: tuple[float, QueryLibraryEntry] | None = None
        for entry in entries:
            similarity = fuzz.token_sort_ratio(question.lower(), entry.normalized_question) / 100.0
            # feedback-weighted: successful, liked queries rank higher
            weight = 1.0 + 0.02 * entry.positive_feedback - 0.1 * entry.negative_feedback
            similarity *= max(weight, 0.5)
            if best is None or similarity > best[0]:
                best = (similarity, entry)
        threshold = settings.get("pipeline.query_library.reuse_similarity_threshold", 0.82)
        if best and best[0] >= threshold:
            ctx.library_match = LibraryMatch(
                entry_id=best[1].id,
                question=best[1].question,
                sql=best[1].sql,
                similarity=round(best[0], 3),
                tables_used=best[1].tables_used or [],
            )
