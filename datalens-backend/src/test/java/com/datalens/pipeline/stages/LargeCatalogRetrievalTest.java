package com.datalens.pipeline.stages;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.datalens.config.DataLensProperties;
import com.datalens.config.DataLensSettings;
import com.datalens.llm.LlmProviderRegistry;
import com.datalens.model.entity.Abbreviation;
import com.datalens.model.entity.BusinessRule;
import com.datalens.model.entity.BusinessTerm;
import com.datalens.model.entity.CatalogColumn;
import com.datalens.model.entity.CatalogDatabase;
import com.datalens.model.entity.CatalogRelationship;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.entity.GlossaryTerm;
import com.datalens.model.entity.Synonym;
import com.datalens.model.repository.AbbreviationRepository;
import com.datalens.model.repository.BusinessMetricRepository;
import com.datalens.model.repository.BusinessRuleRepository;
import com.datalens.model.repository.BusinessTermRepository;
import com.datalens.model.repository.CalculatedFieldRepository;
import com.datalens.model.repository.CatalogColumnRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogRelationshipRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.model.repository.GlossaryTermRepository;
import com.datalens.model.repository.QueryLibraryEntryRepository;
import com.datalens.model.repository.SynonymRepository;
import com.datalens.pipeline.PipelineContext;
import com.datalens.pipeline.ResolvedTableModel;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zaxxer.hikari.HikariDataSource;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.test.context.TestPropertySource;

/**
 * Exercises retrieval/grounding at production-like scale (150+ tables, thousands of columns,
 * realistic glossary/synonym/business-term/abbreviation/business-rule/relationship data) instead
 * of the small local dev catalog, which is too small to reveal ranking or performance problems.
 * Uses a throwaway SQLite file with the schema generated from the JPA entities (create-drop) -
 * isolated from the real dev database. Seeded once for the whole class (PER_CLASS + @BeforeAll,
 * not @BeforeEach): every test here only reads the catalog, and reseeding per-method without
 * clearing prior data would accumulate duplicate tables across test methods (there's no
 * @Transactional rollback in play), silently changing retrieval ranking as more tests are added.
 */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@SpringBootTest(classes = LargeCatalogRetrievalTest.TestConfig.class)
@TestPropertySource(
    properties = {
      "spring.jpa.hibernate.ddl-auto=create-drop",
      "spring.jpa.properties.hibernate.dialect=org.hibernate.community.dialect.SQLiteDialect"
    })
class LargeCatalogRetrievalTest {

  @EnableAutoConfiguration
  @EntityScan("com.datalens.model.entity")
  @EnableJpaRepositories("com.datalens.model.repository")
  static class TestConfig {
    @Bean
    DataSource dataSource() throws IOException {
      Path tmp = Files.createTempFile("datalens-large-catalog-test", ".db");
      tmp.toFile().deleteOnExit();
      HikariDataSource ds = new HikariDataSource();
      ds.setPoolName("large-catalog-test");
      ds.setJdbcUrl("jdbc:sqlite:file:" + tmp.toAbsolutePath() + "?mode=rwc&busy_timeout=30000");
      ds.setDriverClassName("org.sqlite.JDBC");
      ds.setMaximumPoolSize(1);
      return ds;
    }
  }

  @Autowired private CatalogDatabaseRepository databases;
  @Autowired private CatalogTableRepository tables;
  @Autowired private CatalogColumnRepository columns;
  @Autowired private GlossaryTermRepository glossary;
  @Autowired private SynonymRepository synonyms;
  @Autowired private AbbreviationRepository abbreviations;
  @Autowired private BusinessTermRepository businessTerms;
  @Autowired private BusinessRuleRepository businessRules;
  @Autowired private BusinessMetricRepository metrics;
  @Autowired private QueryLibraryEntryRepository library;
  @Autowired private CatalogRelationshipRepository relationships;
  @Autowired private CalculatedFieldRepository calculatedFields;

  private DataLensSettings settings;
  private PipelineStages stages;

  /** One realistic business entity, replicated across databases/naming variants below. */
  private record EntityTemplate(String name, String description, String classification, String[][] columns) {}
  // columns: {name, dataType, description, "pii"|"" }

  private static final EntityTemplate[] ENTITIES = {
    new EntityTemplate(
        "customers",
        "Retail and commercial customer master records.",
        "confidential",
        new String[][] {
          {"customer_id", "STRING", "Unique customer identifier", ""},
          {"first_name", "STRING", "Customer first name", "pii"},
          {"last_name", "STRING", "Customer last name", "pii"},
          {"email", "STRING", "Primary email address", "pii"},
          {"phone", "STRING", "Primary phone number", "pii"},
          {"ssn", "STRING", "Social security number", "pii"},
          {"date_of_birth", "DATE", "Date of birth", "pii"},
          {"status", "STRING", "ACTIVE, INACTIVE, or CLOSED", ""},
          {"segment", "STRING", "Retail, commercial, or private banking segment", ""},
          {"kyc_status", "STRING", "Know-your-customer verification status", ""},
          {"onboarded_at", "TIMESTAMP", "Account opening timestamp", ""},
          {"region", "STRING", "Customer home region", ""},
          {"account_type", "STRING", "Regular, TEST, or INTERNAL account flag", ""},
        }),
    new EntityTemplate(
        "accounts",
        "Deposit and lending account records linked to customers.",
        "confidential",
        new String[][] {
          {"account_id", "STRING", "Unique account identifier", ""},
          {"customer_id", "STRING", "Owning customer identifier", ""},
          {"account_type", "STRING", "Checking, savings, or credit account type", ""},
          {"currency", "STRING", "ISO currency code", ""},
          {"balance", "DECIMAL", "Current account balance", ""},
          {"opened_at", "TIMESTAMP", "Account open date", ""},
          {"status", "STRING", "Account status", ""},
          {"branch_code", "STRING", "Originating branch code", ""},
        }),
    new EntityTemplate(
        "transactions",
        "Posted account transactions.",
        "internal",
        new String[][] {
          {"transaction_id", "STRING", "Unique transaction identifier", ""},
          {"account_id", "STRING", "Related account identifier", ""},
          {"amount", "DECIMAL", "Transaction amount", ""},
          {"currency", "STRING", "ISO currency code", ""},
          {"transaction_type", "STRING", "Debit or credit", ""},
          {"transaction_date", "TIMESTAMP", "Posting date", ""},
          {"merchant_name", "STRING", "Merchant or counterparty name", ""},
          {"status", "STRING", "Cleared, pending, or reversed", ""},
          {"channel", "STRING", "Branch, online, mobile, or ATM channel", ""},
        }),
    new EntityTemplate(
        "loans",
        "Consumer and commercial loan originations.",
        "confidential",
        new String[][] {
          {"loan_id", "STRING", "Unique loan identifier", ""},
          {"customer_id", "STRING", "Borrower customer identifier", ""},
          {"principal_amount", "DECIMAL", "Original principal amount", ""},
          {"interest_rate", "DECIMAL", "Annual interest rate", ""},
          {"days_past_due", "INTEGER", "Days payment is past due", ""},
          {"loan_status", "STRING", "Open, closed, or defaulted", ""},
          {"origination_date", "DATE", "Loan origination date", ""},
          {"maturity_date", "DATE", "Loan maturity date", ""},
          {"collateral_id", "STRING", "Linked collateral identifier", ""},
        }),
    new EntityTemplate(
        "credit_ratings",
        "External credit rating agency assessments per customer.",
        "internal",
        new String[][] {
          {"rating_id", "STRING", "Unique rating record identifier", ""},
          {"customer_id", "STRING", "Rated customer identifier", ""},
          {"rating_agency", "STRING", "Issuing rating agency", ""},
          {"rating_value", "STRING", "Letter-grade rating value", ""},
          {"rating_date", "DATE", "Rating issue date", ""},
          {"outlook", "STRING", "Positive, negative, or stable outlook", ""},
        }),
    new EntityTemplate(
        "risk_scores",
        "Model-generated customer risk scores.",
        "internal",
        new String[][] {
          {"risk_id", "STRING", "Unique risk score record identifier", ""},
          {"customer_id", "STRING", "Scored customer identifier", ""},
          {"risk_tier", "STRING", "LOW, MEDIUM, or HIGH risk tier", ""},
          {"score", "INTEGER", "Numeric risk score 0-100", ""},
          {"model_version", "STRING", "Scoring model version", ""},
          {"scored_at", "TIMESTAMP", "Scoring timestamp", ""},
        }),
    new EntityTemplate(
        "compliance_flags",
        "AML/compliance flags raised against customers.",
        "restricted",
        new String[][] {
          {"flag_id", "STRING", "Unique flag identifier", ""},
          {"customer_id", "STRING", "Flagged customer identifier", ""},
          {"flag_type", "STRING", "AML, sanctions, or fraud flag type", ""},
          {"severity", "STRING", "Low, medium, or high severity", ""},
          {"raised_at", "TIMESTAMP", "Flag raised timestamp", ""},
          {"resolved_at", "TIMESTAMP", "Flag resolution timestamp", ""},
          {"status", "STRING", "Open or resolved", ""},
        }),
    new EntityTemplate(
        "trades",
        "Executed trading desk transactions.",
        "internal",
        new String[][] {
          {"trade_id", "STRING", "Unique trade identifier", ""},
          {"counterparty_id", "STRING", "Trading counterparty identifier", ""},
          {"instrument_id", "STRING", "Traded instrument identifier", ""},
          {"notional", "DECIMAL", "Trade notional amount", ""},
          {"trade_date", "DATE", "Trade execution date", ""},
          {"settlement_date", "DATE", "Trade settlement date", ""},
          {"trader_id", "STRING", "Executing trader identifier", ""},
          {"status", "STRING", "Booked, settled, or cancelled", ""},
        }),
    new EntityTemplate(
        "positions",
        "End-of-day portfolio positions.",
        "internal",
        new String[][] {
          {"position_id", "STRING", "Unique position identifier", ""},
          {"portfolio_id", "STRING", "Owning portfolio identifier", ""},
          {"instrument_id", "STRING", "Held instrument identifier", ""},
          {"quantity", "DECIMAL", "Position quantity", ""},
          {"market_value", "DECIMAL", "Mark-to-market value", ""},
          {"as_of_date", "DATE", "Valuation date", ""},
        }),
    new EntityTemplate(
        "counterparties",
        "Trading and lending counterparty reference data.",
        "internal",
        new String[][] {
          {"counterparty_id", "STRING", "Unique counterparty identifier", ""},
          {"legal_name", "STRING", "Legal entity name", ""},
          {"lei_code", "STRING", "Legal entity identifier code", ""},
          {"jurisdiction", "STRING", "Regulatory jurisdiction", ""},
          {"credit_limit", "DECIMAL", "Approved credit limit", ""},
          {"relationship_manager", "STRING", "Assigned relationship manager", ""},
        }),
  };

  private static final String[] DATABASES = {"analytics", "risk", "finance", "customer360", "archive"};
  private static final String[] VARIANTS = {"", "_v2", "_legacy"};

  /** Which database holds the actively-used ("canonical") copy of each entity, mirroring how a
   * real enterprise catalog has one authoritative source plus per-domain extracts/legacy copies. */
  private static final Map<String, String> CANONICAL_DB =
      Map.of(
          "customers", "customer360",
          "accounts", "customer360",
          "transactions", "customer360",
          "loans", "analytics",
          "risk_scores", "risk",
          "trades", "finance");

  private static String variantNote(String variant) {
    return switch (variant) {
      case "_v2" -> "Newer schema version under migration; prefer the base table unless you need v2-only fields.";
      case "_legacy" -> "Deprecated legacy copy retained for historical reporting; do not use for new analysis.";
      default -> "";
    };
  }

  private String customer360CustomersId;
  private String analyticsLoansId;

  @BeforeAll
  void seedLargeCatalog() throws Exception {
    settings = new DataLensSettings(new DataLensProperties("../backend/config/settings.yaml", "/api/v1"));

    int tableCount = 0;
    int columnCount = 0;
    for (String dbName : DATABASES) {
      CatalogDatabase db = new CatalogDatabase();
      db.setName(dbName);
      db.setDescription(dbName + " database");
      db = databases.save(db);

      for (EntityTemplate entity : ENTITIES) {
        for (String variant : VARIANTS) {
          CatalogTable table = new CatalogTable();
          table.setDatabaseId(db.getId());
          table.setName(entity.name() + variant);
          table.setDescription(entity.description() + " " + variantNote(variant));
          table.setClassification(entity.classification());
          table.setOwner(dbName + "-data-owner");
          table.setSteward(dbName + "-data-steward");
          table.setRowCount(100_000);
          // Realistic enterprise catalogs have many near-duplicate tables (legacy copies,
          // per-database extracts, in-progress v2 migrations); usage_count is the same signal
          // production retrieval already uses to prefer the actively-used, canonical one.
          int usage = switch (variant) {
            case "_v2" -> 15;
            case "_legacy" -> 2;
            default -> 50;
          };
          if (variant.isEmpty() && dbName.equals(CANONICAL_DB.get(entity.name()))) usage = 800;
          table.setUsageCount(usage);
          // Legacy copies are deprecated and taken out of active use, like the variant note says.
          table.setIsActive(!"_legacy".equals(variant));
          table = tables.save(table);
          tableCount++;

          if ("customer360".equals(dbName) && "customers".equals(entity.name()) && variant.isEmpty()) {
            customer360CustomersId = table.getId();
          }
          if ("analytics".equals(dbName) && "loans".equals(entity.name()) && variant.isEmpty()) {
            analyticsLoansId = table.getId();
          }

          List<CatalogColumn> cols = new ArrayList<>();
          int position = 0;
          for (String[] colSpec : entity.columns()) {
            CatalogColumn col = new CatalogColumn();
            col.setTableId(table.getId());
            col.setName(colSpec[0]);
            col.setDataType(colSpec[1]);
            col.setDescription(colSpec[2]);
            col.setPosition(position++);
            if ("pii".equals(colSpec[3])) {
              col.setIsPii(true);
              col.setClassification("restricted");
            }
            // Every entity's first column is its primary business key - a realistic Critical
            // Data Element candidate, tagged the way an enterprise governance program would.
            if (col.getPosition() == 0) col.setClassification("critical");
            cols.add(col);
          }
          columns.saveAll(cols);
          columnCount += cols.size();
        }
      }
    }
    assertThat(tableCount).isGreaterThanOrEqualTo(150);
    assertThat(columnCount).isGreaterThanOrEqualTo(1000);

    seedBusinessKnowledge();

    stages =
        new PipelineStages(
            settings,
            null,
            new ObjectMapper(),
            null,
            null,
            null,
            null,
            tables,
            columns,
            databases,
            glossary,
            synonyms,
            abbreviations,
            businessTerms,
            businessRules,
            metrics,
            library,
            relationships,
            null,
            calculatedFields,
            null);
  }

  private void seedBusinessKnowledge() {
    GlossaryTerm revenue = glossaryTerm("Revenue", "Total income recognized from customer transactions.");
    glossaryTerm("Churn", "Rate at which customers close all accounts within a period.");

    Synonym syn = new Synonym();
    syn.setTermId(revenue.getId());
    syn.setSynonym("sales");
    synonyms.save(syn);

    abbreviation("CDE", "governance", "Critical Data Element", "critical");
    abbreviation("NPL", "analytics.loans", "Non-Performing Loan");
    abbreviation("KYC", "customer360.customers", "Know Your Customer");
    abbreviation("AUM", "finance.positions", "Assets Under Management");

    businessTerm("active customer", "customer360.customers", "status", "ACTIVE");
    businessTerm("high risk customer", "risk.risk_scores", "risk_tier", "HIGH");

    businessRule(
        "Exclude test and internal accounts",
        "global",
        null,
        null,
        "filter",
        "Exclude rows where account_type is TEST or INTERNAL from customer-facing metrics unless explicitly asked.");
    businessRule(
        "Restricted columns require explicit request",
        "global",
        null,
        null,
        "governance",
        "Columns classified as restricted, or tagged PII, must never be included in results unless the question explicitly asks for that specific personal data.");
    businessRule(
        "Non-performing loan definition",
        "table",
        "analytics.loans",
        null,
        "calculation",
        "A non-performing loan (NPL) is a loan where days_past_due > 90 and loan_status is not CLOSED.");
    businessRule(
        "High risk customer definition",
        "table",
        "risk.risk_scores",
        null,
        "calculation",
        "A high-risk customer has risk_tier = HIGH or score >= 80.");
    businessRule(
        "SSN never exported",
        "column",
        "customer360.customers",
        "ssn",
        "governance",
        "SSN must never appear in aggregated or exported results.");

    relationship("customer360.customers", customer360CustomersId, "customer_id");
  }

  private GlossaryTerm glossaryTerm(String term, String definition) {
    GlossaryTerm t = new GlossaryTerm();
    t.setTerm(term);
    t.setDefinition(definition);
    t.setStatus("approved");
    return glossary.save(t);
  }

  private void abbreviation(String abbr, String entity, String value) {
    abbreviation(abbr, entity, value, null);
  }

  private void abbreviation(String abbr, String entity, String value, String mapsToClassification) {
    Abbreviation a = new Abbreviation();
    a.setAbbreviation(abbr);
    a.setEntity(entity);
    a.setValue(value);
    a.setMapsToClassification(mapsToClassification);
    a.setStatus("approved");
    a.setSource("manual");
    abbreviations.save(a);
  }

  private void businessTerm(String term, String entity, String columnName, String value) {
    BusinessTerm t = new BusinessTerm();
    t.setTerm(term);
    t.setEntity(entity);
    t.setColumnName(columnName);
    t.setValue(value);
    t.setStatus("approved");
    t.setSource("manual");
    businessTerms.save(t);
  }

  private void businessRule(
      String name, String scope, String entity, String columnName, String ruleType, String statement) {
    BusinessRule r = new BusinessRule();
    r.setName(name);
    r.setScope(scope);
    r.setEntity(entity);
    r.setColumnName(columnName);
    r.setRuleType(ruleType);
    r.setStatement(statement);
    r.setStatus("approved");
    r.setSource("manual");
    businessRules.save(r);
  }

  /** Not exercised by the retrieval assertions below, but keeps the fixture realistic. */
  private void relationship(String entityName, String tableId, String column) {
    if (tableId == null) return;
    CatalogRelationship rel = new CatalogRelationship();
    rel.setFromTableId(tableId);
    rel.setFromColumn(column);
    rel.setToTableId(tableId);
    rel.setToColumn(column);
    rel.setRelationshipType("many_to_one");
    rel.setJoinType("inner");
    rel.setSource("manual");
    rel.setIsApproved(true);
    relationships.save(rel);
  }

  @Test
  void resolvesRelevantTablesAtScaleWithinTimeBudget() {
    PipelineContext ctx = new PipelineContext();
    ctx.setPrompt("Show active customers and their account balances");

    long start = System.nanoTime();
    stages.semanticSearch(ctx);
    long elapsedMs = (System.nanoTime() - start) / 1_000_000;

    assertThat(ctx.getResolvedTables()).isNotEmpty();
    assertThat(ctx.getResolvedTables().size()).isLessThanOrEqualTo(6);
    assertThat(ctx.getResolvedTables()).anyMatch(t -> t.getName().contains("customers"));
    assertThat(ctx.getResolvedTables()).anyMatch(t -> t.getName().contains("accounts"));
    assertThat(elapsedMs)
        .as("semanticSearch over 150+ tables should stay fast (two-stage funnel, no per-table column N+1)")
        .isLessThan(3000);
  }

  @Test
  void wellDocumentedTableOutranksAnEquallyNamedButUndocumentedOne() {
    CatalogDatabase db = new CatalogDatabase();
    db.setName("docstest");
    db = databases.save(db);

    CatalogTable documented = new CatalogTable();
    documented.setDatabaseId(db.getId());
    documented.setName("widget_telemetry");
    documented.setDescription("Sensor telemetry readings captured from field-deployed widgets.");
    documented.setTags(List.of("iot", "telemetry"));
    documented.setSteward("iot-team");
    documented.setUsageCount(0);
    documented = tables.save(documented);
    columns.save(describedColumn(documented.getId(), "reading_value", "Sensor reading value at capture time."));

    CatalogTable sparse = new CatalogTable();
    sparse.setDatabaseId(db.getId());
    sparse.setName("widget_telemetry_raw");
    sparse.setUsageCount(0);
    sparse = tables.save(sparse);
    columns.save(describedColumn(sparse.getId(), "reading_value", null));

    PipelineContext ctx = new PipelineContext();
    ctx.setPrompt("Show widget telemetry readings");
    stages.semanticSearch(ctx);

    List<String> order = ctx.getResolvedTables().stream().map(ResolvedTableModel::getName).toList();
    int documentedIndex = order.indexOf("widget_telemetry");
    int sparseIndex = order.indexOf("widget_telemetry_raw");
    assertThat(documentedIndex)
        .as("Both tables match the question equally well on name/columns; the fully-described one "
            + "should rank first purely on documentation completeness. Resolved order: " + order)
        .isGreaterThanOrEqualTo(0);
    if (sparseIndex >= 0) {
      assertThat(documentedIndex).isLessThan(sparseIndex);
    }
  }

  @Test
  void retrievalNeverMixesTablesFromADifferentConnectorIntoOnePlan() {
    CatalogDatabase primaryDb = new CatalogDatabase();
    primaryDb.setConnectorId("primary_conn");
    primaryDb.setName("primary_domain");
    primaryDb = databases.save(primaryDb);

    CatalogTable primaryTable = new CatalogTable();
    primaryTable.setDatabaseId(primaryDb.getId());
    primaryTable.setName("orders_ledger");
    primaryTable.setDescription("Orders ledger for the primary connector's warehouse.");
    primaryTable.setUsageCount(0);
    tables.save(primaryTable);

    CatalogDatabase otherDb = new CatalogDatabase();
    otherDb.setConnectorId("other_conn");
    otherDb.setName("other_domain");
    otherDb = databases.save(otherDb);

    CatalogTable otherTable = new CatalogTable();
    otherTable.setDatabaseId(otherDb.getId());
    otherTable.setName("orders_ledger");
    // Same name/description as the primary connector's table and a much higher usage count, so
    // if scoping were broken this one would win the ranking and leak across connectors.
    otherTable.setDescription("Orders ledger for the primary connector's warehouse.");
    otherTable.setUsageCount(1000);
    tables.save(otherTable);

    PipelineContext ctx = new PipelineContext();
    ctx.setConnectorId("primary_conn");
    ctx.setPrompt("Show orders ledger records");
    stages.semanticSearch(ctx);

    assertThat(ctx.getResolvedTables())
        .as("A same-named, higher-usage table belonging to a different connector must never be "
            + "resolved - the two tables live in physically separate databases, so mixing them into "
            + "one plan would produce SQL that can't execute against either connection")
        .allMatch(t -> t.getDatabase().equals("primary_domain"));
    assertThat(ctx.getResolvedTables()).anyMatch(t -> t.getName().equals("orders_ledger"));
  }

  private static CatalogColumn describedColumn(String tableId, String name, String description) {
    CatalogColumn col = new CatalogColumn();
    col.setTableId(tableId);
    col.setName(name);
    col.setDataType("STRING");
    col.setDescription(description);
    col.setPosition(0);
    return col;
  }

  @Test
  void globalBusinessRulesAlwaysApplyButTableScopedRulesOnlySurfaceWhenRelevant() {
    PipelineContext unrelated = new PipelineContext();
    unrelated.setPrompt("Show trade counts by counterparty this month");
    stages.semanticSearch(unrelated);

    List<String> unrelatedRuleNames = unrelated.getBusinessRuleContext().stream()
        .map(m -> String.valueOf(m.get("name")))
        .toList();
    assertThat(unrelatedRuleNames)
        .contains("Exclude test and internal accounts", "Restricted columns require explicit request");
    assertThat(unrelatedRuleNames).doesNotContain("Non-performing loan definition");

    PipelineContext loanQuestion = new PipelineContext();
    loanQuestion.setPrompt("Which loans are non-performing right now?");
    stages.semanticSearch(loanQuestion);

    List<String> loanRuleNames = loanQuestion.getBusinessRuleContext().stream()
        .map(m -> String.valueOf(m.get("name")))
        .toList();
    assertThat(loanRuleNames).contains("Exclude test and internal accounts", "Non-performing loan definition");
  }

  @Test
  void resolvedCustomerColumnsSurfacePiiAndClassificationMetadata() {
    PipelineContext ctx = new PipelineContext();
    ctx.setPrompt("List customer email and phone number by region");
    stages.semanticSearch(ctx);

    assertThat(ctx.getResolvedTables()).anyMatch(t -> t.getName().startsWith("customers"));
    boolean anyPiiColumn =
        ctx.getResolvedTables().stream()
            .filter(t -> t.getName().startsWith("customers"))
            .flatMap(t -> t.getColumns().stream())
            .anyMatch(c -> Boolean.TRUE.equals(c.get("is_pii")));
    assertThat(anyPiiColumn)
        .as("PII columns (email/phone/ssn) captured during enrichment should reach the resolved schema context")
        .isTrue();
  }

  @Test
  void refinerHintsAreFilteredToQuestionRelevanceNotDumpedInFull() throws Exception {
    LlmProviderRegistry llmMock = mock(LlmProviderRegistry.class);
    StringBuilder capturedUserMessage = new StringBuilder();
    when(llmMock.completeJson(anyString(), anyString(), any(), anyString()))
        .thenAnswer(
            invocation -> {
              capturedUserMessage.append(invocation.getArgument(1, String.class));
              return Map.<String, Object>of();
            });

    PipelineStages stagesWithLlm =
        new PipelineStages(
            settings,
            llmMock,
            new ObjectMapper(),
            null,
            null,
            null,
            null,
            tables,
            columns,
            databases,
            glossary,
            synonyms,
            abbreviations,
            businessTerms,
            businessRules,
            metrics,
            library,
            relationships,
            null,
            calculatedFields,
            null);

    PipelineContext ctx = new PipelineContext();
    ctx.setPrompt("What is our NPL ratio this quarter?");
    stagesWithLlm.refine(ctx);

    String userMessage = capturedUserMessage.toString();
    assertThat(userMessage).contains("NPL");
    assertThat(userMessage)
        .as("Unrelated synonyms (e.g. 'sales' -> Revenue) should not be dumped in when the question never mentions them")
        .doesNotContain("sales => Revenue");
  }

  /**
   * Governance questions ("what % of CDE are active") are no longer answered by a special-cased
   * Java method - they're expected to flow through the SAME retrieval->plan->generateSql pipeline
   * as any business question, by registering DataLens's own catalog tables as an ordinary,
   * well-documented, connector-scoped data source (see the real
   * com.datalens.connectors.catalogstore package). This mirrors that shape at a smaller scale:
   * a dedicated connector whose only table is a documented "catalog_columns" table, so a CDE
   * question should resolve it through ordinary documentation-weighted retrieval - no bespoke
   * governance code path involved.
   */
  @Test
  void catalogGovernanceQuestionResolvesTheCatalogStoreTableThroughOrdinaryRetrieval() {
    CatalogDatabase catalogStoreDb = new CatalogDatabase();
    catalogStoreDb.setConnectorId("catalog_store_test");
    catalogStoreDb.setName("datalens_catalog");
    catalogStoreDb = databases.save(catalogStoreDb);

    CatalogTable catalogColumnsTable = new CatalogTable();
    catalogColumnsTable.setDatabaseId(catalogStoreDb.getId());
    catalogColumnsTable.setName("catalog_columns");
    catalogColumnsTable.setDescription(
        "Registry of every column known to the DataLens catalog: data type, classification, "
            + "PII flag, and documentation status, one row per column of every cataloged table.");
    catalogColumnsTable.setSteward("datalens-governance");
    catalogColumnsTable.setUsageCount(0);
    catalogColumnsTable = tables.save(catalogColumnsTable);
    columns.save(
        describedColumn(
            catalogColumnsTable.getId(),
            "classification",
            "Governance classification (e.g. public, internal, confidential, critical, restricted)."));
    columns.save(describedColumn(catalogColumnsTable.getId(), "is_active", "Whether the column's table is active."));

    PipelineContext ctx = new PipelineContext();
    ctx.setConnectorId("catalog_store_test");
    ctx.setPrompt("What % of CDE are active?");
    stages.semanticSearch(ctx);

    assertThat(ctx.getResolvedTables())
        .as("CDE (seeded in the shared fixture as an approved abbreviation for \"Critical Data "
            + "Element\") plus this table's own strong documentation should be enough for ordinary "
            + "retrieval to surface catalog_columns - no special-cased governance intent needed")
        .anyMatch(t -> t.getName().equals("catalog_columns"));
  }

  @Test
  void catalogStoreTableNeverLeaksIntoABusinessConnectorSSession() {
    PipelineContext ctx = new PipelineContext();
    ctx.setConnectorId("analytics_business_connector_unrelated_to_catalog_store");
    ctx.setPrompt("What % of CDE are active?");
    stages.semanticSearch(ctx);

    assertThat(ctx.getResolvedTables())
        .as("A connector that was never seeded with catalog_columns must never resolve it, even "
            + "when the question strongly matches it by name/documentation elsewhere")
        .noneMatch(t -> t.getName().equals("catalog_columns"));
  }
}
