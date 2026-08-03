package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;
import java.util.List;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record RelationshipOut(
    String id,
    String fromTableId,
    String fromTableName,
    String fromDatabaseName,
    String toTableId,
    String toTableName,
    String toDatabaseName,
    List<String> fromColumns,
    List<String> toColumns,
    String relationshipType,
    String joinType,
    String description,
    String source,
    Double confidence,
    boolean isApproved,
    Instant createdAt,
    Instant updatedAt) {}
