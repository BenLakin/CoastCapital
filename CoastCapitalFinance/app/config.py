"""Application configuration."""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Flask
    FLASK_ENV: str = "production"
    SECRET_KEY: str = "change-me-in-production"
    API_KEY: str = ""  # empty = deny all non-health requests

    # MySQL (points to central coastcapital-mysql via docker-compose env)
    MYSQL_HOST: str = "coastcapital-mysql"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "dbadmin"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "finance_silver"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            "?charset=utf8mb4"
        )

    # APIs
    ANTHROPIC_API_KEY: Optional[str] = None

    # LLM Providers — parameterized per use case
    # Primary: stocks of interest (watchlist) — "anthropic", "gemini", "ollama"
    LLM_PROVIDER_PRIMARY: str = "ollama"
    # Secondary: other stocks (big movers only) — "anthropic", "gemini", "ollama"
    LLM_PROVIDER_SECONDARY: str = "ollama"

    # Gemini CLI configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"

    # Local Ollama configuration
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"

    # LLM filtering
    LLM_MAX_ARTICLES_PER_STOCK: int = 3  # max articles to LLM-analyze per stock per day

    # Logging
    LOG_LEVEL: str = "INFO"

    # Forecasting
    DEFAULT_FORECAST_HORIZON: int = 1
    DEFAULT_LOOKBACK_DAYS: int = 252
    MIN_TRAINING_DAYS: int = 252
    FORECAST_HORIZONS: str = "1,5"
    OPTUNA_N_TRIALS: int = 50
    OPTUNA_TIMEOUT: int = 300

    # Portfolio Optimizer
    PORTFOLIO_MAX_WEIGHT: float = 0.20
    PORTFOLIO_INITIAL_CAPITAL: float = 100.0
    PORTFOLIO_HOLDING_HORIZON: int = 21
    MONTE_CARLO_PATHS: int = 1000

    # Holdings Analyzer — Tax rates (computation, not advice)
    TAX_RATE_SHORT_TERM: float = 0.37
    TAX_RATE_LONG_TERM: float = 0.20
    TAX_HOLDING_PERIOD_DAYS: int = 365

    @property
    def forecast_horizons(self) -> list[int]:
        return [int(h.strip()) for h in self.FORECAST_HORIZONS.split(",")]

    # n8n
    N8N_WEBHOOK_SECRET: Optional[str] = None

    # Default watchlist
    DEFAULT_WATCHLIST: str = "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,JPM,BAC,WFC,SPY,QQQ"

    @property
    def watchlist(self) -> list[str]:
        return [t.strip().upper() for t in self.DEFAULT_WATCHLIST.split(",")]

    class Config:
        env_file = "../.env"
        extra = "ignore"


settings = Settings()
