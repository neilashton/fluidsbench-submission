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
    schema_errors,
    sha256_file,
    validate_submission_file,
)


SOURCE = ROOT / "submissions" / "ahmedml" / "transolver"
V2_TEMPLATE = ROOT / "examples" / "v2-template"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def make_real_package(destination: Path, *, approved: bool = False) -> Path:
    """Convert the copied prototype fixture into an open-track package for lifecycle tests."""

    shutil.copytree(SOURCE, destination)
    path = destination / "submission.json"
    submission = load_json(path)
    commit = "a" * 40
    submission["$schema"] = "https://fluidsbench.org/schemas/v2/submission.schema.json"
    submission["schema_version"] = "2.0"
    ground_truth = load_json(ROOT / "leaderboard" / "manifest.json")["data_release"]["profile_ground_truth"]
    submission["profile_data"]["profile_ground_truth_release_id"] = ground_truth["release_id"]
    submission["profile_data"]["profile_ground_truth_manifest_sha256"] = ground_truth["manifest_sha256"]
    submission["code_url"] = "https://example.org/open-model-code"
    submission["evaluation"]["code_revision"] = commit
    submission["reproducibility"] = {
        "contract_version": "open-reproducibility-2.0",
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
        "artifact_documentation_url": "https://example.org/open-model-code/artifacts-v1",
    }
    submission.pop("approval", None)

    evidence_path = destination / "evaluation-evidence.json"
    evidence = load_json(evidence_path)
    evidence["schema_version"] = "2.0"
    evidence["status"] = "submitted_evaluation"
    evidence["code_revision"] = commit
    evidence["dataset_version"] = submission["dataset_version"]
    evidence["split_sha256"] = submission["split_sha256"]
    evidence["case_set_id"] = submission["case_set_id"]
    evidence["profile_ground_truth_release_id"] = ground_truth["release_id"]
    evidence["profile_ground_truth_manifest_sha256"] = ground_truth["manifest_sha256"]
    write_json(evidence_path, evidence)
    submission["evaluation"]["evidence_sha256"] = sha256_file(evidence_path)

    if approved:
        profile_sha256 = sha256_file(destination / "profiles" / "index.json")
        validation = {
            "schema_version": "2.0",
            "contract_version": "open-reproducibility-2.0",
            "submission_id": submission["submission_id"],
            "dataset_id": submission["dataset_id"],
            "split_id": submission["split_id"],
            "case_set_id": submission["case_set_id"],
            "reference_version": submission["evaluation"]["reference_version"],
            "profile_ground_truth_release_id": ground_truth["release_id"],
            "profile_ground_truth_manifest_sha256": ground_truth["manifest_sha256"],
            "validated_by": "Maintainer",
            "validated_at": "2026-07-20T12:00:00Z",
            "status": "validated",
            "validation_scope": "submitted_data_only",
            "model_execution": "not_performed",
            "metric_recomputation": "not_performed",
            "reviewed_submission_sha256": canonical_json_sha256(submission),
            "evaluation_evidence_sha256": submission["evaluation"]["evidence_sha256"],
            "profile_index_sha256": profile_sha256,
        }
        validation_path = destination / "maintainer-validation.json"
        write_json(validation_path, validation)
        submission["approval"] = {
            "status": "approved",
            "approved_by": "Approving Maintainer",
            "approved_at": "2026-07-20",
            "pull_request_url": "https://github.com/fluidsbench/fluidsbench-submission/pull/123",
            "validation": {
                "evidence_file": "maintainer-validation.json",
                "evidence_sha256": sha256_file(validation_path),
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
    def test_v2_template_files_match_their_schemas_and_hashes(self) -> None:
        submission = load_json(V2_TEMPLATE / "submission.json")
        evidence = load_json(V2_TEMPLATE / "evaluation-evidence.json")
        validation = load_json(V2_TEMPLATE / "maintainer-validation.json")
        profile_index = load_json(V2_TEMPLATE / "profiles" / "index.json")
        profile_chunk = load_json(V2_TEMPLATE / "profiles" / "chunk-000.json")

        self.assertNotIn("approval", submission)
        self.assertEqual(schema_errors(submission, "submission.schema.json", schema_version="v2"), [])
        submission_with_null_approval = dict(submission)
        submission_with_null_approval["approval"] = None
        self.assertTrue(
            any(
                "None is not of type 'object'" in error
                for error in schema_errors(
                    submission_with_null_approval,
                    "submission.schema.json",
                    schema_version="v2",
                )
            )
        )
        self.assertEqual(schema_errors(evidence, "evaluation-evidence.schema.json", schema_version="v2"), [])
        self.assertEqual(
            schema_errors(validation, "maintainer-validation.schema.json", schema_version="v2"),
            [],
        )
        self.assertEqual(schema_errors(profile_index, "profile-index.schema.json"), [])
        self.assertEqual(schema_errors(profile_chunk, "profile-chunk.schema.json"), [])

        chunk_path = V2_TEMPLATE / "profiles" / profile_index["chunks"][0]["file"]
        self.assertEqual(profile_index["chunks"][0]["sha256"], sha256_file(chunk_path))
        profile_index_sha256 = sha256_file(V2_TEMPLATE / "profiles" / "index.json")
        self.assertEqual(evidence["profile_index_sha256"], profile_index_sha256)
        self.assertEqual(submission["evaluation"]["evidence_sha256"], sha256_file(V2_TEMPLATE / "evaluation-evidence.json"))
        self.assertEqual(validation["profile_index_sha256"], profile_index_sha256)
        self.assertEqual(validation["evaluation_evidence_sha256"], submission["evaluation"]["evidence_sha256"])
        self.assertEqual(validation["reviewed_submission_sha256"], canonical_json_sha256(submission))

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
            path = make_real_package(destination)
            submission = load_json(path)
            submission["approval"] = {"status": "approved"}
            write_json(path, submission)
            errors, _ = validate_submission_file(path)
            joined = "\n".join(errors)
            self.assertIn("approved_by", joined)
            self.assertIn("approved_at", joined)
            self.assertIn("pull_request_url", joined)
            self.assertIn("validation", joined)

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
            joined = "\n".join(errors)
            self.assertIn("requires reproducibility.contract_version", joined)
            self.assertIn("requires submission schema_version=2.0", joined)

    def test_open_package_is_valid_but_remains_unapproved_at_contributor_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver")
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path, contributor_stage=True)
            self.assertEqual(without_storage_error(errors), [])
            self.assertNotIn("approval", load_json(path))

    def test_approved_package_requires_and_verifies_submitted_data_validation(self) -> None:
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

    def test_validation_evidence_checksum_must_match_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver", approved=True)
            destination = path.parent
            validation_path = destination / "maintainer-validation.json"
            validation = load_json(validation_path)
            validation["evaluation_evidence_sha256"] = "f" * 64
            write_json(validation_path, validation)
            submission = load_json(path)
            submission["approval"]["validation"]["evidence_sha256"] = sha256_file(validation_path)
            write_json(path, submission)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path)
            self.assertIn("evaluation_evidence_sha256 does not match", "\n".join(errors))

    def test_submission_metadata_cannot_change_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver", approved=True)
            submission = load_json(path)
            submission["institution"] = "Changed after maintainer validation"
            write_json(path, submission)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path)
            self.assertIn("reviewed_submission_sha256 does not match", "\n".join(errors))

    def test_validation_pins_public_ground_truth_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver", approved=True)
            destination = path.parent
            validation_path = destination / "maintainer-validation.json"
            validation = load_json(validation_path)
            validation["profile_ground_truth_manifest_sha256"] = "f" * 64
            write_json(validation_path, validation)
            submission = load_json(path)
            submission["approval"]["validation"]["evidence_sha256"] = sha256_file(validation_path)
            write_json(path, submission)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path)
            self.assertIn("profile_ground_truth_manifest_sha256 must match", "\n".join(errors))

    def test_submitter_profile_ground_truth_must_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver")
            submission = load_json(path)
            submission["profile_data"]["profile_ground_truth_manifest_sha256"] = "f" * 64
            write_json(path, submission)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path, contributor_stage=True)
            self.assertIn(
                "profile_data.profile_ground_truth_manifest_sha256 must match the leaderboard manifest",
                "\n".join(errors),
            )

    def test_v2_evaluation_evidence_must_match_submission_comparison_basis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver")
            evidence_path = path.parent / "evaluation-evidence.json"
            evidence = load_json(evidence_path)
            evidence["profile_ground_truth_release_id"] = "different-ground-truth-release"
            write_json(evidence_path, evidence)
            submission = load_json(path)
            submission["evaluation"]["evidence_sha256"] = sha256_file(evidence_path)
            write_json(path, submission)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path, contributor_stage=True)
            self.assertIn(
                "evaluation-evidence.json profile_ground_truth_release_id must equal",
                "\n".join(errors),
            )

    def test_v2_rejects_proprietary_result_code_and_model_licenses(self) -> None:
        license_paths = (
            ("result data", ("result_data_license_spdx",)),
            ("code", ("code", "license_spdx")),
            ("model", ("model_artifact", "license_spdx")),
        )
        for label, field_path in license_paths:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                path = make_real_package(Path(temporary) / "transolver")
                submission = load_json(path)
                target = submission["reproducibility"]
                for key in field_path[:-1]:
                    target = target[key]
                target[field_path[-1]] = "PROPRIETARY"
                write_json(path, submission)
                errors, _ = validate_submission_file(path, contributor_stage=True)
                self.assertIn("'PROPRIETARY' is not one of", "\n".join(errors))

    def test_validation_cannot_claim_model_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver", approved=True)
            validation_path = path.parent / "maintainer-validation.json"
            validation = load_json(validation_path)
            validation["model_execution"] = "performed"
            write_json(validation_path, validation)
            submission = load_json(path)
            submission["approval"]["validation"]["evidence_sha256"] = sha256_file(validation_path)
            write_json(path, submission)
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                errors, _ = validate_submission_file(path)
            self.assertIn("'not_performed' was expected", "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
