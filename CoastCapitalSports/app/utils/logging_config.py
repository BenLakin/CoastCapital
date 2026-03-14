"""
Structured JSON logging for CoastCapital Sports.

Every log record is a single JSON line with:
  ts, level, logger, msg, and optional ctx fields.

Usage:
    from utils.logging_config import get_logger
    log = get_logger(__name__)
    log.info("event", extra={"ctx": {"key": "value"}})
"""

import json as _json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "ctx"):
            payload.update(record.ctx)
        return _json.dumps(payload)


def build_logger(name: str, log_dir: str | None = None) -> logging.Logger:
    """Create a logger with JSON formatting to stdout + rotating file."""
    if log_dir is None:
        log_dir = os.environ.get("LOG_DIR", "/app/logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "sports-engine.log")

    formatter = JsonFormatter()

    stream_h = logging.StreamHandler()
    stream_h.setFormatter(formatter)

    file_h = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5)
    file_h.setFormatter(formatter)

    log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.handlers = [stream_h, file_h]
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a structured JSON logger for the given module."""
    return build_logger(name)
