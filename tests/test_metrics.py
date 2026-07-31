from __future__ import annotations

import unittest

import numpy as np

from reference.metrics import (
    aggregate_case_metrics,
    field_rrmse,
    r2_score,
    relative_l1,
    relative_l2,
    scalar_rrmse,
    weighted_mae,
    weighted_mse,
    weighted_rmse,
)
from reference.scores import arithmetic_mean, composite_overall_score, legacy_aero_scores


class MetricTests(unittest.TestCase):
    def setUp(self) -> None:
        self.truth = np.array([1.0, 2.0, 4.0])
        self.prediction = np.array([2.0, 2.0, 1.0])
        self.weights = np.array([1.0, 2.0, 1.0])

    def test_weighted_errors(self) -> None:
        self.assertAlmostEqual(weighted_mae(self.truth, self.prediction, self.weights), 1.0)
        self.assertAlmostEqual(weighted_mse(self.truth, self.prediction, self.weights), 2.5)
        self.assertAlmostEqual(weighted_rmse(self.truth, self.prediction, self.weights), np.sqrt(2.5))
        self.assertAlmostEqual(relative_l1(self.truth, self.prediction, self.weights), 100.0 / 9.0 * 4.0)
        self.assertAlmostEqual(relative_l2(self.truth, self.prediction, self.weights), 100.0 * np.sqrt(10.0 / 25.0))

    def test_r2_uses_weighted_mean(self) -> None:
        expected = 1.0 - 10.0 / 4.75
        self.assertAlmostEqual(r2_score(self.truth, self.prediction, self.weights), expected)

    def test_rrmse(self) -> None:
        truth = np.array([[1.0, 2.0], [2.0, 4.0]])
        prediction = np.array([[2.0, 2.0], [2.0, 6.0]])
        self.assertAlmostEqual(field_rrmse(truth, prediction), np.sqrt((0.125 + 0.125) / 2.0))
        self.assertAlmostEqual(scalar_rrmse([1.0, 2.0], [2.0, 2.0]), np.sqrt(0.5))

    def test_macro_average(self) -> None:
        cases = [([1.0], [2.0], None), ([10.0], [12.0], None)]
        self.assertAlmostEqual(aggregate_case_metrics(cases, weighted_mae), 1.5)

    def test_score_reductions(self) -> None:
        values = {
            "surface_pressure_rel_l2": 7.5,
            "surface_wall_shear_rel_l2": 10.0,
            "volume_velocity_rel_l2": 6.0,
            "volume_pressure_rel_l2": 7.5,
            "cd_r2": 0.9,
            "cl_r2": 0.8,
            "velocity_profile_r2": 0.7,
            "cp_cut_r2": 0.6,
        }
        scores = legacy_aero_scores(values)
        self.assertAlmostEqual(scores["field_score"], 50.0)
        self.assertAlmostEqual(scores["force_score"], 86.0)
        self.assertAlmostEqual(scores["diagnostic_score"], 66.0)
        self.assertAlmostEqual(scores["overall_score"], 63.0)
        flow_domain_values = dict(values)
        flow_domain_values["flow_domain_velocity_rel_l2"] = flow_domain_values.pop("volume_velocity_rel_l2")
        flow_domain_values["flow_domain_pressure_rel_l2"] = flow_domain_values.pop("volume_pressure_rel_l2")
        self.assertEqual(legacy_aero_scores(flow_domain_values), scores)
        self.assertAlmostEqual(arithmetic_mean({"a": 1.0, "b": 3.0}, ["a", "b"]), 2.0)

    def test_dataset_declared_composite_score(self) -> None:
        declaration = {
            "operation": "weighted_component_scores",
            "components": [
                {"metric_id": "error", "weight": 0.75, "transform": "bounded_error", "cap": 20.0},
                {"metric_id": "quality", "weight": 0.25, "transform": "bounded_quality"},
            ],
        }
        self.assertAlmostEqual(
            composite_overall_score({"error": 10.0, "quality": 0.8}, declaration),
            57.5,
        )
        self.assertAlmostEqual(
            composite_overall_score({"error": 40.0, "quality": 2.0}, declaration),
            25.0,
        )

        invalid = dict(declaration)
        invalid["components"] = [dict(declaration["components"][0], weight=0.5)]
        with self.assertRaises(ValueError):
            composite_overall_score({"error": 10.0}, invalid)

    def test_invalid_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            relative_l2([0.0], [1.0])
        with self.assertRaises(ValueError):
            r2_score([1.0, 1.0], [1.0, 1.0])
        with self.assertRaises(ValueError):
            weighted_mae([1.0], [1.0], [-1.0])
        with self.assertRaises(ValueError):
            weighted_mae([np.nan], [1.0])


if __name__ == "__main__":
    unittest.main()
