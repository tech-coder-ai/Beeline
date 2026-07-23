package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.ArrayList;
import java.util.List;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class ChartSpecDto {
  private String chartType;
  private String title;
  private List<Object> categories = new ArrayList<>();
  private List<ChartSeriesDto> series = new ArrayList<>();
  private String xLabel;
  private String yLabel;
  private boolean stacked;
}
