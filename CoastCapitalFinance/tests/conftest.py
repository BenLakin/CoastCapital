"""
pytest configuration and shared fixtures.

Stubs heavy dependencies (pydantic_settings, sqlalchemy, optuna, structlog)
before app imports so tests can run without Docker or GPU dependencies.
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# ── Stub heavy modules before any app imports ─────────────────────────────────

def _stub_module(name):
    """Register a MagicMock as a fake module so imports don't fail."""
    if name not in sys.modules:
        sys.modules[name] = MagicMock()


# pydantic_settings needs a BaseSettings class that works as a real base class
_pydantic_settings = MagicMock()


class _FakeBaseSettings:
    """Minimal BaseSettings stub so Settings(BaseSettings) can be instantiated."""
    model_config = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


_pydantic_settings.BaseSettings = _FakeBaseSettings
sys.modules.setdefault("pydantic_settings", _pydantic_settings)

# SQLAlchemy needs proper sub-module hierarchy for `from sqlalchemy.X import Y`
_sa = MagicMock()
_sa_orm = MagicMock()
_sa_sql = MagicMock()

# Provide a real DeclarativeBase so ORM model classes can be created
class _FakeDeclarativeBase:
    metadata = MagicMock()
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

_sa_orm.DeclarativeBase = _FakeDeclarativeBase
_sa_orm.relationship = MagicMock()
_sa_orm.sessionmaker = MagicMock()
_sa_orm.Session = MagicMock()

for mod_name, mod_obj in {
    "sqlalchemy": _sa,
    "sqlalchemy.orm": _sa_orm,
    "sqlalchemy.sql": _sa_sql,
    "sqlalchemy.pool": MagicMock(),
    "sqlalchemy.ext": MagicMock(),
    "sqlalchemy.ext.declarative": MagicMock(),
    "sqlalchemy.dialects": MagicMock(),
    "sqlalchemy.dialects.mysql": MagicMock(),
}.items():
    sys.modules.setdefault(mod_name, mod_obj)

# Stub ML / data-science libraries not installed locally
_sklearn = MagicMock()
for sk_sub in [
    "sklearn", "sklearn.ensemble", "sklearn.linear_model",
    "sklearn.preprocessing", "sklearn.model_selection", "sklearn.metrics",
    "sklearn.covariance", "sklearn.base", "sklearn.utils",
]:
    sys.modules.setdefault(sk_sub, MagicMock() if sk_sub != "sklearn" else _sklearn)

_scipy = MagicMock()
for sp_sub in [
    "scipy", "scipy.stats", "scipy.optimize",
]:
    sys.modules.setdefault(sp_sub, MagicMock() if sp_sub != "scipy" else _scipy)

for mod in [
    "optuna", "optuna.study", "optuna.trial",
    "structlog",
    "joblib",
    "yfinance",
    "ta", "ta.momentum", "ta.trend", "ta.volatility", "ta.volume",
    "lightgbm",
    "xgboost",
    "catboost",
    "tenacity",
]:
    _stub_module(mod)

# Set env vars before importing app
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_USER", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("MYSQL_DATABASE", "test_db")
os.environ.setdefault("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))

# Ensure app directory is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Pre-import finance submodules so @patch() can resolve dotted paths.
# All heavy deps are already stubbed above, so these imports succeed
# even without real ML libraries installed.
import app.pipelines.ingestion        # noqa: E402, F401
import app.pipelines.technicals       # noqa: E402, F401
import app.pipelines.daily_process    # noqa: E402, F401
import app.pipelines.backfill         # noqa: E402, F401
import app.forecasting.features       # noqa: E402, F401
import app.forecasting.models         # noqa: E402, F401
import app.forecasting.backtesting    # noqa: E402, F401
import app.forecasting.portfolio      # noqa: E402, F401
import app.forecasting.holdings       # noqa: E402, F401


@pytest.fixture(autouse=True)
def mock_db_connection():
    """Auto-mock database connections for all tests."""
    with patch("app.models.database.create_db_engine") as mock_engine:
        mock_engine.return_value = MagicMock()
        yield mock_engine


@pytest.fixture(autouse=True)
def mock_settings_db():
    """Ensure test settings don't require real DB credentials."""
    with patch("app.config.settings") as mock_settings:
        mock_settings.MYSQL_HOST = "localhost"
        mock_settings.MYSQL_PORT = 3306
        mock_settings.MYSQL_USER = "test"
        mock_settings.MYSQL_PASSWORD = "test"
        mock_settings.MYSQL_DATABASE = "test_db"
        mock_settings.DATABASE_URL = "sqlite:///:memory:"
        mock_settings.ANTHROPIC_API_KEY = None
        mock_settings.NEWS_API_KEY = None
        mock_settings.N8N_WEBHOOK_SECRET = None
        mock_settings.LOG_LEVEL = "WARNING"
        mock_settings.DEFAULT_LOOKBACK_DAYS = 252
        mock_settings.MIN_TRAINING_DAYS = 252
        mock_settings.FORECAST_HORIZONS = "1,5"
        mock_settings.forecast_horizons = [1, 5]
        mock_settings.OPTUNA_N_TRIALS = 5
        mock_settings.OPTUNA_TIMEOUT = 30
        mock_settings.PORTFOLIO_MAX_WEIGHT = 0.20
        mock_settings.PORTFOLIO_INITIAL_CAPITAL = 100.0
        mock_settings.PORTFOLIO_HOLDING_HORIZON = 21
        mock_settings.MONTE_CARLO_PATHS = 100
        mock_settings.TAX_RATE_SHORT_TERM = 0.37
        mock_settings.TAX_RATE_LONG_TERM = 0.20
        mock_settings.TAX_HOLDING_PERIOD_DAYS = 365
        mock_settings.DEFAULT_FORECAST_HORIZON = 1
        mock_settings.watchlist = ["AAPL", "MSFT"]
        yield mock_settings
