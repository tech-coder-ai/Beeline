package com.datalens.schema.response;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
@JsonInclude(JsonInclude.Include.NON_NULL)
public class DataLensResponseDto {
  private String kind = "answer";
  private String executionId;
  private String summary = "";
  private ConfidenceBreakdownDto confidence = new ConfidenceBreakdownDto();
  private String visualization = "text";
  private List<KpiCardDto> cards = new ArrayList<>();
  private List<ChartSpecDto> charts = new ArrayList<>();
  private TableSpecDto table;
  private List<String> insights = new ArrayList<>();
  private List<String> recommendations = new ArrayList<>();
  private List<String> followUpQuestions = new ArrayList<>();
  private ClarificationRequestDto clarification;
  private String sql;
  private SqlExplanationDto sqlExplanation;
  private CostEstimateDto costEstimate;
  private ExecutionStatsDto stats;
  private List<String> tablesUsed = new ArrayList<>();
  private List<String> filtersUsed = new ArrayList<>();
  private List<String> metricsUsed = new ArrayList<>();
  private List<String> warnings = new ArrayList<>();
  private List<ResponseActionDto> actions = new ArrayList<>();
  private Map<String, Object> metadata = new HashMap<>();
  private String error;
}
