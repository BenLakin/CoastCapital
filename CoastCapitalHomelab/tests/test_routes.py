"""
Route tests for CoastCapital HomeLab API.

Tests health, dashboard, and pipeline endpoints.
"""

import json
from unittest.mock import patch, MagicMock


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        assert "ts" in data


class TestDashboard:
    def test_root_redirects_or_renders(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_dashboard_renders(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200


class TestAuthMiddleware:
    def test_missing_api_key_returns_401(self, client):
        resp = client.get("/api/pipeline/system")
        assert resp.status_code == 401
        data = json.loads(resp.data)
        assert data["error"] == "Unauthorized"

    def test_valid_api_key_accepted(self, client, api_headers):
        with patch("app.pipelines.system_pipeline.SystemPipeline") as mock_cls:
            mock_cls.return_value.get_system_health.return_value = {"cpu": 10}
            resp = client.get("/api/pipeline/system", headers=api_headers)
            assert resp.status_code == 200


class TestPipelineEndpoints:
    def test_system_pipeline(self, client, api_headers):
        with patch("app.pipelines.system_pipeline.SystemPipeline") as mock_cls:
            mock_cls.return_value.get_system_health.return_value = {
                "cpu_percent": 15, "memory_percent": 40
            }
            resp = client.get("/api/pipeline/system", headers=api_headers)
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert "cpu_percent" in data

    def test_full_status(self, client, api_headers):
        ok = {"status": "ok"}
        with patch("app.pipelines.system_pipeline.SystemPipeline") as mock_sys, \
             patch("app.pipelines.unifi_pipeline.UniFiPipeline") as mock_unifi, \
             patch("app.pipelines.plex_pipeline.PlexPipeline") as mock_plex, \
             patch("app.pipelines.homeassistant_pipeline.HomeAssistantPipeline") as mock_ha, \
             patch("app.pipelines.ollama_pipeline.OllamaPipeline") as mock_ollama, \
             patch("app.pipelines.dns_pipeline.DNSPipeline") as mock_dns, \
             patch("app.pipelines.portainer_pipeline.PortainerPipeline") as mock_portainer, \
             patch("app.pipelines.homepage_pipeline.HomepagePipeline") as mock_homepage:

            # Wire up the specific methods called by the full-status route
            mock_sys.return_value.get_system_health.return_value = ok
            mock_unifi.return_value.get_network_stats.return_value = ok
            mock_plex.return_value.get_summary.return_value = ok
            mock_ha.return_value.get_summary.return_value = ok
            mock_ollama.return_value.get_summary.return_value = ok
            mock_dns.return_value.get_summary.return_value = ok
            mock_portainer.return_value.get_summary.return_value = ok
            mock_homepage.return_value.get_status.return_value = ok

            resp = client.get("/api/pipeline/full-status", headers=api_headers)
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert "status" in data

    def test_events_endpoint(self, client, api_headers, mock_db):
        resp = client.get("/api/events", headers=api_headers)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "events" in data
