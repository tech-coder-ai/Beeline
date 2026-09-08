package com.datalens.schema.api;

import java.time.Instant;

public record BusinessRuleOut(
    String id,
    String name,
    String scope,
    String entity,
    String columnName,
    String ruleType,
    String statement,
    String status,
    String source,
    Instant createdAt,
    Instant updatedAt) {}
