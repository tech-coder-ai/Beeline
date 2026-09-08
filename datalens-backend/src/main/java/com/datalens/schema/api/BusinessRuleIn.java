package com.datalens.schema.api;

public record BusinessRuleIn(
    String name, String scope, String entity, String columnName, String ruleType, String statement) {}
