package com.datalens.core.exception;

import java.util.Map;
import lombok.Getter;

@Getter
public class DataLensError extends RuntimeException {
  private final int statusCode;
  private final String code;
  private final String message;
  private final Map<String, Object> detail;

  public DataLensError(int statusCode, String code, String message, Map<String, Object> detail) {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
    this.message = message;
    this.detail = detail == null ? Map.of() : detail;
  }

  public DataLensError(String message) {
    this(500, "internal_error", message, Map.of());
  }
}
