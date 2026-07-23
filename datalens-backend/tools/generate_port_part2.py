#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/main/java/com/beeline"

def w(rel: str, content: str) -> None:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)

w("core/json/JsonSafe.java", r'''package com.datalens.core.json;

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
''')

w("core/cache/ResultCache.java", r'''package com.datalens.core.cache;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.datalens.config.DataLensSettings;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class ResultCache {
  private static final Logger log = LoggerFactory.getLogger(ResultCache.class);
  private final DataLensSettings settings;
  private final ObjectMapper mapper;
  private final StringRedisTemplate redis;
  private final Map<String, Entry> memory = new ConcurrentHashMap<>();
  private volatile boolean redisFailed;

  public ResultCache(DataLensSettings settings, ObjectMapper mapper, StringRedisTemplate redis) {
    this.settings = settings;
    this.mapper = mapper;
    this.redis = redis;
  }

  public Map<String, Object> getJson(String key) {
    if (!Boolean.TRUE.equals(settings.get("cache.enabled", true))) return null;
    try {
      String raw = redisGet(key);
      if (raw == null) return null;
      return mapper.readValue(raw, new TypeReference<>() {});
    } catch (Exception e) {
      return null;
    }
  }

  public void setJson(String key, Map<String, Object> value, int ttlSeconds) {
    if (!Boolean.TRUE.equals(settings.get("cache.enabled", true))) return;
    try {
      String raw = mapper.writeValueAsString(value);
      redisSet(key, raw, ttlSeconds);
    } catch (Exception e) {
      log.debug("cache set failed: {}", e.getMessage());
    }
  }

  private String redisGet(String key) {
    if (redisFailed) return memoryGet(key);
    try {
      return redis.opsForValue().get(key);
    } catch (Exception e) {
      redisFailed = true;
      log.warn("Redis unavailable, using in-memory cache: {}", e.getMessage());
      return memoryGet(key);
    }
  }

  private void redisSet(String key, String raw, int ttl) {
    if (redisFailed) {
      memory.put(key, new Entry(System.nanoTime() + ttl * 1_000_000_000L, raw));
      return;
    }
    try {
      redis.opsForValue().set(key, raw, Duration.ofSeconds(ttl));
    } catch (Exception e) {
      redisFailed = true;
      memory.put(key, new Entry(System.nanoTime() + ttl * 1_000_000_000L, raw));
    }
  }

  private String memoryGet(String key) {
    Entry e = memory.get(key);
    if (e == null) return null;
    if (e.expiresNs < System.nanoTime()) {
      memory.remove(key);
      return null;
    }
    return e.raw;
  }

  private record Entry(long expiresNs, String raw) {}
}
''')

w("llm/LlmResult.java", r'''package com.datalens.llm;

import java.util.HashMap;
import java.util.Map;
import lombok.Builder;
import lombok.Value;

@Value
@Builder
public class LlmResult {
  String text;
  String model;
  String provider;
  Integer promptTokens;
  Integer completionTokens;
  @Builder.Default Map<String, Object> raw = new HashMap<>();
}
''')

w("llm/LlmProvider.java", r'''package com.datalens.llm;

import java.util.Map;

public interface LlmProvider {
  String providerId();
  LlmResult complete(String systemPrompt, String userMessage) throws Exception;
}
''')

w("llm/LlmJson.java", r'''package com.datalens.llm;

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
''')

print("part2 chunk1 written")
