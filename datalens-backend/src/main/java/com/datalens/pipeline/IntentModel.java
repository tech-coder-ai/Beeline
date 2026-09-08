package com.datalens.pipeline;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.ArrayList;
import java.util.List;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class IntentModel {
  private List<String> intentTypes = new ArrayList<>(List.of("unknown"));
  private String subject = "";
  private List<String> metrics = new ArrayList<>();
  private List<String> dimensions = new ArrayList<>();
  private List<String> filters = new ArrayList<>();
  private String timeRange;
  private String comparison;
  private Integer topN;
  private String order;
  private double confidence = 0.5;
  private List<String> ambiguities = new ArrayList<>();
  @JsonProperty("is_follow_up")
  private boolean followUp;
  @JsonProperty("needs_data")
  private boolean needsData = true;
}
