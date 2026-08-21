package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record CalculatedFieldOut(
    String id,
    String tableId,
    String name,
    String expression,
    String description,
    boolean isActive,
    String source,
    java.time.Instant createdAt,
    java.time.Instant updatedAt) {}
