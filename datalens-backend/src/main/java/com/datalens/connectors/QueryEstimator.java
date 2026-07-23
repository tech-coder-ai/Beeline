package com.datalens.connectors;

public interface QueryEstimator {
  CostEstimation estimate(String sql) throws Exception;
}
