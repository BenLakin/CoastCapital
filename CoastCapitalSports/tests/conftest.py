"""
Shared fixtures for CoastCapital Sports tests.

Mocks all database connections and heavy imports so tests
run without MySQL, PyTorch, or external services.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Set env vars before any app imports
os.environ.setdefault("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
os.environ.setdefault("API_KEY", "test-sports-api-key")

# Ensure app directory is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


# ── Mock heavy modules before import ──────────────────────────────────────

def _stub_module(name):
    """Register a MagicMock as a fake module so imports don't fail."""
    if name not in sys.modules:
        sys.modules[name] = MagicMock()

# Import numpy/pandas so they are real (installed locally).
# Only mock torch and sklearn which require GPU / large binary deps.
import numpy  # noqa: F401 — ensures real numpy stays in sys.modules
import pandas  # noqa: F401

for mod in [
    "torch", "torch.nn", "torch.optim", "torch.utils", "torch.utils.data",
    "sklearn", "sklearn.metrics", "sklearn.model_selection",
]:
    _stub_module(mod)


@pytest.fixture(autouse=True)
def mock_db():
    """Auto-mock database.get_connection for all tests."""
    with patch("database.get_connection") as mock:
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None
        conn.cursor.return_value = cursor
        mock.return_value = conn
        yield mock


@pytest.fixture(autouse=True)
def mock_pipelines():
    """Auto-mock pipeline imports so tests don't run real pipelines."""
    mocks = {}
    targets = [
        "models.cross_validate_torch_model.cross_validate_model",
        "models.modeling_data.materialize_features_to_modeling_silver",
        "models.score_torch_model.score_model",
        "models.train_torch_model.train_model",
        "models.tune_torch_model.tune_model",
        "models.promote_model.promote_model",
        "models.promote_model.refit_model",
        "models.promote_model.get_model_status",
        "pipelines.backfill_pipeline.run_backfill_pipeline",
        "pipelines.update_pipeline.run_update_pipeline",
    ]
    patchers = []
    for target in targets:
        try:
            p = patch(target, return_value={"status": "ok"})
            mocks[target] = p.start()
            patchers.append(p)
        except Exception:
            pass
    yield mocks
    for p in patchers:
        p.stop()


@pytest.fixture()
def client():
    """Flask test client with mocked dependencies."""
    from main import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def api_headers():
    return {"X-API-Key": os.environ["API_KEY"]}


@pytest.fixture()
def bad_headers():
    return {"X-API-Key": "wrong-key"}
