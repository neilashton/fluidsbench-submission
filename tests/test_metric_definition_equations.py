from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SCORE_EQUATIONS = {
    "overall_score": (
        r"0.50\,S_{\mathrm{field}} + 0.25\,S_{\mathrm{force}}"
        r" + 0.25\,S_{\mathrm{profile}}"
    ),
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
            if equations:
                with self.subTest(dataset=specification["dataset_id"]):
                    self.assertEqual(equations, EXPECTED_SCORE_EQUATIONS)
