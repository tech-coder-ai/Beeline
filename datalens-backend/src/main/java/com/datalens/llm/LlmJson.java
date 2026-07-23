package com.datalens.llm;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class LlmJson {
  private static final Pattern FENCED = Pattern.compile("```(?:json)?\\s*(\\{.*?})\\s*```", Pattern.DOTALL);
  private final ObjectMapper mapper;

  public LlmJson(ObjectMapper mapper) {
    this.mapper = mapper;
  }

  public Map<String, Object> parseLoosely(String text) {
    if (text == null) return Map.of();
    String t = text.strip();
    Matcher m = FENCED.matcher(t);
    if (m.find()) t = m.group(1);
    else {
      int start = t.indexOf('{');
      int end = t.lastIndexOf('}');
      if (start >= 0 && end > start) t = t.substring(start, end + 1);
    }
    try {
      Map<String, Object> parsed = mapper.readValue(t, new TypeReference<>() {});
      return parsed == null ? Map.of() : parsed;
    } catch (Exception e) {
      return Map.of();
    }
  }
}
