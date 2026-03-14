"""Tests for API key authentication enforcement."""
import pytest


PROTECTED_ROUTES = [
    ("GET",  "/api/pipeline/email-summary"),
    ("GET",  "/api/pipeline/news-summary"),
    ("GET",  "/api/pipeline/calendar"),
    ("GET",  "/api/pipeline/reminders"),
    ("GET",  "/api/pipeline/deliveries"),
    ("GET",  "/api/pipeline/dashboard-data"),
    ("GET",  "/api/pipeline/morning-briefing"),
    ("GET",  "/api/pipeline/followup"),
    ("GET",  "/api/pipeline/birthdays"),
    ("POST", "/api/pipeline/comms-plan"),
    ("POST", "/api/pipeline/archive-emails"),
    ("POST", "/api/pipeline/reminders/add"),
    ("POST", "/api/send-email"),
    ("POST", "/api/agent/chat"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_no_api_key_returns_401(client, method, path):
    resp = client.open(path, method=method)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Unauthorized"


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_wrong_api_key_returns_401(client, method, path):
    resp = client.open(
        path, method=method,
        headers={"X-API-Key": "completely-wrong-key"},
    )
    assert resp.status_code == 401


def test_valid_key_in_header_passes_auth(client, auth_headers, monkeypatch):
    """A request with the correct X-API-Key header should not get 401."""
    # Email pipeline will error on IMAP but that's a 500, not 401
    resp = client.get("/api/pipeline/email-summary", headers=auth_headers)
    assert resp.status_code != 401


def test_valid_key_as_query_param_passes_auth(client):
    """API key may also be passed as ?api_key=..."""
    resp = client.get("/api/pipeline/email-summary?api_key=test-api-key")
    assert resp.status_code != 401


def test_health_endpoint_is_public(client):
    """Health check must be accessible without authentication."""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_dashboard_page_is_public(client, mock_db):
    """/dashboard HTML page doesn't require an API key."""
    resp = client.get("/dashboard")
    assert resp.status_code == 200


def test_relationships_page_is_public(client, mock_db):
    """/relationships page doesn't require an API key."""
    resp = client.get("/relationships")
    assert resp.status_code == 200
