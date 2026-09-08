package com.datalens.connectors.catalogstore;

import com.datalens.connectors.AnalyticsConnector;
import com.datalens.connectors.MetadataProvider;
import com.datalens.connectors.QueryEstimator;
import com.datalens.connectors.QueryResult;
import com.datalens.connectors.SqlDialect;
import com.datalens.connectors.StatisticsProvider;
import com.datalens.core.exception.ConnectorError;
import com.datalens.core.exception.GuardRailViolation;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import javax.sql.DataSource;

/**
 * Lets the chat pipeline query DataLens's own catalog-governance tables (classification, tags,
 * activity, business rules, abbreviations, glossary) the same way it queries any business
 * connector - through ordinary retrieval and SQL generation, not a special-cased Java method.
 *
 * <p>Runs against a dedicated, small connection pool pointed at the same JDBC URL as the app's own
 * metadata database (see CatalogStoreConnectorConfig) - never the {@code @Primary} datasource
 * Hibernate uses for the app's own entities, so ad-hoc chat queries can't contend with live JPA
 * traffic or interfere with an in-flight transaction.
 */
public class CatalogStoreAnalyticsConnector implements AnalyticsConnector {
  /**
   * Belt-and-suspenders: catalog retrieval/validation is already scoped so these tables are never
   * grounded for this connector (see CatalogStoreMetadataProvider), but a hand-edited preview SQL
   * could in principle name them directly, so execution itself refuses to touch them too.
   */
  private static final Pattern SENSITIVE_TABLE_REFERENCE =
      Pattern.compile(
          "(?i)\\b(chat_sessions|chat_messages|execution_history|saved_queries|feedback|audit_logs|config_overrides)\\b");

  private final String connectorId;
  private final Map<String, Object> config;
  private final DataSource dataSource;
  private final CatalogStoreDialect dialect;
  private final CatalogStoreMetadataProvider metadataProvider;
  private final CatalogStoreStatisticsProvider statisticsProvider;
  private final CatalogStoreQueryEstimator estimator;

  public CatalogStoreAnalyticsConnector(
      String connectorId, Map<String, Object> config, DataSource dataSource, String driverClassName) {
    this.connectorId = connectorId;
    this.config = config;
    this.dataSource = dataSource;
    this.dialect = new CatalogStoreDialect(CatalogStoreDialect.engineFromDriver(driverClassName));
    this.metadataProvider = new CatalogStoreMetadataProvider(dataSource);
    this.statisticsProvider = new CatalogStoreStatisticsProvider(this);
    this.estimator = new CatalogStoreQueryEstimator();
  }

  @Override
  public String connectorId() {
    return connectorId;
  }

  @Override
  public Map<String, Object> config() {
    return config;
  }

  @Override
  public SqlDialect dialect() {
    return dialect;
  }

  @Override
  public MetadataProvider metadataProvider() {
    return metadataProvider;
  }

  @Override
  public StatisticsProvider statisticsProvider() {
    return statisticsProvider;
  }

  @Override
  public QueryEstimator estimator() {
    return estimator;
  }

  QueryResult runSql(String sql, Integer maxRows) throws Exception {
    if (SENSITIVE_TABLE_REFERENCE.matcher(sql).find()) {
      throw new GuardRailViolation(
          "This query references a table that isn't part of the catalog-governance connector.");
    }
    long started = System.nanoTime();
    try (Connection conn = dataSource.getConnection();
        Statement stmt = conn.createStatement()) {
      boolean hasResult = stmt.execute(sql);
      if (!hasResult) {
        return QueryResult.builder()
            .columns(List.of())
            .columnTypes(List.of())
            .rows(List.of())
            .rowCount(0)
            .executionTimeMs(elapsedMs(started))
            .build();
      }
      try (ResultSet rs = stmt.getResultSet()) {
        ResultSetMetaData meta = rs.getMetaData();
        int colCount = meta.getColumnCount();
        List<String> columns = new ArrayList<>();
        List<String> types = new ArrayList<>();
        for (int i = 1; i <= colCount; i++) {
          String label = meta.getColumnLabel(i);
          columns.add(label.contains(".") ? label.substring(label.lastIndexOf('.') + 1) : label);
          types.add(meta.getColumnTypeName(i));
        }
        List<List<Object>> rows = new ArrayList<>();
        int limit = maxRows != null ? maxRows : Integer.MAX_VALUE;
        boolean truncated = false;
        while (rs.next()) {
          if (rows.size() >= limit) {
            truncated = true;
            break;
          }
          List<Object> row = new ArrayList<>();
          for (int i = 1; i <= colCount; i++) row.add(rs.getObject(i));
          rows.add(row);
        }
        return QueryResult.builder()
            .columns(columns)
            .columnTypes(types)
            .rows(rows)
            .rowCount(rows.size())
            .executionTimeMs(elapsedMs(started))
            .truncated(truncated)
            .build();
      }
    }
  }

  private static int elapsedMs(long startedNs) {
    return (int) ((System.nanoTime() - startedNs) / 1_000_000L);
  }

  @Override
  public QueryResult execute(String sql, int maxRows, int timeoutSeconds) throws Exception {
    try {
      return runSql(sql, maxRows);
    } catch (GuardRailViolation e) {
      throw e;
    } catch (Exception e) {
      throw new ConnectorError("Catalog-store query failed: " + e.getMessage());
    }
  }

  @Override
  public List<Object> testConnection() {
    try {
      runSql("SELECT 1", 1);
      return List.of(true, "Connection successful");
    } catch (Exception e) {
      return List.of(false, e.getMessage());
    }
  }
}
