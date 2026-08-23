from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import promote_drivaerml_candidate as promoter


ROOT = Path(__file__).resolve().parents[1]
BINDINGS_PATH = ROOT / "benchmark-specs" / "drivaerml" / "candidate-release-bindings.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class DrivAerMLCandidateReleaseBindingTests(unittest.TestCase):
    def base_generated_specification(self) -> dict:
        return {
            "profile_definition": {
                "id": "drivaerml-diagnostics-v9-candidate",
                "file": "drivaerml-diagnostics-v9.json",
                "sha256": "1" * 64,
            },
            "scoring_support": {
                "dataset_evaluator_binding": {
                    "status": "pending_frozen_release",
                    "evaluator_reference_version": promoter.EVALUATOR_VERSION,
                    "evaluator_code_revision": None,
                },
                "profile_definition": {
                    "file": "drivaerml-diagnostics-v9.json",
                    "sha256": "1" * 64,
                    "status": "pending",
                },
            },
        }

    def make_ready_fixture(self, root: Path) -> tuple[dict, Path, Path]:
        benchmark = root / "benchmark-specs" / "drivaerml"
        manifest_path = benchmark / "scoring-support" / "candidate-v1" / "manifest.json"
        release_id = "drivaerml-candidate-support-v1"
        manifest = {
            "status": "candidate",
            "release_id": release_id,
            "dataset_id": "drivaerml",
            "dataset_version": promoter.DATASET_VERSION,
            "evaluation_reference_version": promoter.EVALUATOR_VERSION,
        }
        write_json(manifest_path, manifest)
        global_truth = {
            "release_id": "prototype-profile-ground-truth-2026-08-21",
            "manifest_sha256": "2" * 64,
        }
        global_manifest_path = root / "leaderboard" / "manifest.json"
        write_json(
            global_manifest_path,
            {"data_release": {"profile_ground_truth": global_truth}},
        )
        profile_path = benchmark / "drivaerml-diagnostics-v10.json"
        write_json(profile_path, {"id": "drivaerml-diagnostics-v10-candidate"})
        bindings = {
            "schema": "drivaerml-fluidsbench-candidate-release-bindings-v1",
            "status": "ready",
            "unresolved_token_prefix": promoter.UNRESOLVED_RELEASE_PREFIX,
            "candidate_manifest": {
                "status": "candidate",
                "release_id": release_id,
                "manifest_file": "scoring-support/candidate-v1/manifest.json",
                "manifest_url": (
                    "https://fluidsbench.org/assets/drivaerml/"
                    f"{release_id}/manifest.json"
                ),
                "manifest_sha256": promoter.sha256_file(manifest_path),
            },
            "evaluator": {
                "reference_version": promoter.EVALUATOR_VERSION,
                "code_revision": "3" * 40,
            },
            "profile_definition_v10": {
                "file": profile_path.name,
                "sha256": promoter.sha256_file(profile_path),
            },
            "profile_ground_truth": global_truth,
        }
        return bindings, benchmark, global_manifest_path

    def test_checked_in_unresolved_hand_off_never_leaks_into_active_spec(self) -> None:
        bindings = promoter.load_candidate_release_bindings(BINDINGS_PATH)
        self.assertEqual(bindings["status"], "unresolved")
        tokens = promoter.unresolved_release_tokens(bindings)
        self.assertGreaterEqual(len(tokens), 8)
        active = load_json(ROOT / "benchmark-specs" / "drivaerml" / "submission-spec.json")
        self.assertEqual(promoter.unresolved_release_tokens(active), [])
        self.assertNotIn("candidate_manifest", active["scoring_support"])

    def test_unresolved_generator_preserves_later_candidate_and_v10_bindings(self) -> None:
        bindings = promoter.load_candidate_release_bindings(BINDINGS_PATH)
        existing = {
            "profile_definition": {
                "id": "drivaerml-diagnostics-v10-candidate",
                "file": "drivaerml-diagnostics-v10.json",
                "sha256": "4" * 64,
            },
            "scoring_support": {
                "candidate_manifest": {
                    "status": "candidate",
                    "release_id": "later-release-v1",
                },
                "dataset_evaluator_binding": {
                    "status": "frozen",
                    "evaluator_reference_version": promoter.EVALUATOR_VERSION,
                    "evaluator_code_revision": "5" * 40,
                },
                "profile_definition": {
                    "file": "drivaerml-diagnostics-v10.json",
                    "sha256": "4" * 64,
                    "status": "later-reviewed-status",
                    "profile_ground_truth": {
                        "release_id": "later-truth-v1",
                        "manifest_sha256": "6" * 64,
                    },
                },
            },
        }
        generated = self.base_generated_specification()
        result = promoter.apply_release_managed_bindings(
            generated, bindings, existing
        )
        self.assertEqual(
            result["scoring_support"]["candidate_manifest"],
            existing["scoring_support"]["candidate_manifest"],
        )
        self.assertEqual(
            result["scoring_support"]["dataset_evaluator_binding"],
            existing["scoring_support"]["dataset_evaluator_binding"],
        )
        self.assertEqual(
            result["scoring_support"]["profile_definition"],
            existing["scoring_support"]["profile_definition"],
        )

    def test_ready_binding_is_idempotent_and_checks_manifest_and_global_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bindings, benchmark, global_manifest_path = self.make_ready_fixture(
                Path(temporary)
            )
            bindings_path = Path(temporary) / "candidate-release-bindings.json"
            write_json(bindings_path, bindings)
            loaded = promoter.load_candidate_release_bindings(bindings_path)
            with patch.object(promoter, "BENCHMARK_ROOT", benchmark), patch.object(
                promoter, "MANIFEST_PATH", global_manifest_path
            ):
                first = promoter.apply_release_managed_bindings(
                    self.base_generated_specification(), loaded, None
                )
                second = promoter.apply_release_managed_bindings(
                    self.base_generated_specification(), loaded, copy.deepcopy(first)
                )
            self.assertEqual(first, second)
            self.assertEqual(
                first["scoring_support"]["candidate_manifest"],
                bindings["candidate_manifest"],
            )
            self.assertEqual(
                first["scoring_support"]["dataset_evaluator_binding"]["status"],
                "frozen",
            )

            bad_hash = copy.deepcopy(bindings)
            bad_hash["candidate_manifest"]["manifest_sha256"] = "7" * 64
            with patch.object(promoter, "BENCHMARK_ROOT", benchmark), patch.object(
                promoter, "MANIFEST_PATH", global_manifest_path
            ), self.assertRaisesRegex(ValueError, "does not match its local file"):
                promoter.apply_release_managed_bindings(
                    self.base_generated_specification(), bad_hash, None
                )

            bad_truth = copy.deepcopy(bindings)
            bad_truth["profile_ground_truth"]["manifest_sha256"] = "8" * 64
            with patch.object(promoter, "BENCHMARK_ROOT", benchmark), patch.object(
                promoter, "MANIFEST_PATH", global_manifest_path
            ), self.assertRaisesRegex(ValueError, "global leaderboard binding"):
                promoter.apply_release_managed_bindings(
                    self.base_generated_specification(), bad_truth, None
                )

    def test_unresolved_selection_does_not_regress_an_existing_v10_file(self) -> None:
        bindings = promoter.load_candidate_release_bindings(BINDINGS_PATH)
        with tempfile.TemporaryDirectory() as temporary:
            benchmark = Path(temporary)
            profile_path = benchmark / "drivaerml-diagnostics-v10.json"
            profile = {"id": "drivaerml-diagnostics-v10-candidate"}
            write_json(profile_path, profile)
            existing = {
                "profile_definition": {
                    "file": profile_path.name,
                    "sha256": promoter.sha256_file(profile_path),
                }
            }
            with patch.object(promoter, "BENCHMARK_ROOT", benchmark):
                selected_path, selected_profile = promoter.select_generation_profile(
                    bindings, existing
                )
            self.assertEqual(selected_path, profile_path)
            self.assertEqual(selected_profile, profile)


if __name__ == "__main__":
    unittest.main()
