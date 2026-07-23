package com.datalens.core.exception;

import java.util.Map;

public class LLMUnavailable extends DataLensError {
  public LLMUnavailable(String message) { this(message, null); }
  public LLMUnavailable(String message, Map<String, Object> detail) {
    super(503, "llm_unavailable", message, detail);
  }
}
