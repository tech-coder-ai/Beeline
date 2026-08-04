package com.datalens.pipeline;

import com.datalens.llm.LlmResult;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.Data;

@Data
public class PipelineContext {
  private String prompt;
  private String sessionId;
  private String userId = "default";
  private String connectorId;
  private String refinedPrompt;
  private List<String> refinementNotes = new ArrayList<>();
  private List<Map<String, String>> history = new ArrayList<>();
  private ExecutionPlanModel previousPlan;
  private String previousSql;
  private String clarificationAnswer;
  private IntentModel intent;
  private List<ResolvedTableModel> resolvedTables = new ArrayList<>();
  private List<Map<String, Object>> glossaryContext = new ArrayList<>();
  private List<Map<String, Object>> businessTermContext = new ArrayList<>();
  private List<Map<String, Object>> metricContext = new ArrayList<>();
  private LibraryMatchModel libraryMatch;
  private ExecutionPlanModel plan;
  private String sql;
  private String optimizedSql;
  private List<String> validationWarnings = new ArrayList<>();
  private Map<String, Object> cost = new HashMap<>();
  private List<String> resultColumns = new ArrayList<>();
  private List<String> resultTypes = new ArrayList<>();
  private List<List<Object>> resultRows = new ArrayList<>();
  private int rowCount;
  private int executionTimeMs;
  private boolean truncated;
  private boolean cacheHit;
  private Map<String, Double> confidence = new HashMap<>(Map.of("business", 0.0, "metadata", 0.0, "sql", 0.0, "overall", 0.0));
  private List<String> warnings = new ArrayList<>();
  private List<Map<String, Object>> llmCalls = new ArrayList<>();
  private String executionId;
  private boolean sqlFromDeterministicBuilder;
  /**
   * Set when the planner detects a required value it cannot ground (e.g. a time period the
   * question never stated) and had to strip a filter rather than fabricate one. When non-null the
   * orchestrator asks the user instead of previewing/executing a query it knows is incomplete.
   */
  private String clarificationQuestion;

  public String effectivePrompt() {
    return refinedPrompt != null && !refinedPrompt.isBlank() ? refinedPrompt : prompt;
  }

  public void recordLlm(String purpose, LlmResult result, String systemPrompt, String userMessage) {
    Map<String, Object> call = new HashMap<>();
    call.put("purpose", purpose);
    call.put("provider", result.getProvider());
    call.put("model", result.getModel());
    call.put("prompt_tokens", result.getPromptTokens());
    call.put("completion_tokens", result.getCompletionTokens());
    if (systemPrompt != null) call.put("system_prompt", systemPrompt);
    if (userMessage != null) call.put("user_message", userMessage);
    if (result.getText() != null && !result.getText().isBlank()) call.put("response", result.getText());
    llmCalls.add(call);
  }
}
