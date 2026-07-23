package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.ArrayList;
import java.util.List;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class SqlExplanationDto {
  private String summary = "";
  private List<String> tableReasons = new ArrayList<>();
  private List<String> filterReasons = new ArrayList<>();
  private List<String> aggregationReasons = new ArrayList<>();
  private List<String> groupingReasons = new ArrayList<>();
}
