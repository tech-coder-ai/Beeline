package com.datalens.pipeline;

import com.datalens.config.DataLensSettings;
import com.datalens.connectors.AnalyticsConnector;
import com.datalens.connectors.ConnectorRegistry;
import com.datalens.core.exception.DataLensError;
import com.datalens.core.exception.ConnectorError;
import com.datalens.core.exception.GuardRailViolation;
import com.datalens.core.exception.LLMUnavailable;
import com.datalens.core.exception.ValidationFailed;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.entity.ExecutionHistory;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.model.repository.ExecutionHistoryRepository;
import com.datalens.pipeline.stages.PipelineStages;
import com.datalens.schema.response.DataLensResponseDto;
import com.datalens.schema.response.ConfidenceBreakdownDto;
import com.datalens.schema.response.CostEstimateDto;
import com.datalens.schema.response.ExecutionStatsDto;
import com.datalens.schema.response.SqlExplanationDto;
import com.datalens.service.AuditService;
import com.datalens.service.ExplainService;
import com.datalens.service.QueryLibraryService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class Orchestrator {
  private final DataLensSettings settings;
  private final ConnectorRegistry connectors;
  private final PipelineStages stages;
  private final SqlValidator validator;
  private final ExecutionHistoryRepository historyRepo;
  private final CatalogTableRepository tableRepo;
  private final AuditService audit;
  private final ExplainService explain;
  private final QueryLibraryService library;
  private final ObjectMapper mapper;

  public Orchestrator(
      DataLensSettings settings,
      ConnectorRegistry connectors,
      PipelineStages stages,
      SqlValidator validator,
      ExecutionHistoryRepository historyRepo,
      CatalogTableRepository tableRepo,
      AuditService audit,
      ExplainService explain,
      QueryLibraryService library,
      ObjectMapper mapper) {
    this.settings = settings;
    this.connectors = connectors;
    this.stages = stages;
    this.validator = validator;
    this.historyRepo = historyRepo;
    this.tableRepo = tableRepo;
    this.audit = audit;
    this.explain = explain;
    this.library = library;
    this.mapper = mapper;
  }

  @Transactional
  public DataLensResponseDto run(PipelineContext ctx) {
    ExecutionHistory history = new ExecutionHistory();
    history.setSessionId(ctx.getSessionId());
    history.setUserId(ctx.getUserId());
    history.setConnectorId(ctx.getConnectorId());
    history.setPrompt(ctx.getPrompt());
    historyRepo.save(history);
    ctx.setExecutionId(history.getId());

    DataLensResponseDto response;
    try {
      response = runPipeline(ctx, history);
    } catch (GuardRailViolation e) {
      history.setStatus("blocked");
      history.setError(e.getMessage());
      audit.audit(ctx.getUserId(), "guardrail.block", null, null, Map.of("reason", e.getMessage()), "warning");
      response = errorResponse(ctx, "blocked", e.getMessage());
    } catch (LLMUnavailable e) {
      history.setStatus("failed");
      history.setError(e.getMessage());
      response =
          errorResponse(
              ctx,
              "error",
              "The AI model is currently unavailable ("
                  + e.getMessage()
                  + "). You can still run saved queries or browse metadata.");
    } catch (ValidationFailed e) {
      history.setStatus("failed");
      history.setError(e.getMessage());
      response = errorResponse(ctx, "error", e.getMessage());
    } catch (ConnectorError e) {
      history.setStatus("failed");
      history.setError(e.getMessage());
      response = errorResponse(ctx, "error", SqlUtils.compactConnectorError(e.getMessage()));
    } catch (DataLensError e) {
      history.setStatus("failed");
      history.setError(e.getMessage());
      response = errorResponse(ctx, "error", e.getMessage());
    } catch (Exception e) {
      history.setStatus("failed");
      history.setError(e.getMessage());
      response = errorResponse(ctx, "error", e.getMessage());
    }
    recordHistory(ctx, history, response);
    historyRepo.save(history);
    response.setExecutionId(history.getId());
    return response;
  }

  @Transactional
  public DataLensResponseDto executeAndRespond(PipelineContext ctx, ExecutionHistory history) throws Exception {
    AnalyticsConnector connector = connectors.get(ctx.getConnectorId());
    stages.execute(ctx, connector);
    history.setStatus("executed");
    history.setExecutedAt(Instant.now());
    Map<String, Object> narrative = stages.interpret(ctx);
    Map<String, Object> viz = stages.visualize(ctx);
    SqlExplanationDto sqlExplanation = explain.explain(ctx.getOptimizedSql(), connector.dialect().sqlglotDialect(), ctx.effectivePrompt());
    if (!ctx.isCacheHit() && ctx.getSql() != null) library.recordSuccess(ctx);
    bumpUsage(ctx);
    audit.audit(
        ctx.getUserId(),
        "sql.execute",
        null,
        null,
        Map.of("sql", ctx.getOptimizedSql(), "rows", ctx.getRowCount(), "ms", ctx.getExecutionTimeMs()),
        "info");

    DataLensResponseDto response = new DataLensResponseDto();
    response.setKind("answer");
    response.setSummary(String.valueOf(narrative.getOrDefault("summary", "")));
    response.setConfidence(confidenceBreakdown(ctx));
    response.setVisualization(String.valueOf(viz.get("visualization")));
    response.setTable((com.datalens.schema.response.TableSpecDto) viz.get("table"));
    response.setSql(ctx.getOptimizedSql());
    response.setSqlExplanation(sqlExplanation);
    if (ctx.getCost() != null && !ctx.getCost().isEmpty()) {
      response.setCostEstimate(mapper.convertValue(ctx.getCost(), CostEstimateDto.class));
    }
    ExecutionStatsDto stats = new ExecutionStatsDto();
    stats.setExecutionTimeMs(ctx.getExecutionTimeMs());
    stats.setRowCount(ctx.getRowCount());
    stats.setColumnCount(ctx.getResultColumns().size());
    stats.setConnectorId(ctx.getConnectorId());
    stats.setCacheHit(ctx.isCacheHit());
    stats.setReusedFromLibrary(ctx.getLibraryMatch() != null);
    response.setStats(stats);
    if (ctx.getPlan() != null) response.setTablesUsed(ctx.getPlan().getTables());
    response.setWarnings(ctx.getWarnings());
    return response;
  }

  private DataLensResponseDto runPipeline(PipelineContext ctx, ExecutionHistory history) throws Exception {
    AnalyticsConnector connector = connectors.get(ctx.getConnectorId());
    stages.refine(ctx);
    stages.intent(ctx);
    stages.semanticSearch(ctx);

    if (ctx.getIntent() != null && !ctx.getIntent().isNeedsData()) {
      return metadataAnswer(ctx);
    }
    if (ctx.getResolvedTables().isEmpty() && !stages.catalogHasTables()) {
      history.setStatus("blocked");
      DataLensResponseDto r = new DataLensResponseDto();
      r.setKind("answer");
      r.setSummary(
          "No tables have been synchronized into the DataLens catalog yet, so there is no data to query. "
              + "Ask an administrator to run a metadata sync (Admin -> Connectors & Sync -> Full sync) "
              + "once the analytics connector is reachable, then ask again.");
      r.setVisualization("text");
      r.setConfidence(confidenceBreakdown(ctx));
      r.setWarnings(ctx.getWarnings());
      return r;
    }

    double threshold = ((Number) settings.get("pipeline.confidence.clarification_threshold", 0.65)).doubleValue();
    double overall = overallConfidence(ctx, false);
    boolean mustClarify =
        ((ctx.getIntent() != null
                && !ctx.getIntent().getAmbiguities().isEmpty()
                && overall < threshold
                && (ctx.getClarificationAnswer() == null || ctx.getClarificationAnswer().isBlank()))
            || ctx.getResolvedTables().isEmpty());
    if (mustClarify) {
      history.setStatus("clarification");
      DataLensResponseDto r = new DataLensResponseDto();
      r.setKind("clarification");
      r.setSummary("I need one detail before I query the data.");
      r.setClarification(stages.clarification(ctx));
      r.setConfidence(confidenceBreakdown(ctx));
      r.setTablesUsed(ctx.getResolvedTables().stream().map(ResolvedTableModel::qualifiedName).toList());
      r.setWarnings(ctx.getWarnings());
      return r;
    }

    if (ctx.getLibraryMatch() != null && (ctx.getIntent() == null || !ctx.getIntent().isFollowUp())) {
      ctx.setSql(ctx.getLibraryMatch().getSql());
      ExecutionPlanModel plan = new ExecutionPlanModel();
      plan.setTables(ctx.getLibraryMatch().getTablesUsed());
      plan.setRationale("Reused proven query for: \"" + ctx.getLibraryMatch().getQuestion() + "\"");
      plan.setConfidence(ctx.getLibraryMatch().getSimilarity());
      ctx.setPlan(plan);
      ctx.getConfidence().put("sql", ctx.getLibraryMatch().getSimilarity());
    } else {
      stages.plan(ctx);
      stages.generateSql(ctx, connector);
    }

    String dialect = connector.dialect().sqlglotDialect();
    if (ctx.getSql() != null) ctx.setSql(SqlUtils.sanitizeSql(ctx.getSql(), dialect));
    Set<String> known = stages.knownTables();
    validator.validate(ctx.getSql() != null ? ctx.getSql() : "", dialect, ctx, known);
    ctx.setOptimizedSql(stages.optimize(ctx.getSql() != null ? ctx.getSql() : "", dialect, ctx));
    stages.estimateCost(ctx, connector);

    if (Boolean.TRUE.equals(ctx.getCost().get("blocked"))) {
      history.setStatus("blocked");
      history.setCostEstimate(ctx.getCost());
      DataLensResponseDto r = new DataLensResponseDto();
      r.setKind("blocked");
      r.setSummary(String.valueOf(ctx.getCost().getOrDefault("block_reason", "Query exceeds cost thresholds.")));
      r.setSql(ctx.getOptimizedSql());
      r.setCostEstimate(mapper.convertValue(ctx.getCost(), CostEstimateDto.class));
      r.setConfidence(confidenceBreakdown(ctx));
      if (ctx.getPlan() != null) r.setTablesUsed(ctx.getPlan().getTables());
      r.setWarnings(ctx.getWarnings());
      return r;
    }

    Map<String, Object> previewCfg = settings.section("pipeline.query_preview");
    Object manualReview = previewCfg.get("manual_review");
    if (manualReview == null) manualReview = previewCfg.getOrDefault("enabled", true);
    if (Boolean.TRUE.equals(manualReview) && (ctx.getClarificationAnswer() == null || ctx.getClarificationAnswer().isBlank())) {
      history.setStatus("preview");
      DataLensResponseDto r = new DataLensResponseDto();
      r.setKind("preview");
      r.setSummary("Here is the query I plan to run. Review and execute, or refine your question.");
      r.setSql(ctx.getOptimizedSql());
      r.setSqlExplanation(explain.explain(ctx.getOptimizedSql(), dialect, ctx.effectivePrompt()));
      r.setCostEstimate(mapper.convertValue(ctx.getCost(), CostEstimateDto.class));
      r.setConfidence(confidenceBreakdown(ctx));
      if (ctx.getPlan() != null) r.setTablesUsed(ctx.getPlan().getTables());
      r.setWarnings(ctx.getWarnings());
      Map<String, Object> meta = new HashMap<>();
      meta.put("manual_review", true);
      if (ctx.getPlan() != null) meta.put("rationale", ctx.getPlan().getRationale());
      r.setMetadata(meta);
      return r;
    }

    Map<String, Object> review = stages.sqlReview(ctx, dialect);
    if (!Boolean.TRUE.equals(review.get("approved"))
        && ((Number) review.getOrDefault("confidence", 1.0)).doubleValue() < threshold) {
      history.setStatus("clarification");
      DataLensResponseDto r = new DataLensResponseDto();
      r.setKind("clarification");
      r.setSummary("I need one detail before I query the data.");
      r.setClarification(stages.clarification(ctx));
      r.setSql(ctx.getOptimizedSql());
      r.setConfidence(confidenceBreakdown(ctx));
      return r;
    }

    return executeAndRespond(ctx, history);
  }

  private DataLensResponseDto metadataAnswer(PipelineContext ctx) {
    DataLensResponseDto r = new DataLensResponseDto();
    r.setKind("answer");
    r.setSummary("Here is what I found in the catalog.");
    r.setVisualization("text");
    r.setConfidence(confidenceBreakdown(ctx));
    r.setTablesUsed(ctx.getResolvedTables().stream().map(ResolvedTableModel::qualifiedName).toList());
    r.setWarnings(ctx.getWarnings());
    return r;
  }

  private void recordHistory(PipelineContext ctx, ExecutionHistory history, DataLensResponseDto response) {
    history.setRefinedPrompt(ctx.getRefinedPrompt());
    history.setIntent(ctx.getIntent() != null ? mapper.convertValue(ctx.getIntent(), Map.class) : null);
    history.setExecutionPlan(ctx.getPlan() != null ? mapper.convertValue(ctx.getPlan(), Map.class) : null);
    history.setGeneratedSql(ctx.getSql());
    history.setOptimizedSql(ctx.getOptimizedSql());
    history.setRowCount(ctx.getRowCount() > 0 ? ctx.getRowCount() : null);
    history.setExecutionTimeMs(ctx.getExecutionTimeMs() > 0 ? ctx.getExecutionTimeMs() : null);
    history.setCostEstimate(ctx.getCost());
    history.setConfidence(ctx.getConfidence());
    history.setWarnings(ctx.getWarnings());
    if (ctx.getPlan() != null) history.setTablesUsed(ctx.getPlan().getTables());
    if (ctx.getLibraryMatch() != null) history.setReusedQueryId(ctx.getLibraryMatch().getEntryId());
    if (!ctx.getLlmCalls().isEmpty()) {
      history.setLlmProvider(String.valueOf(ctx.getLlmCalls().get(0).get("provider")));
      history.setLlmModel(String.valueOf(ctx.getLlmCalls().get(0).get("model")));
      Map<String, Object> usage = new HashMap<>();
      usage.put("calls", ctx.getLlmCalls());
      history.setTokenUsage(usage);
    }
    if (history.getStatus() == null && response.getKind() != null) {
      history.setStatus(response.getKind());
    }
  }

  private DataLensResponseDto errorResponse(PipelineContext ctx, String kind, String message) {
    DataLensResponseDto r = new DataLensResponseDto();
    r.setKind(kind);
    r.setSummary(message);
    if ("error".equals(kind)) r.setError(message);
    r.setSql(ctx.getOptimizedSql() != null ? ctx.getOptimizedSql() : ctx.getSql());
    r.setConfidence(confidenceBreakdown(ctx));
    r.setWarnings(ctx.getWarnings());
    return r;
  }

  private ConfidenceBreakdownDto confidenceBreakdown(PipelineContext ctx) {
    ConfidenceBreakdownDto c = new ConfidenceBreakdownDto();
    c.setBusiness(ctx.getConfidence().getOrDefault("business", 0.0));
    c.setMetadata(ctx.getConfidence().getOrDefault("metadata", 0.0));
    c.setSql(ctx.getConfidence().getOrDefault("sql", 0.0));
    c.setOverall(ctx.getConfidence().getOrDefault("overall", 0.0));
    return c;
  }

  private double overallConfidence(PipelineContext ctx, boolean planningDone) {
    double business = ctx.getConfidence().getOrDefault("business", 0.0);
    double metadata = ctx.getConfidence().getOrDefault("metadata", 0.0);
    double sql = ctx.getConfidence().getOrDefault("sql", 0.0);
    double overall = planningDone ? 0.3 * business + 0.3 * metadata + 0.4 * sql : 0.5 * business + 0.5 * metadata;
    if (ctx.getLibraryMatch() != null) overall = Math.max(overall, ctx.getLibraryMatch().getSimilarity());
    ctx.getConfidence().put("overall", overall);
    return overall;
  }

  private void bumpUsage(PipelineContext ctx) {
    if (ctx.getPlan() == null) return;
    for (ResolvedTableModel t : ctx.getResolvedTables()) {
      if (ctx.getPlan().getTables().contains(t.qualifiedName())) {
        tableRepo.findById(t.getId()).ifPresent(row -> row.setUsageCount(row.getUsageCount() + 1));
      }
    }
  }
}
