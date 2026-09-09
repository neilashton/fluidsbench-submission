from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from reference import airfrans_handover as handover


class AirfransHandoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.predictions = self.root / "predictions"
        self.dataset = self.root / "Dataset"
        self.split, self.digest = handover.load_official_split("full")
        self.case_id = self.split["case_ids"][0]
        self.arrays = {
            "velocity": np.array([[20., 1.], [21., 2.], [22., 3.]]),
            "pressure": np.array([1., 2., 3.]),
            "airfoil_pressure": np.array([4., 5.]),
            "internal_points": np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]),
            "airfoil_points": np.array([[0., 0., 0.], [1., 0., 0.]]),
        }

    def write(self, case_id: str | None = None) -> Path:
        return handover.write_case(self.predictions, case_id or self.case_id, **self.arrays)

    def make_mock_meshes(self, case_id: str) -> None:
        root = self.dataset / case_id
        root.mkdir(parents=True)
        (root / f"{case_id}_internal.vtu").write_text("unit-test internal mesh")
        (root / f"{case_id}_aerofoil.vtp").write_text("unit-test airfoil mesh")

    def mock_points(self, path: Path) -> np.ndarray:
        return self.arrays["internal_points" if path.suffix == ".vtu" else "airfoil_points"]

    def small_split_check(self) -> dict:
        # Synthetic one-case split only for focused unit tests. The public CLI
        # has no partial-case switch and always loads the real official index.
        small_split = {**self.split, "case_ids": [self.case_id], "case_count": 1}
        with patch.object(handover, "load_official_split", return_value=(small_split, self.digest)):
            with patch.object(handover, "read_mesh_points", side_effect=self.mock_points):
                return handover.check_handover(self.predictions, self.dataset, "full")

    def test_official_lists_have_expected_counts_and_are_hash_checked(self) -> None:
        for split_id, count in (("full", 200), ("aoa_extrapolation", 196)):
            split, _ = handover.load_official_split(split_id)
            self.assertEqual(len(split["case_ids"]), count)
        with patch.object(handover, "sha256_file", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "checksum"):
                handover.load_official_split("full")
        with self.assertRaisesRegex(ValueError, "Unknown"):
            handover.load_official_split("../full")

    def test_case_round_trip_preserves_supplied_predictions(self) -> None:
        path = self.write()
        with np.load(path, allow_pickle=False) as data:
            self.assertEqual(set(data.files), handover.ARRAY_NAMES)
            for key, array in self.arrays.items():
                np.testing.assert_array_equal(data[key], array)
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.write()
        self.assertEqual(path.read_bytes(), before)

    def test_rejects_missing_field_invalid_values_and_partial_points(self) -> None:
        bad = dict(self.arrays)
        del bad["airfoil_pressure"]
        with self.assertRaisesRegex(ValueError, "missing"):
            handover.validate_arrays(bad)
        for replacement in [np.zeros((2, 2)), np.full((3, 2), np.nan),
                            np.full((3, 2), np.inf), np.ones((3, 2), dtype=complex),
                            np.ones((3, 2), dtype=object), np.ones((3, 2), dtype=bool)]:
            with self.subTest(replacement=replacement.dtype):
                with self.assertRaises(ValueError):
                    handover.validate_arrays({**self.arrays, "velocity": replacement})
        with self.assertRaisesRegex(ValueError, "without a path"):
            self.write("airFoil2D_../../escape")

    def test_one_case_does_not_pass_full_split(self) -> None:
        self.write()
        self.make_mock_meshes(self.case_id)
        with patch.object(handover, "read_mesh_points", side_effect=self.mock_points):
            result = handover.check_handover(self.predictions, self.dataset, "full")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["expected_case_count"], 200)
        self.assertEqual(result["checked_case_count"], 1)
        self.assertTrue(any("missing prediction cases" in error for error in result["errors"]))

    def test_full_official_case_coverage_records_source_and_prediction_hashes(self) -> None:
        for case_id in self.split["case_ids"]:
            self.write(case_id)
            self.make_mock_meshes(case_id)
        with patch.object(handover, "read_mesh_points", side_effect=self.mock_points):
            result = handover.check_handover(self.predictions, self.dataset, "full")
        self.assertEqual(result["status"], "complete_handover")
        self.assertEqual(result["checked_case_count"], 200)
        self.assertFalse(result["benchmark_approval"])
        self.assertEqual(result["split_sha256"], self.digest)
        self.assertEqual(result["cases"][0]["prediction_sha256"], handover.sha256_file(self.predictions / f"{self.case_id}.npz"))
        self.assertEqual(result["cases"][0]["internal_point_count"], 3)
        self.assertEqual(result["cases"][0]["airfoil_point_count"], 2)
        self.write("airFoil2D_unexpected")
        with patch.object(handover, "read_mesh_points", side_effect=self.mock_points):
            self.assertIn("unexpected prediction cases", handover.check_handover(self.predictions, self.dataset, "full")["errors"][0])

    def test_reordered_or_rounded_coordinates_fail(self) -> None:
        self.make_mock_meshes(self.case_id)
        for name in ["internal_points", "airfoil_points"]:
            for values in [self.arrays[name][::-1], self.arrays[name] + 1e-7]:
                with self.subTest(array=name):
                    path = handover.write_case(self.predictions, self.case_id, **{**self.arrays, name: values})
                    result = self.small_split_check()
                    self.assertEqual(result["status"], "failed")
                    self.assertIn("point order", result["errors"][0])
                    path.unlink()

    def test_corrupt_archive_is_reported_as_a_failed_case(self) -> None:
        self.predictions.mkdir()
        (self.predictions / f"{self.case_id}.npz").write_bytes(b"not an npz")
        self.assertEqual(self.small_split_check()["status"], "failed")

    def test_duplicate_archive_members_are_rejected(self) -> None:
        self.make_mock_meshes(self.case_id)
        path = self.write()
        buffer = io.BytesIO()
        np.save(buffer, self.arrays["velocity"], allow_pickle=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("velocity.npy", buffer.getvalue())
        result = self.small_split_check()
        self.assertEqual(result["status"], "failed")
        self.assertIn("duplicate", result["errors"][0])

    def test_cli_lists_real_cases_and_reports_failure_with_nonzero_exit(self) -> None:
        listed = subprocess.run([sys.executable, "-m", "reference.airfrans_handover", "list-cases", "--split-id", "full"], cwd=handover.ROOT, text=True, capture_output=True)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(listed.stdout.splitlines(), self.split["case_ids"])
        report_path = self.root / "report.json"
        command = [sys.executable, "-m", "reference.airfrans_handover", "check", "--split-id", "full", "--predictions-root", str(self.predictions), "--dataset-root", str(self.dataset), "--report", str(report_path)]
        failed = subprocess.run(command, cwd=handover.ROOT, text=True, capture_output=True)
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(json.loads(report_path.read_text())["status"], "failed")
        previous = report_path.read_bytes()
        self.assertEqual(subprocess.run(command, cwd=handover.ROOT, capture_output=True).returncode, 1)
        self.assertEqual(report_path.read_bytes(), previous)

    @unittest.skipUnless(importlib.util.find_spec("pyvista"), "PyVista is optional for the native-mesh integration test")
    def test_real_vtk_serialization_and_native_mesh_reader(self) -> None:
        import pyvista as pv

        self.write()
        case_root = self.dataset / self.case_id
        case_root.mkdir(parents=True)
        mesh = pv.UnstructuredGrid(np.array([3, 0, 1, 2]), np.array([pv.CellType.TRIANGLE]), self.arrays["internal_points"])
        mesh.save(case_root / f"{self.case_id}_internal.vtu")
        curve = pv.PolyData(self.arrays["airfoil_points"], lines=np.array([2, 0, 1]))
        curve.save(case_root / f"{self.case_id}_aerofoil.vtp")
        small_split = {**self.split, "case_ids": [self.case_id], "case_count": 1}
        with patch.object(handover, "load_official_split", return_value=(small_split, self.digest)):
            result = handover.check_handover(self.predictions, self.dataset, "full")
        self.assertEqual(result["status"], "complete_handover", result["errors"])


if __name__ == "__main__":
    unittest.main()
