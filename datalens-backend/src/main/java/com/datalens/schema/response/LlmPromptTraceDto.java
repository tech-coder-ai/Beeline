package com.datalens.schema.response;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.Data;

@Data
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class LlmPromptTraceDto {
  private String purpose = "";
  private String provider = "";
  private String model = "";
  private String systemPrompt = "";
  private String userMessage = "";
  private String response = "";
  private Integer promptTokens;
  private Integer completionTokens;
}
