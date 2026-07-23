package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ApprovalOut(String id, String entityType, String entityId, String entityLabel, String field, String currentValue, String proposedValue, String source, Double confidence, String rationale, String status, java.time.Instant createdAt) {}
