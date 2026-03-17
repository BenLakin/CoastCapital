"""
pytorch_model.py — Neural network architecture for binary classification.

Defines ``SportsBinaryClassifier``, a fully-connected network with
configurable depth, batch normalization, and dropout.

Architecture (n_layers=3, hidden_dim=256):
  input_dim → 256 → [BN] → ReLU → Dropout
            → 128 → [BN] → ReLU → Dropout
            →  64 → [BN] → ReLU → Dropout
            →   1 → Sigmoid
"""

import torch
from torch import nn


class SportsBinaryClassifier(nn.Module):
    """Configurable binary classifier for tabular sports features.

    Parameters
    ----------
    input_dim:
        Number of input features (matches ``len(FEATURE_COLUMNS)``).
    hidden_dim:
        Width of the first hidden layer; subsequent layers halve.
    dropout:
        Dropout probability applied after each activation.
    n_layers:
        Number of hidden layers (2-4).  Each layer halves the previous width.
    batch_norm:
        If ``True``, apply batch normalization before each ReLU.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 128,
        dropout: float = 0.2,
        n_layers: int = 3,
        batch_norm: bool = True,
    ):
        super().__init__()

        layers = []
        in_dim = input_dim

        for i in range(n_layers):
            out_dim = max(hidden_dim >> i, 8)  # floor at 8 neurons
            layers.append(nn.Linear(in_dim, out_dim))
            if batch_norm:
                layers.append(nn.BatchNorm1d(out_dim))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
            in_dim = out_dim

        layers.append(nn.Linear(in_dim, 1))
        layers.append(nn.Sigmoid())

        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)
