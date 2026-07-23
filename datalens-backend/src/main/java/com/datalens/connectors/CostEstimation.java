package com.datalens.connectors;

import java.util.HashMap;
import java.util.Map;
import lombok.Builder;
import lombok.Value;

@Value
@Builder
public class CostEstimation {
  Integer estimatedRowsScanned;
  Integer estimatedResultRows;
  Double estimatedRuntimeSeconds;
  Long scanBytes;
  Boolean partitionPruned;
  @Builder.Default Map<String, Object> details = new HashMap<>();
}
