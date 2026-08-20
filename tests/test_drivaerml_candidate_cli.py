from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from reference.drivaerml.diagnostic_evaluator import (
    DrivAerDiagnosticEvaluatorError,
)
from scripts import evaluate_drivaerml_candidate_diagnostics as diagnostic_cli


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_drivaerml_candidate_case.py"


class DrivAerMLCandidateCLITests(unittest.TestCase):
    def test_help_is_candidate_only_and_lists_both_transports(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("closed candidate evaluator", completed.stdout)
        self.assertIn("--monolithic-vtu", completed.stdout)
        self.assertIn("--multipart", completed.stdout)
        self.assertIn("--surface-prediction-manifest", completed.stdout)
        self.assertIn("--volume-prediction-manifest", completed.stdout)
        for obsolete_option in (
            "--volume-weight-npy",
            "--volume-weight-receipt",
            "--volume-weight-aggregate",
            "--pilot-volume-weight-aggregate-sha256",
            "--allow-incomplete-volume-weight-pilot",
            "--volume-weight-sha256",
        ):
            self.assertNotIn(obsolete_option, completed.stdout)

    def test_diagnostic_boundary_reader_rejects_path_replacement_without_redirect(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boundary = root / "boundary.vtp"
            replacement = root / "replacement.vtp"
            original = b"pinned-native-boundary-bytes"
            boundary.write_bytes(original)
            replacement.write_bytes(b"replacement-path-bytes")
            expected = hashlib.sha256(original).hexdigest()
            observed: dict[str, bytes] = {}

            def reader(descriptor_path: Path, raw_ids: object) -> object:
                self.assertEqual(tuple(raw_ids), (3, 9))
                os.replace(replacement, boundary)
                observed["bytes"] = descriptor_path.read_bytes()
                return object()

            with self.assertRaisesRegex(
                DrivAerDiagnosticEvaluatorError,
                "changed while all hashing and parser passes ran",
            ):
                diagnostic_cli._read_verified_boundary_pressure(
                    boundary,
                    (3, 9),
                    expected_sha256=expected,
                    chunk_bytes=7,
                    reader=reader,
                )
            self.assertEqual(observed["bytes"], original)
            self.assertEqual(boundary.read_bytes(), b"replacement-path-bytes")

    def test_diagnostic_boundary_reader_rejects_in_place_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            boundary = Path(temporary) / "boundary.vtp"
            original = b"pinned-native-boundary-bytes"
            boundary.write_bytes(original)
            expected = hashlib.sha256(original).hexdigest()

            def mutating_reader(descriptor_path: Path, raw_ids: object) -> object:
                del descriptor_path, raw_ids
                boundary.write_bytes(b"mutated-native-boundary")
                return object()

            with self.assertRaisesRegex(
                DrivAerDiagnosticEvaluatorError,
                "changed while all hashing and parser passes ran",
            ):
                diagnostic_cli._read_verified_boundary_pressure(
                    boundary,
                    (0,),
                    expected_sha256=expected,
                    chunk_bytes=5,
                    reader=mutating_reader,
                )


if __name__ == "__main__":
    unittest.main()
