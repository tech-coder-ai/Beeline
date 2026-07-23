package com.datalens.core.exception;

import java.util.Map;

public class CostThresholdExceeded extends DataLensError {
  public CostThresholdExceeded(String message) { this(message, null); }
  public CostThresholdExceeded(String message, Map<String, Object> detail) {
    super(422, "cost_threshold_exceeded", message, detail);
  }
}
