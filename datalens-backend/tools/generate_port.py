#!/usr/bin/env python3
"""Generate remaining Beeline Spring port sources."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/main/java/com/beeline"

def w(rel: str, content: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)

# --- response DTOs with fields ---
w("schema/response/ConfidenceBreakdownDto.java", """package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class ConfidenceBreakdownDto {
  private double business;
  private double metadata;
  private double sql;
  private double overall;
}
""")

w("schema/response/KpiCardDto.java", """package com.datalens.schema.response;

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
""")

w("schema/response/ChartSeriesDto.java", """package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.ArrayList;
import java.util.List;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class ChartSeriesDto {
  private String name;
  private String type;
  private List<Object> data = new ArrayList<>();
}
""")

w("schema/response/ChartSpecDto.java", """package com.datalens.schema.response;

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
""")

w("schema/response/TableColumnDto.java", """package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class TableColumnDto {
  private String field;
  private String header;
  private String dataType = "string";
  private boolean isMetric;
}
""")

w("schema/response/TableSpecDto.java", """package com.datalens.schema.response;

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
""")

w("schema/response/CostEstimateDto.java", """package com.datalens.schema.response;

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
""")

w("schema/response/SqlExplanationDto.java", """package com.datalens.schema.response;

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
""")

w("schema/response/ClarificationOptionDto.java", """package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class ClarificationOptionDto {
  private String label;
  private String value;
  private String description;
}
""")

w("schema/response/ClarificationRequestDto.java", """package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.ArrayList;
import java.util.List;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class ClarificationRequestDto {
  private String question;
  private List<ClarificationOptionDto> options = new ArrayList<>();
  private boolean allowFreeText = true;
}
""")

w("schema/response/ExecutionStatsDto.java", """package com.datalens.schema.response;

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
""")

w("schema/response/ResponseActionDto.java", """package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class ResponseActionDto {
  private String actionId;
  private String label;
  private String icon;
  private boolean confirm = true;
}
""")

print("response dtos ok")
