"""Automated SQL review: structural checks plus optional LLM sanity check before auto-execute."""
from __future__ import annotations

import json

import sqlglot
from sqlglot import exp

from app.core.logging import get_logger
from app.llm import prompts
from app.llm.providers import get_llm
from app.pipeline.sql_utils import sanitize_sql
from app.pipeline.types import PipelineContext
from app.schemas.response import ClarificationOption, ClarificationRequest

logger = get_logger(__name__)


class SqlReviewer:
    async def review(
        self, ctx: PipelineContext, dialect: str, settings
    ) -> dict:
        """Return {approved, confidence, issues, clarification?}."""
        sql = sanitize_sql(ctx.optimized_sql or ctx.sql or "", dialect)
        issues: list[str] = list(ctx.validation_warnings)
        structural_ok, structural_issues = self._structural_check(sql, dialect)
        issues.extend(structural_issues)
        if not structural_ok:
            return {
                "approved": False,
                "confidence": 0.0,
                "issues": issues,
                "clarification": None,
            }

        use_llm = settings.get("pipeline.query_preview.automated_review.use_llm", True)
        if use_llm:
            llm_result = await self._llm_review(ctx, sql)
            if llm_result is not None:
                issues.extend(llm_result.get("issues", []))
                if not llm_result.get("approved", True):
                    clarification = self._clarification_from_review(ctx, llm_result)
                    return {
                        "approved": False,
                        "confidence": float(llm_result.get("confidence", 0.5)),
                        "issues": issues,
                        "clarification": clarification,
                    }
                ctx.confidence["review"] = float(llm_result.get("confidence", 0.9))
                return {
                    "approved": True,
                    "confidence": float(llm_result.get("confidence", 0.9)),
                    "issues": issues,
                    "clarification": None,
                }

        overall = self._fallback_confidence(ctx)
        threshold = settings.get("pipeline.confidence.clarification_threshold", 0.65)
        approved = overall >= threshold
        return {
            "approved": approved,
            "confidence": overall,
            "issues": issues,
            "clarification": self._clarification_from_review(
                ctx, {"clarifying_question": "Could you clarify your question so I can run the right query?"}
            ) if not approved else None,
        }

    @staticmethod
    def _structural_check(sql: str, dialect: str) -> tuple[bool, list[str]]:
        issues: list[str] = []
        try:
            tree = sqlglot.parse_one(sql, read=dialect)
        except Exception as exc:  # noqa: BLE001
            return False, [f"SQL could not be parsed: {exc}"]
        if not isinstance(tree, exp.Select):
            return False, ["Only SELECT statements are allowed."]
        for forbidden in (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create):
            if tree.find(forbidden):
                return False, ["Query contains forbidden statement types."]
        return True, issues

    async def _llm_review(self, ctx: PipelineContext, sql: str) -> dict | None:
        try:
            llm = get_llm()
            payload = {
                "question": ctx.effective_prompt,
                "sql": sql,
                "plan_rationale": ctx.plan.rationale if ctx.plan else "",
                "tables": ctx.plan.tables if ctx.plan else [],
            }
            parsed, result = await llm.complete_json(
                prompts.SQL_REVIEWER_SYSTEM,
                json.dumps(payload, default=str),
            )
            ctx.record_llm("sql_review", result)
            return {
                "approved": bool(parsed.get("approved", True)),
                "confidence": float(parsed.get("confidence", 0.85)),
                "issues": [str(i) for i in parsed.get("issues", []) if i],
                "clarifying_question": parsed.get("clarifying_question"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.debug("LLM SQL review unavailable: %s", exc)
            return None

    @staticmethod
    def _fallback_confidence(ctx: PipelineContext) -> float:
        scores = [v for k, v in ctx.confidence.items() if k != "overall" and isinstance(v, (int, float))]
        if not scores:
            return 0.75
        return round(sum(scores) / len(scores), 3)

    @staticmethod
    def _clarification_from_review(ctx: PipelineContext, review: dict) -> ClarificationRequest:
        question = review.get("clarifying_question") or (
            "I need one more detail before I can run this query."
        )
        options = [
            ClarificationOption(label=t.qualified_name, value=t.qualified_name)
            for t in ctx.resolved_tables[:4]
        ]
        if ctx.intent and ctx.intent.ambiguities:
            for amb in ctx.intent.ambiguities[:3]:
                options.append(ClarificationOption(label=amb, value=amb))
        return ClarificationRequest(question=str(question), options=options[:5])
