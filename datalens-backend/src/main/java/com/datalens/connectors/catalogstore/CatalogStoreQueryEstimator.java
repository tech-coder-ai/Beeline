package com.datalens.connectors.catalogstore;

import com.datalens.connectors.CostEstimation;
import com.datalens.connectors.QueryEstimator;

/**
 * The catalog store is small (a few thousand rows of governance metadata, not business data), so
 * real cost estimation isn't worth engine-specific EXPLAIN parsing across sqlite/postgres/oracle -
 * a conservative flat estimate is accurate enough for the cost guardrail to make sense of.
 */
public class CatalogStoreQueryEstimator implements QueryEstimator {
  @Override
  public CostEstimation estimate(String sql) {
    return CostEstimation.builder().estimatedRowsScanned(5000).estimatedRuntimeSeconds(0.2).build();
  }
}
