"""
Centralized logging configuration for CoastCapital Personal Assistant.

Adds two rotating file handlers to the root logger:
  • logs/app.log   — all messages, 10 MB × 5 backups
  • logs/error.log — ERROR+ only, 5 MB × 3 backups

A console StreamHandler is added only outside of pytest (pytest injects
its own capture handler; we skip ours to avoid duplicate output).

Noisy third-party libraries are silenced to WARNING level.

Usage (called once at app startup in main.py):
    from app.logging_config import setup_logging
    setup_logging(log_dir="logs", log_level="INFO")
"""
import logging
import logging.handlers
import os
from pathlib import Path


def setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler — skip inside pytest to avoid duplicate output.
    # pytest sets PYTEST_CURRENT_TEST for the currently-running test.
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        if not any(type(h) is logging.StreamHandler for h in root.handlers):
            ch = logging.StreamHandler()
            ch.setLevel(level)
            ch.setFormatter(fmt)
            root.addHandler(ch)

    # Rotating file handlers — skip if already registered (guards against
    # multiple calls, e.g. gunicorn pre-fork + worker).
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)

        existing = {
            getattr(h, "baseFilename", None)
            for h in root.handlers
            if isinstance(h, logging.handlers.BaseRotatingHandler)
        }

        app_log = os.path.abspath(os.path.join(log_dir, "app.log"))
        if app_log not in existing:
            fh = logging.handlers.RotatingFileHandler(
                app_log,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            fh.setLevel(level)
            fh.setFormatter(fmt)
            root.addHandler(fh)

        err_log = os.path.abspath(os.path.join(log_dir, "error.log"))
        if err_log not in existing:
            eh = logging.handlers.RotatingFileHandler(
                err_log,
                maxBytes=5 * 1024 * 1024,  # 5 MB
                backupCount=3,
                encoding="utf-8",
            )
            eh.setLevel(logging.ERROR)
            eh.setFormatter(fmt)
            root.addHandler(eh)

    except OSError as exc:
        logging.getLogger(__name__).warning(
            "File logging unavailable (%s). Console only.", exc
        )

    # Silence noisy third-party libraries
    for lib in (
        "urllib3",
        "requests",
        "caldav",
        "anthropic._base_client",
        "imaplib",
        "werkzeug",
    ):
        logging.getLogger(lib).setLevel(logging.WARNING)
