package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ColumnOut(String id, String name, int position, String dataType, String inferredSemanticType, String description, Object tags, String classification, boolean isPii, boolean isPartition, Double nullPercentage, Integer distinctCount, Object sampleValues, Object topValues) {}
