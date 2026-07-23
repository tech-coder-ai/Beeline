package com.datalens.api;

import com.datalens.config.DataLensSettings;
import com.datalens.connectors.ConnectorRegistry;
import com.datalens.core.exception.NotFound;
import com.datalens.core.exception.ValidationFailed;
import com.datalens.model.entity.AuditLog;
import com.datalens.model.entity.ExecutionHistory;
import com.datalens.model.entity.SyncRun;
import com.datalens.model.repository.AuditLogRepository;
import com.datalens.model.repository.ExecutionHistoryRepository;
import com.datalens.model.repository.SyncRunRepository;
import com.datalens.schema.api.ConfigUpdate;
import com.datalens.schema.api.ConnectorTestResult;
import com.datalens.schema.api.ConnectorUpsert;
import com.datalens.schema.api.EnrichRequest;
import com.datalens.schema.api.SyncRequest;
import com.datalens.service.AuditService;
import com.datalens.service.EnrichmentService;
import com.datalens.service.LogsPurgeService;
import com.datalens.service.MetadataSyncService;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.data.domain.PageRequest;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${datalens.api-prefix}/admin")
public class AdminController {
  private static final List<String> REDACT_KEYS = List.of("password", "api_key", "secret", "token");

  private final DataLensSettings settings;
  private final ConnectorRegistry connectors;
  private final MetadataSyncService syncService;
  private final EnrichmentService enrichment;
  private final AuditService audit;
  private final AuditLogRepository auditLogs;
  private final ExecutionHistoryRepository executions;
  private final SyncRunRepository syncRuns;
  private final LogsPurgeService purge;
  @PersistenceContext private EntityManager em;

  public AdminController(
      DataLensSettings settings,
      ConnectorRegistry connectors,
      MetadataSyncService syncService,
      EnrichmentService enrichment,
      AuditService audit,
      AuditLogRepository auditLogs,
      ExecutionHistoryRepository executions,
      SyncRunRepository syncRuns,
      LogsPurgeService purge) {
    this.settings = settings;
    this.connectors = connectors;
    this.syncService = syncService;
    this.enrichment = enrichment;
    this.audit = audit;
    this.auditLogs = auditLogs;
    this.executions = executions;
    this.syncRuns = syncRuns;
    this.purge = purge;
  }

  @GetMapping("/connectors")
  public Map<String, Object> connectors() {
    Map<String, Object> definitions = settings.section("connectors.definitions");
    List<Map<String, Object>> list = new ArrayList<>();
    definitions.forEach((id, cfg) -> {
      Map<String, Object> row = new LinkedHashMap<>();
      row.put("id", id);
      if (cfg instanceof Map<?, ?> m) row.putAll(redact(m));
      list.add(row);
    });
    return Map.of(
        "default", connectors.defaultConnectorId(),
        "available_types", connectors.availableTypes(),
        "connectors", list);
  }

  @PostMapping("/connectors")
  public Map<String, String> upsert(@RequestBody ConnectorUpsert body) throws IOException {
    if (body.id() == null || body.id().isBlank()) throw new ValidationFailed("Connector id is required");
    if (body.type() == null || body.type().isBlank()) throw new ValidationFailed("Connector type is required");
    Map<String, Object> definitions = new LinkedHashMap<>(settings.section("connectors.definitions"));
    Map<String, Object> existing = definitions.get(body.id()) instanceof Map<?, ?> m ? new LinkedHashMap<>((Map<String, Object>) m) : new LinkedHashMap<>();
    Map<String, Object> incoming = new LinkedHashMap<>();
    incoming.put("type", body.type());
    incoming.put("display_name", body.displayName());
    incoming.put("host", body.host());
    incoming.put("port", body.port());
    incoming.put("username", body.username());
    incoming.put("password", body.password());
    incoming.put("database", body.database());
    incoming.put("auth", body.auth());
    incoming.put("kerberos_service_name", body.kerberosServiceName());
    incoming.put("principal", body.principal());
    incoming.put("keytab_path", body.keytabPath());
    incoming.put("krb5_ccache", body.krb5Ccache());
    incoming.put("krb5_config", body.krb5Config());
    incoming.put("krb_host", body.krbHost());
    incoming.put("connect_timeout_seconds", body.connectTimeoutSeconds());
    incoming.put("allowed_schemas", body.allowedSchemas());
    incoming.put("read_replicas", body.readReplicas());
    incoming.put("retry", body.retry());
    incoming.put("session_settings", body.sessionSettings());
    definitions.put(body.id(), mergeConnector(existing, incoming));
    settings.persistConnectorDefinitions(definitions);
    connectors.closeAll();
    audit.audit("default", "admin.connector_upsert", null, null, Map.of("id", body.id(), "type", body.type()), "info");
    return Map.of("id", body.id());
  }

  @PutMapping("/connectors/{connectorId}/default")
  public Map<String, String> setDefault(@PathVariable String connectorId) throws IOException {
    if (!settings.section("connectors.definitions").containsKey(connectorId)) {
      throw new NotFound("Connector '" + connectorId + "' is not configured");
    }
    settings.persistConnectorDefinitions(settings.section("connectors.definitions"), connectorId);
    audit.audit("default", "admin.connector_default", null, null, Map.of("connector_id", connectorId), "info");
    return Map.of("default", connectorId);
  }

  @PostMapping("/connectors/{connectorId}/test")
  public ConnectorTestResult test(@PathVariable String connectorId) throws Exception {
    long started = System.nanoTime();
    var res = connectors.get(connectorId).testConnection();
    return new ConnectorTestResult(Boolean.TRUE.equals(res.get(0)), String.valueOf(res.get(1)), (int) ((System.nanoTime() - started) / 1_000_000L));
  }

  @PostMapping("/sync")
  public Map<String, Object> sync(@RequestBody SyncRequest request) {
    audit.audit("default", "admin.sync_trigger", null, null, Map.of("mode", request.mode(), "connector_id", request.connectorId()), "info");
    syncService.syncAsync(request.connectorId(), request.mode() != null ? request.mode() : "incremental");
    return Map.of("started", true, "mode", request.mode());
  }

  @GetMapping("/sync/runs")
  public List<Map<String, Object>> syncRuns() {
    return syncRuns.findTop30ByOrderByCreatedAtDesc().stream().map(this::syncRunMap).toList();
  }

  @PostMapping("/enrich")
  public Map<String, Object> enrich(@RequestBody EnrichRequest request) {
    Map<String, Object> result = enrichment.enrich(request.tableIds());
    audit.audit("default", "admin.enrich_trigger", null, null, result, "info");
    return result;
  }

  @GetMapping("/config")
  public Map<String, Object> config() {
    return redact(settings.raw());
  }

  @PutMapping("/config")
  public Map<String, Object> updateConfig(@RequestBody ConfigUpdate update) {
    Map<String, Object> node = settings.raw();
    String[] path = update.key().split("\\.");
    for (int i = 0; i < path.length - 1; i++) {
      node = (Map<String, Object>) node.computeIfAbsent(path[i], k -> new LinkedHashMap<>());
    }
    node.put(path[path.length - 1], update.value());
    if (update.key().startsWith("connectors.")) connectors.closeAll();
    audit.audit("default", "admin.config_change", null, null, Map.of("key", update.key(), "value", update.value()), "warning");
    return Map.of("key", update.key(), "value", update.value());
  }

  @GetMapping("/feature-flags")
  public Map<String, Object> featureFlags() {
    return settings.section("feature_flags");
  }

  @GetMapping("/logs/audit")
  public List<Map<String, Object>> auditLogs(
      @RequestParam(required = false) String action,
      @RequestParam(required = false) String severity,
      @RequestParam(defaultValue = "100") int limit) {
    return auditLogs.findRecent(PageRequest.of(0, Math.min(limit, 500)), action, severity).stream().map(this::auditMap).toList();
  }

  @GetMapping("/logs/executions")
  public List<Map<String, Object>> executionLogs(
      @RequestParam(required = false) String status,
      @RequestParam(required = false) String search,
      @RequestParam(defaultValue = "100") int limit) {
    return executions.findRecent(PageRequest.of(0, Math.min(limit, 500)), status, search).stream().map(this::executionMap).toList();
  }

  @GetMapping("/analytics/usage")
  public Map<String, Object> usage() {
    long total = executions.count();
    Map<String, Long> byStatus = new LinkedHashMap<>();
    for (Object[] row : executions.countByStatus()) byStatus.put(String.valueOf(row[0]), (Long) row[1]);
    Double avg = executions.avgExecutionMs();
    return Map.of(
        "total_queries", total,
        "by_status", byStatus,
        "avg_execution_ms", avg != null ? Math.round(avg * 10) / 10.0 : null);
  }

  @DeleteMapping("/logs/executions")
  public Map<String, Integer> clearExecutions(@RequestParam(defaultValue = "false") boolean confirm) {
    if (!confirm) throw new ValidationFailed("Pass confirm=true to clear execution history and analytics");
    return purge.purgeExecutions();
  }

  @DeleteMapping("/logs/audit")
  public Map<String, Integer> clearAudit(@RequestParam(defaultValue = "false") boolean confirm) {
    if (!confirm) throw new ValidationFailed("Pass confirm=true to clear the audit trail");
    return purge.purgeAudit();
  }

  @DeleteMapping("/logs")
  public Map<String, Integer> clearAll(
      @RequestParam(defaultValue = "false") boolean confirm,
      @RequestParam(defaultValue = "false") boolean includeSyncRuns) {
    if (!confirm) throw new ValidationFailed("Pass confirm=true to clear logs and analytics");
    return purge.purgeAll(includeSyncRuns);
  }

  private Map<String, Object> syncRunMap(SyncRun r) {
    return Map.of(
        "id", r.getId(), "connector_id", r.getConnectorId(), "mode", r.getMode(), "status", r.getStatus(),
        "tables_synced", r.getTablesSynced(), "columns_synced", r.getColumnsSynced(), "error", r.getError(),
        "created_at", r.getCreatedAt(), "finished_at", r.getFinishedAt());
  }

  private Map<String, Object> auditMap(AuditLog l) {
    return Map.of(
        "id", l.getId(), "user_id", l.getUserId(), "action", l.getAction(), "entity_type", l.getEntityType(),
        "entity_id", l.getEntityId(), "detail", l.getDetail(), "severity", l.getSeverity(), "created_at", l.getCreatedAt());
  }

  private Map<String, Object> executionMap(ExecutionHistory e) {
    return Map.of(
        "id", e.getId(), "prompt", e.getPrompt(), "status", e.getStatus(), "optimized_sql", e.getOptimizedSql(),
        "row_count", e.getRowCount(), "execution_time_ms", e.getExecutionTimeMs(), "confidence", e.getConfidence(),
        "warnings", e.getWarnings(), "error", e.getError(), "llm_model", e.getLlmModel(), "created_at", e.getCreatedAt());
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> redact(Map<String, Object> value) {
    Map<String, Object> out = new LinkedHashMap<>();
    value.forEach((k, v) -> {
      if (v instanceof Map<?, ?> m) out.put(k, redact((Map<String, Object>) m));
      else if (REDACT_KEYS.stream().anyMatch(k.toLowerCase()::contains) && v != null && !String.valueOf(v).isBlank()) out.put(k, "***");
      else out.put(k, v);
    });
    return out;
  }

  private Map<String, Object> mergeConnector(Map<String, Object> existing, Map<String, Object> incoming) {
    Map<String, Object> merged = new LinkedHashMap<>(existing);
    merged.putAll(incoming);
    for (String key : List.of("password", "keytab_path", "krb5_ccache")) {
      Object val = incoming.get(key);
      if ((val == null || String.valueOf(val).isBlank() || "***".equals(val)) && existing.get(key) != null) {
        merged.put(key, existing.get(key));
      }
    }
    return merged;
  }
}
