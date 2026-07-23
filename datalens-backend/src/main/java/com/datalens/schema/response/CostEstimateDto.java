package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.ArrayList;
import java.util.List;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class CostEstimateDto {
  private Integer estimatedRowsScanned;
  private Integer estimatedResultRows;
  private Double estimatedRuntimeSeconds;
  private Long scanBytes;
  private Boolean partitionPruned;
  private int joinCount;
  private List<String> warnings = new ArrayList<>();
  private boolean blocked;
  private String blockReason;
  private List<String> suggestions = new ArrayList<>();
}
