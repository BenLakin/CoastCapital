"""
Tests for the structured JSON logging configuration.
"""

import json
import logging
import os
import tempfile
from utils.logging_config import JsonFormatter, build_logger, get_logger


class TestJsonFormatter:
    def test_basic_format(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello world", args=(), exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["msg"] == "hello world"
        assert "ts" in data

    def test_exception_included(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="", lineno=0,
                msg="failed", args=(), exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert "ValueError" in data["exception"]

    def test_ctx_fields_merged(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="event", args=(), exc_info=None,
        )
        record.ctx = {"sport": "mlb", "rows": 42}
        output = formatter.format(record)
        data = json.loads(output)
        assert data["sport"] == "mlb"
        assert data["rows"] == 42


class TestBuildLogger:
    def test_logger_writes_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = build_logger("test-sports", log_dir=tmpdir)
            log.info("test message")
            log_file = os.path.join(tmpdir, "sports-engine.log")
            assert os.path.exists(log_file)
            with open(log_file) as f:
                line = f.readline()
            data = json.loads(line)
            assert data["msg"] == "test message"

    def test_get_logger_returns_logger(self):
        log = get_logger("test.module")
        assert isinstance(log, logging.Logger)
