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
import com.datalens.pipeline.SqlUtils;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
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
          Target engine is Apache Hive. Use Hive SQL syntax only:
          - Backtick identifiers; assign short table aliases (e.g. sales AS s) and use alias.column.
          - Never use three-part refs like `db`.`table`.`col` — always alias tables first.
          - Date filters: date_sub, add_months, trunc; never T-SQL/PostgreSQL functions.
          - When GROUP BY is present, ORDER BY must use SELECT aliases, not raw table.column.
          - Prefer explicit JOIN ... ON; filter partition columns when available.
          - No CTE writes, no semicolons, no comments.""";
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
    private static final java.util.regex.Pattern NUM_ROWS =
        java.util.regex.Pattern.compile("Num rows:\\s*([\\d,]+)", java.util.regex.Pattern.CASE_INSENSITIVE);
    private static final java.util.regex.Pattern DATA_SIZE =
        java.util.regex.Pattern.compile("Data size:\\s*([\\d,]+)", java.util.regex.Pattern.CASE_INSENSITIVE);

    private final HiveAnalyticsConnector connector;

    HiveQueryEstimator(HiveAnalyticsConnector connector) {
      this.connector = connector;
    }

    @Override
    public CostEstimation estimate(String sql) {
      CostEstimation.CostEstimationBuilder builder = CostEstimation.builder();
      try {
        QueryResult result = connector.runSql("EXPLAIN " + sql, null);
        String planText = explainText(result);
        java.util.Map<String, Object> details = new java.util.HashMap<>();
        details.put("explain", planText.length() > 4000 ? planText.substring(0, 4000) : planText);
        builder.details(details);

        java.util.List<Integer> rowCounts = new ArrayList<>();
        java.util.regex.Matcher m = NUM_ROWS.matcher(planText);
        while (m.find()) rowCounts.add(parseInt(m.group(1)));
        if (!rowCounts.isEmpty()) {
          int max = rowCounts.stream().max(Integer::compareTo).orElse(0);
          builder.estimatedRowsScanned(max);
          builder.estimatedResultRows(rowCounts.get(rowCounts.size() - 1));
          builder.estimatedRuntimeSeconds(Math.round(max / 2_000_000.0 * 10) / 10.0);
        }
        java.util.regex.Matcher size = DATA_SIZE.matcher(planText);
        java.util.List<Long> sizes = new ArrayList<>();
        while (size.find()) sizes.add(parseLong(size.group(1)));
        if (!sizes.isEmpty()) builder.scanBytes(sizes.stream().max(Long::compareTo).orElse(0L));
        builder.partitionPruned(planText.toLowerCase(Locale.ROOT).contains("partition"));
      } catch (Exception e) {
        java.util.Map<String, Object> details = new java.util.HashMap<>();
        details.put("explain_error", e.getMessage());
        builder.details(details);
      }
      CostEstimation built = builder.build();
      if (built.getEstimatedRowsScanned() == null) {
        return CostEstimation.builder().estimatedRowsScanned(1000).estimatedRuntimeSeconds(5.0).build();
      }
      return built;
    }

    @Override
    public void validateCompilation(String sql) throws Exception {
      try {
        QueryResult result = connector.runSql("EXPLAIN " + sql, null);
        String planText = explainText(result);
        String upper = planText.toUpperCase(Locale.ROOT);
        if (upper.contains("FAILED")
            || planText.contains("SemanticException")
            || planText.contains("ParseException")
            || planText.contains("AnalysisException")
            || planText.contains("Invalid table alias")) {
          throw new com.datalens.core.exception.GuardRailViolation(
              "Hive could not compile this query: " + SqlUtils.compactConnectorError(planText));
        }
      } catch (com.datalens.core.exception.GuardRailViolation e) {
        throw e;
      } catch (Exception e) {
        throw new com.datalens.core.exception.GuardRailViolation(
            "Hive could not compile this query: " + SqlUtils.compactConnectorError(e.getMessage()));
      }
    }

    private static String explainText(QueryResult result) {
      return result.getRows().stream().map(r -> r.isEmpty() ? "" : String.valueOf(r.get(0))).reduce((a, b) -> a + "\n" + b).orElse("");
    }

    private static int parseInt(String raw) {
      try {
        return Integer.parseInt(raw.replace(",", ""));
      } catch (NumberFormatException e) {
        return 0;
      }
    }

    private static long parseLong(String raw) {
      try {
        return Long.parseLong(raw.replace(",", ""));
      } catch (NumberFormatException e) {
        return 0L;
      }
    }
  }
}
