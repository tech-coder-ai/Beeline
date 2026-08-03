package com.datalens.schema.api;

public record BusinessTermIn(
    String term, String entity, String columnName, String value, String tableId) {}
