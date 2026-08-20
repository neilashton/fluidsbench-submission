from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from reference.drivaerml import volume_weights as volume_weights_module
from reference.drivaerml.volume_weights import (
    RAW_CELL_ID_ARRAY_NAME,
    REQUIRED_NUMPY_VERSION,
    REQUIRED_PYTHON_VERSION,
    REQUIRED_VTK_VERSION,
    UNBOUND_RECEIPT_SCHEMA,
    VOLUME_ARRAY_NAME,
    DrivAerVolumeWeightError,
    _validated_filter_output,
    _require_frozen_runtime,
    algorithm_settings,
    compute_volume_weights,
    generate_pinned_volume_weights,
    generate_volume_weights,
    read_geometry_only_vtu,
    sha256_file,
    vtk_available,
    write_volume_weights_npy,
)


VTK_READY = vtk_available()
MIXED_GOLDEN_NPY_SHA256 = "25a1b2e0e25d894ecb126786b356a8f5b875f2ccd2aae0a536a82e16528f01d5"
if VTK_READY:
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy


@unittest.skipUnless(VTK_READY, f"optional VTK {REQUIRED_VTK_VERSION} is unavailable")
class DrivAerMLVolumeWeightTests(unittest.TestCase):
    @staticmethod
    def _append_points(points: object, coordinates: list[tuple[float, float, float]]) -> list[int]:
        return [points.InsertNextPoint(*coordinate) for coordinate in coordinates]

    @classmethod
    def mixed_grid(cls) -> object:
        points = vtk.vtkPoints()
        grid = vtk.vtkUnstructuredGrid()
        grid.SetPoints(points)
        grid.Allocate(5)

        tetra = cls._append_points(
            points,
            [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)],
        )
        grid.InsertNextCell(vtk.VTK_TETRA, len(tetra), tetra)

        hexahedron = cls._append_points(
            points,
            [
                (2, 0, 0), (3, 0, 0), (3, 1, 0), (2, 1, 0),
                (2, 0, 1), (3, 0, 1), (3, 1, 1), (2, 1, 1),
            ],
        )
        grid.InsertNextCell(vtk.VTK_HEXAHEDRON, len(hexahedron), hexahedron)

        wedge = cls._append_points(
            points,
            [
                (4, 0, 0), (5, 0, 0), (4, 1, 0),
                (4, 0, 1), (5, 0, 1), (4, 1, 1),
            ],
        )
        # VTK's signed wedge convention requires the outward-oriented triangular
        # faces to use this ordering for the coordinates above.
        wedge_order = [wedge[index] for index in (0, 2, 1, 3, 5, 4)]
        grid.InsertNextCell(vtk.VTK_WEDGE, len(wedge_order), wedge_order)

        pyramid = cls._append_points(
            points,
            [(6, 0, 0), (7, 0, 0), (7, 1, 0), (6, 1, 0), (6.5, 0.5, 1)],
        )
        grid.InsertNextCell(vtk.VTK_PYRAMID, len(pyramid), pyramid)

        polyhedron = cls._append_points(
            points,
            [
                (8, 0, 0), (9, 0, 0), (9, 1, 0), (8, 1, 0),
                (8, 0, 1), (9, 0, 1), (9, 1, 1), (8, 1, 1),
            ],
        )
        faces = vtk.vtkCellArray()
        for local_face in (
            (0, 3, 2, 1),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
        ):
            face = [polyhedron[index] for index in local_face]
            faces.InsertNextCell(len(face), face)
        grid.InsertNextCell(
            vtk.VTK_POLYHEDRON,
            len(polyhedron),
            polyhedron,
            faces,
        )

        point_values = vtk.vtkDoubleArray()
        point_values.SetName("point_payload_that_must_not_load")
        point_values.SetNumberOfTuples(grid.GetNumberOfPoints())
        point_values.Fill(3.0)
        grid.GetPointData().AddArray(point_values)
        cell_values = vtk.vtkDoubleArray()
        cell_values.SetName("cell_payload_that_must_not_load")
        cell_values.SetNumberOfTuples(grid.GetNumberOfCells())
        cell_values.Fill(7.0)
        grid.GetCellData().AddArray(cell_values)
        return grid

    @staticmethod
    def write_vtu(grid: object, path: Path) -> None:
        writer = vtk.vtkXMLUnstructuredGridWriter()
        writer.SetFileName(str(path))
        writer.SetInputData(grid)
        writer.SetDataModeToAppended()
        writer.SetCompressorTypeToNone()
        if writer.Write() != 1:
            raise AssertionError("synthetic VTU writer failed")

    def test_mixed_native_cell_golden_and_compact_receipt(self) -> None:
        expected = np.asarray([1.0 / 6.0, 1.0, 0.5, 1.0 / 3.0, 1.0])
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = directory / "mixed.vtu"
            output = directory / "volumes.npy"
            receipt_path = directory / "volumes.json"
            self.write_vtu(self.mixed_grid(), source)

            geometry, audit = read_geometry_only_vtu(source)
            self.assertEqual(geometry.GetPointData().GetNumberOfArrays(), 0)
            self.assertEqual(geometry.GetCellData().GetNumberOfArrays(), 0)
            self.assertEqual(
                audit.disabled_point_arrays,
                ("point_payload_that_must_not_load",),
            )
            self.assertEqual(
                audit.disabled_cell_arrays,
                ("cell_payload_that_must_not_load",),
            )
            computation = compute_volume_weights(geometry, copy_chunk_size=2)
            np.testing.assert_array_equal(computation.raw_cell_ids, np.arange(5))
            np.testing.assert_allclose(computation.volumes_m3, expected, rtol=1e-14)
            self.assertEqual(
                {
                    computation.output_grid.GetCellData().GetArrayName(index)
                    for index in range(computation.output_grid.GetCellData().GetNumberOfArrays())
                },
                {RAW_CELL_ID_ARRAY_NAME, VOLUME_ARRAY_NAME},
            )

            receipt = generate_volume_weights(
                source,
                output,
                receipt_path,
                case_id="synthetic_mixed",
                copy_chunk_size=2,
            )
            loaded = np.load(output, allow_pickle=False)
            self.assertEqual(loaded.dtype.str, "<f8")
            np.testing.assert_allclose(loaded, expected, rtol=1e-14)
            self.assertEqual(receipt, json.loads(receipt_path.read_text(encoding="utf-8")))
            self.assertNotIn("\n ", receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["versions"]["vtk"], REQUIRED_VTK_VERSION)
            self.assertEqual(receipt["schema"], UNBOUND_RECEIPT_SCHEMA)
            self.assertIn("unbound_low_level", receipt["status"])
            self.assertEqual(receipt["algorithm"], algorithm_settings())
            self.assertEqual(receipt["execution"], {"copy_chunk_size": 2})
            self.assertEqual(receipt["output"]["cell_count"], 5)
            self.assertEqual(receipt["output"]["sha256"], sha256_file(output))
            self.assertEqual(receipt["output"]["sha256"], MIXED_GOLDEN_NPY_SHA256)
            self.assertAlmostEqual(receipt["output"]["volume_sum_m3"], 3.0)
            self.assertAlmostEqual(receipt["output"]["volume_min_m3"], 1.0 / 6.0)
            self.assertAlmostEqual(receipt["output"]["volume_max_m3"], 1.0)

    def test_degenerate_or_empty_cells_fail_closed(self) -> None:
        points = vtk.vtkPoints()
        for coordinate in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)):
            points.InsertNextPoint(*coordinate)
        degenerate = vtk.vtkUnstructuredGrid()
        degenerate.SetPoints(points)
        degenerate.InsertNextCell(vtk.VTK_TETRA, 4, [0, 1, 2, 3])
        with self.assertRaisesRegex(
            DrivAerVolumeWeightError,
            r"zero_count=1.*raw_cell_id.*vtk_cell_type_id.*10.*vtkTetra",
        ):
            compute_volume_weights(degenerate)

        # This otherwise valid wedge has VTK's opposite signed orientation.
        # Rejection proves that the candidate never takes an absolute value.
        wedge_points = vtk.vtkPoints()
        for coordinate in (
            (0, 0, 0), (1, 0, 0), (0, 1, 0),
            (0, 0, 1), (1, 0, 1), (0, 1, 1),
        ):
            wedge_points.InsertNextPoint(*coordinate)
        negative_wedge = vtk.vtkUnstructuredGrid()
        negative_wedge.SetPoints(wedge_points)
        negative_wedge.InsertNextCell(vtk.VTK_WEDGE, 6, [0, 1, 2, 3, 4, 5])
        with self.assertRaisesRegex(
            DrivAerVolumeWeightError,
            r"negative_count=1.*raw_cell_id.*vtk_cell_type_id.*13.*vtkWedge",
        ):
            compute_volume_weights(negative_wedge)

        empty = vtk.vtkUnstructuredGrid()
        empty.SetPoints(vtk.vtkPoints())
        with self.assertRaisesRegex(DrivAerVolumeWeightError, "no native volume cells"):
            compute_volume_weights(empty)

    def test_reordered_ids_and_invalid_output_values_fail_closed(self) -> None:
        computation = compute_volume_weights(self.mixed_grid())
        raw_array = computation.output_grid.GetCellData().GetArray(RAW_CELL_ID_ARRAY_NAME)
        raw_values = vtk_to_numpy(raw_array)
        raw_values[[0, 1]] = raw_values[[1, 0]]
        with self.assertRaisesRegex(DrivAerVolumeWeightError, "reordered"):
            _validated_filter_output(
                computation.output_grid,
                expected_cell_count=5,
                chunk_size=2,
            )

        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "bad.npy"
            for values, message in (
                (np.asarray([1.0, 0.0]), "strictly positive"),
                (np.asarray([1.0, -1.0]), "strictly positive"),
                (np.asarray([1.0, math.nan]), "finite"),
                (np.asarray([1.0, math.inf]), "finite"),
                (np.asarray(["one", "two"]), "numeric"),
            ):
                with self.subTest(message=message, values=values):
                    with self.assertRaisesRegex(DrivAerVolumeWeightError, message):
                        write_volume_weights_npy(values, output)
            self.assertFalse(output.exists())

    def test_path_shape_and_chunk_size_failures(self) -> None:
        with self.assertRaisesRegex(DrivAerVolumeWeightError, "does not exist"):
            read_geometry_only_vtu(Path("missing.vtu"))
        with self.assertRaisesRegex(DrivAerVolumeWeightError, "positive integer"):
            compute_volume_weights(self.mixed_grid(), copy_chunk_size=0)
        with tempfile.TemporaryDirectory() as directory_name:
            with self.assertRaisesRegex(DrivAerVolumeWeightError, ".npy suffix"):
                write_volume_weights_npy(
                    np.asarray([1.0]), Path(directory_name) / "volumes.bin"
                )

    def test_pinned_generation_reads_verified_descriptor_with_real_vtk(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            temporary_vtu = root / "source-for-bytes.vtu"
            self.write_vtu(self.mixed_grid(), temporary_vtu)
            pin_path, monolithic, _ = _make_pinned_monolithic_fixture(
                root, logical_bytes=temporary_vtu.read_bytes()
            )
            output = root / "pinned-volumes.npy"
            receipt_path = root / "pinned-volumes.json"

            receipt = generate_pinned_volume_weights(
                pin_path,
                root,
                "run_44",
                output,
                receipt_path,
                monolithic_vtu=monolithic,
                copy_chunk_size=2,
                source_verification_chunk_bytes=37,
            )

            self.assertEqual(receipt["output"]["cell_count"], 5)
            self.assertEqual(receipt["output"]["sha256"], MIXED_GOLDEN_NPY_SHA256)
            self.assertEqual(
                receipt["native_source_binding"]["verification"]["vtk_input"],
                "retained_verified_file_descriptor",
            )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _make_pinned_monolithic_fixture(
    root: Path, *, logical_bytes: bytes | None = None
) -> tuple[Path, Path, list[bytes]]:
    case_id = "run_44"
    boundary = b"synthetic-boundary"
    if logical_bytes is None:
        logical_bytes = b"synthetic reconstructed geometry bytes for source audit"
    parts = [logical_bytes[:11], logical_bytes[11:29], logical_bytes[29:]]
    logical_path = f"{case_id}/volume_44.vtu"
    part_records = [
        {
            "part_index": index,
            "path": f"{logical_path}.{index:02d}.part",
            "size_bytes": len(payload),
            "lfs_sha256": _sha256_bytes(payload),
        }
        for index, payload in enumerate(parts)
    ]
    boundary_sha = _sha256_bytes(boundary)
    pin = {
        "schema": "drivaerml-fluidsbench-public-native-source-pin-v1",
        "schema_version": 1,
        "repository": {
            "repo_id": "synthetic/drivaerml",
            "revision": "a" * 40,
        },
        "case_scope": {
            "case_count": 1,
            "run_number_min": 44,
            "run_number_max": 44,
            "unavailable_or_held_back_run_numbers": [],
        },
        "cases": [
            {
                "case_id": case_id,
                "run_number": 44,
                "boundary": {
                    "path": f"{case_id}/boundary_44.vtp",
                    "size_bytes": len(boundary),
                    "lfs_sha256": boundary_sha,
                },
                "surface_cell_area": {
                    "path": f"{case_id}/boundary_cell_area_44.npy",
                    "size_bytes": 132,
                    "lfs_sha256": _sha256_bytes(b"synthetic-area"),
                    "dtype": "<f4",
                    "element_count": 1,
                    "source_boundary_sha256": boundary_sha,
                },
                "volume": {
                    "logical_path_after_assembly": logical_path,
                    "part_count": len(parts),
                    "parts": part_records,
                    "total_size_bytes": len(logical_bytes),
                },
            }
        ],
        "totals": {
            "boundary_file_count": 1,
            "boundary_bytes": len(boundary),
            "surface_cell_area_file_count": 1,
            "surface_cell_area_bytes": 132,
            "logical_volume_count": 1,
            "volume_part_file_count": len(parts),
            "reconstructed_volume_bytes": len(logical_bytes),
        },
    }
    pin_path = root / "native-source-pin.json"
    pin_path.write_text(json.dumps(pin), encoding="utf-8")
    monolithic = root / "reconstructed.vtu"
    monolithic.write_bytes(logical_bytes)
    return pin_path, monolithic, parts


def _fake_artifacts(
    source: Path,
    output_npy: Path | str,
    *,
    copy_chunk_size: int,
) -> dict[str, object]:
    output_path = Path(output_npy)
    np.save(output_path, np.asarray([0.25, 0.75], dtype="<f8"))
    return {
        "output": {
            "file": output_path.name,
            "dtype": "<f8",
            "shape": [2],
            "size_bytes": output_path.stat().st_size,
            "sha256": sha256_file(output_path),
            "cell_count": 2,
            "volume_sum_m3": 1.0,
            "volume_min_m3": 0.25,
            "volume_max_m3": 0.75,
        },
        "versions": {
            "python": "test",
            "numpy": np.__version__,
            "vtk": "9.5.2",
            "vtk_source": "vtk version 9.5.2",
        },
        "algorithm": algorithm_settings(),
        "execution": {"copy_chunk_size": copy_chunk_size},
        "reader_audit": {
            "disabled_point_array_count": 0,
            "disabled_point_arrays": [],
            "disabled_cell_array_count": 2,
            "disabled_cell_arrays": ["pMeanTrim", "UMeanTrim"],
        },
    }


class DrivAerMLPinnedVolumeWeightSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        # These tests isolate immutable-source binding and mutation handling.
        # Production runtime enforcement has dedicated fail-before-I/O tests
        # below and real-VTK coverage above uses the actual frozen runtime.
        patcher = mock.patch(
            "reference.drivaerml.volume_weights._require_frozen_runtime"
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_exact_segments_are_verified_before_geometry_and_bound_path_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            pin_path, monolithic, parts = _make_pinned_monolithic_fixture(root)
            output = root / "weights.npy"
            receipt_path = root / "weights.json"
            vtk_source_audit: dict[str, object] = {}

            def capture_verified_source(
                source: Path,
                output_npy: Path | str,
                *,
                copy_chunk_size: int,
            ) -> dict[str, object]:
                vtk_source_audit["path"] = source
                vtk_source_audit["bytes"] = source.read_bytes()
                vtk_source_audit["identity"] = (
                    source.stat().st_dev,
                    source.stat().st_ino,
                )
                return _fake_artifacts(
                    source,
                    output_npy,
                    copy_chunk_size=copy_chunk_size,
                )

            with mock.patch(
                "reference.drivaerml.volume_weights._compute_volume_weight_artifacts",
                side_effect=capture_verified_source,
            ) as geometry_path:
                receipt = generate_pinned_volume_weights(
                    pin_path,
                    root,
                    "run_44",
                    output,
                    receipt_path,
                    monolithic_vtu=monolithic,
                    copy_chunk_size=7,
                    source_verification_chunk_bytes=5,
                )
            geometry_path.assert_called_once()
            vtk_source = vtk_source_audit["path"]
            self.assertIsInstance(vtk_source, Path)
            self.assertIn(vtk_source.parent, {Path("/proc/self/fd"), Path("/dev/fd")})
            self.assertNotEqual(vtk_source, monolithic)
            self.assertEqual(vtk_source_audit["bytes"], b"".join(parts))
            self.assertEqual(
                vtk_source_audit["identity"],
                (monolithic.stat().st_dev, monolithic.stat().st_ino),
            )
            binding = receipt["native_source_binding"]
            self.assertEqual(binding["pin"]["sha256"], sha256_file(pin_path))
            self.assertEqual(binding["pin"]["repository_id"], "synthetic/drivaerml")
            self.assertEqual(binding["pin"]["repository_revision"], "a" * 40)
            self.assertEqual(binding["case_id"], "run_44")
            self.assertEqual(
                binding["logical_volume"]["path"], "run_44/volume_44.vtu"
            )
            self.assertEqual(
                binding["logical_volume"]["ordered_verified_segments"],
                [
                    {
                        "part_index": index,
                        "size_bytes": len(payload),
                        "sha256": _sha256_bytes(payload),
                    }
                    for index, payload in enumerate(parts)
                ],
            )
            self.assertEqual(
                binding["verification"]["timing"],
                "completed_before_vtk_geometry_reader",
            )
            self.assertEqual(
                binding["verification"]["vtk_input"],
                "retained_verified_file_descriptor",
            )
            self.assertEqual(
                binding["verification"]["post_vtk_fstat"], "unchanged"
            )
            serialized = receipt_path.read_text(encoding="utf-8")
            self.assertNotIn(str(root), serialized)
            self.assertNotIn(monolithic.name, serialized)

    def test_same_size_tamper_is_rejected_before_geometry_filter_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            pin_path, monolithic, _ = _make_pinned_monolithic_fixture(root)
            tampered = bytearray(monolithic.read_bytes())
            tampered[17] ^= 0x01
            monolithic.write_bytes(tampered)
            output = root / "weights.npy"
            receipt_path = root / "weights.json"
            with mock.patch(
                "reference.drivaerml.volume_weights._compute_volume_weight_artifacts",
                side_effect=_fake_artifacts,
            ) as geometry_path, self.assertRaisesRegex(
                DrivAerVolumeWeightError, "SHA-256 mismatch"
            ):
                generate_pinned_volume_weights(
                    pin_path,
                    root,
                    "run_44",
                    output,
                    receipt_path,
                    monolithic_vtu=monolithic,
                    source_verification_chunk_bytes=4,
                )
            geometry_path.assert_not_called()
            self.assertFalse(output.exists())
            self.assertFalse(receipt_path.exists())

    def test_source_mutation_during_geometry_pass_fails_and_removes_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            pin_path, monolithic, _ = _make_pinned_monolithic_fixture(root)
            output = root / "weights.npy"
            receipt_path = root / "weights.json"

            def mutate_after_verified_read(
                source: Path,
                output_npy: Path | str,
                *,
                copy_chunk_size: int,
            ) -> dict[str, object]:
                self.assertEqual(source.read_bytes(), monolithic.read_bytes())
                result = _fake_artifacts(
                    source,
                    output_npy,
                    copy_chunk_size=copy_chunk_size,
                )
                with monolithic.open("ab") as handle:
                    handle.write(b"changed-during-vtk")
                    handle.flush()
                    os.fsync(handle.fileno())
                return result

            with mock.patch(
                "reference.drivaerml.volume_weights._compute_volume_weight_artifacts",
                side_effect=mutate_after_verified_read,
            ), self.assertRaisesRegex(
                DrivAerVolumeWeightError, "changed while VTK read"
            ):
                generate_pinned_volume_weights(
                    pin_path,
                    root,
                    "run_44",
                    output,
                    receipt_path,
                    monolithic_vtu=monolithic,
                    source_verification_chunk_bytes=4,
                )
            self.assertFalse(output.exists())
            self.assertFalse(receipt_path.exists())


class DrivAerMLVolumeWeightRuntimePreflightTests(unittest.TestCase):
    def test_python_and_numpy_mismatches_fail_before_source_io(self) -> None:
        cases = (
            ("python", "Python 3.12.13, got 3.12.12"),
            ("numpy", "NumPy 2.2.6, got 2.2.5"),
        )
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            for mismatch, expected in cases:
                with self.subTest(mismatch=mismatch), mock.patch.object(
                    volume_weights_module.platform,
                    "python_version",
                    return_value=(
                        "3.12.12" if mismatch == "python" else REQUIRED_PYTHON_VERSION
                    ),
                ), mock.patch.object(
                    volume_weights_module.np,
                    "__version__",
                    "2.2.5" if mismatch == "numpy" else REQUIRED_NUMPY_VERSION,
                ), mock.patch(
                    "reference.drivaerml.volume_weights.sha256_file"
                ) as source_hash, mock.patch(
                    "reference.drivaerml.volume_weights.load_native_source_pin"
                ) as source_pin, mock.patch(
                    "reference.drivaerml.volume_weights._compute_volume_weight_artifacts"
                ) as geometry:
                    with self.assertRaisesRegex(
                        DrivAerVolumeWeightError, expected
                    ):
                        generate_pinned_volume_weights(
                            root / "missing-pin.json",
                            root,
                            "run_1",
                            root / "weights.npy",
                            root / "receipt.json",
                            monolithic_vtu=root / "missing.vtu",
                        )
                    source_hash.assert_not_called()
                    source_pin.assert_not_called()
                    geometry.assert_not_called()

    def test_vtk_preflight_precedes_source_io(self) -> None:
        with mock.patch.object(
            volume_weights_module.platform,
            "python_version",
            return_value=REQUIRED_PYTHON_VERSION,
        ), mock.patch.object(
            volume_weights_module.np,
            "__version__",
            REQUIRED_NUMPY_VERSION,
        ), mock.patch(
            "reference.drivaerml.volume_weights._require_vtk",
            side_effect=DrivAerVolumeWeightError(
                "DrivAerML volume weights require VTK 9.5.2, got 9.4.2"
            ),
        ) as vtk_gate, mock.patch(
            "reference.drivaerml.volume_weights.sha256_file"
        ) as source_hash:
            with self.assertRaisesRegex(
                DrivAerVolumeWeightError, "VTK 9.5.2, got 9.4.2"
            ):
                generate_pinned_volume_weights(
                    "missing-pin.json",
                    ".",
                    "run_1",
                    "weights.npy",
                    "receipt.json",
                )
            vtk_gate.assert_called_once_with()
            source_hash.assert_not_called()

    def test_exact_python_and_numpy_reach_vtk_gate(self) -> None:
        with mock.patch.object(
            volume_weights_module.platform,
            "python_version",
            return_value=REQUIRED_PYTHON_VERSION,
        ), mock.patch.object(
            volume_weights_module.np,
            "__version__",
            REQUIRED_NUMPY_VERSION,
        ), mock.patch(
            "reference.drivaerml.volume_weights._require_vtk"
        ) as vtk_gate:
            _require_frozen_runtime()
        vtk_gate.assert_called_once_with()


class DrivAerMLVolumeWeightOptionalDependencyTests(unittest.TestCase):
    def test_vtk_source_identity_mismatch_fails_closed(self) -> None:
        fake_vtk = mock.Mock()
        fake_vtk.vtkVersion.GetVTKVersion.return_value = REQUIRED_VTK_VERSION
        fake_vtk.vtkVersion.GetVTKSourceVersion.return_value = (
            "vtk version 9.5.2-custom"
        )
        with mock.patch.object(
            volume_weights_module, "vtk", fake_vtk
        ), mock.patch.object(
            volume_weights_module, "vtk_to_numpy", object()
        ), self.assertRaisesRegex(
            DrivAerVolumeWeightError, "VTK source identity"
        ):
            volume_weights_module._require_vtk()

    def test_optional_dependency_probe_is_boolean(self) -> None:
        self.assertIsInstance(vtk_available(), bool)


if __name__ == "__main__":
    unittest.main()
