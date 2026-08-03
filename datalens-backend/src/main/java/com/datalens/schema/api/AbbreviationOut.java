package com.datalens.schema.api;

import java.time.Instant;

public record AbbreviationOut(
    String id,
    String abbreviation,
    String canonical,
    String description,
    String status,
    String source,
    Instant createdAt,
    Instant updatedAt) {}
