"""Clarification Engine: when confidence is low, ask - never guess."""
from __future__ import annotations

import json

from app.core.logging import get_logger
from app.llm import prompts
from app.llm.providers import get_llm
from app.pipeline.types import PipelineContext
from app.schemas.response import ClarificationOption, ClarificationRequest

logger = get_logger(__name__)


class ClarificationEngine:
    async def build(self, ctx: PipelineContext) -> ClarificationRequest:
        ambiguities = ctx.intent.ambiguities if ctx.intent else []
        available = {
            "metrics": [m["name"] for m in ctx.metric_context],
            "glossary": [g["term"] for g in ctx.glossary_context],
            "tables": [t.qualified_name for t in ctx.resolved_tables],
            "columns": [
                f"{t.qualified_name}.{c['name']}"
                for t in ctx.resolved_tables for c in t.columns
            ][:60],
        }
        try:
            llm = get_llm()
            parsed, result = await llm.complete_json(
                prompts.CLARIFIER_SYSTEM,
                f"Question: {ctx.effective_prompt}\n\n"
                f"Ambiguities: {json.dumps(ambiguities)}\n\n"
                f"Available context: {json.dumps(available)}",
            )
            ctx.record_llm("clarify", result)
            options = [
                ClarificationOption(
                    label=str(o.get("label", "")),
                    value=str(o.get("value", o.get("label", ""))),
                    description=o.get("description"),
                )
                for o in parsed.get("options", []) if o.get("label")
            ]
            if parsed.get("question") and options:
                return ClarificationRequest(question=str(parsed["question"]), options=options[:5])
        except Exception as exc:  # noqa: BLE001
            logger.debug("clarifier LLM unavailable: %s", exc)

        # deterministic fallback
        if ambiguities:
            question = f"Could you clarify what you mean by \"{ambiguities[0]}\"?"
        else:
            question = (
                "I couldn't confidently match your question to the available data. "
                "Which dataset should I use?"
            )
        options = [
            ClarificationOption(label=t.qualified_name, value=t.qualified_name)
            for t in ctx.resolved_tables[:4]
        ]
        return ClarificationRequest(question=question, options=options)
