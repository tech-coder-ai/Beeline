package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class KpiCardDto {
  private String label;
  private String value;
  private Double rawValue;
  private String unit;
  private Double trend;
  private String trendLabel;
  private String severity = "neutral";
}
