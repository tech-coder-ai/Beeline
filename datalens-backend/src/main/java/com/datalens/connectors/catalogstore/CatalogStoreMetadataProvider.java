package com.datalens.connectors.catalogstore;

import com.datalens.connectors.HarvestedColumn;
import com.datalens.connectors.HarvestedTable;
import com.datalens.connectors.MetadataProvider;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import javax.sql.DataSource;

/**
 * Hardcoded allowlist, not a live schema scan: the metadata store also holds chat_sessions,
 * chat_messages, execution_history, saved_queries, feedback, audit_logs, and config_overrides,
 * which hold other users' prompts/responses/config and must NEVER become queryable via natural
 * language. Restricting the allowlist here (not just by which CatalogTable rows happen to be
 * seeded) means even a future re-sync of this connector can't accidentally expose them.
 */
public class CatalogStoreMetadataProvider implements MetadataProvider {
  static final String DATABASE_NAME = "datalens_catalog";

  static final Set<String> ALLOWED_TABLES =
      Set.of(
          "catalog_tables",
          "catalog_columns",
          "business_rules",
          "abbreviations",
          "glossary_terms",
          "business_terms",
          "synonyms",
          "catalog_relationships");

  private final DataSource dataSource;

  CatalogStoreMetadataProvider(DataSource dataSource) {
    this.dataSource = dataSource;
  }

  @Override
  public List<String> listDatabases() {
    return List.of(DATABASE_NAME);
  }

  @Override
  public List<String> listTables(String database) {
    return ALLOWED_TABLES.stream().sorted().toList();
  }

  @Override
  public HarvestedTable describeTable(String database, String table) throws Exception {
    if (!ALLOWED_TABLES.contains(table)) {
      throw new IllegalArgumentException("Table '" + table + "' is not exposed by the catalog-store connector");
    }
    List<HarvestedColumn> columns = new ArrayList<>();
    try (Connection conn = dataSource.getConnection()) {
      DatabaseMetaData meta = conn.getMetaData();
      int position = 0;
      try (ResultSet rs = meta.getColumns(null, null, table, null)) {
        while (rs.next()) {
          columns.add(
              HarvestedColumn.builder()
                  .name(rs.getString("COLUMN_NAME"))
                  .dataType(rs.getString("TYPE_NAME"))
                  .position(position++)
                  .build());
        }
      }
    }
    return HarvestedTable.builder().database(database).name(table).columns(columns).build();
  }
}
