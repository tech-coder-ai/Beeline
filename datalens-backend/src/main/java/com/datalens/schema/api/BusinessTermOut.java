package com.datalens.schema.api;

import java.time.Instant;

public record BusinessTermOut(
    String id,
    String term,
    String entity,
    String columnName,
    String value,
    String tableId,
    String status,
    String source,
    Instant createdAt,
    Instant updatedAt) {}
