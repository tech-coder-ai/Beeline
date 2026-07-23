package com.datalens.core.cache;

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
