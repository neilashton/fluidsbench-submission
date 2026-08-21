"""Candidate native-cell assignments for DrivAerML velocity diagnostics.

This module implements the proposed AutoCFD5 containing-cell semantics without
changing the native ``vtkUnstructuredGrid``.  Raw cell IDs are the zero-based
indices accepted by ``vtkUnstructuredGrid.GetCell``.  A
``vtkCellTreeLocator`` supplies a broad phase using an explicitly expanded
point bound and exact native-cell axis-aligned-bounds intersection; every
returned cell is then evaluated with
``vtkGenericCell.EvaluatePosition``.  A cell is a closure candidate when VTK
reports the point inside or its finite Euclidean closest-point distance is no
larger than the absolute tolerance.  All closure candidates are retained for
the count and the smallest raw cell ID is selected.

The implementation remains a *candidate*: its settings and evidence are
designed for the required 0.5/1/2 micrometre replay, but this module does not
claim that the all-case replay, owner validity mask, or scientific approval is
complete.  VTK is optional at import time. Candidate evidence generation
requires exactly Python 3.12.13, NumPy 2.2.6, and VTK 9.5.2; low-level static
settings remain inspectable without that runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import struct
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .autocfd5 import (
    POINT_IN_CELL_CLOSURE_TOLERANCE_M,
    AutoCFD5Definition,
    VelocityCellAssignmentEvidence,
    VelocityLineDefinition,
    VelocitySampleDefinition,
)

try:  # VTK is an optional, separately pinned evaluator dependency.
    import vtk  # type: ignore[import-not-found]
    from vtk.util.numpy_support import vtk_to_numpy  # type: ignore[import-not-found]
except ImportError as error:  # pragma: no cover - exercised in the base environment.
    vtk = None
    vtk_to_numpy = None
    _VTK_IMPORT_ERROR: ImportError | None = error
else:
    _VTK_IMPORT_ERROR = None


REQUIRED_PYTHON_VERSION = "3.12.13"
REQUIRED_NUMPY_VERSION = "2.2.6"
REQUIRED_VTK_VERSION = "9.5.2"
REQUIRED_VTK_SOURCE_VERSION = "vtk version 9.5.2"
KERNEL_ID = "drivaerml-native-containing-cell-candidate-v3"
REPLAY_SCHEMA = "drivaerml-velocity-cell-tolerance-replay-candidate-v1"
DEFAULT_VALIDATION_CHUNK_SIZE = 1_000_000
TOLERANCE_REPLAY_M = (0.5e-6, 1.0e-6, 2.0e-6)
QUERY_CACHE_KEY_ID = "ieee754-binary64-big-endian-exact-xyz-tolerance-v1"
_QUERY_CACHE_KEY = struct.Struct(">dddd")
_CACHE_MISS = object()

# Integer values are stable VTK public constants and keep static settings
# inspectable even when the optional VTK wheel is absent.
SUPPORTED_CELL_TYPES = (
    (10, "VTK_TETRA"),
    (12, "VTK_HEXAHEDRON"),
    (13, "VTK_WEDGE"),
    (14, "VTK_PYRAMID"),
    (42, "VTK_POLYHEDRON"),
)
_SUPPORTED_CELL_TYPE_IDS = frozenset(code for code, _ in SUPPORTED_CELL_TYPES)
_FIXED_POINT_COUNTS = {10: 4, 12: 8, 13: 6, 14: 5}
OWNER_INVALID_REASONS = frozenset(
    {"inside_morphed_solid", "outside_released_fluid_domain"}
)
NO_CLOSURE_CELL_REASON = "no_native_cell_within_closure_tolerance"
EVALUATE_POSITION_FAILURE_REASON_PREFIX = (
    "vtk_evaluate_position_failed_for_broad_phase_cells:"
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class VelocityAssignmentError(ValueError):
    """Raised when the candidate geometry kernel cannot produce safe evidence."""


def _vtk_version() -> str | None:
    if vtk is None:
        return None
    return str(vtk.vtkVersion.GetVTKVersion())


def vtk_available() -> bool:
    """Return whether the exact optional VTK dependency is importable."""

    return _vtk_version() == REQUIRED_VTK_VERSION


def _require_vtk() -> None:
    if vtk is None or vtk_to_numpy is None:
        detail = f": {_VTK_IMPORT_ERROR}" if _VTK_IMPORT_ERROR is not None else ""
        raise VelocityAssignmentError(
            "DrivAerML velocity assignments require optional "
            f"VTK {REQUIRED_VTK_VERSION}{detail}"
        )
    actual = _vtk_version()
    if actual != REQUIRED_VTK_VERSION:
        raise VelocityAssignmentError(
            f"DrivAerML velocity assignments require VTK {REQUIRED_VTK_VERSION}, "
            f"got {actual}"
        )
    actual_source = str(vtk.vtkVersion.GetVTKSourceVersion())
    if actual_source != REQUIRED_VTK_SOURCE_VERSION:
        raise VelocityAssignmentError(
            "DrivAerML velocity assignments require VTK source identity "
            f"{REQUIRED_VTK_SOURCE_VERSION!r}, got {actual_source!r}"
        )


def _require_frozen_runtime() -> None:
    """Reject candidate evidence generation outside the aggregate runtime."""

    actual_python = platform.python_version()
    if actual_python != REQUIRED_PYTHON_VERSION:
        raise VelocityAssignmentError(
            "DrivAerML velocity assignment generation requires Python "
            f"{REQUIRED_PYTHON_VERSION}, got {actual_python}"
        )
    actual_numpy = np.__version__
    if actual_numpy != REQUIRED_NUMPY_VERSION:
        raise VelocityAssignmentError(
            "DrivAerML velocity assignment generation requires NumPy "
            f"{REQUIRED_NUMPY_VERSION}, got {actual_numpy}"
        )
    _require_vtk()


def _positive_finite(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise VelocityAssignmentError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise VelocityAssignmentError(f"{label} must be finite and positive")
    return result


def _positive_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise VelocityAssignmentError(f"{label} must be a positive integer")
    return value


def _source_hashes(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise VelocityAssignmentError(
            "source_sha256 must be a non-empty tuple of lowercase SHA-256 digests"
        )
    if any(
        not isinstance(item, str) or _SHA256_RE.fullmatch(item) is None
        for item in value
    ):
        raise VelocityAssignmentError(
            "source_sha256 must contain lowercase SHA-256 digests"
        )
    return value


def candidate_kernel_settings() -> dict[str, object]:
    """Return the complete proposed geometry and tie-break settings."""

    return {
        "kernel_id": KERNEL_ID,
        "status": "candidate_pending_all_case_replay_and_owner_approval",
        "required_dependency": {"vtk": REQUIRED_VTK_VERSION},
        "input": {
            "vtk_data_object": "vtkUnstructuredGrid",
            "association": "native_CellData",
            "mesh_transform": "none",
            "raw_vtk_cell_id": "zero_based_native_GetCell_index",
            "supported_cell_types": [
                {"vtk_type_id": code, "vtk_name": name}
                for code, name in SUPPORTED_CELL_TYPES
            ],
        },
        "candidate_discovery": {
            "class": "vtkCellTreeLocator",
            "method": "FindCellsWithinBounds",
            "query": (
                "exact_native_cell_axis_aligned_bounds_intersection_with_"
                "point_bounds_expanded_by_absolute_tolerance"
            ),
            "query_bounds_order": ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax"],
            "deduplicate_raw_cell_ids": True,
            "settings": {
                "automatic": True,
                "number_of_cells_per_node": 8,
                "number_of_build_buckets": 6,
                "cache_cell_bounds": True,
            },
        },
        "closure": {
            "cell_wrapper": "vtkGenericCell",
            "method": "EvaluatePosition",
            "acceptance": "inside_return_code_1_or_sqrt(dist2)<=absolute_tolerance_m",
            "distance": "Euclidean_closest_point_distance_in_metres",
            "evaluate_error_return_code": -1,
            "evaluate_error_action": (
                "retain_the_sample_as_invalid_and_record_sorted_failed_raw_cell_ids"
            ),
        },
        "selection": {
            "enumeration": "all_distinct_cells_passing_closure_predicate",
            "candidate_count": "number_of_distinct_cells_passing_closure_predicate",
            "tie_break": "smallest_raw_vtk_cell_id",
        },
        "invalidity": {
            "owner_reasons": sorted(OWNER_INVALID_REASONS),
            "no_closure_cell_reason": NO_CLOSURE_CELL_REASON,
            "snapping": False,
            "extrapolation": False,
            "owner_reason_overrides_geometric_selection": True,
        },
        "primary_tolerance_m": POINT_IN_CELL_CLOSURE_TOLERANCE_M,
        "required_tolerance_replay_m": list(TOLERANCE_REPLAY_M),
    }


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def candidate_kernel_receipt() -> dict[str, object]:
    """Return runtime versions plus a deterministic hash of static settings."""

    _require_frozen_runtime()
    settings = candidate_kernel_settings()
    return {
        "kernel_id": KERNEL_ID,
        "settings_sha256": hashlib.sha256(_canonical_json(settings)).hexdigest(),
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "vtk": _vtk_version(),
            "vtk_source": str(vtk.vtkVersion.GetVTKSourceVersion()),
        },
        "settings": settings,
    }


def generate_velocity_line_samples(
    line: VelocityLineDefinition,
    nominal_spacing_m: float,
) -> tuple[VelocitySampleDefinition, ...]:
    """Generate an endpoint-inclusive equal-arc grid at nominal spacing.

    The nearest integer number of segments is used and the actual spacing is
    therefore ``endpoint distance / segment_count``.  This exactly reproduces
    the proposed 1, 2, 5, and 10 mm grids, including the three oblique lines.
    """

    if not isinstance(line, VelocityLineDefinition):
        raise VelocityAssignmentError("line must be a VelocityLineDefinition")
    spacing = _positive_finite(nominal_spacing_m, "nominal_spacing_m")
    length = math.dist(line.start_m, line.end_m)
    if not math.isfinite(length) or length <= 0.0:
        raise VelocityAssignmentError("velocity line endpoint distance must be positive")
    segment_count = max(1, int(math.floor(length / spacing + 0.5)))
    point_count = segment_count + 1
    result: list[VelocitySampleDefinition] = []
    for sample_index in range(point_count):
        fraction = sample_index / segment_count
        if sample_index == 0:
            point = line.start_m
        elif sample_index == segment_count:
            point = line.end_m
        else:
            point = tuple(
                start + fraction * (end - start)
                for start, end in zip(line.start_m, line.end_m)
            )
        result.append(
            VelocitySampleDefinition(
                profile_id=line.profile_id,
                sample_index=sample_index,
                point_count=point_count,
                line_fraction=fraction,
                distance_m=fraction * length,
                point_m=point,
            )
        )
    return tuple(result)


def generate_definition_velocity_samples(
    definition: AutoCFD5Definition,
    nominal_spacing_m: float,
) -> tuple[VelocitySampleDefinition, ...]:
    """Generate a complete arbitrary-spacing grid in registry line order."""

    if not isinstance(definition, AutoCFD5Definition):
        raise VelocityAssignmentError("definition must be an AutoCFD5Definition")
    spacing = _positive_finite(nominal_spacing_m, "nominal_spacing_m")
    return tuple(
        sample
        for line in definition.velocity_lines
        for sample in generate_velocity_line_samples(line, spacing)
    )


def _validate_native_grid(grid: Any, *, chunk_size: int) -> tuple[int, int]:
    _require_vtk()
    chunk_size = _positive_integer(chunk_size, "validation_chunk_size")
    if grid is None or not hasattr(grid, "IsA") or not grid.IsA("vtkUnstructuredGrid"):
        raise VelocityAssignmentError("input must be a native vtkUnstructuredGrid")
    cell_count = int(grid.GetNumberOfCells())
    point_count = int(grid.GetNumberOfPoints())
    if cell_count < 1:
        raise VelocityAssignmentError("native volume geometry contains no cells")
    if point_count < 1 or grid.GetPoints() is None:
        raise VelocityAssignmentError("native volume geometry contains no points")

    point_data = grid.GetPoints().GetData()
    if point_data is None:
        raise VelocityAssignmentError("native point coordinates are unavailable")
    coordinates = np.asarray(vtk_to_numpy(point_data))
    if coordinates.shape != (point_count, 3):
        raise VelocityAssignmentError("native point coordinates must have shape [N, 3]")
    for start in range(0, point_count, chunk_size):
        if not np.all(np.isfinite(coordinates[start : start + chunk_size])):
            raise VelocityAssignmentError("native geometry contains non-finite coordinates")

    type_array = grid.GetCellTypesArray()
    if type_array is None:
        raise VelocityAssignmentError("native cell-type array is unavailable")
    cell_types = np.asarray(vtk_to_numpy(type_array))
    if cell_types.shape != (cell_count,):
        raise VelocityAssignmentError("native cell-type array has the wrong length")
    for start in range(0, cell_count, chunk_size):
        chunk = cell_types[start : start + chunk_size]
        supported = np.isin(chunk, tuple(_SUPPORTED_CELL_TYPE_IDS))
        if not np.all(supported):
            offset = int(np.flatnonzero(~supported)[0])
            raw_id = start + offset
            raise VelocityAssignmentError(
                "unsupported native cell type "
                f"{int(chunk[offset])} at raw VTK cell ID {raw_id}"
            )

    cells = grid.GetCells()
    if cells is None:
        raise VelocityAssignmentError("native cell connectivity is unavailable")
    offsets_array = cells.GetOffsetsArray()
    connectivity_array = cells.GetConnectivityArray()
    if offsets_array is None or connectivity_array is None:
        raise VelocityAssignmentError("native cell connectivity arrays are unavailable")
    offsets = np.asarray(vtk_to_numpy(offsets_array))
    connectivity = np.asarray(vtk_to_numpy(connectivity_array))
    if (
        offsets.shape != (cell_count + 1,)
        or int(offsets[0]) != 0
        or int(offsets[-1]) != connectivity.size
    ):
        raise VelocityAssignmentError("native cell offsets are malformed")
    point_counts = np.diff(offsets)
    if np.any(point_counts < 4):
        raw_id = int(np.flatnonzero(point_counts < 4)[0])
        raise VelocityAssignmentError(
            f"native cell {raw_id} has fewer than four connectivity points"
        )
    for cell_type, expected_count in _FIXED_POINT_COUNTS.items():
        wrong = (cell_types == cell_type) & (point_counts != expected_count)
        if np.any(wrong):
            raw_id = int(np.flatnonzero(wrong)[0])
            raise VelocityAssignmentError(
                f"native cell {raw_id} has the wrong point count for type {cell_type}"
            )
    if np.any((cell_types == 42) & (point_counts < 4)):
        raw_id = int(np.flatnonzero((cell_types == 42) & (point_counts < 4))[0])
        raise VelocityAssignmentError(f"native polyhedron {raw_id} is malformed")
    for start in range(0, connectivity.size, chunk_size):
        chunk = connectivity[start : start + chunk_size]
        invalid = (chunk < 0) | (chunk >= point_count)
        if np.any(invalid):
            raise VelocityAssignmentError("native cell connectivity has an invalid point ID")
    return point_count, cell_count


def _sample_key(sample: VelocitySampleDefinition) -> tuple[str, int]:
    return sample.profile_id, sample.sample_index


def _validated_samples(
    samples: Sequence[VelocitySampleDefinition],
) -> tuple[VelocitySampleDefinition, ...]:
    result = tuple(samples)
    if not result:
        raise VelocityAssignmentError("velocity samples cannot be empty")
    if any(not isinstance(sample, VelocitySampleDefinition) for sample in result):
        raise VelocityAssignmentError(
            "velocity samples must contain VelocitySampleDefinition records"
        )
    keys = [_sample_key(sample) for sample in result]
    if len(keys) != len(set(keys)):
        raise VelocityAssignmentError("velocity samples contain duplicate line/sample IDs")
    return result


def _validated_invalid_reasons(
    samples: tuple[VelocitySampleDefinition, ...],
    invalid_reasons: Mapping[tuple[str, int], str] | None,
) -> dict[tuple[str, int], str]:
    if invalid_reasons is None:
        return {}
    if not isinstance(invalid_reasons, Mapping):
        raise VelocityAssignmentError("invalid_reasons must be a mapping")
    result: dict[tuple[str, int], str] = {}
    sample_keys = {_sample_key(sample) for sample in samples}
    for key, reason in invalid_reasons.items():
        if key not in sample_keys:
            raise VelocityAssignmentError(
                f"owner invalidity mask contains an unexpected sample key: {key!r}"
            )
        if reason not in OWNER_INVALID_REASONS:
            raise VelocityAssignmentError(
                f"unsupported owner invalidity reason for {key!r}: {reason!r}"
            )
        result[key] = reason
    return result


class NativeContainingCellKernel:
    """Deterministic candidate locator over an unchanged native volume grid."""

    def __init__(
        self,
        grid: Any,
        *,
        validation_chunk_size: int = DEFAULT_VALIDATION_CHUNK_SIZE,
        query_cache_enabled: bool = True,
    ) -> None:
        if not isinstance(query_cache_enabled, bool):
            raise VelocityAssignmentError("query_cache_enabled must be a boolean")
        _, self.cell_count = _validate_native_grid(
            grid, chunk_size=validation_chunk_size
        )
        self.grid = grid
        self.locator = vtk.vtkCellTreeLocator()
        self.locator.SetAutomatic(True)
        self.locator.SetNumberOfCellsPerNode(8)
        self.locator.SetNumberOfBuckets(6)
        self.locator.SetCacheCellBounds(True)
        self.locator.SetDataSet(grid)
        self.locator.BuildLocator()
        if self.locator.GetDataSet() is not grid:
            raise VelocityAssignmentError("VTK locator did not retain the native grid")
        if (
            not bool(self.locator.GetAutomatic())
            or int(self.locator.GetNumberOfCellsPerNode()) != 8
            or int(self.locator.GetNumberOfBuckets()) != 6
            or not bool(self.locator.GetCacheCellBounds())
        ):
            raise VelocityAssignmentError(
                "VTK cell-tree locator did not retain the pinned build settings"
            )
        # Assignment is deliberately serial.  Reuse the VTK wrappers and the
        # point-count-specific mutable buffers across candidates: constructing
        # them inside the native-cell loop is disproportionately expensive on
        # the 147--163 million-cell pilot meshes and has no bearing on the
        # locator, closure, or raw-ID tie-break semantics.
        self._broad_ids = vtk.vtkIdList()
        self._generic_cell = vtk.vtkGenericCell()
        self._evaluation_scratch: dict[
            int,
            tuple[
                list[float],
                Any,
                list[float],
                Any,
                list[float],
            ],
        ] = {}
        self.query_cache_enabled = query_cache_enabled
        self._query_cache: dict[
            bytes, tuple[tuple[int, ...], tuple[int, ...]]
        ] = {}
        self._query_keys_seen: set[bytes] = set()
        self._query_total_rows = 0
        self._query_evaluation_count = 0

    @staticmethod
    def _exact_query_key(
        point_m: tuple[float, float, float], tolerance_m: float
    ) -> bytes:
        """Encode the exact binary64 XYZ/tolerance values without rounding."""

        return _QUERY_CACHE_KEY.pack(
            float(point_m[0]),
            float(point_m[1]),
            float(point_m[2]),
            float(tolerance_m),
        )

    def query_cache_audit(self) -> dict[str, object]:
        """Return deterministic counters without exposing local cache contents."""

        cache_hits = self._query_total_rows - self._query_evaluation_count
        if cache_hits < 0:  # Defensive invariant; unreachable through public calls.
            raise VelocityAssignmentError("containing-cell query counters are invalid")
        return {
            "enabled": self.query_cache_enabled,
            "key_id": QUERY_CACHE_KEY_ID,
            "total_rows": self._query_total_rows,
            "unique_query_keys": len(self._query_keys_seen),
            "cache_hits": cache_hits,
        }

    def _query_closure_candidates(
        self,
        point_m: tuple[float, float, float],
        tolerance_m: float,
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        key = self._exact_query_key(point_m, tolerance_m)
        self._query_total_rows += 1
        self._query_keys_seen.add(key)
        if self.query_cache_enabled:
            cached = self._query_cache.get(key, _CACHE_MISS)
            if cached is not _CACHE_MISS:
                return cached  # type: ignore[return-value]
        self._query_evaluation_count += 1
        result = self._closure_candidates(point_m, tolerance_m)
        if self.query_cache_enabled:
            self._query_cache[key] = result
        return result

    def _closure_candidates(
        self,
        point_m: tuple[float, float, float],
        tolerance_m: float,
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        bounds = [
            point_m[0] - tolerance_m,
            point_m[0] + tolerance_m,
            point_m[1] - tolerance_m,
            point_m[1] + tolerance_m,
            point_m[2] - tolerance_m,
            point_m[2] + tolerance_m,
        ]
        broad_ids = self._broad_ids
        broad_ids.Reset()
        self.locator.FindCellsWithinBounds(bounds, broad_ids)
        raw_ids = sorted(
            {int(broad_ids.GetId(index)) for index in range(broad_ids.GetNumberOfIds())}
        )
        accepted: list[int] = []
        evaluation_failures: list[int] = []
        tolerance_squared = tolerance_m * tolerance_m
        for raw_id in raw_ids:
            if raw_id < 0 or raw_id >= self.cell_count:
                raise VelocityAssignmentError(
                    f"VTK locator returned invalid raw cell ID {raw_id}"
                )
            cell = self._generic_cell
            self.grid.GetCell(raw_id, cell)
            cell_type = int(cell.GetCellType())
            if cell_type not in _SUPPORTED_CELL_TYPE_IDS:
                raise VelocityAssignmentError(
                    f"unsupported native cell type {cell_type} at raw VTK cell ID {raw_id}"
                )
            cell_point_count = int(cell.GetNumberOfPoints())
            scratch = self._evaluation_scratch.get(cell_point_count)
            if scratch is None:
                scratch = (
                    [0.0, 0.0, 0.0],
                    vtk.reference(0),
                    [0.0, 0.0, 0.0],
                    vtk.reference(0.0),
                    [0.0] * cell_point_count,
                )
                self._evaluation_scratch[cell_point_count] = scratch
            closest, sub_id, parametric, distance_squared, weights = scratch
            status = int(
                cell.EvaluatePosition(
                    point_m,
                    closest,
                    sub_id,
                    parametric,
                    distance_squared,
                    weights,
                )
            )
            if status == -1:
                # VTK documents -1 as a numerical evaluation failure.  This can
                # occur for a malformed/degenerate broad-phase cell even when
                # the query has another usable closure candidate.  Silently
                # dropping that cell could alter both containment and the
                # smallest-raw-ID tie break, so the caller retains the complete
                # sample as explicitly invalid and records every failed ID.
                evaluation_failures.append(raw_id)
                continue
            if status not in {0, 1}:
                raise VelocityAssignmentError(
                    "vtkGenericCell.EvaluatePosition returned undocumented code "
                    f"{status} for raw VTK cell ID {raw_id}"
                )
            distance2 = float(distance_squared)
            numeric_outputs = (*closest, *parametric, *weights, distance2)
            if not all(math.isfinite(float(value)) for value in numeric_outputs):
                raise VelocityAssignmentError(
                    "vtkGenericCell.EvaluatePosition returned non-finite geometry "
                    f"for raw VTK cell ID {raw_id}"
                )
            if distance2 < 0.0:
                raise VelocityAssignmentError(
                    "vtkGenericCell.EvaluatePosition returned a negative squared "
                    f"distance for raw VTK cell ID {raw_id}"
                )
            if status == 1 or distance2 <= tolerance_squared:
                accepted.append(raw_id)
        return tuple(accepted), tuple(evaluation_failures)

    def assign(
        self,
        samples: Sequence[VelocitySampleDefinition],
        *,
        case_id: str,
        source_sha256: tuple[str, ...],
        tolerance_m: float = POINT_IN_CELL_CLOSURE_TOLERANCE_M,
        invalid_reasons: Mapping[tuple[str, int], str] | None = None,
    ) -> tuple[VelocityCellAssignmentEvidence, ...]:
        """Assign samples in caller order and retain every invalid row."""

        if not isinstance(case_id, str) or not case_id.strip():
            raise VelocityAssignmentError("case_id must be a non-empty string")
        tolerance = _positive_finite(tolerance_m, "tolerance_m")
        hashes = _source_hashes(source_sha256)
        records = _validated_samples(samples)
        owner_invalid = _validated_invalid_reasons(records, invalid_reasons)
        result: list[VelocityCellAssignmentEvidence] = []
        for sample in records:
            candidates, evaluation_failures = self._query_closure_candidates(
                sample.point_m, tolerance
            )
            key = _sample_key(sample)
            owner_reason = owner_invalid.get(key)
            if owner_reason is not None:
                valid = False
                reason = owner_reason
                raw_cell_id = None
            elif evaluation_failures:
                valid = False
                reason = EVALUATE_POSITION_FAILURE_REASON_PREFIX + ",".join(
                    str(raw_id) for raw_id in evaluation_failures
                )
                raw_cell_id = None
            elif candidates:
                valid = True
                reason = ""
                raw_cell_id = candidates[0]
            else:
                valid = False
                reason = NO_CLOSURE_CELL_REASON
                raw_cell_id = None
            result.append(
                VelocityCellAssignmentEvidence(
                    case_id=case_id,
                    profile_id=sample.profile_id,
                    sample_index=sample.sample_index,
                    point_m=sample.point_m,
                    distance_m=sample.distance_m,
                    valid=valid,
                    reason=reason,
                    raw_vtk_cell_id=raw_cell_id,
                    candidate_count=len(candidates),
                    geometric_tolerance_m=tolerance,
                    source_sha256=hashes,
                )
            )
        return tuple(result)


def _assignment_dict(record: VelocityCellAssignmentEvidence) -> dict[str, object]:
    return {
        "case_id": record.case_id,
        "profile_id": record.profile_id,
        "sample_index": record.sample_index,
        "point_m": list(record.point_m),
        "distance_m": record.distance_m,
        "valid": record.valid,
        "reason": record.reason,
        "raw_vtk_cell_id": record.raw_vtk_cell_id,
        "candidate_count": record.candidate_count,
        "geometric_tolerance_m": record.geometric_tolerance_m,
        "source_sha256": list(record.source_sha256),
    }


def assignment_evidence_sha256(
    assignments: Sequence[VelocityCellAssignmentEvidence],
) -> str:
    """Hash assignment rows in their explicit evidence order."""

    records = tuple(assignments)
    if any(not isinstance(item, VelocityCellAssignmentEvidence) for item in records):
        raise VelocityAssignmentError("assignment evidence contains the wrong record type")
    return hashlib.sha256(
        _canonical_json([_assignment_dict(item) for item in records])
    ).hexdigest()


@dataclass(frozen=True)
class VelocityToleranceReplay:
    """Three deterministic assignment sets for tolerance-sensitivity review."""

    case_id: str
    source_sha256: tuple[str, ...]
    tolerances_m: tuple[float, ...]
    assignments_by_tolerance: tuple[
        tuple[VelocityCellAssignmentEvidence, ...], ...
    ]

    def as_dict(self, *, include_assignments: bool = True) -> dict[str, object]:
        receipt = candidate_kernel_receipt()
        rows: list[dict[str, object]] = []
        for tolerance, assignments in zip(
            self.tolerances_m, self.assignments_by_tolerance
        ):
            item: dict[str, object] = {
                "tolerance_m": tolerance,
                "assignment_count": len(assignments),
                "valid_count": sum(record.valid for record in assignments),
                "invalid_count": sum(not record.valid for record in assignments),
                "candidate_count_sum": sum(
                    record.candidate_count for record in assignments
                ),
                "multiple_candidate_count": sum(
                    record.candidate_count > 1 for record in assignments
                ),
                "assignment_sha256": assignment_evidence_sha256(assignments),
            }
            if include_assignments:
                item["assignments"] = [
                    _assignment_dict(record) for record in assignments
                ]
            rows.append(item)
        return {
            "schema": REPLAY_SCHEMA,
            "status": "candidate_not_frozen",
            "case_id": self.case_id,
            "source_sha256": list(self.source_sha256),
            "kernel": receipt,
            "tolerances": rows,
        }


def replay_assignment_tolerances(
    kernel: NativeContainingCellKernel,
    samples: Sequence[VelocitySampleDefinition],
    *,
    case_id: str,
    source_sha256: tuple[str, ...],
    invalid_reasons: Mapping[tuple[str, int], str] | None = None,
    tolerances_m: Sequence[float] = TOLERANCE_REPLAY_M,
) -> VelocityToleranceReplay:
    """Run deterministic assignment evidence at 0.5, 1, and 2 micrometres."""

    if not isinstance(kernel, NativeContainingCellKernel):
        raise VelocityAssignmentError("kernel must be a NativeContainingCellKernel")
    records = _validated_samples(samples)
    tolerances = tuple(
        _positive_finite(value, "tolerances_m") for value in tolerances_m
    )
    if not tolerances:
        raise VelocityAssignmentError("tolerances_m cannot be empty")
    if len(tolerances) != len(set(tolerances)):
        raise VelocityAssignmentError("tolerances_m must be unique")
    hashes = _source_hashes(source_sha256)
    assignments = tuple(
        kernel.assign(
            records,
            case_id=case_id,
            source_sha256=hashes,
            tolerance_m=tolerance,
            invalid_reasons=invalid_reasons,
        )
        for tolerance in tolerances
    )
    return VelocityToleranceReplay(
        case_id=case_id,
        source_sha256=hashes,
        tolerances_m=tolerances,
        assignments_by_tolerance=assignments,
    )


__all__ = [
    "DEFAULT_VALIDATION_CHUNK_SIZE",
    "EVALUATE_POSITION_FAILURE_REASON_PREFIX",
    "KERNEL_ID",
    "NO_CLOSURE_CELL_REASON",
    "NativeContainingCellKernel",
    "OWNER_INVALID_REASONS",
    "QUERY_CACHE_KEY_ID",
    "REPLAY_SCHEMA",
    "REQUIRED_VTK_VERSION",
    "SUPPORTED_CELL_TYPES",
    "TOLERANCE_REPLAY_M",
    "VelocityAssignmentError",
    "VelocityToleranceReplay",
    "assignment_evidence_sha256",
    "candidate_kernel_receipt",
    "candidate_kernel_settings",
    "generate_definition_velocity_samples",
    "generate_velocity_line_samples",
    "replay_assignment_tolerances",
    "vtk_available",
]
