# CoastCapital Platform

## What
A FastAPI service that provides Ollama-powered intent classification for Slack command dispatch, an architecture audit agent, a prediction feedback dashboard for ground truth collection, and an MCP server for Claude Code integration. Acts as the central dispatcher layer that routes natural language Slack messages to the correct n8n workflow.

## Why
With 23 n8n workflows across 6 domains, users need a single conversational interface to trigger any workflow on demand. Rather than memorizing webhook URLs or Slack slash commands, users post plain English in `#coast-action-needed` and the Platform dispatcher classifies intent, extracts parameters, and routes to the correct workflow. The feedback dashboard closes the loop by letting users upvote or downvote classifications, which are injected as few-shot examples to continuously improve accuracy.

## How

### Intent Dispatcher
`app/dispatcher.py` uses a local Ollama instance for intent classification. The pipeline:
1. Receives user text from the n8n Slack Dispatcher workflow
2. Ollama LLM classifies intent with parameter extraction + confidence scoring
3. If confidence >= 0.6, returns the intent and webhook path for dispatch
4. If confidence < 0.6, returns a clarification request

Supported intents cover all platform domains: finance (forecast, retrain, watchlist), homelab (health, report, full status), assistant (brief, tasks, followup), sports (daily, NFL picks/ingest, NCAA bracket/prep, backfill, news, optimization), database (maintenance), platform (docker rebuild, architecture audit, system status).

### Architecture Audit Agent
`app/agents/architecture_agent.py` provides a Claude-powered agent that audits the CoastCapital codebase for consistency issues, triggered via the `platform_architecture_audit` n8n workflow.

### Prediction Logging
Every intent classification is logged to `maintenance_db.dispatch_predictions` with source, user text, predicted intent, parameters (JSON), confidence, Ollama model, response time, and webhook path.

### Feedback Dashboard
A Bootstrap 5 dark-themed UI at `/dashboard` (`app/templates/feedback.html`) allows reviewing predictions, upvoting correct ones, and downvoting incorrect ones (with the ability to specify the correct intent and add notes).

### Ground Truth Loop
Upvoted and downvoted predictions are injected as few-shot examples into the Ollama system prompt (max 100 good + 100 bad). Correct examples are formatted as input/output pairs; incorrect examples include the predicted vs. correct intent with user notes.

### MCP Server
`mcp_server.py` exposes intent classification as an MCP tool for Claude Code integration, registered in `.mcp.json` at the project root.

### Database
- **`maintenance_db`**: `dispatch_predictions` table (prediction logging and feedback)

### Stack
FastAPI + Jinja2 + mysql-connector-python + httpx (Ollama) + Anthropic SDK. Gunicorn with uvicorn workers, port 5400. Connects to shared MySQL via Docker network. Uses centralized `../.env` for all configuration. Source volume mount `./app:/app/app` enables dev iteration without container rebuilds.

### N8N Automation (5 workflows in `CoastCapitalN8N/platform/`)
| Workflow | Trigger | What It Does |
|----------|---------|-------------|
| `platform_slack_dispatcher` | Slack trigger | Ollama LLM intent classification and workflow dispatch |
| `platform_error_handler` | Webhook | Anthropic API error analysis, Git branch + PR, Slack notification |
| `platform_system_status` | Webhook | Multi-service health report to `#coast-current-status` |
| `platform_docker_rebuild` | Manual | Rebuild all containers (except MySQL/N8N), health check, Slack report |
| `platform_architecture_audit` | Manual | Architecture audit via Anthropic API |

---

## Rebuild Prompt

> Build a Docker container with a FastAPI app that:
>
> 1. Connects to the shared MySQL database (`maintenance_db`) for prediction logging and feedback storage. Uses centralized `../.env` for all environment variables.
> 2. Implements an Ollama-powered intent classifier (`app/dispatcher.py`) that receives user text, classifies intent with parameter extraction and confidence scoring, and returns the matching webhook path for n8n dispatch.
> 3. Logs every classification to `maintenance_db.dispatch_predictions` with source, user text, predicted intent, parameters (JSON), confidence, Ollama model, response time, and webhook path.
> 4. Provides a Bootstrap 5 dark-themed feedback dashboard at `/dashboard` for reviewing predictions, upvoting correct ones, and downvoting incorrect ones with notes.
> 5. Implements a ground truth loop: upvoted/downvoted predictions are injected as few-shot examples into the Ollama system prompt (max 100 good + 100 bad) to continuously improve classification accuracy.
> 6. Includes an architecture audit agent (`app/agents/architecture_agent.py`) powered by Claude for codebase consistency audits.
> 7. Exposes intent classification as an MCP tool via `mcp_server.py`, registered in `.mcp.json` at the project root.
> 8. Uses shared brand assets from `CoastCapitalBrand/` (CSS variables, SVG logos, favicon).
> 9. Runs on port 5400, connects to shared MySQL via `coastcapitaldatabase_db-network`.
> 10. Five n8n workflows in `CoastCapitalN8N/platform/` handle Slack dispatch, error handling (Anthropic API analysis + Git PR), system status, Docker rebuilds, and architecture audits.
> 11. N8N workflows post to 4 consolidated Slack channels: `#coast-jobs-fyi`, `#coast-action-needed`, `#coast-recent-summaries`, `#coast-current-status`. All messages prefixed with `[Platform]`.
