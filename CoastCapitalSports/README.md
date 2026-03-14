# CoastCapital Sports

## What
A multi-sport quantitative prediction platform that ingests game data from ESPN's public API, engineers 137 features, trains PyTorch neural network classifiers, and generates win/cover/total predictions with Kelly criterion bankroll allocation. Currently covers NFL, NCAA Men's Basketball, and MLB, with full March Madness bracket simulation and optimization.

## Why
Sports betting markets are efficient but not perfectly so — edges exist in granular feature engineering, temporal model validation, and disciplined bankroll management. This module aims to be the best sports prediction platform possible by combining deep statistical features (rolling stats, injury impact, BPI rankings, seed history) with rigorous ML governance (train -> cross-validate -> tune -> promote lifecycle). The bracket optimizer adds a unique angle: pool-winning strategy that balances probability with field ownership leverage.

## How

### Data Ingestion
1. **NFL** (`app/ingestion/nfl_ingest.py`) — ESPN scoreboard + box score + standings + injury reports. Context features: indoor/surface, rest days, short week.
2. **NCAA MBB** (`app/ingestion/ncaa_mbb_ingest.py`) — ESPN scoreboard + box scores + standings + BPI rankings + AP/Coaches polls + pre-game predictor.
3. **MLB** (`app/ingestion/mlb_ingest.py`) — ESPN scoreboard + box scores. Game results + market odds.
4. **News** (`app/ingestion/news_ingest.py`) — ESPN news API with optional Claude summarization. Focus teams: Colts, Cubs, Iowa Hawkeyes.
5. **Schema Sync** (`app/ingestion/schema_sync.py`) — dbt-style auto column evolution via `ALTER TABLE`. Dynamic upsert adds missing columns on the fly.

### Feature Engineering (137 columns)
`app/features/feature_engineering.py` computes:
- Team history (rolling scores, margins, rest days)
- Market features (implied probabilities, moneyline delta)
- NCAA tournament features (seed diff, matchup buckets, upset bands, historical seed win rates)
- Postseason features (round tier, playoff experience, championship flag)
- NFL context (indoor, surface, rest advantage, rolling 3-game stats)
- NCAA context (neutral site, conference matchup, BPI features)
- Targets: `home_win`, `cover_home`, `total_over`

Features are materialized as JSON payloads in `modeling_silver.fact_training_features` for versioned, reproducible training.

### ML Model Lifecycle
- **Architecture** (`app/models/pytorch_model.py`) — 3-layer FC network: `input -> hidden -> hidden/2 -> sigmoid`, with ReLU + Dropout.
- **Training** — Full dataset training, saves as `{sport}_{target}_candidate.pt`.
- **Cross-Validation** — Sequential (temporal) K-fold CV with per-fold loss/accuracy/AUC.
- **Tuning** — Grid search over learning_rate, batch_size, hidden_dim, dropout, epochs.
- **Promotion** — CV-validated candidates logged to `fact_model_registry` as production; old versions retired.
- **Scoring** — Production model scores most-recent N games, returns predicted probabilities.
- **Portfolio** — Kelly criterion fractional allocation across all active signals.

### Bracket Simulation
`app/bracket/` implements full March Madness bracket optimization:
- Fetch 68-team tournament field from ESPN
- Build team statistical profiles from `ncaa_mbb_silver`
- Monte Carlo simulation (symmetric neutral-site matchup predictions)
- Pool-winning optimizer: blends probability with field ownership leverage
- HTML bracket visualization with pick correctness overlay

### Database Schemas
Sport-specific silver schemas (`nfl_silver`, `ncaa_mbb_silver`, `mlb_silver`) plus shared:
- **modeling_silver**: `fact_training_features` (stable columns + `feature_payload JSON`)
- **modeling_internal**: `fact_model_registry`, `fact_model_predictions`, `fact_trading_signals`, `fact_portfolio_simulations`, bracket tables, `fact_sports_news`

Centralized schemas in `CoastCapitalDatabase/mysql/init/01-schemas.sql`:
- **coast_sports_nfl_silver/internal/gold** (with placeholder NBA/MLB/NHL)

### Web Dashboard
Bootstrap 5 dark theme with 3 pages:
- **Sports Summary** — Quick stats cards, focus team scores with W/L badges, news feed with LLM summaries.
- **Model Performance** — CV accuracy/AUC bar charts, production models table, sport filter.
- **Model Diagnostics** — Model registry with promote button, ROC curve, confusion matrix, year-by-year breakdown, promote/keep recommendation banner.

### N8N Automation (8 workflows in `CoastCapitalN8N/sports/`)
| Workflow | Schedule | What It Does |
|----------|----------|-------------|
| `sports_daily_pipeline` | Daily 6:00 AM ET | Ingest all sports + score models + betting recs |
| `sports_weekly_optimization` | Tuesday 3:00 AM ET | Force-refit models + generate weekly betting plan |
| `sports_ncaa_bracket` | Daily 5:00 AM (Mar-Apr) | 10k Monte Carlo bracket simulations |
| `sports_ncaa_tournament_prep` | Manual trigger | Full tournament prep pipeline (field fetch, profiles, simulation, optimization) |
| `sports_news_ingest` | Every 6 hours | Parallel ESPN news for NFL/NCAA/MLB + LLM summaries |
| `sports_backfill` | Manual trigger | Historical data backfill + feature materialization |
| `sports_nfl_weekly_picks` | Monday 6:00 AM ET | In-season NFL weekly picks generation |
| `sports_nfl_game_ingest` | Sun/Thu/Mon 11:30 PM | Game result ingestion + rating updates |

### Stack
Flask + PyTorch + scikit-learn + pandas + numpy + mysql-connector-python + nltk. Port 5000 internal. Uses centralized `../.env` for all configuration. Database connections use `MYSQL_USER`/`MYSQL_PASSWORD` (not root) with `MySQLConnectionPool` for connection pooling. `logging_config.py` supports `LOG_DIR` env var for local log file output. Includes Prometheus `/metrics` endpoint and MySQL web analytics in `maintenance_db`.

### Testing
17/17 tests passing locally. `conftest.py` stubs numpy, pandas, and torch to allow tests to run without heavy dependencies.

---

## Rebuild Prompt

> Create an agent called **SportsAgent** (see `../agents/SPORTS_AGENT.md`) that is the lead developer and quantitative sports analyst for the Coast Capital Sports Prediction Platform. SportsAgent is powered by `claude-sonnet-4-6` and owns this module end to end.
>
> Build a Docker container with a Flask app and pipelines callable by n8n that:
>
> 1. Connects to MySQL with sport-specific schemas (`nfl_silver`, `ncaa_mbb_silver`, `mlb_silver`) and shared schemas (`modeling_silver`, `modeling_internal`). Uses `MYSQL_USER`/`MYSQL_PASSWORD` (not root) with `MySQLConnectionPool` for connection pooling. Also uses centralized schemas `coast_sports_nfl_silver/internal/gold` in the shared database.
> 2. Ingests game data from ESPN public API (scoreboard, box scores, standings, injuries, BPI, polls) for NFL, NCAA MBB, and MLB. Includes a dbt-style dynamic schema sync that auto-adds columns via ALTER TABLE.
> 3. Engineers 137 features across categories: team history (rolling stats), market (implied probs), NCAA tournament (seeds, upset bands), postseason (round tiers, experience), NFL context (indoor, surface, rest), NCAA context (neutral site, BPI). Materializes to `modeling_silver.fact_training_features` as JSON payloads for versioned reproducibility.
> 4. Trains PyTorch 3-layer FC classifiers (input -> hidden -> hidden/2 -> sigmoid) with a full lifecycle: train candidate -> temporal K-fold CV -> grid search tuning -> promote to production -> refit on cron. All versions logged to `fact_model_registry`.
> 5. Scores production models and allocates bankroll using fractional Kelly criterion via `app/portfolio/portfolio_optimizer.py`.
> 6. Implements full March Madness bracket simulation: 68-team field fetch from ESPN, team profile building, Monte Carlo neutral-site simulations, pool-winning optimizer (probability x leverage vs field ownership), HTML bracket visualization.
> 7. Provides a Bootstrap 5 dark-theme dashboard with: Sports Summary (quick stats, focus teams, news), Model Performance (accuracy/AUC charts, production table), Model Diagnostics (registry, ROC, confusion matrix, promote workflow).
> 8. SportsAgent's mission: "Create enterprise value by being the best sports prediction company in the world." Decision framework: accuracy first, sport-agnostic abstractions, centralized Kelly optimization, strict model governance.
> 9. Uses shared brand assets from `CoastCapitalBrand/` (CSS variables, SVG logos, favicon).
> 10. Exposes n8n-ready endpoints: `/daily-pipeline`, `/weekly-optimization`, `/backfill`, `/materialize-features`, `/train-model`, `/score-model`, `/cross-validate-model`, `/tune-model`, `/promote-model`, `/refit-model`, `/simulate-bracket`, `/ingest-news`.
> 11. Eight n8n workflows in `CoastCapitalN8N/sports/` automate Sports operations: `sports_daily_pipeline` (daily 6 AM), `sports_weekly_optimization` (Tue 3 AM), `sports_ncaa_bracket` (daily 5 AM Mar-Apr), `sports_ncaa_tournament_prep` (manual, full tournament prep pipeline), `sports_news_ingest` (every 6h), `sports_backfill` (manual), `sports_nfl_weekly_picks` (Mon 6 AM), `sports_nfl_game_ingest` (Sun/Thu/Mon 11:30 PM). All workflows have dual triggers (cron + webhook) and use centralized `../.env`.
> 12. N8N workflows post to 4 consolidated Slack channels: `#coast-jobs-fyi`, `#coast-action-needed`, `#coast-recent-summaries`, `#coast-current-status`. All messages prefixed with `[Sports]`.
> 13. Includes Prometheus metrics and structured JSON logging.
