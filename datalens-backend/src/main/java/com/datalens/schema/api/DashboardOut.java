package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record DashboardOut(String id, String name, String description, Integer refreshIntervalSeconds, boolean isShared, String shareToken, java.time.Instant createdAt, java.time.Instant updatedAt, java.util.List<WidgetOut> widgets) {}
