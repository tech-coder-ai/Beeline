package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record SavedQueryOut(String id, String name, String description, String sql, String connectorId, String prompt, java.util.List<String> tags, boolean isBookmarked, java.time.Instant lastRunAt, int runCount, java.time.Instant createdAt) {}
