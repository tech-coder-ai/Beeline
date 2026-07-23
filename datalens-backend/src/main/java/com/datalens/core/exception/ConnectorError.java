package com.datalens.core.exception;

import java.util.Map;

public class ConnectorError extends DataLensError {
  public ConnectorError(String message) { this(message, null); }
  public ConnectorError(String message, Map<String, Object> detail) {
    super(502, "connector_error", message, detail);
  }
}
