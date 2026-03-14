# CoastCapital HomeLab

## What
An infrastructure monitoring and management platform that aggregates real-time metrics from an Ubuntu server, UniFi networking, Plex Media Server, Home Assistant, Ollama LLM, CoreDNS, Portainer Docker manager, and Homepage dashboard. Provides a glassmorphism-styled web dashboard and a Claude-powered agent with 19 tools for natural language infrastructure control.

## Why
Running a homelab means juggling a dozen services across multiple interfaces. This module unifies monitoring into a single pane of glass — detecting outages, tracking resource usage, and enabling conversational infrastructure management. n8n health checks run every 5 minutes, catching problems before they cascade.

## How

### Data Pipelines (7 service integrations)
1. **SystemPipeline** (`app/pipelines/system_pipeline.py`) — SSH into Ubuntu server via paramiko, parses `top` + `nvidia-smi` output for CPU, RAM, disk, GPU metrics.
2. **UniFiPipeline** — UniFi Controller API for network stats, connected clients, device status, alerts, and Protect camera summaries.
3. **PlexPipeline** — Plex XML/JSON API for library stats, active streams, and recently added media.
4. **HomeAssistantPipeline** — HA REST API for entity states, service calls, and automation history.
5. **OllamaPipeline** — Ollama REST API for model inventory, running models, and text generation.
6. **PortainerPipeline** — Portainer API for container status, start/stop/restart actions, and stack management.
7. **HomepagePipeline** — Homepage dashboard health check.

All pipelines write snapshots to MySQL (`system_snapshots`, `unifi_snapshots`, etc.) and a shared `homelab_events` log.

### Database (Silver / Internal / Gold)
- **coast_lab_silver**: `dim_host`, `dim_service`, `dim_docker_container`, `fact_metric`, `fact_docker_event`, `fact_log_entry`
- **coast_lab_internal**: `fact_health_score`, `fact_anomaly_detection`, `fact_alert_trigger`
- **coast_lab_gold**: `fact_sla_summary`, `fact_capacity_trend`, `vw_current_health`

### Web Dashboard
Homepage-inspired glassmorphism design (`app/templates/dashboard.html`) with: ambient animated blobs, 5 service groups (Network, Security, Media/AI, Infrastructure, Automation), status dot indicators, events log, and a HomeLabAgent chat panel with quick-action chips. Auto-refreshes per service (60s for system/UniFi, 5min for Plex/HA).

### Agent
**HomeLabAgent** — Claude-powered agentic loop with 19 tools covering all pipeline services. Supports multi-turn conversation with history. Natural language commands like "restart the Plex container" or "how's the network looking?"

### System Monitoring (Multi-Machine)
`SystemPipeline` supports multiple machine types: local Mac, remote Ubuntu (SSH + GPU), and additional machines via `EXTRA_MACHINES` JSON env var. The dashboard dynamically renders one system card per machine using `buildMachineCard()`, with GPU sections shown conditionally.

### Stack
Flask 3.1 + mysql-connector-python + paramiko (SSH) + requests + Anthropic SDK. Gunicorn with 2 workers, port 5200 (external), connects to shared MySQL via Docker network. Uses centralized `../.env` for all configuration. Source volume mount `./app:/app/app` enables dev iteration without container rebuilds. `logging_config.py` supports `LOG_DIR` env var for local log file output. Includes Prometheus `/metrics` endpoint and MySQL web analytics in `maintenance_db`.

### Testing
51/51 tests passing locally. `conftest.py` stubs paramiko to allow tests to run without SSH dependencies.

---

## Rebuild Prompt

> Create an agent called **HomeLabAgent** (see `../agents/HOMELAB_AGENT.md`) that is the lead developer and infrastructure operations expert for the Coast Capital HomeLab Platform. HomeLabAgent is powered by `claude-opus-4-6` and owns this module end to end.
>
> Build a Docker container with a Flask app and pipelines callable by n8n that:
>
> 1. Connects to the shared MySQL database using three schema layers: `coast_lab_silver` (raw metrics), `coast_lab_internal` (health scores, anomalies), and `coast_lab_gold` (SLA summaries, capacity trends). Uses centralized `../.env` for all environment variables.
> 2. Implements 7 service monitoring pipelines: System (SSH/paramiko for CPU/RAM/disk/GPU with multi-machine support via `EXTRA_MACHINES` JSON env var), UniFi (network stats, clients, devices, alerts, Protect cameras), Plex (libraries, streams, recently added), Home Assistant (entities, service calls, automations), Ollama (model inventory, generation), Portainer (containers, stacks, start/stop/restart), and Homepage (health check).
> 3. Stores pipeline snapshots in MySQL with a shared `homelab_events` log table.
> 4. Exposes a full-status endpoint that polls all services in parallel for n8n health checks (every 5 min) and daily reports.
> 5. Provides a glassmorphism-styled dashboard organized by service groups (Network, Security, Media/AI, Infrastructure, Automation) with ambient blobs, status dots, and per-service auto-refresh. System section dynamically renders one card per machine with conditional GPU display.
> 6. Implements HomeLabAgent as a Claude agentic loop with 19 tools mapping to every pipeline method. Supports multi-turn chat with history.
> 7. Uses X-API-Key authentication on all API endpoints.
> 8. Uses shared brand assets from `CoastCapitalBrand/` (CSS variables, SVG logos, favicon).
> 9. Runs on port 5200 (external), connects to shared MySQL via `coastcapitaldatabase_db-network`.
> 10. Includes Prometheus metrics, MySQL web analytics in `maintenance_db`, and structured JSON logging.
> 11. N8N workflows post to 4 consolidated Slack channels: `#coast-jobs-fyi`, `#coast-action-needed`, `#coast-recent-summaries`, `#coast-current-status`. All messages prefixed with `[HomeLab]`.
