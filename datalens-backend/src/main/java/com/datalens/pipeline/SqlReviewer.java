package com.datalens.pipeline;

import com.datalens.config.DataLensSettings;
import com.datalens.llm.LlmPrompts;
import com.datalens.llm.LlmProviderRegistry;
import com.datalens.schema.response.ClarificationOptionDto;
import com.datalens.schema.response.ClarificationRequestDto;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import net.sf.jsqlparser.parser.CCJSqlParserUtil;
import net.sf.jsqlparser.statement.select.Select;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Automated SQL review before auto-execute (Python sql_reviewer parity). */
@Component
public class SqlReviewer {
  private static final Logger log = LoggerFactory.getLogger(SqlReviewer.class);

  private final DataLensSettings settings;
  private final LlmProviderRegistry llm;
  private final ObjectMapper mapper;

  public SqlReviewer(DataLensSettings settings, LlmProviderRegistry llm, ObjectMapper mapper) {
    this.settings = settings;
    this.llm = llm;
    this.mapper = mapper;
  }

  public Map<String, Object> review(PipelineContext ctx, String dialect) {
    String sql = SqlUtils.sanitizeSql(ctx.getOptimizedSql() != null ? ctx.getOptimizedSql() : ctx.getSql(), dialect);
    List<String> issues = new ArrayList<>(ctx.getValidationWarnings());
    List<String> structural = structuralCheck(sql);
    issues.addAll(structural);
    if (!structural.isEmpty()) {
      return Map.of("approved", false, "confidence", 0.0, "issues", issues);
    }

    @SuppressWarnings("unchecked")
    Map<String, Object> previewCfg = settings.section("pipeline.query_preview");
    Object useLlm = previewCfg.get("automated_review.use_llm");
    if (useLlm == null) useLlm = previewCfg.getOrDefault("use_llm", true);
    if (Boolean.TRUE.equals(useLlm)) {
      Map<String, Object> llmResult = llmReview(ctx, sql);
      if (llmResult != null) {
        issues.addAll(stringList(llmResult.get("issues")));
        if (!Boolean.TRUE.equals(llmResult.get("approved"))) {
          Map<String, Object> out = new LinkedHashMap<>();
          out.put("approved", false);
          out.put("confidence", ((Number) llmResult.getOrDefault("confidence", 0.5)).doubleValue());
          out.put("issues", issues);
          out.put("clarification", clarificationFromReview(ctx, llmResult));
          return out;
        }
        ctx.getConfidence().put("review", ((Number) llmResult.getOrDefault("confidence", 0.9)).doubleValue());
        return Map.of(
            "approved", true,
            "confidence", ((Number) llmResult.getOrDefault("confidence", 0.9)).doubleValue(),
            "issues", issues);
      }
    }

    double overall = fallbackConfidence(ctx);
    double threshold = ((Number) settings.get("pipeline.confidence.clarification_threshold", 0.65)).doubleValue();
    boolean approved = overall >= threshold;
    Map<String, Object> out = new LinkedHashMap<>();
    out.put("approved", approved);
    out.put("confidence", overall);
    out.put("issues", issues);
    if (!approved) out.put("clarification", clarificationFromReview(ctx, Map.of()));
    return out;
  }

  public ClarificationRequestDto clarificationFromReview(PipelineContext ctx, Map<String, Object> review) {
    ClarificationRequestDto req = new ClarificationRequestDto();
    Object question = review.get("clarifying_question");
    req.setQuestion(
        question != null && !String.valueOf(question).isBlank()
            ? String.valueOf(question)
            : "I need one more detail before I can run this query.");
    req.setAllowFreeText(true);
    for (ResolvedTableModel t : ctx.getResolvedTables().stream().limit(4).toList()) {
      ClarificationOptionDto opt = new ClarificationOptionDto();
      opt.setLabel(t.qualifiedName());
      opt.setValue(t.qualifiedName());
      opt.setDescription(t.getDescription());
      req.getOptions().add(opt);
    }
    if (ctx.getIntent() != null && ctx.getIntent().getAmbiguities() != null) {
      for (String amb : ctx.getIntent().getAmbiguities().stream().limit(3).toList()) {
        ClarificationOptionDto opt = new ClarificationOptionDto();
        opt.setLabel(amb);
        opt.setValue(amb);
        req.getOptions().add(opt);
      }
    }
    if (req.getOptions().size() > 5) req.setOptions(req.getOptions().subList(0, 5));
    return req;
  }

  private List<String> structuralCheck(String sql) {
    try {
      if (!(CCJSqlParserUtil.parse(sql) instanceof Select)) {
        return List.of("Only SELECT statements are allowed.");
      }
    } catch (Exception e) {
      return List.of("SQL could not be parsed: " + e.getMessage());
    }
    return List.of();
  }

  private Map<String, Object> llmReview(PipelineContext ctx, String sql) {
    try {
      Map<String, Object> payload = new HashMap<>();
      payload.put("question", ctx.effectivePrompt());
      payload.put("sql", sql);
      if (ctx.getPlan() != null) {
        payload.put("plan_rationale", ctx.getPlan().getRationale());
        payload.put("tables", ctx.getPlan().getTables());
      }
      Map<String, Object> parsed =
          llm.completeJson(LlmPrompts.SQL_REVIEWER_SYSTEM, mapper.writeValueAsString(payload));
      Map<String, Object> out = new LinkedHashMap<>();
      out.put("approved", !parsed.containsKey("approved") || Boolean.TRUE.equals(parsed.get("approved")));
      out.put("confidence", ((Number) parsed.getOrDefault("confidence", 0.85)).doubleValue());
      out.put("issues", stringList(parsed.get("issues")));
      out.put("clarifying_question", parsed.get("clarifying_question"));
      return out;
    } catch (Exception e) {
      log.debug("LLM SQL review unavailable: {}", e.getMessage());
      return null;
    }
  }

  private static double fallbackConfidence(PipelineContext ctx) {
    List<Double> scores = new ArrayList<>();
    for (Map.Entry<String, Double> e : ctx.getConfidence().entrySet()) {
      if (!"overall".equals(e.getKey()) && e.getValue() != null) scores.add(e.getValue());
    }
    if (scores.isEmpty()) return 0.75;
    return Math.round(scores.stream().mapToDouble(d -> d).average().orElse(0.75) * 1000) / 1000.0;
  }

  private static List<String> stringList(Object value) {
    if (!(value instanceof List<?> list)) return List.of();
    return list.stream().map(String::valueOf).filter(s -> !s.isBlank()).toList();
  }
}
