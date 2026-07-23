package com.datalens.core.exception;

import java.util.Map;

public class ValidationFailed extends DataLensError {
  public ValidationFailed(String message) { this(message, null); }
  public ValidationFailed(String message, Map<String, Object> detail) {
    super(422, "validation_failed", message, detail);
  }
}
