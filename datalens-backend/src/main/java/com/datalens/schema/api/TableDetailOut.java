package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record TableDetailOut(String id, String name, String tableType, String description, String owner, String steward, Object tags, String classification, Integer rowCount, Long sizeBytes, String storageFormat, Object partitionColumns, java.time.Instant lastSyncedAt, int usageCount, String databaseName, int columnCount, java.util.List<ColumnOut> columns) {}
