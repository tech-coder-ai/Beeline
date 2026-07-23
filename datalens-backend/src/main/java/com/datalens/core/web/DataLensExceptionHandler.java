package com.datalens.core.web;

import com.datalens.core.exception.DataLensError;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DataLensExceptionHandler {
  @ExceptionHandler(DataLensError.class)
  public ResponseEntity<Map<String, Object>> handle(DataLensError exc) {
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("code", exc.getCode());
    body.put("message", exc.getMessage());
    body.put("detail", exc.getDetail());
    return ResponseEntity.status(exc.getStatusCode()).body(body);
  }
}
