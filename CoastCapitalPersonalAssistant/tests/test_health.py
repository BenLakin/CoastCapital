"""Tests for the /health liveness endpoint."""


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_returns_json(client):
    resp = client.get("/health")
    data = resp.get_json()
    assert data is not None


def test_health_status_ok(client):
    resp = client.get("/health")
    assert resp.get_json()["status"] == "ok"


def test_health_service_name(client):
    resp = client.get("/health")
    assert "coastcapital" in resp.get_json()["service"]


def test_health_no_auth_required(client):
    """Health endpoint must be reachable without an API key."""
    resp = client.get("/health")
    assert resp.status_code != 401
