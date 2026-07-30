package com.datalens.connectors;

public interface QueryEstimator {
  CostEstimation estimate(String sql) throws Exception;

  /** Hive EXPLAIN dry-run; throws when the engine cannot compile the statement. */
  default void validateCompilation(String sql) throws Exception {}
}
