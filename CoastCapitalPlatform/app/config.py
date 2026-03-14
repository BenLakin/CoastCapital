"""
Configuration for CoastCapital Platform service.
"""

import os


class Config:
    """Reads from centralized .env (passed via docker-compose env_file)."""

    # Ollama (local LLM for intent classification)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    # Anthropic (for Architecture Agent)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    # MySQL (for prediction logging + feedback)
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "coastcapital-mysql")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "dbadmin")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("PLATFORM_MYSQL_DATABASE", "maintenance_db")

    # Slack
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")

    # Git (for Architecture Agent MR creation)
    GIT_USER_NAME: str = os.getenv("GIT_USER_NAME", "CoastCapital Bot")
    GIT_USER_EMAIL: str = os.getenv("GIT_USER_EMAIL", "bot@coastcapital.local")
    GIT_REMOTE_URL: str = os.getenv("GIT_REMOTE_URL", "")

    # Platform API key (for authenticating N8N calls)
    PLATFORM_API_KEY: str = os.getenv("PLATFORM_API_KEY", "")

    # Workspace root (mounted via docker volume)
    WORKSPACE_ROOT: str = os.getenv("WORKSPACE_ROOT", "/workspace")

    # Feedback ground truth limits
    MAX_GOOD_EXAMPLES: int = int(os.getenv("MAX_GOOD_EXAMPLES", "100"))
    MAX_BAD_EXAMPLES: int = int(os.getenv("MAX_BAD_EXAMPLES", "100"))
