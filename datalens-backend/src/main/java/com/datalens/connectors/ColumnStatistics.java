package com.datalens.connectors;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import lombok.Builder;
import lombok.Value;

@Value
@Builder
public class ColumnStatistics {
  Integer distinctCount;
  Double nullPercentage;
  String minValue;
  String maxValue;
  @Builder.Default List<Object> sampleValues = new ArrayList<>();
  @Builder.Default List<Map<String, Object>> topValues = new ArrayList<>();
}
