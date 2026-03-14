"""
dataset.py — PyTorch Dataset wrapper for tabular sports data.

Converts a pandas DataFrame into a ``torch.utils.data.Dataset`` suitable
for ``DataLoader`` consumption during training and cross-validation.
"""

import torch
from torch.utils.data import Dataset


class TabularSportsDataset(Dataset):
    """Row-level dataset backed by a pandas DataFrame.

    Parameters
    ----------
    dataframe:
        Source DataFrame (must contain *feature_columns* and *target_column*).
    feature_columns:
        List of column names to use as model input features.
    target_column:
        Name of the binary target column (0/1).
    """

    def __init__(self, dataframe, feature_columns, target_column):
        self.features = torch.tensor(dataframe[feature_columns].values, dtype=torch.float32)
        self.targets = torch.tensor(dataframe[target_column].values, dtype=torch.float32).view(-1, 1)

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        return self.features[idx], self.targets[idx]
