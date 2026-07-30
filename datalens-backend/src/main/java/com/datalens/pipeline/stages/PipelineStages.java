package com.datalens.pipeline.stages;

import com.datalens.config.DataLensSettings;
import com.datalens.connectors.AnalyticsConnector;
import com.datalens.connectors.ConnectorRegistry;
import com.datalens.connectors.QueryResult;
import com.datalens.core.cache.ResultCache;
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
import com.datalens.pipeline.SqlUtils;
import com.datalens.pipeline.SqlValidator;
import com.datalens.pipeline.VisualizationPlanner;
import com.datalens.schema.response.ClarificationOptionDto;
import com.datalens.schema.response.ClarificationRequestDto;
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
    this.tables = tables;
    this.columns = columns;
    this.databases = databases;
    this.glossary = glossary;
    this.metrics = metrics;
    this.library = library;
    this.visualizationPlanner = visualizationPlanner;
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
      parsed = llm.completeJson(LlmPrompts.PLANNER_SYSTEM, buildPlannerUserBlock(ctx));
    } catch (LLMUnavailable e) {
      throw e;
    } catch (Exception e) {
      ctx.getWarnings().add("Planner unavailable: " + e.getMessage());
      parsed = Map.of();
    }

    ExecutionPlanModel plan =
        parsed.isEmpty() ? new ExecutionPlanModel() : mapper.convertValue(parsed, ExecutionPlanModel.class);
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
    seedPlanTablesFromResolved(plan, ctx);
    ctx.setPlan(plan);
    ctx.getConfidence().put("sql", plan.getConfidence());
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
        "Execution plan:\n"
            + mapper.writeValueAsString(plan)
            + "\n\nSchema (only these identifiers exist):\n"
            + buildSchemaContext(ctx)
            + "\n\nQuestion:\n"
            + ctx.effectivePrompt();
    try {
      Map<String, Object> parsed = llm.completeJson(system, user);
      String sql = SqlUtils.extractSqlFromLlm(parsed, null);
      if (!sql.isBlank()) {
        ctx.setSql(SqlUtils.sanitizeSql(sql, dialectName));
        Object explanation = parsed.get("explanation");
        if (explanation != null && (plan.getRationale() == null || plan.getRationale().isBlank())) {
          plan.setRationale(String.valueOf(explanation));
        }
        ctx.getConfidence().put("sql", Math.max(ctx.getConfidence().getOrDefault("sql", 0.0), 0.6));
        return;
      }
      ctx.getWarnings().add("LLM returned empty SQL; using deterministic builder.");
    } catch (LLMUnavailable e) {
      throw e;
    } catch (Exception e) {
      ctx.getWarnings().add("LLM SQL generation failed; using deterministic builder: " + e.getMessage());
    }
    ctx.setSql(SqlUtils.buildDeterministic(plan));
    ctx.getConfidence().put("sql", Math.max(ctx.getConfidence().getOrDefault("sql", 0.0), 0.5));
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

  public String buildMetadataSummary(PipelineContext ctx) {
    List<ResolvedTableModel> toShow =
        isListAllTablesQuestion(ctx.effectivePrompt()) ? loadAllCatalogTables() : ctx.getResolvedTables();
    if (toShow.isEmpty()) {
      return "I couldn't find matching metadata in the catalog.";
    }
    List<String> lines = new ArrayList<>();
    int limit = isListAllTablesQuestion(ctx.effectivePrompt()) ? toShow.size() : Math.min(toShow.size(), 5);
    for (ResolvedTableModel table : toShow.stream().limit(limit).toList()) {
      String cols =
          table.getColumns().stream()
              .limit(12)
              .map(c -> String.valueOf(c.get("name")))
              .reduce((a, b) -> a + ", " + b)
              .orElse("");
      StringBuilder line = new StringBuilder("**").append(table.qualifiedName()).append("**");
      if (table.getDescription() != null && !table.getDescription().isBlank()) {
        line.append(" — ").append(table.getDescription());
      }
      if (table.getRowCount() != null) {
        line.append(" (~").append(String.format("%,d", table.getRowCount())).append(" rows)");
      }
      if (!cols.isBlank()) line.append("\nColumns: ").append(cols);
      lines.add(line.toString());
    }
    return "Here is what I found in the catalog:\n\n" + String.join("\n\n", lines);
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
      resolved.add(toResolvedTable(table, dbNames.getOrDefault(table.getDatabaseId(), ""), entry.getKey()));
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
        columns.findByTableIdOrderByPositionAsc(table.getId()).stream().limit(MAX_COLUMNS_PER_TABLE).toList()) {
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
    if (ctx.getPreviousPlan() != null && ctx.getIntent() != null && ctx.getIntent().isFollowUp()) {
      sb.append("This is a FOLLOW-UP. Previous execution plan (modify it per the new message, keep everything else):\n");
      try {
        sb.append(mapper.writeValueAsString(ctx.getPreviousPlan())).append("\n\n");
      } catch (Exception ignored) {
      }
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
    sb.append("Available schema:\n").append(buildSchemaContext(ctx));
    return sb.toString();
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
                      knownTables.contains(j.getLeftTable().toLowerCase(Locale.ROOT))
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

  private String buildSchemaContext(PipelineContext ctx) {
    StringBuilder sb = new StringBuilder();
    for (ResolvedTableModel t : ctx.getResolvedTables()) {
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
