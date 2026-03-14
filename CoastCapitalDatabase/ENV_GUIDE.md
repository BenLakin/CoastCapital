# CoastCapital Database -- Environment Configuration Guide

## Overview

CoastCapital runs on two environments with identical Docker Compose stacks. The
only differences are the host addresses, passwords, and (optionally) resource
limits. Environment-specific values live in `.env` files that Docker Compose
reads at start-up.

---

## Environments

### Dev -- Local MacBook

| Property           | Value                                     |
|--------------------|-------------------------------------------|
| Host               | `localhost` / `127.0.0.1`                 |
| MySQL port         | `3306`                                    |
| n8n port           | `5678`                                    |
| Maintenance API    | `8080`                                    |
| Config file        | `.env.dev`                                |
| Purpose            | Local development, testing, prototyping   |

Start the dev stack:

```bash
# Copy the example and fill in real values
cp .env.dev.example .env.dev

# Launch (reads .env.dev automatically)
docker compose --env-file .env.dev up -d
```

### Prod -- Mac Mini

| Property           | Value                                     |
|--------------------|-------------------------------------------|
| Host               | Mac Mini IP or hostname (e.g. `macmini.local`) |
| MySQL port         | `3306`                                    |
| n8n port           | `5678`                                    |
| Maintenance API    | `8080`                                    |
| Config file        | `.env.prod`                               |
| Purpose            | Always-on services, cron jobs, dashboards |

Start the prod stack:

```bash
cp .env.prod.example .env.prod
# Edit .env.prod with production credentials

docker compose --env-file .env.prod up -d
```

---

## Key Environment Variables

| Variable                       | Description                                   | Example (dev)              |
|--------------------------------|-----------------------------------------------|----------------------------|
| `MYSQL_ROOT_PASSWORD`          | MySQL root password                           | `dev_root_pass`            |
| `MYSQL_USER`                   | Application database user                     | `dbadmin`                  |
| `MYSQL_PASSWORD`               | Application user password                     | `dev_db_pass`              |
| `MYSQL_DATABASE`               | Default database for the MySQL container      | `coastcapital`             |
| `MYSQL_HOST`                   | Hostname for app connections to MySQL         | `localhost`                |
| `MYSQL_PORT`                   | MySQL port                                    | `3306`                     |
| `MYSQL_REPORTING_PASSWORD`     | Password for the `reporting` read-only user   | `dev_reporting_pass`       |
| `MYSQL_MAINTENANCE_PASSWORD`   | Password for the `maintenance` user           | `dev_maintenance_pass`     |
| `N8N_HOST`                     | Public hostname for n8n webhooks              | `localhost`                |
| `N8N_USER`                     | n8n basic-auth username                       | `admin`                    |
| `N8N_PASSWORD`                 | n8n basic-auth password                       | `dev_n8n_pass`             |
| `MAINTENANCE_API_KEY`          | API key for maintenance REST endpoints        | `dev_maint_key`            |
| `TIMEZONE`                     | Default timezone for n8n and cron schedules   | `America/New_York`         |

---

## How `.env` Files Work with Docker Compose

Docker Compose substitutes `${VAR}` placeholders in `docker-compose.yml` with
values from the `.env` file. The `--env-file` flag tells Compose which file to
use:

```bash
# Dev
docker compose --env-file .env.dev up -d

# Prod
docker compose --env-file .env.prod up -d
```

If you use the default `.env` filename in the same directory as
`docker-compose.yml`, you do not need `--env-file` -- Compose picks it up
automatically. However, using separate named files makes it explicit which
environment is running.

---

## Connecting Applications to the Database

Each Flask application reads its own `.env` (or environment variables) to locate
the database. The connection string pattern is:

```
mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{DATABASE_NAME}
```

**Dev example (CoastFinance):**

```
mysql+pymysql://dbadmin:dev_db_pass@localhost:3306/coast_finance_silver
```

**Prod example (CoastFinance):**

```
mysql+pymysql://dbadmin:prod_db_pass@macmini.local:3306/coast_finance_silver
```

Applications can connect to multiple databases on the same MySQL instance by
switching the database name in their connection strings (e.g.
`coast_finance_internal`, `coast_lab_silver`, etc.).

---

## Security Notes

- Never commit `.env.dev` or `.env.prod` to version control.
- Only the `.env.*.example` templates should be tracked in git.
- Use strong, unique passwords in production.
- The `reporting` user has SELECT-only access -- use it for dashboards and BI
  tools.
- The `maintenance` user has operational DDL/DML access but not SUPER on
  individual schemas.

---

## Port Assignments

| Service            | Port  | Protocol |
|--------------------|-------|----------|
| MySQL              | 3306  | TCP      |
| n8n                | 5678  | HTTP     |
| Maintenance API    | 8080  | HTTP     |
| CoastFinance Flask | 5000  | HTTP     |
| CoastHomelab Flask | 5001  | HTTP     |
| CoastAssistant Flask | 5002 | HTTP    |
| CoastSports Flask  | 5003  | HTTP     |
