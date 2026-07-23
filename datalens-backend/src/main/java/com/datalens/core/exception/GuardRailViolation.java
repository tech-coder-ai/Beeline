package com.datalens.core.exception;

import java.util.Map;

public class GuardRailViolation extends DataLensError {
  public GuardRailViolation(String message) { this(message, null); }
  public GuardRailViolation(String message, Map<String, Object> detail) {
    super(422, "guardrail_violation", message, detail);
  }
}
