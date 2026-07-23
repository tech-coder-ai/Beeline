package com.datalens.connectors;

import com.datalens.config.DataLensSettings;
import com.datalens.connectors.hive.HiveAnalyticsConnector;
import com.datalens.core.exception.ConnectorError;
import com.datalens.core.exception.NotFound;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BiFunction;
import org.springframework.stereotype.Component;

@Component
public class ConnectorRegistry {
  private final DataLensSettings settings;
  private final Map<String, BiFunction<String, Map<String, Object>, AnalyticsConnector>> types =
      new LinkedHashMap<>();
  private final Map<String, AnalyticsConnector> instances = new LinkedHashMap<>();

  public ConnectorRegistry(DataLensSettings settings) {
    this.settings = settings;
    register("hive", HiveAnalyticsConnector::new);
  }

  public void register(String type, BiFunction<String, Map<String, Object>, AnalyticsConnector> factory) {
    types.put(type, factory);
  }

  public List<String> availableTypes() {
    return new ArrayList<>(types.keySet()).stream().sorted().toList();
  }

  @SuppressWarnings("unchecked")
  public List<String> listConnectorIds() {
    return new ArrayList<>(settings.section("connectors.definitions").keySet()).stream().sorted().toList();
  }

  public String defaultConnectorId() {
    return String.valueOf(settings.get("connectors.default", "hive"));
  }

  @SuppressWarnings("unchecked")
  public AnalyticsConnector get(String connectorId) {
    String cid = connectorId != null && !connectorId.isBlank() ? connectorId : defaultConnectorId();
    if (instances.containsKey(cid)) return instances.get(cid);
    Map<String, Object> definitions = settings.section("connectors.definitions");
    if (!definitions.containsKey(cid)) throw new NotFound("Connector '" + cid + "' is not configured");
    Map<String, Object> config = (Map<String, Object>) definitions.get(cid);
    String typeName = String.valueOf(config.get("type"));
    var factory = types.get(typeName);
    if (factory == null) {
      throw new ConnectorError(
          "Connector type '" + typeName + "' is not installed. Available: " + availableTypes());
    }
    AnalyticsConnector instance = factory.apply(cid, config);
    instances.put(cid, instance);
    return instance;
  }

  public void closeAll() {
    for (AnalyticsConnector c : instances.values()) {
      try {
        c.close();
      } catch (Exception ignored) {
      }
    }
    instances.clear();
  }
}
