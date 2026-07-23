package com.datalens.connectors;

import java.util.List;
import java.util.Map;
import lombok.Builder;
import lombok.Value;

@Value
@Builder
public class QueryResult {
  List<String> columns;
  List<String> columnTypes;
  List<List<Object>> rows;
  int rowCount;
  int executionTimeMs;
  @Builder.Default boolean truncated = false;
}
