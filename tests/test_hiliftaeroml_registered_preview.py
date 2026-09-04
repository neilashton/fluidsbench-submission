from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts import manage_leaderboard
from scripts import validate_submission as validator

ROOT = Path(__file__).resolve().parents[1]
SUBMISSION = (
    ROOT
    / "submissions"
    / "hiliftaeroml"
    / "hiliftaeroml-transolver-full360-candidate-v1"
    / "submission.json"
)


def manifest() -> dict:
    return validator.manifest_with_benchmark_contract(
        validator.load_json(validator.MANIFEST_PATH)
    )


class HiLiftRegisteredPreviewTests(unittest.TestCase):
    def test_passes_without_hidden_score_recomputation(self) -> None:
        current_manifest = manifest()
        submission = validator.load_json(SUBMISSION)
        binding = validator.registered_hiliftaeroml_preview(
            SUBMISSION,
            submission,
            current_manifest,
        )
        self.assertIsNotNone(binding)

        with patch.object(
            validator,
            "score_hilift_compact_profile_directory",
            side_effect=AssertionError(
                "ordinary preview validation loaded hidden truth"
            ),
        ):
            errors, stats = validator.validate_submission_file(
                SUBMISSION,
                current_manifest,
            )

        self.assertEqual(errors, [])
        self.assertEqual(stats, {"cases": 360, "series": 5400})

    def test_registration_is_exact_and_lifecycle_bound(self) -> None:
        current_manifest = manifest()
        submission = validator.load_json(SUBMISSION)

        changed_submission = deepcopy(submission)
        changed_submission["approval"] = {"status": "prototype"}
        self.assertIsNone(
            validator.registered_hiliftaeroml_preview(
                SUBMISSION,
                changed_submission,
                current_manifest,
            )
        )
        self.assertIsNone(
            validator.registered_hiliftaeroml_preview(
                ROOT / "outside" / "submission.json",
                submission,
                current_manifest,
            )
        )

        official_manifest = deepcopy(current_manifest)
        official_manifest["data_release"]["status"] = "official"
        self.assertIsNone(
            validator.registered_hiliftaeroml_preview(
                SUBMISSION,
                submission,
                official_manifest,
            )
        )

        receipt_path = ROOT / validator.HILIFT_REGISTERED_PREVIEW_RECORD_PATH
        original_load = validator.load_json
        changed_receipt = deepcopy(original_load(receipt_path))
        changed_receipt["activation"]["owner_approval_complete"] = True

        def load_with_changed_receipt(path: Path) -> object:
            if Path(path).resolve() == receipt_path.resolve():
                return changed_receipt
            return original_load(Path(path))

        with patch.object(
            validator,
            "load_json",
            side_effect=load_with_changed_receipt,
        ):
            self.assertIsNone(
                validator.registered_hiliftaeroml_preview(
                    SUBMISSION,
                    submission,
                    current_manifest,
                )
            )

    def test_feed_replaces_prototypes_with_one_ineligible_reference(self) -> None:
        rows = manage_leaderboard.source_rows_by_dataset(manifest())["HiLiftAeroML"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            row["submission_id"],
            "hiliftaeroml-transolver-full360-candidate-v1",
        )
        self.assertEqual(row["split_id"], "full")
        self.assertEqual(row["record_type"], "pre_release_reference")
        self.assertIsNone(row.get("approval"))

        eligibility = manage_leaderboard.claim_eligibility(
            "prototype_dummy_data",
            row,
        )
        self.assertFalse(eligibility["academic_citation"])
        self.assertFalse(eligibility["promotion"])
        self.assertEqual(eligibility["reason_code"], "pre_release_reference")
        self.assertIn("HiLiftAeroML", eligibility["reason"])

        official_manifest = manifest()
        official_manifest["data_release"]["status"] = "official"
        self.assertEqual(
            manage_leaderboard.source_rows_by_dataset(official_manifest)[
                "HiLiftAeroML"
            ],
            [],
        )

    def test_generated_feed_has_one_full_split_rank(self) -> None:
        rows = validator.load_json(
            ROOT / "leaderboard" / "datasets" / "hiliftaeroml.json"
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            row["submission_id"],
            "hiliftaeroml-transolver-full360-candidate-v1",
        )
        self.assertEqual(row["record_type"], "pre_release_reference")
        self.assertEqual(row["ranking"]["rank"], 1)
        self.assertEqual(row["ranking"]["ranked_result_count"], 1)
        self.assertEqual(row["ranking"]["display_value"], "69.1")
        self.assertFalse(row["claim_eligibility"]["academic_citation"])
        self.assertFalse(row["claim_eligibility"]["promotion"])

    def test_cannot_be_approved_while_support_is_closed(self) -> None:
        errors = manage_leaderboard.approve_submission(
            SUBMISSION,
            validated_by="Maintainer",
            validated_at="2026-09-03T12:00:00Z",
            approved_by="Dataset owner",
            approved_at="2026-09-03",
            pull_request_url=(
                "https://github.com/neilashton/fluidsbench-submission/pull/21"
            ),
            dry_run=True,
            update_existing=False,
            rebuild_feeds=False,
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("approval is closed", errors[0])


if __name__ == "__main__":
    unittest.main()
