from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from scripts.validate_submission import sha256_file


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "benchmark-specs" / "drivaerml"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class DrivAerMLContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.specification = load_json(DATASET_ROOT / "submission-spec.json")
        cls.profile = load_json(
            DATASET_ROOT / cls.specification["profile_definition"]["file"]
        )

    def test_candidate_is_concrete_but_closed(self) -> None:
        self.assertEqual(
            self.specification["dataset_version"],
            "drivaerml-native-v1-candidate",
        )
        support = self.specification["scoring_support"]
        self.assertEqual(support["status"], "owner_review_required")
        self.assertFalse(support["submissions_open"])
        self.assertTrue(support["owner_decisions_required"])
        self.assertEqual(
            support["source_release"]["revision"],
            "7a5c0948ce27be709b1116a3a190f806e7a8f79f",
        )

    def test_official_split_indexes_are_exact_owner_manifest_partitions(self) -> None:
        owner = load_json(DATASET_ROOT / "proposal" / "owner-published-splits.json")
        all_public_cases = set(owner["full_train"] + owner["full_val"] + owner["full_test"])
        self.assertEqual(len(all_public_cases), 484)
        for binding in self.specification["splits"]:
            split_id = binding["id"]
            split_path = DATASET_ROOT / binding["index_file"]
            split = load_json(split_path)
            with self.subTest(split_id=split_id):
                self.assertEqual(binding["sha256"], sha256_file(split_path))
                self.assertEqual(split["case_id_status"], "official")
                self.assertEqual(split["train_case_ids"], owner[f"{split_id}_train"])
                self.assertEqual(split["validation_case_ids"], owner[f"{split_id}_val"])
                self.assertEqual(split["case_ids"], owner[f"{split_id}_test"])
                combined = (
                    split["train_case_ids"]
                    + split["validation_case_ids"]
                    + split["case_ids"]
                )
                self.assertEqual(len(combined), len(set(combined)))
                self.assertTrue(set(combined).issubset(all_public_cases))
                if split_id not in {"medium", "scarce", "super_scarce"}:
                    self.assertEqual(set(combined), all_public_cases)
        for split_id in ("medium", "scarce", "super_scarce"):
            self.assertEqual(owner[f"{split_id}_val"], owner["full_val"])
            self.assertEqual(owner[f"{split_id}_test"], owner["full_test"])
            self.assertTrue(set(owner[f"{split_id}_train"]).issubset(owner["full_train"]))
        self.assertTrue(set(owner["super_scarce_train"]).issubset(owner["scarce_train"]))
        self.assertTrue(set(owner["scarce_train"]).issubset(owner["medium_train"]))

    def test_native_cell_support_and_dual_weighting_are_explicit(self) -> None:
        supports = {
            item["id"]: item
            for item in self.specification["scoring_support"]["public_supports"]
        }
        surface = supports["surface_native_cells"]
        self.assertEqual(surface["association"], "CellData")
        self.assertEqual(surface["arrays"], ["pMeanTrim", "wallShearStressMeanTrim"])
        self.assertEqual(
            surface["physical_weight_manifest"]["sha256"],
            "1401c7e80bd86f3aa2d640289db9b088ce1e0825327e18eeb1ab2852de04323e",
        )
        volume = supports["volume_native_cells"]
        self.assertEqual(volume["association"], "CellData")
        self.assertEqual(volume["arrays"], ["UMeanTrim", "pMeanTrim"])
        self.assertIn("optional .02.part", volume["transport_parts"])
        self.assertEqual(volume["primary_weighting"], "one_per_native_cell")
        self.assertIn("pending", volume["secondary_weighting"])

        metrics = {item["id"]: item for item in self.specification["metrics"]}
        self.assertEqual(metrics["surface_pressure_rel_l2"]["weighting"], "surface_face_area")
        self.assertEqual(
            metrics["surface_pressure_equal_entity_rel_l2"]["weighting"],
            "surface_entities_equal",
        )
        self.assertEqual(metrics["volume_velocity_rel_l2"]["weighting"], "volume_cells_equal")
        self.assertEqual(
            metrics["volume_velocity_physical_rel_l2"]["weighting"],
            "cell_volume",
        )

    def test_force_contract_uses_constant_reference_and_field_integration(self) -> None:
        support = self.specification["scoring_support"]
        force_truth = next(
            item
            for item in support["public_supports"]
            if item["id"] == "field_integrated_force_truth"
        )
        self.assertEqual(force_truth["authoritative_public_file"], "force_mom_constref_all.csv")
        self.assertEqual(
            force_truth["per_case_mirror"],
            "<case_id>/force_mom_constref_<run_number>.csv",
        )
        force = support["force_integration"]
        self.assertEqual(force["reference_area_m2"], 2.17)
        self.assertEqual(force["reference_length_m"], 2.78618)
        self.assertEqual(force["centre_of_rotation_m"], [1.40009, 0.0, -0.3176])
        self.assertEqual(
            force["ranked_reduction"],
            "separate_equal_case_RMSE_for_Cd_Cl_and_CmPitch",
        )
        self.assertEqual(force["dependent_axle_loads"]["composite_weight"], 0.0)

    def test_composite_is_the_unclipped_nine_component_proposal(self) -> None:
        composite = self.specification["overall_score_composite"]
        self.assertEqual(composite["status"], "pending_reference_baselines")
        self.assertTrue(composite["allow_negative_scores"])
        self.assertEqual(len(composite["components"]), 9)
        self.assertTrue(
            math.isclose(
                sum(item["weight"] for item in composite["components"]),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        )
        self.assertTrue(
            all(item["transform"] == "physics_null_skill" for item in composite["components"])
        )
        self.assertTrue(all("cap" not in item for item in composite["components"]))
        self.assertTrue(all("baseline_error" not in item for item in composite["components"]))
        self.assertEqual(
            [item["weight"] for item in composite["components"]],
            [0.15, 0.10, 0.15, 0.10, 0.15, 0.05, 0.05, 0.15, 0.10],
        )

    def test_autocfd5_profile_contract_is_fully_pinned(self) -> None:
        binding = self.specification["profile_definition"]
        profile_path = DATASET_ROOT / binding["file"]
        self.assertEqual(binding["sha256"], sha256_file(profile_path))
        pressure = self.profile["pressure_profiles"]
        self.assertEqual(pressure["unique_probe_count"], 209)
        self.assertEqual(pressure["panel_count"], 15)
        self.assertEqual(pressure["panel_membership_row_count"], 217)
        self.assertEqual(
            [station["sample_count"] for station in pressure["stations"]],
            [43, 22, 27, 11, 11, 4, 8, 10, 10, 6, 13, 13, 11, 8, 20],
        )
        velocity = self.profile["velocity_profiles"]
        self.assertEqual(velocity["line_count"], 16)
        self.assertEqual(velocity["sample_count_per_case"], 3756)
        self.assertEqual(
            [station["source_profile_id"] for station in velocity["stations"]],
            [
                "V1", "V2", "V3", "V4", "V5", "V6",
                "U1", "U2", "U3", "U4", "U5", "U6",
                "L1", "R1", "R2", "R3",
            ],
        )

    def test_leaderboard_and_prototypes_use_the_candidate_contract(self) -> None:
        manifest = load_json(ROOT / "leaderboard" / "manifest.json")
        dataset = next(item for item in manifest["datasets"] if item["slug"] == "drivaerml")
        self.assertEqual(dataset["scoring_support"], self.specification["scoring_support"])
        self.assertEqual(dataset["overall_score_composite"], self.specification["overall_score_composite"])
        self.assertEqual(
            [len(panel["stations"]) for panel in dataset["diagnostic_panels"]],
            [15, 16],
        )
        expected_metrics = {item["id"] for item in self.specification["metrics"]}
        for submission_path in sorted((ROOT / "submissions" / "drivaerml").glob("*/submission.json")):
            submission = load_json(submission_path)
            with self.subTest(submission_id=submission["submission_id"]):
                self.assertEqual(submission["dataset_version"], self.specification["dataset_version"])
                self.assertEqual(set(submission["metric_values"]), expected_metrics)
                self.assertEqual(submission["approval"]["status"], "prototype")
                self.assertEqual(submission["metric_values"]["overall_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
