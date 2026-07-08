"""AI Orchestration Engine.

Wires the pipeline stages:

  refine -> intent -> semantic search -> (library reuse | plan -> generate)
  -> validate -> optimize -> estimate cost -> guard decision
  -> (clarify | preview | execute) -> interpret -> visualize -> respond

Every run is recorded in execution_history for full traceability.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import get_connector
from app.core.config import get_settings
from app.core.exceptions import (
    BeelineError,
    ConnectorError,
    GuardRailViolation,
    LLMUnavailable,
    ValidationFailed,
)
from app.core.logging import get_logger
from app.models.catalog import CatalogDatabase, CatalogTable
from app.models.chat import ExecutionHistory
from app.pipeline.stages.clarification import ClarificationEngine
from app.pipeline.stages.cost import CostEstimator
from app.pipeline.stages.executor import QueryExecutor
from app.pipeline.stages.intent import IntentEngine
from app.pipeline.stages.interpreter import ResultInterpreter
from app.pipeline.stages.optimizer import SQLOptimizer
from app.pipeline.stages.planner import QueryPlanner
from app.pipeline.stages.refiner import QueryRefiner
from app.pipeline.stages.semantic_search import SemanticSearch
from app.pipeline.stages.sql_generator import SQLGenerator
from app.pipeline.stages.sql_reviewer import SqlReviewer
from app.pipeline.stages.validator import SQLValidator
from app.pipeline.stages.visualization import VisualizationPlanner
from app.pipeline.sql_utils import sanitize_sql, compact_connector_error
from app.pipeline.types import ExecutionPlan, PipelineContext
from app.schemas.response import (
    BeelineResponse,
    ConfidenceBreakdown,
    CostEstimate,
    ExecutionStats,
    SqlExplanation,
)
from app.services.audit import audit
from app.services.explain import explain_service
from app.services.query_library import QueryLibraryService

logger = get_logger(__name__)


class Orchestrator:
    def __init__(self) -> None:
        self.refiner = QueryRefiner()
        self.intent_engine = IntentEngine()
        self.semantic_search = SemanticSearch()
        self.planner = QueryPlanner()
        self.generator = SQLGenerator()
        self.validator = SQLValidator()
        self.optimizer = SQLOptimizer()
        self.cost_estimator = CostEstimator()
        self.executor = QueryExecutor()
        self.interpreter = ResultInterpreter()
        self.viz_planner = VisualizationPlanner()
        self.clarifier = ClarificationEngine()
        self.sql_reviewer = SqlReviewer()
        self.library = QueryLibraryService()

    # ------------------------------------------------------------------ entry
    async def run(self, ctx: PipelineContext, db: AsyncSession) -> BeelineResponse:
        settings = get_settings()
        history = ExecutionHistory(
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            connector_id=ctx.connector_id,
            prompt=ctx.prompt,
        )
        db.add(history)
        await db.flush()
        ctx.execution_id = history.id

        try:
            response = await self._run_pipeline(ctx, db, history, settings)
        except GuardRailViolation as exc:
            history.status = "blocked"
            history.error = exc.message
            await audit(db, ctx.user_id, "guardrail.block", detail={
                "prompt": ctx.prompt, "sql": ctx.sql, "reason": exc.message,
            }, severity="warning")
            response = self._error_response(ctx, "blocked", exc.message)
        except LLMUnavailable as exc:
            history.status = "failed"
            history.error = exc.message
            response = self._error_response(
                ctx, "error",
                f"The AI model is currently unavailable ({exc.message}). "
                "You can still run saved queries or browse metadata.",
            )
        except ValidationFailed as exc:
            history.status = "failed"
            history.error = exc.message
            response = self._error_response(ctx, "error", exc.message)
        except ConnectorError as exc:
            history.status = "failed"
            history.error = exc.message
            response = self._error_response(ctx, "error", compact_connector_error(exc.message))
        except BeelineError as exc:
            history.status = "failed"
            history.error = exc.message
            response = self._error_response(ctx, "error", exc.message)

        self._record_history(ctx, history, response)
        await db.flush()
        response.execution_id = history.id
        return response

    # ------------------------------------------------------------------ pipeline
    async def _run_pipeline(
        self, ctx: PipelineContext, db: AsyncSession, history: ExecutionHistory, settings
    ) -> BeelineResponse:
        connector = get_connector(ctx.connector_id)

        await self.refiner.run(ctx, db)
        await self.intent_engine.run(ctx)
        await self.semantic_search.run(ctx, db)

        if ctx.intent and not ctx.intent.needs_data:
            return await self._metadata_answer(ctx)

        # No answer to a clarification can ever populate an empty catalog - detect
        # that case once and give a clear, actionable message instead of looping
        # clarification requests forever.
        if not ctx.resolved_tables and not await self._catalog_has_tables(db):
            history.status = "blocked"
            return BeelineResponse(
                kind="answer",
                summary=(
                    "No tables have been synchronized into Beeline's catalog yet, so there is "
                    "no data to query. Ask an administrator to run a metadata sync "
                    "(Admin -> Connectors & Sync -> Full sync) once the analytics connector is "
                    "reachable, then ask again."
                ),
                visualization="text",
                confidence=self._confidence_breakdown(ctx),
                warnings=ctx.warnings,
            )

        # -------- confidence gate: clarify, never guess
        overall = self._overall_confidence(ctx, planning_done=False)
        threshold = settings.get("pipeline.confidence.clarification_threshold", 0.65)
        must_clarify = (
            (ctx.intent and ctx.intent.ambiguities and overall < threshold and not ctx.clarification_answer)
            or not ctx.resolved_tables
        )
        if must_clarify:
            history.status = "clarification"
            clarification = await self.clarifier.build(ctx)
            return BeelineResponse(
                kind="clarification",
                summary="I need one detail before I query the data.",
                clarification=clarification,
                confidence=self._confidence_breakdown(ctx),
                tables_used=[t.qualified_name for t in ctx.resolved_tables],
                warnings=ctx.warnings,
            )

        # -------- SQL: reuse from library or plan+generate
        if ctx.library_match and not (ctx.intent and ctx.intent.is_follow_up):
            ctx.sql = ctx.library_match.sql
            ctx.plan = ExecutionPlan(
                tables=ctx.library_match.tables_used,
                rationale=f"Reused proven query for: \"{ctx.library_match.question}\" "
                          f"(similarity {ctx.library_match.similarity:.0%}).",
                confidence=ctx.library_match.similarity,
            )
            ctx.confidence["sql"] = ctx.library_match.similarity
        else:
            await self.planner.run(ctx, db)
            await self.generator.run(ctx, connector)

        # -------- validate + optimize + estimate
        dialect = connector.dialect.sqlglot_dialect
        if ctx.sql:
            ctx.sql = sanitize_sql(ctx.sql, dialect)
        known_tables = await self._known_tables(db)
        self.validator.validate(ctx.sql or "", dialect, ctx, known_tables)
        ctx.optimized_sql = self.optimizer.optimize(
            ctx.sql or "", dialect, ctx
        )
        await self.cost_estimator.run(ctx, connector)

        if ctx.cost.get("blocked"):
            history.status = "blocked"
            history.cost_estimate = ctx.cost
            return BeelineResponse(
                kind="blocked",
                summary=ctx.cost.get("block_reason") or "Query exceeds cost thresholds.",
                sql=ctx.optimized_sql,
                cost_estimate=CostEstimate(**ctx.cost),
                confidence=self._confidence_breakdown(ctx),
                tables_used=ctx.plan.tables if ctx.plan else [],
                recommendations=ctx.cost.get("suggestions", []),
                warnings=ctx.warnings + ctx.validation_warnings,
            )

        # -------- preview / auto-review gate
        preview_cfg = settings.section("pipeline.query_preview") or {}
        manual_review = preview_cfg.get("manual_review")
        if manual_review is None:
            # Backward compat: enabled=false meant skip preview and auto-execute.
            manual_review = preview_cfg.get("enabled", True)

        if manual_review and not ctx.clarification_answer:
            history.status = "preview"
            sql_explanation = await self._sql_explanation(ctx, connector)
            return BeelineResponse(
                kind="preview",
                summary="Here is the query I plan to run. Review and execute, or refine your question.",
                sql=ctx.optimized_sql,
                sql_explanation=sql_explanation,
                cost_estimate=CostEstimate(**ctx.cost) if ctx.cost else None,
                confidence=self._confidence_breakdown(ctx),
                tables_used=ctx.plan.tables if ctx.plan else [],
                filters_used=[f"{f.column} {f.operator} {f.value}" for f in (ctx.plan.filters if ctx.plan else [])],
                metrics_used=[a.alias or a.function for a in (ctx.plan.aggregations if ctx.plan else [])],
                warnings=ctx.warnings + ctx.validation_warnings,
                metadata={"rationale": ctx.plan.rationale if ctx.plan else "", "manual_review": True},
            )

        review = await self.sql_reviewer.review(ctx, connector.dialect.sqlglot_dialect, settings)
        clarify_threshold = settings.get("pipeline.confidence.clarification_threshold", 0.65)
        if not review["approved"] and (
            review["confidence"] < clarify_threshold or review.get("clarification")
        ):
            history.status = "clarification"
            clarification = review.get("clarification") or await self.clarifier.build(ctx)
            return BeelineResponse(
                kind="clarification",
                summary="I need one detail before I query the data.",
                clarification=clarification,
                sql=ctx.optimized_sql,
                confidence=self._confidence_breakdown(ctx),
                tables_used=ctx.plan.tables if ctx.plan else [],
                warnings=ctx.warnings + ctx.validation_warnings + review.get("issues", []),
            )
        if review.get("issues"):
            ctx.warnings.extend(review["issues"])

        return await self.execute_and_respond(ctx, db, history)

    # ------------------------------------------------------------------ execution
    async def execute_and_respond(
        self, ctx: PipelineContext, db: AsyncSession, history: ExecutionHistory
    ) -> BeelineResponse:
        connector = get_connector(ctx.connector_id)
        await self.executor.run(ctx, connector)
        history.status = "executed"
        history.executed_at = datetime.now(timezone.utc)

        narrative = await self.interpreter.run(ctx)
        viz = self.viz_planner.run(ctx)
        sql_explanation = await self._sql_explanation(ctx, connector)

        if not ctx.cache_hit and ctx.row_count >= 0 and ctx.sql:
            await self.library.record_success(ctx, db)
        await self._bump_usage(ctx, db)
        await audit(db, ctx.user_id, "sql.execute", detail={
            "sql": ctx.optimized_sql, "rows": ctx.row_count, "ms": ctx.execution_time_ms,
        })

        return BeelineResponse(
            kind="answer",
            summary=narrative["summary"],
            confidence=self._confidence_breakdown(ctx),
            visualization=viz["visualization"],
            cards=viz["cards"],
            charts=viz["charts"],
            table=viz["table"],
            insights=narrative["insights"],
            recommendations=narrative["recommendations"],
            follow_up_questions=narrative["follow_up_questions"],
            sql=ctx.optimized_sql,
            sql_explanation=sql_explanation,
            cost_estimate=CostEstimate(**ctx.cost) if ctx.cost else None,
            stats=ExecutionStats(
                execution_time_ms=ctx.execution_time_ms,
                row_count=ctx.row_count,
                column_count=len(ctx.result_columns),
                connector_id=ctx.connector_id,
                cache_hit=ctx.cache_hit,
                reused_from_library=ctx.library_match is not None,
            ),
            tables_used=ctx.plan.tables if ctx.plan else [],
            filters_used=[f"{f.column} {f.operator} {f.value}" for f in (ctx.plan.filters if ctx.plan else [])],
            metrics_used=[a.alias or f"{a.function}({a.column})" for a in (ctx.plan.aggregations if ctx.plan else [])],
            warnings=ctx.warnings + ctx.validation_warnings,
            metadata={
                "rationale": ctx.plan.rationale if ctx.plan else "",
                "refined_prompt": ctx.refined_prompt,
                "refinement_notes": ctx.refinement_notes,
                "library_match": ctx.library_match.question if ctx.library_match else None,
            },
        )

    # ------------------------------------------------------------------ helpers
    async def _metadata_answer(self, ctx: PipelineContext) -> BeelineResponse:
        lines = []
        for table in ctx.resolved_tables[:5]:
            cols = ", ".join(c["name"] for c in table.columns[:12])
            lines.append(
                f"**{table.qualified_name}**"
                + (f" — {table.description}" if table.description else "")
                + (f" (~{table.row_count:,} rows)" if table.row_count else "")
                + f"\nColumns: {cols}"
            )
        summary = (
            "Here is what I found in the catalog:\n\n" + "\n\n".join(lines)
            if lines else "I couldn't find matching metadata in the catalog."
        )
        return BeelineResponse(
            kind="answer",
            summary=summary,
            visualization="text",
            confidence=self._confidence_breakdown(ctx),
            tables_used=[t.qualified_name for t in ctx.resolved_tables],
            follow_up_questions=[
                f"Show me sample data from {ctx.resolved_tables[0].qualified_name}"
            ] if ctx.resolved_tables else [],
            warnings=ctx.warnings,
        )

    def _overall_confidence(self, ctx: PipelineContext, planning_done: bool) -> float:
        business = ctx.confidence.get("business", 0.0)
        metadata = ctx.confidence.get("metadata", 0.0)
        sql = ctx.confidence.get("sql", 0.0)
        if planning_done:
            overall = 0.3 * business + 0.3 * metadata + 0.4 * sql
        else:
            overall = 0.5 * business + 0.5 * metadata
        if ctx.library_match:
            overall = max(overall, ctx.library_match.similarity)
        ctx.confidence["overall"] = round(overall, 3)
        return overall

    def _confidence_breakdown(self, ctx: PipelineContext) -> ConfidenceBreakdown:
        return ConfidenceBreakdown(
            business=round(ctx.confidence.get("business", 0.0), 3),
            metadata=round(ctx.confidence.get("metadata", 0.0), 3),
            sql=round(ctx.confidence.get("sql", 0.0), 3),
            overall=round(ctx.confidence.get("overall", 0.0), 3),
        )

    async def _sql_explanation(self, ctx: PipelineContext, connector) -> SqlExplanation | None:
        sql = ctx.optimized_sql or ctx.sql
        if not sql:
            return None
        try:
            return await explain_service.explain(
                sql, connector.dialect.sqlglot_dialect, question=ctx.effective_prompt
            )
        except Exception as exc:  # noqa: BLE001 - explanation is optional
            logger.debug("SQL explanation unavailable: %s", exc)
            return None

    async def _catalog_has_tables(self, db: AsyncSession) -> bool:
        row = (
            await db.execute(select(CatalogTable.id).where(CatalogTable.is_active.is_(True)).limit(1))
        ).first()
        return row is not None

    async def _known_tables(self, db: AsyncSession) -> set[str]:
        rows = (
            await db.execute(
                select(CatalogDatabase.name, CatalogTable.name)
                .join(CatalogTable, CatalogTable.database_id == CatalogDatabase.id)
                .where(CatalogTable.is_active.is_(True))
            )
        ).all()
        return {f"{d}.{t}".lower() for d, t in rows}

    async def _bump_usage(self, ctx: PipelineContext, db: AsyncSession) -> None:
        for table in ctx.resolved_tables:
            if ctx.plan and table.qualified_name in ctx.plan.tables:
                row = await db.get(CatalogTable, table.id)
                if row:
                    row.usage_count += 1

    def _record_history(
        self, ctx: PipelineContext, history: ExecutionHistory, response: BeelineResponse
    ) -> None:
        history.refined_prompt = ctx.refined_prompt
        history.intent = ctx.intent.model_dump() if ctx.intent else None
        history.execution_plan = ctx.plan.model_dump() if ctx.plan else None
        history.generated_sql = ctx.sql
        history.optimized_sql = ctx.optimized_sql
        history.row_count = ctx.row_count or None
        history.execution_time_ms = ctx.execution_time_ms or None
        history.cost_estimate = ctx.cost or None
        history.confidence = ctx.confidence
        history.warnings = ctx.warnings + ctx.validation_warnings
        history.tables_used = ctx.plan.tables if ctx.plan else []
        history.reused_query_id = ctx.library_match.entry_id if ctx.library_match else None
        if ctx.llm_calls:
            history.llm_provider = ctx.llm_calls[0].get("provider")
            history.llm_model = ctx.llm_calls[0].get("model")
            history.token_usage = {
                "prompt_tokens": sum(c.get("prompt_tokens") or 0 for c in ctx.llm_calls),
                "completion_tokens": sum(c.get("completion_tokens") or 0 for c in ctx.llm_calls),
                "calls": ctx.llm_calls,
            }

    def _error_response(self, ctx: PipelineContext, kind: str, message: str) -> BeelineResponse:
        return BeelineResponse(
            kind=kind,  # type: ignore[arg-type]
            summary=message,
            error=message if kind == "error" else None,
            sql=ctx.optimized_sql or ctx.sql,
            confidence=self._confidence_breakdown(ctx),
            recommendations=ctx.cost.get("suggestions", []) if ctx.cost else [],
            warnings=ctx.warnings + ctx.validation_warnings,
        )


orchestrator = Orchestrator()
