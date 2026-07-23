package com.datalens.pipeline.stages;

import com.datalens.config.DataLensSettings;
import com.datalens.connectors.AnalyticsConnector;
import com.datalens.connectors.ConnectorRegistry;
import com.datalens.connectors.QueryResult;
import com.datalens.core.cache.ResultCache;
import com.datalens.core.exception.ConnectorError;
import com.datalens.core.exception.LLMUnavailable;
import com.datalens.llm.LlmPrompts;
import com.datalens.llm.LlmProviderRegistry;
import com.datalens.llm.LlmResult;
import com.datalens.model.entity.BusinessMetric;
import com.datalens.model.entity.CatalogDatabase;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.entity.GlossaryTerm;
import com.datalens.model.entity.QueryLibraryEntry;
import com.datalens.model.repository.BusinessMetricRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.model.repository.GlossaryTermRepository;
import com.datalens.model.repository.QueryLibraryEntryRepository;
import com.datalens.pipeline.ExecutionPlanModel;
import com.datalens.pipeline.IntentModel;
import com.datalens.pipeline.LibraryMatchModel;
import com.datalens.pipeline.PipelineContext;
import com.datalens.pipeline.ResolvedTableModel;
import com.datalens.pipeline.SqlUtils;
import com.datalens.pipeline.SqlValidator;
import com.datalens.schema.response.ChartSeriesDto;
import com.datalens.schema.response.ChartSpecDto;
import com.datalens.schema.response.ClarificationOptionDto;
import com.datalens.schema.response.ClarificationRequestDto;
import com.datalens.schema.response.KpiCardDto;
import com.datalens.schema.response.TableColumnDto;
import com.datalens.schema.response.TableSpecDto;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import org.apache.commons.text.similarity.JaroWinklerSimilarity;
import org.springframework.stereotype.Component;

@Component
public class PipelineStages {
  private final DataLensSettings settings;
  private final LlmProviderRegistry llm;
  private final ObjectMapper mapper;
  private final ConnectorRegistry connectors;
  private final ResultCache cache;
  private final SqlValidator validator;
  private final CatalogTableRepository tables;
  private final CatalogDatabaseRepository databases;
  private final GlossaryTermRepository glossary;
  private final BusinessMetricRepository metrics;
  private final QueryLibraryEntryRepository library;
  private final JaroWinklerSimilarity similarity = new JaroWinklerSimilarity();

  public PipelineStages(
      DataLensSettings settings,
      LlmProviderRegistry llm,
      ObjectMapper mapper,
      ConnectorRegistry connectors,
      ResultCache cache,
      SqlValidator validator,
      CatalogTableRepository tables,
      CatalogDatabaseRepository databases,
      GlossaryTermRepository glossary,
      BusinessMetricRepository metrics,
      QueryLibraryEntryRepository library) {
    this.settings = settings;
    this.llm = llm;
    this.mapper = mapper;
    this.connectors = connectors;
    this.cache = cache;
    this.validator = validator;
    this.tables = tables;
    this.databases = databases;
    this.glossary = glossary;
    this.metrics = metrics;
    this.library = library;
  }

  public void refine(PipelineContext ctx) {
    try {
      Map<String, Object> parsed =
          llm.completeJson(LlmPrompts.REFINER_SYSTEM, "Message:\n" + ctx.getPrompt());
      if (parsed.get("refined_prompt") != null) ctx.setRefinedPrompt(String.valueOf(parsed.get("refined_prompt")));
    } catch (Exception e) {
      ctx.getWarnings().add("Refiner unavailable: " + e.getMessage());
    }
  }

  public void intent(PipelineContext ctx) {
    try {
      Map<String, Object> parsed = llm.completeJson(LlmPrompts.INTENT_SYSTEM, ctx.effectivePrompt());
      if (!parsed.isEmpty()) {
        ctx.setIntent(mapper.convertValue(parsed, IntentModel.class));
        ctx.getConfidence().put("business", ctx.getIntent().getConfidence());
        return;
      }
    } catch (LLMUnavailable e) {
      ctx.getWarnings().add("LLM unavailable for intent analysis (" + e.getMessage() + "); using heuristics.");
    } catch (Exception ignored) {
    }
    ctx.setIntent(heuristicIntent(ctx.effectivePrompt()));
    ctx.getConfidence().put("business", ctx.getIntent().getConfidence());
  }

  public void semanticSearch(PipelineContext ctx) {
    String search = ctx.effectivePrompt();
    if (ctx.getIntent() != null) {
      List<String> parts = new ArrayList<>(ctx.getIntent().getMetrics());
      parts.addAll(ctx.getIntent().getDimensions());
      if (ctx.getIntent().getSubject() != null) parts.add(ctx.getIntent().getSubject());
      search += " " + String.join(" ", parts);
    }
    Set<String> qTokens = tokens(search);
    resolveGlossary(ctx, search, qTokens);
    resolveMetrics(ctx, search, qTokens);
    resolveTables(ctx, search, qTokens);
    searchLibrary(ctx, ctx.effectivePrompt());
    double meta =
        ctx.getResolvedTables().stream().mapToDouble(ResolvedTableModel::getScore).max().orElse(0.0);
    ctx.getConfidence().put("metadata", meta);
  }

  public void plan(PipelineContext ctx) throws Exception {
    String schema = buildSchemaContext(ctx);
    Map<String, Object> parsed =
        llm.completeJson(LlmPrompts.PLANNER_SYSTEM, schema + "\n\nQuestion:\n" + ctx.effectivePrompt());
    ctx.setPlan(mapper.convertValue(parsed, ExecutionPlanModel.class));
    if (ctx.getPlan() != null) ctx.getConfidence().put("sql", ctx.getPlan().getConfidence());
  }

  public void generateSql(PipelineContext ctx, AnalyticsConnector connector) throws Exception {
    String prompt =
        connector.dialect().dialectHints()
            + "\nSchema:\n"
            + buildSchemaContext(ctx)
            + "\nPlan:\n"
            + mapper.writeValueAsString(ctx.getPlan())
            + "\nQuestion:\n"
            + ctx.effectivePrompt();
    LlmResult result = llm.getActive().complete(LlmPrompts.SQL_GENERATOR_SYSTEM, prompt);
    ctx.recordLlm("sql_generator", result);
    ctx.setSql(result.getText().strip());
    ctx.getConfidence().put("sql", Math.max(ctx.getConfidence().getOrDefault("sql", 0.0), 0.6));
  }

  public String optimize(String sql, String dialect, PipelineContext ctx) {
    sql = SqlUtils.sanitizeSql(sql, dialect);
    int defaultLimit = ((Number) settings.get("guardrails.default_limit", 1000)).intValue();
    String optimized = SqlUtils.injectLimit(sql, defaultLimit);
    if (!optimized.equals(sql) && ctx != null) {
      ctx.getValidationWarnings().add("No LIMIT specified; automatically capped at " + defaultLimit + " rows.");
    }
    return optimized;
  }

  public void estimateCost(PipelineContext ctx, AnalyticsConnector connector) throws Exception {
    String sql = ctx.getOptimizedSql() != null ? ctx.getOptimizedSql() : ctx.getSql();
    var est = connector.estimator().estimate(sql);
    Map<String, Object> cost = new HashMap<>();
    cost.put("estimated_rows_scanned", est.getEstimatedRowsScanned());
    cost.put("estimated_result_rows", est.getEstimatedResultRows());
    cost.put("estimated_runtime_seconds", est.getEstimatedRuntimeSeconds());
    cost.put("scan_bytes", est.getScanBytes());
    cost.put("partition_pruned", est.getPartitionPruned());
    cost.put("join_count", 0);
    cost.put("warnings", List.of());
    cost.put("blocked", false);
    cost.put("suggestions", List.of());
    double maxSeconds = ((Number) settings.get("guardrails.max_estimated_runtime_seconds", 600)).doubleValue();
    if (est.getEstimatedRuntimeSeconds() != null && est.getEstimatedRuntimeSeconds() > maxSeconds) {
      cost.put("blocked", true);
      cost.put("block_reason", "Estimated runtime exceeds configured threshold.");
    }
    ctx.setCost(cost);
  }

  public void execute(PipelineContext ctx, AnalyticsConnector connector) throws Exception {
    String sql = ctx.getOptimizedSql() != null ? ctx.getOptimizedSql() : ctx.getSql();
    int maxRows = ((Number) settings.get("guardrails.max_result_rows", 10000)).intValue();
    int timeout = ((Number) settings.get("guardrails.query_timeout_seconds", 300)).intValue();
    String cacheKey = "result:" + sha256(connector.connectorId() + ":" + sql);
    Map<String, Object> cached = cache.getJson(cacheKey);
    if (cached != null) {
      ctx.setResultColumns(castList(cached.get("columns")));
      ctx.setResultTypes(castList(cached.get("types")));
      ctx.setResultRows(castRows(cached.get("rows")));
      ctx.setRowCount(((Number) cached.getOrDefault("row_count", 0)).intValue());
      ctx.setExecutionTimeMs(0);
      ctx.setTruncated(Boolean.TRUE.equals(cached.get("truncated")));
      ctx.setCacheHit(true);
      return;
    }
    QueryResult result = connector.execute(sql, maxRows, timeout);
    ctx.setResultColumns(result.getColumns());
    ctx.setResultTypes(result.getColumnTypes());
    ctx.setResultRows(result.getRows());
    ctx.setRowCount(result.getRowCount());
    ctx.setExecutionTimeMs(result.getExecutionTimeMs());
    ctx.setTruncated(result.isTruncated());
    Map<String, Object> payload = new HashMap<>();
    payload.put("columns", result.getColumns());
    payload.put("types", result.getColumnTypes());
    payload.put("rows", result.getRows());
    payload.put("row_count", result.getRowCount());
    payload.put("truncated", result.isTruncated());
    cache.setJson(cacheKey, payload, ((Number) settings.get("cache.result_ttl_seconds", 900)).intValue());
  }

  public Map<String, Object> interpret(PipelineContext ctx) {
    try {
      Map<String, Object> parsed =
          llm.completeJson(
              LlmPrompts.INTERPRETER_SYSTEM,
              "Question: "
                  + ctx.effectivePrompt()
                  + "\nColumns: "
                  + ctx.getResultColumns()
                  + "\nSample rows: "
                  + ctx.getResultRows().stream().limit(5).toList());
      return parsed;
    } catch (Exception e) {
      return Map.of(
          "summary",
          "Query returned " + ctx.getRowCount() + " row(s).",
          "insights",
          List.of(),
          "recommendations",
          List.of(),
          "follow_up_questions",
          List.of());
    }
  }

  public Map<String, Object> visualize(PipelineContext ctx) {
    Map<String, Object> out = new HashMap<>();
    out.put("visualization", ctx.getRowCount() == 1 ? "kpi" : "grid");
    out.put("cards", List.<KpiCardDto>of());
    out.put("charts", List.<ChartSpecDto>of());
    TableSpecDto table = new TableSpecDto();
    for (String col : ctx.getResultColumns()) {
      TableColumnDto c = new TableColumnDto();
      c.setField(col);
      c.setHeader(col);
      table.getColumns().add(c);
    }
    for (List<Object> row : ctx.getResultRows()) {
      Map<String, Object> map = new HashMap<>();
      for (int i = 0; i < ctx.getResultColumns().size(); i++) {
        map.put(ctx.getResultColumns().get(i), i < row.size() ? row.get(i) : null);
      }
      table.getRows().add(map);
    }
    table.setTotalRows(ctx.getRowCount());
    table.setTruncated(ctx.isTruncated());
    out.put("table", table);
    return out;
  }

  public ClarificationRequestDto clarification(PipelineContext ctx) {
    ClarificationRequestDto req = new ClarificationRequestDto();
    req.setQuestion("Which table or metric should I use?");
    if (!ctx.getResolvedTables().isEmpty()) {
      for (ResolvedTableModel t : ctx.getResolvedTables().stream().limit(5).toList()) {
        ClarificationOptionDto opt = new ClarificationOptionDto();
        opt.setLabel(t.qualifiedName());
        opt.setValue(t.qualifiedName());
        opt.setDescription(t.getDescription());
        req.getOptions().add(opt);
      }
    }
    return req;
  }

  public Map<String, Object> sqlReview(PipelineContext ctx, String dialect) {
    try {
      return llm.completeJson(
          LlmPrompts.SQL_REVIEWER_SYSTEM,
          "Question:\n" + ctx.effectivePrompt() + "\nSQL:\n" + ctx.getOptimizedSql());
    } catch (Exception e) {
      return Map.of("approved", true, "confidence", 0.8, "issues", List.of());
    }
  }

  public Set<String> knownTables() {
    Set<String> out = new HashSet<>();
    for (CatalogDatabase db : databases.findAll()) {
      for (CatalogTable t : tables.findByDatabaseIdAndIsActiveTrue(db.getId())) {
        out.add((db.getName() + "." + t.getName()).toLowerCase(Locale.ROOT));
      }
    }
    return out;
  }

  public boolean catalogHasTables() {
    return tables.findAll().stream().anyMatch(t -> Boolean.TRUE.equals(t.getIsActive()));
  }

  private void resolveGlossary(PipelineContext ctx, String question, Set<String> qTokens) {
    List<GlossaryTerm> terms = glossary.findAll();
    List<Map.Entry<Double, GlossaryTerm>> scored = new ArrayList<>();
    for (GlossaryTerm term : terms) {
      if (!"approved".equals(term.getStatus())) continue;
      double s = score(question, qTokens, term.getTerm() + " " + term.getDefinition());
      if (s > 0.25) scored.add(Map.entry(s, term));
    }
    scored.sort(Comparator.comparingDouble((Map.Entry<Double, GlossaryTerm> e) -> e.getKey()).reversed());
    for (var e : scored.stream().limit(8).toList()) {
      GlossaryTerm t = e.getValue();
      ctx.getGlossaryContext()
          .add(Map.of("term", t.getTerm(), "definition", t.getDefinition() != null ? t.getDefinition() : ""));
    }
  }

  private void resolveMetrics(PipelineContext ctx, String search, Set<String> qTokens) {
    for (BusinessMetric m : metrics.findAll()) {
      if (!"approved".equals(m.getStatus())) continue;
      double s = score(search, qTokens, m.getName() + " " + m.getDescription());
      if (s > 0.3) {
        ctx.getMetricContext()
            .add(
                Map.of(
                    "name", m.getName(),
                    "expression", m.getExpression(),
                    "table", m.getTableQualifiedName() != null ? m.getTableQualifiedName() : "",
                    "aggregation", m.getAggregation() != null ? m.getAggregation() : "",
                    "description", m.getDescription() != null ? m.getDescription() : ""));
      }
    }
  }

  private void resolveTables(PipelineContext ctx, String search, Set<String> qTokens) {
    List<ResolvedTableModel> resolved = new ArrayList<>();
    for (CatalogTable table : tables.findByIsActiveTrueOrderByUsageCountDescNameAsc()) {
      String dbName =
          databases.findById(table.getDatabaseId()).map(CatalogDatabase::getName).orElse("");
      String candidate =
          table.getName()
              + " "
              + (table.getDescription() != null ? table.getDescription() : "")
              + " "
              + dbName;
      double s = score(search, qTokens, candidate);
      if (s < 0.2) continue;
      ResolvedTableModel rt = new ResolvedTableModel();
      rt.setId(table.getId());
      rt.setDatabase(dbName);
      rt.setName(table.getName());
      rt.setDescription(table.getDescription());
      rt.setRowCount(table.getRowCount());
      if (table.getPartitionColumns() instanceof List<?> parts) {
        rt.setPartitionColumns(parts.stream().map(String::valueOf).toList());
      }
      rt.setScore(s);
      resolved.add(rt);
      if (resolved.size() >= 6) break;
    }
    ctx.setResolvedTables(resolved);
  }

  private void searchLibrary(PipelineContext ctx, String question) {
    String norm = normalizeQuestion(question);
    List<QueryLibraryEntry> entries = library.findByIsActiveTrue();
    QueryLibraryEntry best = null;
    double bestScore = 0;
    for (QueryLibraryEntry e : entries) {
      double s = similarity.apply(norm, e.getNormalizedQuestion());
      if (s > bestScore) {
        bestScore = s;
        best = e;
      }
    }
    double threshold = ((Number) settings.get("pipeline.library_reuse_threshold", 0.82)).doubleValue();
    if (best != null && bestScore >= threshold) {
      LibraryMatchModel match = new LibraryMatchModel();
      match.setEntryId(best.getId());
      match.setQuestion(best.getQuestion());
      match.setSql(best.getSql());
      match.setSimilarity(bestScore);
      if (best.getTablesUsed() instanceof List<?> t) match.setTablesUsed(t.stream().map(String::valueOf).toList());
      ctx.setLibraryMatch(match);
    }
  }

  private String buildSchemaContext(PipelineContext ctx) {
    StringBuilder sb = new StringBuilder();
    for (ResolvedTableModel t : ctx.getResolvedTables()) {
      sb.append("TABLE ").append(t.qualifiedName()).append("\n");
      if (t.getDescription() != null) sb.append("  desc: ").append(t.getDescription()).append("\n");
    }
    return sb.toString();
  }

  private static IntentModel heuristicIntent(String text) {
    IntentModel intent = new IntentModel();
    String lowered = text.toLowerCase(Locale.ROOT);
    if (lowered.contains("table") || lowered.contains("column") || lowered.contains("metadata")) {
      intent.getIntentTypes().set(0, "metadata_question");
      intent.setNeedsData(false);
      intent.setConfidence(0.55);
    } else {
      intent.setConfidence(0.45);
    }
    return intent;
  }

  private static Set<String> tokens(String text) {
    Set<String> out = new HashSet<>();
    for (String t : text.toLowerCase(Locale.ROOT).replaceAll("[^a-zA-Z0-9]+", " ").split("\\s+")) {
      if (t.length() > 2) out.add(t);
    }
    return out;
  }

  private double score(String question, Set<String> qTokens, String candidate) {
    Set<String> cTokens = tokens(candidate);
    if (cTokens.isEmpty() || qTokens.isEmpty()) return 0;
    Set<String> inter = new HashSet<>(qTokens);
    inter.retainAll(cTokens);
    double overlap = inter.size() / (double) qTokens.size();
    double fuzzy = similarity.apply(question.toLowerCase(Locale.ROOT), candidate.toLowerCase(Locale.ROOT));
    return 0.6 * overlap + 0.4 * fuzzy;
  }

  private static String normalizeQuestion(String text) {
    return text.toLowerCase(Locale.ROOT).trim().replaceAll("\\s+", " ");
  }

  private static String sha256(String input) {
    try {
      MessageDigest md = MessageDigest.getInstance("SHA-256");
      byte[] digest = md.digest(input.getBytes(StandardCharsets.UTF_8));
      StringBuilder sb = new StringBuilder();
      for (byte b : digest) sb.append(String.format("%02x", b));
      return sb.toString();
    } catch (Exception e) {
      throw new RuntimeException(e);
    }
  }

  @SuppressWarnings("unchecked")
  private static List<String> castList(Object o) {
    return o instanceof List<?> l ? l.stream().map(String::valueOf).toList() : List.of();
  }

  @SuppressWarnings("unchecked")
  private static List<List<Object>> castRows(Object o) {
    if (!(o instanceof List<?> outer)) return List.of();
    List<List<Object>> rows = new ArrayList<>();
    for (Object row : outer) {
      if (row instanceof List<?> r) rows.add(new ArrayList<>(r));
    }
    return rows;
  }
}
