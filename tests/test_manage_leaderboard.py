from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import manage_leaderboard


class ManageLeaderboardTests(unittest.TestCase):
    def test_feed_row_pins_profile_index_bytes(self) -> None:
        path = manage_leaderboard.ROOT / "submissions" / "ahmedml" / "transolver" / "submission.json"
        manifest = {
            "data_release": {"status": "prototype_dummy_data"},
            "datasets": [{"name": "AhmedML"}],
        }
        with patch.object(manage_leaderboard, "submission_files", return_value=[path]):
            row = manage_leaderboard.source_rows_by_dataset(manifest)["AhmedML"][0]
        profile_index_path = manage_leaderboard.ROOT / row["profile_data"]["index_file"]
        self.assertEqual(row["profile_data"]["index_sha256"], manage_leaderboard.sha256_file(profile_index_path))

    def test_prototype_feed_contains_only_prototype_rows(self) -> None:
        paths = [
            manage_leaderboard.ROOT / "submissions" / "ahmedml" / submission_id / "submission.json"
            for submission_id in ("approved", "prototype", "pending")
        ]
        submissions = {
            path: {
                "submission_id": path.parent.name,
                "dataset": "AhmedML",
                "approval": {"status": path.parent.name} if path.parent.name != "pending" else {},
                "profile_data": {"index_file": "profiles/index.json"},
            }
            for path in paths
        }
        manifest = {
            "data_release": {"status": "prototype_dummy_data"},
            "datasets": [{"name": "AhmedML"}],
        }
        with (
            patch.object(manage_leaderboard, "submission_files", return_value=paths),
            patch.object(manage_leaderboard, "load_json", side_effect=lambda path: submissions[Path(path)]),
        ):
            rows = manage_leaderboard.source_rows_by_dataset(manifest)["AhmedML"]
        self.assertEqual([row["submission_id"] for row in rows], ["prototype"])

    def test_official_feed_contains_only_approved_rows(self) -> None:
        paths = [
            manage_leaderboard.ROOT / "submissions" / "ahmedml" / submission_id / "submission.json"
            for submission_id in ("approved", "prototype", "pending")
        ]
        submissions = {
            path: {
                "submission_id": path.parent.name,
                "dataset": "AhmedML",
                "approval": {"status": path.parent.name} if path.parent.name != "pending" else {},
                "profile_data": {"index_file": "profiles/index.json"},
            }
            for path in paths
        }
        manifest = {"data_release": {"status": "official"}, "datasets": [{"name": "AhmedML"}]}
        submissions[paths[0]]["approval"]["validation"] = {
            "evidence_file": "maintainer-validation.json",
            "evidence_sha256": "a" * 64,
        }
        validation = {
            "schema_version": "2.0",
            "status": "validated",
            "contract_version": "open-reproducibility-2.0",
            "reference_version": "v1",
            "case_set_id": "standard",
            "profile_ground_truth_release_id": "gt-v1",
            "profile_ground_truth_manifest_sha256": "d" * 64,
            "validated_by": "Maintainer",
            "validated_at": "2026-07-20T00:00:00Z",
            "validation_scope": "submitted_data_only",
            "model_execution": "not_performed",
            "metric_recomputation": "not_performed",
            "reviewed_submission_sha256": "b" * 64,
            "evaluation_evidence_sha256": "e" * 64,
            "profile_index_sha256": "c" * 64,
        }
        original_load = lambda path: (
            validation if Path(path).name == "maintainer-validation.json" else submissions[Path(path)]
        )
        with (
            patch.object(manage_leaderboard, "submission_files", return_value=paths),
            patch.object(manage_leaderboard, "load_json", side_effect=original_load),
        ):
            rows = manage_leaderboard.source_rows_by_dataset(manifest)["AhmedML"]
        self.assertEqual([row["submission_id"] for row in rows], ["approved"])
        self.assertEqual(rows[0]["maintainer_validation"]["schema_version"], "2.0")
        self.assertEqual(rows[0]["maintainer_validation"]["status"], "validated")
        self.assertEqual(rows[0]["maintainer_validation"]["reviewed_submission_sha256"], "b" * 64)
        self.assertEqual(rows[0]["maintainer_validation"]["profile_index_sha256"], "c" * 64)
        self.assertEqual(rows[0]["maintainer_validation"]["model_execution"], "not_performed")
        self.assertEqual(rows[0]["maintainer_validation"]["profile_ground_truth_release_id"], "gt-v1")
        self.assertTrue(rows[0]["maintainer_validation"]["evidence_path"].endswith("maintainer-validation.json"))

    def test_prototype_release_id_contains_feed_digest(self) -> None:
        manifest = {
            "datasets": [{"name": "AhmedML", "file": "leaderboard/datasets/ahmedml.json"}],
            "all_file": "leaderboard/all.json",
            "data_release": {"status": "prototype_dummy_data"},
        }
        rows = {"AhmedML": [{"submission_id": "example", "submitted_at": "2026-07-15"}]}
        with patch.object(manage_leaderboard, "source_rows_by_dataset", return_value=rows):
            updated, _, all_rows = manage_leaderboard.expected_outputs(manifest)
        digest = hashlib.sha256(manage_leaderboard.json_bytes(all_rows)).hexdigest()
        self.assertEqual(updated["data_release"]["feed_sha256"], digest)
        self.assertEqual(updated["data_release"]["id"], f"prototype-dev-2026-07-15-{digest[:12]}")

    def test_official_release_requires_archive_and_license_provenance(self) -> None:
        manifest = {"data_release": {"status": "official", "archive_url": None}}
        errors = manage_leaderboard.release_contract_errors(manifest)
        self.assertIn("an official data release requires an immutable HTTPS data_release.archive_url", errors)
        self.assertIn("an official data release requires a full immutable data_release.source_commit", errors)
        self.assertTrue(any("asset_base_url" in error for error in errors))
        self.assertTrue(any("profile_ground_truth" in error for error in errors))
        self.assertTrue(any("data_release.license" in error for error in errors))

    def test_prototype_release_may_have_no_archive(self) -> None:
        manifest = {
            "data_release": {
                "status": "prototype_dummy_data",
                "archive_url": None,
                "asset_base_url": "https://raw.githubusercontent.com/neilashton/fluidsbench-submission/dev/",
                "reproducibility_contract_version": "open-reproducibility-2.0",
                "profile_ground_truth": {
                    "release_id": "prototype-profile-ground-truth-1",
                    "manifest_url": "https://fluidsbench.org/assets/data/profile-ground-truth/manifest.json",
                    "manifest_sha256": "a" * 64,
                },
                "license": {
                    "spdx_id": "Apache-2.0",
                    "name": "Apache License 2.0",
                    "url": "https://www.apache.org/licenses/LICENSE-2.0",
                    "scope": "Leaderboard metadata and contributed profiles.",
                },
            }
        }
        self.assertEqual(manage_leaderboard.release_contract_errors(manifest), [])


if __name__ == "__main__":
    unittest.main()
