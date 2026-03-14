"""
Tests for pipelines/backfill_pipeline.py — date iteration and multi-sport backfill.

Verifies orchestration logic: correct ingest function dispatch, error handling
for failed dates, and season-to-date-range conversion.
"""

from unittest.mock import patch, call

import pytest

from pipelines.backfill_pipeline import (
    SUPPORTED_SPORTS,
    backfill_sport,
    run_backfill_pipeline,
)


# ── backfill_sport ────────────────────────────────────────────────────────────

class TestBackfillSport:
    def test_unsupported_sport_raises(self):
        with pytest.raises(ValueError, match="Unsupported sport"):
            backfill_sport("curling", "2024-01-01", "2024-01-03")

    @patch("pipelines.backfill_pipeline.nfl_ingest")
    def test_nfl_calls_insert_nfl_data(self, mock_nfl):
        result = backfill_sport("nfl", "2024-09-08", "2024-09-10")
        assert result["sport"] == "nfl"
        assert result["processed_dates"] == 3
        assert result["failed_dates"] == []
        assert result["status"] == "ok"
        assert mock_nfl.insert_nfl_data.call_count == 3

    @patch("pipelines.backfill_pipeline.ncaa_mbb_ingest")
    def test_ncaa_mbb_calls_correct_function(self, mock_ncaa):
        result = backfill_sport("ncaa_mbb", "2024-03-01", "2024-03-02")
        assert result["sport"] == "ncaa_mbb"
        assert mock_ncaa.insert_ncaa_mbb_data.call_count == 2

    @patch("pipelines.backfill_pipeline.mlb_ingest")
    def test_mlb_calls_correct_function(self, mock_mlb):
        result = backfill_sport("mlb", "2024-04-01", "2024-04-01")
        assert result["sport"] == "mlb"
        assert mock_mlb.insert_mlb_data.call_count == 1

    @patch("pipelines.backfill_pipeline.nfl_ingest")
    def test_failed_dates_tracked(self, mock_nfl):
        """Failures should be logged but not stop the pipeline."""
        mock_nfl.insert_nfl_data.side_effect = [None, Exception("ESPN down"), None]
        result = backfill_sport("nfl", "2024-09-08", "2024-09-10")
        assert result["processed_dates"] == 2
        assert len(result["failed_dates"]) == 1
        assert result["status"] == "partial_error"

    @patch("pipelines.backfill_pipeline.nfl_ingest")
    def test_all_dates_fail(self, mock_nfl):
        mock_nfl.insert_nfl_data.side_effect = Exception("total failure")
        result = backfill_sport("nfl", "2024-09-08", "2024-09-09")
        assert result["processed_dates"] == 0
        assert len(result["failed_dates"]) == 2
        assert result["status"] == "partial_error"


# ── run_backfill_pipeline ─────────────────────────────────────────────────────

class TestRunBackfillPipeline:
    @patch("pipelines.backfill_pipeline.backfill_sport")
    def test_single_sport(self, mock_bf):
        mock_bf.return_value = {
            "sport": "nfl", "start_date": "2024-09-08",
            "end_date": "2024-09-10", "processed_dates": 3,
            "failed_dates": [], "status": "ok",
        }
        result = run_backfill_pipeline(sport="nfl", start_date="2024-09-08", end_date="2024-09-10")
        assert result["status"] == "ok"
        assert len(result["results"]) == 1
        mock_bf.assert_called_once_with("nfl", "2024-09-08", "2024-09-10")

    @patch("pipelines.backfill_pipeline.backfill_sport")
    def test_all_sports(self, mock_bf):
        mock_bf.return_value = {
            "sport": "any", "start_date": "2024-01-01",
            "end_date": "2024-01-02", "processed_dates": 2,
            "failed_dates": [], "status": "ok",
        }
        result = run_backfill_pipeline(sport="all", start_date="2024-01-01", end_date="2024-01-02")
        assert len(result["results"]) == len(SUPPORTED_SPORTS)
        assert result["status"] == "ok"

    def test_no_dates_or_season_raises(self):
        with pytest.raises(ValueError, match="Provide start_date"):
            run_backfill_pipeline(sport="nfl")

    @patch("pipelines.backfill_pipeline.backfill_sport")
    @patch("pipelines.backfill_pipeline.default_season_window", return_value=("2024-09-01", "2025-02-15"))
    def test_season_derives_dates(self, mock_window, mock_bf):
        mock_bf.return_value = {
            "sport": "nfl", "start_date": "2024-09-01",
            "end_date": "2025-02-15", "processed_dates": 100,
            "failed_dates": [], "status": "ok",
        }
        result = run_backfill_pipeline(sport="nfl", season=2024)
        mock_window.assert_called_once_with("nfl", 2024)
        assert result["status"] == "ok"

    @patch("pipelines.backfill_pipeline.backfill_sport")
    def test_partial_error_propagated(self, mock_bf):
        mock_bf.side_effect = [
            {"sport": "nfl", "status": "ok", "start_date": "2024-01-01",
             "end_date": "2024-01-02", "processed_dates": 2, "failed_dates": []},
            {"sport": "ncaa_mbb", "status": "partial_error", "start_date": "2024-01-01",
             "end_date": "2024-01-02", "processed_dates": 1, "failed_dates": ["2024-01-02"]},
            {"sport": "mlb", "status": "ok", "start_date": "2024-01-01",
             "end_date": "2024-01-02", "processed_dates": 2, "failed_dates": []},
        ]
        result = run_backfill_pipeline(sport="all", start_date="2024-01-01", end_date="2024-01-02")
        assert result["status"] == "partial_error"


# ── Supported sports constant ─────────────────────────────────────────────────

class TestSupportedSports:
    def test_all_three_sports(self):
        assert "nfl" in SUPPORTED_SPORTS
        assert "ncaa_mbb" in SUPPORTED_SPORTS
        assert "mlb" in SUPPORTED_SPORTS
        assert len(SUPPORTED_SPORTS) == 3
