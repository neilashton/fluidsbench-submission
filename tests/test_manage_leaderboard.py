from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import manage_leaderboard


class ManageLeaderboardTests(unittest.TestCase):
    def test_public_feed_requires_approval_or_prototype_status(self) -> None:
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
        manifest = {"datasets": [{"name": "AhmedML"}]}
        with (
            patch.object(manage_leaderboard, "submission_files", return_value=paths),
            patch.object(manage_leaderboard, "load_json", side_effect=lambda path: submissions[Path(path)]),
        ):
            rows = manage_leaderboard.source_rows_by_dataset(manifest)["AhmedML"]
        self.assertEqual([row["submission_id"] for row in rows], ["approved", "prototype"])

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


if __name__ == "__main__":
    unittest.main()
