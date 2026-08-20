#!/usr/bin/env python3
"""Build a complete, synthetic DrivAerML-shaped schema-v3 package.

This deliberately does not read or emulate the numerical contents of a VTP or
VTU file.  It exercises the boundaries between ordered multipart transport,
raw-cell chunk accounting, additive field statistics, keyed prediction
packaging, the generic FluidsBench evaluator, and the public JSON schemas.

The real DrivAerML scoring support is still a closed candidate.  This driver
therefore uses a separate synthetic dataset/support namespace, writes an
explicitly ineligible dummy ``submission.json``, and makes no DrivAerML
activation, participant, approval, or model-quality claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from reference.drivaerml.accumulators import (  # noqa: E402
    FinalizedFieldStatistics,
    StreamingFieldAccumulator,
    field_chunk_statistics,
)
from reference.evaluate_predictions import evaluate_prediction_artifact  # noqa: E402
from reference.scoring_support import sha256_file  # noqa: E402

try:  # noqa: E402
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as error:  # pragma: no cover - requirements.txt supplies it
    raise SystemExit(
        "jsonschema is required; install the repository requirements first"
    ) from error


SUBMISSION_ID = "synthetic-drivaerml-native-chunk-demo"
DATASET_ID = "synthetic-drivaerml-shaped"
DATASET_VERSION = "synthetic-native-chunk-demo-v1"
RELEASE_ID = "synthetic-drivaerml-shaped-support-v1"
CASE_SET_ID = "two-and-three-part-pilots"
SPLIT_ID = "synthetic-demo"
SUPPORT_ID = "volume-native-cells"
PROFILE_RELEASE_ID = "synthetic-drivaerml-shaped-profiles-v1"
REAL_DRIVAERML_DATASET_ID = "drivaerml"
REAL_DRIVAERML_CANDIDATE_STATUS = "candidate_scoring_contract"
REAL_DRIVAERML_SCORING_STATUS = "owner_review_required"
GENERATED_AT = "2026-08-20T00:00:00Z"
SUBMITTED_AT = "2026-08-20"


@dataclass(frozen=True)
class DemoCase:
    """One small synthetic case with independent byte-part and cell chunks."""

    case_id: str
    part_count: int
    entity_count: int
    chunk_ranges: tuple[tuple[int, int], ...]
    processing_order: tuple[int, ...]
    case_offset: float


CASES = (
    DemoCase(
        case_id="run_1",
        part_count=2,
        entity_count=7,
        chunk_ranges=((0, 2), (2, 6), (6, 7)),
        processing_order=(2, 0, 1),
        case_offset=0.0,
    ),
    DemoCase(
        case_id="run_44",
        part_count=3,
        entity_count=8,
        chunk_ranges=((0, 1), (1, 4), (4, 6), (6, 8)),
        processing_order=(3, 1, 0, 2),
        case_offset=4.4,
    ),
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{json.dumps(value, indent=2, ensure_ascii=True)}\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: Iterable[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _schema_errors(schema_path: Path, value: object) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(value),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
        for error in errors
    ]


def _validate_schema(schema_relative_path: str, value_path: Path) -> None:
    errors = _schema_errors(
        REPOSITORY_ROOT / "schemas" / schema_relative_path,
        json.loads(value_path.read_text(encoding="utf-8")),
    )
    if errors:
        raise ValueError(
            f"{value_path} does not match {schema_relative_path}:\n"
            + "\n".join(errors)
        )


def _assert_closed_real_drivaerml_candidate(candidate_spec: object) -> None:
    """Prevent this dummy generator from crossing the real activation gate."""

    if not isinstance(candidate_spec, dict):
        raise ValueError("real DrivAerML candidate specification must be an object")
    scoring_state = candidate_spec.get("scoring_support")
    if not isinstance(scoring_state, dict):
        raise ValueError("real DrivAerML scoring-support state is missing")
    if (
        candidate_spec.get("dataset_id") != REAL_DRIVAERML_DATASET_ID
        or candidate_spec.get("status") != REAL_DRIVAERML_CANDIDATE_STATUS
        or scoring_state.get("status") != REAL_DRIVAERML_SCORING_STATUS
        or scoring_state.get("submissions_open") is not False
    ):
        raise ValueError(
            "the real DrivAerML candidate is no longer in the exact closed, "
            "owner-review-required state expected by this synthetic fixture"
        )
    if (
        DATASET_ID == REAL_DRIVAERML_DATASET_ID
        or not DATASET_ID.startswith("synthetic-")
        or not RELEASE_ID.startswith("synthetic-")
        or not SUBMISSION_ID.startswith("synthetic-")
    ):
        raise ValueError(
            "dummy package identifiers must stay in an unmistakably synthetic "
            "namespace distinct from the real DrivAerML dataset"
        )


def _case_source_arrays(case: DemoCase) -> dict[str, np.ndarray]:
    """Return deterministic source truth and positive weights for a demo case."""

    raw_ids = np.arange(case.entity_count, dtype=np.int64)
    index = raw_ids.astype(np.float64)
    phase = case.case_offset
    pressure_truth = 8.0 + phase + 0.7 * index
    velocity_truth = np.column_stack(
        (
            30.0 + phase + 0.5 * index,
            -1.0 + 0.12 * index,
            0.5 - 0.07 * index,
        )
    )
    volumes = 0.5 + 0.03 * index + 0.01 * phase
    coordinates = np.column_stack(
        (0.25 * index, np.full(case.entity_count, phase), -0.1 * index)
    )
    return {
        "raw_ids": raw_ids,
        "pressure_truth": pressure_truth,
        "velocity_truth": velocity_truth,
        "volumes": volumes,
        "coordinates": coordinates,
    }


def _synthetic_model_outputs(case: DemoCase, raw_ids: np.ndarray) -> dict[str, np.ndarray]:
    """Produce model outputs separately from the reconstructed source payload."""

    index = raw_ids.astype(np.float64)
    phase = case.case_offset
    pressure_prediction = (
        8.0
        + phase
        + 0.7 * index
        + np.where(raw_ids % 2 == 0, 0.25, -0.4)
    )
    velocity_prediction = np.column_stack(
        (
            30.1 + phase + 0.51 * index,
            -1.0 + 0.12 * index + np.where(raw_ids % 2 == 0, -0.06, 0.04),
            0.47 - 0.065 * index,
        )
    )
    return {
        "pressure_prediction": pressure_prediction,
        "velocity_prediction": velocity_prediction,
    }


def _transport_payload(case: DemoCase, arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    """Create a pedagogical JSON byte stream; this is intentionally not VTU."""

    return {
        "warning": "synthetic JSON teaching payload; not VTK and not DrivAerML data",
        "case_id": case.case_id,
        "raw_cell_ids": arrays["raw_ids"].tolist(),
        "cell_volumes": arrays["volumes"].tolist(),
        "pMeanTrim_truth": arrays["pressure_truth"].tolist(),
        "UMeanTrim_truth": arrays["velocity_truth"].tolist(),
        "coordinates": arrays["coordinates"].tolist(),
    }


def _split_ordered_transport(
    output: Path,
    case: DemoCase,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split/rejoin arbitrary bytes, keeping byte parts distinct from cell chunks."""

    encoded = _canonical_bytes(payload)
    boundaries = [round(len(encoded) * index / case.part_count) for index in range(case.part_count + 1)]
    parts: list[dict[str, Any]] = []
    reconstructed_blocks: list[bytes] = []
    part_directory = output / "synthetic-transport" / case.case_id
    for part_index, (start, stop) in enumerate(
        zip(boundaries[:-1], boundaries[1:], strict=True)
    ):
        block = encoded[start:stop]
        part_path = part_directory / f"payload.{part_index:02d}.part"
        part_path.parent.mkdir(parents=True, exist_ok=True)
        part_path.write_bytes(block)
        reconstructed_blocks.append(part_path.read_bytes())
        parts.append(
            {
                "part_index": part_index,
                "file": part_path.relative_to(output).as_posix(),
                "byte_size": len(block),
                "sha256": _sha256_bytes(block),
            }
        )
    reconstructed = b"".join(reconstructed_blocks)
    if reconstructed != encoded:
        raise ValueError(f"{case.case_id} ordered byte reconstruction changed the payload")
    decoded = json.loads(reconstructed.decode("utf-8"))
    if decoded != payload:
        raise ValueError(f"{case.case_id} reconstructed payload changed semantically")
    return decoded, {
        "part_count": case.part_count,
        "parts": parts,
        "logical_byte_size": len(encoded),
        "logical_sha256": _sha256_bytes(encoded),
        "ordered_byte_reconstruction_exact": True,
        "note": (
            "Part boundaries are arbitrary byte offsets and are independent of "
            "the raw-cell inference chunks below."
        ),
    }


def _compare_sums(
    chunked: FinalizedFieldStatistics,
    whole: FinalizedFieldStatistics,
) -> dict[str, Any]:
    absolute_differences: dict[str, float] = {}
    for weighting in ("uniform", "physical"):
        chunk_sums = getattr(chunked, weighting)
        whole_sums = getattr(whole, weighting)
        for field in (
            "absolute_error",
            "squared_error",
            "squared_truth",
            "total_weight",
        ):
            key = f"{weighting}.{field}"
            absolute_differences[key] = abs(
                float(getattr(chunk_sums, field)) - float(getattr(whole_sums, field))
            )
            if not math.isclose(
                float(getattr(chunk_sums, field)),
                float(getattr(whole_sums, field)),
                rel_tol=2e-15,
                abs_tol=1e-15,
            ):
                raise ValueError(f"chunked/full sufficient statistics differ for {key}")
        if chunk_sums.entity_count != whole_sums.entity_count:
            raise ValueError(f"chunked/full entity counts differ for {weighting}")
    return {
        "passed": True,
        "maximum_absolute_sufficient_statistic_difference": max(
            absolute_differences.values(), default=0.0
        ),
        "absolute_differences": absolute_differences,
    }


def _accumulate_field(
    case: DemoCase,
    arrays: dict[str, np.ndarray],
    *,
    truth_key: str,
    prediction_key: str,
    component_count: int,
) -> tuple[FinalizedFieldStatistics, dict[str, Any]]:
    raw_ids = arrays["raw_ids"]
    truth = arrays[truth_key]
    prediction = arrays[prediction_key]
    volumes = arrays["volumes"]

    chunk_statistics = [
        field_chunk_statistics(
            raw_ids[start:stop],
            truth[start:stop],
            prediction[start:stop],
            volumes[start:stop],
        )
        for start, stop in case.chunk_ranges
    ]
    chunked = StreamingFieldAccumulator(
        case.entity_count,
        component_count=component_count,
    )
    for chunk_index in case.processing_order:
        chunked.add_statistics(chunk_statistics[chunk_index])
    chunked_result = chunked.finalize()

    whole = StreamingFieldAccumulator(
        case.entity_count,
        component_count=component_count,
    )
    whole.add_chunk(raw_ids, truth, prediction, volumes)
    whole_result = whole.finalize()
    invariance = _compare_sums(chunked_result, whole_result)
    return chunked_result, invariance


def _support_ids(raw_ids: Iterable[int]) -> list[str]:
    return [f"raw-cell-{int(raw_id):012d}" for raw_id in raw_ids]


def _metric_evidence(
    pressure: FinalizedFieldStatistics,
    velocity: FinalizedFieldStatistics,
) -> dict[str, dict[str, Any]]:
    return {
        "volume_pressure_rel_l2": pressure.uniform.relative_l2_evidence(
            weighting="uniform",
            dataset_weighting="volume_cells_equal",
        ),
        "volume_pressure_physical_rel_l2": pressure.physical.relative_l2_evidence(
            weighting="support_weights",
            dataset_weighting="cell_volume",
        ),
        "volume_velocity_rel_l2": velocity.uniform.relative_l2_evidence(
            weighting="uniform",
            dataset_weighting="volume_cells_equal",
        ),
        "volume_velocity_physical_rel_l2": velocity.physical.relative_l2_evidence(
            weighting="support_weights",
            dataset_weighting="cell_volume",
        ),
    }


def _assert_evaluator_matches_chunks(
    case_metrics: dict[str, Any],
    expected: dict[str, dict[str, dict[str, Any]]],
) -> None:
    for case in case_metrics["cases"]:
        actual = case["supports"][0]["metric_sufficient_statistics"]
        for metric_id, expected_statistics in expected[case["case_id"]].items():
            actual_statistics = actual[metric_id]
            for key in (
                "reduction",
                "weighting",
                "dataset_weighting",
                "entity_count",
            ):
                if actual_statistics[key] != expected_statistics[key]:
                    raise ValueError(
                        f"{case['case_id']}/{metric_id}/{key} differs between "
                        "chunk accumulator and schema-v3 evaluator"
                    )
            for key in ("numerator", "denominator", "total_weight"):
                if not math.isclose(
                    float(actual_statistics[key]),
                    float(expected_statistics[key]),
                    rel_tol=2e-15,
                    abs_tol=1e-15,
                ):
                    raise ValueError(
                        f"{case['case_id']}/{metric_id}/{key} differs between "
                        "chunk accumulator and schema-v3 evaluator"
                    )


def _support_definition() -> dict[str, Any]:
    components = [
        {
            "id": "pressure",
            "target_field": "pMeanTrim_truth",
            "target_association": "table_field",
            "prediction_field": "pMeanTrim_prediction",
        }
    ]
    velocity_components = [
        {
            "id": component,
            "target_field": f"UMeanTrim_{component}_truth",
            "target_association": "table_field",
            "prediction_field": f"UMeanTrim_{component}_prediction",
        }
        for component in ("x", "y", "z")
    ]
    bindings = [
        {
            "metric_id": metric_id,
            "quantity_id": quantity_id,
            "reduction": "relative_l2_percent",
            "weighting": weighting,
            "dataset_weighting": dataset_weighting,
            "aggregation": "per_geometry_then_macro_average",
            "case_evidence": "metric_value",
        }
        for metric_id, quantity_id, weighting, dataset_weighting in (
            (
                "volume_pressure_rel_l2",
                "volume_pressure",
                "uniform",
                "volume_cells_equal",
            ),
            (
                "volume_pressure_physical_rel_l2",
                "volume_pressure",
                "support_weights",
                "cell_volume",
            ),
            (
                "volume_velocity_rel_l2",
                "volume_velocity",
                "uniform",
                "volume_cells_equal",
            ),
            (
                "volume_velocity_physical_rel_l2",
                "volume_velocity",
                "support_weights",
                "cell_volume",
            ),
        )
    ]
    return {
        "id": SUPPORT_ID,
        "domain": "volume",
        "location_definition": {
            "mode": "materialized_table",
            "format": "json",
            "artifact_role": "ground_truth_table",
            "support_id_rule": {"kind": "artifact_field", "field": "support_id"},
            "coordinate_fields": ["x", "y", "z"],
            "weight_rule": {
                "kind": "artifact_field",
                "artifact_role": "ground_truth_table",
                "field": "cell_volume",
            },
            "ordering": "support_id_ascending",
        },
        "quantities": [
            {"id": "volume_pressure", "unit": "m^2/s^2", "components": components},
            {"id": "volume_velocity", "unit": "m/s", "components": velocity_components},
        ],
        "metric_bindings": bindings,
        "required_coverage": {
            "count_fraction": 1.0,
            "weight_fraction": 1.0,
            "unmapped_count": 0,
        },
        "extrapolation_policy": "forbidden",
    }


def _per_case_count(values: list[int]) -> dict[str, Any]:
    ordered = sorted(values)
    middle = len(ordered) // 2
    median = (
        float(ordered[middle])
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    return {
        "kind": "per_case",
        "minimum": min(ordered),
        "median": median,
        "maximum": max(ordered),
    }


def _used_native_volume_representation(entity_counts: list[int]) -> dict[str, Any]:
    return {
        "used": True,
        "representation": "synthetic raw native-cell-shaped table",
        "entity_counts": [
            {"entity": "native_cells", "count": _per_case_count(entity_counts)}
        ],
        "native_comparison": {"status": "not_applicable"},
        "sampling": {"kind": "none"},
        "domain": {"kind": "full_dataset_domain"},
        "connectivity": "none",
        "notes": "Tiny synthetic teaching fixture; no VTK mesh is represented.",
    }


def _write_submission_package(
    output: Path,
    *,
    support_manifest_path: Path,
    prediction_manifest_path: Path,
    case_metrics_path: Path,
) -> tuple[dict[str, Path], Path]:
    """Write the remaining schema-v3 package without making real-data claims."""

    case_ids = [case.case_id for case in CASES]
    entity_counts = [case.entity_count for case in CASES]
    split_path = output / "synthetic-split.json"
    _write_json(
        split_path,
        {
            "status": "synthetic_ineligible_fixture",
            "dataset_id": DATASET_ID,
            "split_id": SPLIT_ID,
            "case_ids": case_ids,
            "not_an_official_drivaerml_split": True,
        },
    )
    split_sha256 = sha256_file(split_path)

    profile_chunk_path = output / "profiles" / "chunk-000.json"
    profile_cases: list[dict[str, Any]] = []
    for case in CASES:
        arrays = _case_source_arrays(case)
        predicted = _synthetic_model_outputs(case, arrays["raw_ids"])
        profile_cases.append(
            {
                "case_id": case.case_id,
                "series": [
                    {
                        "panel_id": "synthetic-native-cell-sequence",
                        "station_id": "raw-cell-order",
                        "quantity_id": "pMeanTrim",
                        "coordinate": arrays["raw_ids"].astype(float).tolist(),
                        "prediction": predicted["pressure_prediction"].tolist(),
                    }
                ],
            }
        )
    _write_json(
        profile_chunk_path,
        {"schema_version": "1.0", "cases": profile_cases},
    )
    profile_index_path = output / "profiles" / "index.json"
    _write_json(
        profile_index_path,
        {
            "schema_version": "1.0",
            "submission_id": SUBMISSION_ID,
            "dataset_id": DATASET_ID,
            "split_id": SPLIT_ID,
            "case_set_id": CASE_SET_ID,
            "case_count": len(CASES),
            "case_id_status": "prototype_generated",
            "chunks": [
                {
                    "file": profile_chunk_path.name,
                    "case_ids": case_ids,
                    "sha256": sha256_file(profile_chunk_path),
                }
            ],
        },
    )
    profile_ground_truth_path = output / "profiles" / "ground-truth-manifest.json"
    _write_json(
        profile_ground_truth_path,
        {
            "release_id": PROFILE_RELEASE_ID,
            "status": "synthetic_ineligible_fixture",
            "case_ids": case_ids,
            "note": "No real DrivAerML profile truth is present in this fixture.",
        },
    )
    profile_ground_truth_sha256 = sha256_file(profile_ground_truth_path)

    case_record_path = output / "discretization" / "cases.jsonl"
    case_records = [
        {
            "$schema": "https://fluidsbench.org/schemas/v3/discretization-case.schema.json",
            "schema_version": "1.0",
            "submission_id": SUBMISSION_ID,
            "dataset_id": DATASET_ID,
            "split_id": SPLIT_ID,
            "case_id": case.case_id,
            "inference": {
                "inputs": [],
                "direct_outputs": [
                    {
                        "id": "volume-native-cell-output",
                        "entity_counts": [
                            {"entity": "native_cells", "count": case.entity_count}
                        ],
                        "native_entity_counts": [
                            {"entity": "native_cells", "count": case.entity_count}
                        ],
                        "native_fractions": [
                            {"entity": "native_cells", "fraction": 1.0}
                        ],
                        "domain": {"kind": "full_dataset_domain"},
                    }
                ],
                "mappings": [
                    {
                        "support_id": SUPPORT_ID,
                        "source_output_id": "volume-native-cell-output",
                        "support_count": case.entity_count,
                        "scored_count": case.entity_count,
                        "unmapped_count": 0,
                        "extrapolated_count": 0,
                        "final_coverage_fraction": 1.0,
                    }
                ],
            },
        }
        for case in CASES
    ]
    _write_jsonl(case_record_path, case_records)

    discretization_path = output / "discretization.json"
    representation = _used_native_volume_representation(entity_counts)
    _write_json(
        discretization_path,
        {
            "$schema": "https://fluidsbench.org/schemas/v3/discretization.schema.json",
            "schema_version": "1.0",
            "submission_id": SUBMISSION_ID,
            "dataset_id": DATASET_ID,
            "split_id": SPLIT_ID,
            "scoring_support_release_id": RELEASE_ID,
            "scoring_support_manifest_sha256": sha256_file(support_manifest_path),
            "training": {
                "surface_input": {"used": False},
                "surface_supervision": {"used": False},
                "volume_input": {"used": False},
                "volume_supervision": representation,
            },
            "inference": {
                "geometry_dependency": "other",
                "geometry_dependency_explanation": (
                    "Synthetic arrays generated internally; no real geometry was read."
                ),
                "surface_input": {"used": False},
                "volume_input": {"used": False},
                "direct_outputs": [
                    {
                        "id": "volume-native-cell-output",
                        "domain": "volume",
                        "representation": representation,
                        "queries_per_forward_pass": _per_case_count(entity_counts),
                    }
                ],
                "mappings": [
                    {
                        "support_id": SUPPORT_ID,
                        "source_output_id": "volume-native-cell-output",
                        "method": {"kind": "identity"},
                        "implementation": (
                            "examples/drivaerml-candidate-native-chunks/reference_driver.py"
                        ),
                        "extrapolation_policy": "forbidden",
                        "unmapped_fraction": 0.0,
                        "extrapolated_fraction": 0.0,
                        "final_coverage_fraction": 1.0,
                    }
                ],
            },
            "case_manifest": {
                "format": "jsonl",
                "file": "discretization/cases.jsonl",
                "sha256": sha256_file(case_record_path),
                "case_count": len(CASES),
            },
            "notes": "Synthetic and ineligible; no native DrivAerML mesh was used.",
        },
    )

    case_metrics = json.loads(case_metrics_path.read_text(encoding="utf-8"))
    evidence_path = output / "evaluation-evidence.json"
    _write_json(
        evidence_path,
        {
            "$schema": "https://fluidsbench.org/schemas/v3/evaluation-evidence.schema.json",
            "schema_version": "3.0",
            "submission_id": SUBMISSION_ID,
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "split_id": SPLIT_ID,
            "split_sha256": split_sha256,
            "case_set_id": CASE_SET_ID,
            "reference_version": "synthetic-drivaerml-chunk-driver-v2",
            "command": (
                "python examples/drivaerml-candidate-native-chunks/"
                "reference_driver.py --output OUTPUT"
            ),
            "generated_at": GENERATED_AT,
            "status": "submitted_evaluation",
            "metric_values": case_metrics["metric_values"],
            "profile_index_sha256": sha256_file(profile_index_path),
            "profile_ground_truth_release_id": PROFILE_RELEASE_ID,
            "profile_ground_truth_manifest_sha256": profile_ground_truth_sha256,
            "scoring_support_release_id": RELEASE_ID,
            "scoring_support_manifest_sha256": sha256_file(support_manifest_path),
            "discretization_sha256": sha256_file(discretization_path),
            "case_metrics_sha256": sha256_file(case_metrics_path),
            "notes": (
                "Schema exercise only: synthetic, ineligible, unapproved, and not "
                "a DrivAerML participant evaluation."
            ),
        },
    )

    submission_path = output / "submission.json"
    _write_json(
        submission_path,
        {
            "$schema": "https://fluidsbench.org/schemas/v3/submission.schema.json",
            "schema_version": "3.0",
            "submission_id": SUBMISSION_ID,
            "model": "Deterministic Synthetic Teaching Function",
            "model_type": "Synthetic fixture",
            "model_types": ["Synthetic fixture"],
            "training_regime": "other",
            "training_regime_explanation": (
                "No model was trained; deterministic synthetic values exercise packaging only."
            ),
            "target_data_used": "none",
            "external_pretraining": False,
            "pretraining_data": [],
            "dataset": "Synthetic DrivAerML-shaped teaching fixture",
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "split": "Synthetic two-case demonstration",
            "split_id": SPLIT_ID,
            "case_set_id": CASE_SET_ID,
            "split_sha256": split_sha256,
            "parameter_count_millions": None,
            "submitter_name": "FluidsBench synthetic fixture",
            "institution": "No institution; generated test fixture",
            "paper_url": "",
            "submitted_at": SUBMITTED_AT,
            "evaluation": {
                "reference_version": "synthetic-drivaerml-chunk-driver-v2",
                "command": (
                    "python examples/drivaerml-candidate-native-chunks/"
                    "reference_driver.py --output OUTPUT"
                ),
                "evidence_file": "evaluation-evidence.json",
                "evidence_sha256": sha256_file(evidence_path),
            },
            "reproducibility": {
                "contract_version": "open-reproducibility-3.0",
                "access": "public",
                "public_test_data_use": "evaluation_only",
                "result_data_license_spdx": "CC-BY-4.0",
            },
            "scoring_support": {
                "status": "candidate",
                "release_id": RELEASE_ID,
                "manifest_url": (
                    "https://example.invalid/fluidsbench/synthetic-drivaerml-shaped/"
                    "support/manifest.json"
                ),
                "manifest_sha256": sha256_file(support_manifest_path),
            },
            "spatial_discretization": {
                "format": "fluidsbench-discretization-v1",
                "file": "discretization.json",
                "sha256": sha256_file(discretization_path),
            },
            "case_metrics": {
                "format": "fluidsbench-case-metrics-v1",
                "file": "metrics/cases.json",
                "sha256": sha256_file(case_metrics_path),
                "case_count": len(CASES),
            },
            "metric_values": case_metrics["metric_values"],
            "profile_data": {
                "format": "fluidsbench-profile-chunks-v1",
                "index_file": "profiles/index.json",
                "case_count": len(CASES),
                "case_set_id": CASE_SET_ID,
                "profile_ground_truth_release_id": PROFILE_RELEASE_ID,
                "profile_ground_truth_manifest_sha256": profile_ground_truth_sha256,
            },
            "note": (
                "INELIGIBLE SYNTHETIC FIXTURE. This is not DrivAerML data, an "
                "active DrivAerML contract, a model result, owner approval, or an "
                "independent participant dry run. Candidate status applies only "
                "to this isolated fictional support namespace."
            ),
        },
    )
    return (
        {
            "v1/profile-chunk.schema.json": profile_chunk_path,
            "v1/profile-index.schema.json": profile_index_path,
            "v3/discretization-case.schema.json": case_record_path,
            "v3/discretization.schema.json": discretization_path,
            "v3/evaluation-evidence.schema.json": evidence_path,
            "v3/submission.schema.json": submission_path,
        },
        submission_path,
    )


def run_demo(output: Path) -> dict[str, Any]:
    """Generate, evaluate, and schema-check the candidate dry-run slice."""

    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    candidate_spec_path = (
        REPOSITORY_ROOT / "benchmark-specs" / "drivaerml" / "submission-spec.json"
    )
    candidate_spec = json.loads(candidate_spec_path.read_text(encoding="utf-8"))
    _assert_closed_real_drivaerml_candidate(candidate_spec)
    scoring_state = candidate_spec["scoring_support"]

    support_data_directory = output / "support" / "case-sets" / CASE_SET_ID / "data"
    prediction_data_directory = output / "predictions" / "data"
    case_instances: list[dict[str, Any]] = []
    prediction_cases: list[dict[str, Any]] = []
    case_receipts: list[dict[str, Any]] = []
    expected_statistics: dict[str, dict[str, dict[str, Any]]] = {}

    for case in CASES:
        generated = _case_source_arrays(case)
        decoded, transport_receipt = _split_ordered_transport(
            output,
            case,
            _transport_payload(case, generated),
        )
        arrays = {
            "raw_ids": np.asarray(decoded["raw_cell_ids"], dtype=np.int64),
            "pressure_truth": np.asarray(decoded["pMeanTrim_truth"], dtype=np.float64),
            "velocity_truth": np.asarray(decoded["UMeanTrim_truth"], dtype=np.float64),
            "volumes": np.asarray(decoded["cell_volumes"], dtype=np.float64),
            "coordinates": np.asarray(decoded["coordinates"], dtype=np.float64),
        }
        arrays.update(_synthetic_model_outputs(case, arrays["raw_ids"]))
        pressure, pressure_invariance = _accumulate_field(
            case,
            arrays,
            truth_key="pressure_truth",
            prediction_key="pressure_prediction",
            component_count=1,
        )
        velocity, velocity_invariance = _accumulate_field(
            case,
            arrays,
            truth_key="velocity_truth",
            prediction_key="velocity_prediction",
            component_count=3,
        )
        expected_statistics[case.case_id] = _metric_evidence(pressure, velocity)

        ids = _support_ids(arrays["raw_ids"])
        coordinates = arrays["coordinates"]
        truth_table = {
            "columns": {
                "support_id": ids,
                "x": coordinates[:, 0].tolist(),
                "y": coordinates[:, 1].tolist(),
                "z": coordinates[:, 2].tolist(),
                "cell_volume": arrays["volumes"].tolist(),
                "pMeanTrim_truth": arrays["pressure_truth"].tolist(),
                "UMeanTrim_x_truth": arrays["velocity_truth"][:, 0].tolist(),
                "UMeanTrim_y_truth": arrays["velocity_truth"][:, 1].tolist(),
                "UMeanTrim_z_truth": arrays["velocity_truth"][:, 2].tolist(),
            }
        }
        prediction_table = {
            "columns": {
                "support_id": ids,
                "pMeanTrim_prediction": arrays["pressure_prediction"].tolist(),
                "UMeanTrim_x_prediction": arrays["velocity_prediction"][:, 0].tolist(),
                "UMeanTrim_y_prediction": arrays["velocity_prediction"][:, 1].tolist(),
                "UMeanTrim_z_prediction": arrays["velocity_prediction"][:, 2].tolist(),
            }
        }
        truth_path = support_data_directory / f"{case.case_id}-ground-truth.json"
        prediction_path = prediction_data_directory / f"{case.case_id}.json"
        _write_json(truth_path, truth_table)
        _write_json(prediction_path, prediction_table)
        case_instances.append(
            {
                "case_id": case.case_id,
                "support_instances": [
                    {
                        "support_id": SUPPORT_ID,
                        "entity_count": case.entity_count,
                        "artifacts": [
                            {
                                "role": "ground_truth_table",
                                "path": f"data/{truth_path.name}",
                                "sha256": sha256_file(truth_path),
                                "byte_size": truth_path.stat().st_size,
                                "format": "json",
                            }
                        ],
                    }
                ],
            }
        )
        prediction_cases.append(
            {
                "case_id": case.case_id,
                "files": [
                    {
                        "support_id": SUPPORT_ID,
                        "file": f"data/{prediction_path.name}",
                        "sha256": sha256_file(prediction_path),
                        "format": "json",
                        "row_count": case.entity_count,
                    }
                ],
            }
        )
        case_receipts.append(
            {
                "case_id": case.case_id,
                "synthetic": True,
                "entity_count": case.entity_count,
                "transport": transport_receipt,
                "inference_chunks": {
                    "raw_id_half_open_ranges": [list(item) for item in case.chunk_ranges],
                    "processing_order_by_range_index": list(case.processing_order),
                    "complete_duplicate_free_coverage": True,
                    "independent_of_transport_part_boundaries": True,
                },
                "full_case_vs_chunked": {
                    "pressure": pressure_invariance,
                    "velocity": velocity_invariance,
                },
            }
        )

    support_case_directory = output / "support" / "case-sets" / CASE_SET_ID
    chunk_path = support_case_directory / "chunk-000.json"
    chunk = {
        "$schema": "https://fluidsbench.org/schemas/scoring-support/v1/case-chunk.schema.json",
        "schema_version": "1.0",
        "release_id": RELEASE_ID,
        "dataset_id": DATASET_ID,
        "case_set_id": CASE_SET_ID,
        "cases": case_instances,
    }
    _write_json(chunk_path, chunk)
    index_path = support_case_directory / "index.json"
    index = {
        "$schema": "https://fluidsbench.org/schemas/scoring-support/v1/case-index.schema.json",
        "schema_version": "1.0",
        "release_id": RELEASE_ID,
        "dataset_id": DATASET_ID,
        "case_set_id": CASE_SET_ID,
        "case_count": len(CASES),
        "chunks": [
            {
                "file": chunk_path.name,
                "sha256": sha256_file(chunk_path),
                "case_count": len(CASES),
                "case_ids": [case.case_id for case in CASES],
            }
        ],
    }
    _write_json(index_path, index)
    support_manifest_path = output / "support" / "manifest.json"
    support_manifest = {
        "$schema": "https://fluidsbench.org/schemas/scoring-support/v1/manifest.schema.json",
        "schema_version": "1.0",
        "release_id": RELEASE_ID,
        "status": "candidate",
        "published_at": "2026-08-20T00:00:00Z",
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "evaluation_reference_version": "synthetic-drivaerml-chunk-driver-v2",
        "coordinate_frame": {
            "id": "synthetic-cartesian-v1",
            "axis_order": ["x", "y", "z"],
            "handedness": "right",
            "length_unit": "m",
            "normalization": "none",
        },
        "supports": [_support_definition()],
        "case_sets": [
            {
                "id": CASE_SET_ID,
                "case_count": len(CASES),
                "index_file": f"case-sets/{CASE_SET_ID}/index.json",
                "index_sha256": sha256_file(index_path),
            }
        ],
        "notes": (
            "Synthetic candidate support only. This is not DrivAerML data, active "
            "DrivAerML scoring support, a participant result, or owner approval."
        ),
    }
    _write_json(support_manifest_path, support_manifest)

    prediction_manifest_path = output / "predictions" / "manifest.json"
    prediction_manifest = {
        "$schema": "https://fluidsbench.org/schemas/v3/prediction-artifact.schema.json",
        "schema_version": "1.0",
        "format": "fluidsbench-prediction-artifact-v1",
        "artifact_id": "drivaerml-synthetic-complete-predictions-v1",
        "kind": "scored_predictions",
        "submission_id": SUBMISSION_ID,
        "dataset_id": DATASET_ID,
        "split_id": SPLIT_ID,
        "case_set_id": CASE_SET_ID,
        "support_release_id": RELEASE_ID,
        "support_manifest_sha256": sha256_file(support_manifest_path),
        "case_count": len(CASES),
        "cases": prediction_cases,
    }
    _write_json(prediction_manifest_path, prediction_manifest)

    case_metrics = evaluate_prediction_artifact(
        support_manifest_path=support_manifest_path,
        case_set_id=CASE_SET_ID,
        prediction_manifest_path=prediction_manifest_path,
        submission_id=SUBMISSION_ID,
        split_id=SPLIT_ID,
    )
    _assert_evaluator_matches_chunks(case_metrics, expected_statistics)
    case_metrics_path = output / "metrics" / "cases.json"
    _write_json(case_metrics_path, case_metrics)

    package_schema_paths, submission_path = _write_submission_package(
        output,
        support_manifest_path=support_manifest_path,
        prediction_manifest_path=prediction_manifest_path,
        case_metrics_path=case_metrics_path,
    )

    schema_checks = [
        ("scoring-support/v1/manifest.schema.json", support_manifest_path),
        ("scoring-support/v1/case-index.schema.json", index_path),
        ("scoring-support/v1/case-chunk.schema.json", chunk_path),
        ("v3/prediction-artifact.schema.json", prediction_manifest_path),
        ("v3/case-metrics.schema.json", case_metrics_path),
    ]
    discretization_records_path = package_schema_paths.pop(
        "v3/discretization-case.schema.json"
    )
    schema_checks.extend(package_schema_paths.items())
    for schema_relative_path, value_path in schema_checks:
        _validate_schema(schema_relative_path, value_path)
    discretization_record_count = 0
    for line_number, line in enumerate(
        discretization_records_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line:
            continue
        errors = _schema_errors(
            REPOSITORY_ROOT / "schemas" / "v3" / "discretization-case.schema.json",
            json.loads(line),
        )
        if errors:
            raise ValueError(
                f"{discretization_records_path}:{line_number} does not match "
                "v3/discretization-case.schema.json:\n" + "\n".join(errors)
            )
        discretization_record_count += 1
    if discretization_record_count != len(CASES):
        raise ValueError("synthetic discretization JSONL does not cover both cases")

    receipt = {
        "status": "candidate_demo_valid",
        "mode": "synthetic_candidate_dry_run",
        "claims": {
            "uses_real_drivaerml_data": False,
            "validates_native_vtp_or_vtu_parsing": False,
            "validates_real_volume_cell_weights": False,
            "covers_surface_forces_or_autocfd5_profiles": False,
            "schema_v3_dummy_submission_generated": True,
            "official_drivaerml_submission_generated": False,
            "eligible_for_leaderboard_or_scientific_claims": False,
            "owner_scientific_approval": False,
            "independent_participant_dry_run": False,
        },
        "official_submission_block": (
            "DrivAerML scoring support is owner_review_required and submissions_open "
            "is false; generated submission.json belongs only to a separate, "
            "fictional, ineligible synthetic namespace."
        ),
        "observed_candidate_contract": {
            "file": candidate_spec_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "dataset_id": candidate_spec["dataset_id"],
            "dataset_status": candidate_spec["status"],
            "scoring_support_status": scoring_state["status"],
            "submissions_open": scoring_state["submissions_open"],
        },
        "demonstrated": [
            "ordered two-part byte reconstruction for synthetic run_1",
            "ordered three-part byte reconstruction for synthetic run_44",
            "raw-cell IDs and complete duplicate-free inference chunk coverage",
            "additive sufficient statistics reduced once per complete case",
            "full-case versus chunked relative-L2 invariance",
            "schema-v3 keyed prediction artifact packaging",
            "generic evaluator generation of schema-v3 case metrics",
            "complete schema-v3 dummy submission package construction",
            "public JSON Schema validation of generated artifacts",
        ],
        "cases": case_receipts,
        "metric_values": case_metrics["metric_values"],
        "artifacts": {
            path.relative_to(output).as_posix(): {
                "sha256": sha256_file(path),
                "byte_size": path.stat().st_size,
            }
            for path in (
                support_manifest_path,
                index_path,
                chunk_path,
                prediction_manifest_path,
                case_metrics_path,
                submission_path,
                output / "evaluation-evidence.json",
                output / "discretization.json",
                output / "discretization" / "cases.jsonl",
                output / "profiles" / "index.json",
                output / "profiles" / "chunk-000.json",
            )
        },
        "schema_checks": [item[0] for item in schema_checks]
        + ["v3/discretization-case.schema.json"],
    }
    receipt_path = output / "validation-receipt.json"
    _write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="new or empty directory for the generated synthetic dry-run bundle",
    )
    args = parser.parse_args()
    try:
        receipt = run_demo(args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(
        "CANDIDATE DEMO VALID: synthetic DrivAerML-shaped chunk/package dry run; "
        f"receipt={args.output.resolve() / 'validation-receipt.json'}"
    )
    print(receipt["official_submission_block"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
