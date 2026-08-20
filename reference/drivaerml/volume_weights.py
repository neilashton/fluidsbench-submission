"""Deterministic candidate native-cell volume weights for DrivAerML.

This module is intentionally optional: importing it does not require VTK, but
executing its geometry path requires exactly VTK 9.6.0. Strict pinned evidence
generation additionally requires Python 3.12.13 and NumPy 2.2.6 so its receipt
is aggregate-compatible.  The XML reader disables every advertised point- and
cell-data array before loading the unstructured-grid geometry.  A zero-based
int64 raw-cell ID is then attached before a
``vtkCellSizeFilter`` configured to calculate volume only. VTK 9.6 uses
type-specific Verdict volume routines for tetrahedra, pyramids, wedges, and
hexahedra. Its polyhedron path calls ``TriangulateIds(1)`` and sums the signed
Verdict tetrahedron volumes. Production geometry is rejected unless every raw
cell type is one of the five types present in the immutable release.

The filter output is accepted only when cell count and raw order are unchanged
and it contains exactly one strictly positive finite volume per native cell.
Values are never absolutized, masked, or reordered.  The public NPY output is
little-endian float64 and is copied in bounded chunks.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import subprocess
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
REQUIRED_VTK_VERSION = "9.6.0"
REQUIRED_VTK_SOURCE_VERSION = "vtk version 9.6.0"
REQUIRED_PLATFORM_SYSTEM = "Linux"
REQUIRED_PLATFORM_MACHINE = "aarch64"
REQUIRED_PYTHON_IMPLEMENTATION = "CPython"
PINNED_ENVIRONMENT_BINDING = {
    "runtime_platform": {
        "python_implementation": REQUIRED_PYTHON_IMPLEMENTATION,
        "system": REQUIRED_PLATFORM_SYSTEM,
        "machine": REQUIRED_PLATFORM_MACHINE,
        "platform": "Linux-6.8.0-1028-nvidia-64k-aarch64-with-glibc2.39",
        "vtk_smp_backend": "Sequential",
    },
    "wheel_identity_semantics": (
        "declared_frozen_install_artifacts; wheel archives are not recoverable "
        "from an installed environment"
    ),
    "numpy_wheel": {
        "filename": (
            "numpy-2.2.6-cp312-cp312-manylinux_2_17_aarch64."
            "manylinux2014_aarch64.whl"
        ),
        "sha256": "f2618db89be1b4e05f7a1a847a9c1c0abd63e63a1607d892dd54668dd92faf87",
    },
    "vtk_wheel": {
        "filename": "vtk-9.6.0-cp312-cp312-manylinux_2_28_aarch64.whl",
        "sha256": "1b1f0537c7886d671bd3cb3c09409e2a6565444ccee96dc5a12d19252a1755bf",
        "source_commit": "edd2a192de28f042a548ef8f8663c255aadd6b08",
    },
    "installed_distribution_attestation": {
        "semantics": (
            "runtime SHA-256 of installed dist-info identity files and selected "
            "volume-algorithm-relevant VTK native libraries"
        ),
        "numpy": {
            "METADATA": "77c8e31c559eae4dfab00dee334c3a57ec23d0b7cf7249472bf35648eddca83b",
            "RECORD": "fe9d08da2ce70f2ba9a7944480668cd255f215e004c489b3cf8dbd440cca61c7",
            "WHEEL": "64f227aa6a15d0048f30e4346dbdbafd69917e5cd429229c06801bda20ea7b2a",
        },
        "vtk": {
            "METADATA": "6ac6453585bced1da6a7540376b966ddfc175d9771623ac401c8125814bf5f22",
            "RECORD": "134f60b2569c85a7a1403f37a775ac11ed0eec9f71c05601df2432da564a69e5",
            "WHEEL": "3712ebfda42f91cd1321f91f5b857f30f7a734b4541320aa6db63b6494609e18",
        },
        "vtk_native_libraries": {
            "vtkmodules/libvtkFiltersVerdict.so": "2889c578fa91acc69f93663bdf15e43ce1c371437f02949d67e14fabcdd7f587",
            "vtkmodules/libvtkverdict.so": "731b4704a805eb958e33eaa6009c35f6c2c37edbf399f28fe2a3f91b8be2df6b",
            "vtkmodules/libvtkCommonDataModel.so": "5b0427d52a8be8883734cd3b341f6b7d14f08db05dc1c3c8cfbc6500b09c8629",
            "vtkmodules/libvtkCommonCore.so": "269c198f88794288326a401ee21e4333f0376c1c3b7e10eddbc000faff1b46aa",
            "vtkmodules/libvtkIOXML.so": "443dc33cbd9a7fa01ef181107ab45fa63227a062c8e94e926db52a1411cf98ca",
            "vtkmodules/libvtkIOXMLParser.so": "d9ffd34ea0b3d61b7b9dcc2429b8d4b139e80215cb2fb267a8add3da34d7d602",
        },
    },
}
RAW_CELL_ID_ARRAY_NAME = "__fluidsbench_raw_cell_id"
VOLUME_ARRAY_NAME = "__fluidsbench_cell_volume_m3"
ALLOWED_NATIVE_CELL_TYPES = {
    10: "vtkTetra",
    12: "vtkHexahedron",
    13: "vtkWedge",
    14: "vtkPyramid",
    42: "vtkPolyhedron",
}
DEFAULT_COPY_CHUNK_SIZE = 1_000_000
DEFAULT_SOURCE_VERIFICATION_CHUNK_BYTES = 64 * 1024 * 1024
RECEIPT_SCHEMA = "drivaerml-volume-cell-weights-candidate-v3"
RECEIPT_SCHEMA_VERSION = 3
UNBOUND_RECEIPT_SCHEMA = "drivaerml-volume-cell-weights-unbound-low-level-v2"
IMPLEMENTATION_RELATIVE_PATHS = (
    "reference/__init__.py",
    "reference/metrics.py",
    "reference/scores.py",
    "reference/drivaerml/__init__.py",
    "reference/drivaerml/accumulators.py",
    "reference/drivaerml/source.py",
    "reference/drivaerml/volume_weights.py",
    "scripts/aggregate_drivaerml_volume_weights.py",
)
_GIT_REVISION_RE = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


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
    statistics: dict[str, object]
    native_cell_types: dict[str, object]


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
    actual_python_implementation = platform.python_implementation()
    if actual_python_implementation != REQUIRED_PYTHON_IMPLEMENTATION:
        raise DrivAerVolumeWeightError(
            "DrivAerML pinned volume-weight generation requires Python "
            f"implementation {REQUIRED_PYTHON_IMPLEMENTATION}, got "
            f"{actual_python_implementation}"
        )
    actual_system = platform.system()
    actual_machine = platform.machine()
    if (
        actual_system != REQUIRED_PLATFORM_SYSTEM
        or actual_machine != REQUIRED_PLATFORM_MACHINE
    ):
        raise DrivAerVolumeWeightError(
            "DrivAerML pinned volume-weight generation requires platform "
            f"{REQUIRED_PLATFORM_SYSTEM}/{REQUIRED_PLATFORM_MACHINE}, got "
            f"{actual_system}/{actual_machine}"
        )
    _require_vtk()
    _verify_installed_environment()


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


def _distribution_file_map(
    distribution_name: str,
    expected_relative_paths: Sequence[str],
) -> dict[str, Path]:
    try:
        distribution = importlib.metadata.distribution(distribution_name)
    except importlib.metadata.PackageNotFoundError as error:
        raise DrivAerVolumeWeightError(
            f"required installed distribution is missing: {distribution_name}"
        ) from error
    entries = distribution.files
    if entries is None:
        raise DrivAerVolumeWeightError(
            f"installed distribution has no file manifest: {distribution_name}"
        )
    by_relative = {entry.as_posix(): entry for entry in entries}
    result: dict[str, Path] = {}
    for relative in expected_relative_paths:
        matches = [
            entry
            for path, entry in by_relative.items()
            if path == relative
            or (
                "/" not in relative
                and path.endswith(f".dist-info/{relative}")
            )
        ]
        if len(matches) != 1:
            raise DrivAerVolumeWeightError(
                "installed distribution file coverage is not exact: "
                f"{distribution_name}/{relative}"
            )
        result[relative] = Path(distribution.locate_file(matches[0]))
    return result


def _verify_installed_environment() -> None:
    """Fail closed unless the measured pinned runtime is byte-identical."""

    expected_platform = PINNED_ENVIRONMENT_BINDING["runtime_platform"]
    actual_platform = platform.platform()
    if actual_platform != expected_platform["platform"]:
        raise DrivAerVolumeWeightError(
            "DrivAerML pinned volume-weight platform identity differs: "
            f"expected {expected_platform['platform']}, got {actual_platform}"
        )
    actual_backend = str(vtk.vtkSMPTools.GetBackend())
    if actual_backend != expected_platform["vtk_smp_backend"]:
        raise DrivAerVolumeWeightError(
            "DrivAerML pinned volume-weight VTK SMP backend differs: "
            f"expected {expected_platform['vtk_smp_backend']}, got {actual_backend}"
        )

    attestation = PINNED_ENVIRONMENT_BINDING["installed_distribution_attestation"]
    for distribution_name in ("numpy", "vtk"):
        expected = attestation[distribution_name]
        paths = _distribution_file_map(distribution_name, tuple(expected))
        for filename, expected_sha256 in expected.items():
            actual_sha256 = sha256_file(paths[filename])
            if actual_sha256 != expected_sha256:
                raise DrivAerVolumeWeightError(
                    "installed distribution identity differs: "
                    f"{distribution_name}/{filename}"
                )

    expected_libraries = attestation["vtk_native_libraries"]
    library_paths = _distribution_file_map("vtk", tuple(expected_libraries))
    for relative, expected_sha256 in expected_libraries.items():
        actual_sha256 = sha256_file(library_paths[relative])
        if actual_sha256 != expected_sha256:
            raise DrivAerVolumeWeightError(
                f"installed VTK native library differs: {relative}"
            )


def _file_identity(path: Path) -> tuple[int, int] | None:
    try:
        status = path.stat()
    except FileNotFoundError:
        return None
    return int(status.st_dev), int(status.st_ino)


def _unlink_if_same_file(path: Path, identity: tuple[int, int] | None) -> None:
    """Remove only the exact file inode created by the current invocation."""

    if identity is None or _file_identity(path) != identity:
        return
    path.unlink(missing_ok=True)


def implementation_file_records(
    repository_root: Path | str | None = None,
) -> list[dict[str, str]]:
    """Hash the complete directly executed implementation in stable order.

    Paths in the returned value are repository-relative public identities.  A
    caller can therefore serialize the value without leaking a local checkout
    location.  Git state is deliberately handled separately so the strict
    aggregator can compare receipt hashes with its current implementation
    without asserting that a documentation-only checkout is clean.
    """

    root = (
        _REPOSITORY_ROOT
        if repository_root is None
        else Path(repository_root).expanduser().resolve()
    )
    records: list[dict[str, str]] = []
    for relative in IMPLEMENTATION_RELATIVE_PATHS:
        path = root / relative
        if not path.is_file():
            raise DrivAerVolumeWeightError(
                f"volume-weight implementation file is missing: {relative}"
            )
        records.append({"path": relative, "sha256": sha256_file(path)})
    return records


def _git_text(repository_root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=repository_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DrivAerVolumeWeightError(
            "cannot resolve clean Git provenance for pinned volume-weight generation"
        ) from error
    return completed.stdout.strip()


def _git_bytes(repository_root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=repository_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DrivAerVolumeWeightError(
            "cannot read committed implementation bytes for pinned "
            "volume-weight generation"
        ) from error
    return completed.stdout


def _capture_implementation_binding(
    repository_root: Path | str | None = None,
) -> dict[str, object]:
    """Capture a clean, resolved Git revision and exact implementation hashes."""

    root = (
        _REPOSITORY_ROOT
        if repository_root is None
        else Path(repository_root).expanduser().resolve()
    )
    top_level = _git_text(root, "rev-parse", "--show-toplevel")
    try:
        git_root = Path(top_level).resolve()
    except (OSError, RuntimeError) as error:
        raise DrivAerVolumeWeightError(
            "pinned volume-weight generation requires a resolved Git worktree"
        ) from error
    if git_root != root:
        raise DrivAerVolumeWeightError(
            "pinned volume-weight implementation is not at its expected Git root"
        )
    revision = _git_text(root, "rev-parse", "--verify", "HEAD^{commit}")
    if _GIT_REVISION_RE.fullmatch(revision) is None:
        raise DrivAerVolumeWeightError(
            "pinned volume-weight generation requires a resolved 40-hex Git revision"
        )
    status = _git_text(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise DrivAerVolumeWeightError(
            "pinned volume-weight generation requires a clean Git worktree"
        )
    files = implementation_file_records(root)
    for record in files:
        committed = _git_bytes(root, "show", f"{revision}:{record['path']}")
        committed_sha256 = hashlib.sha256(committed).hexdigest()
        if committed_sha256 != record["sha256"]:
            raise DrivAerVolumeWeightError(
                "pinned volume-weight implementation differs from its committed "
                f"Git revision: {record['path']}"
            )
    return {
        "git_revision": revision,
        "worktree_clean": True,
        "files": files,
    }


def _algorithm_error(algorithm: Any, label: str) -> None:
    error_code = int(algorithm.GetErrorCode())
    if error_code == 0:
        return
    description = vtk.vtkErrorCode.GetStringFromErrorCode(error_code)
    raise DrivAerVolumeWeightError(f"{label} failed: {description} ({error_code})")


def _vtk_event_message(arguments: tuple[object, ...]) -> str:
    """Return a bounded single-line diagnostic from VTK observer arguments."""

    if not arguments:
        return "no message supplied"
    value = arguments[-1]
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    message = " ".join(str(value).split())
    return (message or "no message supplied")[:1000]


def _run_vtk_algorithm_stage(
    algorithm: Any,
    label: str,
    operation: Callable[[], object],
) -> None:
    """Fail on local events, global VTK diagnostics, exceptions, or error code.

    ``GetErrorCode`` alone is insufficient: several VTK algorithms report a
    recoverable-looking warning or error event while leaving the code at zero.
    Candidate evidence is therefore invalidated by either event class. A
    scoped global string output window also captures diagnostics emitted by
    child cells (not merely by the observed top-level algorithm).
    """

    if vtk is None:
        raise DrivAerVolumeWeightError(f"{label} cannot run without VTK")
    events: list[tuple[str, str]] = []

    def capture(_caller: object, event: str, *arguments: object) -> None:
        events.append((str(event), _vtk_event_message(arguments)))

    observer_ids: list[int] = []
    previous_output_window = vtk.vtkOutputWindow.GetInstance()
    diagnostic_window = vtk.vtkStringOutputWindow()
    operation_error: Exception | None = None
    diagnostics = ""
    try:
        vtk.vtkOutputWindow.SetInstance(diagnostic_window)
        for event in ("WarningEvent", "ErrorEvent"):
            observer_ids.append(int(algorithm.AddObserver(event, capture)))
        try:
            operation()
        except Exception as error:  # defer until global diagnostics are inspected.
            operation_error = error
    except Exception as error:
        operation_error = error
    finally:
        try:
            for observer_id in observer_ids:
                algorithm.RemoveObserver(observer_id)
        finally:
            try:
                diagnostics = " ".join(str(diagnostic_window.GetOutput()).split())
            finally:
                vtk.vtkOutputWindow.SetInstance(previous_output_window)
    if diagnostics:
        error = DrivAerVolumeWeightError(
            f"{label} emitted VTK global diagnostic: {diagnostics[:1000]}"
        )
        if operation_error is not None:
            raise error from operation_error
        raise error
    if events:
        event, message = events[0]
        error = DrivAerVolumeWeightError(
            f"{label} emitted VTK {event}: {message}; "
            f"event_count={len(events)}"
        )
        if operation_error is not None:
            raise error from operation_error
        raise error
    if operation_error is not None:
        if isinstance(operation_error, DrivAerVolumeWeightError):
            raise operation_error
        raise DrivAerVolumeWeightError(
            f"{label} raised an exception: {operation_error}"
        ) from operation_error
    _algorithm_error(algorithm, label)


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
    _run_vtk_algorithm_stage(
        reader,
        "vtkXMLUnstructuredGridReader metadata pass",
        reader.UpdateInformation,
    )

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

    _run_vtk_algorithm_stage(
        reader,
        "vtkXMLUnstructuredGridReader geometry pass",
        reader.Update,
    )
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
            "event_policy": (
                "fail_on_any_algorithm_WarningEvent_or_ErrorEvent_or_"
                "scoped_vtkStringOutputWindow_diagnostic"
            ),
        },
        "native_cell_types": {
            "array_source": "vtkUnstructuredGrid.GetCellTypes",
            "dtype": "uint8",
            "order": "zero_based_raw_vtk_cell_order",
            "payload_sha256": "SHA256_of_raw_order_uint8_type_id_bytes",
            "allowed_vtk_cell_types": [
                {"vtk_cell_type_id": type_id, "vtk_cell_type_name": name}
                for type_id, name in ALLOWED_NATIVE_CELL_TYPES.items()
            ],
        },
        "raw_cell_ids": {
            "array_name": RAW_CELL_ID_ARRAY_NAME,
            "dtype": "int64",
            "definition": "zero_based_raw_vtk_cell_order",
        },
        "cell_size_filter": {
            "class": "vtkCellSizeFilter",
            "vtk_version": REQUIRED_VTK_VERSION,
            "compute_vertex_count": False,
            "compute_length": False,
            "compute_area": False,
            "compute_volume": True,
            "compute_sum": False,
            "volume_array_name": VOLUME_ARRAY_NAME,
            "event_policy": (
                "fail_on_any_algorithm_WarningEvent_or_ErrorEvent_or_"
                "scoped_vtkStringOutputWindow_diagnostic"
            ),
            "cell_type_dispatch": {
                "10_vtkTetra": "vtkMeshQuality::TetVolume",
                "12_vtkHexahedron": "vtkMeshQuality::HexVolume",
                "13_vtkWedge": (
                    "vtkMeshQuality::WedgeVolume_with_VTK_to_Verdict_reorder"
                ),
                "14_vtkPyramid": "vtkMeshQuality::PyramidVolume",
                "42_vtkPolyhedron": (
                    "vtkCell::TriangulateIds(1)_then_signed_"
                    "vtkMeshQuality::TetVolume_sum"
                ),
            },
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


def _vtk_cell_type_name(type_id: int) -> str:
    """Resolve a diagnostic name with the non-deprecated VTK 9.6 utility."""

    frozen = ALLOWED_NATIVE_CELL_TYPES.get(type_id)
    if frozen is not None:
        return frozen
    name = vtk.vtkCellTypeUtilities.GetClassNameFromTypeId(type_id)
    return str(name) if name else "unknown"


def _raw_cell_type_array(grid: Any, *, expected_cell_count: int) -> np.ndarray:
    vtk_types = grid.GetCellTypes()
    if vtk_types is None:
        raise DrivAerVolumeWeightError("native grid has no raw cell-type array")
    if (
        int(vtk_types.GetNumberOfComponents()) != 1
        or int(vtk_types.GetNumberOfTuples()) != expected_cell_count
    ):
        raise DrivAerVolumeWeightError("native raw cell-type array has the wrong shape")
    types = np.asarray(vtk_to_numpy(vtk_types))
    if types.dtype != np.dtype(np.uint8) or types.shape != (expected_cell_count,):
        raise DrivAerVolumeWeightError(
            "native raw cell-type array must be one uint8 ID per native cell"
        )
    return types


def _audit_native_cell_types(
    grid: Any,
    *,
    expected_cell_count: int,
    chunk_size: int,
) -> tuple[np.ndarray, dict[str, object]]:
    """Hash and histogram the raw-order uint8 VTK cell-type payload."""

    types = _raw_cell_type_array(grid, expected_cell_count=expected_cell_count)
    digest = hashlib.sha256()
    histogram: dict[int, int] = {}
    first_unsupported: list[dict[str, object]] = []
    allowed = frozenset(ALLOWED_NATIVE_CELL_TYPES)
    for start in range(0, expected_cell_count, chunk_size):
        stop = min(start + chunk_size, expected_cell_count)
        chunk = np.asarray(types[start:stop])
        digest.update(memoryview(np.ascontiguousarray(chunk)).cast("B"))
        unique, counts = np.unique(chunk, return_counts=True)
        for raw_type_id, raw_count in zip(unique, counts, strict=True):
            type_id = int(raw_type_id)
            histogram[type_id] = histogram.get(type_id, 0) + int(raw_count)
            if type_id not in allowed and len(first_unsupported) < 16:
                for local_index in np.flatnonzero(chunk == raw_type_id)[
                    : 16 - len(first_unsupported)
                ]:
                    first_unsupported.append(
                        {
                            "raw_cell_id": start + int(local_index),
                            "vtk_cell_type_id": type_id,
                            "vtk_cell_type_name": _vtk_cell_type_name(type_id),
                        }
                    )
    unsupported = sorted(set(histogram) - allowed)
    if unsupported:
        raise DrivAerVolumeWeightError(
            "native production geometry contains unsupported VTK cell types; "
            f"allowed={sorted(allowed)}, unsupported={unsupported}, "
            f"first_unsupported={first_unsupported}"
        )
    rows = [
        {
            "vtk_cell_type_id": type_id,
            "vtk_cell_type_name": ALLOWED_NATIVE_CELL_TYPES[type_id],
            "cell_count": histogram[type_id],
        }
        for type_id in sorted(histogram)
    ]
    if sum(int(row["cell_count"]) for row in rows) != expected_cell_count:
        raise DrivAerVolumeWeightError("native cell-type histogram count is inconsistent")
    return types, {
        "dtype": "uint8",
        "shape": [expected_cell_count],
        "order": "zero_based_raw_vtk_cell_order",
        "payload_sha256": digest.hexdigest(),
        "histogram": rows,
    }


def _volume_statistics(
    values: np.ndarray,
    *,
    chunk_size: int,
    cell_types: np.ndarray | None = None,
) -> dict[str, object]:
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
    per_type_partial_sums: dict[int, list[float]] = {}
    per_type_counts: dict[int, int] = {}
    per_type_minima: dict[int, float] = {}
    per_type_maxima: dict[int, float] = {}
    if cell_types is not None and (
        cell_types.dtype != np.dtype(np.uint8) or cell_types.shape != values.shape
    ):
        raise DrivAerVolumeWeightError("cell-type and volume arrays must align exactly")
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
                if cell_types is not None:
                    cell_type_id = int(cell_types[raw_cell_id])
                    detail.update(
                        {
                            "vtk_cell_type_id": cell_type_id,
                            "vtk_cell_type_name": _vtk_cell_type_name(cell_type_id),
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
        if cell_types is not None:
            type_chunk = np.asarray(cell_types[start:stop])
            for raw_type_id in np.unique(type_chunk):
                type_id = int(raw_type_id)
                selected = chunk[type_chunk == raw_type_id]
                type_partial = float(np.sum(selected, dtype=np.float64))
                if not math.isfinite(type_partial):
                    raise DrivAerVolumeWeightError("per-type cell-volume sum overflowed")
                per_type_partial_sums.setdefault(type_id, []).append(type_partial)
                per_type_counts[type_id] = per_type_counts.get(type_id, 0) + int(
                    selected.size
                )
                selected_min = float(np.min(selected))
                selected_max = float(np.max(selected))
                per_type_minima[type_id] = min(
                    per_type_minima.get(type_id, math.inf), selected_min
                )
                per_type_maxima[type_id] = max(
                    per_type_maxima.get(type_id, -math.inf), selected_max
                )
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
    result: dict[str, object] = {
        "cell_count": int(values.size),
        "volume_sum_m3": total,
        "volume_min_m3": minimum,
        "volume_max_m3": maximum,
    }
    if cell_types is not None:
        per_type: list[dict[str, object]] = []
        for type_id in sorted(per_type_counts):
            type_sum = math.fsum(per_type_partial_sums[type_id])
            if not math.isfinite(type_sum) or type_sum <= 0.0:
                raise DrivAerVolumeWeightError(
                    "per-type cell-volume sum must be finite and positive"
                )
            per_type.append(
                {
                    "vtk_cell_type_id": type_id,
                    "vtk_cell_type_name": ALLOWED_NATIVE_CELL_TYPES[type_id],
                    "cell_count": per_type_counts[type_id],
                    "volume_sum_m3": type_sum,
                    "volume_min_m3": per_type_minima[type_id],
                    "volume_max_m3": per_type_maxima[type_id],
                }
            )
        result["per_vtk_cell_type"] = per_type
    return result


def _validated_filter_output(
    output: Any,
    *,
    expected_cell_count: int,
    chunk_size: int,
    expected_native_cell_types: dict[str, object] | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
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
    output_cell_types, output_cell_type_audit = _audit_native_cell_types(
        output,
        expected_cell_count=expected_cell_count,
        chunk_size=chunk_size,
    )
    if (
        expected_native_cell_types is not None
        and output_cell_type_audit != expected_native_cell_types
    ):
        raise DrivAerVolumeWeightError(
            "vtkCellSizeFilter changed raw cell types or their order"
        )

    statistics = _volume_statistics(
        volumes,
        chunk_size=chunk_size,
        cell_types=output_cell_types,
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
    _input_cell_types, native_cell_type_audit = _audit_native_cell_types(
        grid,
        expected_cell_count=cell_count,
        chunk_size=chunk_size,
    )

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
    _run_vtk_algorithm_stage(size_filter, "vtkCellSizeFilter", size_filter.Update)

    output = vtk.vtkUnstructuredGrid()
    output.ShallowCopy(size_filter.GetOutput())
    raw_ids, volumes, statistics = _validated_filter_output(
        output,
        expected_cell_count=cell_count,
        chunk_size=chunk_size,
        expected_native_cell_types=native_cell_type_audit,
    )
    return VolumeWeightComputation(
        output_grid=output,
        raw_cell_ids=raw_ids,
        volumes_m3=volumes,
        statistics=statistics,
        native_cell_types=native_cell_type_audit,
    )


def write_volume_weights_npy(
    volumes_m3: Any,
    path: Path | str,
    *,
    copy_chunk_size: int = DEFAULT_COPY_CHUNK_SIZE,
    replace_existing: bool = True,
) -> dict[str, object]:
    """Write validated volumes to an atomic little-endian float64 NPY file."""

    chunk_size = _positive_chunk_size(copy_chunk_size)
    if not isinstance(replace_existing, bool):
        raise DrivAerVolumeWeightError("replace_existing must be Boolean")
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
    published_identity: tuple[int, int] | None = None
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
        if replace_existing:
            os.replace(temporary, destination)
        else:
            try:
                os.link(temporary, destination)
            except FileExistsError as error:
                raise DrivAerVolumeWeightError(
                    f"volume-weight output already exists: {destination}"
                ) from error
            published_identity = _file_identity(destination)
            temporary.unlink()

        result = {
            "file": destination.name,
            "dtype": "<f8",
            "shape": [int(values.size)],
            "size_bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
            **statistics,
        }
    except Exception:
        temporary.unlink(missing_ok=True)
        if not replace_existing:
            _unlink_if_same_file(destination, published_identity)
        raise

    return result


def _write_compact_json(
    path: Path,
    value: dict[str, object],
    *,
    replace_existing: bool = True,
) -> None:
    if not isinstance(replace_existing, bool):
        raise DrivAerVolumeWeightError("replace_existing must be Boolean")
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
    published_identity: tuple[int, int] | None = None
    try:
        temporary_handle.write(encoded)
        temporary_handle.flush()
        os.fsync(temporary_handle.fileno())
        temporary_handle.close()
        if replace_existing:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                raise DrivAerVolumeWeightError(
                    f"volume-weight receipt already exists: {path}"
                ) from error
            published_identity = _file_identity(path)
            temporary.unlink()
    except Exception:
        temporary_handle.close()
        temporary.unlink(missing_ok=True)
        if not replace_existing:
            _unlink_if_same_file(path, published_identity)
        raise


def _compute_volume_weight_artifacts(
    source_vtu: Path,
    output_npy: Path | str,
    *,
    copy_chunk_size: int,
    replace_existing_output: bool = True,
) -> dict[str, object]:
    """Run the geometry/filter/output path after any required source audit."""

    source = Path(source_vtu)
    grid, read_audit = read_geometry_only_vtu(source)
    computation = compute_volume_weights(grid, copy_chunk_size=copy_chunk_size)
    output = write_volume_weights_npy(
        computation.volumes_m3,
        output_npy,
        copy_chunk_size=copy_chunk_size,
        replace_existing=replace_existing_output,
    )
    output["per_vtk_cell_type"] = computation.statistics["per_vtk_cell_type"]
    published_identity = _file_identity(Path(output_npy))
    try:
        if output["cell_count"] != computation.statistics["cell_count"]:
            raise DrivAerVolumeWeightError(
                "written NPY cell count differs from VTK output"
            )
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
            "native_cell_types": computation.native_cell_types,
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
    except Exception:
        if not replace_existing_output:
            _unlink_if_same_file(Path(output_npy), published_identity)
        raise


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
    output_path = Path(output_npy).expanduser()
    receipt_path = Path(receipt_json).expanduser()
    if output_path.resolve(strict=False) == receipt_path.resolve(strict=False):
        raise DrivAerVolumeWeightError(
            "volume-weight output and receipt must use different paths"
        )
    if output_path.exists():
        raise DrivAerVolumeWeightError(
            f"volume-weight output already exists: {output_path}"
        )
    if receipt_path.exists():
        raise DrivAerVolumeWeightError(
            f"volume-weight receipt already exists: {receipt_path}"
        )
    copy_size = _positive_chunk_size(copy_chunk_size)
    verification_size = _positive_verification_chunk_bytes(
        source_verification_chunk_bytes
    )
    _require_frozen_runtime()
    # This gate must precede native-source pin loading and all dataset I/O.
    implementation_binding = _capture_implementation_binding()
    pin_path = Path(native_source_pin_path).expanduser().resolve()
    generated_output_identity: tuple[int, int] | None = None
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
                    output_path,
                    copy_chunk_size=copy_size,
                    replace_existing_output=False,
                )
                generated_output_identity = _file_identity(output_path)
                if generated_output_identity is None:
                    raise DrivAerVolumeWeightError(
                        "volume-weight generator did not publish its output"
                    )
                verified_stream.assert_unchanged(
                    context="while VTK read the verified monolithic source"
                )
            except Exception:
                # The destination is a newly generated derivative of a source
                # whose integrity could not be maintained through the VTK pass.
                _unlink_if_same_file(output_path, generated_output_identity)
                raise
    except DrivAerVolumeWeightError:
        raise
    except (NativeSourceError, OSError) as error:
        raise DrivAerVolumeWeightError(
            f"pinned monolithic source verification failed: {error}"
        ) from error
    try:
        ending_implementation_binding = _capture_implementation_binding()
        if ending_implementation_binding != implementation_binding:
            raise DrivAerVolumeWeightError(
                "volume-weight implementation binding changed during generation"
            )
    except Exception:
        # Never retain an array generated while its executable identity was
        # dirty, unresolved, or different at the end of the run.
        _unlink_if_same_file(output_path, generated_output_identity)
        raise

    execution = dict(artifacts["execution"])
    execution["source_verification_chunk_bytes"] = verification_size
    artifacts["execution"] = execution
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "candidate_exact_native_source_verified_before_vtk",
        "case_id": case_id,
        "implementation_binding": implementation_binding,
        "environment_binding": PINNED_ENVIRONMENT_BINDING,
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
    try:
        _write_compact_json(receipt_path, receipt, replace_existing=False)
    except Exception:
        _unlink_if_same_file(output_path, generated_output_identity)
        raise
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
