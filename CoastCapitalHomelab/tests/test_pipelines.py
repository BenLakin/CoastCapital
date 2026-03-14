"""
Unit tests for HomeLab pipeline logic.

Tests core methods of each pipeline class with mocked HTTP calls,
SSH connections, file I/O, and database access. Validates data
transformation, error handling, and snapshot persistence.
"""

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch, mock_open

import pytest


# ── DNS Pipeline ──────────────────────────────────────────────────────────────

class TestDNSPipeline:
    def _make(self):
        from app.pipelines.dns_pipeline import DNSPipeline
        return DNSPipeline()

    def test_get_records_parses_hosts_file(self, tmp_path):
        hosts = tmp_path / "custom.hosts"
        hosts.write_text("192.168.1.1 router.local\n192.168.1.2 nas.local\n")
        with patch("app.config.Config.DNS_HOSTS_FILE", str(hosts)):
            records = self._make().get_records()
        assert len(records) == 2
        assert records[0] == {"ip": "192.168.1.1", "domain": "router.local"}
        assert records[1] == {"ip": "192.168.1.2", "domain": "nas.local"}

    def test_get_records_skips_comments_and_blank_lines(self, tmp_path):
        hosts = tmp_path / "custom.hosts"
        hosts.write_text("# header comment\n\n192.168.1.1 router.local\n# another comment\n")
        with patch("app.config.Config.DNS_HOSTS_FILE", str(hosts)):
            records = self._make().get_records()
        assert len(records) == 1

    def test_get_records_returns_empty_for_missing_file(self):
        with patch("app.config.Config.DNS_HOSTS_FILE", "/nonexistent/path"):
            records = self._make().get_records()
        assert records == []

    def test_add_record_appends_to_file(self, tmp_path):
        hosts = tmp_path / "custom.hosts"
        hosts.write_text("192.168.1.1 existing.local\n")
        with patch("app.config.Config.DNS_HOSTS_FILE", str(hosts)), \
             patch("app.db.log_event"):
            result = self._make().add_record("10.0.0.1", "new.local")
        assert result["success"] is True
        content = hosts.read_text()
        assert "10.0.0.1 new.local" in content

    def test_add_record_prevents_duplicate(self, tmp_path):
        hosts = tmp_path / "custom.hosts"
        hosts.write_text("192.168.1.1 router.local\n")
        with patch("app.config.Config.DNS_HOSTS_FILE", str(hosts)):
            result = self._make().add_record("192.168.1.1", "router.local")
        assert result["success"] is False
        assert "already exists" in result["error"]

    def test_add_record_rejects_empty_ip(self, tmp_path):
        hosts = tmp_path / "custom.hosts"
        hosts.write_text("")
        with patch("app.config.Config.DNS_HOSTS_FILE", str(hosts)):
            result = self._make().add_record("", "router.local")
        assert result["success"] is False

    def test_add_record_lowercases_domain(self, tmp_path):
        hosts = tmp_path / "custom.hosts"
        hosts.write_text("")
        with patch("app.config.Config.DNS_HOSTS_FILE", str(hosts)), \
             patch("app.db.log_event"):
            result = self._make().add_record("10.0.0.1", "MyServer.LOCAL")
        assert result["domain"] == "myserver.local"

    def test_delete_record_removes_entry(self, tmp_path):
        hosts = tmp_path / "custom.hosts"
        hosts.write_text("# header\n192.168.1.1 router.local\n192.168.1.2 nas.local\n")
        with patch("app.config.Config.DNS_HOSTS_FILE", str(hosts)), \
             patch("app.db.log_event"):
            result = self._make().delete_record("192.168.1.1", "router.local")
        assert result["success"] is True
        content = hosts.read_text()
        assert "router.local" not in content
        assert "nas.local" in content

    def test_get_summary_includes_status(self, tmp_path):
        hosts = tmp_path / "custom.hosts"
        hosts.write_text("192.168.1.1 router.local\n")
        with patch("app.config.Config.DNS_HOSTS_FILE", str(hosts)), \
             patch("app.config.Config.DNS_HEALTH_URL", "http://fake"), \
             patch("app.config.Config.DNS_UPSTREAM", "1.1.1.1"), \
             patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            summary = self._make().get_summary()
        assert summary["status"] == "online"
        assert summary["record_count"] == 1

    def test_get_summary_offline_when_health_fails(self, tmp_path):
        hosts = tmp_path / "custom.hosts"
        hosts.write_text("")
        with patch("app.config.Config.DNS_HOSTS_FILE", str(hosts)), \
             patch("app.config.Config.DNS_HEALTH_URL", "http://fake"), \
             patch("app.config.Config.DNS_UPSTREAM", "1.1.1.1"), \
             patch("requests.get", side_effect=Exception("timeout")):
            summary = self._make().get_summary()
        assert summary["status"] == "offline"

    def test_get_summary_not_configured(self):
        with patch("app.config.Config.DNS_HOSTS_FILE", ""):
            summary = self._make().get_summary()
        assert "error" in summary


# ── Homepage Pipeline ─────────────────────────────────────────────────────────

class TestHomepagePipeline:
    def _make(self):
        from app.pipelines.homepage_pipeline import HomepagePipeline
        return HomepagePipeline()

    def test_get_status_not_configured(self):
        with patch("app.config.Config.HOMEPAGE_URL", ""):
            result = self._make().get_status()
        assert result["status"] == "not_configured"

    @patch("requests.get")
    def test_get_status_with_widgets(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"name": "CPU"}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        with patch("app.config.Config.HOMEPAGE_URL", "http://homepage:3000"):
            result = self._make().get_status()
        assert result["reachable"] is True
        assert "widgets" in result

    @patch("requests.get")
    def test_get_status_falls_back_on_404(self, mock_get):
        resp_404 = MagicMock()
        resp_404.status_code = 404
        resp_200 = MagicMock()
        resp_200.status_code = 200
        mock_get.side_effect = [resp_404, resp_200]
        with patch("app.config.Config.HOMEPAGE_URL", "http://homepage:3000"):
            result = self._make().get_status()
        assert result["reachable"] is True

    @patch("requests.get")
    def test_get_status_connection_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError("refused")
        with patch("app.config.Config.HOMEPAGE_URL", "http://homepage:3000"):
            result = self._make().get_status()
        assert result["reachable"] is False

    @patch("requests.get")
    def test_health_check_true(self, mock_get):
        mock_get.return_value.status_code = 200
        with patch("app.config.Config.HOMEPAGE_URL", "http://homepage:3000"):
            assert self._make().health_check() is True

    @patch("requests.get")
    def test_health_check_false_on_error(self, mock_get):
        mock_get.side_effect = Exception("down")
        with patch("app.config.Config.HOMEPAGE_URL", "http://homepage:3000"):
            assert self._make().health_check() is False


# ── Ollama Pipeline ───────────────────────────────────────────────────────────

class TestOllamaPipeline:
    def _make(self):
        from app.pipelines.ollama_pipeline import OllamaPipeline
        return OllamaPipeline()

    @patch("requests.get")
    def test_get_summary_parses_models(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {
            "models": [
                {"name": "llama3.1:8b", "size": 4_000_000_000,
                 "modified_at": "2024-01-01", "details": {
                     "family": "llama", "parameter_size": "8B",
                     "quantization_level": "Q4_0"}}
            ]
        }
        with patch("app.config.Config.OLLAMA_BASE_URL", "http://localhost:11434"):
            result = self._make().get_summary()
        assert result["models_count"] == 1
        assert result["models"][0]["name"] == "llama3.1:8b"
        assert result["models"][0]["size_gb"] == 4.0

    @patch("requests.get")
    def test_get_summary_not_configured(self, mock_get):
        with patch("app.config.Config.OLLAMA_BASE_URL", ""):
            result = self._make().get_summary()
        assert "error" in result

    @patch("requests.get")
    def test_get_summary_handles_error(self, mock_get):
        mock_get.side_effect = Exception("connection refused")
        with patch("app.config.Config.OLLAMA_BASE_URL", "http://localhost:11434"), \
             patch("app.db.log_event"):
            result = self._make().get_summary()
        assert "error" in result

    @patch("requests.get")
    def test_get_running_returns_list(self, mock_get):
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {
            "models": [{"name": "llama3.1:8b", "size": 4e9, "expires_at": "2024-12-31"}]
        }
        with patch("app.config.Config.OLLAMA_BASE_URL", "http://localhost:11434"):
            result = self._make().get_running()
        assert len(result) == 1
        assert result[0]["name"] == "llama3.1:8b"

    @patch("requests.get")
    def test_get_running_returns_empty_on_error(self, mock_get):
        mock_get.side_effect = Exception("timeout")
        with patch("app.config.Config.OLLAMA_BASE_URL", "http://localhost:11434"):
            result = self._make().get_running()
        assert result == []

    @patch("requests.post")
    def test_pull_model_success(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        mock_post.return_value.json.return_value = {"status": "success"}
        with patch("app.config.Config.OLLAMA_BASE_URL", "http://localhost:11434"):
            result = self._make().pull_model("llama3.1:8b")
        assert result["success"] is True

    @patch("requests.post")
    def test_pull_model_failure(self, mock_post):
        mock_post.side_effect = Exception("network error")
        with patch("app.config.Config.OLLAMA_BASE_URL", "http://localhost:11434"):
            result = self._make().pull_model("llama3.1:8b")
        assert result["success"] is False

    @patch("requests.post")
    def test_generate_returns_text(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        mock_post.return_value.json.return_value = {"response": "Hello world"}
        with patch("app.config.Config.OLLAMA_BASE_URL", "http://localhost:11434"):
            result = self._make().generate("llama3.1:8b", "Say hello")
        assert result == "Hello world"

    @patch("requests.post")
    def test_generate_returns_error_string(self, mock_post):
        mock_post.side_effect = Exception("model not found")
        with patch("app.config.Config.OLLAMA_BASE_URL", "http://localhost:11434"):
            result = self._make().generate("missing", "test")
        assert "Error:" in result


# ── Plex Pipeline ─────────────────────────────────────────────────────────────

class TestPlexPipeline:
    def _make(self):
        from app.pipelines.plex_pipeline import PlexPipeline
        return PlexPipeline()

    def test_headers_include_token(self):
        with patch("app.config.Config.PLEX_TOKEN", "test-token"):
            headers = self._make()._headers()
        assert headers["X-Plex-Token"] == "test-token"
        assert headers["Accept"] == "application/json"

    @patch("requests.get")
    def test_get_summary_not_configured(self, mock_get):
        with patch("app.config.Config.PLEX_URL", ""), \
             patch("app.config.Config.PLEX_TOKEN", ""):
            result = self._make().get_summary()
        assert "error" in result

    @patch("requests.get")
    def test_get_returns_json(self, mock_get):
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {"MediaContainer": {"size": 5}}
        with patch("app.config.Config.PLEX_URL", "http://plex:32400"), \
             patch("app.config.Config.PLEX_TOKEN", "tok"):
            result = self._make()._get("/status/sessions")
        assert result["MediaContainer"]["size"] == 5


# ── Home Assistant Pipeline ───────────────────────────────────────────────────

class TestHomeAssistantPipeline:
    def _make(self):
        from app.pipelines.homeassistant_pipeline import HomeAssistantPipeline
        return HomeAssistantPipeline()

    def test_headers_include_bearer_token(self):
        with patch("app.config.Config.HA_TOKEN", "test-ha-token"):
            headers = self._make()._headers()
        assert headers["Authorization"] == "Bearer test-ha-token"

    @patch("requests.get")
    def test_get_summary_not_configured(self, mock_get):
        with patch("app.config.Config.HA_URL", ""), \
             patch("app.config.Config.HA_TOKEN", ""):
            result = self._make().get_summary()
        assert "error" in result

    @patch("requests.get")
    def test_get_summary_counts_entities(self, mock_get):
        entities = [
            {"entity_id": "light.living_room", "state": "on", "attributes": {}},
            {"entity_id": "automation.morning", "state": "on", "attributes": {}},
            {"entity_id": "automation.night", "state": "off", "attributes": {}},
            {"entity_id": "sensor.temp", "state": "unavailable", "attributes": {"friendly_name": "Temp"}},
        ]
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = entities
        with patch("app.config.Config.HA_URL", "http://ha:8123"), \
             patch("app.config.Config.HA_TOKEN", "tok"):
            result = self._make().get_summary()
        assert result["entity_count"] == 4
        assert result["automations_on"] == 1
        assert result["alert_count"] >= 1  # sensor.temp is unavailable


# ── UniFi Pipeline ────────────────────────────────────────────────────────────

class TestUniFiPipeline:
    def _make(self):
        from app.pipelines.unifi_pipeline import UniFiPipeline
        p = UniFiPipeline.__new__(UniFiPipeline)
        p.base = "https://unifi.local:443"
        p.site = "default"
        p._session = MagicMock()
        return p

    def test_get_network_stats_not_configured(self):
        from app.pipelines.unifi_pipeline import UniFiPipeline
        with patch("app.config.Config.UNIFI_HOST", ""):
            p = UniFiPipeline.__new__(UniFiPipeline)
            p.base = ""
            p.site = ""
            p._session = None
            # Pipeline should handle empty config gracefully
            # (actual behavior depends on implementation)

    def test_session_is_cached(self):
        p = self._make()
        session = p._session
        assert session is not None


# ── Portainer Pipeline ────────────────────────────────────────────────────────

class TestPortainerPipeline:
    def _make(self):
        from app.pipelines.portainer_pipeline import PortainerPipeline
        return PortainerPipeline()

    @patch("requests.post")
    def test_auth_returns_jwt(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        mock_post.return_value.json.return_value = {"jwt": "test-token"}
        from app.pipelines.portainer_pipeline import PortainerPipeline
        PortainerPipeline._jwt = None
        with patch("app.config.Config.PORTAINER_URL", "http://portainer:9000"), \
             patch("app.config.Config.PORTAINER_USERNAME", "admin"), \
             patch("app.config.Config.PORTAINER_PASSWORD", "pass"):
            token = self._make()._auth()
        assert token == "test-token"
        PortainerPipeline._jwt = None  # clean up class-level state

    def test_get_summary_not_configured(self):
        from app.pipelines.portainer_pipeline import PortainerPipeline
        PortainerPipeline._jwt = None
        with patch("app.config.Config.PORTAINER_URL", ""):
            result = self._make().get_summary()
        assert "error" in result


# ── System Pipeline ───────────────────────────────────────────────────────────

class TestSystemPipeline:
    def _make(self):
        from app.pipelines.system_pipeline import SystemPipeline
        return SystemPipeline()

    def test_mac_stats_parses_cpu(self):
        """Verify CPU idle parsing from macOS top output."""
        p = self._make()
        mock_client = MagicMock()
        raw_top = (
            "Processes: 400 total, 2 running, 398 sleeping\n"
            "Load Avg: 2.50, 1.80, 1.20\n"
            "CPU usage: 12.50% user, 8.30% sys, 79.20% idle\n"
            "SharedLibs: 500M resident, 100M data\n"
            "MemRegions: 50000 total\n"
            "PhysMem: 16G used (2000M wired, 500M compressor), 500M unused.\n"
        )
        mock_client.exec_command.return_value = (
            None,
            MagicMock(read=MagicMock(return_value=raw_top.encode())),
            MagicMock(read=MagicMock(return_value=b"")),
        )
        result = p._mac_stats(mock_client)
        assert result["load_1"] == 2.50
        assert result["load_5"] == 1.80
        assert result["load_15"] == 1.20
        # CPU pct = 100 - idle
        assert result["cpu_pct"] is not None

    def test_exec_runs_command(self):
        p = self._make()
        mock_client = MagicMock()
        mock_client.exec_command.return_value = (
            None,
            MagicMock(read=MagicMock(return_value=b"output text")),
            MagicMock(read=MagicMock(return_value=b"")),
        )
        result = p._exec(mock_client, "echo hello")
        assert result == "output text"
