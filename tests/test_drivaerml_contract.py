from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from scripts.validate_submission import sha256_file


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "benchmark-specs" / "drivaerml"
REMOVED_PHYSICAL_VOLUME_METRIC_IDS = {
    "volume_velocity_physical_rel_l2",
    "volume_pressure_physical_rel_l2",
    "drivaerml_volume_velocity_physical_mae",
    "drivaerml_volume_velocity_physical_rmse",
    "drivaerml_volume_pressure_physical_mae",
    "drivaerml_volume_pressure_physical_rmse",
}


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
            "drivaerml-native-v2-candidate",
        )
        support = self.specification["scoring_support"]
        self.assertEqual(support["status"], "owner_review_required")
        self.assertFalse(support["submissions_open"])
        self.assertTrue(support["owner_decisions_required"])
        self.assertEqual(
            support["source_release"]["revision"],
            "7a5c0948ce27be709b1116a3a190f806e7a8f79f",
        )
        self.assertEqual(
            self.specification["evaluation_reference_version"],
            "drivaerml-evaluator-v2-candidate",
        )
        self.assertEqual(
            support["dataset_evaluator_binding"]["evaluator_reference_version"],
            "drivaerml-evaluator-v2-candidate",
        )
        self.assertEqual(
            support["activation_gates"]["volume_field_weighting"],
            "complete_equal_native_cell_no_geometric_cell_volume_weights_required",
        )
        self.assertFalse(
            any(
                "volume" in decision and "weight" in decision
                for decision in support["owner_decisions_required"]
            )
        )

    def test_candidate_evidence_manifest_is_hash_complete_and_nonactivating(self) -> None:
        support = self.specification["scoring_support"]
        self.assertEqual(
            support["candidate_evidence_manifest_file"], "evidence/manifest.json"
        )
        manifest = load_json(DATASET_ROOT / support["candidate_evidence_manifest_file"])
        self.assertEqual(
            manifest["status"], "candidate_evidence_not_scoring_support"
        )
        self.assertFalse(manifest["official_submission_scoring_enabled"])
        self.assertFalse(manifest["owner_scientific_approval"])
        files = [item["file"] for item in manifest["artifacts"]]
        self.assertEqual(len(files), len(set(files)))
        for artifact in manifest["artifacts"]:
            with self.subTest(file=artifact["file"]):
                path = DATASET_ROOT / "evidence" / artifact["file"]
                self.assertTrue(path.is_file())
                self.assertEqual(artifact["sha256"], sha256_file(path))
                self.assertFalse(artifact["public_scoring_support_eligible"])

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

    def test_native_cell_support_uses_surface_areas_and_equal_volume_cells(self) -> None:
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
        self.assertEqual(volume["weighting"], "one_per_native_cell")
        self.assertFalse(volume["geometric_cell_volume_weights_required"])
        self.assertNotIn("primary_weighting", volume)
        self.assertNotIn("secondary_weighting", volume)
        all_case_evidence = volume["candidate_primary_validation_evidence"]
        self.assertEqual(
            all_case_evidence["file"],
            "evidence/native-volume-equal-cell-primary-all484.json",
        )
        self.assertTrue(all_case_evidence["equal_native_cell_weighting_exercised"])
        self.assertTrue(all_case_evidence["complete_all_484_cases"])
        self.assertEqual(
            all_case_evidence["artifact_schema"],
            "drivaerml-native-volume-equal-cell-primary-all-case-audit-v1",
        )
        self.assertTrue(all_case_evidence["legacy_unit_weight_vocabulary"])
        self.assertEqual(
            all_case_evidence["current_tool_aggregate_schema"],
            "drivaerml-native-volume-equal-cell-all-case-audit-v2",
        )
        self.assertIn("explicit_normalization", all_case_evidence["normalization_status"])

        metrics = {item["id"]: item for item in self.specification["metrics"]}
        self.assertEqual(len(metrics), 32)
        self.assertTrue(REMOVED_PHYSICAL_VOLUME_METRIC_IDS.isdisjoint(metrics))
        self.assertEqual(metrics["surface_pressure_rel_l2"]["weighting"], "surface_face_area")
        self.assertEqual(
            metrics["surface_pressure_equal_entity_rel_l2"]["weighting"],
            "surface_entities_equal",
        )
        self.assertEqual(metrics["volume_velocity_rel_l2"]["weighting"], "volume_cells_equal")
        self.assertEqual(
            metrics["drivaerml_volume_velocity_equal_entity_rmse"]["weighting"],
            "volume_cells_equal",
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

    def test_all_case_cp_candidate_evidence_is_bound_but_not_scoring_support(self) -> None:
        candidate = self.specification["scoring_support"]["profile_definition"][
            "candidate_cp_validation_evidence"
        ]
        path = DATASET_ROOT / candidate["file"]
        self.assertEqual(candidate["sha256"], sha256_file(path))
        self.assertEqual(candidate["case_count"], 484)
        self.assertEqual(candidate["probe_row_count"], 484 * 209)
        self.assertEqual(
            candidate["valid_mapping_count"] + candidate["invalid_mapping_count"],
            candidate["probe_row_count"],
        )
        self.assertEqual(candidate["invalid_mapping_count"], 875)
        self.assertEqual(candidate["omitted_row_count"], 0)
        self.assertFalse(candidate["public_scoring_support_eligible"])
        self.assertFalse(candidate["owner_visual_signoff"])

        evidence = load_json(path)
        self.assertEqual(evidence["case_count"], candidate["case_count"])
        self.assertEqual(
            evidence["aggregate"]["probe_row_count"],
            candidate["probe_row_count"],
        )
        self.assertEqual(
            evidence["aggregate"]["mapping_invalid_count"],
            candidate["invalid_mapping_count"],
        )
        self.assertFalse(evidence["public_scoring_support_eligible"])
        self.assertFalse(evidence["owner_visual_signoff_claimed"])

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
        self.assertEqual(len(expected_metrics), 32)
        self.assertTrue(
            REMOVED_PHYSICAL_VOLUME_METRIC_IDS.isdisjoint(expected_metrics)
        )
        self.assertEqual(dataset["submission_format"], "drivaerml_native_candidate_v2")
        manifest_metric_ids = {
            definition["id"] for definition in manifest["metric_definitions"]
        }
        self.assertTrue(
            {
                "drivaerml_volume_velocity_physical_mae",
                "drivaerml_volume_velocity_physical_rmse",
                "drivaerml_volume_pressure_physical_mae",
                "drivaerml_volume_pressure_physical_rmse",
            }.isdisjoint(manifest_metric_ids)
        )
        self.assertIn("volume_velocity_physical_rel_l2", manifest_metric_ids)
        self.assertIn("volume_pressure_physical_rel_l2", manifest_metric_ids)
        for submission_path in sorted((ROOT / "submissions" / "drivaerml").glob("*/submission.json")):
            submission = load_json(submission_path)
            with self.subTest(submission_id=submission["submission_id"]):
                self.assertEqual(submission["dataset_version"], self.specification["dataset_version"])
                self.assertEqual(set(submission["metric_values"]), expected_metrics)
                self.assertEqual(submission["approval"]["status"], "prototype")
                self.assertEqual(submission["metric_values"]["overall_score"], 0.0)

    def test_leaderboard_catalog_and_fixture_population_are_drivaer_specific(self) -> None:
        manifest = load_json(ROOT / "leaderboard" / "manifest.json")
        dataset = next(
            item for item in manifest["datasets"] if item["slug"] == "drivaerml"
        )
        dimensional = {
            item["id"]: item
            for item in manifest["metric_catalog"]["dimensional_fields"]
        }
        coefficients = {
            item["id"]: item
            for item in manifest["metric_catalog"]["coefficient_errors"]
        }

        # Generic catalog entries remain unchanged for the other datasets.
        self.assertEqual(dimensional["surface_pressure"]["unit"], "Pa")
        self.assertEqual(dimensional["surface_wall_shear"]["unit"], "Pa")
        self.assertEqual(dimensional["volume_pressure"]["unit"], "Pa")
        self.assertEqual(coefficients["c_drag"]["statistic"], "mae")
        self.assertEqual(coefficients["c_lift"]["statistic"], "mae")
        self.assertEqual(coefficients["c_pitch"]["statistic"], "mae")

        expected_dimensional = [
            "drivaerml_surface_pmeantrim_native_area",
            "drivaerml_surface_wallshearstressmeantrim_native_area",
            "drivaerml_volume_umeantrim_equal_cell",
            "drivaerml_volume_pmeantrim_equal_cell",
        ]
        expected_coefficients = [
            "drivaerml_cd_equal_case_rmse",
            "drivaerml_cl_equal_case_rmse",
            "drivaerml_cmpitch_equal_case_rmse",
        ]
        self.assertEqual(
            dataset["metrics"]["dimensional_fields"], expected_dimensional
        )
        self.assertEqual(
            dataset["metrics"]["coefficient_errors"], expected_coefficients
        )
        for metric_id in expected_dimensional[:2]:
            self.assertEqual(dimensional[metric_id]["unit"], "m^2/s^2")
            self.assertEqual(
                dimensional[metric_id]["weighting"],
                "native_surface_polygon_area",
            )
        self.assertEqual(
            dimensional["drivaerml_volume_umeantrim_equal_cell"]["unit"],
            "m/s",
        )
        self.assertEqual(
            dimensional["drivaerml_volume_pmeantrim_equal_cell"]["unit"],
            "m^2/s^2",
        )
        for metric_id in expected_dimensional[2:]:
            self.assertEqual(
                dimensional[metric_id]["weighting"],
                "equal_native_volume_cell",
            )
        for metric_id in expected_coefficients:
            self.assertEqual(coefficients[metric_id]["statistic"], "rmse")
            self.assertEqual(
                coefficients[metric_id]["aggregation"], "all_test_cases"
            )
            self.assertEqual(coefficients[metric_id]["weighting"], "cases_equal")

        selected_ids = set(expected_dimensional + expected_coefficients)
        for other in manifest["datasets"]:
            if other["slug"] == "drivaerml":
                continue
            other_ids = {
                metric_id
                for group in other.get("metrics", {}).values()
                for metric_id in group
            }
            self.assertTrue(selected_ids.isdisjoint(other_ids), other["slug"])

        fixture_paths = sorted(
            (ROOT / "submissions" / "drivaerml").glob("*/submission.json")
        )
        fixtures = [load_json(path) for path in fixture_paths]
        population = dataset["submission_population"]
        self.assertEqual(dataset["submission_count"], len(fixtures))
        self.assertEqual(population["feed_row_count"], len(fixtures))
        self.assertEqual(
            population["prototype_ineligible_fixture_count"], len(fixtures)
        )
        self.assertEqual(population["eligible_submission_count"], 0)
        self.assertEqual(population["scientific_result_count"], 0)
        self.assertEqual(
            population["submission_count_semantics"],
            "all_current_feed_rows_are_structural_prototype_fixtures_not_eligible_submissions",
        )
        self.assertTrue(
            all(item["approval"]["status"] == "prototype" for item in fixtures)
        )
        self.assertEqual(
            dataset["updated_at"], max(item["submitted_at"] for item in fixtures)
        )
        self.assertEqual(
            population["updated_at_semantics"],
            "latest_submitted_at_date_among_prototype_fixture_rows_not_a_contract_or_scientific_evidence_update",
        )


if __name__ == "__main__":
    unittest.main()
