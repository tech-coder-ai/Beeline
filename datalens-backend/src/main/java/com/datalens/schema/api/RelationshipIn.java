package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.List;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record RelationshipIn(
    String fromTableId,
    String toTableId,
    List<String> fromColumns,
    List<String> toColumns,
    String relationshipType,
    String joinType,
    String description,
    Boolean isApproved) {}
