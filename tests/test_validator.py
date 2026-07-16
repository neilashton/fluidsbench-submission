from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_submission import ROOT, load_json, validate_submission_file


SOURCE = ROOT / "submissions" / "ahmedml" / "transolver"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class ValidatorTests(unittest.TestCase):
    def test_complete_example_is_valid(self) -> None:
        errors, stats = validate_submission_file(SOURCE / "submission.json")
        self.assertEqual(errors, [])
        self.assertEqual(stats["cases"], 50)
        self.assertGreater(stats["series"], 0)

    def test_missing_metric_and_inconsistent_training_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "transolver"
            shutil.copytree(SOURCE, destination)
            path = destination / "submission.json"
            submission = load_json(path)
            submission["metric_values"].pop("overall_score")
            submission["training_regime"] = "pretrained_zero_shot"
            submission["external_pretraining"] = False
            submission["target_data_used"] = "official_train"
            write_json(path, submission)
            errors, _ = validate_submission_file(path)
            joined = "\n".join(errors)
            self.assertIn("metric_values is missing: overall_score", joined)
            self.assertIn("pretrained_zero_shot requires external_pretraining=true", joined)
            self.assertIn("pretrained_zero_shot requires target_data_used=none", joined)

    def test_non_increasing_profile_coordinate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "transolver"
            shutil.copytree(SOURCE, destination)
            index_path = destination / "profiles" / "index.json"
            index = load_json(index_path)
            chunk_path = destination / "profiles" / index["chunks"][0]["file"]
            chunk = load_json(chunk_path)
            coordinates = chunk["cases"][0]["series"][0]["coordinate"]
            coordinates[1] = coordinates[0]
            write_json(chunk_path, chunk)
            index["chunks"][0]["sha256"] = hashlib.sha256(chunk_path.read_bytes()).hexdigest()
            write_json(index_path, index)
            errors, _ = validate_submission_file(destination / "submission.json")
            self.assertIn("coordinates must be strictly increasing", "\n".join(errors))

    def test_non_finite_profile_value_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "transolver"
            shutil.copytree(SOURCE, destination)
            index_path = destination / "profiles" / "index.json"
            index = load_json(index_path)
            chunk_path = destination / "profiles" / index["chunks"][0]["file"]
            chunk = load_json(chunk_path)
            chunk["cases"][0]["series"][0]["prediction"][0] = float("nan")
            write_json(chunk_path, chunk)
            index["chunks"][0]["sha256"] = hashlib.sha256(chunk_path.read_bytes()).hexdigest()
            write_json(index_path, index)
            errors, _ = validate_submission_file(destination / "submission.json")
            self.assertIn("predictions must be finite numbers", "\n".join(errors))

    def test_changed_evaluation_evidence_fails_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "transolver"
            shutil.copytree(SOURCE, destination)
            evidence_path = destination / "evaluation-evidence.json"
            evidence = load_json(evidence_path)
            evidence["notes"] = "Changed after submission.json recorded the evidence checksum."
            write_json(evidence_path, evidence)
            errors, _ = validate_submission_file(destination / "submission.json")
            self.assertIn("does not match evaluation.evidence_sha256", "\n".join(errors))

    def test_evaluation_command_must_match_hashed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "transolver"
            shutil.copytree(SOURCE, destination)
            path = destination / "submission.json"
            submission = load_json(path)
            submission["evaluation"]["command"] = "python evaluate.py --different-run"
            write_json(path, submission)
            errors, _ = validate_submission_file(path)
            self.assertIn("evaluation-evidence.json command must equal", "\n".join(errors))

    def test_approved_submission_requires_review_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "transolver"
            shutil.copytree(SOURCE, destination)
            path = destination / "submission.json"
            submission = load_json(path)
            submission["approval"] = {"status": "approved"}
            write_json(path, submission)
            errors, _ = validate_submission_file(path)
            joined = "\n".join(errors)
            self.assertIn("approved_by", joined)
            self.assertIn("approved_at", joined)
            self.assertIn("pull_request_url", joined)


if __name__ == "__main__":
    unittest.main()
