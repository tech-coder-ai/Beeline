package com.datalens.connectors.catalogstore;

import com.datalens.connectors.ColumnStatistics;
import com.datalens.connectors.StatisticsProvider;
import java.util.ArrayList;
import java.util.List;

public class CatalogStoreStatisticsProvider implements StatisticsProvider {
  private final CatalogStoreAnalyticsConnector connector;

  CatalogStoreStatisticsProvider(CatalogStoreAnalyticsConnector connector) {
    this.connector = connector;
  }

  @Override
  public ColumnStatistics columnStatistics(String database, String table, String column, int sampleLimit)
      throws Exception {
    if (!CatalogStoreMetadataProvider.ALLOWED_TABLES.contains(table)) {
      return ColumnStatistics.builder().build();
    }
    var result =
        connector.runSql(
            "SELECT \"" + column + "\", COUNT(*) AS c FROM \"" + table + "\" GROUP BY \"" + column
                + "\" ORDER BY c DESC LIMIT " + sampleLimit,
            sampleLimit);
    List<Object> samples = new ArrayList<>();
    for (List<Object> row : result.getRows()) samples.add(row.get(0));
    return ColumnStatistics.builder().sampleValues(samples).build();
  }
}
