from __future__ import annotations

import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SCORE_EQUATIONS = {
    "overall_score": r"\sum_k \alpha_k S_k,\quad \sum_k \alpha_k=1",
    "field_score": (
        r"2\sum_j w_j\max\!\left(0,\,100\left(1-\frac{e_j}{c_j}\right)\right)"
    ),
    "force_score": r"\frac{0.15\,S_{C_D} + 0.10\,S_{C_L}}{0.25}",
    "diagnostic_score": (
        r"\frac{0.15\,S_{\mathrm{velocity}} + 0.10\,S_{C_p}}{0.25}"
    ),
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class MetricDefinitionEquationTests(unittest.TestCase):
    def test_score_equations_use_published_mathjax_latex(self) -> None:
        manifest = load_json(ROOT / "leaderboard" / "manifest.json")
        equations = {
            definition["id"]: definition["equation"]
            for definition in manifest["metric_definitions"]
            if definition.get("id") in EXPECTED_SCORE_EQUATIONS
        }
        self.assertEqual(equations, EXPECTED_SCORE_EQUATIONS)

    def test_dataset_score_equations_match_leaderboard_definitions(self) -> None:
        for path in sorted((ROOT / "benchmark-specs").glob("*/submission-spec.json")):
            specification = load_json(path)
            equations = {
                definition["id"]: definition["equation"]
                for definition in specification["metrics"]
                if definition.get("id") in EXPECTED_SCORE_EQUATIONS
            }
            with self.subTest(dataset=specification["dataset_id"]):
                self.assertIn("overall_score", equations)
                self.assertEqual(
                    equations,
                    {metric_id: EXPECTED_SCORE_EQUATIONS[metric_id] for metric_id in equations},
                )

    def test_every_dataset_declares_the_same_overall_ranking_interface(self) -> None:
        for path in sorted((ROOT / "benchmark-specs").glob("*/submission-spec.json")):
            specification = load_json(path)
            with self.subTest(dataset=specification["dataset_id"]):
                self.assertEqual(
                    specification["ranking"],
                    {
                        "metric_id": "overall_score",
                        "direction": "higher",
                        "decimal_places": 1,
                        "rounding": "decimal_half_up",
                        "method": "competition",
                    },
                )
                composite = specification["overall_score_composite"]
                self.assertEqual(composite["metric_id"], "overall_score")
                self.assertEqual(composite["operation"], "weighted_component_scores")
                self.assertTrue(composite["components"])
                self.assertTrue(
                    math.isclose(
                        sum(component["weight"] for component in composite["components"]),
                        1.0,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                )
                metric_ids = {metric["id"] for metric in specification["metrics"]}
                self.assertTrue(
                    all(component["metric_id"] in metric_ids for component in composite["components"])
                )
