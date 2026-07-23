package com.datalens.api;

import com.datalens.config.DataLensSettings;
import com.datalens.connectors.ConnectorRegistry;
import com.datalens.core.exception.NotFound;
import com.datalens.model.entity.Dashboard;
import com.datalens.model.entity.DashboardWidget;
import com.datalens.model.entity.ExecutionHistory;
import com.datalens.model.entity.Feedback;
import com.datalens.model.entity.SavedQuery;
import com.datalens.model.repository.DashboardRepository;
import com.datalens.model.repository.DashboardWidgetRepository;
import com.datalens.model.repository.ExecutionHistoryRepository;
import com.datalens.model.repository.FeedbackRepository;
import com.datalens.model.repository.SavedQueryRepository;
import com.datalens.pipeline.PipelineContext;
import com.datalens.pipeline.SqlUtils;
import com.datalens.pipeline.SqlValidator;
import com.datalens.pipeline.stages.PipelineStages;
import com.datalens.schema.api.DashboardIn;
import com.datalens.schema.api.DashboardOut;
import com.datalens.schema.api.FeedbackIn;
import com.datalens.schema.api.SavedQueryIn;
import com.datalens.schema.api.SavedQueryOut;
import com.datalens.schema.api.SqlExecuteRequest;
import com.datalens.schema.api.SqlValidateRequest;
import com.datalens.schema.api.WidgetIn;
import com.datalens.schema.api.WidgetOut;
import com.datalens.service.AuditService;
import com.datalens.service.ExplainService;
import com.datalens.service.QueryLibraryService;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${datalens.api-prefix}")
public class WorkspaceController {
  private final ConnectorRegistry connectors;
  private final DataLensSettings settings;
  private final SqlValidator validator;
  private final PipelineStages stages;
  private final ExplainService explain;
  private final SavedQueryRepository queries;
  private final DashboardRepository dashboards;
  private final DashboardWidgetRepository widgets;
  private final FeedbackRepository feedback;
  private final ExecutionHistoryRepository executions;
  private final AuditService audit;
  private final QueryLibraryService library;

  public WorkspaceController(
      ConnectorRegistry connectors,
      DataLensSettings settings,
      SqlValidator validator,
      PipelineStages stages,
      ExplainService explain,
      SavedQueryRepository queries,
      DashboardRepository dashboards,
      DashboardWidgetRepository widgets,
      FeedbackRepository feedback,
      ExecutionHistoryRepository executions,
      AuditService audit,
      QueryLibraryService library) {
    this.connectors = connectors;
    this.settings = settings;
    this.validator = validator;
    this.stages = stages;
    this.explain = explain;
    this.queries = queries;
    this.dashboards = dashboards;
    this.widgets = widgets;
    this.feedback = feedback;
    this.executions = executions;
    this.audit = audit;
    this.library = library;
  }

  @PostMapping("/sql/validate")
  public Map<String, Object> validateSql(@RequestBody SqlValidateRequest request) {
    var connector = connectors.get(request.connectorId());
    var warnings = validator.validate(request.sql(), connector.dialect().sqlglotDialect(), null, null);
    return Map.of("valid", true, "warnings", warnings);
  }

  @PostMapping("/sql/execute")
  public Map<String, Object> executeSql(@RequestBody SqlExecuteRequest request) throws Exception {
    var connector = connectors.get(request.connectorId());
    String dialect = connector.dialect().sqlglotDialect();
    validator.validate(request.sql(), dialect, null, null);
    PipelineContext ctx = new PipelineContext();
    ctx.setPrompt("(direct sql)");
    ctx.setConnectorId(request.connectorId());
    String sql = stages.optimize(request.sql(), dialect, ctx);
    int maxRows =
        Math.min(
            request.limit() != null ? request.limit() : ((Number) settings.get("guardrails.max_result_rows", 10000)).intValue(),
            ((Number) settings.get("guardrails.max_result_rows", 10000)).intValue());
    var result = connector.execute(sql, maxRows, ((Number) settings.get("guardrails.query_timeout_seconds", 300)).intValue());
    ctx.setResultColumns(result.getColumns());
    ctx.setResultTypes(result.getColumnTypes());
    ctx.setResultRows(result.getRows());
    ctx.setRowCount(result.getRowCount());
    ctx.setTruncated(result.isTruncated());
    Map<String, Object> viz = stages.visualize(ctx);
    audit.audit("default", "sql.execute_direct", null, null, Map.of("sql", sql, "rows", result.getRowCount()), "info");
    Map<String, Object> out = new HashMap<>();
    out.put("columns", result.getColumns());
    out.put("rows", result.getRows());
    out.put("row_count", result.getRowCount());
    out.put("execution_time_ms", result.getExecutionTimeMs());
    out.put("truncated", result.isTruncated());
    out.put("visualization", viz.get("visualization"));
    out.put("charts", viz.get("charts"));
    out.put("cards", viz.get("cards"));
    out.put("table", viz.get("table"));
    out.put("sql", sql);
    return out;
  }

  @PostMapping("/sql/explain")
  public Object explainSql(@RequestBody SqlValidateRequest request) {
    var connector = connectors.get(request.connectorId());
    return explain.explain(request.sql(), connector.dialect().sqlglotDialect(), request.question());
  }

  @GetMapping("/queries")
  public List<SavedQueryOut> listQueries() {
    return queries.findAllByOrderByUpdatedAtDesc().stream().map(this::toQueryOut).toList();
  }

  @PostMapping("/queries")
  public SavedQueryOut saveQuery(@RequestBody SavedQueryIn in) {
    SavedQuery q = new SavedQuery();
    q.setName(in.name());
    q.setDescription(in.description());
    q.setSql(in.sql());
    q.setConnectorId(in.connectorId());
    q.setPrompt(in.prompt());
    q.setTags(in.tags());
    return toQueryOut(queries.save(q));
  }

  @PatchMapping("/queries/{queryId}/bookmark")
  public Map<String, Object> bookmark(@PathVariable String queryId) {
    SavedQuery q = queries.findById(queryId).orElseThrow(() -> new NotFound("Saved query not found"));
    q.setIsBookmarked(!Boolean.TRUE.equals(q.getIsBookmarked()));
    queries.save(q);
    return Map.of("id", queryId, "is_bookmarked", q.getIsBookmarked());
  }

  @DeleteMapping("/queries/{queryId}")
  public Map<String, String> deleteQuery(@PathVariable String queryId) {
    queries.deleteById(queryId);
    return Map.of("deleted", queryId);
  }

  @PostMapping("/queries/{queryId}/run")
  public Map<String, Object> runQuery(@PathVariable String queryId) throws Exception {
    SavedQuery q = queries.findById(queryId).orElseThrow(() -> new NotFound("Saved query not found"));
    Map<String, Object> result = executeSql(new SqlExecuteRequest(q.getSql(), q.getConnectorId(), null));
    q.setRunCount(q.getRunCount() + 1);
    q.setLastRunAt(Instant.now());
    queries.save(q);
    return result;
  }

  @GetMapping("/dashboards")
  public List<DashboardOut> dashboards() {
    return dashboards.findAllByOrderByUpdatedAtDesc().stream().map(this::toDashboardOut).toList();
  }

  @PostMapping("/dashboards")
  public DashboardOut createDashboard(@RequestBody DashboardIn in) {
    Dashboard d = new Dashboard();
    d.setName(in.name());
    d.setDescription(in.description());
    d.setRefreshIntervalSeconds(in.refreshIntervalSeconds());
    d = dashboards.save(d);
    return new DashboardOut(
        d.getId(), d.getName(), d.getDescription(), d.getRefreshIntervalSeconds(), false, null, d.getCreatedAt(), d.getUpdatedAt(), List.of());
  }

  @GetMapping("/dashboards/{dashboardId}")
  public DashboardOut getDashboard(@PathVariable String dashboardId) {
    return toDashboardOut(dashboards.findById(dashboardId).orElseThrow(() -> new NotFound("Dashboard not found")));
  }

  @PostMapping("/dashboards/{dashboardId}/widgets")
  public Map<String, String> addWidget(@PathVariable String dashboardId, @RequestBody WidgetIn in) {
    Dashboard d = dashboards.findById(dashboardId).orElseThrow(() -> new NotFound("Dashboard not found"));
    DashboardWidget w = new DashboardWidget();
    w.setDashboardId(dashboardId);
    w.setTitle(in.title());
    w.setWidgetType(in.widgetType());
    w.setSize(in.size() != null ? in.size() : "half");
    w.setSql(in.sql());
    w.setConnectorId(in.connectorId());
    w.setVisualization(in.visualization());
    w.setSnapshot(in.snapshot());
    w.setSourceExecutionId(in.sourceExecutionId());
    w.setPosition(widgets.findByDashboardId(dashboardId).size());
    widgets.save(w);
    return Map.of("id", w.getId(), "dashboard_id", dashboardId);
  }

  @DeleteMapping("/dashboards/{dashboardId}/widgets/{widgetId}")
  public Map<String, String> removeWidget(@PathVariable String dashboardId, @PathVariable String widgetId) {
    DashboardWidget w = widgets.findById(widgetId).orElseThrow(() -> new NotFound("Widget not found"));
    if (!dashboardId.equals(w.getDashboardId())) throw new NotFound("Widget not found");
    widgets.delete(w);
    return Map.of("deleted", widgetId);
  }

  @PatchMapping("/dashboards/{dashboardId}/share")
  public Map<String, String> share(@PathVariable String dashboardId) {
    Dashboard d = dashboards.findById(dashboardId).orElseThrow(() -> new NotFound("Dashboard not found"));
    d.setIsShared(true);
    if (d.getShareToken() == null) d.setShareToken(token());
    dashboards.save(d);
    return Map.of("share_token", d.getShareToken());
  }

  @DeleteMapping("/dashboards/{dashboardId}")
  public Map<String, String> deleteDashboard(@PathVariable String dashboardId) {
    dashboards.deleteById(dashboardId);
    return Map.of("deleted", dashboardId);
  }

  @PostMapping("/feedback")
  public Map<String, String> feedback(@RequestBody FeedbackIn in) {
    Feedback f = new Feedback();
    f.setExecutionId(in.executionId());
    f.setMessageId(in.messageId());
    f.setRating(in.rating());
    f.setCategory(in.category());
    f.setComment(in.comment());
    f.setCorrectedSql(in.correctedSql());
    feedback.save(f);
    if (in.executionId() != null) library.applyFeedback(in.executionId(), "up".equals(in.rating()));
    audit.audit("default", "feedback.submit", null, null, Map.of("rating", in.rating(), "category", in.category()), "info");
    return Map.of("id", f.getId());
  }

  @GetMapping("/feedback")
  public List<Map<String, Object>> listFeedback(@RequestParam(required = false) String status) {
    return feedback.findRecent(status).stream().limit(200)
        .map(
            f -> {
              Map<String, Object> m = new HashMap<>();
              m.put("id", f.getId());
              m.put("execution_id", f.getExecutionId());
              m.put("rating", f.getRating());
              m.put("category", f.getCategory());
              m.put("comment", f.getComment());
              m.put("corrected_sql", f.getCorrectedSql());
              m.put("status", f.getStatus());
              m.put("created_at", f.getCreatedAt());
              return m;
            })
        .toList();
  }

  @GetMapping("/executions/{executionId}")
  public Map<String, Object> getExecution(@PathVariable String executionId) {
    ExecutionHistory e = executions.findById(executionId).orElseThrow(() -> new NotFound("Execution not found"));
    Map<String, Object> m = new HashMap<>();
    m.put("id", e.getId());
    m.put("prompt", e.getPrompt());
    m.put("refined_prompt", e.getRefinedPrompt());
    m.put("intent", e.getIntent());
    m.put("execution_plan", e.getExecutionPlan());
    m.put("generated_sql", e.getGeneratedSql());
    m.put("optimized_sql", e.getOptimizedSql());
    m.put("status", e.getStatus());
    m.put("row_count", e.getRowCount());
    m.put("execution_time_ms", e.getExecutionTimeMs());
    m.put("cost_estimate", e.getCostEstimate());
    m.put("confidence", e.getConfidence());
    m.put("warnings", e.getWarnings());
    m.put("error", e.getError());
    m.put("llm_model", e.getLlmModel());
    m.put("llm_provider", e.getLlmProvider());
    m.put("token_usage", e.getTokenUsage());
    m.put("tables_used", e.getTablesUsed());
    m.put("created_at", e.getCreatedAt());
    return m;
  }

  private SavedQueryOut toQueryOut(SavedQuery q) {
    Object tags = q.getTags() instanceof List<?> l ? l.stream().map(String::valueOf).toList() : List.of();
    return new SavedQueryOut(
        q.getId(),
        q.getName(),
        q.getDescription(),
        q.getSql(),
        q.getConnectorId(),
        q.getPrompt(),
        (List<String>) tags,
        Boolean.TRUE.equals(q.getIsBookmarked()),
        q.getLastRunAt(),
        q.getRunCount() != null ? q.getRunCount() : 0,
        q.getCreatedAt());
  }

  private DashboardOut toDashboardOut(Dashboard d) {
    List<WidgetOut> ws =
        widgets.findByDashboardIdOrderByPositionAsc(d.getId()).stream()
            .map(
                w ->
                    new WidgetOut(
                        w.getId(),
                        w.getTitle(),
                        w.getWidgetType(),
                        w.getSize(),
                        w.getSql(),
                        w.getConnectorId(),
                        w.getVisualization() instanceof Map<?, ?> m ? (Map<String, Object>) m : Map.of(),
                        w.getSnapshot() instanceof Map<?, ?> m ? (Map<String, Object>) m : Map.of(),
                        w.getSourceExecutionId(),
                        w.getPosition() != null ? w.getPosition() : 0))
            .toList();
    return new DashboardOut(
        d.getId(),
        d.getName(),
        d.getDescription(),
        d.getRefreshIntervalSeconds(),
        Boolean.TRUE.equals(d.getIsShared()),
        d.getShareToken(),
        d.getCreatedAt(),
        d.getUpdatedAt(),
        ws);
  }

  private static String token() {
    byte[] bytes = new byte[18];
    new SecureRandom().nextBytes(bytes);
    return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
  }
}
