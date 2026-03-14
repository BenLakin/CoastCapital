# CoastCapital N8N Workflows

## What
A standalone n8n Docker container with 22 workflow JSON files organized into subdirectories (`finance/`, `homelab/`, `assistant/`, `sports/`, `database/`, `platform/`) that automate scheduled tasks across all CoastCapital modules. Includes domain workflows (Finance, HomeLab, Assistant, Sports, Database) plus four platform workflows: an Ollama LLM-powered Slack dispatcher with parameter extraction and confidence scoring, an Anthropic API-powered error handler that auto-creates Git MRs for fixes, a multi-service system status reporter, and a Docker rebuild workflow for rebuilding all containers except MySQL and N8N.

## Why
Each CoastCapital module exposes Flask API endpoints designed to be called on schedule. n8n provides the cron orchestration, conditional branching (success/failure), parallel execution, webhook-based on-demand triggering, and Slack notification delivery without embedding scheduling logic in the application code. This separation means pipeline logic stays in Python while scheduling, retry, alerting, and error recovery stay in n8n.

## How

### Docker Setup

N8N runs as a standalone container with its own `docker-compose.yml`:

```bash
cd CoastCapitalN8N
docker compose up -d
```

- **Container**: `coastcapital-n8n`
- **Port**: 5678
- **MySQL backend**: Stores metadata in `n8n_db` on the shared `coastcapital-mysql` instance
- **Network**: Connects to `coastcapitaldatabase_db-network` (external)
- **Git repo mount**: `../:/workspace:rw` for auto-MR error handler workflow
- **Docker socket**: `/var/run/docker.sock` mounted for the Docker rebuild workflow (requires `DOCKER_GID` env var for socket access)
- **Environment**: All vars from centralized `../.env` (N8N_USER, N8N_PASSWORD, SLACK_BOT_TOKEN, OLLAMA_BASE_URL, OLLAMA_MODEL, ANTHROPIC_API_KEY, DOCKER_GID, Git credentials)

### Workflow Architecture

Every workflow follows these patterns:
- **Dual triggers**: Cron schedule + webhook endpoint for on-demand execution
- **Job Started notification**: Posts to `#coast-jobs-fyi` at workflow start
- **Module tag prefixes**: All Slack messages tagged with `[Finance]`, `[HomeLab]`, `[Sports]`, `[Assistant]`, `[Database]`, or `[Platform]`
- **Error handler integration**: Failure branches POST to `/webhook/platform-error-handler`
- **4 Slack channels**: `#coast-jobs-fyi`, `#coast-action-needed`, `#coast-recent-summaries`, `#coast-current-status`

### Workflow Inventory

| # | File | Schedule | Webhook Path | Domain | Description |
|---|------|----------|-------------|--------|-------------|
| 1 | `finance/finance_daily_forecast.json` | Weekdays 6:30 AM ET | `/webhook/finance-forecast` | Finance | ML forecast pipeline, Slack brief |
| 2 | `finance/finance_weekly_retrain.json` | Sunday 2:00 AM ET | `/webhook/finance-retrain` | Finance | Retrain all ML models |
| 3 | `finance/finance_watchlist_sync.json` | Daily 5:00 AM ET | `/webhook/finance-watchlist` | Finance | Sync watchlist, backfill new tickers |
| 4 | `homelab/homelab_health_check.json` | Every 5 minutes | `/webhook/homelab-health` | HomeLab | Poll service health, alert on failure |
| 5 | `homelab/homelab_daily_report.json` | Daily 8:00 AM ET | `/webhook/homelab-report` | HomeLab | Aggregate metrics, infrastructure digest |
| 6 | `homelab/homelab_full_status.json` | Daily 7:30 AM ET | `/webhook/homelab-full-status` | HomeLab | Full 8-service sweep, summary report |
| 7 | `assistant/assistant_daily_brief.json` | Daily 7:00 AM ET | `/webhook/assistant-brief` | Assistant | Calendar + tasks + news morning brief |
| 8 | `assistant/assistant_task_sync.json` | Every 30 minutes | `/webhook/assistant-tasks` | Assistant | Sync tasks to database |
| 9 | `assistant/assistant_followup_check.json` | Daily 9:00 AM ET | `/webhook/assistant-followup` | Assistant | Check unanswered emails > 3 days |
|10 | `sports/sports_daily_pipeline.json` | Daily 6:00 AM ET | `/webhook/sports-daily` | Sports | Full daily: ingest + score + bets |
|11 | `sports/sports_weekly_optimization.json` | Tuesday 3:00 AM ET | `/webhook/sports-optimization` | Sports | Refit models, weekly betting plan |
|12 | `sports/sports_ncaa_bracket.json` | Daily 5:00 AM (Mar-Apr) | `/webhook/sports-ncaa-bracket` | Sports | 10k Monte Carlo bracket simulation |
|13 | `sports/sports_ncaa_tournament_prep.json` | Manual trigger | `/webhook/sports-ncaa-tournament-prep` | Sports | Full tournament prep pipeline |
|14 | `sports/sports_news_ingest.json` | Every 6 hours | `/webhook/sports-news` | Sports | ESPN news ingest + LLM summaries |
|15 | `sports/sports_backfill.json` | Manual trigger | `/webhook/sports-backfill` | Sports | Historical backfill + features |
|16 | `sports/sports_nfl_weekly_picks.json` | Monday 6:00 AM ET | `/webhook/sports-nfl-picks` | Sports | Weekly NFL picks (in-season) |
|17 | `sports/sports_nfl_game_ingest.json` | Sun/Thu/Mon 11:30 PM | `/webhook/sports-nfl-ingest` | Sports | Game results + rating updates |
|18 | `database/mysql_maintenance.json` | Nightly 2 AM + 6h health | `/webhook/db-maintenance` | Database | Analyze, optimize, health snapshots |
|19 | `platform/platform_slack_dispatcher.json` | Slack trigger | — | Platform | Ollama LLM intent → workflow dispatch |
|20 | `platform/platform_error_handler.json` | Webhook trigger | `/webhook/platform-error-handler` | Platform | Anthropic API → Git MR → Slack |
|21 | `platform/platform_system_status.json` | Webhook trigger | `/webhook/platform-system-status` | Platform | Multi-service health report |
|22 | `platform/platform_docker_rebuild.json` | Manual trigger | `/webhook/platform-docker-rebuild` | Platform | Rebuild all containers (except MySQL/N8N) |

### Platform Workflows

#### Slack Dispatcher (`platform/platform_slack_dispatcher.json`)
Listens in `#coast-action-needed` for user messages. Uses local Ollama LLM (`OLLAMA_BASE_URL`/`OLLAMA_MODEL`) to classify intent with parameter extraction and confidence scoring. Dispatches to the appropriate workflow via its webhook trigger. Responds with confirmation or help text for unknown intents.

Supported intents: `finance_forecast`, `finance_retrain`, `finance_watchlist`, `homelab_health`, `homelab_report`, `assistant_brief`, `assistant_tasks`, `sports_daily`, `sports_nfl_picks`, `sports_ncaa_bracket`, `sports_ncaa_tournament_prep`, `sports_backfill`, `sports_news`, `sports_optimization`, `db_maintenance`, `system_status`, `docker_rebuild`.

#### Error Handler (`platform/platform_error_handler.json`)
Receives error payloads from all other workflows via webhook. Flow:
1. Captures error context (workflow_name, error_message, error_type, stack_trace, module)
2. Calls Anthropic API (Claude) to analyze the error and suggest a code fix
3. Creates a Git branch (`fix/{workflow}-{timestamp}`), commits the suggested fix
4. Opens a GitHub Pull Request via GitHub API
5. Notifies `#coast-action-needed` with the MR link for human review

#### System Status (`platform/platform_system_status.json`)
Triggered by webhook or Slack message in `#coast-current-status`. Polls all service health endpoints in parallel (Finance, HomeLab, Assistant, Sports, Maintenance API, Platform), builds a formatted status report, and replies to the requesting channel.

#### Docker Rebuild (`platform/platform_docker_rebuild.json`)
Manually triggered workflow that rebuilds all Docker containers except MySQL and N8N. Uses the mounted Docker socket (`/var/run/docker.sock`) to issue rebuild commands. Requires `DOCKER_GID` env var for socket access permissions.

### Credential Names (configured in n8n UI)

| Credential | Type | Used By |
|------------|------|---------|
| `Finance Webhook Auth` | HTTP Header | finance_* workflows |
| `HomeLab Webhook Auth` | HTTP Header | homelab_* workflows |
| `Assistant Webhook Auth` | HTTP Header | assistant_* workflows |
| `Sports Webhook Auth` | HTTP Header | sports_* workflows |
| `CoastCapital Slack` | Slack API | All workflows |
| `CoastCapital SMTP` | SMTP | Workflows with email delivery |

### Import

Import workflows into n8n via: Settings -> Import from File.
Workflow files are organized in subdirectories: `finance/`, `homelab/`, `assistant/`, `sports/`, `database/`, `platform/`.

---

## Rebuild Prompt

> Create 22 n8n workflow JSON files organized into subdirectories (`finance/`, `homelab/`, `assistant/`, `sports/`, `database/`, `platform/`) and a standalone Docker container for the CoastCapital platform automation layer. Each workflow must be valid n8n v1 export format with proper node types (`n8n-nodes-base.scheduleTrigger`, `n8n-nodes-base.webhook`, `httpRequest`, `if`, `set`, `code`, `slack`, `executeCommand`), UUIDs, and connection mappings.
>
> The n8n container runs standalone via `CoastCapitalN8N/docker-compose.yml`, using the centralized `../.env` for all credentials. It stores metadata in `n8n_db` on the shared MySQL instance and connects via `coastcapitaldatabase_db-network`. The git repo is mounted at `/workspace` for the error handler workflow. The Docker socket is mounted at `/var/run/docker.sock` for the rebuild workflow (requires `DOCKER_GID` env var).
>
> Every workflow must have: (1) dual triggers (cron + webhook), (2) a "Job Started" Slack notification to `#coast-jobs-fyi`, (3) module tag prefixes on all messages, (4) error handler call on failure branches POSTing to `/webhook/platform-error-handler`.
>
> Domain workflows (18):
> 1. **finance_daily_forecast** — Weekday 6:30 AM ET, POST to Finance Flask `/n8n/daily-forecast`, result to `#coast-recent-summaries`.
> 2. **finance_weekly_retrain** — Sunday 2 AM ET, POST `/n8n/retrain-all` with 600s timeout.
> 3. **finance_watchlist_sync** — Daily 5 AM ET, GET watchlist, conditional backfill for new tickers.
> 4. **homelab_health_check** — Every 5 min, parallel health checks, alert `#coast-action-needed` on failure.
> 5. **homelab_daily_report** — Daily 8 AM ET, parallel GET health-summary + docker-status, Slack + email.
> 6. **homelab_full_status** — Daily 7:30 AM, POST `/api/pipeline/full-status`, 8-service sweep to `#coast-recent-summaries`.
> 7. **assistant_daily_brief** — Daily 7 AM ET, parallel calendar + tasks + news, POST morning-brief, Slack + email.
> 8. **assistant_task_sync** — Every 30 min, parallel sync, alert on error.
> 9. **assistant_followup_check** — Daily 9 AM, POST `/api/pipeline/followup`, stale emails to `#coast-action-needed`.
> 10-16. **sports_*** — 7 sports workflows (daily pipeline, weekly optimization, NCAA bracket, news, backfill, NFL picks, NFL game ingest).
> 17. **sports_ncaa_tournament_prep** — Manual trigger, full tournament prep pipeline (field fetch, profiles, simulation, optimization).
> 18. **mysql_maintenance** — Nightly 2 AM + 6h health captures.
>
> Platform workflows (4):
> 19. **platform_slack_dispatcher** — Slack trigger in `#coast-action-needed`, local Ollama LLM intent classification with parameter extraction and confidence scoring, switch-based dispatch to workflow webhooks.
> 20. **platform_error_handler** — Webhook receives error payload, Anthropic API analysis, Git branch + commit + PR, Slack notification.
> 21. **platform_system_status** — Webhook + Slack trigger, parallel health checks on all services, formatted report to `#coast-current-status`.
> 22. **platform_docker_rebuild** — Manual trigger, rebuilds all Docker containers except MySQL and N8N via mounted Docker socket.
>
> Use 4 Slack channels: `#coast-jobs-fyi` (lifecycle), `#coast-action-needed` (errors + commands), `#coast-recent-summaries` (reports), `#coast-current-status` (status queries). Use consistent credential naming: `{Domain} Webhook Auth` for HTTP auth, `CoastCapital Slack` for Slack. Agent definition: `../agents/` directory at project root.
