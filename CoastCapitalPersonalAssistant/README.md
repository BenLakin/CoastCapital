# CoastCapital Personal Assistant

## What
An AI-powered personal assistant that integrates with iCloud (email, calendar, reminders), tracks relationships and gift preferences, builds daily communications plans, detects travel itineraries and package deliveries from email, monitors follow-up threads, and generates morning briefings. Provides a Tailwind-styled web UI for action items, relationship CRM, and a Claude-powered chat agent.

## Why
Important personal communications, upcoming events, and administrative tasks are scattered across email, calendars, and various apps. This module aggregates them into a single intelligent layer that surfaces what matters most — prioritizing family (especially Kim), flagging unanswered emails, recommending birthday gifts, and drafting ready-to-send communications. The morning briefing ensures nothing falls through the cracks.

## How

### Data Pipelines (11 integrations)
1. **EmailPipeline** — iCloud IMAP fetch + Claude summarization + family email filtering. Sends via SMTP with STARTTLS.
2. **NewsPipeline** — NewsAPI + RSS fallback (BBC, NYT, TechCrunch, Wired, VentureBeat) across 4 categories (world, tech, AI, B2B). Claude summarizes each category.
3. **CalendarPipeline** — CalDAV sync with iCloud, auto-detects birthdays and holidays.
4. **RemindersPipeline** — CalDAV VTODO fetch/create/complete against iCloud Reminders.
5. **CommunicationsPipeline** — Aggregates email + calendar + news, Claude generates prioritized comms plan with structured action items (who, what, draft email body).
6. **DeliveriesPipeline** — Scans email for shipping keywords, extracts carrier and tracking numbers via regex (UPS, FedEx, USPS, Amazon, DHL).
7. **ArchivePipeline** — Rule-based email archiving (no-reply, newsletters, receipts). Claude learns new rules from unmatched emails.
8. **MorningBriefingPipeline** — Aggregates calendar, reminders, emails, action items, deliveries, travel, birthdays, weather (wttr.in) into a formatted briefing. Optionally emails to self.
9. **FollowupPipeline** — Scans iCloud Sent folder, cross-references INBOX In-Reply-To headers, surfaces emails waiting 3+ days for reply.
10. **TravelPipeline** — Detects travel confirmations from airlines/hotels in email, Claude extracts structured itineraries.
11. **BirthdayPipeline** — Birthday tracking with preference categories (12 types), Claude-powered gift suggestions, interaction logging.

### Database (Silver / Internal / Gold)
- **coast_assistant_silver**: `dim_person`, `dim_topic`, `fact_conversation`, `fact_calendar_event`, `fact_task`, `fact_document`
- **coast_assistant_internal**: `fact_entity`, `fact_memory_chunk`, `fact_embedding_ref`, `fact_action_log`
- **coast_assistant_gold**: `fact_daily_summary`, `fact_reminder`, `fact_relationship_edge`

Currently uses a local DB schema (`assistant_db`) with tables: `email_cache`, `news_cache`, `action_items`, `archive_rules`, `deliveries`, `relationships`, `relationship_preferences`, `relationship_interactions`, `gifts`, `followup_tracker`, `travel_itineraries`, `morning_briefings`.

### Web Dashboard
Tailwind CSS dark theme with sidebar navigation:
- **Dashboard** — Recent emails (family highlighted), action items (priority-colored), news by category, deliveries, pipeline trigger buttons, and AssistantAgent chat widget.
- **Communications** — Full action item list with inline email drafts, dismiss/send controls, rebuild plan button.
- **Relationships** — Contact grid with birthday badges, add person modal. Individual profile pages with preference tags (12 categories), AI gift suggestions, gift history, and interaction log.

### Agent
**AssistantAgent** — Claude-powered agentic loop with 10 tools (email, calendar, reminders, news, deliveries, comms plan, family contacts, send email). Owner-personalized system prompt with today's date injected.

### Stack
Flask 3.0 + mysql-connector-python + anthropic + caldav + icalendar + feedparser + beautifulsoup4. Gunicorn with 2 workers, port 5100 (external). Uses centralized `../.env` for all configuration. Source volume mount `./app:/app/app` enables dev iteration without container rebuilds. Redundant HEALTHCHECK removed from Dockerfile (docker-compose handles health checks). Includes Prometheus `/metrics` endpoint and MySQL web analytics in `maintenance_db`.

### Testing
156/156 tests passing locally.

---

## Rebuild Prompt

> Create an agent called **AssistantAgent** (see `../agents/ASSISTANT_AGENT.md`) that is the lead developer and personal operations manager for the Coast Capital Personal Assistant. AssistantAgent is powered by `claude-opus-4-6` and owns this module end to end.
>
> Build a Docker container with a Flask app and pipelines callable by n8n that:
>
> 1. Connects to the shared MySQL database using three schema layers: `coast_assistant_silver` (raw conversations, events, tasks), `coast_assistant_internal` (entities, memory, embeddings), and `coast_assistant_gold` (summaries, reminders, knowledge graph). Uses centralized `../.env` for all environment variables.
> 2. Integrates with iCloud via IMAP/SMTP (email), CalDAV (calendar + reminders), fetching and summarizing emails with Claude.
> 3. Implements 11 pipelines: Email (fetch/summarize/send/family filter), News (NewsAPI + RSS across world/tech/AI/B2B), Calendar (CalDAV with birthday/holiday detection), Reminders (VTODO create/complete), Communications (Claude-generated prioritized comms plan with draft emails), Deliveries (email scan with carrier regex extraction), Archive (rule-based + Claude-learned email archiving), Morning Briefing (aggregated daily digest with weather), Followup (detect unanswered sent emails 3+ days), Travel (Claude-extracted itineraries from airline/hotel emails), Birthday (preference tracking + Claude gift suggestions).
> 4. Implements a relationship CRM with: 12 preference categories, gift tracking with suggestions, interaction logging, birthday countdown alerts (21-day window).
> 5. Provides a Tailwind-styled dashboard with sidebar navigation, action item management, and inline email drafting/sending.
> 6. Implements AssistantAgent as a Claude agentic loop with 10 tools. System prompt is personalized with owner name and current date.
> 7. Family contacts (especially Kim Lakin) are always prioritized in email filtering, comms plans, and agent responses.
> 8. Uses X-API-Key authentication on all API endpoints.
> 9. Uses shared brand assets from `CoastCapitalBrand/` (CSS variables, SVG logos, favicon).
> 10. Runs on port 5100 (external), connects to shared MySQL via `coastcapitaldatabase_db-network`.
> 11. Includes Prometheus metrics, MySQL web analytics in `maintenance_db`, and structured JSON logging.
> 12. N8N workflows post to 4 consolidated Slack channels: `#coast-jobs-fyi`, `#coast-action-needed`, `#coast-recent-summaries`, `#coast-current-status`. All messages prefixed with `[Assistant]`.
