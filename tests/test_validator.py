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
    validate_evaluation_evidence,
    validate_open_reproducibility,
    validate_v3_case_metrics,
    validate_v3_discretization,
    validate_v3_prediction_metadata,
    validate_submission_file,
)


SOURCE = ROOT / "submissions" / "ahmedml" / "transolver"
V2_TEMPLATE = ROOT / "examples" / "v2-template"
V3_TEMPLATE = ROOT / "examples" / "v3-template"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    def validate_v3_reproducibility_fragments(
        self,
        directory: Path,
        submission: dict,
        evidence: dict,
    ) -> list[str]:
        evidence_path = directory / submission["evaluation"]["evidence_file"]
        write_json(evidence_path, evidence)
        submission["evaluation"]["evidence_sha256"] = sha256_file(evidence_path)
        errors: list[str] = []
        loaded_evidence = validate_evaluation_evidence(
            errors.append,
            directory,
            submission,
        )
        profile_ground_truth = submission["profile_data"]
        validate_open_reproducibility(
            errors.append,
            directory,
            submission,
            loaded_evidence,
            {
                "data_release": {
                    "profile_ground_truth": {
                        "release_id": profile_ground_truth[
                            "profile_ground_truth_release_id"
                        ],
                        "manifest_sha256": profile_ground_truth[
                            "profile_ground_truth_manifest_sha256"
                        ],
                    }
                }
            },
            {"status": "official"},
            {"index_file": "does-not-exist.json"},
            contributor_stage=False,
        )
        return errors

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

    def test_v3_template_validation_record_uses_canonical_submission_hash(self) -> None:
        submission = load_json(V3_TEMPLATE / "submission.json")
        validation = load_json(V3_TEMPLATE / "maintainer-validation.json")

        self.assertEqual(
            validation["reviewed_submission_sha256"],
            canonical_json_sha256(submission),
        )
        self.assertEqual(
            validation["evaluation_evidence_sha256"],
            sha256_file(V3_TEMPLATE / "evaluation-evidence.json"),
        )

    def test_v3_optional_reproducibility_artifacts_may_be_omitted(self) -> None:
        submission = load_json(V3_TEMPLATE / "submission.json")
        evidence = load_json(V3_TEMPLATE / "evaluation-evidence.json")
        submission.pop("code_url")
        submission["evaluation"].pop("code_revision")
        evidence.pop("code_revision")
        for field in (
            "code",
            "model_artifact",
            "environment",
            "artifact_documentation_url",
        ):
            submission["reproducibility"].pop(field)

        self.assertEqual(
            schema_errors(
                submission,
                "submission.schema.json",
                schema_version="v3",
            ),
            [],
        )
        self.assertEqual(
            schema_errors(
                evidence,
                "evaluation-evidence.schema.json",
                schema_version="v3",
            ),
            [],
        )
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(
                self.validate_v3_reproducibility_fragments(
                    Path(temporary),
                    submission,
                    evidence,
                ),
                [],
            )

        for required_field in (
            "contract_version",
            "access",
            "public_test_data_use",
            "result_data_license_spdx",
        ):
            with self.subTest(required_field=required_field):
                malformed = load_json(V3_TEMPLATE / "submission.json")
                malformed["reproducibility"].pop(required_field)
                joined = "\n".join(
                    schema_errors(
                        malformed,
                        "submission.schema.json",
                        schema_version="v3",
                    )
                )
                self.assertIn(
                    f"'{required_field}' is a required property",
                    joined,
                )

    def test_v3_supplied_reproducibility_artifacts_remain_strict(self) -> None:
        mutations = (
            (("code", "repository_url"), "http://example.org/code"),
            (("code", "commit"), "not-a-full-commit"),
            (("code", "license_spdx"), "PROPRIETARY"),
            (("model_artifact", "url"), "http://example.org/model"),
            (("model_artifact", "sha256"), "not-a-sha256"),
            (("model_artifact", "license_spdx"), "PROPRIETARY"),
            (("environment", "kind"), "requirements"),
            (("environment", "url"), "http://example.org/environment"),
            (("environment", "sha256"), "not-a-sha256"),
            (
                ("artifact_documentation_url",),
                "http://example.org/artifacts",
            ),
        )
        for field_path, malformed_value in mutations:
            with self.subTest(field_path=".".join(field_path)):
                submission = load_json(V3_TEMPLATE / "submission.json")
                target = submission["reproducibility"]
                for field in field_path[:-1]:
                    target = target[field]
                target[field_path[-1]] = malformed_value
                errors = schema_errors(
                    submission,
                    "submission.schema.json",
                    schema_version="v3",
                )
                self.assertTrue(errors)
                self.assertTrue(
                    any(
                        "reproducibility." + ".".join(field_path) in error
                        for error in errors
                    ),
                    "\n".join(errors),
                )

        evidence = load_json(V3_TEMPLATE / "evaluation-evidence.json")
        evidence["code_revision"] = "not-a-full-commit"
        self.assertTrue(
            any(
                "code_revision" in error
                for error in schema_errors(
                    evidence,
                    "evaluation-evidence.schema.json",
                    schema_version="v3",
                )
            )
        )
        submission = load_json(V3_TEMPLATE / "submission.json")
        submission["code_url"] = "http://example.org/code"
        submission["evaluation"]["code_revision"] = "not-a-full-commit"
        alias_errors = "\n".join(
            schema_errors(
                submission,
                "submission.schema.json",
                schema_version="v3",
            )
        )
        self.assertIn("code_url", alias_errors)
        self.assertIn("evaluation.code_revision", alias_errors)

    def test_v3_code_aliases_are_conditional_and_cannot_be_orphaned(self) -> None:
        submission = load_json(V3_TEMPLATE / "submission.json")
        evidence = load_json(V3_TEMPLATE / "evaluation-evidence.json")
        submission["reproducibility"].pop("code")
        with tempfile.TemporaryDirectory() as temporary:
            joined = "\n".join(
                self.validate_v3_reproducibility_fragments(
                    Path(temporary),
                    submission,
                    evidence,
                )
            )
        self.assertIn("code_url requires reproducibility.code", joined)
        self.assertIn(
            "evaluation.code_revision requires reproducibility.code",
            joined,
        )
        self.assertIn(
            "evaluation-evidence.json code_revision requires reproducibility.code",
            joined,
        )

        submission = load_json(V3_TEMPLATE / "submission.json")
        evidence = load_json(V3_TEMPLATE / "evaluation-evidence.json")
        submission.pop("code_url")
        submission["evaluation"].pop("code_revision")
        evidence.pop("code_revision")
        with tempfile.TemporaryDirectory() as temporary:
            joined = "\n".join(
                self.validate_v3_reproducibility_fragments(
                    Path(temporary),
                    submission,
                    evidence,
                )
            )
        self.assertIn(
            "code_url must equal reproducibility.code.repository_url",
            joined,
        )
        self.assertIn(
            "evaluation.code_revision must equal the full "
            "reproducibility.code.commit",
            joined,
        )
        self.assertIn(
            "evaluation-evidence.json code_revision must equal the full "
            "reproducibility.code.commit",
            joined,
        )

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

    def test_historical_v2_package_remains_valid_but_cannot_be_a_new_contribution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = make_real_package(Path(temporary) / "transolver")
            with patch("scripts.validate_submission.load_json", side_effect=official_contract_load_json):
                historical_errors, _ = validate_submission_file(path)
                contributor_errors, _ = validate_submission_file(path, contributor_stage=True)
            self.assertEqual(without_storage_error(historical_errors), [])
            self.assertIn(
                "new contributor-stage submitted_evaluation packages require submission schema_version=3.0",
                "\n".join(contributor_errors),
            )
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

    def test_v3_case_metrics_and_discretization_bind_exact_support(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            submission = {
                "submission_id": "example-model-v3",
                "dataset_id": "example",
                "split_id": "full",
                "case_set_id": "standard",
                "scoring_support": {
                    "status": "official",
                    "release_id": "example-support-v1",
                    "manifest_url": "https://example.org/releases/example-support-v1/manifest.json",
                    "manifest_sha256": "a" * 64,
                },
                "spatial_discretization": {
                    "format": "fluidsbench-discretization-v1",
                    "file": "discretization.json",
                    "sha256": "0" * 64,
                },
                "case_metrics": {
                    "format": "fluidsbench-case-metrics-v1",
                    "file": "metrics/cases.json",
                    "sha256": "0" * 64,
                    "case_count": 2,
                },
                "metric_values": {"surface_pressure_rel_l2": 2.0},
            }
            split_case_ids = ["case-001", "case-002"]
            support_manifest = {
                "supports": [
                    {
                        "id": "surface",
                        "extrapolation_policy": "forbidden",
                        "metric_bindings": [
                            {
                                "metric_id": "surface_pressure_rel_l2",
                                "quantity_id": "pressure",
                                "reduction": "relative_l2_percent",
                                "weighting": "support_weights",
                                "dataset_weighting": "surface_face_area",
                                "aggregation": "per_geometry_then_macro_average",
                                "case_evidence": "metric_value",
                            }
                        ],
                    }
                ]
            }
            support_case_index = {
                "_loaded_cases": [
                    {
                        "case_id": case_id,
                        "support_instances": [{"support_id": "surface", "entity_count": 2}],
                    }
                    for case_id in split_case_ids
                ]
            }
            case_metrics = {
                "$schema": "https://fluidsbench.org/schemas/v3/case-metrics.schema.json",
                "schema_version": "1.0",
                "submission_id": submission["submission_id"],
                "dataset_id": submission["dataset_id"],
                "split_id": submission["split_id"],
                "case_set_id": submission["case_set_id"],
                "scoring_support_release_id": submission["scoring_support"]["release_id"],
                "scoring_support_manifest_sha256": submission["scoring_support"]["manifest_sha256"],
                "case_count": 2,
                "cases": [
                    {
                        "case_id": case_id,
                        "supports": [
                            {
                                "support_id": "surface",
                                "support_count": 2,
                                "scored_count": 2,
                                "coverage_fraction": 1.0,
                                "weight_coverage_fraction": 1.0,
                                "unmapped_count": 0,
                                "extrapolated_count": 0,
                                "metric_values": {"surface_pressure_rel_l2": value},
                            }
                        ],
                    }
                    for case_id, value in zip(split_case_ids, (1.0, 3.0))
                ],
                "metric_values": submission["metric_values"],
            }
            case_metrics_path = directory / submission["case_metrics"]["file"]
            write_json(case_metrics_path, case_metrics)
            submission["case_metrics"]["sha256"] = sha256_file(case_metrics_path)

            representation = {
                "used": True,
                "representation": "point_values",
                "entity_counts": [
                    {"entity": "points", "count": {"kind": "fixed", "value": 2}}
                ],
                "native_comparison": {"status": "not_applicable"},
                "sampling": {"kind": "none"},
                "domain": {"kind": "full_dataset_domain"},
                "connectivity": "none",
            }
            case_records = [
                {
                    "$schema": "https://fluidsbench.org/schemas/v3/discretization-case.schema.json",
                    "schema_version": "1.0",
                    "submission_id": submission["submission_id"],
                    "dataset_id": submission["dataset_id"],
                    "split_id": submission["split_id"],
                    "case_id": case_id,
                    "inference": {
                        "inputs": [],
                        "direct_outputs": [
                            {
                                "id": "surface-output",
                                "entity_counts": [{"entity": "points", "count": 2}],
                            }
                        ],
                        "mappings": [
                            {
                                "support_id": "surface",
                                "source_output_id": "surface-output",
                                "support_count": 2,
                                "scored_count": 2,
                                "unmapped_count": 0,
                                "extrapolated_count": 0,
                                "final_coverage_fraction": 1.0,
                            }
                        ],
                    },
                }
                for case_id in split_case_ids
            ]
            case_records_path = directory / "discretization" / "cases.jsonl"
            case_records_path.parent.mkdir(parents=True)
            case_records_path.write_text(
                "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in case_records),
                encoding="utf-8",
            )
            discretization = {
                "$schema": "https://fluidsbench.org/schemas/v3/discretization.schema.json",
                "schema_version": "1.0",
                "submission_id": submission["submission_id"],
                "dataset_id": submission["dataset_id"],
                "split_id": submission["split_id"],
                "scoring_support_release_id": submission["scoring_support"]["release_id"],
                "scoring_support_manifest_sha256": submission["scoring_support"]["manifest_sha256"],
                "training": {
                    "surface_input": {"used": False},
                    "surface_supervision": {"used": False},
                    "volume_input": {"used": False},
                    "volume_supervision": {"used": False},
                },
                "inference": {
                    "geometry_dependency": "surface_geometry",
                    "surface_input": {"used": False},
                    "volume_input": {"used": False},
                    "direct_outputs": [
                        {
                            "id": "surface-output",
                            "domain": "surface",
                            "representation": representation,
                            "queries_per_forward_pass": {"kind": "fixed", "value": 2},
                        }
                    ],
                    "mappings": [
                        {
                            "support_id": "surface",
                            "source_output_id": "surface-output",
                            "method": {"kind": "identity"},
                            "implementation": "src/evaluate.py",
                            "extrapolation_policy": "forbidden",
                            "unmapped_fraction": 0.0,
                            "extrapolated_fraction": 0.0,
                            "final_coverage_fraction": 1.0,
                        }
                    ],
                },
                "case_manifest": {
                    "format": "jsonl",
                    "file": "discretization/cases.jsonl",
                    "sha256": sha256_file(case_records_path),
                    "case_count": 2,
                },
            }
            discretization_path = directory / submission["spatial_discretization"]["file"]
            write_json(discretization_path, discretization)
            submission["spatial_discretization"]["sha256"] = sha256_file(discretization_path)

            errors: list[str] = []
            validate_v3_case_metrics(
                errors.append,
                directory,
                submission,
                split_case_ids,
                support_manifest,
                support_case_index,
            )
            validate_v3_discretization(
                errors.append,
                directory,
                submission,
                split_case_ids,
                support_manifest,
                support_case_index,
            )
            self.assertEqual(errors, [])

            case_metrics["cases"][0]["supports"][0]["scored_count"] = 1
            write_json(case_metrics_path, case_metrics)
            submission["case_metrics"]["sha256"] = sha256_file(case_metrics_path)
            errors = []
            validate_v3_case_metrics(
                errors.append,
                directory,
                submission,
                split_case_ids,
                support_manifest,
                support_case_index,
            )
            self.assertIn("must score every support entity", "\n".join(errors))

            case_metrics["cases"][0]["supports"][0]["scored_count"] = 2
            for case in case_metrics["cases"]:
                case["supports"][0]["metric_values"] = {"invented_metric": 2.0}
            write_json(case_metrics_path, case_metrics)
            submission["case_metrics"]["sha256"] = sha256_file(case_metrics_path)
            errors = []
            validate_v3_case_metrics(
                errors.append,
                directory,
                submission,
                split_case_ids,
                support_manifest,
                support_case_index,
            )
            self.assertIn(
                "metric IDs must exactly match the official support bindings",
                "\n".join(errors),
            )
            self.assertIn("must have one value per test case", "\n".join(errors))

            discretization["inference"]["surface_input"] = {
                **representation,
                "case_record_id": "surface-input",
            }
            for record in case_records:
                record["inference"]["inputs"] = [
                    {
                        "id": "surface-input",
                        "entity_counts": [{"entity": "points", "count": 999}],
                    }
                ]
            case_records_path.write_text(
                "".join(
                    json.dumps(record, separators=(",", ":")) + "\n"
                    for record in case_records
                ),
                encoding="utf-8",
            )
            discretization["case_manifest"]["sha256"] = sha256_file(case_records_path)
            write_json(discretization_path, discretization)
            submission["spatial_discretization"]["sha256"] = sha256_file(
                discretization_path
            )
            errors = []
            validate_v3_discretization(
                errors.append,
                directory,
                submission,
                split_case_ids,
                support_manifest,
                support_case_index,
            )
            self.assertIn(
                "inference input 'surface-input'/'points' fixed count does not "
                "match case records",
                "\n".join(errors),
            )

            discretization["inference"]["surface_input"]["native_comparison"] = {
                "status": "reported",
                "native_entity_counts": [
                    {"entity": "points", "count": {"kind": "fixed", "value": 4}}
                ],
                "fractions": [
                    {
                        "entity": "points",
                        "fraction": {"kind": "fixed", "value": 0.5},
                    }
                ],
            }
            for record in case_records:
                record["inference"]["inputs"][0] = {
                    "id": "surface-input",
                    "entity_counts": [{"entity": "points", "count": 2}],
                    "native_entity_counts": [{"entity": "points", "count": 4}],
                    "native_fractions": [{"entity": "points", "fraction": 0.5}],
                }
            case_records[1]["inference"]["inputs"][0]["native_fractions"][0][
                "fraction"
            ] = 0.75
            case_records_path.write_text(
                "".join(
                    json.dumps(record, separators=(",", ":")) + "\n"
                    for record in case_records
                ),
                encoding="utf-8",
            )
            discretization["case_manifest"]["sha256"] = sha256_file(case_records_path)
            write_json(discretization_path, discretization)
            submission["spatial_discretization"]["sha256"] = sha256_file(
                discretization_path
            )
            errors = []
            validate_v3_discretization(
                errors.append,
                directory,
                submission,
                split_case_ids,
                support_manifest,
                support_case_index,
            )
            self.assertIn(
                "native fraction must equal count/native_count",
                "\n".join(errors),
            )
            self.assertIn(
                "fixed native fraction does not match case records",
                "\n".join(errors),
            )

    def test_prediction_artifact_checks_are_optional_and_maintainer_owned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            split_case_ids = ["case-001", "case-002"]
            submission = {
                "submission_id": "example-model-v3",
                "dataset_id": "example",
                "split_id": "full",
                "scoring_support": {
                    "release_id": "example-support-v1",
                    "manifest_sha256": "a" * 64,
                },
                "prediction_artifacts": [
                    {
                        "artifact_id": "example-predictions",
                        "support_release_id": "example-support-v1",
                        "support_manifest_sha256": "a" * 64,
                        "split_id": "full",
                        "revision": "b" * 40,
                        "manifest_sha256": "c" * 64,
                        "coverage": {
                            "kind": "example_cases",
                            "case_count": 1,
                            "expected_case_count": 2,
                            "case_ids": ["case-001"],
                        },
                    }
                ],
            }
            errors: list[str] = []
            self.assertIsNone(
                validate_v3_prediction_metadata(
                    errors.append,
                    directory,
                    submission,
                    split_case_ids,
                    contributor_stage=False,
                )
            )
            self.assertEqual(errors, [])

            checks = {
                "$schema": "https://fluidsbench.org/schemas/v3/prediction-artifact-checks.schema.json",
                "schema_version": "1.0",
                "submission_id": submission["submission_id"],
                "checks": [
                    {
                        "artifact_id": "example-predictions",
                        "status": "accessible",
                        "checked_at": "2026-07-27T12:00:00Z",
                        "checked_by": "Maintainer",
                        "repository_revision": "b" * 40,
                        "manifest_sha256": "c" * 64,
                        "checked_case_count": 1,
                        "recomputed_case_count": 0,
                        "expected_case_count": 2,
                        "metric_recomputation": "not_performed",
                    }
                ],
            }
            write_json(directory / "prediction-artifact-checks.json", checks)
            errors = []
            validate_v3_prediction_metadata(
                errors.append,
                directory,
                submission,
                split_case_ids,
                contributor_stage=True,
            )
            self.assertIn(
                "contributors must not add prediction-artifact-checks.json",
                "\n".join(errors),
            )

            checks["checks"][0].update(
                {
                    "status": "metrics_recomputed",
                    "checked_case_count": 1,
                    "recomputed_case_count": 1,
                    "metric_recomputation": "performed",
                }
            )
            write_json(directory / "prediction-artifact-checks.json", checks)
            errors = []
            validate_v3_prediction_metadata(
                errors.append,
                directory,
                submission,
                split_case_ids,
                contributor_stage=False,
            )
            self.assertIn(
                "performed metric recomputation requires the complete benchmark split",
                "\n".join(errors),
            )


if __name__ == "__main__":
    unittest.main()
