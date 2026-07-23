package com.datalens.connectors;

public interface StatisticsProvider {
  ColumnStatistics columnStatistics(String database, String table, String column, int sampleLimit)
      throws Exception;
}
