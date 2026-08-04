"""Trace LLM calls onto the pipeline context for debug mode."""
from __future__ import annotations

from app.llm.base import LLMResult
from app.llm.providers import get_llm
from app.pipeline.types import PipelineContext


async def complete_json_traced(
    ctx: PipelineContext,
    purpose: str,
    system_prompt: str,
    user_message: str,
) -> tuple[dict, LLMResult]:
    llm = get_llm()
    parsed, result = await llm.complete_json(system_prompt, user_message)
    ctx.record_llm(purpose, result, system_prompt=system_prompt, user_message=user_message)
    return parsed, result
