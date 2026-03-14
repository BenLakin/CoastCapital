"""
pytorch_model.py — Neural network architecture for binary classification.

Defines ``SportsBinaryClassifier``, a 3-layer fully-connected network
with ReLU activations, dropout, and a sigmoid output.

Architecture:
  input_dim → hidden_dim → hidden_dim/2 → 1 (sigmoid)
"""

import torch
from torch import nn


class SportsBinaryClassifier(nn.Module):
    """Two-hidden-layer binary classifier for tabular sports features.

    Parameters
    ----------
    input_dim:
        Number of input features (matches ``len(FEATURE_COLUMNS)``).
    hidden_dim:
        Width of the first hidden layer; the second is ``hidden_dim // 2``.
    dropout:
        Dropout probability applied after each ReLU.
    """

    def __init__(self, input_dim, hidden_dim=128, dropout=0.1):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        return self.network(x)
