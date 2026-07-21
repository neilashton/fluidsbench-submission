from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.validate_submission import (
    ROOT,
    canonical_json_sha256,
    load_json,
    sha256_file,
    validate_submission_file,
)


SOURCE = ROOT / "submissions" / "ahmedml" / "transolver"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def make_real_package(destination: Path, *, approved: bool = False) -> Path:
    """Convert the copied prototype fixture into an open-track package for lifecycle tests."""

    shutil.copytree(SOURCE, destination)
    path = destination / "submission.json"
    submission = load_json(path)
    commit = "a" * 40
    submission["code_url"] = "https://example.org/open-model-code"
    submission["evaluation"]["code_revision"] = commit
    submission["reproducibility"] = {
        "contract_version": "open-reproducibility-1.0",
        "access": "public",
        "public_test_data_use": "evaluation_only",
        "result_data_license_spdx": "CC-BY-4.0",
        "code": {
            "repository_url": submission["code_url"],
            "commit": commit,
            "license_spdx": "Apache-2.0",
        },
        "model_artifact": {
            "url": "https://example.org/model-v1.tar.zst",
            "sha256": "b" * 64,
            "license_spdx": "Apache-2.0",
        },
        "environment": {
            "kind": "lockfile",
            "url": "https://example.org/model-v1.lock",
            "sha256": "c" * 64,
        },
        "replay_instructions_url": "https://example.org/open-model-code/replay-v1",
    }
    submission.pop("approval", None)

    evidence_path = destination / "evaluation-evidence.json"
    evidence = load_json(evidence_path)
    evidence["status"] = "submitted_evaluation"
    evidence["code_revision"] = commit
    write_json(evidence_path, evidence)
    submission["evaluation"]["evidence_sha256"] = sha256_file(evidence_path)

    if approved:
        profile_sha256 = sha256_file(destination / "profiles" / "index.json")
        replay = {
            "schema_version": "1.0",
            "contract_version": "open-reproducibility-1.0",
            "submission_id": submission["submission_id"],
            "dataset_id": submission["dataset_id"],
            "split_id": submission["split_id"],
            "reference_version": submission["evaluation"]["reference_version"],
            "replayed_by": "Independent Maintainer",
            "replayed_at": "2026-07-20T12:00:00Z",
            "independence": {
                "independent_of_submitter": True,
                "conflict_of_interest_disclosure": "No conflict of interest declared.",
            },
            "code": {
                "repository_url": submission["reproducibility"]["code"]["repository_url"],
                "commit": commit,
            },
            "model_artifact": {
                "url": submission["reproducibility"]["model_artifact"]["url"],
                "sha256": submission["reproducibility"]["model_artifact"]["sha256"],
            },
            "environment": submission["reproducibility"]["environment"],
            "command": submission["evaluation"]["command"],
            "status": "reproduced",
            "metric_values": submission["metric_values"],
            "metric_abs_tolerance": 0.0,
            "reviewed_submission_sha256": canonical_json_sha256(submission),
            "submitted_profile_index_sha256": profile_sha256,
            "replayed_profile_index_sha256": profile_sha256,
        }
        replay_path = destination / "maintainer-replay.json"
        write_json(replay_path, replay)
        submission["approval"] = {
            "status": "approved",
            "approved_by": "Approving Maintainer",
            "approved_at": "2026-07-20",
            "pull_request_url": "https://github.com/fluidsbench/fluidsbench-submission/pull/123",
            "replay": {
                "evidence_file": "maintainer-replay.json",
                "evidence_sha256": sha256_file(replay_path),
            },
        }
    write_json(path, submission)
    return path


def official_contract_load_json(path: Path) -> object:
    """Make the prototype AhmedML owner contract official without modifying source fixtures."""

    value = load_json(Path(path))
    path = Path(path)
    if path == ROOT / "benchmark-specs" / "ahmedml" / "submission-spec.json":
        value["status"] = "official"
        for split in value["splits"]:
            if split["id"] == "full":
                split["case_id_status"] = "official"
    elif path == ROOT / "benchmark-specs" / "ahmedml" / "splits" / "full.json":
        value["case_id_status"] = "official"
    return value


def without_storage_error(errors: list[str]) -> list[str]:
    return [error for error in errors if "submission.json must be stored at" not in error]


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

    def test_real_contributor_package_requires_open_reproducibility_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "transolver"
            shutil.copytree(SOURCE, destination)
            evidence_path = destination / "evaluation-evidence.json"
            evidence = load_json(evidence_path)
            evidence["status"] = "submitted_evaluation"
            write_json(evidence_path, evidence)
            path = destination / "submission.json"
            submission = load_json(path)
            submission.pop("approval", None)
            submission["evaluation"]["evidence_sha256"] = sha256_file(evidence_path)
            write_json(path, submission)
            errors, _ = validate_submission_file(path, contributor_stage=True)
            self.assertIn("requires reproducibility.contract_version", "\n".join(errors))

    def test_open_package_is_valid_but_remains_unapproved_at_contributor_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver")
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path, contributor_stage=True)
            self.assertEqual(without_storage_error(errors), [])
            self.assertNotIn("approval", load_json(path))

    def test_approved_package_requires_and_verifies_independent_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver", approved=True)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path)
            self.assertEqual(without_storage_error(errors), [])

    def test_contributor_stage_rejects_maintainer_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver", approved=True)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path, contributor_stage=True)
            self.assertIn("contributor-stage submissions cannot set approval.status=approved", "\n".join(errors))

    def test_contributor_stage_rejects_prototype_packages(self) -> None:
        errors, _ = validate_submission_file(SOURCE / "submission.json", contributor_stage=True)
        joined = "\n".join(errors)
        self.assertIn("contributor-stage packages require evaluation-evidence.status=submitted_evaluation", joined)
        self.assertIn("contributors must leave approval absent", joined)

    def test_replay_metric_difference_fails_declared_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver", approved=True)
            destination = path.parent
            replay_path = destination / "maintainer-replay.json"
            replay = load_json(replay_path)
            replay["metric_values"]["overall_score"] += 0.01
            write_json(replay_path, replay)
            submission = load_json(path)
            submission["approval"]["replay"]["evidence_sha256"] = sha256_file(replay_path)
            write_json(path, submission)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path)
            self.assertIn("replay metric overall_score differs", "\n".join(errors))

    def test_submission_metadata_cannot_change_after_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver", approved=True)
            submission = load_json(path)
            submission["institution"] = "Changed after independent review"
            write_json(path, submission)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path)
            self.assertIn("reviewed_submission_sha256 does not match", "\n".join(errors))

    def test_submitter_cannot_attest_their_own_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver", approved=True)
            destination = path.parent
            replay_path = destination / "maintainer-replay.json"
            replay = load_json(replay_path)
            replay["replayed_by"] = load_json(path)["submitter_name"]
            write_json(replay_path, replay)
            submission = load_json(path)
            submission["approval"]["replay"]["evidence_sha256"] = sha256_file(replay_path)
            write_json(path, submission)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path)
            self.assertIn("someone other than submitter_name", "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
