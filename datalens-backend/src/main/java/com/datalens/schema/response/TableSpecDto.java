package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class TableSpecDto {
  private List<TableColumnDto> columns = new ArrayList<>();
  private List<Map<String, Object>> rows = new ArrayList<>();
  private int totalRows;
  private boolean truncated;
}
