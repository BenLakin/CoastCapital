"""
Tests for the Ollama intent dispatcher.
"""

import json
from unittest.mock import patch, MagicMock

from app.dispatcher import classify_intent, get_intent_registry, IntentResult


class TestIntentRegistry:
    def test_registry_not_empty(self):
        intents = get_intent_registry()
        assert len(intents) > 0

    def test_registry_has_required_fields(self):
        for intent in get_intent_registry():
            assert "id" in intent
            assert "webhook" in intent
            assert "params" in intent
            assert "desc" in intent

    def test_all_webhooks_start_with_slash(self):
        for intent in get_intent_registry():
            assert intent["webhook"].startswith("/webhook/")


class TestClassifyIntent:
    @patch("app.dispatcher.requests.post")
    def test_high_confidence_returns_intent(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": json.dumps({
                "intent": "finance_forecast",
                "params": {"tickers": ["AAPL"]},
                "confidence": 0.95,
                "clarification": None,
            })
        }
        mock_post.return_value = mock_resp

        result = classify_intent("run the finance forecast for AAPL")
        assert result.intent == "finance_forecast"
        assert result.confidence == 0.95
        assert result.webhook_path == "/webhook/finance-forecast"

    @patch("app.dispatcher.requests.post")
    def test_low_confidence_triggers_clarification(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": json.dumps({
                "intent": "sports_daily",
                "params": {},
                "confidence": 0.3,
                "clarification": "Did you mean the sports daily pipeline?",
            })
        }
        mock_post.return_value = mock_resp

        result = classify_intent("do the sports thing")
        assert result.intent == "unclear"
        assert result.clarification is not None

    @patch("app.dispatcher.requests.post")
    def test_ollama_failure_returns_unclear(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("Connection refused")

        result = classify_intent("run something")
        assert result.intent == "unclear"
        assert result.confidence == 0.0

    @patch("app.dispatcher.requests.post")
    def test_invalid_json_returns_unclear(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "not json at all"}
        mock_post.return_value = mock_resp

        result = classify_intent("test")
        assert result.intent == "unclear"


class TestIntentResult:
    def test_to_dict(self):
        result = IntentResult(
            intent="finance_forecast",
            params={"tickers": ["AAPL"]},
            confidence=0.9,
            webhook_path="/webhook/finance-forecast",
        )
        d = result.to_dict()
        assert d["intent"] == "finance_forecast"
        assert d["confidence"] == 0.9
        assert d["webhook_path"] == "/webhook/finance-forecast"
