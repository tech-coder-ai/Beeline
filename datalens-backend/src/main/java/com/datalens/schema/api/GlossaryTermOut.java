package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record GlossaryTermOut(String id, String term, String definition, String businessMeaning, java.util.List<String> examples, String owner, java.util.List<String> tags, java.util.List<String> synonyms, String status, String source, java.time.Instant createdAt) {}
