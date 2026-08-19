#!/usr/bin/env python3
"""Publish the DrivAerNet++ surface-pressure scoring support from the public VTK release.

Why a dataset-specific publisher: the DrivAerNet++ public release is remote
(Harvard Dataverse doi:10.7910/DVN/K7PWNJ version 1.0, Globus-backed) native
legacy-VTK PolyData, while the generic FluidsBench loader accepts local
materialized JSON/CSV/NPZ tables only.  This tool materializes the complete
native support -- every PointData pressure point of each selected
``SurfacePressureVTK/DrivAer_<ID>.vtk`` file, exactly once -- into
loader-compatible NPZ ground-truth tables plus the hashed
manifest -> case-index -> chunk chain, and then self-checks the output with
the generic loader and the reference metrics.

Materialization rules (versioned by this file's SHA-256 in the eventual
publication-validation record):

* stable support ID  = ``p%08d`` of the source point index, so lexicographic
  ``support_id_ascending`` ordering equals native point order;
* coordinates        = the source point coordinates, unchanged (metres);
* ground truth       = PointData array ``p`` (kinematic pressure, m^2/s^2);
* weights            = mass-lumped dual surface areas: every polygon's area
  (fan triangulation from its first vertex for non-triangles) is split
  equally among that polygon's vertices.

Usage:
  python benchmark-specs/drivaernetplusplus/tools/publish_scoring_support.py \
    --vtk-dir /data/DrivAerNetPlusPlus/SurfacePressureVTK \
    --out /tmp/dnpp-support --limit 3

The default split is the official 1,154-case evaluation split
(``splits/official_test.json``); use ``--limit``/``--case-ids`` for sample
runs on a handful of locally available cases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from reference import metrics
from reference.evaluate_predictions import (
    relative_l2_from_sufficient_statistics,
    relative_l2_sufficient_statistics,
)
from reference.scoring_support import (
    ScoredPredictions,
    align_predictions,
    load_scoring_support,
    load_support_release,
)

DATASET_ID = "drivaernetplusplus"
SUPPORT_ID = "surface-pressure-native"
QUANTITY_ID = "surface_pressure"
DEFAULT_RELEASE_ID = "drivaernetplusplus-surface-pressure-draft"
DEFAULT_SPLIT = Path(__file__).resolve().parents[1] / "splits" / "official_test.json"
PRESSURE_ARRAY = "p"
FILE_PREFIX = "DrivAer_"

METRIC_BINDINGS = [
    {
        "metric_id": "surface_pressure_rel_l2",
        "quantity_id": QUANTITY_ID,
        "reduction": "relative_l2_percent",
        "weighting": "support_weights",
        "dataset_weighting": "surface_point_dual_area",
        "aggregation": "per_geometry_then_macro_average",
        "case_evidence": "metric_value",
    },
    {
        "metric_id": "surface_pressure_equal_entity_rel_l2",
        "quantity_id": QUANTITY_ID,
        "reduction": "relative_l2_percent",
        "weighting": "uniform",
        "dataset_weighting": "surface_points_equal",
        "aggregation": "per_geometry_then_macro_average",
        "case_evidence": "metric_value",
    },
    {
        "metric_id": "surface_pressure_rel_l1",
        "quantity_id": QUANTITY_ID,
        "reduction": "relative_l1_percent",
        "weighting": "support_weights",
        "dataset_weighting": "surface_point_dual_area",
        "aggregation": "per_geometry_then_macro_average",
        "case_evidence": "metric_value",
    },
    {
        "metric_id": "surface_pressure_r2",
        "quantity_id": QUANTITY_ID,
        "reduction": "r2",
        "weighting": "uniform",
        "dataset_weighting": "surface_points_equal",
        "aggregation": "flatten_all_aligned_field_values",
        "case_evidence": "aggregate_only",
    },
]


class PublisherError(ValueError):
    """Raised when the pinned public data cannot produce the agreed support."""


# ---------------------------------------------------------------------------
# Legacy VTK PolyData parsing
# ---------------------------------------------------------------------------


def parse_legacy_vtk_polydata(path: Path) -> tuple[np.ndarray, list[list[int]], dict[str, np.ndarray]]:
    """Parse an ASCII legacy VTK PolyData file into points, polygons, point data.

    Handles the classic ``POLYGONS n size`` connectivity block and the newer
    ``OFFSETS``/``CONNECTIVITY`` layout, plus ``SCALARS`` and ``FIELD`` point
    data.  BINARY files fall back to pyvista/vtk when installed.
    """

    try:
        text = path.read_text(encoding="ascii", errors="strict")
    except UnicodeDecodeError:
        # Binary legacy VTK payloads are not ASCII-decodable.
        return _parse_with_pyvista(path)

    lines = text.splitlines()
    if len(lines) > 2 and lines[2].strip().upper() == "BINARY":
        return _parse_with_pyvista(path)

    tokens: list[str] = []
    for line in lines:
        tokens.extend(line.split())

    position = 0

    def peek() -> str:
        return tokens[position] if position < len(tokens) else ""

    def take(count: int) -> list[str]:
        nonlocal position
        if position + count > len(tokens):
            raise PublisherError(f"{path}: truncated VTK stream")
        chunk = tokens[position : position + count]
        position += count
        return chunk

    points: np.ndarray | None = None
    polygons: list[list[int]] = []
    point_data: dict[str, np.ndarray] = {}
    n_points = 0
    in_point_data = False

    while position < len(tokens):
        keyword = peek().upper()
        if keyword == "POINTS":
            take(1)
            n_points = int(take(1)[0])
            take(1)  # dtype
            values = np.asarray(take(3 * n_points), dtype=np.float64)
            points = values.reshape(n_points, 3)
        elif keyword == "POLYGONS":
            take(1)
            declared = int(take(1)[0])
            total = int(take(1)[0])
            if peek().upper() == "OFFSETS":
                take(1)
                take(1)  # dtype
                offsets = np.asarray(take(declared), dtype=np.int64)
                take(1)  # CONNECTIVITY
                take(1)  # dtype
                connectivity = np.asarray(take(total), dtype=np.int64)
                for start, stop in zip(offsets[:-1], offsets[1:]):
                    polygons.append([int(v) for v in connectivity[start:stop]])
            else:
                consumed = 0
                for _ in range(declared):
                    size = int(take(1)[0])
                    polygons.append([int(v) for v in take(size)])
                    consumed += 1 + size
                if consumed != total:
                    raise PublisherError(
                        f"{path}: POLYGONS block consumed {consumed} ints, declared {total}"
                    )
        elif keyword == "POINT_DATA":
            take(1)
            declared_points = int(take(1)[0])
            if declared_points != n_points:
                raise PublisherError(
                    f"{path}: POINT_DATA count {declared_points} != POINTS count {n_points}"
                )
            in_point_data = True
        elif keyword == "CELL_DATA":
            take(1)
            take(1)
            in_point_data = False
        elif keyword == "SCALARS" and in_point_data:
            take(1)
            name = take(1)[0]
            take(1)  # dtype
            components = 1
            if peek().isdigit():
                components = int(take(1)[0])
            if peek().upper() == "LOOKUP_TABLE":
                take(2)
            values = np.asarray(take(components * n_points), dtype=np.float64)
            point_data[name] = values.reshape(n_points, components).squeeze()
        elif keyword == "VECTORS" and in_point_data:
            take(1)
            name = take(1)[0]
            take(1)  # dtype
            values = np.asarray(take(3 * n_points), dtype=np.float64)
            point_data[name] = values.reshape(n_points, 3)
        elif keyword == "NORMALS" and in_point_data:
            take(1)
            take(1)
            take(1)
            take(3 * n_points)
        elif keyword == "FIELD" and in_point_data:
            take(1)
            take(1)  # field name
            array_count = int(take(1)[0])
            for _ in range(array_count):
                name = take(1)[0]
                components = int(take(1)[0])
                tuples = int(take(1)[0])
                take(1)  # dtype
                values = np.asarray(take(components * tuples), dtype=np.float64)
                if tuples == n_points:
                    point_data[name] = values.reshape(tuples, components).squeeze()
        else:
            take(1)

    if points is None:
        raise PublisherError(f"{path}: no POINTS block found")
    if not polygons:
        raise PublisherError(f"{path}: no POLYGONS connectivity found")
    return points, polygons, point_data


def _parse_with_pyvista(path: Path) -> tuple[np.ndarray, list[list[int]], dict[str, np.ndarray]]:
    try:
        import pyvista  # type: ignore
    except ImportError as error:  # pragma: no cover - environment dependent
        raise PublisherError(
            f"{path} is a binary legacy VTK file; install pyvista (pip install pyvista) "
            "so the publisher can read it, or convert the file to ASCII"
        ) from error
    mesh = pyvista.read(path)  # pragma: no cover - exercised only with real data
    faces = []
    raw = np.asarray(mesh.faces, dtype=np.int64)
    index = 0
    while index < len(raw):
        size = int(raw[index])
        faces.append([int(v) for v in raw[index + 1 : index + 1 + size]])
        index += 1 + size
    data = {name: np.asarray(mesh.point_data[name], dtype=np.float64) for name in mesh.point_data}
    return np.asarray(mesh.points, dtype=np.float64), faces, data


# ---------------------------------------------------------------------------
# Support construction
# ---------------------------------------------------------------------------


def mass_lumped_dual_areas(points: np.ndarray, polygons: list[list[int]]) -> np.ndarray:
    """Split every polygon's area equally among its vertices.

    Non-triangles are fan-triangulated from their first vertex; the polygon
    area is the sum of its fan-triangle areas.  This deterministic rule is the
    versioned nodal/dual construction for the dataset's point-associated
    pressure field.
    """

    weights = np.zeros(len(points), dtype=np.float64)
    for polygon in polygons:
        if len(polygon) < 3:
            raise PublisherError(f"polygon with fewer than 3 vertices: {polygon}")
        base = points[polygon[0]]
        area = 0.0
        for left, right in zip(polygon[1:-1], polygon[2:]):
            area += 0.5 * float(
                np.linalg.norm(np.cross(points[left] - base, points[right] - base))
            )
        share = area / len(polygon)
        for vertex in polygon:
            weights[vertex] += share
    return weights


def build_case_columns(vtk_path: Path) -> dict[str, np.ndarray]:
    """Materialize one case's complete native support into table columns."""

    points, polygons, point_data = parse_legacy_vtk_polydata(vtk_path)
    if PRESSURE_ARRAY not in point_data:
        raise PublisherError(
            f"{vtk_path}: PointData array {PRESSURE_ARRAY!r} not found; "
            f"available: {sorted(point_data)}"
        )
    pressure = np.asarray(point_data[PRESSURE_ARRAY], dtype=np.float64)
    if pressure.ndim != 1 or len(pressure) != len(points):
        raise PublisherError(f"{vtk_path}: pressure array shape {pressure.shape} is not per-point")
    weights = mass_lumped_dual_areas(points, polygons)
    if not float(np.sum(weights)) > 0:
        raise PublisherError(f"{vtk_path}: dual-area weights sum to zero")
    support_ids = np.asarray([f"p{index:08d}" for index in range(len(points))])
    return {
        "support_id": support_ids,
        "x": points[:, 0],
        "y": points[:, 1],
        "z": points[:, 2],
        "weight": weights,
        "p_true": pressure,
    }


def case_vtk_path(vtk_dir: Path, case_id: str) -> Path:
    return vtk_dir / f"{FILE_PREFIX}{case_id}.vtk"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def write_release(
    out_dir: Path,
    case_tables: dict[str, dict[str, np.ndarray]],
    *,
    release_id: str,
    case_set_id: str,
    chunk_size: int,
    published_at: str,
) -> Path:
    """Write ground-truth tables plus the hashed manifest/index/chunk chain."""

    case_set_dir = out_dir / "case-sets" / case_set_id
    data_dir = case_set_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    case_ids = list(case_tables)
    chunk_descriptors = []
    for chunk_index in range(0, len(case_ids), chunk_size):
        chunk_case_ids = case_ids[chunk_index : chunk_index + chunk_size]
        cases_payload = []
        for case_id in chunk_case_ids:
            columns = case_tables[case_id]
            table_path = data_dir / f"{case_id}.npz"
            np.savez_compressed(table_path, **columns)
            cases_payload.append(
                {
                    "case_id": case_id,
                    "support_instances": [
                        {
                            "support_id": SUPPORT_ID,
                            "entity_count": int(len(columns["support_id"])),
                            "artifacts": [
                                {
                                    "role": "ground_truth_table",
                                    "path": f"data/{case_id}.npz",
                                    "sha256": sha256_file(table_path),
                                    "format": "npz",
                                }
                            ],
                        }
                    ],
                }
            )
        chunk_name = f"chunk-{chunk_index // chunk_size:03d}.json"
        chunk_path = case_set_dir / chunk_name
        write_json(
            chunk_path,
            {
                "$schema": "https://fluidsbench.org/schemas/scoring-support/v1/case-chunk.schema.json",
                "schema_version": "1.0",
                "release_id": release_id,
                "dataset_id": DATASET_ID,
                "case_set_id": case_set_id,
                "cases": cases_payload,
            },
        )
        chunk_descriptors.append(
            {
                "file": chunk_name,
                "sha256": sha256_file(chunk_path),
                "case_count": len(chunk_case_ids),
                "case_ids": chunk_case_ids,
            }
        )

    index_path = case_set_dir / "index.json"
    write_json(
        index_path,
        {
            "$schema": "https://fluidsbench.org/schemas/scoring-support/v1/case-index.schema.json",
            "schema_version": "1.0",
            "release_id": release_id,
            "dataset_id": DATASET_ID,
            "case_set_id": case_set_id,
            "case_count": len(case_ids),
            "chunks": chunk_descriptors,
        },
    )

    manifest_path = out_dir / "manifest.json"
    write_json(
        manifest_path,
        {
            "$schema": "https://fluidsbench.org/schemas/scoring-support/v1/manifest.schema.json",
            "schema_version": "1.0",
            "release_id": release_id,
            "status": "owner_review_required",
            "published_at": published_at,
            "dataset_id": DATASET_ID,
            "dataset_version": "prototype-1",
            "evaluation_reference_version": "prototype-1",
            "coordinate_frame": {
                "id": "drivaernetplusplus-physical-v1",
                "axis_order": ["x", "y", "z"],
                "handedness": "right",
                "length_unit": "m",
                "normalization": "none",
            },
            "supports": [
                {
                    "id": SUPPORT_ID,
                    "domain": "surface",
                    "location_definition": {
                        "mode": "materialized_table",
                        "format": "npz",
                        "artifact_role": "ground_truth_table",
                        "support_id_rule": {"kind": "artifact_field", "field": "support_id"},
                        "coordinate_fields": ["x", "y", "z"],
                        "weight_rule": {
                            "kind": "artifact_field",
                            "artifact_role": "ground_truth_table",
                            "field": "weight",
                        },
                        "ordering": "support_id_ascending",
                    },
                    "quantities": [
                        {
                            "id": QUANTITY_ID,
                            "unit": "m2/s2",
                            "components": [
                                {
                                    "id": "p",
                                    "target_field": "p_true",
                                    "target_association": "table_field",
                                    "prediction_field": "p_pred",
                                }
                            ],
                        }
                    ],
                    "metric_bindings": METRIC_BINDINGS,
                    "required_coverage": {
                        "count_fraction": 1.0,
                        "weight_fraction": 1.0,
                        "unmapped_count": 0,
                    },
                    "extrapolation_policy": "forbidden",
                }
            ],
            "case_sets": [
                {
                    "id": case_set_id,
                    "case_count": len(case_ids),
                    "index_file": f"case-sets/{case_set_id}/index.json",
                    "index_sha256": sha256_file(index_path),
                }
            ],
            "notes": (
                "Draft materialization of the complete native DrivAerNet++ surface-pressure "
                "support (Dataverse doi:10.7910/DVN/K7PWNJ version 1.0). Not an official "
                "release: no publication-validation record has been recorded yet."
            ),
        },
    )
    return manifest_path


# ---------------------------------------------------------------------------
# Self-check: generic loader + reference metrics on the freshly written release
# ---------------------------------------------------------------------------


def self_check(manifest_path: Path, case_set_id: str) -> None:
    release = load_support_release(manifest_path, case_set_id)
    checked = 0
    for case_id in release.cases:
        support = load_scoring_support(release, case_id, SUPPORT_ID)
        truth = support.targets[QUANTITY_ID]

        identity = ScoredPredictions(
            case_id=case_id,
            support_name=SUPPORT_ID,
            support_ids=support.support_ids,
            values={QUANTITY_ID: truth.copy()},
        )
        aligned = align_predictions(support, identity)[QUANTITY_ID]
        flat_truth = truth[:, 0]
        flat_prediction = aligned[:, 0]
        if metrics.relative_l2(flat_truth, flat_prediction, support.weights) != 0.0:
            raise PublisherError(f"{case_id}: identity prediction did not score exactly zero")
        if metrics.r2_score(flat_truth, flat_prediction) != 1.0:
            raise PublisherError(f"{case_id}: identity prediction did not reach R2 = 1")

        perturbed = flat_truth.copy()
        perturbed[0] += 1.0
        expected = 100.0 * float(
            np.sqrt(
                support.weights[0]
                / np.sum(support.weights * np.square(flat_truth))
            )
        )
        observed = metrics.relative_l2(flat_truth, perturbed, support.weights)
        if abs(observed - expected) > 1e-9 * max(1.0, expected):
            raise PublisherError(
                f"{case_id}: perturbation check failed ({observed} vs {expected})"
            )

        thirds = np.array_split(np.arange(len(flat_truth)), 3)
        statistics = [
            relative_l2_sufficient_statistics(
                truth[piece],
                aligned[piece],
                support.weights[piece],
                weighting="support_weights",
            )
            for piece in thirds
            if len(piece)
        ]
        single = relative_l2_sufficient_statistics(
            truth, aligned, support.weights, weighting="support_weights"
        )
        if abs(
            sum(chunk["numerator"] for chunk in statistics) - single["numerator"]
        ) > 1e-12 or abs(
            sum(chunk["denominator"] for chunk in statistics) - single["denominator"]
        ) > 1e-9 * max(1.0, float(single["denominator"])):
            raise PublisherError(f"{case_id}: chunked sufficient statistics do not add up")
        relative_l2_from_sufficient_statistics(statistics)
        checked += 1
    print(f"SELF-CHECK PASS: {checked} case(s), identity/perturbation/chunk checks green")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_split(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vtk-dir", type=Path, required=True,
                        help="Local directory containing SurfacePressureVTK files")
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT,
                        help="FluidsBench split index JSON (default: official_test)")
    parser.add_argument("--out", type=Path, required=True, help="Output release directory")
    parser.add_argument("--release-id", default=DEFAULT_RELEASE_ID)
    parser.add_argument("--chunk-size", type=int, default=64, help="Cases per chunk file")
    parser.add_argument("--limit", type=int, default=None,
                        help="Materialize only the first N split cases (sample run)")
    parser.add_argument("--case-ids", nargs="*", default=None,
                        help="Materialize exactly these case IDs (must belong to the split)")
    parser.add_argument("--published-at", default="1970-01-01T00:00:00Z",
                        help="Timestamp recorded in the draft manifest")
    parser.add_argument("--no-self-check", action="store_true")
    args = parser.parse_args(argv)

    split = load_split(args.split)
    case_ids = list(split["case_ids"])
    if args.case_ids:
        unknown = sorted(set(args.case_ids) - set(case_ids))
        if unknown:
            parser.error(f"case IDs not in split {split.get('split_id')!r}: {unknown[:5]}")
        case_ids = list(args.case_ids)
    if args.limit is not None:
        case_ids = case_ids[: args.limit]
    if not case_ids:
        parser.error("no cases selected")

    case_tables: dict[str, dict[str, np.ndarray]] = {}
    for case_id in case_ids:
        vtk_path = case_vtk_path(args.vtk_dir, case_id)
        if not vtk_path.is_file():
            raise PublisherError(f"missing public surface-pressure file: {vtk_path}")
        case_tables[case_id] = build_case_columns(vtk_path)
        print(f"materialized {case_id}: {len(case_tables[case_id]['support_id'])} points")

    manifest_path = write_release(
        args.out,
        case_tables,
        release_id=args.release_id,
        case_set_id=str(split.get("case_set_id", "official_test")),
        chunk_size=args.chunk_size,
        published_at=args.published_at,
    )
    print(f"wrote draft release manifest: {manifest_path}")

    if not args.no_self_check:
        self_check(manifest_path, str(split.get("case_set_id", "official_test")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
