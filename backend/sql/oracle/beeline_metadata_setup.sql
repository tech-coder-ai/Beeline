-- =============================================================================
-- Beeline / DataLens — Oracle metadata repository setup
-- =============================================================================
--
-- Creates the full application metadata schema (catalog, chat, governance,
-- semantic layer, dashboards, etc.) for Oracle 19c+.
--
-- Schema revision: d4e5f6a7b8c9 (Alembic head — includes business_terms,
-- abbreviations, and extended catalog_relationships columns).
--
-- Identifier style: quoted lowercase names match SQLite/PostgreSQL and JPA
-- @Table(name = "...") annotations used by Spring Boot and SQLAlchemy.
--
-- JSON columns are stored as CLOB (UTF-8 JSON text). The Java JsonAttributeConverter
-- and Python SQLAlchemy JSON types read/write plain JSON strings.
--
-- Run as a DBA or schema owner:
--   sqlplus sys/password@//host:1521/ORCLPDB1 as sysdba @beeline_metadata_setup.sql
--   -- or connect as beeline_meta after creating the user (see Section 1).
--
-- =============================================================================


-- =============================================================================
-- SECTION 1 — Optional DBA setup (uncomment and edit paths/credentials)
-- =============================================================================
/*
CREATE TABLESPACE beeline_meta
  DATAFILE 'beeline_meta01.dbf' SIZE 500M
  AUTOEXTEND ON NEXT 100M MAXSIZE UNLIMITED
  EXTENT MANAGEMENT LOCAL
  SEGMENT SPACE MANAGEMENT AUTO;

CREATE USER beeline_meta IDENTIFIED BY "ChangeMeOnInstall"
  DEFAULT TABLESPACE beeline_meta
  TEMPORARY TABLESPACE temp
  QUOTA UNLIMITED ON beeline_meta;

GRANT CREATE SESSION TO beeline_meta;
GRANT CREATE TABLE TO beeline_meta;
GRANT CREATE SEQUENCE TO beeline_meta;
GRANT CREATE VIEW TO beeline_meta;

-- Connect as beeline_meta before running the DDL below:
-- CONNECT beeline_meta/ChangeMeOnInstall@//hostname:1521/ORCLPDB1
*/


-- =============================================================================
-- SECTION 2 — Optional clean install (drops all app objects; DATA LOSS)
-- =============================================================================
/*
BEGIN
  FOR r IN (
    SELECT table_name
    FROM user_tables
    WHERE table_name IN (
      'ABBREVIATIONS','API_ACTIONS','APPROVAL_ITEMS','AUDIT_LOGS','BUSINESS_METRICS',
      'BUSINESS_TERMS','CATALOG_COLUMNS','CATALOG_DATABASES','CATALOG_RELATIONSHIPS',
      'CATALOG_TABLES','CHAT_MESSAGES','CHAT_SESSIONS','CONFIG_OVERRIDES','DASHBOARDS',
      'DASHBOARD_WIDGETS','EXECUTION_HISTORY','FEEDBACK','GLOSSARY_TERMS',
      'METADATA_VERSIONS','PROMPT_TEMPLATES','QUERY_LIBRARY','SAVED_QUERIES',
      'SYNONYMS','SYNC_RUNS','ALEMBIC_VERSION'
    )
  ) LOOP
    EXECUTE IMMEDIATE 'DROP TABLE "' || LOWER(r.table_name) || '" CASCADE CONSTRAINTS PURGE';
  END LOOP;
END;
/
*/


-- =============================================================================
-- SECTION 3 — Core tables (no foreign keys)
-- =============================================================================

CREATE TABLE "api_actions" (
  "id"              VARCHAR2(32)  NOT NULL,
  "action_id"       VARCHAR2(64)  NOT NULL,
  "label"           VARCHAR2(128) NOT NULL,
  "icon"            VARCHAR2(64),
  "method"          VARCHAR2(8)   NOT NULL,
  "url"             CLOB          NOT NULL,
  "headers"         CLOB,
  "body_template"   CLOB,
  "confirm"         NUMBER(1)     DEFAULT 0 NOT NULL,
  "enabled"         NUMBER(1)     DEFAULT 1 NOT NULL,
  "created_at"      TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"      TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_api_actions" PRIMARY KEY ("id"),
  CONSTRAINT "uk_api_actions_action_id" UNIQUE ("action_id"),
  CONSTRAINT "ck_api_actions_confirm" CHECK ("confirm" IN (0, 1)),
  CONSTRAINT "ck_api_actions_enabled" CHECK ("enabled" IN (0, 1))
);

CREATE TABLE "approval_items" (
  "id"               VARCHAR2(32)  NOT NULL,
  "entity_type"      VARCHAR2(32)  NOT NULL,
  "entity_id"        VARCHAR2(32)  NOT NULL,
  "entity_label"     VARCHAR2(512) NOT NULL,
  "field"            VARCHAR2(64)  NOT NULL,
  "current_value"    CLOB,
  "proposed_value"   CLOB          NOT NULL,
  "proposed_payload" CLOB,
  "source"           VARCHAR2(16)  NOT NULL,
  "confidence"       BINARY_DOUBLE,
  "rationale"        CLOB,
  "status"           VARCHAR2(16)  NOT NULL,
  "reviewed_by"      VARCHAR2(64),
  "reviewed_at"      TIMESTAMP(6) WITH TIME ZONE,
  "review_note"      CLOB,
  "final_value"      CLOB,
  "created_at"       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_approval_items" PRIMARY KEY ("id")
);

CREATE INDEX "ix_approval_items_entity_id"   ON "approval_items" ("entity_id");
CREATE INDEX "ix_approval_items_entity_type" ON "approval_items" ("entity_type");
CREATE INDEX "ix_approval_items_status"      ON "approval_items" ("status");

CREATE TABLE "audit_logs" (
  "id"          VARCHAR2(32) NOT NULL,
  "user_id"     VARCHAR2(64) NOT NULL,
  "action"      VARCHAR2(64) NOT NULL,
  "entity_type" VARCHAR2(32),
  "entity_id"   VARCHAR2(64),
  "detail"      CLOB,
  "severity"    VARCHAR2(16) DEFAULT 'info' NOT NULL,
  "created_at"  TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"  TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_audit_logs" PRIMARY KEY ("id")
);

CREATE INDEX "ix_audit_logs_action"  ON "audit_logs" ("action");
CREATE INDEX "ix_audit_logs_user_id" ON "audit_logs" ("user_id");

CREATE TABLE "business_metrics" (
  "id"                   VARCHAR2(32)  NOT NULL,
  "name"                 VARCHAR2(255) NOT NULL,
  "description"          CLOB,
  "expression"           CLOB          NOT NULL,
  "table_qualified_name" VARCHAR2(512),
  "unit"                 VARCHAR2(32),
  "aggregation"          VARCHAR2(32),
  "is_kpi"               NUMBER(1)     DEFAULT 0 NOT NULL,
  "tags"                 CLOB,
  "status"               VARCHAR2(16)  DEFAULT 'approved' NOT NULL,
  "created_at"           TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"           TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_business_metrics" PRIMARY KEY ("id"),
  CONSTRAINT "uk_business_metrics_name" UNIQUE ("name"),
  CONSTRAINT "ck_business_metrics_is_kpi" CHECK ("is_kpi" IN (0, 1))
);

CREATE TABLE "catalog_databases" (
  "id"             VARCHAR2(32)  NOT NULL,
  "connector_id"   VARCHAR2(64)  NOT NULL,
  "name"           VARCHAR2(255) NOT NULL,
  "description"    CLOB,
  "table_count"    NUMBER(10)    DEFAULT 0 NOT NULL,
  "last_synced_at" TIMESTAMP(6) WITH TIME ZONE,
  "created_at"     TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"     TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_catalog_databases" PRIMARY KEY ("id")
);

CREATE INDEX "ix_catalog_databases_connector_id" ON "catalog_databases" ("connector_id");
CREATE INDEX "ix_catalog_databases_name"         ON "catalog_databases" ("name");

CREATE TABLE "chat_sessions" (
  "id"              VARCHAR2(32)  NOT NULL,
  "title"           VARCHAR2(255) DEFAULT 'New chat' NOT NULL,
  "user_id"         VARCHAR2(64)  DEFAULT 'default' NOT NULL,
  "is_pinned"       NUMBER(1)     DEFAULT 0 NOT NULL,
  "is_archived"     NUMBER(1)     DEFAULT 0 NOT NULL,
  "is_shared"       NUMBER(1)     DEFAULT 0 NOT NULL,
  "share_token"     VARCHAR2(64),
  "context_summary" CLOB,
  "connector_id"    VARCHAR2(64),
  "created_at"      TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"      TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_chat_sessions" PRIMARY KEY ("id"),
  CONSTRAINT "uk_chat_sessions_share_token" UNIQUE ("share_token"),
  CONSTRAINT "ck_chat_sessions_is_pinned"   CHECK ("is_pinned" IN (0, 1)),
  CONSTRAINT "ck_chat_sessions_is_archived" CHECK ("is_archived" IN (0, 1)),
  CONSTRAINT "ck_chat_sessions_is_shared"   CHECK ("is_shared" IN (0, 1))
);

CREATE INDEX "ix_chat_sessions_user_id" ON "chat_sessions" ("user_id");

CREATE TABLE "config_overrides" (
  "id"         VARCHAR2(32)  NOT NULL,
  "key"        VARCHAR2(255) NOT NULL,
  "value"      CLOB,
  "updated_by" VARCHAR2(64)  DEFAULT 'admin' NOT NULL,
  "created_at" TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at" TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_config_overrides" PRIMARY KEY ("id"),
  CONSTRAINT "uk_config_overrides_key" UNIQUE ("key")
);

CREATE TABLE "dashboards" (
  "id"                       VARCHAR2(32)  NOT NULL,
  "user_id"                  VARCHAR2(64)  DEFAULT 'default' NOT NULL,
  "name"                     VARCHAR2(255) NOT NULL,
  "description"              CLOB,
  "is_shared"                NUMBER(1)     DEFAULT 0 NOT NULL,
  "share_token"              VARCHAR2(64),
  "refresh_interval_seconds" NUMBER(10),
  "layout"                   CLOB,
  "created_at"               TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"               TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_dashboards" PRIMARY KEY ("id"),
  CONSTRAINT "uk_dashboards_share_token" UNIQUE ("share_token"),
  CONSTRAINT "ck_dashboards_is_shared" CHECK ("is_shared" IN (0, 1))
);

CREATE INDEX "ix_dashboards_user_id" ON "dashboards" ("user_id");

CREATE TABLE "execution_history" (
  "id"               VARCHAR2(32) NOT NULL,
  "session_id"       VARCHAR2(32),
  "user_id"          VARCHAR2(64) DEFAULT 'default' NOT NULL,
  "connector_id"     VARCHAR2(64),
  "prompt"           CLOB         NOT NULL,
  "refined_prompt"   CLOB,
  "intent"           CLOB,
  "execution_plan"   CLOB,
  "generated_sql"    CLOB,
  "optimized_sql"    CLOB,
  "status"           VARCHAR2(24) DEFAULT 'pending' NOT NULL,
  "row_count"        NUMBER(10),
  "execution_time_ms" NUMBER(10),
  "cost_estimate"    CLOB,
  "confidence"       CLOB,
  "warnings"         CLOB,
  "error"            CLOB,
  "llm_model"        VARCHAR2(128),
  "llm_provider"     VARCHAR2(64),
  "token_usage"      CLOB,
  "tables_used"      CLOB,
  "reused_query_id"  VARCHAR2(32),
  "executed_at"      TIMESTAMP(6) WITH TIME ZONE,
  "created_at"       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_execution_history" PRIMARY KEY ("id")
);

CREATE INDEX "ix_execution_history_session_id" ON "execution_history" ("session_id");

CREATE TABLE "glossary_terms" (
  "id"               VARCHAR2(32)  NOT NULL,
  "term"             VARCHAR2(255) NOT NULL,
  "definition"       CLOB          NOT NULL,
  "business_meaning" CLOB,
  "examples"         CLOB,
  "owner"            VARCHAR2(255),
  "tags"             CLOB,
  "status"           VARCHAR2(16)  DEFAULT 'approved' NOT NULL,
  "source"           VARCHAR2(16)  DEFAULT 'manual' NOT NULL,
  "created_at"       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_glossary_terms" PRIMARY KEY ("id"),
  CONSTRAINT "uk_glossary_terms_term" UNIQUE ("term")
);

CREATE TABLE "metadata_versions" (
  "id"            VARCHAR2(32) NOT NULL,
  "entity_type"   VARCHAR2(32) NOT NULL,
  "entity_id"     VARCHAR2(32) NOT NULL,
  "field"         VARCHAR2(64) NOT NULL,
  "old_value"     CLOB,
  "new_value"     CLOB,
  "version"       NUMBER(10)   DEFAULT 1 NOT NULL,
  "changed_by"    VARCHAR2(64) DEFAULT 'system' NOT NULL,
  "change_source" VARCHAR2(32) DEFAULT 'manual' NOT NULL,
  "approval_id"   VARCHAR2(32),
  "created_at"    TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"    TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_metadata_versions" PRIMARY KEY ("id")
);

CREATE INDEX "ix_metadata_versions_entity_id"   ON "metadata_versions" ("entity_id");
CREATE INDEX "ix_metadata_versions_entity_type" ON "metadata_versions" ("entity_type");

CREATE TABLE "prompt_templates" (
  "id"         VARCHAR2(32)  NOT NULL,
  "name"       VARCHAR2(128) NOT NULL,
  "version"    NUMBER(10)    DEFAULT 1 NOT NULL,
  "template"   CLOB          NOT NULL,
  "is_active"  NUMBER(1)     DEFAULT 1 NOT NULL,
  "notes"      CLOB,
  "created_at" TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at" TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_prompt_templates" PRIMARY KEY ("id"),
  CONSTRAINT "ck_prompt_templates_is_active" CHECK ("is_active" IN (0, 1))
);

CREATE INDEX "ix_prompt_templates_name" ON "prompt_templates" ("name");

CREATE TABLE "query_library" (
  "id"                  VARCHAR2(32) NOT NULL,
  "question"            CLOB         NOT NULL,
  "normalized_question" CLOB         NOT NULL,
  "sql"                 CLOB         NOT NULL,
  "connector_id"        VARCHAR2(64),
  "tables_used"         CLOB,
  "intent"              CLOB,
  "execution_plan"      CLOB,
  "success_count"       NUMBER(10)   DEFAULT 1 NOT NULL,
  "positive_feedback"   NUMBER(10)   DEFAULT 0 NOT NULL,
  "negative_feedback"   NUMBER(10)   DEFAULT 0 NOT NULL,
  "avg_execution_ms"    BINARY_DOUBLE,
  "is_active"           NUMBER(1)    DEFAULT 1 NOT NULL,
  "created_at"          TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"          TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_query_library" PRIMARY KEY ("id"),
  CONSTRAINT "ck_query_library_is_active" CHECK ("is_active" IN (0, 1))
);

-- Function-based index: Oracle cannot index CLOB directly (matches Alembic ix_query_library_question).
CREATE INDEX "ix_query_library_question" ON "query_library" (DBMS_LOB.SUBSTR("question", 4000, 1));

CREATE TABLE "saved_queries" (
  "id"           VARCHAR2(32)  NOT NULL,
  "user_id"      VARCHAR2(64)  DEFAULT 'default' NOT NULL,
  "name"         VARCHAR2(255) NOT NULL,
  "description"  CLOB,
  "sql"          CLOB          NOT NULL,
  "connector_id" VARCHAR2(64),
  "prompt"       CLOB,
  "tags"         CLOB,
  "is_bookmarked" NUMBER(1)    DEFAULT 0 NOT NULL,
  "last_run_at"  TIMESTAMP(6) WITH TIME ZONE,
  "run_count"    NUMBER(10)   DEFAULT 0 NOT NULL,
  "created_at"   TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"   TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_saved_queries" PRIMARY KEY ("id"),
  CONSTRAINT "ck_saved_queries_is_bookmarked" CHECK ("is_bookmarked" IN (0, 1))
);

CREATE INDEX "ix_saved_queries_user_id" ON "saved_queries" ("user_id");

CREATE TABLE "sync_runs" (
  "id"             VARCHAR2(32) NOT NULL,
  "connector_id"   VARCHAR2(64) NOT NULL,
  "mode"           VARCHAR2(16) NOT NULL,
  "status"         VARCHAR2(16) DEFAULT 'running' NOT NULL,
  "tables_synced"  NUMBER(10)   DEFAULT 0 NOT NULL,
  "columns_synced" NUMBER(10)   DEFAULT 0 NOT NULL,
  "error"          CLOB,
  "finished_at"    TIMESTAMP(6) WITH TIME ZONE,
  "created_at"     TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"     TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_sync_runs" PRIMARY KEY ("id")
);

CREATE INDEX "ix_sync_runs_connector_id" ON "sync_runs" ("connector_id");

CREATE TABLE "abbreviations" (
  "id"           VARCHAR2(32) NOT NULL,
  "abbreviation" VARCHAR2(64) NOT NULL,
  "canonical"    VARCHAR2(255) NOT NULL,
  "description"  CLOB,
  "status"       VARCHAR2(16) DEFAULT 'approved' NOT NULL,
  "source"       VARCHAR2(16) DEFAULT 'manual' NOT NULL,
  "created_at"   TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"   TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_abbreviations" PRIMARY KEY ("id")
);

CREATE INDEX "ix_abbreviations_abbreviation" ON "abbreviations" ("abbreviation");


-- =============================================================================
-- SECTION 4 — Catalog hierarchy
-- =============================================================================

CREATE TABLE "catalog_tables" (
  "id"                 VARCHAR2(32)  NOT NULL,
  "database_id"        VARCHAR2(32)  NOT NULL,
  "name"               VARCHAR2(255) NOT NULL,
  "table_type"         VARCHAR2(32)  DEFAULT 'TABLE' NOT NULL,
  "description"        CLOB,
  "technical_comment"  CLOB,
  "owner"              VARCHAR2(255),
  "steward"            VARCHAR2(255),
  "tags"               CLOB,
  "classification"     VARCHAR2(64),
  "row_count"          NUMBER(10),
  "size_bytes"         NUMBER(19),
  "storage_format"     VARCHAR2(64),
  "compression"        VARCHAR2(64),
  "partition_columns"  CLOB,
  "last_analyzed_at"   TIMESTAMP(6) WITH TIME ZONE,
  "last_synced_at"     TIMESTAMP(6) WITH TIME ZONE,
  "usage_count"        NUMBER(10)    DEFAULT 0 NOT NULL,
  "is_active"          NUMBER(1)     DEFAULT 1 NOT NULL,
  "created_at"         TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"         TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_catalog_tables" PRIMARY KEY ("id"),
  CONSTRAINT "fk_catalog_tables_database"
    FOREIGN KEY ("database_id") REFERENCES "catalog_databases" ("id"),
  CONSTRAINT "ck_catalog_tables_is_active" CHECK ("is_active" IN (0, 1))
);

CREATE INDEX "ix_catalog_tables_database_id" ON "catalog_tables" ("database_id");
CREATE INDEX "ix_catalog_tables_name"         ON "catalog_tables" ("name");

CREATE TABLE "catalog_columns" (
  "id"                     VARCHAR2(32)  NOT NULL,
  "table_id"               VARCHAR2(32)  NOT NULL,
  "name"                   VARCHAR2(255) NOT NULL,
  "position"               NUMBER(10)    DEFAULT 0 NOT NULL,
  "data_type"              VARCHAR2(128) NOT NULL,
  "inferred_semantic_type" VARCHAR2(64),
  "semantic_confidence"    BINARY_DOUBLE,
  "description"            CLOB,
  "technical_comment"      CLOB,
  "tags"                   CLOB,
  "classification"         VARCHAR2(64),
  "is_pii"                 NUMBER(1)     DEFAULT 0 NOT NULL,
  "is_partition"           NUMBER(1)     DEFAULT 0 NOT NULL,
  "is_primary_key"         NUMBER(1)     DEFAULT 0 NOT NULL,
  "null_percentage"        BINARY_DOUBLE,
  "distinct_percentage"    BINARY_DOUBLE,
  "distinct_count"         NUMBER(10),
  "min_value"              VARCHAR2(255),
  "max_value"              VARCHAR2(255),
  "sample_values"          CLOB,
  "top_values"             CLOB,
  "created_at"             TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"             TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_catalog_columns" PRIMARY KEY ("id"),
  CONSTRAINT "fk_catalog_columns_table"
    FOREIGN KEY ("table_id") REFERENCES "catalog_tables" ("id"),
  CONSTRAINT "ck_catalog_columns_is_pii"        CHECK ("is_pii" IN (0, 1)),
  CONSTRAINT "ck_catalog_columns_is_partition"  CHECK ("is_partition" IN (0, 1)),
  CONSTRAINT "ck_catalog_columns_is_primary_key" CHECK ("is_primary_key" IN (0, 1))
);

CREATE INDEX "ix_catalog_columns_table_id" ON "catalog_columns" ("table_id");
CREATE INDEX "ix_catalog_columns_name"      ON "catalog_columns" ("name");

CREATE TABLE "catalog_relationships" (
  "id"                VARCHAR2(32)  NOT NULL,
  "from_table_id"     VARCHAR2(32)  NOT NULL,
  "from_column"       VARCHAR2(255) NOT NULL,
  "to_table_id"       VARCHAR2(32)  NOT NULL,
  "to_column"         VARCHAR2(255) NOT NULL,
  "from_columns"      CLOB,
  "to_columns"        CLOB,
  "relationship_type" VARCHAR2(32)  DEFAULT 'many_to_one' NOT NULL,
  "join_type"         VARCHAR2(16)  DEFAULT 'inner' NOT NULL,
  "description"       CLOB,
  "source"            VARCHAR2(32)  DEFAULT 'manual' NOT NULL,
  "confidence"        BINARY_DOUBLE,
  "is_approved"       NUMBER(1)     DEFAULT 1 NOT NULL,
  "created_at"        TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"        TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_catalog_relationships" PRIMARY KEY ("id"),
  CONSTRAINT "fk_catalog_relationships_from_table"
    FOREIGN KEY ("from_table_id") REFERENCES "catalog_tables" ("id"),
  CONSTRAINT "fk_catalog_relationships_to_table"
    FOREIGN KEY ("to_table_id") REFERENCES "catalog_tables" ("id"),
  CONSTRAINT "ck_catalog_relationships_is_approved" CHECK ("is_approved" IN (0, 1))
);

CREATE INDEX "ix_catalog_relationships_from_table_id" ON "catalog_relationships" ("from_table_id");
CREATE INDEX "ix_catalog_relationships_to_table_id"   ON "catalog_relationships" ("to_table_id");

CREATE TABLE "business_terms" (
  "id"          VARCHAR2(32)  NOT NULL,
  "term"        VARCHAR2(255) NOT NULL,
  "entity"      VARCHAR2(512) NOT NULL,
  "column_name" VARCHAR2(255) NOT NULL,
  "value"       CLOB          NOT NULL,
  "table_id"    VARCHAR2(32),
  "status"      VARCHAR2(16)  DEFAULT 'approved' NOT NULL,
  "source"      VARCHAR2(16)  DEFAULT 'manual' NOT NULL,
  "created_at"  TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"  TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_business_terms" PRIMARY KEY ("id"),
  CONSTRAINT "fk_business_terms_table"
    FOREIGN KEY ("table_id") REFERENCES "catalog_tables" ("id")
);

CREATE INDEX "ix_business_terms_term"   ON "business_terms" ("term");
CREATE INDEX "ix_business_terms_entity" ON "business_terms" ("entity");


-- =============================================================================
-- SECTION 5 — Chat, dashboards, feedback, synonyms
-- =============================================================================

CREATE TABLE "chat_messages" (
  "id"               VARCHAR2(32) NOT NULL,
  "session_id"       VARCHAR2(32) NOT NULL,
  "role"             VARCHAR2(16) NOT NULL,
  "content"          CLOB,
  "response_payload" CLOB,
  "execution_id"     VARCHAR2(32),
  "created_at"       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_chat_messages" PRIMARY KEY ("id"),
  CONSTRAINT "fk_chat_messages_session"
    FOREIGN KEY ("session_id") REFERENCES "chat_sessions" ("id"),
  CONSTRAINT "fk_chat_messages_execution"
    FOREIGN KEY ("execution_id") REFERENCES "execution_history" ("id")
);

CREATE INDEX "ix_chat_messages_session_id" ON "chat_messages" ("session_id");

CREATE TABLE "dashboard_widgets" (
  "id"                  VARCHAR2(32)  NOT NULL,
  "dashboard_id"        VARCHAR2(32)  NOT NULL,
  "title"               VARCHAR2(255) NOT NULL,
  "widget_type"         VARCHAR2(32)  NOT NULL,
  "position"            NUMBER(10)    DEFAULT 0 NOT NULL,
  "size"                VARCHAR2(16)  DEFAULT 'half' NOT NULL,
  "sql"                 CLOB,
  "connector_id"        VARCHAR2(64),
  "visualization"       CLOB,
  "snapshot"            CLOB,
  "source_execution_id" VARCHAR2(32),
  "created_at"          TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"          TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_dashboard_widgets" PRIMARY KEY ("id"),
  CONSTRAINT "fk_dashboard_widgets_dashboard"
    FOREIGN KEY ("dashboard_id") REFERENCES "dashboards" ("id")
);

CREATE INDEX "ix_dashboard_widgets_dashboard_id" ON "dashboard_widgets" ("dashboard_id");

CREATE TABLE "feedback" (
  "id"           VARCHAR2(32) NOT NULL,
  "execution_id" VARCHAR2(32),
  "message_id"   VARCHAR2(32),
  "user_id"      VARCHAR2(64) DEFAULT 'default' NOT NULL,
  "rating"       VARCHAR2(8)  NOT NULL,
  "category"     VARCHAR2(32),
  "comment"      CLOB,
  "corrected_sql" CLOB,
  "status"       VARCHAR2(16) DEFAULT 'open' NOT NULL,
  "learning"     BINARY_DOUBLE,
  "created_at"   TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at"   TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_feedback" PRIMARY KEY ("id"),
  CONSTRAINT "fk_feedback_execution"
    FOREIGN KEY ("execution_id") REFERENCES "execution_history" ("id")
);

CREATE INDEX "ix_feedback_execution_id" ON "feedback" ("execution_id");

CREATE TABLE "synonyms" (
  "id"         VARCHAR2(32)  NOT NULL,
  "term_id"    VARCHAR2(32)  NOT NULL,
  "synonym"    VARCHAR2(255) NOT NULL,
  "source"     VARCHAR2(16)  DEFAULT 'manual' NOT NULL,
  "confidence" BINARY_DOUBLE,
  "created_at" TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  "updated_at" TIMESTAMP(6) WITH TIME ZONE NOT NULL,
  CONSTRAINT "pk_synonyms" PRIMARY KEY ("id"),
  CONSTRAINT "fk_synonyms_term"
    FOREIGN KEY ("term_id") REFERENCES "glossary_terms" ("id")
);

CREATE INDEX "ix_synonyms_term_id" ON "synonyms" ("term_id");
CREATE INDEX "ix_synonyms_synonym" ON "synonyms" ("synonym");


-- =============================================================================
-- SECTION 6 — Alembic migration tracking (Python backend only)
-- =============================================================================

CREATE TABLE "alembic_version" (
  "version_num" VARCHAR2(32) NOT NULL,
  CONSTRAINT "pk_alembic_version" PRIMARY KEY ("version_num")
);

INSERT INTO "alembic_version" ("version_num") VALUES ('d4e5f6a7b8c9');

COMMIT;


-- =============================================================================
-- SECTION 7 — Application connection examples
-- =============================================================================
--
-- Spring Boot (datalens-backend/src/main/resources/application.yml):
--
--   spring:
--     datasource:
--       url: jdbc:oracle:thin:@//hostname:1521/ORCLPDB1
--       username: beeline_meta
--       password: ChangeMeOnInstall
--       driver-class-name: oracle.jdbc.OracleDriver
--       hikari:
--         maximum-pool-size: 10
--     jpa:
--       hibernate:
--         ddl-auto: none
--       properties:
--         hibernate:
--           dialect: org.hibernate.dialect.OracleDialect
--           jdbc:
--             time_zone: UTC
--
-- Add the Oracle JDBC driver to pom.xml:
--   <dependency>
--     <groupId>com.oracle.database.jdbc</groupId>
--     <artifactId>ojdbc11</artifactId>
--     <scope>runtime</scope>
--   </dependency>
--
-- Python FastAPI (backend/config/settings.yaml):
--
--   metadata_repository:
--     url: oracle+oracledb://beeline_meta:ChangeMeOnInstall@hostname:1521/?service_name=ORCLPDB1
--
-- Install driver: pip install oracledb
--
-- =============================================================================
