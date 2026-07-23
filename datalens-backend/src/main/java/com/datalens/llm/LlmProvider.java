package com.datalens.llm;

import java.util.Map;

public interface LlmProvider {
  String providerId();
  LlmResult complete(String systemPrompt, String userMessage) throws Exception;
}
