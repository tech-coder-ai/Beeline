package com.datalens.connectors.catalogstore;

import com.datalens.model.entity.CatalogColumn;
import com.datalens.model.entity.CatalogDatabase;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.repository.CatalogColumnRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogTableRepository;
import java.util.List;
import java.util.Map;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * Registers DataLens's own governance tables (see CatalogStoreMetadataProvider.ALLOWED_TABLES) as
 * ordinary catalog rows under the "catalog_store" connector, with real descriptions - so a
 * governance question ("what % of columns are classified critical") is found by the SAME
 * documentation-weighted retrieval that finds any business table, and answered with ordinary
 * generated SQL, instead of a bespoke code path. Idempotent and safe to run on every boot: creates
 * missing rows and refreshes descriptions so a later change to this class takes effect on restart
 * without a manual migration.
 */
@Component
public class CatalogStoreSelfDescribingSeeder implements ApplicationRunner {
  private static final String CONNECTOR_ID = "catalog_store";
  private static final String DATABASE_NAME = CatalogStoreMetadataProvider.DATABASE_NAME;

  private record ColSpec(String name, String dataType, String description) {}

  private record TableSpec(String name, String description, String classification, List<ColSpec> columns) {}

  private static final List<TableSpec> TABLES =
      List.of(
          new TableSpec(
              "catalog_tables",
              "Registry of every table known to the DataLens catalog across all connectors: "
                  + "classification, ownership, activity, usage, and documentation status.",
              "internal",
              List.of(
                  new ColSpec("id", "VARCHAR", "Unique table identifier."),
                  new ColSpec("database_id", "VARCHAR", "Owning database identifier."),
                  new ColSpec("name", "VARCHAR", "Table name as it exists in the source connector."),
                  new ColSpec("description", "TEXT", "Steward-written business description of the table."),
                  new ColSpec("classification", "VARCHAR", "Governance classification (e.g. public, internal, confidential, critical)."),
                  new ColSpec("owner", "VARCHAR", "Business owner of the table."),
                  new ColSpec("steward", "VARCHAR", "Data steward responsible for the table's documentation."),
                  new ColSpec("row_count", "INTEGER", "Approximate row count at last sync."),
                  new ColSpec("usage_count", "INTEGER", "How many times this table has been used to answer a question."),
                  new ColSpec("is_active", "BOOLEAN", "Whether the table is actively maintained (0/1)."),
                  new ColSpec("is_enabled", "BOOLEAN", "Whether the table is enabled for use in SQL generation (0/1)."))),
          new TableSpec(
              "catalog_columns",
              "Registry of every column known to the DataLens catalog: data type, classification, "
                  + "PII flag, and documentation status, one row per column of every cataloged table.",
              "internal",
              List.of(
                  new ColSpec("id", "VARCHAR", "Unique column identifier."),
                  new ColSpec("table_id", "VARCHAR", "Owning table identifier."),
                  new ColSpec("name", "VARCHAR", "Column name as it exists in the source connector."),
                  new ColSpec("data_type", "VARCHAR", "Column's data type in the source connector."),
                  new ColSpec("description", "TEXT", "Steward-written business description of the column."),
                  new ColSpec("classification", "VARCHAR", "Governance classification (e.g. public, internal, confidential, critical, restricted)."),
                  new ColSpec("is_pii", "BOOLEAN", "Whether the column holds personally identifiable information (0/1)."),
                  new ColSpec("is_partition", "BOOLEAN", "Whether the column is a partition key in the source connector (0/1)."),
                  new ColSpec("is_primary_key", "BOOLEAN", "Whether the column is the table's primary key (0/1)."))),
          new TableSpec(
              "business_rules",
              "Steward-authored governance policy and conditional business logic (exclusions, "
                  + "classification definitions, calculation rules), scoped globally or to a "
                  + "specific table or column.",
              "internal",
              List.of(
                  new ColSpec("id", "VARCHAR", "Unique rule identifier."),
                  new ColSpec("name", "VARCHAR", "Short name of the rule."),
                  new ColSpec("scope", "VARCHAR", "global, table, or column - who the rule applies to."),
                  new ColSpec("entity", "VARCHAR", "Qualified table name the rule applies to, when scope is table or column."),
                  new ColSpec("column_name", "VARCHAR", "Column name the rule applies to, when scope is column."),
                  new ColSpec("rule_type", "VARCHAR", "Free-text category, e.g. filter, calculation, governance."),
                  new ColSpec("statement", "TEXT", "The rule itself, in plain language."),
                  new ColSpec("status", "VARCHAR", "approved or pending."))),
          new TableSpec(
              "abbreviations",
              "Abbreviation and acronym expansions used across the catalog (e.g. CDE = Critical "
                  + "Data Element), optionally mapped to a catalog classification for governance "
                  + "questions about counts/percentages.",
              "internal",
              List.of(
                  new ColSpec("id", "VARCHAR", "Unique abbreviation identifier."),
                  new ColSpec("abbreviation", "VARCHAR", "The short form, e.g. CDE."),
                  new ColSpec("entity", "VARCHAR", "Qualified table name or free-text domain the abbreviation relates to."),
                  new ColSpec("value", "TEXT", "The expanded meaning, e.g. Critical Data Element."),
                  new ColSpec("maps_to_classification", "VARCHAR", "Catalog classification value this abbreviation refers to, when it names a governance classification rather than a business value."),
                  new ColSpec("status", "VARCHAR", "approved or pending."))),
          new TableSpec(
              "glossary_terms",
              "Business vocabulary definitions used to interpret analytical questions.",
              "internal",
              List.of(
                  new ColSpec("id", "VARCHAR", "Unique term identifier."),
                  new ColSpec("term", "VARCHAR", "The business term."),
                  new ColSpec("definition", "TEXT", "Plain-language definition of the term."),
                  new ColSpec("business_meaning", "TEXT", "Additional business context for the term."),
                  new ColSpec("owner", "VARCHAR", "Business owner of the definition."),
                  new ColSpec("status", "VARCHAR", "approved or pending."))),
          new TableSpec(
              "business_terms",
              "Bindings from a business term to a specific entity.column = value, e.g. "
                  + "\"active customer\" -> customers.status = ACTIVE.",
              "internal",
              List.of(
                  new ColSpec("id", "VARCHAR", "Unique binding identifier."),
                  new ColSpec("term", "VARCHAR", "The business term, e.g. active customer."),
                  new ColSpec("entity", "VARCHAR", "Qualified table name the binding applies to."),
                  new ColSpec("column_name", "VARCHAR", "Column name the binding applies to."),
                  new ColSpec("value", "TEXT", "The value that satisfies the term, e.g. ACTIVE."),
                  new ColSpec("status", "VARCHAR", "approved or pending."))),
          new TableSpec(
              "synonyms",
              "Alternate wording mapped to a canonical glossary term, used to resolve informal "
                  + "phrasing in questions.",
              "internal",
              List.of(
                  new ColSpec("id", "VARCHAR", "Unique synonym identifier."),
                  new ColSpec("term_id", "VARCHAR", "Referenced glossary_terms.id."),
                  new ColSpec("synonym", "VARCHAR", "The alternate wording."),
                  new ColSpec("confidence", "DECIMAL", "Confidence score for the synonym mapping."))),
          new TableSpec(
              "catalog_relationships",
              "Steward-approved join paths between cataloged tables.",
              "internal",
              List.of(
                  new ColSpec("id", "VARCHAR", "Unique relationship identifier."),
                  new ColSpec("from_table_id", "VARCHAR", "Source table identifier."),
                  new ColSpec("from_column", "VARCHAR", "Source join column."),
                  new ColSpec("to_table_id", "VARCHAR", "Target table identifier."),
                  new ColSpec("to_column", "VARCHAR", "Target join column."),
                  new ColSpec("relationship_type", "VARCHAR", "e.g. many_to_one, one_to_one."),
                  new ColSpec("join_type", "VARCHAR", "e.g. inner, left."),
                  new ColSpec("is_approved", "BOOLEAN", "Whether a steward has approved this join path (0/1)."))));

  private final CatalogDatabaseRepository databases;
  private final CatalogTableRepository tables;
  private final CatalogColumnRepository columns;

  public CatalogStoreSelfDescribingSeeder(
      CatalogDatabaseRepository databases, CatalogTableRepository tables, CatalogColumnRepository columns) {
    this.databases = databases;
    this.tables = tables;
    this.columns = columns;
  }

  @Override
  public void run(ApplicationArguments args) {
    CatalogDatabase db =
        databases
            .findByConnectorIdAndName(CONNECTOR_ID, DATABASE_NAME)
            .orElseGet(
                () -> {
                  CatalogDatabase d = new CatalogDatabase();
                  d.setConnectorId(CONNECTOR_ID);
                  d.setName(DATABASE_NAME);
                  d.setDescription("DataLens's own catalog-governance metadata.");
                  return databases.save(d);
                });

    for (TableSpec spec : TABLES) {
      CatalogTable table =
          tables
              .findByDatabaseIdAndName(db.getId(), spec.name())
              .orElseGet(
                  () -> {
                    CatalogTable t = new CatalogTable();
                    t.setDatabaseId(db.getId());
                    t.setName(spec.name());
                    return t;
                  });
      table.setDescription(spec.description());
      table.setClassification(spec.classification());
      table.setSteward("datalens-governance");
      table.setIsActive(true);
      table.setIsEnabled(true);
      table = tables.save(table);

      Map<String, CatalogColumn> existingByName = new java.util.HashMap<>();
      for (CatalogColumn c : columns.findByTableIdOrderByPositionAsc(table.getId())) {
        existingByName.put(c.getName(), c);
      }
      int position = 0;
      for (ColSpec colSpec : spec.columns()) {
        CatalogColumn col = existingByName.get(colSpec.name());
        if (col == null) {
          col = new CatalogColumn();
          col.setTableId(table.getId());
          col.setName(colSpec.name());
        }
        col.setDataType(colSpec.dataType());
        col.setDescription(colSpec.description());
        col.setPosition(position++);
        columns.save(col);
      }
    }
  }
}
