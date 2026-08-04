"""Attach captured LLM prompts to chat responses when debug mode is enabled."""
from __future__ import annotations

from app.core.config import get_settings
from app.pipeline.types import PipelineContext
from app.schemas.response import BeelineResponse, LlmPromptTrace


def attach_debug_prompts(ctx: PipelineContext, response: BeelineResponse) -> None:
    if not get_settings().get("feature_flags.debug_mode", False):
        return
    if not ctx.llm_calls:
        return
    response.prompts_used = [
        LlmPromptTrace(
            purpose=str(c.get("purpose") or ""),
            provider=str(c.get("provider") or ""),
            model=str(c.get("model") or ""),
            system_prompt=str(c.get("system_prompt") or ""),
            user_message=str(c.get("user_message") or ""),
            prompt_tokens=c.get("prompt_tokens"),
            completion_tokens=c.get("completion_tokens"),
        )
        for c in ctx.llm_calls
    ]
