package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class ExecutionStatsDto {
  private Integer executionTimeMs;
  private Integer rowCount;
  private Integer columnCount;
  private String connectorId;
  private boolean cacheHit;
  private boolean reusedFromLibrary;
}
