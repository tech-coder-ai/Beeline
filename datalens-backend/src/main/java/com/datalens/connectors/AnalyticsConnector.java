package com.datalens.connectors;

import java.util.List;
import java.util.Map;

public interface AnalyticsConnector {
  String connectorId();

  Map<String, Object> config();

  SqlDialect dialect();

  MetadataProvider metadataProvider();

  StatisticsProvider statisticsProvider();

  QueryEstimator estimator();

  QueryResult execute(String sql, int maxRows, int timeoutSeconds) throws Exception;

  /** @return [ok, message] */
  List<Object> testConnection() throws Exception;

  default void close() {}
}
