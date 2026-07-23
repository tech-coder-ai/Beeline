package com.datalens.core.exception;

import java.util.Map;

public class NotFound extends DataLensError {
  public NotFound(String message) { this(message, null); }
  public NotFound(String message, Map<String, Object> detail) {
    super(404, "not_found", message, detail);
  }
}
