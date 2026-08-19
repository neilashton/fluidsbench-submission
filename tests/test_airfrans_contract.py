from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AIRFRANS_ROOT = ROOT / "benchmark-specs" / "airfrans"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AirfransContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.specification = load_json(AIRFRANS_ROOT / "submission-spec.json")
        binding = self.specification["profile_definition"]
        self.profile_definition_path = AIRFRANS_ROOT / binding["file"]
        self.profile_definition = load_json(self.profile_definition_path)

    def test_profile_definition_is_pinned_and_matches_submission_panel(self) -> None:
        binding = self.specification["profile_definition"]
        self.assertEqual(binding["id"], "airfrans-boundary-layer-v1")
        self.assertEqual(binding["sha256"], sha256_file(self.profile_definition_path))
        self.assertEqual(binding["status"], "owner_review_required")

        source = self.profile_definition["source_library"]
        self.assertEqual(source["version"], "0.1.5.1")
        self.assertEqual(source["commit"], "d35d4035d8ba6fa98c1a6662be925c2fc777610b")
        self.assertEqual(
            source["source_file_sha256"],
            "77a74740ad482fa99adf8829ebdc4c4fe38b85de24d30d30a0c07806b1306c17",
        )

        extraction = self.profile_definition["extraction"]
        expected_arguments = {
            "y": 0.1,
            "extrado": True,
            "direction": "normals",
            "local_frame": False,
            "resolution": 1000,
            "compressible": False,
        }
        for call_name, reference in (
            ("ground_truth_call_arguments", True),
            ("prediction_call_arguments", False),
        ):
            self.assertEqual(
                extraction[call_name],
                {**expected_arguments, "reference": reference},
            )
        self.assertEqual(extraction["resolution_segments"], 1000)
        self.assertEqual(extraction["sample_count"], 1001)

        panel = self.specification["profile_panels"][0]
        self.assertTrue(panel["required"])
        self.assertFalse(panel["allow_unlisted_stations"])
        self.assertEqual(panel["profile_definition_id"], binding["id"])
        self.assertEqual(panel["metric_id"], "velocity_profile_r2")
        self.assertEqual(panel["sample_count"], 1001)
        self.assertEqual(panel["coordinate_interval"], [0.0, 0.1])
        self.assertEqual(
            panel["station_ids"],
            [station["id"] for station in self.profile_definition["stations"]],
        )
        self.assertEqual(
            panel["quantity_ids"],
            [quantity["id"] for quantity in self.profile_definition["quantities"]],
        )

    def test_split_ids_are_bound_to_the_official_manifest_member(self) -> None:
        expected_manifest_keys = {
            "full": "full_test",
            "scarce": "full_test",
            "reynolds_extrapolation": "reynolds_test",
            "aoa_extrapolation": "aoa_test",
        }
        spec_splits = {entry["id"]: entry for entry in self.specification["splits"]}
        for split_id, manifest_key in expected_manifest_keys.items():
            with self.subTest(split=split_id):
                entry = spec_splits[split_id]
                split_path = AIRFRANS_ROOT / entry["index_file"]
                split = load_json(split_path)
                source = split["source"]
                self.assertEqual(entry["sha256"], sha256_file(split_path))
                self.assertEqual(source["manifest_member"], "Dataset/manifest.json")
                self.assertEqual(
                    source["manifest_sha256"],
                    "3d1320005bcf3d94df80df2bf8338dd6ce6d394c6beafa14849b4ce1de7def13",
                )
                self.assertEqual(source["manifest_key"], manifest_key)
                self.assertEqual(
                    source["loader_commit"],
                    "d35d4035d8ba6fa98c1a6662be925c2fc777610b",
                )
                self.assertEqual(
                    source["loader_file_sha256"],
                    "21fee60ef9451fa5eb2634ccc80125acac2e387a1ba15e75ecc7ae5ec64c0675",
                )
                self.assertEqual(
                    source["case_ids_sha256"],
                    canonical_json_sha256(split["case_ids"]),
                )
                self.assertEqual(split["case_count"], len(split["case_ids"]))
        self.assertEqual(
            load_json(AIRFRANS_ROOT / spec_splits["full"]["index_file"])["case_ids"],
            load_json(AIRFRANS_ROOT / spec_splits["scarce"]["index_file"])["case_ids"],
        )

    def test_prototype_profiles_exercise_every_required_series(self) -> None:
        panel = self.specification["profile_panels"][0]
        expected_series = {
            (panel["id"], station_id, quantity_id)
            for station_id in panel["station_ids"]
            for quantity_id in panel["quantity_ids"]
        }
        fixture_root = ROOT / "submissions" / "airfrans"
        for submission_path in sorted(fixture_root.glob("*/submission.json")):
            with self.subTest(submission=submission_path.parent.name):
                submission = load_json(submission_path)
                self.assertEqual(submission["approval"]["status"], "prototype")
                index = load_json(submission_path.parent / submission["profile_data"]["index_file"])
                for chunk_entry in index["chunks"]:
                    chunk = load_json(submission_path.parent / "profiles" / chunk_entry["file"])
                    for case in chunk["cases"]:
                        observed = {
                            (series["panel_id"], series["station_id"], series["quantity_id"])
                            for series in case["series"]
                        }
                        self.assertEqual(observed, expected_series)
                        self.assertTrue(
                            all(series["coordinate"] == [0.0, 0.05, 0.1] for series in case["series"])
                        )

    def test_leaderboard_panel_matches_the_airfrans_contract(self) -> None:
        manifest = load_json(ROOT / "leaderboard" / "manifest.json")
        dataset = next(item for item in manifest["datasets"] if item["slug"] == "airfrans")
        self.assertEqual(dataset["profile_definition"], self.specification["profile_definition"])
        self.assertEqual([panel["id"] for panel in dataset["diagnostic_panels"]], ["velocity_profiles"])
        panel = dataset["diagnostic_panels"][0]
        self.assertEqual(panel["profile_definition_id"], "airfrans-boundary-layer-v1")
        self.assertEqual(
            [quantity["id"] for quantity in panel["quantities"]],
            ["velocity_x_ratio", "velocity_y_ratio"],
        )
        self.assertEqual(
            [station["id"] for station in panel["stations"]],
            ["upper_x_0_25c", "upper_x_0_50c", "upper_x_0_75c", "upper_x_0_95c"],
        )
        self.assertTrue(panel["required"])
        self.assertFalse(panel["allow_unlisted_stations"])


if __name__ == "__main__":
    unittest.main()
