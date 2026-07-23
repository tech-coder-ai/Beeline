package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ChatMessageOut(String id, String role, String content, java.util.Map<String,Object> responsePayload, String executionId, java.time.Instant createdAt) {}
