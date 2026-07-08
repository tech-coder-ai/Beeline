# Beeline — Setup Guide

Step-by-step instructions for getting Beeline running locally. For an
architecture overview and the pipeline diagram, see [README.md](README.md).

Three paths:

- **[Option A: Docker Compose](#option-a-docker-compose-full-stack)** — full stack
  including a standalone local Hive instance and seeded sample data. Slowest
  first run (image pulls), zero manual setup.
- **[Option B: Manual local setup](#option-b-manual-local-setup)** — backend +
  frontend run directly on your machine. Fastest iteration loop. Point at local
  Hive (including the partial-Docker Hive option), cloud Hive, or nothing while
  Hive is unreachable — the app degrades gracefully.
- **[Option C: Backend + UI with cloud Hive](#option-c-backend--ui-with-cloud-hive-no-docker)** —
  same as Option B but explicitly for connecting to a remote/cloud Hive cluster
  with no Docker at all.

---

## Prerequisites (summary)

| Tool | Version | Required for | Check |
|---|---|---|---|
| Python | 3.11+ (**3.12 recommended**) | Backend | `python3.12 --version` |
| pip or [uv](https://docs.astral.sh/uv/) | latest | Backend install | `uv --version` |
| Node.js | **20+** (22 works) | Frontend | `node --version` |
| npm | **10+** | Frontend install | `npm --version` |
| Docker + Compose | Option A (and optional Hive in B) | `docker --version` |
| LLM access | — | Chat NL→SQL (degrades without) | OpenAI key or Stellar endpoint |
| Hive / HiveServer2 | — | Data queries & catalog sync | Local (Docker) or cloud endpoint |
| Redis | — | Optional | Falls back to in-memory cache |
| PostgreSQL | — | Optional | SQLite is the default metadata store |

Beeline's metadata repository (chat sessions, catalog, dashboards, logs) is
**separate from Hive**. Metadata Manager, Glossary, Dashboards, Query Library,
and Admin all work against SQLite/Postgres even when Hive is unreachable.

---

## Backend prerequisites (detailed)

| Requirement | Details |
|---|---|
| **Python** | `>=3.11` per `backend/pyproject.toml`; **3.12 recommended** |
| **Virtual env** | `python3.12 -m venv .venv` or `uv venv --python 3.12 .venv` |
| **Install** | `pip install -e ".[dev]"` or `uv pip install -e ".[dev]"` from `backend/` |
| **Metadata DB** | **SQLite** (default, zero setup, file `backend/beeline_meta.db`) or **PostgreSQL 16+** |
| **Redis** | Optional — query-result cache falls back to in-memory if unavailable |
| **Hive** | Optional for UI exploration; required for NL→SQL against real data |
| **LLM** | One of: OpenAI-compatible (`OPENAI_API_KEY`) or Stellar (`STELLAR_ENDPOINT`) |

**Python dependencies** (from `backend/pyproject.toml`):

| Package | Purpose |
|---|---|
| fastapi, uvicorn | REST API |
| sqlalchemy[asyncio], aiosqlite, asyncpg | Metadata repository |
| pydantic, pydantic-settings | Config & validation |
| alembic | Postgres schema migrations |
| httpx | LLM HTTP clients |
| sqlglot | SQL parsing & guard rails |
| redis | Optional result cache |
| pyyaml | `settings.yaml` |
| pyhive, thrift | Hive connector |
| rapidfuzz | Query-library similarity |
| openpyxl | Spreadsheet import |
| pytest, ruff | Dev/test (optional `[dev]` extra) |

**Environment variables:**

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI-compatible LLM provider |
| `STELLAR_ENDPOINT` | Custom Stellar LLM endpoint |
| `BEELINE_CONFIG` | Path to settings file (e.g. `config/settings.yaml`) |
| `BEELINE__SECTION__KEY` | Dot-path overrides, e.g. `BEELINE__CONNECTORS__DEFINITIONS__HIVE__HOST=localhost` |

Config files: `backend/config/settings.yaml` (local dev), `backend/config/settings.docker.yaml` (Docker).

---

## Frontend prerequisites (detailed)

| Requirement | Details |
|---|---|
| **Node.js** | 20+ (Angular 20; Node 22 used in Docker build) |
| **npm** | 10+ |
| **Install** | `npm install --legacy-peer-deps` (required once — peer dep ranges) |
| **Dev server** | `npm run start -- --port 4210` |
| **API proxy** | `frontend/proxy.conf.json` forwards `/api` → backend (default `http://localhost:8010`) |
| **Env file** | None — feature flags and config come from the backend API |

**npm dependencies** (from `frontend/package.json`):

| Package | Purpose |
|---|---|
| @angular/* 20.x | App framework (standalone + signals) |
| @angular/material, @angular/cdk | UI components |
| ag-grid-angular, ag-grid-community | Data grids |
| echarts, ngx-echarts | Charts |
| marked | Markdown rendering |
| rxjs, zone.js, tslib | Angular runtime |

**Dev dependencies:** Angular CLI/build, TypeScript 5.9, Karma/Jasmine (tests).

**Tests (optional):** Chrome/Chromium for `ng test`.

---

## Option A: Docker Compose (full stack)

This brings up Postgres (metadata repository), Redis, a standalone
HiveServer2 with an embedded Derby metastore, a one-shot job that loads
~4,300 rows of generated sample sales data, the backend, and the frontend.

```bash
git clone <this-repo>
cd Beeline
cp .env.example .env
```

Edit `.env`:

```bash
# Pick ONE provider path and configure it in backend/config/settings.docker.yaml (llm.active)
OPENAI_API_KEY=sk-...
# or, if using the Stellar provider:
STELLAR_ENDPOINT=http://host.docker.internal:9000/generate
```

Start everything:

```bash
docker compose up --build
```

First run downloads the `apache/hive:3.1.3`, `postgres:16-alpine`, and
`redis:7-alpine` images and builds the backend/frontend images — expect
several minutes. Subsequent starts are fast.

Services and ports:

| Service | URL / Port |
|---|---|
| Frontend | http://localhost:8080 |
| Backend API + docs | http://localhost:8000/api/docs |
| Postgres | localhost:5432 (`beeline`/`beeline`) |
| Redis | localhost:6379 |
| HiveServer2 | localhost:10000 (Beeline) / localhost:10002 (web UI) |

**Load the sample data into Beeline's catalog.** The `hive-init` container
creates the `sales.dim_customers`, `sales.dim_products`, and
`sales.fact_sales` tables directly in Hive, but Beeline's NL pipeline only
ever reads its own synchronized catalog — never the live Hive metastore. Sync
it once the stack is up:

1. Open http://localhost:8080 → **Admin → Connectors & Sync**
2. Click **Test connection** on the Hive connector to confirm it's reachable
   (the `hive-init` job can take ~30–60s after `hive-server` starts)
3. Click **Full sync**
4. Switch to **Metadata → Catalog** to confirm the three tables appear

Now the Chat page can answer questions like *"Show sales by region for last 6
months"* or *"Which products have declining revenue?"* against real data.

To stop: `docker compose down`. Add `-v` to also drop the Postgres and Hive
warehouse volumes (full reset).

---

## Option B: Manual local setup

### 1. Backend

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install -e ".[dev]" --python .venv/bin/python
```

(No `uv`? `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"` works
identically.)

Start the API:

```bash
.venv/bin/uvicorn app.main:app --reload --port 8010
```

- If port `8010` is already in use on your machine, pick another and update
  `frontend/proxy.conf.json` (see step 2) to match.
- The backend auto-creates `backend/beeline_meta.db` (SQLite) on first start —
  no migration step needed for local dev. To use Postgres instead, edit
  `backend/config/settings.yaml` → `metadata_repository.url`, or run Alembic
  migrations against a Postgres instance (see [Migrations](#migrations-alembic)).
- Verify it's up: http://localhost:8010/api/docs

**Point it at Hive** (optional — everything except Chat's data queries works
without this): edit `backend/config/settings.yaml` → `connectors.definitions.hive`,
or override via environment variables without touching the file:

```bash
export BEELINE__CONNECTORS__DEFINITIONS__HIVE__HOST=your-hive-host
export BEELINE__CONNECTORS__DEFINITIONS__HIVE__PORT=10000
export BEELINE__CONNECTORS__DEFINITIONS__HIVE__DATABASE=default
```

No Hive available but want to try the full NL→SQL flow? You can bring up just
the Hive pieces with `docker compose up -d hive-server hive-init` and point
the local backend above at `localhost:10000` — **but only if you have never
run `docker compose up` for this project before** (i.e. `docker network ls`
shows no `beeline_default` network yet). If you later run the full
`docker compose up` for all services, tear this partial stack down first
(`docker compose down`) rather than layering it on top — see
[Troubleshooting](#containers-cant-reach-each-other--namegaierror-name-or-service-not-known)
below for why.

After Hive is reachable, sync the catalog:

1. Open http://localhost:4210 → **Admin → Connectors & Sync**
2. Click **Test connection** on the Hive connector
3. Click **Full sync**
4. Confirm tables under **Metadata → Catalog**

### 2. Frontend

```bash
cd frontend
npm install --legacy-peer-deps
```

`--legacy-peer-deps` is required once — `@angular/animations` and
`@angular/material`/`@angular/cdk` resolve to slightly different exact-version
peer ranges than npm's default resolver accepts, even though the versions
installed are correct. You won't need the flag again after the initial
install.

`proxy.conf.json` forwards `/api/*` to the backend so the Angular dev server
and the API appear same-origin to the browser:

```json
{ "/api": { "target": "http://localhost:8010", "secure": false, "changeOrigin": true } }
```

If you started the backend on a different port, update `target` here first.

Start the dev server:

```bash
npm run start -- --port 4210
```

(Port `4200` is Angular's default — use it if it's free on your machine:
`npm run start`.)

Open http://localhost:4210.

### 3. Sanity check

- Chat page loads with the four suggestion chips and an empty session list.
- Ask a question. With no catalog synced yet, you should see the
  **clarification** flow ("I couldn't confidently match your question to the
  available data...") rather than an error — this is correct behavior, not a
  bug.
- Admin → Connectors & Sync shows the configured Hive connector (test
  connection will fail until Hive is reachable — expected if you skipped the
  Hive step above).

---

## Option C: Backend + UI with cloud Hive (no Docker)

Same as [Option B](#option-b-manual-local-setup) for starting the backend and
frontend — but **without any Docker services**. Use this when your Hive
cluster runs in the cloud and you only run Beeline's API and UI locally.

### 1. Start backend and frontend

Follow [Option B §1 Backend](#1-backend) and [Option B §2 Frontend](#2-frontend).

### 2. Connect to cloud Hive

Edit `backend/config/settings.yaml` → `connectors.definitions.hive`, **or**
override with environment variables:

```bash
export BEELINE__CONNECTORS__DEFINITIONS__HIVE__HOST=hive.cloud.example.com
export BEELINE__CONNECTORS__DEFINITIONS__HIVE__PORT=10000
export BEELINE__CONNECTORS__DEFINITIONS__HIVE__DATABASE=default
export BEELINE__CONNECTORS__DEFINITIONS__HIVE__USERNAME=your_user
export BEELINE__CONNECTORS__DEFINITIONS__HIVE__PASSWORD=your_password
export BEELINE__CONNECTORS__DEFINITIONS__HIVE__AUTH=LDAP    # NONE | NOSASL | LDAP | KERBEROS
```

Or use **Admin → Connectors & Sync** in the UI to add/update the connector
(host, port, auth, credentials) without restarting.

### 3. Sync the catalog

1. Open http://localhost:4210 → **Admin → Connectors & Sync**
2. Click **Test connection** on your Hive connector
3. Click **Full sync** to harvest databases/tables/columns into Beeline's catalog
4. Confirm tables under **Metadata → Catalog**
5. Ask questions on the **Chat** page

**Network notes for cloud Hive:**

- Your machine must reach the HiveServer2 host/port (VPN, security group, or
  bastion as required by your cloud provider).
- TLS-terminated endpoints may need a different port or a tunnel — point
  `host`/`port` at whatever endpoint accepts the Hive thrift protocol.
- Kerberos setups need additional client configuration on the machine running
  the backend (keytab, `krb5.conf`); LDAP/NOSASL are simpler for first tests.

### What works without Hive

| Feature | Without Hive |
|---|---|
| Chat UI | Loads; clarification flow when catalog is empty |
| Metadata Manager, Glossary | Works (empty until sync) |
| Dashboards, Query Library | Works |
| Admin → Logs & Analytics | Works |
| Admin → Connectors | Works (test connection fails until Hive is reachable) |
| NL→SQL with real data | Needs catalog sync from Hive |

---

## Configuring the LLM provider

`backend/config/settings.yaml` → `llm.active` picks the provider; provider
configs live under `llm.providers`.

**OpenAI-compatible** (OpenAI, Azure OpenAI, vLLM, Ollama, etc.):

```yaml
llm:
  active: openai
  providers:
    openai:
      type: openai
      base_url: https://api.openai.com/v1
      api_key: ${OPENAI_API_KEY}
      model: gpt-4o
```

Set `OPENAI_API_KEY` in your shell or a `.env` file before starting uvicorn.

**Stellar** (your custom local endpoint):

```yaml
llm:
  active: stellar
  providers:
    stellar:
      type: stellar
      endpoint: http://localhost:9000/generate
      response_field: response   # dot-path into the JSON reply, e.g. data.output
```

Beeline POSTs `{"systemPrompt": "...", "userMessage": "..."}` to `endpoint`
and reads the reply text from `response_field` of the JSON response (blank
`response_field` = treat the entire response body as the reply text).

No API key configured, or the endpoint unreachable? The pipeline degrades
gracefully — intent classification falls back to keyword heuristics, SQL
generation falls back to a deterministic plan-to-SQL builder — and a warning
is surfaced in the chat UI's **Warnings** tab rather than a hard failure.

---

## Admin: clear logs and analytics

**Admin → Logs & Analytics → Clear logs** removes:

- Execution history (and derived usage analytics)
- User feedback tied to executions
- Audit trail entries

Chat messages, dashboards, metadata catalog, and glossary are **not** deleted.
Execution links on chat messages and dashboard widgets are cleared safely.

API equivalents (require `confirm=true`):

```bash
# Clear everything shown on the Logs & Analytics tab
curl -X DELETE 'http://localhost:8010/api/v1/admin/logs?confirm=true'

# Or individually:
curl -X DELETE 'http://localhost:8010/api/v1/admin/logs/executions?confirm=true'
curl -X DELETE 'http://localhost:8010/api/v1/admin/logs/audit?confirm=true'
```

---

## Migrations (Alembic)

Local dev SQLite doesn't need migrations — `init_db()` creates tables on
startup. For Postgres or any environment where you want tracked schema
changes:

```bash
cd backend
export BEELINE_CONFIG=$(pwd)/config/settings.yaml   # or settings.docker.yaml
.venv/bin/alembic upgrade head
```

After changing a model in `app/models/`, generate a new migration:

```bash
.venv/bin/alembic revision --autogenerate -m "describe the change"
```

Review the generated file in `alembic/versions/` before applying it — always
true of autogenerated migrations, but especially so given SQLite's limited
`ALTER TABLE` support if you're testing against it.

---

## Running tests

```bash
# backend (guard rails, SQL optimizer, deterministic SQL builder,
# visualization planner, LLM provider contracts)
cd backend && .venv/bin/pytest -q

# frontend
cd frontend && npx ng test --watch=false --browsers=ChromeHeadless
```

The frontend test runner (Karma) needs a Chrome/Chromium binary. If
`ng test` can't find one, point it at your install:

```bash
CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  npx ng test --watch=false --browsers=ChromeHeadless
```

---

## Troubleshooting

**`npm install` fails with `ERESOLVE` / peer dependency conflicts**
Use `npm install --legacy-peer-deps`. This is expected for this dependency
set (see [Frontend](#2-frontend) above) — not a sign of a broken lockfile.

**Backend fails to start: `ModuleNotFoundError`**
You're likely running the system Python instead of the venv. Always invoke
`.venv/bin/uvicorn` / `.venv/bin/pytest` / `.venv/bin/alembic` explicitly, or
`source .venv/bin/activate` first.

**Port already in use**
Both `8010` (backend) and `4210` (frontend) were chosen to dodge common
defaults (`8000`, `4200`) that are frequently occupied by other local
projects. If they're taken too, pick any free port and update
`frontend/proxy.conf.json` (backend target) and your `ng serve --port`
invocation (frontend) accordingly — nothing else is hardcoded to these ports.

**Chat always asks for clarification / never returns data**
Expected until you sync the Hive catalog (Admin → Connectors & Sync → Full
sync) — Beeline refuses to guess at tables it hasn't verified exist, by
design. Confirm tables appear under Metadata → Catalog first.

**Cannot reach cloud Hive**
Check VPN, firewall rules, and that `host`/`port`/`auth` match your cluster's
HiveServer2 endpoint. Use Admin → Test connection for the exact error message.

**`docker compose up` — `hive-init` keeps retrying**
HiveServer2 can take 30–90 seconds to become ready on first boot (Derby
metastore initialization). `hive-init` polls every 5 seconds and will proceed
automatically once ready; this is not a failure unless it's still retrying
after several minutes, in which case check `docker compose logs hive-server`.

**Guard rail rejects a query you believe is safe**
This is very likely correct — Beeline is intentionally strict (single
SELECT statement, no comments, no cartesian joins, bounded join depth). See
`backend/tests/test_guardrails.py` for the exact rules and
`backend/config/settings.yaml` → `guardrails` for the adjustable thresholds
(the SELECT-only enforcement itself is not configurable).

**Containers can't reach each other — `socket.gaierror: Name or service not known`**
The backend crashes on startup trying to resolve `postgres` (or `redis`,
`hive-server`) by hostname. This means the containers ended up on different
Docker networks — typically because some services were started in an earlier
`docker compose up <specific-service>` run, and the rest were brought up
later in a separate invocation. Docker Compose only guarantees every service
lands on the same network (`beeline_default`) when they're created together;
layering a second `up` on top of a stack that was partially started earlier
can leave the older containers stranded on a network the newer ones aren't
attached to.

Confirm this is the cause: `docker network inspect beeline_default` and check
whether every service you expect (`postgres`, `redis`, `hive-server`,
`backend`, `frontend`) actually appears in the container list.

Fix: tear down and bring the whole stack up together.

```bash
docker compose down          # removes containers only — named volumes
                              # (beeline-postgres, beeline-hive-warehouse)
                              # are preserved, so your synced catalog and
                              # Postgres data survive
docker compose up -d
```

Avoid re-triggering this by not mixing `docker compose up <service>` and
`docker compose up` (no args) across separate invocations for the same
project — always bring up the full stack, or tear down first if you
deliberately want a subset running.
