package com.datalens.llm;

import java.util.HashMap;
import java.util.Map;
import lombok.Builder;
import lombok.Value;

@Value
@Builder
public class LlmResult {
  String text;
  String model;
  String provider;
  Integer promptTokens;
  Integer completionTokens;
  @Builder.Default Map<String, Object> raw = new HashMap<>();
}
