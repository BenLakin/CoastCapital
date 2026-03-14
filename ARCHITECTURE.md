# CoastCapital Platform Architecture

## System Overview

CoastCapital is a multi-domain personal platform running on Docker, with a
shared MySQL 8.4 database layer, standalone n8n workflow automation, five
independent application services (four Flask + one FastAPI), and Prometheus
metrics with centralized MySQL web analytics. Each domain is owned by a dedicated AI agent that serves
as lead developer and ongoing maintainer.

All services share a single centralized `.env` file at the project root and
communicate via a shared Docker network (`coastcapitaldatabase_db-network`).
n8n handles cron scheduling, Slack dispatch, and error handling as a standalone
container. The Platform module provides an Ollama-powered intent dispatcher with
a feedback dashboard for ground truth collection. Four consolidated Slack
channels replace the original 12+ per-module channels.

```
+-------------------------------------------------------------------------+
|                         CoastCapital Platform                           |
+-------------------------------------------------------------------------+
|                                                                         |
|  +------------------+  +------------------+  +--------------------+     |
|  | CoastFinance     |  | CoastHomelab     |  | CoastAssistant     |     |
|  | Flask :5000      |  | Flask :5200(ext) |  | Flask :5100(ext)   |     |
|  | FinanceAgent     |  | HomeLabAgent     |  | AssistantAgent     |     |
|  |                  |  |                  |  |                    |     |
|  | - ML Forecasting |  | - Device Monitor |  | - iCloud Sync      |     |
|  | - Stock Analysis |  | - Docker Mgmt    |  | - Calendar/Tasks   |     |
|  | - News Sentiment |  | - Service Health |  | - Comms Planning   |     |
|  | - Market Dashboard| | - UniFi/Plex/HA |  | - Email/Contacts   |     |
|  +--------+---------+  +--------+---------+  +---------+----------+     |
|           |                      |                      |               |
|  +--------+---------+  +--------+---------+  +---------+----------+     |
|  | CoastSports      |  | CoastCapitalBrand|  | CoastPlatform      |     |
|  | Flask :5300(ext) |  | (Shared Assets)  |  | FastAPI :5400      |     |
|  | SportsAgent      |  |                  |  |                    |     |
|  |                  |  | - brand.css      |  | - Ollama Dispatch  |     |
|  | - NFL/NCAA/MLB   |  | - SVG logos      |  | - Feedback UI      |     |
|  | - PyTorch Models |  | - Design tokens  |  | - Ground Truth     |     |
|  | - Bracket Sim    |  +------------------+  | - MCP Server       |     |
|  +--------+---------+                        +--------+-----------+     |
|           |                                           |                 |
|           +----------+---+---+---+---+----------------+                 |
|                      |                       |                          |
|              +-------v--------+       +------v-----------+              |
|              | MySQL 8.4      |       | n8n (standalone)  |              |
|              | :3306          |       | :5678             |              |
|              |                |       |                   |              |
|              | 23 databases   |<------+ 23 workflows      |              |
|              | Silver/Int/Gold|       | Cron + Webhook    |              |
|              +-------+--------+       | Slack Dispatcher  |              |
|                      |                | Error Handler     |              |
|              +-------v--------+       +-------------------+              |
|              | Maintenance API|                                          |
|              | :8080          |                                          |
|              | OPTIMIZE/CHECK |                                          |
|              +----------------+                                          |
+-------------------------------------------------------------------------+
```

---

## Configuration

### Centralized `.env`

A single `.env` file at the project root (`/CoastCapital/.env`) replaces the
five per-module `.env` files that existed previously. All docker-compose files
reference it via `env_file: - ../.env`. A documented template at `.env.example`
lists every variable organized by section.

| Section | Example Variables |
|---------|-------------------|
| Global | `TIMEZONE` |
| MySQL | `MYSQL_ROOT_PASSWORD`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST`, `MYSQL_PORT` |
| Maintenance API | `MAINTENANCE_API_KEY` |
| Platform | `PLATFORM_API_KEY`, `PLATFORM_MYSQL_DATABASE` |
| N8N | `N8N_USER`, `N8N_PASSWORD`, `N8N_HOST` |
| Slack | `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` |
| LLM Providers | `ANTHROPIC_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |
| Git / Automation | `GIT_USER_NAME`, `GIT_USER_EMAIL`, `GIT_REMOTE_URL` |
| Finance | `SECRET_KEY`, `ALPHA_VANTAGE_API_KEY`, `NEWS_API_KEY`, `POLYGON_API_KEY` |
| HomeLab | `FLASK_SECRET_KEY`, SSH vars, UniFi/Plex/HA/Portainer |
| Assistant | `ICLOUD_EMAIL`, `ICLOUD_APP_PASSWORD`, `OWNER_NAME`, `FAMILY_EMAILS` |
| Sports | `LLM_PROVIDER`, `LLM_MODEL`, `MODEL_DIR` |

### Dev vs Prod Topology

```
DEV (MacBook - local development)          PROD (Mac Mini - always-on)
+----------------------------------+       +----------------------------------+
|  Docker Compose                  |       |  Docker Compose                  |
|  .env (root)                     |       |  .env (root)                     |
|                                  |       |                                  |
|  MySQL      localhost:3306       |       |  MySQL      macmini.local:3306   |
|  n8n        localhost:5678       |       |  n8n        macmini.local:5678   |
|  Maint API  localhost:8080       |       |  Maint API  macmini.local:8080   |
|  Finance    localhost:5000       |       |  Finance    macmini.local:5000   |
|  HomeLab    localhost:5200       |       |  HomeLab    macmini.local:5200   |
|  Assistant  localhost:5100       |       |  Assistant  macmini.local:5100   |
|  Sports     localhost:5300       |       |  Sports     macmini.local:5300   |
|  Platform   localhost:5400       |       |  Platform   macmini.local:5400   |
+----------------------------------+       +----------------------------------+
```

Both environments use the same Docker Compose files and identical init SQL.
The only differences are credentials and hostnames, controlled by the root
`.env` file.

### Volume Mount Strategy

All application modules mount their source code into the container via
`./app:/app/app` in `docker-compose.yml`. This allows dev-time code changes to
take effect immediately without a container rebuild. Only dependency changes
(new pip packages, updated `requirements.txt`) require a full Docker image
rebuild. Log directories are similarly mounted (`./logs:/app/logs`) for
host-accessible log files.

---

## Agent Architecture

Each module is owned by a dedicated AI agent that acts as lead developer,
domain expert, and ongoing maintainer. Agent definition files are consolidated
in `/CoastCapital/agents/`.

| Module | Agent | Model | Agent File |
|--------|-------|-------|------------|
| CoastCapitalFinance | **FinanceAgent** | claude-sonnet-4-6 | `agents/FINANCE_AGENT.md` |
| CoastCapitalHomelab | **HomeLabAgent** | claude-opus-4-6 | `agents/HOMELAB_AGENT.md` |
| CoastCapitalPersonalAssistant | **AssistantAgent** | claude-opus-4-6 | `agents/ASSISTANT_AGENT.md` |
| CoastCapitalSports | **SportsAgent** | claude-sonnet-4-6 | `agents/SPORTS_AGENT.md` |
| CoastCapitalPlatform | — | — | — |
| CoastCapitalDatabase | **DBAgent** | claude-sonnet-4-6 | — |
| CoastCapital (overall) | **AgentArchitect** | claude-opus-4-6 | — |

---

## Database Architecture

All databases reside on a single MySQL 8.4 instance (`coastcapital-mysql`).
Each domain follows a three-layer medallion architecture (Silver / Internal / Gold).
Finance uses the central MySQL instance (no separate container).

### Database Inventory

| # | Database                      | Domain       | Layer    | Purpose                              |
|---|-------------------------------|-------------|----------|--------------------------------------|
| 1 | `n8n_db`                     | Core         | --       | n8n internal metadata                |
| 2 | `maintenance_db`             | Core         | --       | DB health, optimization logs, dispatch predictions |
| 3 | `finance_silver`             | Finance      | Silver   | Raw OHLCV, news, earnings, macro     |
| 4 | `finance_internal`           | Finance      | Internal | Forecasts, backtests, model registry |
| 5 | `finance_gold`               | Finance      | Gold     | Portfolio snapshots, signal perf     |
| 6 | `homelab_silver`             | HomeLab      | Silver   | Host/service metrics, Docker events  |
| 7 | `homelab_internal`           | HomeLab      | Internal | Health scores, anomaly detection     |
| 8 | `homelab_gold`               | HomeLab      | Gold     | SLA summaries, capacity trends       |
| 9 | `assistant_silver`           | Assistant    | Silver   | Conversations, calendar, tasks, docs |
|10 | `assistant_internal`         | Assistant    | Internal | Entities, memory, embeddings, actions|
|11 | `assistant_gold`             | Assistant    | Gold     | Daily summaries, reminders, KG edges |
|12 | `nfl_silver`                 | Sports (NFL) | Silver   | Teams, players, games, injuries      |
|13 | `nfl_internal`               | Sports (NFL) | Internal | Ratings, projections, predictions    |
|14 | `nfl_gold`                   | Sports (NFL) | Gold     | Weekly picks, standings, rankings    |
|15-23 | `nba_*`, `mlb_*`, `nhl_*` Silver/Internal/Gold | Sports | Various | Placeholder -- future |

### Schema Layer Definitions

```
Silver    Raw/cleaned data from external APIs, scrapers, and user input.
          Fact + Dimension tables. Source of truth.

Internal  Computed signals, ML model outputs, derived metrics.
          Model registry, backtests, anomaly scores.
          Cross-references Silver layer by ID.

Gold      Final aggregated views and tables for dashboards, reports, and APIs.
          Includes SQL VIEWs that join across Silver and Internal layers.
```

### Database Users

| User          | Access Level                              |
|---------------|-------------------------------------------|
| `dbadmin`     | ALL PRIVILEGES on all application databases |
| `reporting`   | SELECT only on all application databases    |
| `maintenance` | DDL + DML on all databases, SUPER on *.*    |

---

## Service-to-Database Mapping

```
CoastFinance Flask (:5000) → coastcapital-mysql
  |-- finance_silver          (read/write)
  |-- finance_internal        (read/write)
  |-- finance_gold            (read/write)

CoastHomelab Flask (:5200 external, :5000 internal)
  |-- homelab_silver          (read/write)
  |-- homelab_internal        (read/write)
  |-- homelab_gold            (read/write)

CoastAssistant Flask (:5100 external, :5000 internal)
  |-- assistant_silver        (read/write)
  |-- assistant_internal      (read/write)
  |-- assistant_gold          (read/write)

CoastSports Flask (:5000)  [uses dbadmin with connection pooling — fixed from root]
  |-- nfl_silver / ncaa_mbb_silver / mlb_silver
  |-- modeling_silver / modeling_internal / research_gold

n8n (:5678) → standalone container
  |-- n8n_db                  (read/write, internal use)

CoastPlatform FastAPI (:5400)
  |-- maintenance_db          (read/write — dispatch_predictions table)

Maintenance API (:8080)
  |-- maintenance_db          (read/write)
  |-- All databases           (OPTIMIZE, ANALYZE, CHECK)

All Flask modules → maintenance_db.web_analytics (centralized web analytics)
```

---

## Slack Channel Architecture

Four consolidated channels replace the original 12+ per-module channels.
All messages are prefixed with module tags: `[Finance]`, `[HomeLab]`, `[Sports]`,
`[Assistant]`, `[Database]`, `[Platform]`.

| Channel | Purpose | Who Posts |
|---------|---------|-----------|
| `#coast-jobs-fyi` | Job started/completed notifications | All 23 workflows |
| `#coast-action-needed` | Failures, errors, MR review, Slack command dispatch | Error handler, health checks, user commands |
| `#coast-current-status` | On-demand system status queries | Platform system status workflow |
| `#coast-recent-summaries` | Reports, forecasts, briefings, picks, digests | Finance signals, HomeLab daily, morning brief, sports picks |

### Slack Dispatcher (Ollama)

Users can trigger any workflow on-demand by posting in `#coast-action-needed`.
The **Platform Slack Dispatcher** workflow uses a **local Ollama** instance for
intent classification (replaced Gemini). The pipeline is:

1. Slack message received
2. Ollama LLM classifies intent with parameter extraction + confidence scoring
3. If confidence >= 0.6, dispatch to the appropriate workflow webhook
4. If confidence < 0.6, post a clarification request to `#coast-action-needed`

Supported intents: `finance_forecast`, `finance_retrain`, `finance_watchlist`,
`homelab_health`, `homelab_report`, `homelab_full_status`, `assistant_brief`,
`assistant_tasks`, `assistant_followup`, `sports_daily`, `sports_nfl_picks`,
`sports_nfl_ingest`, `sports_ncaa_bracket`, `sports_ncaa_prep`, `sports_backfill`,
`sports_news`, `sports_optimization`, `db_maintenance`, `docker_rebuild`,
`architecture_audit`, `system_status`.

### Platform Dispatcher Service (CoastCapitalPlatform)

The Platform module (FastAPI on :5400) provides both an MCP server for Claude
Code integration and a web-based feedback dashboard for ground truth collection.

**Prediction Logging:** Every intent classification is logged to
`maintenance_db.dispatch_predictions` with source, user text, predicted intent,
parameters (JSON), confidence, Ollama model, response time, and webhook path.

**Feedback Dashboard:** A Bootstrap 5 dark-themed UI at `/dashboard` allows
reviewing predictions, upvoting correct ones, and downvoting incorrect ones
(with the ability to specify the correct intent and add notes).

**Ground Truth Loop:** Upvoted and downvoted predictions are injected as
few-shot examples into the Ollama system prompt (max 100 good + 100 bad).
Correct examples are formatted as input→output pairs; incorrect examples
include the predicted vs. correct intent with user notes.

**MCP Server:** `mcp_server.py` exposes intent classification as an MCP tool
for Claude Code, registered in `.mcp.json` at the project root.

---

## N8N Workflow Inventory

N8N runs as a **standalone container** (`coastcapital-n8n`) with its own
`CoastCapitalN8N/docker-compose.yml`. It stores metadata in `n8n_db` on the
shared MySQL instance. All 23 workflow JSON files live in `CoastCapitalN8N/`.

Every workflow supports **dual triggers**: cron schedule + webhook endpoint.
Every workflow posts a "Job Started" notification to `#coast-jobs-fyi` and
includes an error handler call on failure branches that POSTs to the
Platform Error Handler webhook.

### Workflow Table

| # | File | Schedule | Webhook Path | Domain | Description |
|---|------|----------|-------------|--------|-------------|
| 1 | `finance_daily_forecast.json` | Weekdays 6:30 AM ET | `/webhook/finance-forecast` | Finance | ML forecast pipeline, Slack brief |
| 2 | `finance_weekly_retrain.json` | Sunday 2:00 AM ET | `/webhook/finance-retrain` | Finance | Retrain all ML models |
| 3 | `finance_watchlist_sync.json` | Daily 5:00 AM ET | `/webhook/finance-watchlist` | Finance | Sync watchlist, backfill new tickers |
| 4 | `homelab_health_check.json` | Every 5 minutes | `/webhook/homelab-health` | HomeLab | Poll service health, alert on failure |
| 5 | `homelab_daily_report.json` | Daily 8:00 AM ET | `/webhook/homelab-report` | HomeLab | Aggregate metrics, infrastructure digest |
| 6 | `homelab_full_status.json` | Daily 7:30 AM ET | `/webhook/homelab-full-status` | HomeLab | Full 8-service sweep, summary report |
| 7 | `assistant_daily_brief.json` | Daily 7:00 AM ET | `/webhook/assistant-brief` | Assistant | Calendar + tasks + news morning brief |
| 8 | `assistant_task_sync.json` | Every 30 minutes | `/webhook/assistant-tasks` | Assistant | Sync tasks to database |
| 9 | `assistant_followup_check.json` | Daily 9:00 AM ET | `/webhook/assistant-followup` | Assistant | Check unanswered emails > 3 days |
|10 | `sports_daily_pipeline.json` | Daily 6:00 AM ET | `/webhook/sports-daily` | Sports | Full daily: ingest + score + bets |
|11 | `sports_weekly_optimization.json` | Tuesday 3:00 AM ET | `/webhook/sports-optimization` | Sports | Refit models, weekly betting plan |
|12 | `sports_ncaa_bracket.json` | Daily 5:00 AM (Mar-Apr) | `/webhook/sports-ncaa-bracket` | Sports | 10k Monte Carlo bracket simulation |
|13 | `sports_news_ingest.json` | Every 6 hours | `/webhook/sports-news` | Sports | ESPN news ingest + LLM summaries |
|14 | `sports_backfill.json` | Manual trigger | `/webhook/sports-backfill` | Sports | Historical backfill + features |
|15 | `sports_nfl_weekly_picks.json` | Monday 6:00 AM ET | `/webhook/sports-nfl-picks` | Sports | Weekly NFL picks (in-season) |
|16 | `sports_nfl_game_ingest.json` | Sun/Thu/Mon 11:30 PM | `/webhook/sports-nfl-ingest` | Sports | Game results + rating updates |
|17 | `mysql_maintenance.json` | Nightly 2 AM + 6h health | `/webhook/db-maintenance` | Database | Analyze, optimize, health snapshots |
|18 | `platform_slack_dispatcher.json` | Slack trigger | — | Platform | Ollama LLM intent → workflow dispatch |
|19 | `platform_error_handler.json` | Webhook trigger | `/webhook/platform-error-handler` | Platform | Anthropic API → Git MR → Slack |
|20 | `platform_system_status.json` | Webhook trigger | `/webhook/platform-system-status` | Platform | Multi-service health report |
|21 | `platform_docker_rebuild.json` | Manual trigger | `/webhook/docker-rebuild` | Platform | Rebuild all containers (except MySQL/N8N) → health check → Slack report |
|22 | `platform_architecture_audit.json` | Manual trigger | `/webhook/architecture-audit` | Platform | Architecture audit via Anthropic API |
|23 | `sports_ncaa_tournament_prep.json` | Manual trigger | `/webhook/sports-ncaa-prep` | Sports | Full NCAA prep: backfill → features → train → promote → simulate bracket |

### Error Handler Pipeline

When any workflow fails, it POSTs error context to the **Platform Error Handler**
(`/webhook/platform-error-handler`). The handler:

1. Captures error details (workflow name, error message, stack trace, module)
2. Calls Anthropic API (`claude-sonnet-4-6`) to analyze the error and suggest a fix
3. Creates a Git branch (`fix/{workflow}-{timestamp}`), commits the suggested fix
4. Opens a GitHub Pull Request via GitHub API
5. Notifies `#coast-action-needed` with the MR link for review

---

## Brand System

All modules consume shared brand assets from `CoastCapitalBrand/`:

```
CoastCapitalBrand/
  css/brand.css       CSS custom properties, base typography, shared components
  css/nav.css         Platform navigation bar styles
  js/nav.js           Cross-module navigation component (auto-injected)
  img/logo.svg        Full wordmark (CoastCapital)
  img/logo-icon.svg   Icon-only mark for compact headers
  img/favicon.svg     Browser tab icon
```

### Platform Navigation

A shared JavaScript nav bar (`nav.js` + `nav.css`) is injected at the top of every
module page. It auto-detects the current module from `window.location.port` and
highlights the active module/page. Cross-module links resolve using the current
hostname with the target port, so it works in both dev (localhost) and prod
(macmini.local) without configuration.

Registered modules in nav.js: Finance (:5000), Sports (:5300), HomeLab (:5200),
Assistant (:5100), Database (:8080), Platform (:5400), N8N (:5678).

Each module mounts or copies brand assets into its `static/brand/` directory.
See `CoastCapitalBrand/README.md` for integration instructions.

---

## System Monitoring

The HomeLab module provides multi-machine system monitoring via `SystemPipeline`.

### Supported Machine Types
- **Local Mac** — macOS `top`, `vm_stat`, `df`, `sysctl` for CPU, RAM, disk
- **Remote Ubuntu** — SSH via paramiko, Linux `top`, `df`, `nvidia-smi` for CPU, RAM, disk, GPU
- **Extra Machines** — JSON-configured via `EXTRA_MACHINES` env var for additional hosts

### EXTRA_MACHINES Format
```json
[
  {
    "name": "GPU-Server-2",
    "type": "ubuntu",
    "desc": "Secondary GPU compute node",
    "host": "192.168.1.50",
    "user": "ubuntu",
    "ssh_key": "/keys/gpu2_rsa"
  }
]
```

### Dashboard
The HomeLab dashboard dynamically renders one system card per machine using
`buildMachineCard()` in JavaScript. GPU sections are conditionally shown only
when `gpu_name` is present in the machine data.

---

## Port Assignments

| Port | Service              | Protocol | Container Name              | Notes                        |
|------|----------------------|----------|-----------------------------|------------------------------|
| 3306 | MySQL 8.4            | TCP      | coastcapital-mysql          | Shared database instance     |
| 5000 | CoastFinance Flask   | HTTP     | coast_capital_finance       | Stock analysis + ML API      |
| 5100 | CoastAssistant Flask | HTTP     | coastcapital-assistant      | Personal assistant API       |
| 5200 | CoastHomelab Flask   | HTTP     | coastcapital-homelab        | Infrastructure monitoring    |
| 5300 | CoastSports Flask    | HTTP     | coastcapital-sports         | Sports prediction + ML       |
| 5400 | CoastPlatform FastAPI| HTTP     | coastcapital-platform       | Dispatcher + feedback UI     |
| 5678 | n8n (standalone)     | HTTP     | coastcapital-n8n            | Workflow automation UI       |
| 8080 | Maintenance API      | HTTP     | coastcapital-db-maintenance | DB health + optimization     |

---

## Directory Structure

```
CoastCapital/
|-- .env                            Centralized environment variables (all modules)
|-- .env.example                    Template with all ~80 variables documented
|-- .mcp.json                       MCP server registration for Claude Code
|-- .gitignore                      Prevents committing secrets, logs, caches
|-- ARCHITECTURE.md                 This file
|
|-- agents/                         Consolidated agent definition files
|   |-- FINANCE_AGENT.md
|   |-- HOMELAB_AGENT.md
|   |-- ASSISTANT_AGENT.md
|   |-- SPORTS_AGENT.md
|
|-- tests/                          Cross-module integration tests
|   |-- test_connectivity.py        2-pass: health + metrics, N8N integration
|
|-- CoastCapitalBrand/              Shared brand assets (CSS, logos, icons)
|   |-- css/brand.css
|   |-- js/nav.js                   Platform navigation (includes N8N)
|   |-- img/logo.svg, logo-icon.svg, favicon.svg
|
|-- CoastCapitalDatabase/           MySQL + Maintenance API
|   |-- docker-compose.yml          Docker stack (MySQL + Maintenance API)
|   |-- mysql/init/01-schemas.sql   All database + table DDL (23 databases)
|   |-- mysql/init/02-maintenance-procedures.sql
|   |-- mysql/config/my.cnf         MySQL tuning configuration
|   |-- maintenance-api/            FastAPI maintenance REST API (:8080)
|
|-- CoastCapitalPlatform/           Ollama intent dispatcher + feedback dashboard
|   |-- docker-compose.yml          FastAPI service (:5400)
|   |-- app/main.py                 FastAPI app (HTML + JSON API)
|   |-- app/dispatcher.py           Ollama intent classifier + ground truth
|   |-- app/db.py                   MySQL pool, prediction logging, feedback
|   |-- app/mcp_server.py           MCP server for Claude Code integration
|   |-- app/templates/              Jinja2 templates (feedback dashboard)
|   |-- app/static/                 CSS + JS for feedback UI
|
|-- CoastCapitalN8N/                Standalone n8n container + 23 workflow files
|   |-- docker-compose.yml          N8N standalone (MySQL backend, git repo mount)
|   |-- workflows/
|   |   |-- finance/     (3 files)  Finance workflows
|   |   |-- homelab/     (3 files)  HomeLab workflows
|   |   |-- assistant/   (3 files)  Assistant workflows
|   |   |-- sports/      (7 files)  Sports workflows (includes ncaa_tournament_prep)
|   |   |-- database/    (1 file)   Database maintenance workflow
|   |   |-- platform/    (5 files)  Platform workflows (dispatcher, error, status, docker_rebuild, architecture_audit)
|
|-- CoastCapitalFinance/            Agent: FinanceAgent
|   |-- docker-compose.yml          Flask only (uses central MySQL)
|   |-- app/models/                 SQLAlchemy star schema
|   |-- app/pipelines/              Ingestion, technicals, backfill
|   |-- app/forecasting/            LightGBM + XGBoost ensemble
|   |-- app/agents/                 Claude-powered finance agent
|   |-- app/routes/                 n8n + REST + market APIs
|   |-- app/static/                 Bloomberg-style dark dashboard
|   |-- app/utils/metrics.py         Prometheus metrics + MySQL web analytics
|
|-- CoastCapitalHomelab/            Agent: HomeLabAgent
|   |-- app/pipelines/              8 service pipelines (SSH, UniFi, Plex, HA, etc.)
|   |-- app/pipelines/system_pipeline.py  Multi-machine + EXTRA_MACHINES support
|   |-- app/agents/                 Claude-powered homelab agent (22 tools)
|   |-- app/templates/              Glassmorphism dashboard (dynamic machine cards)
|   |-- app/utils/metrics.py         Prometheus metrics + MySQL web analytics
|
|-- CoastCapitalPersonalAssistant/  Agent: AssistantAgent
|   |-- app/pipelines/              12 pipelines (email, calendar, news, weather, comms, etc.)
|   |-- app/agents/                 Claude-powered assistant agent (10 tools)
|   |-- app/templates/              Dashboard, communications, relationships
|   |-- app/utils/metrics.py         Prometheus metrics + MySQL web analytics
|
|-- CoastCapitalSports/             Agent: SportsAgent
|   |-- app/ingestion/              ESPN ingest (NFL, NCAA, MLB)
|   |-- app/models/                 PyTorch train/CV/tune/promote lifecycle
|   |-- app/features/               137 feature columns + feature engineering
|   |-- app/bracket/                NCAA tournament simulation + optimizer
|   |-- app/portfolio/              Kelly criterion bankroll allocation
|   |-- app/utils/metrics.py         Prometheus metrics + MySQL web analytics
```

---

## Observability

### Prometheus Metrics

Every module exposes a `/metrics` endpoint via `prometheus_client` for scraping.
Standard metrics: `http_requests_total` (Counter), `http_request_duration_seconds`
(Histogram), `http_errors_total` (Counter). All labeled by `module`, `method`, `path`.

### Centralized Web Analytics (MySQL)

All modules log page views, errors, and actions to a shared
`maintenance_db.web_analytics` table via fire-and-forget `threading.Thread(daemon=True)`
INSERTs. Each row includes a `module` column (`finance`, `homelab`, `sports`,
`assistant`) and `path` column to identify origin. The shared `metrics.py` in
each module handles both Prometheus counters and MySQL logging.

### Structured Logging

All modules output JSON-formatted logs:
- Finance: `structlog`
- HomeLab: `JsonFormatter`
- Sports: `JsonFormatter`
- Assistant: Rotating file handlers
- Database APIs: Custom formatters

Log directories are mounted via Docker volumes (`./logs:/app/logs`).

---

## Testing

### Local Unit/Integration Tests

| Module | Test Count | Notes |
|--------|-----------|-------|
| PersonalAssistant | 156 | Runs locally without Docker |
| HomeLab | 13 | Runs locally without Docker |
| Sports | 17 | Runs locally without Docker |
| Finance | — | Requires Docker (MySQL) |
| Database | — | Requires Docker (MySQL) |
| **Total (local)** | **186** | |

### Platform Integration Test Suite

`tests/test_connectivity.py` implements a two-pass integration test:

| Pass | What It Tests | How |
|------|--------------|-----|
| Pass 1 — Health + Metrics | GET `/health` on all 7 services + `/metrics` on 4 Flask modules | Parametrized pytest, assert 200 OK |
| Pass 2 — N8N | All 23 webhook paths respond | POST test payloads, verify acknowledgment |

Run: `pytest tests/test_connectivity.py` (requires all containers running).

---

## Data Flow

```
External APIs                  n8n Dual Triggers
(yfinance, ESPN, iCloud,       (cron schedules + webhook endpoints)
 NewsAPI, weather)                     |
        |                             v
        v                    Flask Service APIs
   Flask Pipelines  <-----  (/n8n/* and /api/* endpoints)
        |
        v
  Silver Layer (raw data)
        |
        v
  Internal Layer (ML models, scores, predictions)
        |
        v
  Gold Layer (views, aggregates, dashboards)
        |
        v
  Slack Channels / Email / Dashboard consumers
        |
  #coast-jobs-fyi          Job lifecycle notifications
  #coast-action-needed     Errors, commands, MR review
  #coast-recent-summaries  Reports, forecasts, picks
  #coast-current-status    On-demand status queries
```

### Error Flow

```
Any Workflow Failure
        |
        v
  POST /webhook/platform-error-handler
        |
        v
  Anthropic API (Claude analysis + fix suggestion)
        |
        v
  Git: branch → commit → push → GitHub PR
        |
        v
  Slack #coast-action-needed (MR link for review)
```
