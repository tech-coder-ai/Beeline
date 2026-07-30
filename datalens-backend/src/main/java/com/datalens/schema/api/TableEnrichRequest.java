package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.List;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record TableEnrichRequest(
    String description,
    List<String> tags,
    List<GlossaryHint> glossaryHints,
    Boolean refreshRowCount) {

  @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
  public record GlossaryHint(String term, String definition) {}
}
