"""Ridge lineal para el motor ML — modelo v2 tras el protocolo de
simplificación (ver docs/BACKTEST_MOTOR_ML.md).

Forma cerrada con estandarización de features; lambda FIJO a priori (10.0,
el valor usado en el análisis de variantes en desarrollo — no se tunea).
Sin dependencias nuevas: numpy puro.
"""

import numpy as np
import pandas as pd

from quantbot.engines.ml_features import FEATURE_COLUMNS

RIDGE_LAMBDA = 10.0


class RidgeModel:
    def __init__(self, ridge_lambda: float = RIDGE_LAMBDA) -> None:
        self.ridge_lambda = ridge_lambda
        self._beta: np.ndarray | None = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        values = X[list(FEATURE_COLUMNS)].to_numpy(dtype=float)
        self._mean = values.mean(axis=0)
        self._std = values.std(axis=0)
        self._std[self._std < 1e-12] = 1.0
        standardized = (values - self._mean) / self._std
        design = np.column_stack([np.ones(len(standardized)), standardized])
        penalty = self.ridge_lambda * np.eye(design.shape[1])
        penalty[0, 0] = 0.0  # el intercepto no se penaliza
        self._beta = np.linalg.solve(
            design.T @ design + penalty, design.T @ y.to_numpy(dtype=float)
        )

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._beta is None:
            raise ValueError("RidgeModel sin entrenar")
        values = X[list(FEATURE_COLUMNS)].to_numpy(dtype=float)
        standardized = (values - self._mean) / self._std
        design = np.column_stack([np.ones(len(standardized)), standardized])
        return design @ self._beta
