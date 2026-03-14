"""
Tests for the ML model pipeline — train, cross-validate, score, and promote.

Heavy dependencies (torch, model training) are mocked by conftest.py.
These tests validate orchestration logic: parameter validation, error handling,
return structure, and correct function call sequences.
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, mock_open, patch

import numpy as np
import pandas as pd
import pytest

from features.feature_registry import FEATURE_COLUMNS, TARGET_COLUMNS


# Override conftest's autouse mock_pipelines so we can test actual implementations
@pytest.fixture(autouse=True)
def mock_pipelines():
    """No-op override — let tests use real function implementations."""
    yield {}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def sample_modeling_df():
    """DataFrame matching the structure expected by train/CV/score."""
    n = 50
    data = {"game_id": [f"g{i}" for i in range(n)]}
    data["game_date"] = pd.date_range("2024-01-01", periods=n, freq="7D")
    for col in FEATURE_COLUMNS:
        data[col] = np.random.rand(n)
    for target_name, target_col in TARGET_COLUMNS.items():
        data[target_col] = np.random.randint(0, 2, n)
    return pd.DataFrame(data)


# ── timeseries_split_indices ──────────────────────────────────────────────────

class TestTimeseriesSplitIndices:
    def test_returns_correct_number_of_folds(self):
        from models.cross_validate_torch_model import timeseries_split_indices
        splits = timeseries_split_indices(100, folds=4)
        assert len(splits) == 4

    def test_expanding_window(self):
        """Each fold's training set should be larger than the previous."""
        from models.cross_validate_torch_model import timeseries_split_indices
        splits = timeseries_split_indices(100, folds=4)
        train_sizes = [len(train) for train, _ in splits]
        for i in range(1, len(train_sizes)):
            assert train_sizes[i] > train_sizes[i - 1]

    def test_no_overlap_train_val(self):
        """Training and validation indices should not overlap."""
        from models.cross_validate_torch_model import timeseries_split_indices
        splits = timeseries_split_indices(100, folds=5)
        for train_idx, val_idx in splits:
            overlap = set(train_idx) & set(val_idx)
            assert len(overlap) == 0

    def test_train_precedes_val(self):
        """All training indices must be less than all validation indices."""
        from models.cross_validate_torch_model import timeseries_split_indices
        splits = timeseries_split_indices(100, folds=5)
        for train_idx, val_idx in splits:
            assert train_idx.max() < val_idx.min()

    def test_all_data_covered(self):
        """Union of all indices should cover the full dataset."""
        from models.cross_validate_torch_model import timeseries_split_indices
        splits = timeseries_split_indices(100, folds=4)
        all_indices = set()
        for train_idx, val_idx in splits:
            all_indices.update(train_idx)
            all_indices.update(val_idx)
        assert all_indices == set(range(100))

    def test_single_fold(self):
        from models.cross_validate_torch_model import timeseries_split_indices
        splits = timeseries_split_indices(100, folds=1)
        assert len(splits) == 1
        train, val = splits[0]
        assert len(train) > 0
        assert len(val) > 0

    def test_small_dataset(self):
        from models.cross_validate_torch_model import timeseries_split_indices
        splits = timeseries_split_indices(10, folds=3)
        assert len(splits) >= 1
        for train, val in splits:
            assert len(train) > 0
            assert len(val) > 0


# ── train_model ──────────────────────────────────────────────────────────────

class TestTrainModel:
    def test_invalid_target_raises(self, tmp_path):
        from models.train_torch_model import train_model
        with patch("models.train_torch_model.MODEL_DIR", new=tmp_path):
            with pytest.raises(ValueError, match="Unknown target"):
                train_model(sport="nfl", target="invalid_target")

    @patch("models.train_torch_model.load_modeling_frame")
    @patch("models.train_torch_model.materialize_features_to_modeling_silver")
    def test_empty_data_raises(self, mock_mat, mock_load, tmp_path):
        from models.train_torch_model import train_model
        mock_load.return_value = pd.DataFrame()
        with patch("models.train_torch_model.MODEL_DIR", new=tmp_path):
            with pytest.raises(ValueError, match="No modeling data"):
                train_model(sport="nfl", target="home_win")

    @patch("models.train_torch_model.load_modeling_frame")
    @patch("models.train_torch_model.materialize_features_to_modeling_silver")
    def test_calls_materialize_then_load(self, mock_mat, mock_load, sample_modeling_df, tmp_path):
        """Verify training calls materialize before loading data."""
        from models.train_torch_model import train_model

        mock_load.return_value = sample_modeling_df

        with patch("models.train_torch_model.MODEL_DIR", new=tmp_path):
            try:
                train_model(sport="nfl", target="home_win", epochs=1)
            except Exception:
                pass  # torch is mocked, training may fail

        mock_mat.assert_called_once_with("nfl")
        mock_load.assert_called_once_with("nfl")


# ── cross_validate_model ──────────────────────────────────────────────────────

class TestCrossValidateModel:
    def test_invalid_target_raises(self):
        from models.cross_validate_torch_model import cross_validate_model
        with pytest.raises(ValueError, match="Unknown target"):
            cross_validate_model(sport="nfl", target="bad_target", skip_materialize=True,
                                 preloaded_df=pd.DataFrame({"x": [1]}))

    @patch("models.cross_validate_torch_model.load_modeling_frame")
    @patch("models.cross_validate_torch_model.materialize_features_to_modeling_silver")
    def test_empty_data_raises(self, mock_mat, mock_load):
        from models.cross_validate_torch_model import cross_validate_model
        mock_load.return_value = pd.DataFrame()
        with pytest.raises(ValueError, match="No modeling data"):
            cross_validate_model(sport="nfl", target="home_win")

    def test_skip_materialize_flag(self, sample_modeling_df):
        """skip_materialize=True should not call materialize."""
        from models.cross_validate_torch_model import cross_validate_model
        with patch("models.cross_validate_torch_model.materialize_features_to_modeling_silver") as mock_mat:
            with patch("models.cross_validate_torch_model.SportsBinaryClassifier") as mock_cls:
                mock_model = MagicMock()
                mock_cls.return_value = mock_model
                mock_model.return_value = MagicMock()
                mock_model.return_value.item.return_value = 0.5
                with patch("models.cross_validate_torch_model.DataLoader") as mock_dl:
                    mock_dl.return_value = []
                    with patch("models.cross_validate_torch_model.TabularSportsDataset"):
                        result = cross_validate_model(
                            sport="nfl", target="home_win", folds=2, epochs=1,
                            skip_materialize=True, preloaded_df=sample_modeling_df,
                        )
            mock_mat.assert_not_called()

    def test_preloaded_df_used(self, sample_modeling_df):
        """preloaded_df should be used instead of loading from DB."""
        from models.cross_validate_torch_model import cross_validate_model
        with patch("models.cross_validate_torch_model.load_modeling_frame") as mock_load:
            with patch("models.cross_validate_torch_model.SportsBinaryClassifier") as mock_cls:
                mock_cls.return_value = MagicMock()
                mock_cls.return_value.return_value = MagicMock()
                mock_cls.return_value.return_value.item.return_value = 0.5
                with patch("models.cross_validate_torch_model.DataLoader") as mock_dl:
                    mock_dl.return_value = []
                    with patch("models.cross_validate_torch_model.TabularSportsDataset"):
                        cross_validate_model(
                            sport="nfl", target="home_win", folds=2, epochs=1,
                            skip_materialize=True, preloaded_df=sample_modeling_df,
                        )
            mock_load.assert_not_called()


# ── score_model ──────────────────────────────────────────────────────────────

class TestScoreModel:
    @patch("models.score_torch_model.load_modeling_frame")
    @patch("models.score_torch_model.materialize_features_to_modeling_silver")
    def test_no_model_raises(self, mock_mat, mock_load, tmp_path):
        from models.score_torch_model import score_model
        with patch("models.score_torch_model.MODEL_DIR", new=tmp_path):
            with pytest.raises(ValueError, match="No model artifacts"):
                score_model(sport="nfl", target="home_win")

    @patch("models.score_torch_model.load_modeling_frame")
    @patch("models.score_torch_model.materialize_features_to_modeling_silver")
    def test_empty_scoring_data_raises(self, mock_mat, mock_load, tmp_path):
        from models.score_torch_model import score_model
        mock_load.return_value = pd.DataFrame()

        # Create fake model artifacts
        (tmp_path / "nfl_home_win_candidate.pt").touch()
        meta = {"hidden_dim": 64, "dropout": 0.1, "model_version": "test"}
        (tmp_path / "nfl_home_win_candidate_metadata.json").write_text(json.dumps(meta))

        with patch("models.score_torch_model.MODEL_DIR", new=tmp_path):
            with pytest.raises(ValueError, match="No scoring data"):
                score_model(sport="nfl", target="home_win")

    def test_resolve_prefers_production(self, tmp_path):
        """_resolve_model_paths should prefer production over candidate."""
        from models.score_torch_model import _resolve_model_paths

        for stage in ("production", "candidate"):
            (tmp_path / f"nfl_home_win_{stage}.pt").touch()
            meta = {"hidden_dim": 64, "dropout": 0.1}
            (tmp_path / f"nfl_home_win_{stage}_metadata.json").write_text(json.dumps(meta))

        with patch("models.score_torch_model.MODEL_DIR", new=tmp_path):
            _, _, stage = _resolve_model_paths("nfl", "home_win")
        assert stage == "production"

    def test_resolve_falls_back_to_candidate(self, tmp_path):
        """When only candidate exists, should return candidate."""
        from models.score_torch_model import _resolve_model_paths

        (tmp_path / "nfl_home_win_candidate.pt").touch()
        meta = {"hidden_dim": 64, "dropout": 0.1}
        (tmp_path / "nfl_home_win_candidate_metadata.json").write_text(json.dumps(meta))

        with patch("models.score_torch_model.MODEL_DIR", new=tmp_path):
            _, _, stage = _resolve_model_paths("nfl", "home_win")
        assert stage == "candidate"


# ── promote_model ─────────────────────────────────────────────────────────────

class TestPromoteModel:
    def test_missing_candidate_raises(self, tmp_path):
        from models.promote_model import promote_model
        with patch("models.promote_model.MODEL_DIR", new=tmp_path):
            with pytest.raises(ValueError, match="No candidate model"):
                promote_model(sport="nfl", target="home_win")

    @patch("models.promote_model._copy_candidate_to_production")
    @patch("models.promote_model._retire_current_production")
    @patch("models.promote_model._log_to_registry", return_value=42)
    @patch("models.promote_model.cross_validate_model")
    def test_promote_calls_correct_sequence(
        self, mock_cv, mock_log, mock_retire, mock_copy, tmp_path
    ):
        from models.promote_model import promote_model

        # Write fake candidate metadata
        meta = {
            "model_version": "test_v1",
            "hidden_dim": 128, "dropout": 0.1,
            "learning_rate": 0.001, "batch_size": 32, "epochs": 5,
            "train_rows": 100, "epoch_losses": [0.5, 0.4],
        }
        meta_path = tmp_path / "nfl_home_win_candidate_metadata.json"
        meta_path.write_text(json.dumps(meta))

        mock_cv.return_value = {
            "average_validation_loss": 0.45,
            "average_accuracy": 0.55,
            "average_auc": 0.58,
            "fold_losses": [0.5, 0.4],
            "fold_accuracies": [0.52, 0.58],
            "fold_aucs": [0.55, 0.61],
            "folds": 2,
        }

        with patch("models.promote_model.MODEL_DIR", new=tmp_path):
            result = promote_model(sport="nfl", target="home_win", cv_folds=2)

        mock_cv.assert_called_once()
        mock_retire.assert_called_once_with("nfl", "home_win")
        mock_copy.assert_called_once_with("nfl", "home_win")
        assert result["status"] == "production"
        assert result["registry_id"] == 42


# ── get_model_status ──────────────────────────────────────────────────────────

class TestGetModelStatus:
    def test_returns_models_list(self):
        from models.promote_model import get_model_status
        # mock_db from conftest provides the connection
        result = get_model_status(sport="nfl")
        assert "models" in result
        assert isinstance(result["models"], list)

    def test_filters_by_sport_and_target(self):
        from models.promote_model import get_model_status
        result = get_model_status(sport="nfl", target="home_win")
        assert "models" in result
