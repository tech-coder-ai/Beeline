package com.datalens.core.exception;

import java.util.Map;

public class ClarificationRequired extends DataLensError {
  public ClarificationRequired(String message) { this(message, null); }
  public ClarificationRequired(String message, Map<String, Object> detail) {
    super(200, "clarification_required", message, detail);
  }
}
