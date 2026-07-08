"""Intent Engine: classifies the analytical intent of the user message.

Uses the LLM with conversation context; degrades to keyword heuristics when
the LLM is unavailable (graceful degradation requirement).
"""
from __future__ import annotations

import re

from app.core.exceptions import LLMUnavailable
from app.core.logging import get_logger
from app.llm import prompts
from app.llm.providers import get_llm
from app.pipeline.types import Intent, PipelineContext

logger = get_logger(__name__)

_HEURISTICS: list[tuple[str, str]] = [
    (r"\btop\s+\d+|\btop\b|\bhighest\b|\bbest\b", "top_n"),
    (r"\bbottom\s+\d+|\blowest\b|\bworst\b", "bottom_n"),
    (r"\btrend|\bover time|\bmonthly|\bweekly|\bdaily|\bby month|\bby year", "time_series"),
    (r"\bcompare|\bvs\b|\bversus|\bdifference between", "comparison"),
    (r"\byear over year|\byoy\b", "yoy"),
    (r"\bmonth over month|\bmom\b", "mom"),
    (r"\bquarter over quarter|\bqoq\b", "qoq"),
    (r"\brunning total|\bcumulative", "running_total"),
    (r"\brolling|\bmoving average", "rolling_average"),
    (r"\bmedian\b", "median"),
    (r"\bdistinct\b|\bunique\b", "distinct_count"),
    (r"\bwhy\b|\bcaused?\b|\breason\b|\broot cause", "root_cause"),
    (r"\bforecast|\bpredict|\bproject", "forecasting"),
    (r"\banomal|\boutlier|\bunusual", "anomaly"),
    (r"\bcorrelat", "correlation"),
    (r"\bdistribution|\bhistogram|\bspread", "distribution"),
    (r"\bsum|\btotal|\baverage|\bavg|\bcount|\bhow many|\bhow much", "aggregation"),
    (r"\bwhat tables|\bwhat data|\bwhich columns|\bmetadata|\bdescribe table", "metadata_question"),
]


class IntentEngine:
    async def run(self, ctx: PipelineContext) -> None:
        history_block = ""
        if ctx.history:
            turns = "\n".join(
                f"{turn['role']}: {turn['content']}" for turn in ctx.history[-8:] if turn.get("content")
            )
            history_block = f"Recent conversation:\n{turns}\n\n"
        clarification_block = (
            f"The user answered a clarification question with: {ctx.clarification_answer}\n\n"
            if ctx.clarification_answer else ""
        )
        try:
            llm = get_llm()
            parsed, result = await llm.complete_json(
                prompts.INTENT_SYSTEM,
                f"{history_block}{clarification_block}Current message:\n{ctx.effective_prompt}",
            )
            ctx.record_llm("intent", result)
            if parsed:
                ctx.intent = Intent(**{k: v for k, v in parsed.items() if k in Intent.model_fields})
                ctx.confidence["business"] = float(ctx.intent.confidence)
                return
        except LLMUnavailable as exc:
            ctx.warnings.append(f"LLM unavailable for intent analysis ({exc.message}); using heuristics.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("intent LLM failed, falling back to heuristics: %s", exc)

        ctx.intent = self._heuristic_intent(ctx.effective_prompt)
        ctx.confidence["business"] = ctx.intent.confidence

    @staticmethod
    def _heuristic_intent(text: str) -> Intent:
        lowered = text.lower()
        matched = [intent for pattern, intent in _HEURISTICS if re.search(pattern, lowered)]
        top_match = re.search(r"\btop\s+(\d+)", lowered)
        time_match = re.search(
            r"last\s+(\d+)\s+(day|week|month|quarter|year)s?|\blast (year|month|quarter|week)\b|\bytd\b",
            lowered,
        )
        return Intent(
            intent_types=matched or ["aggregation"],
            subject=text[:120],
            top_n=int(top_match.group(1)) if top_match else None,
            time_range=time_match.group(0) if time_match else None,
            needs_data="metadata_question" not in matched,
            confidence=0.45 if matched else 0.3,
        )
