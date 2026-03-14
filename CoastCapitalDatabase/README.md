# CoastCapital Database

## What
The shared MySQL 8.4 data layer for the entire CoastCapital platform. Hosts 25 databases across 5 domains (Finance, HomeLab, Assistant, Sports, Core), each following a Silver/Internal/Gold medallion architecture. Includes n8n workflow automation and a FastAPI maintenance API with stored procedures for automated health monitoring.

## Why
All four application modules need a reliable, well-tuned, centrally managed database. Rather than each module running its own MySQL instance, a single shared instance provides: consistent schema governance (medallion layers), unified user/permission management, centralized maintenance (OPTIMIZE, ANALYZE, CHECK on schedule), and a single backup/replication target. The maintenance API turns DBA tasks into n8n-automatable HTTP calls.

## How

### Database Initialization
`mysql/init/01-schemas.sql` creates all 25 databases and their tables in a single idempotent DDL script. Run automatically on first `docker-compose up` via MySQL's `docker-entrypoint-initdb.d` mechanism.

### Medallion Architecture
Every application domain gets three databases:
- **Silver** — Raw/cleaned data from external APIs. Fact + Dimension tables. Source of truth.
- **Internal** — Computed signals, ML outputs, derived metrics. References Silver by ID.
- **Gold** — Aggregated views and tables for dashboards, reports, and APIs.

### Schema Inventory
| Domain | Silver | Internal | Gold |
|--------|--------|----------|------|
| Finance | `coast_finance_silver` | `coast_finance_internal` | `coast_finance_gold` |
| HomeLab | `coast_lab_silver` | `coast_lab_internal` | `coast_lab_gold` |
| Assistant | `coast_assistant_silver` | `coast_assistant_internal` | `coast_assistant_gold` |
| Sports (NFL) | `coast_sports_nfl_silver` | `coast_sports_nfl_internal` | `coast_sports_nfl_gold` |
| Sports (NBA/MLB/NHL) | Placeholders created, tables TBD | | |
| Core | `coastcapital`, `n8n_db`, `maintenance_db` | | |

### Maintenance System
`mysql/init/02-maintenance-procedures.sql` creates 8 stored procedures: `optimize_schema`, `analyze_schema`, `check_schema`, `capture_table_health`, `capture_slow_query_summary`, `generate_settings_recommendations`, `run_full_maintenance`, `flush_status_and_caches`. Scheduled events run nightly health captures and weekly log purges.

### APIs
- **Maintenance API** (`:8080`, FastAPI) — `POST /maintenance/run` triggers stored procedures. `GET /maintenance/status`, `/recommendations`, `/health-snapshot` for monitoring.

### MySQL Tuning (`mysql/config/my.cnf`)
2GB InnoDB buffer pool (4 instances), O_DIRECT flush, ROW binary logging with GTID, slow query log at 1s threshold, 500 max connections, performance_schema enabled.

### Docker Services
- **mysql** — MySQL 8.4, port 3306, custom my.cnf, init scripts on first run
- **maintenance-api** — Python 3.12 FastAPI, port 8080, X-API-Key auth. Source volume mount for dev without rebuilds.

### Testing
Tests require Docker (FastAPI dependency). Run tests inside the container.

> **Note:** n8n has been extracted into its own standalone container at `CoastCapitalN8N/docker-compose.yml`. It connects to the same MySQL instance via the shared Docker network.

### Environment Management
All services use the centralized `.env` file at the project root (`../.env`) via `env_file: - ../.env` in docker-compose.yml. See `/CoastCapital/.env.example` for the full variable template.

---

## Rebuild Prompt

> Create an agent called **DBAgent** that is the lead database architect and administrator for the CoastCapital platform. DBAgent is powered by `claude-sonnet-4-6` and owns the database layer end to end.
>
> Build a Docker Compose stack with MySQL 8.4 and a FastAPI maintenance service that:
>
> 1. Creates databases following a Silver/Internal/Gold medallion architecture across 5 domains: Finance (coast_finance_*), HomeLab (coast_lab_*), Assistant (coast_assistant_*), Sports NFL (coast_sports_nfl_*), plus placeholders for NBA/MLB/NHL, and core databases (coastcapital, n8n_db, maintenance_db).
> 2. Initializes all tables via idempotent DDL in `mysql/init/01-schemas.sql`. Uses dim/fact star schema modeling. All tables have `id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY` and `created_at DATETIME DEFAULT CURRENT_TIMESTAMP`.
> 3. Creates 3 database users: `dbadmin` (full access), `reporting` (SELECT only), `maintenance` (DDL/DML + SUPER).
> 4. Implements 8 maintenance stored procedures (optimize, analyze, check, health capture, slow query summary, settings recommendations, full maintenance, flush) with scheduled events for nightly health and weekly purges.
> 5. Provides a FastAPI maintenance API on port 8080 with X-API-Key auth that exposes stored procedures as HTTP endpoints.
> 6. Tunes MySQL for production: 2GB InnoDB buffer pool, O_DIRECT flush, ROW binary logging with GTID, slow query log, performance_schema enabled.
> 7. Uses centralized `../.env` for all environment variables. Supports dev (MacBook) and prod (Mac Mini) via the same docker-compose.yml with different .env values.
> 8. n8n runs as a separate standalone container (see `CoastCapitalN8N/`), using MySQL backend (n8n_db) on the same shared network.
> 9. N8N workflows post to 4 consolidated Slack channels: `#coast-jobs-fyi`, `#coast-action-needed`, `#coast-recent-summaries`, `#coast-current-status`. Database messages prefixed with `[Database]`.
