package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ChatSessionOut(String id, String title, boolean isPinned, boolean isArchived, boolean isShared, String shareToken, java.time.Instant createdAt, java.time.Instant updatedAt, int messageCount) {}
