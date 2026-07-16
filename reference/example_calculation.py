"""Minimal example showing how participant-owned arrays use the references."""

from __future__ import annotations

import numpy as np

from reference.metrics import relative_l1, relative_l2, weighted_mae, weighted_mse, weighted_rmse


ground_truth = np.array([101325.0, 100980.0, 100410.0])
prediction = np.array([101300.0, 101020.0, 100500.0])
face_areas = np.array([0.10, 0.15, 0.08])

print(f"Relative L1: {relative_l1(ground_truth, prediction, face_areas):.6f}%")
print(f"Relative L2: {relative_l2(ground_truth, prediction, face_areas):.6f}%")
print(f"MAE: {weighted_mae(ground_truth, prediction, face_areas):.6f} Pa")
print(f"MSE: {weighted_mse(ground_truth, prediction, face_areas):.6f} Pa^2")
print(f"RMSE: {weighted_rmse(ground_truth, prediction, face_areas):.6f} Pa")
