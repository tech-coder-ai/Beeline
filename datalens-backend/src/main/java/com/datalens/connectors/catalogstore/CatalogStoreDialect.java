package com.datalens.connectors.catalogstore;

import com.datalens.connectors.SqlDialect;

/**
 * Dialect for querying DataLens's own metadata store (whichever engine {@code
 * metadata_repository.url} points at - sqlite, postgresql, or oracle) as an ordinary analytics
 * connector, so catalog-governance questions ("what % of columns are classified critical") flow
 * through the same plan/generateSql pipeline as any business question instead of a special case.
 */
public class CatalogStoreDialect implements SqlDialect {
  enum Engine {
    SQLITE,
    POSTGRESQL,
    ORACLE
  }

  private final Engine engine;

  CatalogStoreDialect(Engine engine) {
    this.engine = engine;
  }

  static Engine engineFromDriver(String driverClassName) {
    if (driverClassName == null) return Engine.SQLITE;
    String d = driverClassName.toLowerCase(java.util.Locale.ROOT);
    if (d.contains("postgresql")) return Engine.POSTGRESQL;
    if (d.contains("oracle")) return Engine.ORACLE;
    return Engine.SQLITE;
  }

  @Override
  public String sqlDialectName() {
    return switch (engine) {
      case POSTGRESQL -> "postgresql";
      case ORACLE -> "oracle";
      case SQLITE -> "sqlite";
    };
  }

  @Override
  public String quoteIdentifier(String name) {
    return "\"" + name + "\"";
  }

  @Override
  public String dialectHints() {
    String limitHint =
        engine == Engine.ORACLE
            ? "Use FETCH FIRST n ROWS ONLY (or ROWNUM) instead of LIMIT."
            : "Use standard LIMIT n.";
    return """
        Target engine is the DataLens metadata store (%s) - its own governance catalog, not the
        business data warehouse. Use standard SQL:
        - Double-quote identifiers ("table"."column"); assign short table aliases and use alias.column.
        - %s
        - is_active/is_pii/is_approved-style columns are stored as 0/1; compare with numeric literals.
        - No CTE writes, no semicolons, no comments.
        """
        .formatted(sqlDialectName(), limitHint);
  }
}
