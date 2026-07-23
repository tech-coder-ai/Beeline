# DataLens Backend (Java 21)

**DataLens** is the Spring Boot 3.x Java service for the Beeline platform — API-compatible with the Python FastAPI backend in [`../backend`](../backend).

## Requirements

- Java **21**
- Maven **3.9+**
- Shared config: [`../backend/config/settings.yaml`](../backend/config/settings.yaml)
- Shared metadata DB: [`../backend/beeline_meta.db`](../backend/beeline_meta.db) (SQLite, `ddl-auto: none`)

## Run

### Standalone (embedded Tomcat, development)

Requires a Tomcat-capable classpath at runtime (e.g. run from the IDE with full dependencies, or deploy the WAR below).

```bash
cd datalens-backend
export OPENAI_API_KEY=sk-...   # when llm.active uses OpenAI
mvn -q package
# Deploy target/datalens.war to Tomcat, or use spring-boot:run for local dev:
mvn spring-boot:run
```

### WAR for Tomcat / servlet container

```bash
cd datalens-backend
mvn -q clean package
```

Artifact: **`target/datalens.war`**

Deploy to Tomcat (example):

```bash
cp target/datalens.war $CATALINA_HOME/webapps/
```

Set `datalens.config-path` and the SQLite JDBC URL to absolute paths on the server (defaults are relative to the process working directory). Optional context path via `server.servlet.context-path` in `application.yml` or the Tomcat app name (`/datalens` when the WAR is named `datalens.war`).

- API base: http://localhost:8010/api/v1
- OpenAPI UI: http://localhost:8010/api/docs
- OpenAPI JSON: http://localhost:8010/api/openapi.json
- Actuator: http://localhost:8010/actuator/health

Run **one** backend at a time on port **8010** (same as the Python app).

## Configuration

| Property | Default | Purpose |
|----------|---------|---------|
| `datalens.config-path` | `../backend/config/settings.yaml` | Platform YAML |
| `datalens.api-prefix` | `/api/v1` | REST prefix |
| `server.port` | `8010` | HTTP port |

Environment overrides for this service: `DATALENS__SECTION__KEY=value` (Python backend uses `BEELINE__…` for the same YAML shape).

## REST parity

Controllers under `com.datalens.api` mirror FastAPI routers:

| Area | Paths |
|------|--------|
| Chat | `POST /chat`, sessions CRUD |
| Metadata | `/metadata/*`, approvals, import |
| Glossary | `/glossary`, `/glossary/metrics` |
| Workspace | `/sql/*`, `/queries`, `/dashboards`, `/feedback`, `/executions/{id}` |
| Admin | `/admin/*` connectors, sync, enrich, config, logs |
| Health | `/health`, `/health/deep` |

JSON uses **snake_case** (Jackson `SNAKE_CASE`).

## Package layout

| Package | Role |
|---------|------|
| `com.datalens.config` | YAML settings, CORS, Jackson |
| `com.datalens.api` | REST controllers |
| `com.datalens.schema` | API records + `DataLensResponseDto` |
| `com.datalens.model` | JPA entities + repositories |
| `com.datalens.service` | Chat, sync, approval, import, etc. |
| `com.datalens.pipeline` | Orchestrator + stages (`PipelineStages`) |
| `com.datalens.connectors` | Registry + Hive JDBC |
| `com.datalens.llm` | OpenAI-compatible + Stellar (`RestClient`) |

## Parity notes

| Topic | Python | Spring |
|-------|--------|--------|
| SQL parse/guard | **sqlglot** | **JSqlParser** — same rules, different edge-case coverage |
| SQL sanitize | sqlglot AST rewrites | Regex + JSqlParser LIMIT injection |
| Semantic search | rapidfuzz | Jaro–Winkler + token overlap |
| Hive access | PyHive (async threads) | Hive JDBC 3.x |
| Result cache | Redis + memory fallback | In-memory cache (Redis autoconfig disabled) |
| Kerberos kinit | Supported in Python connector | Not ported — configure tickets externally for JDBC |
| Pipeline stages | Separate modules | Consolidated in `PipelineStages` + `Orchestrator` (same flow) |

Extend `SqlValidator` / `SqlUtils` when you hit sqlglot vs JSqlParser differences.

## Build

```bash
mvn -q clean package    # produces target/datalens.war
mvn -q test             # when tests are added
```

If `mvn` is missing, install Maven 3.9+ and a JDK 21 toolchain.
