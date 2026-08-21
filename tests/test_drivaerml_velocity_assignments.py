from __future__ import annotations

import hashlib
import json
import math
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from reference.drivaerml import velocity_assignments as velocity_assignments_module
from reference.drivaerml.autocfd5 import (
    VelocityCellAssignmentEvidence,
    VelocitySampleDefinition,
    load_autocfd5_definition,
)
from reference.drivaerml.velocity_assignments import (
    EVALUATE_POSITION_FAILURE_REASON_PREFIX,
    KERNEL_ID,
    NO_CLOSURE_CELL_REASON,
    QUERY_CACHE_KEY_ID,
    REQUIRED_NUMPY_VERSION,
    REQUIRED_PYTHON_VERSION,
    REQUIRED_VTK_VERSION,
    TOLERANCE_REPLAY_M,
    NativeContainingCellKernel,
    VelocityAssignmentError,
    _require_frozen_runtime,
    assignment_evidence_sha256,
    candidate_kernel_receipt,
    candidate_kernel_settings,
    generate_definition_velocity_samples,
    replay_assignment_tolerances,
    vtk_available,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "benchmark-specs" / "drivaerml" / "autocfd5-profiles-v8.json"
SOURCE_HASHES = ("a" * 64, "b" * 64)
VTK_READY = vtk_available()
SYNTHETIC_ASSIGNMENT_SHA256 = (
    "437f69f14282929a7a7ba2388f62ee3266a2611f3c25d7900752c9326333b404"
)
FULL_GRID_SHA256 = "46ffdde32e4892562d7e80e41a5727d50db22420efde26f17aa0db363b43a9f0"
KERNEL_SETTINGS_SHA256 = (
    "882371d517217698b8ba04d073aec8be171ec78d0bce8456abf4864043cb9ab0"
)

if VTK_READY:
    import vtk


def _sample_payload(samples: tuple[VelocitySampleDefinition, ...]) -> bytes:
    rows = [
        {
            "profile_id": row.profile_id,
            "sample_index": row.sample_index,
            "point_count": row.point_count,
            "line_fraction": row.line_fraction,
            "distance_m": row.distance_m,
            "point_m": list(row.point_m),
        }
        for row in samples
    ]
    return json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


class DrivAerMLVelocityGridDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definition = load_autocfd5_definition(PROFILE_PATH)

    def test_full_definition_generates_all_four_nested_grids(self) -> None:
        expected_counts = {
            0.001: 37_416,
            0.002: 18_716,
            0.005: 7_496,
            0.010: 3_756,
        }
        generated = {
            spacing: generate_definition_velocity_samples(self.definition, spacing)
            for spacing in expected_counts
        }
        self.assertEqual(
            {spacing: len(rows) for spacing, rows in generated.items()},
            expected_counts,
        )
        one_mm_by_line: dict[str, list[VelocitySampleDefinition]] = {}
        for row in generated[0.001]:
            one_mm_by_line.setdefault(row.profile_id, []).append(row)
        for spacing, stride in ((0.002, 2), (0.005, 5), (0.010, 10)):
            coarse_by_line: dict[str, list[VelocitySampleDefinition]] = {}
            for row in generated[spacing]:
                coarse_by_line.setdefault(row.profile_id, []).append(row)
            for profile_id, coarse in coarse_by_line.items():
                reference = one_mm_by_line[profile_id][::stride]
                self.assertEqual(len(coarse), len(reference))
                np.testing.assert_allclose(
                    [row.point_m for row in coarse],
                    [row.point_m for row in reference],
                    rtol=0.0,
                    atol=2.0e-15,
                )
                np.testing.assert_allclose(
                    [row.distance_m for row in coarse],
                    [row.distance_m for row in reference],
                    rtol=0.0,
                    atol=2.0e-15,
                )

        fixed = self.definition.velocity_samples
        ten_mm = generated[0.010]
        self.assertEqual(
            [(row.profile_id, row.sample_index, row.point_count) for row in ten_mm],
            [(row.profile_id, row.sample_index, row.point_count) for row in fixed],
        )
        np.testing.assert_allclose(
            [row.point_m for row in ten_mm],
            [row.point_m for row in fixed],
            rtol=0.0,
            atol=2.0e-11,
        )
        np.testing.assert_allclose(
            [row.distance_m for row in ten_mm],
            [row.distance_m for row in fixed],
            rtol=0.0,
            atol=2.0e-11,
        )
        self.assertEqual(
            hashlib.sha256(_sample_payload(ten_mm)).hexdigest(),
            FULL_GRID_SHA256,
        )

    def test_grid_generation_rejects_invalid_spacing(self) -> None:
        for value in (0.0, -0.001, math.nan, math.inf, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    VelocityAssignmentError, "finite and positive|numeric"
                ):
                    generate_definition_velocity_samples(self.definition, value)

    def test_candidate_settings_are_explicitly_not_frozen(self) -> None:
        settings = candidate_kernel_settings()
        self.assertEqual(settings["kernel_id"], KERNEL_ID)
        self.assertIn("candidate_pending", settings["status"])
        self.assertEqual(
            settings["selection"]["candidate_count"],
            "number_of_distinct_cells_passing_closure_predicate",
        )
        self.assertEqual(
            settings["required_tolerance_replay_m"], list(TOLERANCE_REPLAY_M)
        )
        self.assertFalse(settings["invalidity"]["snapping"])
        self.assertFalse(settings["invalidity"]["extrapolation"])


@unittest.skipUnless(VTK_READY, f"optional VTK {REQUIRED_VTK_VERSION} is unavailable")
class DrivAerMLVelocityContainingCellTests(unittest.TestCase):
    @staticmethod
    def _append_points(
        points: object, coordinates: list[tuple[float, float, float]]
    ) -> list[int]:
        return [points.InsertNextPoint(*coordinate) for coordinate in coordinates]

    @classmethod
    def mixed_grid(cls) -> object:
        points = vtk.vtkPoints()
        points.SetDataTypeToDouble()
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
                (2, 0, 0),
                (3, 0, 0),
                (3, 1, 0),
                (2, 1, 0),
                (2, 0, 1),
                (3, 0, 1),
                (3, 1, 1),
                (2, 1, 1),
            ],
        )
        grid.InsertNextCell(vtk.VTK_HEXAHEDRON, len(hexahedron), hexahedron)

        wedge = cls._append_points(
            points,
            [
                (4, 0, 0),
                (5, 0, 0),
                (4, 1, 0),
                (4, 0, 1),
                (5, 0, 1),
                (4, 1, 1),
            ],
        )
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
                (8, 0, 0),
                (9, 0, 0),
                (9, 1, 0),
                (8, 1, 0),
                (8, 0, 1),
                (9, 0, 1),
                (9, 1, 1),
                (8, 1, 1),
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
        return grid

    @staticmethod
    def two_hex_grid() -> object:
        points = vtk.vtkPoints()
        points.SetDataTypeToDouble()
        for point in (
            (0, 0, 0),
            (1, 0, 0),
            (1, 1, 0),
            (0, 1, 0),
            (0, 0, 1),
            (1, 0, 1),
            (1, 1, 1),
            (0, 1, 1),
            (2, 0, 0),
            (2, 1, 0),
            (2, 0, 1),
            (2, 1, 1),
        ):
            points.InsertNextPoint(*point)
        grid = vtk.vtkUnstructuredGrid()
        grid.SetPoints(points)
        grid.InsertNextCell(vtk.VTK_HEXAHEDRON, 8, [0, 1, 2, 3, 4, 5, 6, 7])
        grid.InsertNextCell(vtk.VTK_HEXAHEDRON, 8, [1, 8, 9, 2, 5, 10, 11, 6])
        return grid

    @staticmethod
    def sample(
        profile_id: str,
        sample_index: int,
        point_m: tuple[float, float, float],
    ) -> VelocitySampleDefinition:
        return VelocitySampleDefinition(
            profile_id=profile_id,
            sample_index=sample_index,
            point_count=2,
            line_fraction=0.0,
            distance_m=float(sample_index),
            point_m=point_m,
        )

    def test_all_five_native_cell_types_and_golden_evidence(self) -> None:
        grid = self.mixed_grid()
        cell_types_before = [grid.GetCellType(index) for index in range(5)]
        points_before = np.asarray(
            [grid.GetPoint(index) for index in range(grid.GetNumberOfPoints())]
        )
        samples = (
            self.sample("tetra", 0, (0.1, 0.1, 0.1)),
            self.sample("hex", 1, (2.5, 0.5, 0.5)),
            self.sample("wedge", 2, (4.2, 0.2, 0.5)),
            self.sample("pyramid", 3, (6.5, 0.5, 0.2)),
            self.sample("polyhedron", 4, (8.5, 0.5, 0.5)),
        )
        assignments = NativeContainingCellKernel(grid).assign(
            samples,
            case_id="synthetic_mixed",
            source_sha256=SOURCE_HASHES,
        )
        self.assertTrue(
            all(isinstance(row, VelocityCellAssignmentEvidence) for row in assignments)
        )
        self.assertEqual([row.raw_vtk_cell_id for row in assignments], list(range(5)))
        self.assertEqual([row.candidate_count for row in assignments], [1] * 5)
        self.assertTrue(all(row.valid and row.reason == "" for row in assignments))
        self.assertEqual(assignment_evidence_sha256(assignments), SYNTHETIC_ASSIGNMENT_SHA256)
        self.assertEqual(
            [grid.GetCellType(index) for index in range(5)], cell_types_before
        )
        np.testing.assert_array_equal(
            [grid.GetPoint(index) for index in range(grid.GetNumberOfPoints())],
            points_before,
        )
        self.assertEqual(grid.GetCellData().GetNumberOfArrays(), 0)

    def test_serial_vtk_query_objects_are_reused_with_exact_weight_lengths(self) -> None:
        kernel = NativeContainingCellKernel(
            self.mixed_grid(), query_cache_enabled=False
        )
        broad_ids_identity = id(kernel._broad_ids)
        generic_cell_identity = id(kernel._generic_cell)
        samples = (
            self.sample("tetra_first", 0, (0.1, 0.1, 0.1)),
            self.sample("tetra_second", 0, (0.2, 0.2, 0.2)),
            self.sample("hex", 0, (2.5, 0.5, 0.5)),
            self.sample("wedge", 0, (4.2, 0.2, 0.5)),
            self.sample("pyramid", 0, (6.5, 0.5, 0.2)),
            self.sample("polyhedron", 0, (8.5, 0.5, 0.5)),
        )
        assignments = kernel.assign(
            samples,
            case_id="synthetic_scratch_reuse",
            source_sha256=SOURCE_HASHES,
        )
        self.assertTrue(all(row.valid for row in assignments))
        self.assertEqual(id(kernel._broad_ids), broad_ids_identity)
        self.assertEqual(id(kernel._generic_cell), generic_cell_identity)
        self.assertEqual(set(kernel._evaluation_scratch), {4, 5, 6, 8})
        for point_count, scratch in kernel._evaluation_scratch.items():
            self.assertEqual(len(scratch[-1]), point_count)

    def test_shared_face_enumerates_both_and_selects_smallest_raw_id(self) -> None:
        kernel = NativeContainingCellKernel(self.two_hex_grid())
        assignments = kernel.assign(
            (self.sample("face", 0, (1.0, 0.5, 0.5)),),
            case_id="synthetic_face",
            source_sha256=SOURCE_HASHES,
        )
        self.assertEqual(assignments[0].candidate_count, 2)
        self.assertEqual(assignments[0].raw_vtk_cell_id, 0)

    def test_input_order_is_preserved(self) -> None:
        kernel = NativeContainingCellKernel(self.two_hex_grid())
        samples = (
            self.sample("second_cell_first", 7, (1.5, 0.5, 0.5)),
            self.sample("first_cell_second", 3, (0.5, 0.5, 0.5)),
        )
        assignments = kernel.assign(
            samples,
            case_id="synthetic_order",
            source_sha256=SOURCE_HASHES,
        )
        self.assertEqual(
            [(row.profile_id, row.sample_index) for row in assignments],
            [("second_cell_first", 7), ("first_cell_second", 3)],
        )
        self.assertEqual([row.raw_vtk_cell_id for row in assignments], [1, 0])

    def test_cached_and_uncached_assignments_and_hashes_are_identical(self) -> None:
        samples = (
            self.sample("inside_first", 0, (0.5, 0.5, 0.5)),
            self.sample("inside_duplicate", 0, (0.5, 0.5, 0.5)),
            self.sample("outside_first", 0, (-2.0, 0.5, 0.5)),
            self.sample("outside_duplicate", 0, (-2.0, 0.5, 0.5)),
        )
        cached_kernel = NativeContainingCellKernel(
            self.two_hex_grid(), query_cache_enabled=True
        )
        uncached_kernel = NativeContainingCellKernel(
            self.two_hex_grid(), query_cache_enabled=False
        )
        cached = cached_kernel.assign(
            samples,
            case_id="synthetic_cached",
            source_sha256=SOURCE_HASHES,
        )
        uncached = uncached_kernel.assign(
            samples,
            case_id="synthetic_cached",
            source_sha256=SOURCE_HASHES,
        )
        self.assertEqual(cached, uncached)
        self.assertEqual(
            assignment_evidence_sha256(cached),
            assignment_evidence_sha256(uncached),
        )
        self.assertEqual(
            cached_kernel.query_cache_audit(),
            {
                "enabled": True,
                "key_id": QUERY_CACHE_KEY_ID,
                "total_rows": 4,
                "unique_query_keys": 2,
                "cache_hits": 2,
            },
        )
        self.assertEqual(
            uncached_kernel.query_cache_audit(),
            {
                "enabled": False,
                "key_id": QUERY_CACHE_KEY_ID,
                "total_rows": 4,
                "unique_query_keys": 2,
                "cache_hits": 0,
            },
        )

    def test_cache_retains_failure_rows_and_uses_exact_xyz_tolerance_keys(self) -> None:
        exact = (0.5, 0.5, 0.5)
        adjacent = (math.nextafter(0.5, math.inf), 0.5, 0.5)
        samples = (
            self.sample("exact_first", 0, exact),
            self.sample("exact_duplicate", 0, exact),
            self.sample("adjacent_binary64", 0, adjacent),
        )
        cached_kernel = NativeContainingCellKernel(self.two_hex_grid())
        with patch.object(
            cached_kernel,
            "_closure_candidates",
            return_value=((0,), (1,)),
        ) as cached_query:
            cached = cached_kernel.assign(
                samples,
                case_id="synthetic_failure_cache",
                source_sha256=SOURCE_HASHES,
            )
            cached_kernel.assign(
                (self.sample("different_tolerance", 0, exact),),
                case_id="synthetic_failure_cache",
                source_sha256=SOURCE_HASHES,
                tolerance_m=2.0e-6,
            )
        self.assertEqual(cached_query.call_count, 3)
        self.assertTrue(all(not row.valid for row in cached))
        self.assertTrue(all(row.raw_vtk_cell_id is None for row in cached))
        self.assertTrue(all(row.candidate_count == 1 for row in cached))
        self.assertTrue(
            all(
                row.reason == EVALUATE_POSITION_FAILURE_REASON_PREFIX + "1"
                for row in cached
            )
        )
        self.assertEqual(
            cached_kernel.query_cache_audit(),
            {
                "enabled": True,
                "key_id": QUERY_CACHE_KEY_ID,
                "total_rows": 4,
                "unique_query_keys": 3,
                "cache_hits": 1,
            },
        )

        uncached_kernel = NativeContainingCellKernel(
            self.two_hex_grid(), query_cache_enabled=False
        )
        with patch.object(
            uncached_kernel,
            "_closure_candidates",
            return_value=((0,), (1,)),
        ) as uncached_query:
            uncached = uncached_kernel.assign(
                samples,
                case_id="synthetic_failure_cache",
                source_sha256=SOURCE_HASHES,
            )
        self.assertEqual(uncached_query.call_count, 3)
        self.assertEqual(cached, uncached)
        self.assertEqual(
            assignment_evidence_sha256(cached),
            assignment_evidence_sha256(uncached),
        )

    def test_invalid_rows_are_retained_with_owner_reasons(self) -> None:
        kernel = NativeContainingCellKernel(self.two_hex_grid())
        samples = (
            self.sample("outside", 0, (-2.0, 0.5, 0.5)),
            self.sample("solid", 0, (4.0, 0.5, 0.5)),
            self.sample("masked_inside", 0, (0.5, 0.5, 0.5)),
            self.sample("unclassified", 0, (5.0, 0.5, 0.5)),
        )
        invalid_reasons = {
            ("outside", 0): "outside_released_fluid_domain",
            ("solid", 0): "inside_morphed_solid",
            ("masked_inside", 0): "inside_morphed_solid",
        }
        assignments = kernel.assign(
            samples,
            case_id="synthetic_invalid",
            source_sha256=SOURCE_HASHES,
            invalid_reasons=invalid_reasons,
        )
        self.assertEqual(
            [row.reason for row in assignments],
            [
                "outside_released_fluid_domain",
                "inside_morphed_solid",
                "inside_morphed_solid",
                NO_CLOSURE_CELL_REASON,
            ],
        )
        self.assertEqual([row.candidate_count for row in assignments], [0, 0, 1, 0])
        self.assertTrue(all(not row.valid for row in assignments))
        self.assertTrue(all(row.raw_vtk_cell_id is None for row in assignments))

    def test_evaluate_position_failure_is_retained_as_invalid(self) -> None:
        kernel = NativeContainingCellKernel(self.two_hex_grid())
        sample = self.sample("evaluation_failure", 0, (0.5, 0.5, 0.5))
        with patch.object(
            kernel,
            "_closure_candidates",
            return_value=((0,), (1,)),
        ):
            assignment = kernel.assign(
                (sample,),
                case_id="synthetic_evaluation_failure",
                source_sha256=SOURCE_HASHES,
            )[0]
        self.assertFalse(assignment.valid)
        self.assertIsNone(assignment.raw_vtk_cell_id)
        self.assertEqual(assignment.candidate_count, 1)
        self.assertEqual(
            assignment.reason,
            EVALUATE_POSITION_FAILURE_REASON_PREFIX + "1",
        )

    def test_half_one_two_micrometre_replay_is_tolerance_sensitive(self) -> None:
        kernel = NativeContainingCellKernel(self.two_hex_grid())
        # 1.5 micrometres from the x=0 face: accepted only at 2 micrometres.
        sample = self.sample("tolerance", 0, (-1.5e-6, 0.5, 0.5))
        replay = replay_assignment_tolerances(
            kernel,
            (sample,),
            case_id="synthetic_tolerance",
            source_sha256=SOURCE_HASHES,
        )
        self.assertEqual(replay.tolerances_m, TOLERANCE_REPLAY_M)
        self.assertEqual(
            [rows[0].valid for rows in replay.assignments_by_tolerance],
            [False, False, True],
        )
        self.assertEqual(
            [rows[0].raw_vtk_cell_id for rows in replay.assignments_by_tolerance],
            [None, None, 0],
        )
        self.assertEqual(
            [rows[0].candidate_count for rows in replay.assignments_by_tolerance],
            [0, 0, 1],
        )
        self.assertTrue(
            all(
                isinstance(rows[0], VelocityCellAssignmentEvidence)
                for rows in replay.assignments_by_tolerance
            )
        )
        receipt = replay.as_dict()
        self.assertEqual(receipt, replay.as_dict())
        self.assertEqual(receipt["status"], "candidate_not_frozen")
        self.assertEqual(receipt["kernel"]["versions"]["vtk"], REQUIRED_VTK_VERSION)
        self.assertEqual(
            [row["valid_count"] for row in receipt["tolerances"]], [0, 0, 1]
        )

    def test_unsupported_and_nonfinite_geometry_fail_closed(self) -> None:
        points = vtk.vtkPoints()
        points.SetDataTypeToDouble()
        for point in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)):
            points.InsertNextPoint(*point)
        unsupported = vtk.vtkUnstructuredGrid()
        unsupported.SetPoints(points)
        unsupported.InsertNextCell(vtk.VTK_QUAD, 4, [0, 1, 2, 3])
        with self.assertRaisesRegex(VelocityAssignmentError, "unsupported native cell type"):
            NativeContainingCellKernel(unsupported)

        nonfinite_points = vtk.vtkPoints()
        nonfinite_points.SetDataTypeToDouble()
        for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, math.nan)):
            nonfinite_points.InsertNextPoint(*point)
        nonfinite = vtk.vtkUnstructuredGrid()
        nonfinite.SetPoints(nonfinite_points)
        nonfinite.InsertNextCell(vtk.VTK_TETRA, 4, [0, 1, 2, 3])
        with self.assertRaisesRegex(VelocityAssignmentError, "non-finite coordinates"):
            NativeContainingCellKernel(nonfinite)

    def test_duplicate_samples_and_bad_owner_mask_fail_closed(self) -> None:
        kernel = NativeContainingCellKernel(self.two_hex_grid())
        sample = self.sample("duplicate", 0, (0.5, 0.5, 0.5))
        with self.assertRaisesRegex(VelocityAssignmentError, "duplicate"):
            kernel.assign(
                (sample, sample),
                case_id="synthetic",
                source_sha256=SOURCE_HASHES,
            )
        with self.assertRaisesRegex(VelocityAssignmentError, "unexpected sample key"):
            kernel.assign(
                (sample,),
                case_id="synthetic",
                source_sha256=SOURCE_HASHES,
                invalid_reasons={("missing", 0): "inside_morphed_solid"},
            )
        with self.assertRaisesRegex(VelocityAssignmentError, "unsupported owner"):
            kernel.assign(
                (sample,),
                case_id="synthetic",
                source_sha256=SOURCE_HASHES,
                invalid_reasons={("duplicate", 0): "guessed_reason"},
            )

    def test_runtime_receipt_pins_exact_vtk_and_settings_hash(self) -> None:
        receipt = candidate_kernel_receipt()
        self.assertEqual(receipt["versions"]["vtk"], REQUIRED_VTK_VERSION)
        self.assertEqual(receipt["versions"]["vtk_source"], "vtk version 9.5.2")
        self.assertEqual(receipt["settings"], candidate_kernel_settings())
        self.assertEqual(receipt["settings_sha256"], KERNEL_SETTINGS_SHA256)


class DrivAerMLVelocityAssignmentOptionalDependencyTests(unittest.TestCase):
    def test_python_and_numpy_mismatches_fail_before_vtk(self) -> None:
        cases = (
            ("python", "Python 3.12.13, got 3.12.12"),
            ("numpy", "NumPy 2.2.6, got 2.2.5"),
        )
        for mismatch, expected in cases:
            with self.subTest(mismatch=mismatch), patch.object(
                velocity_assignments_module.platform,
                "python_version",
                return_value=(
                    "3.12.12" if mismatch == "python" else REQUIRED_PYTHON_VERSION
                ),
            ), patch.object(
                velocity_assignments_module.np,
                "__version__",
                "2.2.5" if mismatch == "numpy" else REQUIRED_NUMPY_VERSION,
            ), patch(
                "reference.drivaerml.velocity_assignments._require_vtk"
            ) as vtk_gate:
                with self.assertRaisesRegex(VelocityAssignmentError, expected):
                    _require_frozen_runtime()
                vtk_gate.assert_not_called()

    def test_exact_python_and_numpy_reach_vtk_gate(self) -> None:
        with patch.object(
            velocity_assignments_module.platform,
            "python_version",
            return_value=REQUIRED_PYTHON_VERSION,
        ), patch.object(
            velocity_assignments_module.np,
            "__version__",
            REQUIRED_NUMPY_VERSION,
        ), patch(
            "reference.drivaerml.velocity_assignments._require_vtk"
        ) as vtk_gate:
            _require_frozen_runtime()
        vtk_gate.assert_called_once_with()

    def test_vtk_source_identity_mismatch_fails_closed(self) -> None:
        fake_vtk = Mock()
        fake_vtk.vtkVersion.GetVTKVersion.return_value = REQUIRED_VTK_VERSION
        fake_vtk.vtkVersion.GetVTKSourceVersion.return_value = (
            "vtk version 9.5.2-custom"
        )
        with patch.object(
            velocity_assignments_module, "vtk", fake_vtk
        ), patch.object(
            velocity_assignments_module, "vtk_to_numpy", object()
        ), self.assertRaisesRegex(VelocityAssignmentError, "VTK source identity"):
            velocity_assignments_module._require_vtk()

    def test_optional_dependency_probe_is_boolean(self) -> None:
        self.assertIsInstance(vtk_available(), bool)


if __name__ == "__main__":
    unittest.main()
