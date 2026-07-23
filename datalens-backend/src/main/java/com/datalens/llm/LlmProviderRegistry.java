package com.datalens.llm;

import com.datalens.config.DataLensSettings;
import com.datalens.core.exception.LLMUnavailable;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class LlmProviderRegistry {
  private final DataLensSettings settings;
  private final RestClient.Builder restBuilder;
  private final LlmJson llmJson;
  private final ObjectMapper mapper;
  private final Map<String, LlmProvider> instances = new LinkedHashMap<>();

  public LlmProviderRegistry(
      DataLensSettings settings, RestClient.Builder restBuilder, LlmJson llmJson, ObjectMapper mapper) {
    this.settings = settings;
    this.restBuilder = restBuilder;
    this.llmJson = llmJson;
    this.mapper = mapper;
  }

  public void reset() {
    instances.clear();
  }

  @SuppressWarnings("unchecked")
  public LlmProvider get(String providerName) {
    String name = providerName != null ? providerName : String.valueOf(settings.get("llm.active", "openai"));
    if (instances.containsKey(name)) return instances.get(name);
    Map<String, Object> providers = settings.section("llm.providers");
    if (!providers.containsKey(name)) {
      throw new LLMUnavailable("LLM provider '" + name + "' is not configured");
    }
    Map<String, Object> config = (Map<String, Object>) providers.get(name);
    String type = String.valueOf(config.getOrDefault("type", name));
    LlmProvider provider =
        switch (type) {
          case "stellar" -> new StellarLlmProvider(config, restBuilder, settings);
          case "openai" -> new OpenAiLlmProvider(config, restBuilder, settings, mapper);
          default -> throw new LLMUnavailable("Unknown LLM provider type '" + type + "'");
        };
    instances.put(name, provider);
    return provider;
  }

  public LlmProvider getActive() {
    return get(null);
  }

  public Map<String, Object> completeJson(String systemPrompt, String userMessage) throws Exception {
    LlmProvider llm = getActive();
    LlmResult result =
        llm.complete(systemPrompt + "\n\nRespond with valid JSON only. No prose, no markdown fences.", userMessage);
    return llmJson.parseLoosely(result.getText());
  }

  static class OpenAiLlmProvider implements LlmProvider {
    private final Map<String, Object> config;
    private final RestClient client;
    private final DataLensSettings settings;
    private final ObjectMapper mapper;

    OpenAiLlmProvider(
        Map<String, Object> config, RestClient.Builder builder, DataLensSettings settings, ObjectMapper mapper) {
      this.config = config;
      this.settings = settings;
      this.mapper = mapper;
      String base = String.valueOf(config.getOrDefault("base_url", "https://api.openai.com/v1")).replaceAll("/$", "");
      this.client = builder.baseUrl(base).build();
    }

    @Override
    public String providerId() {
      return "openai";
    }

    @Override
    public LlmResult complete(String systemPrompt, String userMessage) {
      int timeout = ((Number) settings.get("llm.request_timeout_seconds", 60)).intValue();
      Map<String, Object> payload = new LinkedHashMap<>();
      payload.put("model", config.getOrDefault("model", "gpt-4o"));
      payload.put("temperature", config.getOrDefault("temperature", 0.1));
      payload.put("max_tokens", config.getOrDefault("max_tokens", 4096));
      payload.put(
          "messages",
          java.util.List.of(
              Map.of("role", "system", "content", systemPrompt),
              Map.of("role", "user", "content", userMessage)));
      RestClient.RequestHeadersSpec<?> req =
          client
              .post()
              .uri("/chat/completions")
              .contentType(MediaType.APPLICATION_JSON)
              .body(payload);
      if (config.get("api_key") != null && !String.valueOf(config.get("api_key")).isBlank()) {
        req = req.header("Authorization", "Bearer " + config.get("api_key"));
      }
      try {
        String body =
            req.retrieve()
                .body(String.class);
        JsonNode data = mapper.readTree(body);
        JsonNode usage = data.path("usage");
        return LlmResult.builder()
            .text(data.path("choices").path(0).path("message").path("content").asText(""))
            .model(data.path("model").asText(String.valueOf(payload.get("model"))))
            .provider(providerId())
            .promptTokens(usage.path("prompt_tokens").isMissingNode() ? null : usage.path("prompt_tokens").asInt())
            .completionTokens(
                usage.path("completion_tokens").isMissingNode() ? null : usage.path("completion_tokens").asInt())
            .build();
      } catch (Exception e) {
        throw new LLMUnavailable("OpenAI-compatible endpoint unavailable: " + e.getMessage());
      }
    }
  }

  static class StellarLlmProvider implements LlmProvider {
    private final Map<String, Object> config;
    private final RestClient client;
    private final DataLensSettings settings;
    private final ObjectMapper mapper = new ObjectMapper();

    StellarLlmProvider(Map<String, Object> config, RestClient.Builder builder, DataLensSettings settings) {
      this.config = config;
      this.settings = settings;
      this.client = builder.build();
    }

    @Override
    public String providerId() {
      return "stellar";
    }

    @Override
    public LlmResult complete(String systemPrompt, String userMessage) {
      String endpoint = String.valueOf(config.get("endpoint"));
      if (endpoint.isBlank()) throw new LLMUnavailable("Stellar provider has no endpoint configured");
      Map<String, Object> payload = Map.of("systemPrompt", systemPrompt, "userMessage", userMessage);
      try {
        String body =
            client
                .post()
                .uri(endpoint)
                .contentType(MediaType.APPLICATION_JSON)
                .body(payload)
                .retrieve()
                .body(String.class);
        String field = String.valueOf(config.getOrDefault("response_field", "response"));
        String text = body;
        if (!field.isBlank()) {
          try {
            JsonNode node = mapper.readTree(body);
            for (String part : field.split("\\.")) node = node.path(part);
            text = node.asText(body);
          } catch (Exception ignored) {
            text = body;
          }
        }
        return LlmResult.builder().text(text).model("stellar").provider(providerId()).build();
      } catch (Exception e) {
        throw new LLMUnavailable("Stellar endpoint unavailable: " + e.getMessage());
      }
    }
  }
}
