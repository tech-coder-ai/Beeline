package com.datalens.connectors;

public interface SqlDialect {
  String sqlDialectName();

  default String sqlglotDialect() {
    return sqlDialectName();
  }

  String quoteIdentifier(String name);

  default String dialectHints() {
    return "";
  }
}
