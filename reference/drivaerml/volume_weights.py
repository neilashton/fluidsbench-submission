"""Deterministic candidate native-cell volume weights for DrivAerML.

This module is intentionally optional: importing it does not require VTK, but
executing its geometry path requires exactly VTK 9.5.2.  Strict pinned evidence
generation additionally requires Python 3.12.13 and NumPy 2.2.6 so its receipt
is aggregate-compatible.  The XML reader disables every advertised point- and
cell-data array before loading the unstructured-grid geometry.  A zero-based
int64 raw-cell ID is then attached before a
``vtkCellSizeFilter`` configured to calculate volume only.

The filter output is accepted only when cell count and raw order are unchanged
and it contains exactly one strictly positive finite volume per native cell.
Values are never absolutized, masked, or reordered.  The public NPY output is
little-endian float64 and is copied in bounded chunks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from .source import (
    NativeSourceError,
    PinnedVolumePart,
    SegmentVerification,
    load_native_source_pin,
    open_verified_monolithic,
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
RAW_CELL_ID_ARRAY_NAME = "__fluidsbench_raw_cell_id"
VOLUME_ARRAY_NAME = "__fluidsbench_cell_volume_m3"
DEFAULT_COPY_CHUNK_SIZE = 1_000_000
DEFAULT_SOURCE_VERIFICATION_CHUNK_BYTES = 64 * 1024 * 1024
RECEIPT_SCHEMA = "drivaerml-volume-cell-weights-candidate-v2"
RECEIPT_SCHEMA_VERSION = 2
UNBOUND_RECEIPT_SCHEMA = "drivaerml-volume-cell-weights-unbound-low-level-v1"


class DrivAerVolumeWeightError(ValueError):
    """Raised when geometry or generated cell volumes violate the contract."""


@dataclass(frozen=True)
class GeometryReadAudit:
    """Source arrays disabled by the geometry-only XML reader."""

    disabled_point_arrays: tuple[str, ...]
    disabled_cell_arrays: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "disabled_point_array_count": len(self.disabled_point_arrays),
            "disabled_point_arrays": list(self.disabled_point_arrays),
            "disabled_cell_array_count": len(self.disabled_cell_arrays),
            "disabled_cell_arrays": list(self.disabled_cell_arrays),
        }


@dataclass(frozen=True)
class VolumeWeightComputation:
    """Validated zero-copy views backed by the retained VTK output grid."""

    output_grid: Any
    raw_cell_ids: np.ndarray
    volumes_m3: np.ndarray
    statistics: dict[str, float | int]


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
        raise DrivAerVolumeWeightError(
            f"DrivAerML volume weights require optional VTK {REQUIRED_VTK_VERSION}{detail}"
        )
    actual = _vtk_version()
    if actual != REQUIRED_VTK_VERSION:
        raise DrivAerVolumeWeightError(
            f"DrivAerML volume weights require VTK {REQUIRED_VTK_VERSION}, got {actual}"
        )
    actual_source = str(vtk.vtkVersion.GetVTKSourceVersion())
    if actual_source != REQUIRED_VTK_SOURCE_VERSION:
        raise DrivAerVolumeWeightError(
            "DrivAerML volume weights require VTK source identity "
            f"{REQUIRED_VTK_SOURCE_VERSION!r}, got {actual_source!r}"
        )


def _require_frozen_runtime() -> None:
    """Reject production generation outside the receipt-accepted runtime.

    Keep this stricter gate on the pinned production entry point rather than
    low-level geometry helpers so synthetic algorithm tests can still run in a
    different interpreter.  The checks deliberately precede source hashing and
    any VTK geometry work, which avoids scanning a roughly 50 GB logical VTU
    only to produce a receipt that the strict aggregator must reject.
    """

    actual_python = platform.python_version()
    if actual_python != REQUIRED_PYTHON_VERSION:
        raise DrivAerVolumeWeightError(
            "DrivAerML pinned volume-weight generation requires Python "
            f"{REQUIRED_PYTHON_VERSION}, got {actual_python}"
        )
    actual_numpy = np.__version__
    if actual_numpy != REQUIRED_NUMPY_VERSION:
        raise DrivAerVolumeWeightError(
            "DrivAerML pinned volume-weight generation requires NumPy "
            f"{REQUIRED_NUMPY_VERSION}, got {actual_numpy}"
        )
    _require_vtk()


def _positive_chunk_size(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DrivAerVolumeWeightError("copy_chunk_size must be a positive integer")
    return value


def _positive_verification_chunk_bytes(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DrivAerVolumeWeightError(
            "source_verification_chunk_bytes must be a positive integer"
        )
    return value


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a local file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _algorithm_error(algorithm: Any, label: str) -> None:
    error_code = int(algorithm.GetErrorCode())
    if error_code == 0:
        return
    description = vtk.vtkErrorCode.GetStringFromErrorCode(error_code)
    raise DrivAerVolumeWeightError(f"{label} failed: {description} ({error_code})")


def read_geometry_only_vtu(path: Path | str) -> tuple[Any, GeometryReadAudit]:
    """Read VTU geometry after disabling every advertised data array."""

    _require_vtk()
    source = Path(path)
    if not source.is_file():
        raise DrivAerVolumeWeightError(f"VTU source does not exist: {source}")
    is_retained_descriptor = source.parent in {
        Path("/proc/self/fd"),
        Path("/dev/fd"),
    }
    if source.suffix.lower() != ".vtu" and not is_retained_descriptor:
        raise DrivAerVolumeWeightError("geometry source must use the .vtu suffix")

    reader = vtk.vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(source))
    reader.UpdateInformation()
    _algorithm_error(reader, "vtkXMLUnstructuredGridReader metadata pass")

    point_arrays = tuple(
        str(reader.GetPointArrayName(index))
        for index in range(reader.GetNumberOfPointArrays())
    )
    cell_arrays = tuple(
        str(reader.GetCellArrayName(index))
        for index in range(reader.GetNumberOfCellArrays())
    )
    for name in point_arrays:
        reader.SetPointArrayStatus(name, 0)
    for name in cell_arrays:
        reader.SetCellArrayStatus(name, 0)

    reader.Update()
    _algorithm_error(reader, "vtkXMLUnstructuredGridReader geometry pass")
    output = reader.GetOutput()
    if output is None or not output.IsA("vtkUnstructuredGrid"):
        raise DrivAerVolumeWeightError("VTU reader did not produce an unstructured grid")

    # Detach a lightweight grid shell from the reader while sharing geometry.
    grid = vtk.vtkUnstructuredGrid()
    grid.ShallowCopy(output)
    # Fail closed against arrays synthesized by a reader despite selection.
    grid.GetPointData().Initialize()
    grid.GetCellData().Initialize()
    if grid.GetNumberOfCells() < 1:
        raise DrivAerVolumeWeightError("VTU geometry contains no native volume cells")
    if grid.GetNumberOfPoints() < 1:
        raise DrivAerVolumeWeightError("VTU geometry contains no points")
    return grid, GeometryReadAudit(point_arrays, cell_arrays)


def algorithm_settings() -> dict[str, object]:
    """Return the exact frozen candidate algorithm settings."""

    return {
        "reader": {
            "class": "vtkXMLUnstructuredGridReader",
            "point_data_arrays": "all_disabled_after_update_information",
            "cell_data_arrays": "all_disabled_after_update_information",
            "geometry_only": True,
        },
        "raw_cell_ids": {
            "array_name": RAW_CELL_ID_ARRAY_NAME,
            "dtype": "int64",
            "definition": "zero_based_raw_vtk_cell_order",
        },
        "cell_size_filter": {
            "class": "vtkCellSizeFilter",
            "compute_vertex_count": False,
            "compute_length": False,
            "compute_area": False,
            "compute_volume": True,
            "compute_sum": False,
            "volume_array_name": VOLUME_ARRAY_NAME,
        },
        "acceptance": {
            "preserve_cell_count": True,
            "preserve_int64_raw_cell_ids": True,
            "one_strictly_positive_finite_volume_per_cell": True,
            "absolute_value": False,
            "masking": False,
            "reordering": False,
        },
        "npy": {
            "dtype": "<f8",
            "format_version": "1.0",
            "fortran_order": False,
            "bounded_chunk_copy": True,
        },
    }


def _attach_raw_cell_ids(grid: Any, *, chunk_size: int) -> None:
    count = int(grid.GetNumberOfCells())
    raw_ids = vtk.vtkTypeInt64Array()
    raw_ids.SetName(RAW_CELL_ID_ARRAY_NAME)
    raw_ids.SetNumberOfComponents(1)
    raw_ids.SetNumberOfTuples(count)
    view = np.asarray(vtk_to_numpy(raw_ids))
    if view.dtype != np.dtype(np.int64) or view.shape != (count,):
        raise DrivAerVolumeWeightError("VTK did not allocate an int64 raw-cell-ID array")
    for start in range(0, count, chunk_size):
        stop = min(start + chunk_size, count)
        view[start:stop] = np.arange(start, stop, dtype=np.int64)
    grid.GetCellData().AddArray(raw_ids)


def _volume_statistics(
    values: np.ndarray,
    *,
    chunk_size: int,
    cell_type_at: Callable[[int], tuple[int, str]] | None = None,
) -> dict[str, float | int]:
    if values.ndim != 1 or values.size < 1:
        raise DrivAerVolumeWeightError("cell volumes must be a non-empty one-dimensional array")
    if values.dtype.kind not in {"i", "u", "f"}:
        raise DrivAerVolumeWeightError("cell volumes must be numeric")
    partial_sums: list[float] = []
    minimum = math.inf
    maximum = -math.inf
    nonfinite_count = 0
    zero_count = 0
    negative_count = 0
    first_invalid: list[dict[str, object]] = []
    for start in range(0, values.size, chunk_size):
        stop = min(start + chunk_size, values.size)
        chunk = np.asarray(values[start:stop])
        finite = np.isfinite(chunk)
        zero = finite & (chunk == 0.0)
        negative = finite & (chunk < 0.0)
        invalid = ~finite | zero | negative
        nonfinite_count += int(np.count_nonzero(~finite))
        zero_count += int(np.count_nonzero(zero))
        negative_count += int(np.count_nonzero(negative))
        if len(first_invalid) < 16 and np.any(invalid):
            for local_index in np.flatnonzero(invalid)[: 16 - len(first_invalid)]:
                raw_cell_id = start + int(local_index)
                detail: dict[str, object] = {
                    "raw_cell_id": raw_cell_id,
                    "value_m3": float(chunk[int(local_index)]),
                }
                if cell_type_at is not None:
                    cell_type_id, cell_type_name = cell_type_at(raw_cell_id)
                    detail.update(
                        {
                            "vtk_cell_type_id": cell_type_id,
                            "vtk_cell_type_name": cell_type_name,
                        }
                    )
                first_invalid.append(detail)
        if np.any(invalid):
            continue
        partial = float(np.sum(chunk, dtype=np.float64))
        if not math.isfinite(partial):
            raise DrivAerVolumeWeightError("cell-volume sum overflowed")
        partial_sums.append(partial)
        minimum = min(minimum, float(np.min(chunk)))
        maximum = max(maximum, float(np.max(chunk)))
    if nonfinite_count or zero_count or negative_count:
        raise DrivAerVolumeWeightError(
            "every native cell must have one strictly positive finite volume; "
            f"nonfinite_count={nonfinite_count}, zero_count={zero_count}, "
            f"negative_count={negative_count}, first_invalid={first_invalid}"
        )
    try:
        total = math.fsum(partial_sums)
    except OverflowError as error:
        raise DrivAerVolumeWeightError("cell-volume sum overflowed") from error
    if not math.isfinite(total) or total <= 0.0:
        raise DrivAerVolumeWeightError("cell-volume sum must be finite and positive")
    return {
        "cell_count": int(values.size),
        "volume_sum_m3": total,
        "volume_min_m3": minimum,
        "volume_max_m3": maximum,
    }


def _validated_filter_output(
    output: Any,
    *,
    expected_cell_count: int,
    chunk_size: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, float | int]]:
    """Validate cell count/order and return zero-copy raw-ID/volume views."""

    if int(output.GetNumberOfCells()) != expected_cell_count:
        raise DrivAerVolumeWeightError("vtkCellSizeFilter changed native cell count")
    cell_data = output.GetCellData()
    raw_array = cell_data.GetArray(RAW_CELL_ID_ARRAY_NAME)
    if raw_array is None:
        raise DrivAerVolumeWeightError("vtkCellSizeFilter dropped raw cell IDs")
    if (
        raw_array.GetNumberOfComponents() != 1
        or raw_array.GetNumberOfTuples() != expected_cell_count
    ):
        raise DrivAerVolumeWeightError("filtered raw cell IDs have the wrong shape")
    raw_ids = np.asarray(vtk_to_numpy(raw_array))
    if raw_ids.dtype != np.dtype(np.int64) or raw_ids.shape != (expected_cell_count,):
        raise DrivAerVolumeWeightError("filtered raw cell IDs must remain int64")
    for start in range(0, expected_cell_count, chunk_size):
        stop = min(start + chunk_size, expected_cell_count)
        if not np.array_equal(
            raw_ids[start:stop], np.arange(start, stop, dtype=np.int64)
        ):
            raise DrivAerVolumeWeightError(
                "vtkCellSizeFilter changed or reordered raw cell IDs"
            )

    volume_array = cell_data.GetArray(VOLUME_ARRAY_NAME)
    if volume_array is None:
        raise DrivAerVolumeWeightError("vtkCellSizeFilter did not produce its volume array")
    if (
        volume_array.GetNumberOfComponents() != 1
        or volume_array.GetNumberOfTuples() != expected_cell_count
    ):
        raise DrivAerVolumeWeightError("filtered cell volumes have the wrong shape")
    volumes = np.asarray(vtk_to_numpy(volume_array))
    if volumes.dtype != np.dtype(np.float64) or volumes.shape != (expected_cell_count,):
        raise DrivAerVolumeWeightError("vtkCellSizeFilter volumes must be binary64 scalars")
    def cell_type_at(raw_cell_id: int) -> tuple[int, str]:
        type_id = int(output.GetCellType(raw_cell_id))
        type_name = vtk.vtkCellTypes.GetClassNameFromTypeId(type_id)
        return type_id, str(type_name) if type_name is not None else "unknown"

    statistics = _volume_statistics(
        volumes,
        chunk_size=chunk_size,
        cell_type_at=cell_type_at,
    )
    return raw_ids, volumes, statistics


def compute_volume_weights(
    grid: Any,
    *,
    copy_chunk_size: int = DEFAULT_COPY_CHUNK_SIZE,
) -> VolumeWeightComputation:
    """Run the frozen candidate filter on an in-memory unstructured grid."""

    _require_vtk()
    chunk_size = _positive_chunk_size(copy_chunk_size)
    if grid is None or not hasattr(grid, "IsA") or not grid.IsA("vtkUnstructuredGrid"):
        raise DrivAerVolumeWeightError("grid must be a vtkUnstructuredGrid")
    cell_count = int(grid.GetNumberOfCells())
    if cell_count < 1:
        raise DrivAerVolumeWeightError("grid contains no native volume cells")

    # Work on a geometry-only shell; the caller's arrays are neither loaded nor mutated.
    working = vtk.vtkUnstructuredGrid()
    working.ShallowCopy(grid)
    working.GetPointData().Initialize()
    working.GetCellData().Initialize()
    _attach_raw_cell_ids(working, chunk_size=chunk_size)

    size_filter = vtk.vtkCellSizeFilter()
    size_filter.SetInputData(working)
    size_filter.ComputeVertexCountOff()
    size_filter.ComputeLengthOff()
    size_filter.ComputeAreaOff()
    size_filter.ComputeVolumeOn()
    size_filter.ComputeSumOff()
    size_filter.SetVolumeArrayName(VOLUME_ARRAY_NAME)
    size_filter.Update()
    _algorithm_error(size_filter, "vtkCellSizeFilter")

    output = vtk.vtkUnstructuredGrid()
    output.ShallowCopy(size_filter.GetOutput())
    raw_ids, volumes, statistics = _validated_filter_output(
        output,
        expected_cell_count=cell_count,
        chunk_size=chunk_size,
    )
    return VolumeWeightComputation(
        output_grid=output,
        raw_cell_ids=raw_ids,
        volumes_m3=volumes,
        statistics=statistics,
    )


def write_volume_weights_npy(
    volumes_m3: Any,
    path: Path | str,
    *,
    copy_chunk_size: int = DEFAULT_COPY_CHUNK_SIZE,
) -> dict[str, object]:
    """Write validated volumes to an atomic little-endian float64 NPY file."""

    chunk_size = _positive_chunk_size(copy_chunk_size)
    values = np.asarray(volumes_m3)
    statistics = _volume_statistics(values, chunk_size=chunk_size)
    destination = Path(path)
    if destination.suffix.lower() != ".npy":
        raise DrivAerVolumeWeightError("volume-weight output must use the .npy suffix")
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    )
    temporary = Path(temporary_handle.name)
    temporary_handle.close()
    try:
        output = np.lib.format.open_memmap(
            temporary,
            mode="w+",
            dtype=np.dtype("<f8"),
            shape=(values.size,),
            fortran_order=False,
            version=(1, 0),
        )
        for start in range(0, values.size, chunk_size):
            stop = min(start + chunk_size, values.size)
            output[start:stop] = np.asarray(values[start:stop], dtype=np.dtype("<f8"))
        output.flush()
        del output
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return {
        "file": destination.name,
        "dtype": "<f8",
        "shape": [int(values.size)],
        "size_bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        **statistics,
    }


def _write_compact_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    temporary_handle = tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(temporary_handle.name)
    try:
        temporary_handle.write(encoded)
        temporary_handle.flush()
        os.fsync(temporary_handle.fileno())
        temporary_handle.close()
        os.replace(temporary, path)
    except Exception:
        temporary_handle.close()
        temporary.unlink(missing_ok=True)
        raise


def _compute_volume_weight_artifacts(
    source_vtu: Path,
    output_npy: Path | str,
    *,
    copy_chunk_size: int,
) -> dict[str, object]:
    """Run the geometry/filter/output path after any required source audit."""

    source = Path(source_vtu)
    grid, read_audit = read_geometry_only_vtu(source)
    computation = compute_volume_weights(grid, copy_chunk_size=copy_chunk_size)
    output = write_volume_weights_npy(
        computation.volumes_m3,
        output_npy,
        copy_chunk_size=copy_chunk_size,
    )
    if output["cell_count"] != computation.statistics["cell_count"]:
        raise DrivAerVolumeWeightError("written NPY cell count differs from VTK output")
    for name in ("volume_sum_m3", "volume_min_m3", "volume_max_m3"):
        if not math.isclose(
            float(output[name]),
            float(computation.statistics[name]),
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise DrivAerVolumeWeightError(
                f"written NPY {name} differs from validated VTK output"
            )
    return {
        "output": output,
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "vtk": _vtk_version(),
            "vtk_source": str(vtk.vtkVersion.GetVTKSourceVersion()),
        },
        "algorithm": algorithm_settings(),
        "execution": {"copy_chunk_size": _positive_chunk_size(copy_chunk_size)},
        "reader_audit": read_audit.as_dict(),
    }


def generate_volume_weights(
    source_vtu: Path | str,
    output_npy: Path | str,
    receipt_json: Path | str,
    *,
    case_id: str | None = None,
    copy_chunk_size: int = DEFAULT_COPY_CHUNK_SIZE,
) -> dict[str, object]:
    """Low-level geometry API for synthetic tests and algorithm development.

    This deliberately emits an unbound receipt that the strict candidate
    aggregator will reject.  Production candidate weights must use
    :func:`generate_pinned_volume_weights`, which proves the source bytes
    against ``native-source-pin.json`` before VTK reads the geometry.
    """

    source = Path(source_vtu)
    artifacts = _compute_volume_weight_artifacts(
        source,
        output_npy,
        copy_chunk_size=copy_chunk_size,
    )
    receipt: dict[str, object] = {
        "schema": UNBOUND_RECEIPT_SCHEMA,
        "schema_version": 1,
        "status": "unbound_low_level_geometry_fixture_not_aggregate_eligible",
        "source_vtu": {
            "file": source.name,
            "size_bytes": source.stat().st_size,
        },
        **artifacts,
    }
    if case_id is not None:
        if not isinstance(case_id, str) or not case_id:
            raise DrivAerVolumeWeightError("case_id must be a non-empty string")
        receipt["case_id"] = case_id
    _write_compact_json(Path(receipt_json), receipt)
    return receipt


def _verified_segment_binding(
    verifications: tuple[SegmentVerification, ...],
    *,
    expected_parts: Sequence[PinnedVolumePart],
) -> list[dict[str, int | str]]:
    parts = tuple(expected_parts)
    if len(verifications) != len(parts):
        raise DrivAerVolumeWeightError(
            "verified monolithic source does not cover every pinned segment"
        )
    result: list[dict[str, int | str]] = []
    expected_offset = 0
    for part_index, (verification, part) in enumerate(
        zip(verifications, parts, strict=True)
    ):
        if (
            part.part_index != part_index
            or verification.file_offset != expected_offset
            or verification.size_bytes != part.size_bytes
            or verification.sha256 != part.sha256
        ):
            raise DrivAerVolumeWeightError(
                "verified monolithic segment differs from the native-source pin"
            )
        result.append(
            {
                "part_index": part_index,
                "size_bytes": verification.size_bytes,
                "sha256": verification.sha256,
            }
        )
        expected_offset += part.size_bytes
    return result


def generate_pinned_volume_weights(
    native_source_pin_path: Path | str,
    dataset_root: Path | str,
    case_id: str,
    output_npy: Path | str,
    receipt_json: Path | str,
    *,
    monolithic_vtu: Path | str | None = None,
    copy_chunk_size: int = DEFAULT_COPY_CHUNK_SIZE,
    source_verification_chunk_bytes: int = (
        DEFAULT_SOURCE_VERIFICATION_CHUNK_BYTES
    ),
) -> dict[str, object]:
    """Verify one pinned monolithic VTU, then calculate native-cell volumes.

    Every byte range corresponding to an ordered release part is size- and
    SHA-256-verified before the VTK reader or ``vtkCellSizeFilter`` is invoked.
    The receipt records only immutable public identities, never local paths.
    """

    if not isinstance(case_id, str) or not case_id:
        raise DrivAerVolumeWeightError("case_id must be a non-empty string")
    copy_size = _positive_chunk_size(copy_chunk_size)
    verification_size = _positive_verification_chunk_bytes(
        source_verification_chunk_bytes
    )
    _require_frozen_runtime()
    pin_path = Path(native_source_pin_path).expanduser().resolve()
    try:
        pin_sha256 = sha256_file(pin_path)
        pin = load_native_source_pin(pin_path)
        if sha256_file(pin_path) != pin_sha256:
            raise DrivAerVolumeWeightError(
                "native-source pin changed while it was being loaded"
            )
        case = pin.case(case_id)
        resolved = pin.resolve(case_id, dataset_root)
        source_segments = resolved.monolithic_segments(monolithic_vtu)
        source = source_segments[0].path
        with open_verified_monolithic(
            resolved,
            source,
            verification_chunk_size=verification_size,
        ) as verified_stream:
            segment_binding = _verified_segment_binding(
                verified_stream.verification,
                expected_parts=case.volume_parts,
            )
            vtk_source = verified_stream.single_file_descriptor_path()
            try:
                artifacts = _compute_volume_weight_artifacts(
                    vtk_source,
                    output_npy,
                    copy_chunk_size=copy_size,
                )
                verified_stream.assert_unchanged(
                    context="while VTK read the verified monolithic source"
                )
            except Exception:
                # The destination is a newly generated derivative of a source
                # whose integrity could not be maintained through the VTK pass.
                Path(output_npy).unlink(missing_ok=True)
                raise
    except DrivAerVolumeWeightError:
        raise
    except (NativeSourceError, OSError) as error:
        raise DrivAerVolumeWeightError(
            f"pinned monolithic source verification failed: {error}"
        ) from error
    execution = dict(artifacts["execution"])
    execution["source_verification_chunk_bytes"] = verification_size
    artifacts["execution"] = execution
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "candidate_exact_native_source_verified_before_vtk",
        "case_id": case_id,
        "native_source_binding": {
            "pin": {
                "sha256": pin_sha256,
                "repository_id": pin.repository_id,
                "repository_revision": pin.repository_revision,
            },
            "case_id": case_id,
            "logical_volume": {
                "path": case.volume_logical_path.as_posix(),
                "size_bytes": case.volume_total_size_bytes,
                "ordered_verified_segments": segment_binding,
            },
            "verification": {
                "method": "exact_ordered_segment_size_and_sha256",
                "timing": "completed_before_vtk_geometry_reader",
                "vtk_input": "retained_verified_file_descriptor",
                "post_vtk_fstat": "unchanged",
            },
        },
        **artifacts,
    }
    _write_compact_json(Path(receipt_json), receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a reconstructed DrivAerML VTU against its immutable source "
            "pin, then generate deterministic native-cell volume weights."
        )
    )
    parser.add_argument("--native-source-pin", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--monolithic-vtu",
        type=Path,
        help="reconstructed VTU; defaults to the pinned logical dataset path",
    )
    parser.add_argument("--output-npy", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--copy-chunk-size", type=int, default=DEFAULT_COPY_CHUNK_SIZE)
    parser.add_argument(
        "--source-verification-chunk-bytes",
        type=int,
        default=DEFAULT_SOURCE_VERIFICATION_CHUNK_BYTES,
    )
    args = parser.parse_args()
    try:
        receipt = generate_pinned_volume_weights(
            args.native_source_pin,
            args.dataset_root,
            args.case_id,
            args.output_npy,
            args.receipt,
            monolithic_vtu=args.monolithic_vtu,
            copy_chunk_size=args.copy_chunk_size,
            source_verification_chunk_bytes=args.source_verification_chunk_bytes,
        )
    except DrivAerVolumeWeightError as error:
        parser.error(str(error))
    output = receipt["output"]
    print(
        f"PASS {args.case_id}: "
        f"{output['cell_count']} cells, sha256={output['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
