package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record WidgetOut(String id, String title, String widgetType, String size, String sql, String connectorId, java.util.Map<String,Object> visualization, java.util.Map<String,Object> snapshot, String sourceExecutionId, int position) {}
