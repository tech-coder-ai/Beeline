package com.datalens.api;

import com.datalens.config.DataLensSettings;
import com.datalens.connectors.AnalyticsConnector;
import com.datalens.connectors.ConnectorRegistry;
import com.datalens.model.repository.AuditLogRepository;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${datalens.api-prefix}")
public class HealthController {
  private final DataLensSettings settings;
  private final AuditLogRepository audit;
  private final ConnectorRegistry connectors;
  public HealthController(DataLensSettings settings, AuditLogRepository audit, ConnectorRegistry connectors) {
    this.settings = settings; this.audit = audit; this.connectors = connectors;
  }
  @GetMapping("/health") public Map<String,String> health() {
    return Map.of("status", "ok", "app", String.valueOf(settings.get("app.name", "DataLens")));
  }
  @GetMapping("/health/deep") public Map<String,String> deep() {
    Map<String,String> checks = new LinkedHashMap<>();
    checks.put("api", "ok");
    try { audit.count(); checks.put("metadata_repository", "ok"); }
    catch (Exception e) { checks.put("metadata_repository", "error: " + e.getMessage()); }
    for (String cid : connectors.listConnectorIds()) {
      try {
        AnalyticsConnector c = connectors.get(cid);
        var res = c.testConnection();
        checks.put("connector:" + cid, Boolean.TRUE.equals(res.get(0)) ? "ok" : String.valueOf(res.get(1)));
      } catch (Exception e) { checks.put("connector:" + cid, "error: " + e.getMessage()); }
    }
    return checks;
  }
}
