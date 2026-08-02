package com.datalens.pipeline.stages;

import com.datalens.config.DataLensSettings;
import com.datalens.connectors.AnalyticsConnector;
import com.datalens.connectors.ConnectorRegistry;
import com.datalens.connectors.QueryResult;
import com.datalens.core.cache.ResultCache;
import com.datalens.core.exception.GuardRailViolation;
import com.datalens.core.exception.LLMUnavailable;
import com.datalens.core.exception.ValidationFailed;
import com.datalens.llm.LlmPrompts;
import com.datalens.llm.LlmProviderRegistry;
import com.datalens.model.entity.BusinessMetric;
import com.datalens.model.entity.CatalogColumn;
import com.datalens.model.entity.CatalogDatabase;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.entity.GlossaryTerm;
import com.datalens.model.entity.QueryLibraryEntry;
import com.datalens.model.repository.BusinessMetricRepository;
import com.datalens.model.repository.CatalogColumnRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.model.repository.GlossaryTermRepository;
import com.datalens.model.repository.QueryLibraryEntryRepository;
import com.datalens.pipeline.ExecutionPlanModel;
import com.datalens.pipeline.IntentModel;
import com.datalens.pipeline.LibraryMatchModel;
import com.datalens.pipeline.PipelineContext;
import com.datalens.pipeline.ResolvedTableModel;
import com.datalens.pipeline.SqlReviewer;
import com.datalens.pipeline.SqlUtils;
import com.datalens.pipeline.SqlValidator;
import com.datalens.pipeline.VisualizationPlanner;
import com.datalens.schema.response.ClarificationOptionDto;
import com.datalens.schema.response.ClarificationRequestDto;
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
  private static final int MAX_TABLES = 6;
  private static final int MAX_COLUMNS_PER_TABLE = 40;

  private final DataLensSettings settings;
  private final LlmProviderRegistry llm;
  private final ObjectMapper mapper;
  private final ConnectorRegistry connectors;
  private final ResultCache cache;
  private final SqlValidator validator;
  private final SqlReviewer sqlReviewer;
  private final CatalogTableRepository tables;
  private final CatalogColumnRepository columns;
  private final CatalogDatabaseRepository databases;
  private final GlossaryTermRepository glossary;
  private final BusinessMetricRepository metrics;
  private final QueryLibraryEntryRepository library;
  private final VisualizationPlanner visualizationPlanner;
  private final JaroWinklerSimilarity similarity = new JaroWinklerSimilarity();

  public PipelineStages(
      DataLensSettings settings,
      LlmProviderRegistry llm,
      ObjectMapper mapper,
      ConnectorRegistry connectors,
      ResultCache cache,
      SqlValidator validator,
      SqlReviewer sqlReviewer,
      CatalogTableRepository tables,
      CatalogColumnRepository columns,
      CatalogDatabaseRepository databases,
      GlossaryTermRepository glossary,
      BusinessMetricRepository metrics,
      QueryLibraryEntryRepository library,
      VisualizationPlanner visualizationPlanner) {
    this.settings = settings;
    this.llm = llm;
    this.mapper = mapper;
    this.connectors = connectors;
    this.cache = cache;
    this.validator = validator;
    this.sqlReviewer = sqlReviewer;
    this.tables = tables;
    this.columns = columns;
    this.databases = databases;
    this.glossary = glossary;
    this.metrics = metrics;
    this.library = library;
    this.visualizationPlanner = visualizationPlanner;
  }

  /** Recent session turns rendered for LLM prompts so follow-up questions keep their context. */
  private static String conversationContext(PipelineContext ctx) {
    if (ctx.getHistory() == null || ctx.getHistory().isEmpty()) return "";
    StringBuilder sb = new StringBuilder("Recent conversation (oldest first):\n");
    for (Map<String, String> turn : ctx.getHistory()) {
      String content = turn.getOrDefault("content", "");
      if (content.length() > 500) content = content.substring(0, 500) + "…";
      sb.append(turn.getOrDefault("role", "user")).append(": ").append(content).append("\n");
    }
    return sb.append("\n").toString();
  }

  public void refine(PipelineContext ctx) {
    try {
      Map<String, Object> parsed =
          llm.completeJson(
              LlmPrompts.REFINER_SYSTEM, conversationContext(ctx) + "Message:\n" + ctx.getPrompt(), ctx, "refine");
      if (parsed.get("refined_prompt") != null) ctx.setRefinedPrompt(String.valueOf(parsed.get("refined_prompt")));
    } catch (Exception e) {
      ctx.getWarnings().add("Refiner unavailable: " + e.getMessage());
    }
  }

  public void intent(PipelineContext ctx) {
    try {
      Map<String, Object> parsed =
          llm.completeJson(LlmPrompts.INTENT_SYSTEM, conversationContext(ctx) + ctx.effectivePrompt(), ctx, "intent");
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
    applyClarificationSelection(ctx);
    searchLibrary(ctx, ctx.effectivePrompt());
    double meta =
        ctx.getResolvedTables().stream().mapToDouble(ResolvedTableModel::getScore).max().orElse(0.0);
    ctx.getConfidence().put("metadata", meta);
  }

  public void plan(PipelineContext ctx) throws Exception {
    if (ctx.getResolvedTables().isEmpty()) {
      ExecutionPlanModel empty = new ExecutionPlanModel();
      empty.setRationale("No matching tables found in the catalog.");
      empty.setConfidence(0.0);
      ctx.setPlan(empty);
      return;
    }

    Map<String, Object> parsed;
    try {
      parsed = llm.completeJson(LlmPrompts.PLANNER_SYSTEM, buildPlannerUserBlock(ctx), ctx, "plan");
    } catch (LLMUnavailable e) {
      throw e;
    } catch (Exception e) {
      ctx.getWarnings().add("Planner unavailable: " + e.getMessage());
      parsed = Map.of();
    }

    ExecutionPlanModel plan;
    try {
      plan = parsed.isEmpty() ? new ExecutionPlanModel() : mapper.convertValue(normalizePlanShape(parsed), ExecutionPlanModel.class);
    } catch (Exception e) {
      ctx.getWarnings().add("Planner returned malformed output; using catalog matches instead.");
      plan = new ExecutionPlanModel();
    }
    if (plan == null) plan = new ExecutionPlanModel();
    if (plan.getRationale() == null || plan.getRationale().isBlank()) {
      plan.setRationale(parsed.isEmpty() ? "Planner produced no output." : "");
    }

    Set<String> removed = validatePlanReferences(plan, ctx);
    if (!removed.isEmpty()) {
      ctx.getWarnings()
          .add(
              "Removed unknown identifiers proposed by the model: "
                  + String.join(", ", removed.stream().sorted().toList()));
      plan.setConfidence(Math.max(plan.getConfidence() - 0.2 * removed.size(), 0.1));
    }
    stripPlaceholderFilters(plan, ctx);
    seedPlanTablesFromResolved(plan, ctx);
    ctx.setPlan(plan);
    ctx.getConfidence().put("sql", plan.getConfidence());
  }

  private static final Pattern DATE_COLUMN_HINT =
      Pattern.compile("(?i)(date|_at$|_dt$|period|_time$|timestamp)");
  private static final Pattern DATE_LIKE_VALUE = Pattern.compile("^\\d{4}(-\\d{1,2}(-\\d{1,2})?)?$");

  /**
   * Catches a real failure mode where the model can't ground a required value (most often a time
   * period the question never stated) and, instead of omitting the filter or flagging it, invents
   * a placeholder literal like "specified period" or "TBD". Left alone that string becomes a real
   * WHERE clause that matches nothing, so the query silently "succeeds" with zero rows. When found,
   * the filter is dropped and ctx is flagged so the orchestrator asks the user for the value instead
   * of previewing/executing a query it already knows is incomplete.
   */
  private void stripPlaceholderFilters(ExecutionPlanModel plan, PipelineContext ctx) {
    if (plan.getFilters().isEmpty()) return;
    List<ExecutionPlanModel.PlanFilter> kept = new ArrayList<>();
    List<String> flagged = new ArrayList<>();
    for (ExecutionPlanModel.PlanFilter f : plan.getFilters()) {
      if (isPlaceholderDateFilter(f)) {
        String col = f.getColumn().contains(".") ? f.getColumn().substring(f.getColumn().lastIndexOf('.') + 1) : f.getColumn();
        flagged.add(col);
      } else {
        kept.add(f);
      }
    }
    if (flagged.isEmpty()) return;
    plan.setFilters(kept);
    plan.setConfidence(Math.min(plan.getConfidence(), 0.2));
    ctx.setClarificationQuestion(
        "I need a specific date or date range for "
            + String.join(", ", flagged)
            + " to run this query - which period should I use?");
  }

  private static boolean isPlaceholderDateFilter(ExecutionPlanModel.PlanFilter f) {
    if (f.getColumn() == null || f.getValue() == null) return false;
    if ("is_null".equals(f.getOperator()) || "is_not_null".equals(f.getOperator())) return false;
    String col = f.getColumn().contains(".") ? f.getColumn().substring(f.getColumn().lastIndexOf('.') + 1) : f.getColumn();
    if (!DATE_COLUMN_HINT.matcher(col).find()) return false;
    if (!(f.getValue() instanceof String value)) return false;
    if (value.startsWith("relative:")) return false;
    return !DATE_LIKE_VALUE.matcher(value.trim()).matches();
  }

  public void generateSql(PipelineContext ctx, AnalyticsConnector connector) throws Exception {
    ExecutionPlanModel plan = ctx.getPlan();
    if (plan == null) plan = new ExecutionPlanModel();
    seedPlanTablesFromResolved(plan, ctx);
    if (plan.getTables().isEmpty()) {
      throw new ValidationFailed(
          "I couldn't map your question to any known tables. Try mentioning the dataset explicitly.");
    }
    String dialectName = connector.dialect().sqlglotDialect();
    String system =
        String.format(
            LlmPrompts.SQL_GENERATOR_SYSTEM,
            dialectName.toUpperCase(Locale.ROOT),
            connector.dialect().dialectHints());
    String user =
        conversationContext(ctx)
            + "Execution plan:\n"
            + mapper.writeValueAsString(plan)
            + "\n\nSchema (only these identifiers exist):\n"
            + buildSchemaContext(ctx, plan.getTables())
            + "\n\nRelative date translations: "
            + mapper.writeValueAsString(SqlUtils.relativeDateTranslations())
            + "\n\nQuestion:\n"
            + ctx.effectivePrompt();
    try {
      Map<String, Object> parsed = llm.completeJson(system, user, ctx, "sql_generation");
      String sql = SqlUtils.extractSqlFromLlm(parsed, null);
      boolean planHasProjection = !plan.getColumns().isEmpty() || !plan.getAggregations().isEmpty();
      boolean rejectedStar = !sql.isBlank() && SqlUtils.isSelectStar(sql) && planHasProjection;
      if (rejectedStar) {
        ctx.getWarnings().add("Model produced SELECT *; regenerated with the plan's explicit columns.");
        sql = "";
      }
      if (!sql.isBlank()) {
        ctx.setSql(SqlUtils.sanitizeSql(sql, dialectName));
        Object explanation = parsed.get("explanation");
        if (explanation != null && (plan.getRationale() == null || plan.getRationale().isBlank())) {
          plan.setRationale(String.valueOf(explanation));
        }
        ctx.getConfidence().put("sql", Math.max(ctx.getConfidence().getOrDefault("sql", 0.0), 0.6));
        return;
      }
      if (!rejectedStar) ctx.getWarnings().add("LLM returned empty SQL; using deterministic builder.");
    } catch (LLMUnavailable e) {
      throw e;
    } catch (Exception e) {
      ctx.getWarnings().add("LLM SQL generation failed; using deterministic builder: " + e.getMessage());
    }
    ctx.setSql(SqlUtils.buildDeterministic(plan));
    ctx.setSqlFromDeterministicBuilder(true);
    ctx.getConfidence().put("sql", Math.max(ctx.getConfidence().getOrDefault("sql", 0.0), 0.5));
  }

  /**
   * Sanitize, validate guardrails, optimize, Hive EXPLAIN dry-run, and estimate cost. On rejection the
   * pipeline first asks the LLM to repair the query using the exact error, then falls back to the
   * deterministic plan-built SQL.
   */
  public void prepareSql(PipelineContext ctx, AnalyticsConnector connector) throws Exception {
    String dialect = connector.dialect().sqlglotDialect();
    Set<String> known = knownTables();
    try {
      applySqlChecks(ctx, connector, dialect, known);
      return;
    } catch (GuardRailViolation | com.datalens.core.exception.ConnectorError e) {
      if (ctx.isSqlFromDeterministicBuilder() || ctx.getPlan() == null) throw e;
      if (tryLlmRepair(ctx, connector, dialect, known, e.getMessage())) return;
      ctx.getWarnings().add("Regenerated SQL from the structured plan after Hive rejected the AI-generated query.");
      ctx.setSql(SqlUtils.buildDeterministic(ctx.getPlan()));
      ctx.setSqlFromDeterministicBuilder(true);
      applySqlChecks(ctx, connector, dialect, known);
    }
  }

  /** One-shot LLM repair with the validation error as feedback. Returns true when the fixed SQL passes. */
  private boolean tryLlmRepair(
      PipelineContext ctx, AnalyticsConnector connector, String dialect, Set<String> known, String error) {
    if (ctx.getSql() == null || ctx.getSql().isBlank()) return false;
    try {
      String system =
          String.format(
              LlmPrompts.SQL_REPAIR_SYSTEM,
              dialect.toUpperCase(Locale.ROOT),
              connector.dialect().dialectHints());
      String user =
          "Rejected SQL:\n"
              + ctx.getSql()
              + "\n\nValidation error:\n"
              + SqlUtils.compactConnectorError(error)
              + "\n\nSchema (only these identifiers exist):\n"
              + buildSchemaContext(ctx, ctx.getPlan() != null ? ctx.getPlan().getTables() : List.of())
              + "\nQuestion:\n"
              + ctx.effectivePrompt();
      Map<String, Object> parsed = llm.completeJson(system, user, ctx, "sql_repair");
      String repaired = SqlUtils.extractSqlFromLlm(parsed, null);
      if (repaired.isBlank() || SqlUtils.isSelectStar(repaired)) return false;
      String previous = ctx.getSql();
      ctx.setSql(SqlUtils.sanitizeSql(repaired, dialect));
      try {
        applySqlChecks(ctx, connector, dialect, known);
        ctx.getWarnings().add("Repaired the generated SQL after validation feedback.");
        return true;
      } catch (Exception rejected) {
        ctx.setSql(previous);
        return false;
      }
    } catch (Exception e) {
      return false;
    }
  }

  private void applySqlChecks(PipelineContext ctx, AnalyticsConnector connector, String dialect, Set<String> known)
      throws Exception {
    if (ctx.getSql() != null) ctx.setSql(SqlUtils.sanitizeSql(ctx.getSql(), dialect));
    validator.validate(ctx.getSql() != null ? ctx.getSql() : "", dialect, ctx, known);
    ctx.setOptimizedSql(optimize(ctx.getSql() != null ? ctx.getSql() : "", dialect, ctx));
    validateCompilation(ctx, connector);
    estimateCost(ctx, connector);
  }

  public void validateCompilation(PipelineContext ctx, AnalyticsConnector connector) throws Exception {
    String sql = ctx.getOptimizedSql() != null ? ctx.getOptimizedSql() : ctx.getSql();
    if (sql == null || sql.isBlank()) return;
    connector.estimator().validateCompilation(sql);
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
                  + ctx.getResultRows().stream().limit(5).toList(),
              ctx,
              "interpret");
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
    return visualizationPlanner.run(ctx).toMap();
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
    } else {
      Map<String, String> dbNames = new HashMap<>();
      for (CatalogDatabase db : databases.findAll()) dbNames.put(db.getId(), db.getName());
      for (CatalogTable table :
          tables.findByIsActiveTrueOrderByUsageCountDescNameAsc().stream().limit(5).toList()) {
        String dbName = dbNames.getOrDefault(table.getDatabaseId(), "");
        ClarificationOptionDto opt = new ClarificationOptionDto();
        opt.setLabel(dbName + "." + table.getName());
        opt.setValue(dbName + "." + table.getName());
        opt.setDescription(table.getDescription());
        req.getOptions().add(opt);
      }
    }
    return req;
  }

  public Map<String, Object> sqlReview(PipelineContext ctx, String dialect) {
    return sqlReviewer.review(ctx, dialect);
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

  public String buildMetadataSummary(PipelineContext ctx) {
    List<ResolvedTableModel> toShow =
        isListAllTablesQuestion(ctx.effectivePrompt()) ? loadAllCatalogTables() : ctx.getResolvedTables();
    if (toShow.isEmpty()) {
      return "I couldn't find matching metadata in the catalog.";
    }
    int count = isListAllTablesQuestion(ctx.effectivePrompt()) ? toShow.size() : Math.min(toShow.size(), 5);
    return count == 1
        ? "Found 1 table in the catalog."
        : String.format("Found %,d tables in the catalog.", count);
  }

  public TableSpecDto buildMetadataTable(PipelineContext ctx) {
    List<ResolvedTableModel> toShow =
        isListAllTablesQuestion(ctx.effectivePrompt()) ? loadAllCatalogTables() : ctx.getResolvedTables();
    TableSpecDto table = new TableSpecDto();
    if (toShow.isEmpty()) return table;

    table.getColumns().add(metadataColumn("table", "Table"));
    table.getColumns().add(metadataColumn("description", "Description"));
    table.getColumns().add(metadataColumn("rows", "Rows"));
    table.getColumns().add(metadataColumn("columns", "Columns"));

    int limit = isListAllTablesQuestion(ctx.effectivePrompt()) ? toShow.size() : Math.min(toShow.size(), 5);
    for (ResolvedTableModel t : toShow.stream().limit(limit).toList()) {
      Map<String, Object> row = new HashMap<>();
      row.put("table", t.qualifiedName());
      row.put("description", t.getDescription() != null && !t.getDescription().isBlank() ? t.getDescription() : "—");
      row.put("rows", t.getRowCount() != null ? String.format("%,d", t.getRowCount()) : "—");
      row.put("columns", formatColumnList(t));
      table.getRows().add(row);
    }
    table.setTotalRows(table.getRows().size());
    table.setTruncated(false);
    return table;
  }

  private static TableColumnDto metadataColumn(String field, String header) {
    TableColumnDto col = new TableColumnDto();
    col.setField(field);
    col.setHeader(header);
    col.setDataType("string");
    col.setMetric(false);
    return col;
  }

  private static String formatColumnList(ResolvedTableModel table) {
    List<String> names =
        table.getColumns().stream().map(c -> String.valueOf(c.get("name"))).filter(n -> !n.isBlank()).toList();
    if (names.isEmpty()) return "—";
    int max = 20;
    if (names.size() <= max) return String.join(", ", names);
    return String.join(", ", names.subList(0, max)) + String.format(" … +%d more", names.size() - max);
  }

  public List<ResolvedTableModel> metadataTablesForResponse(PipelineContext ctx) {
    return isListAllTablesQuestion(ctx.effectivePrompt()) ? loadAllCatalogTables() : ctx.getResolvedTables();
  }

  private List<ResolvedTableModel> loadAllCatalogTables() {
    Map<String, String> dbNames = new HashMap<>();
    for (CatalogDatabase db : databases.findAll()) dbNames.put(db.getId(), db.getName());
    List<ResolvedTableModel> out = new ArrayList<>();
    for (CatalogTable table : tables.findByIsActiveTrueOrderByUsageCountDescNameAsc()) {
      out.add(toResolvedTable(table, dbNames.getOrDefault(table.getDatabaseId(), ""), 1.0));
    }
    out.sort(
        Comparator.comparing(ResolvedTableModel::getDatabase)
            .thenComparing(ResolvedTableModel::getName, String.CASE_INSENSITIVE_ORDER));
    return out;
  }

  private static boolean isListAllTablesQuestion(String prompt) {
    if (prompt == null || prompt.isBlank()) return false;
    String p = prompt.toLowerCase(Locale.ROOT);
    boolean mentionsTables = p.contains("table") || p.contains("dataset") || p.contains("catalog");
    boolean listIntent =
        p.contains("all")
            || p.contains("list")
            || p.contains("show")
            || p.contains("what")
            || p.contains("available")
            || p.contains("which");
    return mentionsTables && listIntent;
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
    List<Map.Entry<Double, CatalogTable>> scored = new ArrayList<>();
    Map<String, String> dbNames = new HashMap<>();
    for (CatalogDatabase db : databases.findAll()) dbNames.put(db.getId(), db.getName());

    for (CatalogTable table : tables.findByIsActiveTrueOrderByUsageCountDescNameAsc()) {
      String dbName = dbNames.getOrDefault(table.getDatabaseId(), "");
      List<CatalogColumn> tableColumns = columns.findByTableIdOrderByPositionAsc(table.getId());
      String columnText =
          tableColumns.stream()
              .map(c -> c.getName() + " " + (c.getDescription() != null ? c.getDescription() : ""))
              .reduce((a, b) -> a + " " + b)
              .orElse("");
      String candidate =
          table.getName()
              + " "
              + (table.getDescription() != null ? table.getDescription() : "")
              + " "
              + (table.getTechnicalComment() != null ? table.getTechnicalComment() : "")
              + " "
              + tagsText(table.getTags())
              + " "
              + columnText
              + " "
              + dbName;
      double s = score(search, qTokens, candidate);
      s += Math.min(table.getUsageCount() != null ? table.getUsageCount() : 0, 50) * 0.002;
      if (s > 0.15) scored.add(Map.entry(Math.min(s, 1.0), table));
    }

    scored.sort(Comparator.comparingDouble((Map.Entry<Double, CatalogTable> e) -> e.getKey()).reversed());
    List<ResolvedTableModel> resolved = new ArrayList<>();
    for (var entry : scored.stream().limit(MAX_TABLES).toList()) {
      CatalogTable table = entry.getValue();
      resolved.add(
          toResolvedTable(table, dbNames.getOrDefault(table.getDatabaseId(), ""), entry.getKey(), qTokens));
    }
    ctx.setResolvedTables(resolved);
  }

  private void applyClarificationSelection(PipelineContext ctx) {
    String answer = ctx.getClarificationAnswer();
    if (answer == null || answer.isBlank()) return;
    String key = SqlUtils.normalizeTableRef(answer.strip());
    if (!key.contains(".")) return;
    String[] parts = key.split("\\.", 2);
    for (CatalogDatabase db : databases.findAll()) {
      if (!db.getName().equalsIgnoreCase(parts[0])) continue;
      CatalogTable table =
          tables.findByDatabaseIdAndName(db.getId(), parts[1])
              .orElseGet(
                  () ->
                      tables.findByDatabaseIdAndIsActiveTrue(db.getId()).stream()
                          .filter(t -> t.getName().equalsIgnoreCase(parts[1]))
                          .findFirst()
                          .orElse(null));
      if (table != null && !Boolean.FALSE.equals(table.getIsActive())) {
        ResolvedTableModel selected = toResolvedTable(table, db.getName(), 1.0);
        List<ResolvedTableModel> next = new ArrayList<>();
        next.add(selected);
        for (ResolvedTableModel existing : ctx.getResolvedTables()) {
          if (!existing.qualifiedName().equalsIgnoreCase(key)) next.add(existing);
        }
        ctx.setResolvedTables(next.stream().limit(MAX_TABLES).toList());
      }
      return;
    }
  }

  private ResolvedTableModel toResolvedTable(CatalogTable table, String dbName, double score) {
    return toResolvedTable(table, dbName, score, null);
  }

  private ResolvedTableModel toResolvedTable(
      CatalogTable table, String dbName, double score, Set<String> qTokens) {
    ResolvedTableModel rt = new ResolvedTableModel();
    rt.setId(table.getId());
    rt.setDatabase(dbName);
    rt.setName(table.getName());
    rt.setDescription(table.getDescription() != null ? table.getDescription() : table.getTechnicalComment());
    rt.setRowCount(table.getRowCount());
    if (table.getPartitionColumns() instanceof List<?> parts) {
      rt.setPartitionColumns(parts.stream().map(String::valueOf).toList());
    }
    rt.setScore(score);
    List<Map<String, Object>> colMaps = new ArrayList<>();
    for (CatalogColumn col :
        selectRelevantColumns(columns.findByTableIdOrderByPositionAsc(table.getId()), qTokens)) {
      Map<String, Object> colMap = new HashMap<>();
      colMap.put("name", col.getName());
      colMap.put("data_type", col.getDataType());
      colMap.put(
          "description",
          col.getDescription() != null ? col.getDescription() : col.getTechnicalComment());
      colMap.put("is_partition", Boolean.TRUE.equals(col.getIsPartition()));
      if (col.getSampleValues() instanceof List<?> samples) {
        colMap.put("sample_values", samples.stream().limit(5).map(String::valueOf).toList());
      }
      colMaps.add(colMap);
    }
    rt.setColumns(colMaps);
    return rt;
  }

  /**
   * On wide tables the first-N-by-position window can drop exactly the columns the question needs.
   * Rank columns by relevance to the question instead: question-token matches first, then partition
   * and key-like columns, preserving schema order among the selected set.
   */
  private static List<CatalogColumn> selectRelevantColumns(List<CatalogColumn> all, Set<String> qTokens) {
    if (all.size() <= MAX_COLUMNS_PER_TABLE) return all;
    if (qTokens == null || qTokens.isEmpty()) return all.subList(0, MAX_COLUMNS_PER_TABLE);
    Map<String, Double> scores = new HashMap<>();
    for (CatalogColumn col : all) {
      double s = 0;
      String name = col.getName() != null ? col.getName().toLowerCase(Locale.ROOT) : "";
      for (String token : name.split("_")) {
        if (qTokens.contains(token)) s += 2;
      }
      if (qTokens.contains(name.replace("_", ""))) s += 2;
      String desc = col.getDescription() != null ? col.getDescription().toLowerCase(Locale.ROOT) : "";
      for (String token : qTokens) {
        if (!desc.isEmpty() && desc.contains(token)) s += 1;
      }
      if (Boolean.TRUE.equals(col.getIsPartition())) s += 3;
      if (name.equals("id") || name.endsWith("_id") || name.endsWith("_key") || name.endsWith("_date")
          || name.equals("name") || name.endsWith("_name")) {
        s += 0.5;
      }
      scores.put(col.getId(), s);
    }
    List<CatalogColumn> ranked = new ArrayList<>(all);
    ranked.sort(
        Comparator.comparingDouble((CatalogColumn c) -> -scores.getOrDefault(c.getId(), 0.0))
            .thenComparingInt(c -> c.getPosition() != null ? c.getPosition() : Integer.MAX_VALUE));
    Set<String> keep = new HashSet<>();
    for (CatalogColumn c : ranked.subList(0, MAX_COLUMNS_PER_TABLE)) keep.add(c.getId());
    return all.stream().filter(c -> keep.contains(c.getId())).toList();
  }

  private void seedPlanTablesFromResolved(ExecutionPlanModel plan, PipelineContext ctx) {
    if (!plan.getTables().isEmpty() || ctx.getResolvedTables().isEmpty()) return;
    plan.setTables(
        ctx.getResolvedTables().stream().map(ResolvedTableModel::qualifiedName).limit(3).toList());
    if (plan.getRationale() == null || plan.getRationale().isBlank()) {
      plan.setRationale("Using top catalog table matches.");
    }
    plan.setConfidence(Math.max(plan.getConfidence(), 0.35));
  }

  private String buildPlannerUserBlock(PipelineContext ctx) {
    StringBuilder sb = new StringBuilder();
    sb.append(conversationContext(ctx));
    if (ctx.getPreviousPlan() != null && ctx.getIntent() != null && ctx.getIntent().isFollowUp()) {
      sb.append(
          "Marked as a possible follow-up. Previous execution plan, shown ONLY for reference:\n");
      try {
        sb.append(mapper.writeValueAsString(ctx.getPreviousPlan())).append("\n\n");
      } catch (Exception ignored) {
      }
      sb.append(
          "Build the new plan primarily from the NEW question below. Only carry over a filter, "
              + "column, or grouping from the previous plan if the new question does not specify its "
              + "own and clearly depends on the earlier one (e.g. \"now break that down by region\", "
              + "\"same period last year\"). If the new question states its own metric, columns, or "
              + "grouping, use those instead - never keep the previous plan's aggregations or group_by "
              + "just because a plan was shown above.\n\n");
    }
    sb.append("Question: ").append(ctx.effectivePrompt()).append("\n\n");
    if (ctx.getIntent() != null) {
      try {
        sb.append("Intent analysis: ").append(mapper.writeValueAsString(ctx.getIntent())).append("\n\n");
      } catch (Exception ignored) {
      }
    }
    if (!ctx.getGlossaryContext().isEmpty()) {
      sb.append("Business glossary context: ");
      try {
        sb.append(mapper.writeValueAsString(ctx.getGlossaryContext())).append("\n\n");
      } catch (Exception ignored) {
      }
    }
    if (!ctx.getMetricContext().isEmpty()) {
      sb.append("Defined business metrics: ");
      try {
        sb.append(mapper.writeValueAsString(ctx.getMetricContext())).append("\n\n");
      } catch (Exception ignored) {
      }
    }
    sb.append("Available schema:\n").append(buildSchemaContext(ctx, List.of()));
    return sb.toString();
  }

  private static final Set<String> PLAN_LIST_FIELDS =
      Set.of("tables", "columns", "joins", "filters", "aggregations", "group_by", "order_by");

  /** LLMs occasionally emit a single object for a plan field the schema declares as a list; tolerate it. */
  @SuppressWarnings("unchecked")
  private static Map<String, Object> normalizePlanShape(Map<String, Object> parsed) {
    Map<String, Object> out = new HashMap<>(parsed);
    for (String field : PLAN_LIST_FIELDS) {
      Object value = out.get(field);
      if (value instanceof Map) out.put(field, List.of(value));
    }
    return out;
  }

  private Set<String> validatePlanReferences(ExecutionPlanModel plan, PipelineContext ctx) {
    Set<String> knownTables =
        ctx.getResolvedTables().stream()
            .map(t -> t.qualifiedName().toLowerCase(Locale.ROOT))
            .collect(java.util.stream.Collectors.toSet());
    Set<String> knownColumns = new HashSet<>();
    for (ResolvedTableModel table : ctx.getResolvedTables()) {
      for (Map<String, Object> col : table.getColumns()) {
        knownColumns.add((table.qualifiedName() + "." + col.get("name")).toLowerCase(Locale.ROOT));
      }
      // The resolved model may be pruned for prompt size; accept any real catalog column.
      for (CatalogColumn col : columns.findByTableIdOrderByPositionAsc(table.getId())) {
        knownColumns.add((table.qualifiedName() + "." + col.getName()).toLowerCase(Locale.ROOT));
      }
    }

    Set<String> removed = new HashSet<>();
    plan.setTables(
        plan.getTables().stream()
            .filter(
                t -> {
                  boolean ok = knownTables.contains(t.toLowerCase(Locale.ROOT));
                  if (!ok) removed.add(t);
                  return ok;
                })
            .toList());
    plan.setColumns(
        plan.getColumns().stream()
            .filter(
                c -> {
                  if (columnOk(c, knownColumns)) return true;
                  removed.add(c);
                  return false;
                })
            .toList());
    plan.setGroupBy(
        plan.getGroupBy().stream()
            .filter(
                c -> {
                  if (columnOk(c, knownColumns)) return true;
                  removed.add(c);
                  return false;
                })
            .toList());
    plan.setFilters(
        plan.getFilters().stream()
            .filter(
                f -> {
                  if (columnOk(f.getColumn(), knownColumns)) return true;
                  removed.add(f.getColumn());
                  return false;
                })
            .toList());
    plan.setAggregations(
        plan.getAggregations().stream()
            .filter(
                a -> {
                  if ("*".equals(a.getColumn()) || columnOk(a.getColumn(), knownColumns)) return true;
                  removed.add(a.getColumn());
                  return false;
                })
            .toList());
    plan.setJoins(
        plan.getJoins().stream()
            .filter(
                j -> {
                  boolean ok =
                      j.getLeftTable() != null
                          && j.getRightTable() != null
                          && knownTables.contains(j.getLeftTable().toLowerCase(Locale.ROOT))
                          && knownTables.contains(j.getRightTable().toLowerCase(Locale.ROOT))
                          && columnOk(j.getLeftTable() + "." + j.getLeftColumn(), knownColumns)
                          && columnOk(j.getRightTable() + "." + j.getRightColumn(), knownColumns);
                  if (!ok) removed.add(j.getLeftTable() + "<->" + j.getRightTable());
                  return ok;
                })
            .toList());
    removed.remove(null);
    return removed;
  }

  private static boolean columnOk(String qualified, Set<String> knownColumns) {
    if (qualified == null) return false;
    String q = qualified.toLowerCase(Locale.ROOT);
    if (knownColumns.contains(q)) return true;
    return !q.contains(".");
  }

  private static String tagsText(Object tags) {
    if (tags instanceof List<?> list) {
      return list.stream().map(String::valueOf).reduce((a, b) -> a + " " + b).orElse("");
    }
    return tags != null ? String.valueOf(tags) : "";
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

  /**
   * Schema block for LLM prompts. When {@code onlyTables} is non-empty, restrict to those tables so
   * the SQL generator sees just the plan's tables instead of every semantic-search candidate.
   */
  private String buildSchemaContext(PipelineContext ctx, List<String> onlyTables) {
    Set<String> filter = new HashSet<>();
    for (String t : onlyTables) filter.add(SqlUtils.normalizeTableRef(t));
    List<ResolvedTableModel> tables =
        ctx.getResolvedTables().stream()
            .filter(t -> filter.isEmpty() || filter.contains(t.qualifiedName().toLowerCase(Locale.ROOT)))
            .toList();
    if (tables.isEmpty()) tables = ctx.getResolvedTables();
    StringBuilder sb = new StringBuilder();
    for (ResolvedTableModel t : tables) {
      sb.append("TABLE ").append(t.qualifiedName());
      if (t.getRowCount() != null) sb.append(", ~").append(t.getRowCount()).append(" rows");
      if (t.getDescription() != null) sb.append(" - ").append(t.getDescription());
      sb.append("\n");
      for (Map<String, Object> col : t.getColumns()) {
        sb.append("  - ").append(col.get("name")).append(" (").append(col.get("data_type")).append(")");
        if (Boolean.TRUE.equals(col.get("is_partition"))) sb.append(" [PARTITION]");
        if (col.get("description") != null && !String.valueOf(col.get("description")).isBlank()) {
          sb.append(": ").append(col.get("description"));
        }
        sb.append("\n");
      }
      sb.append("\n");
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
