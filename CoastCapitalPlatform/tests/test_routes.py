"""
Tests for Platform API routes.
"""

import json
from unittest.mock import patch, MagicMock, AsyncMock

from app.dispatcher import IntentResult


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "coastcapital-platform"


class TestClassifyIntent:
    @patch("app.main.classify_intent")
    def test_classify_returns_result(self, mock_classify, client, api_headers):
        mock_classify.return_value = IntentResult(
            intent="finance_forecast",
            params={"tickers": ["AAPL"]},
            confidence=0.95,
            webhook_path="/webhook/finance-forecast",
        )
        resp = client.post(
            "/api/classify-intent",
            json={"text": "run forecast for AAPL"},
            headers=api_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "finance_forecast"
        assert data["confidence"] == 0.95

    def test_classify_requires_text(self, client, api_headers):
        resp = client.post("/api/classify-intent", json={}, headers=api_headers)
        assert resp.status_code == 422  # Validation error

    def test_classify_rejects_bad_api_key(self, client):
        resp = client.post(
            "/api/classify-intent",
            json={"text": "test"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401


class TestIntentsList:
    def test_intents_returns_list(self, client, api_headers):
        resp = client.get("/api/intents", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "intents" in data
        assert len(data["intents"]) > 0


class TestArchitectureAudit:
    @patch("app.agents.architecture_agent.run_audit", new_callable=AsyncMock)
    def test_audit_returns_findings(self, mock_audit, client, api_headers):
        mock_audit.return_value = [
            {"severity": "warning", "module": "Sports", "title": "Missing docstring",
             "description": "main.py missing module docstring", "file": "main.py", "suggested_fix": "Add docstring"}
        ]
        resp = client.post("/api/architecture-audit", json={}, headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["findings"][0]["severity"] == "warning"

    @patch("app.agents.architecture_agent.run_audit", new_callable=AsyncMock)
    def test_audit_dry_run(self, mock_audit, client, api_headers):
        mock_audit.return_value = []
        resp = client.post("/api/architecture-audit", json={"dry_run": True}, headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
