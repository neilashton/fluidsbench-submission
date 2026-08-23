from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import assemble_drivaerml_schema_v3_candidate as assembler


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "examples" / "v3-template"
DRIVAER_TEMPLATE = (
    ROOT / "examples" / "drivaerml-v3-candidate" / "package-config.template.json"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class DrivAerMLCandidatePackageAssemblerTests(unittest.TestCase):
    def make_fixture(self, root: Path) -> dict[str, Path]:
        benchmark = root / "benchmark-specs" / "drivaerml"
        benchmark.mkdir(parents=True)
        split_path = benchmark / "splits" / "default.json"
        split = {
            "schema_version": "1.0",
            "dataset_id": "drivaerml",
            "split_id": "default",
            "case_set_id": "standard",
            "split_label": "Default",
            "case_id_status": "official",
            "case_count": 2,
            "case_ids": ["case-001", "case-002"],
        }
        write_json(split_path, split)

        profile_path = benchmark / "drivaerml-diagnostics-v10.json"
        write_json(profile_path, {"id": "drivaerml-diagnostics-v10-candidate"})
        profile_sha256 = assembler.sha256_file(profile_path)
        evaluator_revision = "b" * 40
        global_truth = load_json(ROOT / "leaderboard" / "manifest.json")[
            "data_release"
        ]["profile_ground_truth"]
        candidate = {
            "status": "candidate",
            "release_id": "drivaerml-candidate-support-v1",
            "manifest_url": (
                "https://fluidsbench.org/assets/drivaerml/"
                "drivaerml-candidate-support-v1/manifest.json"
            ),
        }
        support_manifest_path = benchmark / "scoring-support" / "candidate" / "manifest.json"
        write_json(
            support_manifest_path,
            {
                "status": "candidate",
                "release_id": candidate["release_id"],
                "dataset_id": "drivaerml",
                "dataset_version": "drivaerml-native-v3-candidate",
                "evaluation_reference_version": "drivaerml-evaluator-v3-candidate",
            },
        )
        support_sha256 = assembler.sha256_file(support_manifest_path)
        candidate["manifest_sha256"] = support_sha256
        metric_values = load_json(TEMPLATE / "metrics" / "cases.json")[
            "metric_values"
        ]
        specification = {
            "schema_version": "1.1",
            "dataset_id": "drivaerml",
            "dataset_name": "DrivAerML",
            "dataset_version": "drivaerml-native-v3-candidate",
            "status": "candidate_scoring_contract",
            "evaluation_reference_version": "drivaerml-evaluator-v3-candidate",
            "scoring_support": {
                "status": "owner_review_required",
                "submissions_open": False,
                "candidate_manifest": {
                    **candidate,
                    "manifest_file": "scoring-support/candidate/manifest.json",
                },
                "dataset_evaluator_binding": {
                    "status": "frozen",
                    "evaluator_reference_version": "drivaerml-evaluator-v3-candidate",
                    "evaluator_code_revision": evaluator_revision,
                },
                "profile_definition": {
                    "profile_ground_truth": {
                        "release_id": global_truth["release_id"],
                        "manifest_sha256": global_truth["manifest_sha256"],
                    }
                },
            },
            "profile_definition": {
                "id": "drivaerml-diagnostics-v10-candidate",
                "file": profile_path.name,
                "sha256": profile_sha256,
            },
            "profile_panels": [
                {
                    "id": "synthetic_profile",
                    "required": True,
                    "station_ids": ["centreline"],
                    "quantity_ids": ["pressure"],
                }
            ],
            "metrics": [{"id": metric_id} for metric_id in metric_values],
            "splits": [
                {
                    "id": "default",
                    "label": "Default",
                    "index_file": "splits/default.json",
                    "case_count": 2,
                    "case_set_id": "standard",
                    "case_id_status": "official",
                    "sha256": assembler.sha256_file(split_path),
                }
            ],
        }
        specification_path = benchmark / "submission-spec.json"
        write_json(specification_path, specification)

        case_metrics = load_json(TEMPLATE / "metrics" / "cases.json")
        case_metrics.update(
            {
                "submission_id": "drivaerml-test-model-v1",
                "dataset_id": "drivaerml",
                "split_id": "default",
                "case_set_id": "standard",
                "scoring_support_release_id": candidate["release_id"],
                "scoring_support_manifest_sha256": support_sha256,
            }
        )
        case_metrics_path = root / "inputs" / "metrics" / "cases.json"
        write_json(case_metrics_path, case_metrics)

        profiles_path = root / "inputs" / "profiles"
        shutil.copytree(TEMPLATE / "profiles", profiles_path)
        profile_index = load_json(profiles_path / "index.json")
        profile_index.update(
            {
                "submission_id": "drivaerml-test-model-v1",
                "dataset_id": "drivaerml",
                "split_id": "default",
                "case_set_id": "standard",
            }
        )
        write_json(profiles_path / "index.json", profile_index)

        case_records = []
        for line in (TEMPLATE / "discretization" / "cases.jsonl").read_text(
            encoding="utf-8"
        ).splitlines():
            record = json.loads(line)
            record.update(
                {
                    "submission_id": "drivaerml-test-model-v1",
                    "dataset_id": "drivaerml",
                    "split_id": "default",
                }
            )
            case_records.append(record)
        cases_path = root / "inputs" / "discretization" / "cases.jsonl"
        cases_path.parent.mkdir(parents=True)
        cases_path.write_text(
            "".join(json.dumps(record) + "\n" for record in case_records),
            encoding="utf-8",
        )

        spatial = load_json(TEMPLATE / "discretization.json")
        config = {
            "schema": assembler.CONFIG_SCHEMA,
            "split_id": "default",
            "participant": {
                "submission_id": "drivaerml-test-model-v1",
                "result_revision": {
                    "series_id": "drivaerml-test-model",
                    "version": 1,
                    "supersedes": None,
                    "change_summary": "Initial candidate dry run.",
                },
                "model": "Test model",
                "model_type": "Coordinate network",
                "model_types": ["Coordinate network"],
                "training_regime": "from_scratch",
                "target_data_used": "official_train",
                "external_pretraining": False,
                "pretraining_data": [],
                "parameter_count_millions": None,
                "submitter_name": "Test Submitter",
                "institution": "Test Institution",
                "paper_url": "",
                "submitted_at": "2026-08-22",
                "reproducibility": {
                    "contract_version": "open-reproducibility-3.0",
                    "access": "public",
                    "public_test_data_use": "evaluation_only",
                    "result_data_license_spdx": "CC-BY-4.0",
                },
            },
            "evaluation": {
                "command": "python frozen_evaluator.py --split default",
                "generated_at": "2026-08-22T12:00:00Z",
            },
            "spatial_discretization": {
                "training": spatial["training"],
                "inference": spatial["inference"],
                "notes": "Test fixture.",
            },
            "release_bindings": {
                "candidate_manifest": candidate,
                "evaluator": {
                    "reference_version": "drivaerml-evaluator-v3-candidate",
                    "code_revision": evaluator_revision,
                },
                "profile_definition_v10": {
                    "file": profile_path.name,
                    "sha256": profile_sha256,
                },
                "profile_ground_truth": {
                    "release_id": global_truth["release_id"],
                    "manifest_sha256": global_truth["manifest_sha256"],
                },
            },
        }
        config_path = root / "package-config.json"
        write_json(config_path, config)
        return {
            "specification": specification_path,
            "config": config_path,
            "case_metrics": case_metrics_path,
            "profiles": profiles_path,
            "discretization_cases": cases_path,
            "output": root / "output" / "drivaerml-test-model-v1",
        }

    def test_checked_in_template_reports_explicit_tokens_without_ready_claim(self) -> None:
        config = load_json(DRIVAER_TEMPLATE)
        tokens = assembler.unresolved_tokens(config)
        self.assertGreater(len(tokens), 10)
        self.assertTrue(
            any(item["token"].startswith("__UNRESOLVED_DRIVAERML_") for item in tokens)
        )
        self.assertTrue(any(item["token"].startswith("__REPLACE_") for item in tokens))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                assembler.PackageAssemblyError, "contains unresolved"
            ):
                assembler.assemble_package(
                    config_path=DRIVAER_TEMPLATE,
                    specification_path=ROOT / "benchmark-specs" / "drivaerml" / "submission-spec.json",
                    case_metrics_path=Path(temporary) / "missing-metrics.json",
                    profiles_path=Path(temporary) / "missing-profiles",
                    discretization_cases_path=Path(temporary) / "missing-cases.jsonl",
                    output_path=Path(temporary) / "must-not-exist",
                )
            self.assertFalse((Path(temporary) / "must-not-exist").exists())

    def test_assembly_canonicalizes_metric_and_profile_object_order_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_fixture(Path(temporary))
            metrics = load_json(paths["case_metrics"])
            metrics["metric_values"] = dict(reversed(list(metrics["metric_values"].items())))
            write_json(paths["case_metrics"], metrics)

            chunk_path = paths["profiles"] / "chunk-000.json"
            chunk = load_json(chunk_path)
            # One series is sufficient in this tiny contract; rewriting the
            # source exercises the input-index hash boundary.
            write_json(chunk_path, chunk)
            index = load_json(paths["profiles"] / "index.json")
            index["chunks"][0]["sha256"] = assembler.sha256_file(chunk_path)
            write_json(paths["profiles"] / "index.json", index)

            result = assembler.assemble_package(
                config_path=paths["config"],
                specification_path=paths["specification"],
                case_metrics_path=paths["case_metrics"],
                profiles_path=paths["profiles"],
                discretization_cases_path=paths["discretization_cases"],
                output_path=paths["output"],
            )
            self.assertEqual(result["status"], "candidate_package_assembled_not_approved")
            submission = load_json(paths["output"] / "submission.json")
            evidence = load_json(paths["output"] / "evaluation-evidence.json")
            self.assertNotIn("approval", submission)
            self.assertNotIn("code_revision", submission["evaluation"])
            self.assertNotIn("code_revision", evidence)
            self.assertFalse((paths["output"] / "maintainer-validation.json").exists())
            expected_order = [
                item["id"] for item in load_json(paths["specification"])["metrics"]
            ]
            self.assertEqual(list(submission["metric_values"]), expected_order)
            self.assertEqual(
                submission["case_metrics"]["sha256"],
                assembler.sha256_file(paths["output"] / "metrics" / "cases.json"),
            )

    def test_conflicting_evaluator_identity_and_profile_chunk_drift_fail(self) -> None:
        for mutation, message in (
            ("metrics", "submission_id must equal"),
            ("profiles", "input index binding"),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                paths = self.make_fixture(Path(temporary))
                if mutation == "metrics":
                    metrics = load_json(paths["case_metrics"])
                    metrics["submission_id"] = "different-result-v1"
                    write_json(paths["case_metrics"], metrics)
                else:
                    chunk_path = paths["profiles"] / "chunk-000.json"
                    chunk = load_json(chunk_path)
                    chunk["cases"][0]["series"][0]["prediction"][0] += 0.25
                    write_json(chunk_path, chunk)
                with self.assertRaisesRegex(assembler.PackageAssemblyError, message):
                    assembler.assemble_package(
                        config_path=paths["config"],
                        specification_path=paths["specification"],
                        case_metrics_path=paths["case_metrics"],
                        profiles_path=paths["profiles"],
                        discretization_cases_path=paths["discretization_cases"],
                        output_path=paths["output"],
                    )
                self.assertFalse(paths["output"].exists())

    def test_participant_code_commit_is_optional_but_consistent_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_fixture(Path(temporary))
            config = load_json(paths["config"])
            commit = "c" * 40
            config["participant"]["code_url"] = "https://github.com/example/model"
            config["participant"]["reproducibility"]["code"] = {
                "repository_url": "https://github.com/example/model",
                "commit": commit,
                "license_spdx": "Apache-2.0",
            }
            write_json(paths["config"], config)
            assembler.assemble_package(
                config_path=paths["config"],
                specification_path=paths["specification"],
                case_metrics_path=paths["case_metrics"],
                profiles_path=paths["profiles"],
                discretization_cases_path=paths["discretization_cases"],
                output_path=paths["output"],
            )
            submission = load_json(paths["output"] / "submission.json")
            evidence = load_json(paths["output"] / "evaluation-evidence.json")
            self.assertEqual(submission["evaluation"]["code_revision"], commit)
            self.assertEqual(evidence["code_revision"], commit)


if __name__ == "__main__":
    unittest.main()
