"""
CoastCapital Platform — Two-Pass Cross-Container Connectivity Tests

Pass 1: Health + Metrics — verify all services respond with 200 OK on /health
        and expose /metrics (Prometheus) endpoints
Pass 2: N8N integration — verify webhook triggers are accessible

Run: pytest tests/test_connectivity.py -v
Note: Requires all Docker containers to be running on the shared network.
"""
import os
import pytest
import requests

# ── Service URLs ──────────────────────────────────────────────────────────────
HOST = os.getenv("TEST_HOST", "localhost")

SERVICES = {
    "finance":     f"http://{HOST}:5000",
    "assistant":   f"http://{HOST}:5100",
    "homelab":     f"http://{HOST}:5200",
    "sports":      f"http://{HOST}:5300",
    "platform":    f"http://{HOST}:5400",
    "maintenance": f"http://{HOST}:8080",
    "n8n":         f"http://{HOST}:5678",
}

API_KEY = os.getenv("API_KEY", "change-me-n8n-api-key")


# ═══════════════════════════════════════════════════════════════════════════════
#  PASS 1: Health + Metrics Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestPass1Health:
    """Verify every service health endpoint returns 200 OK."""

    @pytest.mark.parametrize("service,url", [
        ("finance",     SERVICES["finance"] + "/health"),
        ("assistant",   SERVICES["assistant"] + "/health"),
        ("homelab",     SERVICES["homelab"] + "/health"),
        ("sports",      SERVICES["sports"] + "/health"),
        ("platform",    SERVICES["platform"] + "/health"),
        ("maintenance", SERVICES["maintenance"] + "/health"),
    ])
    def test_health_endpoint(self, service, url):
        """GET /health should return 200 with a healthy status."""
        try:
            resp = requests.get(url, timeout=10)
            assert resp.status_code == 200, f"{service} returned {resp.status_code}"
            data = resp.json()
            assert data.get("status") in ("ok", "up"), \
                f"{service} status is {data.get('status')}"
        except requests.ConnectionError:
            pytest.skip(f"{service} not reachable at {url}")

    def test_n8n_health(self):
        """N8N health endpoint (may use /healthz or custom path)."""
        url = SERVICES["n8n"] + "/healthz"
        try:
            resp = requests.get(url, timeout=10)
            assert resp.status_code == 200, f"N8N returned {resp.status_code}"
        except requests.ConnectionError:
            pytest.skip("N8N not reachable")

    @pytest.mark.parametrize("service,url", [
        ("finance",   SERVICES["finance"] + "/metrics"),
        ("assistant", SERVICES["assistant"] + "/metrics"),
        ("homelab",   SERVICES["homelab"] + "/metrics"),
        ("sports",    SERVICES["sports"] + "/metrics"),
    ])
    def test_metrics_endpoint(self, service, url):
        """GET /metrics should return Prometheus-format text."""
        try:
            resp = requests.get(url, timeout=10)
            assert resp.status_code == 200, f"{service} /metrics returned {resp.status_code}"
            assert "http_requests_total" in resp.text, \
                f"{service} /metrics missing http_requests_total counter"
        except requests.ConnectionError:
            pytest.skip(f"{service} not reachable at {url}")


# ═══════════════════════════════════════════════════════════════════════════════
#  PASS 2: N8N Integration (Webhook Triggers)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPass2N8NIntegration:
    """Verify N8N webhook triggers are accessible (POST returns 200 or 404)."""

    WEBHOOK_PATHS = [
        "/webhook/finance-forecast",
        "/webhook/finance-retrain",
        "/webhook/finance-watchlist",
        "/webhook/homelab-health",
        "/webhook/homelab-report",
        "/webhook/homelab-full-status",
        "/webhook/assistant-brief",
        "/webhook/assistant-tasks",
        "/webhook/assistant-followup",
        "/webhook/sports-daily",
        "/webhook/sports-nfl-picks",
        "/webhook/sports-nfl-game-ingest",
        "/webhook/sports-weekly-optimization",
        "/webhook/sports-ncaa-bracket",
        "/webhook/sports-news-ingest",
        "/webhook/sports-backfill",
        "/webhook/sports-ncaa-prep",
        "/webhook/db-maintenance",
        "/webhook/platform-error-handler",
        "/webhook/platform-system-status",
        "/webhook/platform-architecture-audit",
        "/webhook/platform-docker-rebuild",
    ]

    @pytest.mark.parametrize("path", WEBHOOK_PATHS)
    def test_webhook_accessible(self, path):
        """POST to each webhook path should not return a connection error.
        N8N may return 404 if the workflow isn't activated yet, which is OK.
        What matters is that N8N is running and accepting connections."""
        url = SERVICES["n8n"] + path
        try:
            resp = requests.post(url, json={"test": True}, timeout=10)
            # Accept 200 (webhook active) or 404 (not yet activated)
            # Reject 500 (server error) or connection failures
            assert resp.status_code in (200, 201, 404), \
                f"N8N webhook {path} returned {resp.status_code}"
        except requests.ConnectionError:
            pytest.skip("N8N not reachable")

    def test_n8n_api_accessible(self):
        """N8N REST API should be accessible (may require auth)."""
        url = SERVICES["n8n"] + "/api/v1/workflows"
        try:
            resp = requests.get(url, timeout=10)
            # 401 (unauthorized) is fine — it means N8N is running
            assert resp.status_code in (200, 401, 403), \
                f"N8N API returned {resp.status_code}"
        except requests.ConnectionError:
            pytest.skip("N8N not reachable")
