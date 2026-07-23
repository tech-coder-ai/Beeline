package com.datalens.core.json;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class JsonSafe {
  private final ObjectMapper mapper;

  public JsonSafe(ObjectMapper mapper) {
    this.mapper = mapper;
  }

  @SuppressWarnings("unchecked")
  public Map<String, Object> toMap(Object value) {
    return mapper.convertValue(value, Map.class);
  }
}
