package com.datalens.pipeline;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ExecutionPlanModel {
  private List<String> tables = new ArrayList<>();
  private List<String> columns = new ArrayList<>();
  private List<PlanJoin> joins = new ArrayList<>();
  private List<PlanFilter> filters = new ArrayList<>();
  private List<PlanAggregation> aggregations = new ArrayList<>();
  private List<String> groupBy = new ArrayList<>();
  private List<Map<String, Object>> orderBy = new ArrayList<>();
  private Integer limit;
  private String timeColumn;
  private String timeGrain;
  private String rationale = "";
  private double confidence = 0.5;

  @Data
  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class PlanJoin {
    private String leftTable;
    private String leftColumn;
    private String rightTable;
    private String rightColumn;
    private String joinType = "inner";
  }

  @Data
  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class PlanFilter {
    private String column;
    private String operator = "=";
    private Object value;
    private String reason = "";
  }

  @Data
  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class PlanAggregation {
    private String function;
    private String column;
    private String alias = "";
    private String reason = "";
  }
}
