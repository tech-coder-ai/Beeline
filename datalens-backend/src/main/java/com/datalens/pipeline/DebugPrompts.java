package com.datalens.pipeline;

import com.datalens.config.DataLensSettings;
import com.datalens.schema.response.DataLensResponseDto;
import com.datalens.schema.response.LlmPromptTraceDto;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class DebugPrompts {
  private DebugPrompts() {}

  public static void attach(DataLensSettings settings, PipelineContext ctx, DataLensResponseDto response) {
    if (!Boolean.TRUE.equals(settings.get("feature_flags.debug_mode", false))) return;
    if (ctx.getLlmCalls() == null || ctx.getLlmCalls().isEmpty()) return;
    List<LlmPromptTraceDto> traces = new ArrayList<>();
    for (Map<String, Object> call : ctx.getLlmCalls()) {
      LlmPromptTraceDto trace = new LlmPromptTraceDto();
      trace.setPurpose(stringValue(call.get("purpose")));
      trace.setProvider(stringValue(call.get("provider")));
      trace.setModel(stringValue(call.get("model")));
      trace.setSystemPrompt(stringValue(call.get("system_prompt")));
      trace.setUserMessage(stringValue(call.get("user_message")));
      trace.setResponse(stringValue(call.get("response")));
      if (call.get("prompt_tokens") instanceof Number n) trace.setPromptTokens(n.intValue());
      if (call.get("completion_tokens") instanceof Number n) trace.setCompletionTokens(n.intValue());
      traces.add(trace);
    }
    response.setPromptsUsed(traces);
  }

  @SuppressWarnings("unchecked")
  public static void restoreCalls(PipelineContext ctx, Map<String, Object> tokenUsage) {
    if (tokenUsage == null || tokenUsage.isEmpty()) return;
    Object calls = tokenUsage.get("calls");
    if (!(calls instanceof List<?> list) || list.isEmpty()) return;
    ctx.getLlmCalls().clear();
    for (Object item : list) {
      if (item instanceof Map<?, ?> raw) {
        ctx.getLlmCalls().add((Map<String, Object>) raw);
      }
    }
  }

  private static String stringValue(Object value) {
    return value != null ? String.valueOf(value) : "";
  }
}
