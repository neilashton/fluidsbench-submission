"""Exercise contributor intake with synthetic evidence, never a model result."""

from __future__ import annotations

import copy
import io
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from reference.ahmedml.pre_release import GENUINE_INFERENCE_ATTESTATION
from scripts import manage_leaderboard as manager
from scripts import validate_submission as validator


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


class AhmedMLDevIntakeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        (self.root / "benchmark-specs").symlink_to(SOURCE_ROOT / "benchmark-specs", target_is_directory=True)
        (self.root / "leaderboard").mkdir()
        shutil.copy2(SOURCE_ROOT / "leaderboard/manifest.json", self.root / "leaderboard/manifest.json")
        old_id = validator.AHMEDML_DEVELOPMENT_FIXTURE_ID
        new_id = "ahmedml-intake-test-v1"
        self.directory = self.root / "submissions/ahmedml" / new_id
        shutil.copytree(SOURCE_ROOT / "submissions/ahmedml" / old_id, self.directory)
        # Reuse numerical coverage only. Simulate an assembler's contributor
        # declarations inside a disposable test repository; never publish it.
        for path in self.directory.rglob("*"):
            if path.suffix in {".json", ".jsonl"}:
                path.write_text(path.read_text().replace(old_id, new_id))
        self.path = self.directory / "submission.json"
        submission = load(self.path)
        submission["model"] = "Synthetic intake test, not a scientific result"
        submission["result_revision"]["series_id"] = "ahmedml-intake-test"
        methodology = load(SOURCE_ROOT / "examples/v3-template/submission.json")["methodology"]
        methodology["record_kind"] = "submitter_reported"
        fields = submission["methodology"]["architecture"]["predicted_fields"]
        for field in fields:
            field["component_ids"] = ["coordinate-network"]
        methodology["architecture"]["predicted_fields"] = fields
        methodology["inference_compute"]["case_count"] = 50
        submission["methodology"] = methodology
        submission["parameter_count_millions"] = 0.001
        discretization_path = self.directory / "discretization.json"
        discretization = load(discretization_path)
        discretization["case_manifest"]["sha256"] = validator.sha256_file(
            self.directory / discretization["case_manifest"]["file"]
        )
        write(discretization_path, discretization)
        index_path = self.directory / "profiles/index.json"
        index = load(index_path)
        for chunk in index["chunks"]:
            chunk["sha256"] = validator.sha256_file(index_path.parent / chunk["file"])
        write(index_path, index)
        evidence_path = self.directory / "evaluation-evidence.json"
        evidence = load(evidence_path)
        evidence["notes"] = GENUINE_INFERENCE_ATTESTATION
        evidence["profile_index_sha256"] = validator.sha256_file(index_path)
        for declaration, evidence_key in (
            ("spatial_discretization", "discretization_sha256"),
            ("case_metrics", "case_metrics_sha256"),
            ("regional_diagnostics", "regional_diagnostics_sha256"),
        ):
            digest = validator.sha256_file(self.directory / submission[declaration]["file"])
            submission[declaration]["sha256"] = digest
            evidence[evidence_key] = digest
        write(evidence_path, evidence)
        submission["evaluation"]["evidence_sha256"] = validator.sha256_file(evidence_path)
        write(self.path, submission)
        self.manifest = load(self.root / "leaderboard/manifest.json")
        # With no published rows, the feed builder uses the release date as
        # its fallback. Keep that date stable across this empty-feed test.
        today = datetime.now(timezone.utc).date().isoformat() + "T00:00:00Z"
        self.manifest["generated_at"] = today
        self.manifest["data_release"]["generated_at"] = today
        write(self.root / "leaderboard/manifest.json", self.manifest)
        for module in (validator, manager):
            self.stack.enter_context(patch.object(module, "ROOT", self.root))
            self.stack.enter_context(patch.object(module, "MANIFEST_PATH", self.root / "leaderboard/manifest.json"))
        for name in ("CLAIMS_ROOT", "CLAIMS_INDEX_PATH", "REVISION_HISTORY_PATH"):
            relative = getattr(manager, name).relative_to(SOURCE_ROOT)
            self.stack.enter_context(patch.object(manager, name, self.root / relative))

    def validate(self, **kwargs):
        return validator.validate_submission_file(self.path, self.manifest, **kwargs)

    def test_complete_candidate_passes_contributor_and_repository_intake(self):
        for contributor in (False, True):
            with self.subTest(contributor=contributor):
                errors, stats = self.validate(dev_intake=True, contributor_stage=contributor)
                self.assertEqual(errors, [])
                self.assertEqual(stats, {"cases": 50, "series": 350})
        errors, totals = validator.validate_many(dev_intake=True, manifest=self.manifest)
        self.assertEqual(errors, [])
        self.assertEqual(totals["submissions"], 1)
        self.assertEqual(manager.source_rows_by_dataset(self.manifest)["AhmedML"], [])

    def test_normal_and_production_validation_still_reject_candidate(self):
        for contributor in (False, True):
            errors, _ = self.validate(contributor_stage=contributor)
            self.assertIn("submissions are closed", "\n".join(errors))
        for key, value in (("source_ref", "main"), ("status", "official")):
            with self.subTest(key=key):
                original = copy.deepcopy(self.manifest)
                self.manifest["data_release"][key] = value
                errors, _ = self.validate(dev_intake=True)
                self.assertIn("requires the prototype dev release", "\n".join(errors))
                self.manifest = original

    def test_intake_rejects_maintainer_metadata(self):
        (self.directory / "maintainer-validation.json").write_text("{}")
        errors, _ = self.validate(dev_intake=True, contributor_stage=True)
        self.assertIn("must not contain maintainer-validation.json", "\n".join(errors))

    def test_intake_rejects_changed_profile_bytes(self):
        with (self.directory / "profiles/chunk-000.json").open("a") as output:
            output.write(" ")
        errors, _ = self.validate(dev_intake=True)
        self.assertIn("profile chunk digest differs", "\n".join(errors))

    def test_intake_rejects_fixture_methodology(self):
        submission = load(self.path)
        submission["methodology"]["record_kind"] = "prototype_fixture"
        write(self.path, submission)
        errors, _ = self.validate(dev_intake=True)
        self.assertIn("genuine-inference", "\n".join(errors))

    def test_intake_rejects_missing_inference_attestation(self):
        path = self.directory / "evaluation-evidence.json"
        evidence = load(path)
        evidence["notes"] = "No inference attestation"
        write(path, evidence)
        submission = load(self.path)
        submission["evaluation"]["evidence_sha256"] = validator.sha256_file(path)
        write(self.path, submission)
        errors, _ = self.validate(dev_intake=True)
        self.assertIn("attestation differs", "\n".join(errors))

    def test_cli_and_generated_feed_check_accept_unpublished_candidate(self):
        with redirect_stdout(io.StringIO()) as output:
            result = validator.main(["--dev-intake", "--contributor-stage", str(self.directory)])
        self.assertEqual(result, 0)
        self.assertIn("DEV INTAKE VALID", output.getvalue())
        # Build/check from the same source set: the unapproved candidate must
        # not create a leaderboard row or require generated files in its PR.
        for command in ("build", "check"):
            with patch("sys.argv", ["manage_leaderboard.py", command, "--dev-intake"]), redirect_stdout(io.StringIO()):
                self.assertEqual(manager.main(), 0)
        self.assertEqual(load(self.root / "leaderboard/datasets/ahmedml.json"), [])
