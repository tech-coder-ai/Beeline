package com.datalens.connectors.hive;

import com.datalens.connectors.AnalyticsConnector;
import com.datalens.connectors.ColumnStatistics;
import com.datalens.connectors.CostEstimation;
import com.datalens.connectors.HarvestedColumn;
import com.datalens.connectors.HarvestedTable;
import com.datalens.connectors.MetadataProvider;
import com.datalens.connectors.QueryEstimator;
import com.datalens.connectors.QueryResult;
import com.datalens.connectors.SqlDialect;
import com.datalens.connectors.StatisticsProvider;
import com.datalens.core.exception.ConnectorError;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import lombok.Getter;

public class HiveAnalyticsConnector implements AnalyticsConnector {
  @Getter private final String connectorId;
  @Getter private final Map<String, Object> config;
  private final HiveDialect dialect = new HiveDialect();
  private final HiveMetadataProvider metadataProvider = new HiveMetadataProvider(this);
  private final HiveStatisticsProvider statisticsProvider = new HiveStatisticsProvider(this);
  private final HiveQueryEstimator estimator = new HiveQueryEstimator(this);

  public HiveAnalyticsConnector(String connectorId, Map<String, Object> config) {
    this.connectorId = connectorId;
    this.config = config;
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

  Connection openConnection() throws Exception {
    String host = String.valueOf(config.getOrDefault("host", "localhost"));
    int port = ((Number) config.getOrDefault("port", 10000)).intValue();
    String database = String.valueOf(config.getOrDefault("database", "default"));
    String url = "jdbc:hive2://" + host + ":" + port + "/" + database;
    Properties props = new Properties();
    props.setProperty("user", String.valueOf(config.getOrDefault("username", "hive")));
    if (config.get("password") != null) props.setProperty("password", String.valueOf(config.get("password")));
    return DriverManager.getConnection(url, props);
  }

  QueryResult runSql(String sql, Integer maxRows) throws Exception {
    long started = System.nanoTime();
    try (Connection conn = openConnection();
        Statement stmt = conn.createStatement()) {
      @SuppressWarnings("unchecked")
      Map<String, String> sessionSettings = (Map<String, String>) config.get("session_settings");
      if (sessionSettings != null) {
        for (var e : sessionSettings.entrySet()) {
          stmt.execute("SET " + e.getKey() + "=" + e.getValue());
        }
      }
      stmt.setQueryTimeout(((Number) config.getOrDefault("connect_timeout_seconds", 15)).intValue());
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
    int attempts = 1;
    Object retry = config.get("retry");
    if (retry instanceof Map<?, ?> m && m.get("attempts") instanceof Number n) attempts = n.intValue();
    Exception last = null;
    for (int i = 0; i < attempts; i++) {
      try {
        return runSql(sql, maxRows);
      } catch (Exception e) {
        last = e;
      }
    }
    throw new ConnectorError("Hive execution failed after " + attempts + " attempts: " + last.getMessage());
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

  static class HiveDialect implements SqlDialect {
    @Override
    public String sqlDialectName() {
      return "hive";
    }

    @Override
    public String quoteIdentifier(String name) {
      return "`" + name + "`";
    }

    @Override
    public String dialectHints() {
      return """
          Target engine is Apache Hive. Use Hive SQL syntax: backtick identifiers,
          date functions like date_sub/add_months/trunc, prefer explicit JOIN ... ON,
          always filter partition columns when present. Alias every FROM/JOIN table.""";
    }
  }

  static class HiveMetadataProvider implements MetadataProvider {
    private final HiveAnalyticsConnector connector;

    HiveMetadataProvider(HiveAnalyticsConnector connector) {
      this.connector = connector;
    }

    @Override
    public List<String> listDatabases() throws Exception {
      var result = connector.runSql("SHOW DATABASES", null);
      return result.getRows().stream().map(r -> String.valueOf(r.get(0))).toList();
    }

    @Override
    public List<String> listTables(String database) throws Exception {
      var result = connector.runSql("SHOW TABLES IN `" + database + "`", null);
      return result.getRows().stream().map(r -> String.valueOf(r.get(0))).toList();
    }

    @Override
    public HarvestedTable describeTable(String database, String table) throws Exception {
      var result = connector.runSql("DESCRIBE FORMATTED `" + database + "`.`" + table + "`", null);
      return HiveDescribeParser.parse(database, table, result.getRows());
    }
  }

  static class HiveStatisticsProvider implements StatisticsProvider {
    private final HiveAnalyticsConnector connector;

    HiveStatisticsProvider(HiveAnalyticsConnector connector) {
      this.connector = connector;
    }

    @Override
    public ColumnStatistics columnStatistics(String database, String table, String column, int sampleLimit)
        throws Exception {
      var result =
          connector.runSql(
              "SELECT `" + column + "`, COUNT(*) AS c FROM `" + database + "`.`" + table + "` GROUP BY `"
                  + column
                  + "` ORDER BY c DESC LIMIT "
                  + sampleLimit,
              sampleLimit);
      List<Object> samples = result.getRows().stream().map(r -> r.get(0)).toList();
      return ColumnStatistics.builder().sampleValues(new ArrayList<>(samples)).build();
    }
  }

  static class HiveQueryEstimator implements QueryEstimator {
    private final HiveAnalyticsConnector connector;

    HiveQueryEstimator(HiveAnalyticsConnector connector) {
      this.connector = connector;
    }

    @Override
    public CostEstimation estimate(String sql) {
      return CostEstimation.builder().estimatedResultRows(1000).estimatedRuntimeSeconds(5.0).build();
    }
  }
}
