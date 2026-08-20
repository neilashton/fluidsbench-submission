#!/usr/bin/env python3
"""Promote the reviewed DrivAerML proposal into the active closed candidate.

This migration is deliberately reproducible and idempotent. It activates the
real public split identities and the participant-facing scientific contract,
but it does not open submissions or manufacture the missing physics-null
baselines, profile supports, or all-case evaluator replays.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / "benchmark-specs" / "drivaerml"
PROPOSAL_ROOT = BENCHMARK_ROOT / "proposal"
SUBMISSIONS_ROOT = ROOT / "submissions" / "drivaerml"
MANIFEST_PATH = ROOT / "leaderboard" / "manifest.json"

DATASET_REVISION = "7a5c0948ce27be709b1116a3a190f806e7a8f79f"
DATASET_VERSION = "drivaerml-native-v1-candidate"
EVALUATOR_VERSION = "drivaerml-evaluator-v1-candidate"
SPLIT_MANIFEST_SHA256 = "032a2e9f88926d9218a1943b51e650135cc78683cad6b0a38f3cf4f9dfba647d"
SOURCE_PIN_SHA256 = "4fc9077f8f23f4994c98f4d0e7a17aef7b998de4c996638e3a8a616b6d923fdd"
SURFACE_AREA_MANIFEST_SHA256 = "1401c7e80bd86f3aa2d640289db9b088ce1e0825327e18eeb1ab2852de04323e"
FORCE_TABLE_SHA256 = "4e9e003da38ccdcacad359451079888361eae221d3c8dad7fd5682250d257865"

DRIVAER_DIMENSIONAL_CATALOG = (
    {
        "id": "drivaerml_surface_pmeantrim_native_area",
        "label": "Surface pMeanTrim",
        "unit": "m^2/s^2",
        "digits": 3,
        "statistics": ["mae", "rmse"],
        "weighting": "native_surface_polygon_area",
    },
    {
        "id": "drivaerml_surface_wallshearstressmeantrim_native_area",
        "label": "Surface wallShearStressMeanTrim",
        "unit": "m^2/s^2",
        "digits": 3,
        "statistics": ["mae", "rmse"],
        "weighting": "native_surface_polygon_area",
    },
    {
        "id": "drivaerml_volume_umeantrim_equal_cell",
        "label": "Volume UMeanTrim",
        "unit": "m/s",
        "digits": 3,
        "statistics": ["mae", "rmse"],
        "weighting": "equal_native_volume_cell",
    },
    {
        "id": "drivaerml_volume_pmeantrim_equal_cell",
        "label": "Volume pMeanTrim",
        "unit": "m^2/s^2",
        "digits": 3,
        "statistics": ["mae", "rmse"],
        "weighting": "equal_native_volume_cell",
    },
)

DRIVAER_COEFFICIENT_CATALOG = (
    {
        "id": "drivaerml_cd_equal_case_rmse",
        "label": "Field-integrated C_D",
        "unit": "",
        "digits": 5,
        "statistic": "rmse",
        "aggregation": "all_test_cases",
        "weighting": "cases_equal",
    },
    {
        "id": "drivaerml_cl_equal_case_rmse",
        "label": "Field-integrated C_L",
        "unit": "",
        "digits": 5,
        "statistic": "rmse",
        "aggregation": "all_test_cases",
        "weighting": "cases_equal",
    },
    {
        "id": "drivaerml_cmpitch_equal_case_rmse",
        "label": "Field-integrated C_M pitch",
        "unit": "",
        "digits": 5,
        "statistic": "rmse",
        "aggregation": "all_test_cases",
        "weighting": "cases_equal",
    },
)

SPLITS = {
    "full": ("Full", "standard"),
    "medium": ("Medium", "standard"),
    "scarce": ("Scarce", "standard"),
    "super_scarce": ("Super scarce", "standard"),
    "geometry": ("Geometry", "geometry"),
    "high_drag": ("High drag", "high_drag"),
    "low_drag": ("Low drag", "low_drag"),
    "rear_separation": ("Rear separation", "rear_separation"),
}

SCORE_EQUATIONS = {
    "overall_score": r"\sum_k \alpha_k S_k,\quad \sum_k \alpha_k=1",
    "field_score": r"\frac{\sum_{j\in F}\alpha_j S_j}{\sum_{j\in F}\alpha_j}",
    "force_score": r"\frac{\sum_{j\in C}\alpha_j S_j}{\sum_{j\in C}\alpha_j}",
    "diagnostic_score": r"\frac{\sum_{j\in D}\alpha_j S_j}{\sum_{j\in D}\alpha_j}",
}

RELATIVE_L2_EQUATION = (
    r"100\,\frac{\sqrt{\sum_i w_i\lVert\hat{\mathbf{y}}_i-"
    r"\mathbf{y}_i\rVert_2^2}}{\sqrt{\sum_i w_i\lVert\mathbf{y}_i\rVert_2^2}}"
)
MAE_EQUATION = (
    r"\frac{\sum_i w_i\lVert\hat{\mathbf{y}}_i-\mathbf{y}_i\rVert_2}{\sum_i w_i}"
)
RMSE_EQUATION = (
    r"\sqrt{\frac{\sum_i w_i\lVert\hat{\mathbf{y}}_i-\mathbf{y}_i\rVert_2^2}{\sum_i w_i}}"
)
CASE_RMSE_EQUATION = r"\sqrt{\frac{1}{N}\sum_c(\hat{y}_c-y_c)^2}"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{json.dumps(value, indent=2, ensure_ascii=True)}\n",
        encoding="utf-8",
    )


def upsert_catalog_entries(
    catalog_entries: list[dict[str, Any]],
    dataset_entries: tuple[dict[str, Any], ...],
) -> None:
    """Add or replace only dataset-prefixed metric-catalog entries."""

    positions = {
        entry.get("id"): index
        for index, entry in enumerate(catalog_entries)
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    for entry in dataset_entries:
        metric_id = entry["id"]
        if not metric_id.startswith("drivaerml_"):
            raise ValueError("DrivAerML catalog entries must use a dataset-prefixed ID")
        position = positions.get(metric_id)
        if position is None:
            positions[metric_id] = len(catalog_entries)
            catalog_entries.append(dict(entry))
        else:
            catalog_entries[position] = dict(entry)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def score_metric(metric_id: str) -> dict[str, Any]:
    return {
        "id": metric_id,
        "unit": "",
        "direction": "higher",
        "kind": "score",
        "equation": SCORE_EQUATIONS[metric_id],
        "aggregation": "derived_score_equation",
        "weighting": "dataset_declared_component_weights",
    }


def metric(
    metric_id: str,
    *,
    unit: str,
    equation: str,
    aggregation: str,
    weighting: str,
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "unit": unit,
        "direction": "lower",
        "kind": "error",
        "equation": equation,
        "aggregation": aggregation,
        "weighting": weighting,
    }


def build_metrics() -> list[dict[str, Any]]:
    metrics = [score_metric(metric_id) for metric_id in SCORE_EQUATIONS]
    metrics.extend(
        [
            metric(
                "surface_pressure_rel_l2",
                unit="%",
                equation=RELATIVE_L2_EQUATION,
                aggregation="per_geometry_then_macro_average",
                weighting="surface_face_area",
            ),
            metric(
                "surface_pressure_equal_entity_rel_l2",
                unit="%",
                equation=RELATIVE_L2_EQUATION,
                aggregation="per_geometry_then_macro_average",
                weighting="surface_entities_equal",
            ),
            metric(
                "surface_wall_shear_rel_l2",
                unit="%",
                equation=RELATIVE_L2_EQUATION,
                aggregation="per_geometry_then_macro_average",
                weighting="surface_face_area",
            ),
            metric(
                "surface_wall_shear_equal_entity_rel_l2",
                unit="%",
                equation=RELATIVE_L2_EQUATION,
                aggregation="per_geometry_then_macro_average",
                weighting="surface_entities_equal",
            ),
            metric(
                "volume_velocity_rel_l2",
                unit="%",
                equation=RELATIVE_L2_EQUATION,
                aggregation="per_geometry_then_macro_average",
                weighting="volume_cells_equal",
            ),
            metric(
                "volume_velocity_physical_rel_l2",
                unit="%",
                equation=RELATIVE_L2_EQUATION,
                aggregation="per_geometry_then_macro_average",
                weighting="cell_volume",
            ),
            metric(
                "volume_pressure_rel_l2",
                unit="%",
                equation=RELATIVE_L2_EQUATION,
                aggregation="per_geometry_then_macro_average",
                weighting="volume_cells_equal",
            ),
            metric(
                "volume_pressure_physical_rel_l2",
                unit="%",
                equation=RELATIVE_L2_EQUATION,
                aggregation="per_geometry_then_macro_average",
                weighting="cell_volume",
            ),
        ]
    )

    absolute_fields = [
        ("surface_pressure", "m^2/s^2", "area", "surface_face_area"),
        ("surface_pressure", "m^2/s^2", "equal_entity", "surface_entities_equal"),
        ("surface_wall_shear", "m^2/s^2", "area", "surface_face_area"),
        ("surface_wall_shear", "m^2/s^2", "equal_entity", "surface_entities_equal"),
        ("volume_velocity", "m/s", "equal_entity", "volume_cells_equal"),
        ("volume_velocity", "m/s", "physical", "cell_volume"),
        ("volume_pressure", "m^2/s^2", "equal_entity", "volume_cells_equal"),
        ("volume_pressure", "m^2/s^2", "physical", "cell_volume"),
    ]
    for field_id, unit, token, weighting in absolute_fields:
        prefix = f"drivaerml_{field_id}_{token}"
        metrics.extend(
            [
                metric(
                    f"{prefix}_mae",
                    unit=unit,
                    equation=MAE_EQUATION,
                    aggregation="per_geometry_then_macro_average",
                    weighting=weighting,
                ),
                metric(
                    f"{prefix}_rmse",
                    unit=unit,
                    equation=RMSE_EQUATION,
                    aggregation="per_geometry_then_macro_average",
                    weighting=weighting,
                ),
            ]
        )

    for metric_id in (
        "field_integrated_cd_rmse",
        "field_integrated_cl_rmse",
        "field_integrated_cmpitch_rmse",
        "field_integrated_clf_rmse",
        "field_integrated_clr_rmse",
    ):
        metrics.append(
            metric(
                metric_id,
                unit="",
                equation=CASE_RMSE_EQUATION,
                aggregation="all_test_cases",
                weighting="cases_equal",
            )
        )
    metrics.extend(
        [
            metric(
                "field_integrated_lift_closure_max_abs",
                unit="",
                equation=r"\max_c\lvert\hat{C}_{L,c}-(\hat{C}_{Lf,c}+\hat{C}_{Lr,c})\rvert",
                aggregation="all_test_cases",
                weighting="maximum_case_residual",
            ),
            metric(
                "velocity_profile_uinf_rmse",
                unit="",
                equation=(
                    r"\frac{1}{N}\sum_c\frac{1}{16}\sum_l"
                    r"\sqrt{\frac{\int_l(\hat{U}/U_\infty-U/U_\infty)^2\,ds}{\int_l ds}}"
                ),
                aggregation="equal_case_equal_line_macro_average",
                weighting="trapezoidal_arc_length_within_line",
            ),
            metric(
                "velocity_profile_experimental_subset_uinf_rmse",
                unit="",
                equation=(
                    r"\frac{1}{N}\sum_c\frac{1}{11}\sum_{l\in E}"
                    r"\sqrt{\frac{\int_l(\hat{U}/U_\infty-U/U_\infty)^2\,ds}{\int_l ds}}"
                ),
                aggregation="equal_case_equal_experimental_line_macro_average",
                weighting="trapezoidal_arc_length_within_line",
            ),
            metric(
                "cp_probe_rmse",
                unit="",
                equation=r"\frac{1}{N}\sum_c\sqrt{\frac{1}{209}\sum_{i=1}^{209}(\hat{C}_{p,ci}-C_{p,ci})^2}",
                aggregation="per_case_unique_probe_rmse_then_macro_average",
                weighting="209_unique_probes_equal",
            ),
            metric(
                "cp_panel_macro_rmse",
                unit="",
                equation=r"\frac{1}{N}\sum_c\frac{1}{15}\sum_p\sqrt{\frac{1}{n_p}\sum_{i\in p}(\hat{C}_{p,ci}-C_{p,ci})^2}",
                aggregation="per_case_panel_rmse_then_equal_panel_and_case_average",
                weighting="panel_membership_rows_equal",
            ),
        ]
    )
    return metrics


def build_profile_definition() -> dict[str, Any]:
    membership_path = PROPOSAL_ROOT / "autocfd_cp_panel_membership.csv"
    taps_path = PROPOSAL_ROOT / "autocfd_cp_taps_nominal.csv"
    component_path = PROPOSAL_ROOT / "autocfd_cp_tap_component_registry.csv"
    lines_path = PROPOSAL_ROOT / "autocfd_velocity_lines_nominal.csv"
    samples_path = PROPOSAL_ROOT / "autocfd_velocity_samples_10mm.csv"

    pressure_rows = read_csv(membership_path)
    pressure_groups: dict[str, list[dict[str, str]]] = {}
    for row in pressure_rows:
        pressure_groups.setdefault(row["panel_id"], []).append(row)
    corrected_labels = {"upperbody_centerline": "Upper-body centreline"}
    pressure_stations = []
    for panel_id, rows in pressure_groups.items():
        pressure_stations.append(
            {
                "id": panel_id,
                "label": corrected_labels.get(panel_id, rows[0]["panel_label"]),
                "source_label": rows[0]["panel_label"],
                "sample_count": len(rows),
                "coordinate_id": "panel_point_index",
                "coordinate_unit": "",
                "probes": [
                    {
                        "panel_point_index": int(row["panel_point_index"]),
                        "autocfd_probe_id": int(row["autocfd_probe_id"]),
                        "point_m": [float(row["x_m"]), float(row["y_m"]), float(row["z_m"])],
                    }
                    for row in rows
                ],
            }
        )

    line_rows = read_csv(lines_path)
    sample_rows = read_csv(samples_path)
    samples_by_line: dict[str, list[dict[str, str]]] = {}
    for row in sample_rows:
        samples_by_line.setdefault(row["profile_id"], []).append(row)
    velocity_stations = []
    for row in line_rows:
        profile_id = row["profile_id"]
        samples = samples_by_line[profile_id]
        velocity_stations.append(
            {
                "id": f"autocfd5_{profile_id.lower()}",
                "source_profile_id": profile_id,
                "label": f"AutoCFD5 {profile_id}",
                "start_m": [float(row["start_x_m"]), float(row["start_y_m"]), float(row["start_z_m"])],
                "end_m": [float(row["end_x_m"]), float(row["end_y_m"]), float(row["end_z_m"])],
                "length_m": float(row["length_m"]),
                "scoring_spacing_m": float(row["scoring_spacing_m"]),
                "sample_count": int(row["scoring_point_count"]),
                "coordinate_interval_m": [0.0, float(samples[-1]["distance_m"])],
                "experimental_availability": row["autocfd_experimental_availability"],
            }
        )

    return {
        "schema_version": "1.0",
        "id": "drivaerml-autocfd5-v8-candidate",
        "dataset_id": "drivaerml",
        "status": "candidate_support_pending_all_case_validation",
        "source": {
            "result_template_version": 8,
            "cp_nominal_registry": {"file": "proposal/autocfd_cp_taps_nominal.csv", "sha256": sha256_file(taps_path)},
            "cp_panel_membership": {"file": "proposal/autocfd_cp_panel_membership.csv", "sha256": sha256_file(membership_path)},
            "cp_component_registry": {"file": "proposal/autocfd_cp_tap_component_registry.csv", "sha256": sha256_file(component_path)},
            "velocity_lines": {"file": "proposal/autocfd_velocity_lines_nominal.csv", "sha256": sha256_file(lines_path)},
            "velocity_scoring_grid": {"file": "proposal/autocfd_velocity_samples_10mm.csv", "sha256": sha256_file(samples_path)},
        },
        "pressure_profiles": {
            "ranked_metric_id": "cp_probe_rmse",
            "unique_probe_count": len({row["autocfd_probe_id"] for row in pressure_rows}),
            "panel_count": len(pressure_stations),
            "panel_membership_row_count": len(pressure_rows),
            "duplicate_rule": "a reused probe is scored once in the ranked unique-probe metric and once in each containing display panel",
            "quantity": "Cp=2*pMeanTrim/(38.889^2)",
            "stations": pressure_stations,
        },
        "velocity_profiles": {
            "ranked_metric_id": "velocity_profile_uinf_rmse",
            "quantity": "magnitude(UMeanTrim)/38.889",
            "scoring_grid": "fixed_10_mm_candidate_grid",
            "line_count": len(velocity_stations),
            "sample_count_per_case": sum(station["sample_count"] for station in velocity_stations),
            "stations": velocity_stations,
        },
        "activation_requirements": [
            "publish_all_case_containing_cell_assignments_and_hashes",
            "pass_velocity_1_2_5_10mm_resolution_convergence",
            "pass_all_case_cp_projection_and_source_relation_replay",
            "complete_owner_visual_signoff_for_all_cp_component_mappings",
        ],
    }


def write_splits() -> list[dict[str, Any]]:
    owner = load_json(PROPOSAL_ROOT / "owner-published-splits.json")
    entries = []
    for split_id, (label, case_set_id) in SPLITS.items():
        train = owner[f"{split_id}_train"]
        validation = owner[f"{split_id}_val"]
        test = owner[f"{split_id}_test"]
        split = {
            "schema_version": "1.0",
            "dataset_id": "drivaerml",
            "split_id": split_id,
            "case_set_id": case_set_id,
            "split_label": label,
            "case_id_status": "official",
            "training_case_count": len(train),
            "validation_case_count": len(validation),
            "case_count": len(test),
            "train_case_ids": train,
            "validation_case_ids": validation,
            "case_ids": test,
            "source": {
                "repository": "neashton/drivaerml",
                "revision": DATASET_REVISION,
                "manifest_path": "splits/manifest.json",
                "manifest_sha256": SPLIT_MANIFEST_SHA256,
                "manifest_keys": [f"{split_id}_train", f"{split_id}_val", f"{split_id}_test"],
            },
            "usage": {
                "train": "model fitting and training-only preprocessing statistics",
                "validation": "checkpoint and hyperparameter selection",
                "test": "evaluation only; no fitting, tuning, or preprocessing statistics",
            },
        }
        path = BENCHMARK_ROOT / "splits" / f"{split_id}.json"
        write_json(path, split)
        entries.append(
            {
                "id": split_id,
                "label": label,
                "index_file": f"splits/{split_id}.json",
                "training_case_count": len(train),
                "validation_case_count": len(validation),
                "case_count": len(test),
                "case_set_id": case_set_id,
                "case_id_status": "official",
                "sha256": sha256_file(path),
            }
        )
    return entries


def build_profile_panels(profile: dict[str, Any]) -> list[dict[str, Any]]:
    pressure = profile["pressure_profiles"]["stations"]
    velocity = profile["velocity_profiles"]["stations"]
    return [
        {
            "id": "pressure_profiles",
            "required": True,
            "allow_unlisted_stations": False,
            "minimum_points": 2,
            "coordinate_order": "strictly_increasing",
            "coordinate_id": "panel_point_index",
            "coordinate_unit": "",
            "metric_id": "cp_probe_rmse",
            "station_ids": [station["id"] for station in pressure],
            "quantity_ids": ["cp"],
            "station_sample_counts": {station["id"]: station["sample_count"] for station in pressure},
            "station_coordinate_intervals": {station["id"]: [1.0, float(station["sample_count"])] for station in pressure},
            "station_coordinate_spacings": {station["id"]: "uniform" for station in pressure},
        },
        {
            "id": "velocity_profiles",
            "required": True,
            "allow_unlisted_stations": False,
            "minimum_points": 2,
            "coordinate_order": "strictly_increasing",
            "coordinate_id": "distance_m",
            "coordinate_unit": "m",
            "metric_id": "velocity_profile_uinf_rmse",
            "station_ids": [station["id"] for station in velocity],
            "quantity_ids": ["velocity_ratio"],
            "station_sample_counts": {station["id"]: station["sample_count"] for station in velocity},
            "station_coordinate_intervals": {station["id"]: station["coordinate_interval_m"] for station in velocity},
            "station_coordinate_spacings": {station["id"]: "uniform" for station in velocity},
        },
    ]


def build_composite() -> dict[str, Any]:
    weighted = [
        ("surface_pressure_rel_l2", 0.15),
        ("surface_wall_shear_rel_l2", 0.10),
        ("volume_velocity_rel_l2", 0.15),
        ("volume_pressure_rel_l2", 0.10),
        ("field_integrated_cd_rmse", 0.15),
        ("field_integrated_cl_rmse", 0.05),
        ("field_integrated_cmpitch_rmse", 0.05),
        ("velocity_profile_uinf_rmse", 0.15),
        ("cp_probe_rmse", 0.10),
    ]
    return {
        "metric_id": "overall_score",
        "operation": "weighted_component_scores",
        "status": "pending_reference_baselines",
        "allow_negative_scores": True,
        "component_skill_equation": "100*(1-E_j/B_j)",
        "components": [
            {
                "metric_id": metric_id,
                "weight": weight,
                "transform": "physics_null_skill",
                "baseline_id": f"drivaerml.physics_null.{metric_id}",
                "baseline_status": "pending_all_case_evaluator_replay",
            }
            for metric_id, weight in weighted
        ],
        "tolerance": 1e-6,
        "activation_rule": "set status=active and publish one finite positive baseline_error per component only after frozen evaluator replay and sensitivity review",
    }


def build_scoring_support(profile_path: Path) -> dict[str, Any]:
    return {
        "status": "owner_review_required",
        "submissions_open": False,
        "closed_reason": (
            "The participant contract and official splits are published, but ranking remains closed until "
            "deterministic volume weights, all-case velocity replay, Cp failure resolution and visual review, "
            "physics-null baselines, genuine-model sensitivity analysis, schema-v3 nonspatial-result binding, "
            "force-replay review, and immutable evaluator/scoring-support owner approval are complete."
        ),
        "candidate_evidence_index_file": "evidence/README.md",
        "candidate_evidence_manifest_file": "evidence/manifest.json",
        "source_release": {
            "provider": "Hugging Face Hub",
            "repository": "neashton/drivaerml",
            "revision": DATASET_REVISION,
            "public_case_count": 484,
            "native_source_pin": {"file": "proposal/native-source-pin.json", "sha256": SOURCE_PIN_SHA256},
            "owner_split_manifest": {"file": "proposal/owner-published-splits.json", "sha256": SPLIT_MANIFEST_SHA256},
            "proposal_contract": {"file": "proposal/contract-proposal.json", "sha256": sha256_file(PROPOSAL_ROOT / "contract-proposal.json")},
        },
        "case_file_binding": {
            "case_id_pattern": "^run_([1-9][0-9]*)$",
            "case_id_variable": "<case_id>",
            "run_number_variable": "<run_number>",
            "example": {"case_id": "run_11", "run_number": 11},
        },
        "coverage_contract": {
            "dimensionality": "3D native surface and 3D native finite-volume domain",
            "rule": "every_required_native_CellData_tuple_exactly_once",
            "inference_may_be_chunked": True,
            "chunk_metrics_must_use_additive_sufficient_statistics": True,
            "complete_case_and_entity_coverage_required": True,
            "full_prediction_artifact_required": False,
            "case_aggregation": "calculate_each_complete_case_then_macro_average_cases_equally",
            "vector_error": "componentwise_difference_then_euclidean_norm_not_difference_of_magnitudes",
        },
        "public_supports": [
            {
                "id": "surface_native_cells",
                "public_file": "<case_id>/boundary_<run_number>.vtp",
                "format": "VTK PolyData",
                "association": "CellData",
                "entities": "all_native_polygons_in_raw_VTK_cell_order",
                "stable_id": ["case_id", "zero_based_raw_vtk_cell_id"],
                "arrays": ["pMeanTrim", "wallShearStressMeanTrim"],
                "array_components": {"pMeanTrim": 1, "wallShearStressMeanTrim": 3},
                "array_units": {"pMeanTrim": "m^2/s^2", "wallShearStressMeanTrim": "m^2/s^2"},
                "physical_weight_file": "<case_id>/boundary_cell_area_<run_number>.npy",
                "physical_weight_dtype": "little_endian_float32",
                "physical_weight_association": "one_positive_finite_area_per_native_polygon_in_identical_order",
                "physical_weight_manifest": {"path": "surface_cell_areas/manifest.json", "sha256": SURFACE_AREA_MANIFEST_SHA256},
            },
            {
                "id": "volume_native_cells",
                "logical_public_file": "<case_id>/volume_<run_number>.vtu",
                "transport_parts": "resolve the exact ordered .00.part, .01.part, and optional .02.part list from proposal/native-source-pin.json",
                "transport_assembly": "byte_concatenate_pinned_parts_in_part_index_order_with_no_delimiter_or_transformation",
                "part_count_policy": "474 cases have two parts and 10 pinned cases have three; never assume exactly two",
                "format": "VTK UnstructuredGrid",
                "association": "CellData",
                "entities": "all_native_finite_volume_cells_in_raw_VTK_cell_order",
                "stable_id": ["case_id", "zero_based_raw_vtk_cell_id"],
                "arrays": ["UMeanTrim", "pMeanTrim"],
                "array_components": {"UMeanTrim": 3, "pMeanTrim": 1},
                "array_units": {"UMeanTrim": "m/s", "pMeanTrim": "m^2/s^2"},
                "primary_weighting": "one_per_native_cell",
                "secondary_weighting": "benchmark_computed_cell_volume_pending_frozen_publication",
                "candidate_secondary_weight_status": {
                    "status": "blocked_real_pilot_positive_finite_gate_not_passed",
                    "candidate_algorithm": "VTK_9.5.2_vtkCellSizeFilter_volume_only",
                    "accepted_weight_artifact_exists": False,
                    "owner_scientific_decision_required": True,
                    "diagnostic_evidence": [
                        {
                            "file": "evidence/volume-cell-types-run_1-pilot.json",
                            "sha256": "63f4c794807fd4d327d2e5017db585b41047c758e1ca9eeb4d22f2010817092e",
                            "status": "diagnostic_only_not_a_volume_weight_definition",
                        },
                        {
                            "file": "evidence/volume-cell-types-run_44-pilot.json",
                            "sha256": "4f3a1cc6bf1c4010daf4a94c2bdf56cc9fb4a684e8cb2610dce6f00bcf482f71",
                            "status": "diagnostic_only_not_a_volume_weight_definition",
                        },
                    ],
                },
                "candidate_primary_validation_evidence": {
                    "file": "evidence/native-volume-run1-run44-equal-cell-primary-pilot.json",
                    "sha256": "d009b6ac708fa320d21492b4cc44fc846b61e99b445836b5dedc704a934592d7",
                    "status": "two_case_equal_cell_primary_pilot_only",
                    "physical_volume_secondary_exercised": False,
                    "complete_all_484_cases": False,
                },
            },
            {
                "id": "field_integrated_force_truth",
                "authoritative_public_file": "force_mom_constref_all.csv",
                "sha256": FORCE_TABLE_SHA256,
                "per_case_mirror": "<case_id>/force_mom_constref_<run_number>.csv",
                "per_case_mirror_policy": "accepted_as_a_convenience_only_after_exact_row_replay_against_the_authoritative_aggregate",
                "exact_header": ["run", "cd", "cl", "clf", "clr", "cs"],
                "ranked_targets": {"Cd": "cd", "Cl": "cl", "CmPitch": "casewise_(clf-clr)/2"},
                "report_only_targets": {"Clf": "clf", "Clr": "clr"},
            },
        ],
        "scored_field_bindings": [
            {
                "target_id": "surface_pressure",
                "support_id": "surface_native_cells",
                "array": "pMeanTrim",
                "components": 1,
                "primary_metric": "surface_pressure_rel_l2",
                "primary_weighting": "surface_face_area",
                "secondary_metric": "surface_pressure_equal_entity_rel_l2",
                "secondary_weighting": "surface_entities_equal",
            },
            {
                "target_id": "surface_wall_shear",
                "support_id": "surface_native_cells",
                "array": "wallShearStressMeanTrim",
                "components": 3,
                "primary_metric": "surface_wall_shear_rel_l2",
                "primary_weighting": "surface_face_area",
                "secondary_metric": "surface_wall_shear_equal_entity_rel_l2",
                "secondary_weighting": "surface_entities_equal",
            },
            {
                "target_id": "volume_velocity",
                "support_id": "volume_native_cells",
                "array": "UMeanTrim",
                "components": 3,
                "primary_metric": "volume_velocity_rel_l2",
                "primary_weighting": "volume_cells_equal",
                "secondary_metric": "volume_velocity_physical_rel_l2",
                "secondary_weighting": "cell_volume",
            },
            {
                "target_id": "volume_pressure",
                "support_id": "volume_native_cells",
                "array": "pMeanTrim",
                "components": 1,
                "primary_metric": "volume_pressure_rel_l2",
                "primary_weighting": "volume_cells_equal",
                "secondary_metric": "volume_pressure_physical_rel_l2",
                "secondary_weighting": "cell_volume",
            },
        ],
        "relative_l2_policy": {
            "surface_primary": "surface_face_area",
            "surface_secondary": "equal_native_polygon",
            "volume_primary": "equal_native_cell",
            "volume_secondary": "physical_cell_volume",
            "chunk_rule": "sum_case_numerators_denominators_counts_and_weights_across_chunks_then_apply_one_nonlinear_reduction",
            "forbidden_chunk_rule": "average_chunk_local_metric_values",
        },
        "force_integration": {
            "source_fields": ["surface pMeanTrim", "surface wallShearStressMeanTrim"],
            "freestream_velocity_m_per_s": 38.889,
            "density_kg_per_m3": 1.0,
            "reference_area_m2": 2.17,
            "reference_length_m": 2.78618,
            "centre_of_rotation_m": [1.40009, 0.0, -0.3176],
            "drag_axis": "+x",
            "lift_axis": "+z",
            "pitch_axis": "+y",
            "body_force_equation": "rho_inf*sum_f(pMeanTrim_f*A_f-wallShearStressMeanTrim_f*norm(A_f))",
            "body_moment_equation": "rho_inf*sum_f(cross(C_f-CoR,pMeanTrim_f*A_f-wallShearStressMeanTrim_f*norm(A_f)))",
            "face_area_and_centre_convention": "OpenFOAM_v2212_primitiveMeshTools_makeFaceCentresAndAreas",
            "ranked_reduction": "separate_equal_case_RMSE_for_Cd_Cl_and_CmPitch",
            "dependent_axle_loads": {"Clf": "Cl/2+CmPitch", "Clr": "Cl/2-CmPitch", "composite_weight": 0.0},
            "candidate_validation_evidence": {
                "file": "evidence/force-replay-all484.json",
                "sha256": "631cd02c3a4215b254489652c1d93dfd781ecdb9478ff1ab11f24294743e8a17",
                "status": "all_484_cases_passed_candidate_evaluator",
                "owner_scientific_approval": False,
            },
        },
        "profile_definition": {
            "file": str(profile_path.relative_to(BENCHMARK_ROOT)),
            "sha256": sha256_file(profile_path),
            "status": "candidate_all_case_cp_mapping_complete_with_explicit_failures_velocity_all_case_pending",
            "candidate_cp_validation_evidence": {
                "file": "evidence/cp-mapping-all484-hardened.json",
                "sha256": "634e95279a2fb1078b3547616f29ddfc0a38ffe03f0b487fa0688be95aadbe81",
                "case_count": 484,
                "probe_row_count": 101156,
                "valid_mapping_count": 100281,
                "invalid_mapping_count": 875,
                "omitted_row_count": 0,
                "public_scoring_support_eligible": False,
                "owner_visual_signoff": False,
            },
        },
        "participant_process": [
            "select one official split and use only its train list for fitting and training statistics",
            "load every required boundary VTP CellData tuple and its same-order public area array",
            "reconstruct each logical volume VTU from the exact per-case part list; process native cells in bounded-memory chunks without resampling",
            "retain raw native cell IDs so chunks form one complete duplicate-free case partition",
            "accumulate additive sufficient statistics per chunk and reduce only after the complete case is assembled logically",
            "derive field-integrated forces and AutoCFD5 diagnostics from the submitted fields using the candidate evaluator for implementation evidence; official submissions must use the future frozen owner-approved evaluator",
            "submit scalar metrics, per-case evidence, profile display chunks, and optional prediction artifact locations through the current FluidsBench schema",
        ],
        "activation_gates": {
            "official_splits": "complete",
            "pinned_native_files": "complete",
            "surface_area_weights": "all_484_candidate_order_count_hash_and_value_audit_passed_owner_release_approval_pending",
            "volume_cell_weights": "blocked_real_pilot_positive_finite_gate_not_passed_owner_algorithm_decision_pending",
            "force_evaluator": "all_484_candidate_replay_passed_owner_approval_pending",
            "velocity_profiles": "definition_complete_mapping_and_convergence_pending",
            "cp_probes": "all_484_candidate_mapping_and_cp_equation_replay_complete_with_875_explicit_invalid_rows_owner_resolution_and_visual_signoff_pending",
            "physics_null_baselines": "pending",
            "composite_sensitivity_and_bootstrap": "blocked_pending_frozen_evaluator_and_at_least_three_genuine_model_checkpoint_predictions",
            "schema_v3_nonspatial_result_binding": "candidate_adapter_exists_but_force_velocity_and_cp_values_require_dataset_specific_validation_or_hash_bound_maintainer_receipt_before_activation",
            "independent_participant_dry_run": "pending",
            "owner_evaluator_approval": "pending",
        },
        "owner_decisions_required": [
            "publish_volume_cell_weights_and_frozen_geometry_algorithm",
            "approve_all_case_native_array_inventory_and_exclusion_policy",
            "approve_all_484_case_force_replay_and_chunk_invariance",
            "approve_velocity_assignment_and_resolution_convergence",
            "resolve_and_approve_all_875_explicit_cp_mapping_failures_and_visual_atlas",
            "provide_at_least_three_genuine_trained_model_checkpoint_predictions_for_sensitivity_and_method_ordering",
            "publish_physics_null_denominators_sensitivity_controls_and_bootstrap_indexes",
            "approve_dataset_specific_schema_v3_nonspatial_result_validation_or_hash_bound_maintainer_receipt",
            "approve_immutable_evaluator_and_scoring_support_release_before_opening_submissions",
        ],
    }


def build_specification(
    split_entries: list[dict[str, Any]], profile_path: Path, profile: dict[str, Any]
) -> dict[str, Any]:
    composite = build_composite()
    return {
        "schema_version": "1.1",
        "dataset_id": "drivaerml",
        "dataset_name": "DrivAerML",
        "dataset_version": DATASET_VERSION,
        "status": "candidate_scoring_contract",
        "contract_base_path": "benchmark-specs/drivaerml/",
        "contract_base_path_scope": "repository_relative_contract_artifact_fields_only; upstream_dataset_paths_resolve_within_source_release",
        "scoring_support": build_scoring_support(profile_path),
        "evaluation_reference_version": EVALUATOR_VERSION,
        "default_field_reduction": "per_geometry_then_macro_average",
        "ranking": {
            "metric_id": "overall_score",
            "direction": "higher",
            "decimal_places": 1,
            "rounding": "decimal_half_up",
            "method": "competition",
        },
        "overall_score_composite": composite,
        "component_score_groups": {
            "operation": "normalized_weighted_component_scores",
            "groups": [
                {
                    "metric_id": "field_score",
                    "component_metric_ids": [
                        "surface_pressure_rel_l2",
                        "surface_wall_shear_rel_l2",
                        "volume_velocity_rel_l2",
                        "volume_pressure_rel_l2",
                    ],
                },
                {
                    "metric_id": "force_score",
                    "component_metric_ids": [
                        "field_integrated_cd_rmse",
                        "field_integrated_cl_rmse",
                        "field_integrated_cmpitch_rmse",
                    ],
                },
                {
                    "metric_id": "diagnostic_score",
                    "component_metric_ids": ["velocity_profile_uinf_rmse", "cp_probe_rmse"],
                },
            ],
            "tolerance": 1e-6,
        },
        "metrics": build_metrics(),
        "profile_definition": {
            "id": profile["id"],
            "file": str(profile_path.relative_to(BENCHMARK_ROOT)),
            "sha256": sha256_file(profile_path),
            "status": "candidate_all_case_cp_mapping_complete_with_explicit_failures_velocity_all_case_pending",
        },
        "profile_panels": build_profile_panels(profile),
        "splits": split_entries,
    }


def presentation_definition(metric_spec: dict[str, Any]) -> dict[str, Any]:
    metric_id = metric_spec["id"]
    labels = {
        "field_integrated_cd_rmse": "Field-integrated C_D RMSE",
        "field_integrated_cl_rmse": "Field-integrated C_L RMSE",
        "field_integrated_cmpitch_rmse": "Field-integrated C_M,pitch RMSE",
        "field_integrated_clf_rmse": "Field-integrated C_Lf RMSE",
        "field_integrated_clr_rmse": "Field-integrated C_Lr RMSE",
        "field_integrated_lift_closure_max_abs": "Lift closure max. error",
        "velocity_profile_uinf_rmse": "AutoCFD5 velocity-profile RMSE",
        "velocity_profile_experimental_subset_uinf_rmse": "Experimental-line velocity RMSE",
        "cp_probe_rmse": "AutoCFD5 Cp-probe RMSE",
        "cp_panel_macro_rmse": "AutoCFD5 Cp-panel macro RMSE",
    }
    if metric_id.startswith("drivaerml_"):
        readable = metric_id.removeprefix("drivaerml_").replace("_", " ")
        label = f"DrivAerML {readable}"
        column_group = "absolute"
        group = "absolute-rmse" if metric_id.endswith("rmse") else "absolute-mae"
        group_label = "Absolute RMSE" if metric_id.endswith("rmse") else "Absolute MAE"
        digits = 3
    else:
        label = labels[metric_id]
        column_group = "diagnostics" if "profile" in metric_id or metric_id.startswith("cp_") else "integral"
        group = "profile-errors" if column_group == "diagnostics" else "force-errors"
        group_label = "Profile errors" if column_group == "diagnostics" else "Integral force / moment errors"
        digits = 5 if metric_spec["unit"] == "" else 3
    return {
        "id": metric_id,
        "label": label,
        "description": f"DrivAerML candidate contract metric using {metric_spec['weighting']}. Lower is better.",
        "group": group,
        "group_label": group_label,
        "column_group": column_group,
        "unit": metric_spec["unit"],
        "digits": digits,
        "direction": metric_spec["direction"],
        "kind": metric_spec["kind"],
        "equation": metric_spec["equation"],
        "comparison_group": group,
        "comparison_group_label": group_label,
        "column_group_label": "Diagnostics" if column_group == "diagnostics" else ("Absolute" if column_group == "absolute" else "Integral forces / moments"),
    }


def diagnostic_panels(profile: dict[str, Any]) -> list[dict[str, Any]]:
    source_url = "https://autocfd5.s3.eu-west-1.amazonaws.com/"
    pressure_stations = [
        {
            "id": station["id"],
            "label": station["label"],
            "x_label": "AutoCFD5 panel point index",
            "description": f"Pinned AutoCFD5 v8 panel sequence with {station['sample_count']} membership rows.",
            "basis": "pinned_autocfd5_v8_probe_registry",
            "source_url": source_url,
        }
        for station in profile["pressure_profiles"]["stations"]
    ]
    velocity_stations = [
        {
            "id": station["id"],
            "label": station["label"],
            "x_label": "Distance along line, m",
            "description": f"Pinned 10 mm AutoCFD5 line with {station['sample_count']} samples.",
            "basis": "pinned_autocfd5_v8_velocity_line",
            "source_url": source_url,
        }
        for station in profile["velocity_profiles"]["stations"]
    ]
    return [
        {
            "id": "pressure_profiles",
            "title": "AutoCFD5 pressure-coefficient profiles",
            "description": "Display panels use 217 ordered memberships; the ranked metric deduplicates them to 209 probes per case.",
            "data_key": "cp_profiles",
            "profile_definition_id": profile["id"],
            "coordinate_unit": "",
            "x_keys": ["panel_point_index", "x"],
            "quantities": [{"id": "cp", "label": "Cp", "y_label": "Pressure coefficient, Cp", "y_keys": ["cp"], "unit": ""}],
            "stations": pressure_stations,
            "required": True,
            "allow_unlisted_stations": False,
            "required_series_fields": ["case_id", "station_id"],
            "reverse_y": True,
        },
        {
            "id": "velocity_profiles",
            "title": "AutoCFD5 velocity profiles",
            "description": "Sixteen fixed lines scored on the pinned 10 mm grid using arc-length trapezoidal RMSE of |U|/Uinf.",
            "data_key": "velocity_profiles",
            "profile_definition_id": profile["id"],
            "coordinate_unit": "m",
            "x_keys": ["distance_m", "distance", "x"],
            "quantities": [{"id": "velocity_ratio", "label": "|U|/Uinf", "y_label": "Velocity magnitude / freestream", "y_keys": ["velocity_ratio", "u_over_u_inf"], "unit": ""}],
            "stations": velocity_stations,
            "required": True,
            "allow_unlisted_stations": False,
            "required_series_fields": ["case_id", "station_id"],
        },
    ]


def update_manifest(specification: dict[str, Any], profile: dict[str, Any]) -> None:
    manifest = load_json(MANIFEST_PATH)
    catalog = manifest["metric_catalog"]
    upsert_catalog_entries(
        catalog["dimensional_fields"], DRIVAER_DIMENSIONAL_CATALOG
    )
    upsert_catalog_entries(
        catalog["coefficient_errors"], DRIVAER_COEFFICIENT_CATALOG
    )
    definitions = manifest["metric_definitions"]
    positions = {definition["id"]: index for index, definition in enumerate(definitions)}
    existing_ids = set(positions)
    for metric_spec in specification["metrics"]:
        metric_id = metric_spec["id"]
        if metric_id in existing_ids:
            continue
        definition = presentation_definition(metric_spec)
        definitions.append(definition)
        existing_ids.add(metric_id)

    dataset = next(item for item in manifest["datasets"] if item["slug"] == "drivaerml")
    dataset["contract_base_path"] = specification["contract_base_path"]
    dataset["contract_base_path_scope"] = specification["contract_base_path_scope"]
    fixture_documents = [
        load_json(path)
        for path in sorted(SUBMISSIONS_ROOT.glob("*/submission.json"))
    ]
    if not fixture_documents or any(
        not isinstance(document.get("submitted_at"), str)
        for document in fixture_documents
    ):
        raise ValueError("DrivAerML prototype fixtures require submitted_at dates")
    fixture_count = len(fixture_documents)
    dataset["submission_count"] = fixture_count
    dataset["updated_at"] = max(
        document["submitted_at"] for document in fixture_documents
    )
    dataset["submission_population"] = {
        "feed_row_count": fixture_count,
        "prototype_ineligible_fixture_count": fixture_count,
        "eligible_submission_count": 0,
        "scientific_result_count": 0,
        "submission_count_semantics": (
            "all_current_feed_rows_are_structural_prototype_fixtures_not_eligible_submissions"
        ),
        "updated_at_semantics": (
            "latest_submitted_at_date_among_prototype_fixture_rows_not_a_contract_or_scientific_evidence_update"
        ),
    }
    dataset["submission_format"] = "drivaerml_native_candidate_v1"
    dataset["metrics"] = {
        "dimensional_fields": [
            entry["id"] for entry in DRIVAER_DIMENSIONAL_CATALOG
        ],
        "coefficient_errors": [
            entry["id"] for entry in DRIVAER_COEFFICIENT_CATALOG
        ],
    }
    dataset["metric_ids"] = [item["id"] for item in specification["metrics"]]
    dataset["scoring_support"] = specification["scoring_support"]
    dataset["overall_score_composite"] = specification[
        "overall_score_composite"
    ]
    dataset["profile_definition"] = specification["profile_definition"]
    dataset["metric_definition_overrides"] = {
        "surface_pressure_rel_l2": {
            "label": "Surface p rel. L2 (area-weighted)",
            "description": "Per-case area-weighted relative L2 of native CellData pMeanTrim, then equal-case mean. Kinematic pressure is in m^2/s^2.",
        },
        "surface_wall_shear_rel_l2": {
            "label": "Surface WSS rel. L2 (area-weighted)",
            "description": "Per-case area-weighted relative L2 of the native three-component wallShearStressMeanTrim vector, then equal-case mean.",
        },
        "volume_velocity_rel_l2": {
            "label": "Volume velocity rel. L2 (equal-cell)",
            "description": "Per-case equal-native-cell relative L2 of the three-component UMeanTrim vector, then equal-case mean.",
        },
        "volume_pressure_rel_l2": {
            "label": "Volume p rel. L2 (equal-cell)",
            "description": "Per-case equal-native-cell relative L2 of CellData pMeanTrim, then equal-case mean.",
        },
    }
    dataset["diagnostic_panels"] = diagnostic_panels(profile)
    write_json(MANIFEST_PATH, manifest)


def first_and_last(series: dict[str, Any] | None, fallback: tuple[float, float]) -> tuple[float, float]:
    if isinstance(series, dict):
        predictions = series.get("prediction")
        if isinstance(predictions, list) and len(predictions) >= 2:
            return float(predictions[0]), float(predictions[-1])
    return fallback


def migrated_series(case: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    existing = [series for series in case.get("series", []) if isinstance(series, dict)]
    pressure_sources = [series for series in existing if series.get("panel_id") == "pressure_profiles"]
    velocity_sources = [series for series in existing if series.get("panel_id") == "velocity_profiles"]
    result = []
    for index, station in enumerate(profile["pressure_profiles"]["stations"]):
        exact = next((series for series in pressure_sources if series.get("station_id") == station["id"]), None)
        source = exact or (pressure_sources[index % len(pressure_sources)] if pressure_sources else None)
        left, right = first_and_last(source, (0.0, 0.0))
        offset = 0.0 if exact is not None else 0.0002 * index
        result.append(
            {
                "panel_id": "pressure_profiles",
                "station_id": station["id"],
                "quantity_id": "cp",
                "coordinate": [1.0, float(station["sample_count"])],
                "prediction": [round(left + offset, 7), round(right + offset, 7)],
            }
        )
    for index, station in enumerate(profile["velocity_profiles"]["stations"]):
        exact = next((series for series in velocity_sources if series.get("station_id") == station["id"]), None)
        source = exact or (velocity_sources[index % len(velocity_sources)] if velocity_sources else None)
        left, right = first_and_last(source, (1.0, 1.0))
        offset = 0.0 if exact is not None else 0.0002 * index
        result.append(
            {
                "panel_id": "velocity_profiles",
                "station_id": station["id"],
                "quantity_id": "velocity_ratio",
                "coordinate": station["coordinate_interval_m"],
                "prediction": [round(left + offset, 7), round(right + offset, 7)],
            }
        )
    return result


def value(values: dict[str, Any], metric_id: str, fallback_id: str | None, default: float) -> float:
    candidate = values.get(metric_id)
    if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
        candidate = values.get(fallback_id) if fallback_id else None
    if not isinstance(candidate, (int, float)) or isinstance(candidate, bool) or not math.isfinite(candidate):
        candidate = default
    return max(0.0, float(candidate))


def migrated_metric_values(old: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {metric_id: 0.0 for metric_id in SCORE_EQUATIONS}
    primaries = {
        "surface_pressure_rel_l2": 5.0,
        "surface_wall_shear_rel_l2": 8.0,
        "volume_velocity_rel_l2": 6.0,
        "volume_pressure_rel_l2": 7.0,
    }
    for metric_id, default in primaries.items():
        result[metric_id] = value(old, metric_id, None, default)
    result["surface_pressure_equal_entity_rel_l2"] = value(old, "surface_pressure_equal_entity_rel_l2", "surface_pressure_rel_l2", 5.0)
    result["surface_wall_shear_equal_entity_rel_l2"] = value(old, "surface_wall_shear_equal_entity_rel_l2", "surface_wall_shear_rel_l2", 8.0)
    result["volume_velocity_physical_rel_l2"] = value(old, "volume_velocity_physical_rel_l2", "volume_velocity_rel_l2", 6.0)
    result["volume_pressure_physical_rel_l2"] = value(old, "volume_pressure_physical_rel_l2", "volume_pressure_rel_l2", 7.0)

    old_absolute = {
        "surface_pressure": ("surface_pressure_mae", "surface_pressure_rmse", 25.0, 35.0),
        "surface_wall_shear": ("surface_wall_shear_mae", "surface_wall_shear_rmse", 0.8, 1.2),
        "volume_velocity": ("volume_velocity_mae", "volume_velocity_rmse", 2.0, 3.0),
        "volume_pressure": ("volume_pressure_mae", "volume_pressure_rmse", 35.0, 50.0),
    }
    tokens = {
        "surface_pressure": ("area", "equal_entity"),
        "surface_wall_shear": ("area", "equal_entity"),
        "volume_velocity": ("equal_entity", "physical"),
        "volume_pressure": ("equal_entity", "physical"),
    }
    for field_id, (old_mae, old_rmse, default_mae, default_rmse) in old_absolute.items():
        for token in tokens[field_id]:
            prefix = f"drivaerml_{field_id}_{token}"
            result[f"{prefix}_mae"] = value(old, f"{prefix}_mae", old_mae, default_mae)
            result[f"{prefix}_rmse"] = value(old, f"{prefix}_rmse", old_rmse, default_rmse)

    cd = value(old, "field_integrated_cd_rmse", "c_drag_mae", 0.005)
    cl = value(old, "field_integrated_cl_rmse", "c_lift_mae", 0.01)
    result.update(
        {
            "field_integrated_cd_rmse": cd,
            "field_integrated_cl_rmse": cl,
            "field_integrated_cmpitch_rmse": value(old, "field_integrated_cmpitch_rmse", None, max(0.001, 0.75 * cl)),
            "field_integrated_clf_rmse": value(old, "field_integrated_clf_rmse", None, max(0.001, 0.8 * cl)),
            "field_integrated_clr_rmse": value(old, "field_integrated_clr_rmse", None, max(0.001, 0.8 * cl)),
            "field_integrated_lift_closure_max_abs": value(old, "field_integrated_lift_closure_max_abs", None, 1e-7),
        }
    )
    old_velocity_r2 = value(old, "velocity_profile_r2", None, 0.95)
    old_cp_r2 = value(old, "cp_cut_r2", None, 0.95)
    velocity_rmse = value(old, "velocity_profile_uinf_rmse", None, math.sqrt(max(0.0, 1.0 - old_velocity_r2)))
    cp_rmse = value(old, "cp_probe_rmse", None, math.sqrt(max(0.0, 1.0 - old_cp_r2)))
    result.update(
        {
            "velocity_profile_uinf_rmse": velocity_rmse,
            "velocity_profile_experimental_subset_uinf_rmse": value(old, "velocity_profile_experimental_subset_uinf_rmse", None, velocity_rmse),
            "cp_probe_rmse": cp_rmse,
            "cp_panel_macro_rmse": value(old, "cp_panel_macro_rmse", None, cp_rmse),
        }
    )
    return result


def migrate_submission(directory: Path, specification: dict[str, Any], profile: dict[str, Any]) -> None:
    submission_path = directory / "submission.json"
    submission = load_json(submission_path)
    split = next(item for item in specification["splits"] if item["id"] == submission["split_id"])
    split_index = load_json(BENCHMARK_ROOT / split["index_file"])
    case_ids = split_index["case_ids"]

    index_path = directory / submission["profile_data"]["index_file"]
    index = load_json(index_path)
    cursor = 0
    for chunk_entry in index["chunks"]:
        chunk_path = index_path.parent / chunk_entry["file"]
        chunk = load_json(chunk_path)
        count = len(chunk["cases"])
        replacement_ids = case_ids[cursor : cursor + count]
        if len(replacement_ids) != count:
            raise ValueError(f"profile chunk partition exceeds official {submission['split_id']} test set")
        for case, case_id in zip(chunk["cases"], replacement_ids):
            case["case_id"] = case_id
            case["series"] = migrated_series(case, profile)
        chunk_entry["case_ids"] = replacement_ids
        write_json(chunk_path, chunk)
        chunk_entry["sha256"] = sha256_file(chunk_path)
        cursor += count
    if cursor != len(case_ids):
        raise ValueError(f"profile chunks cover {cursor} cases but split requires {len(case_ids)}")
    index.update(
        {
            "dataset_id": "drivaerml",
            "split_id": submission["split_id"],
            "case_set_id": split["case_set_id"],
            "case_count": len(case_ids),
            "case_id_status": "official",
        }
    )
    write_json(index_path, index)

    metric_values = migrated_metric_values(submission.get("metric_values", {}))
    ordered_ids = [item["id"] for item in specification["metrics"]]
    metric_values = {metric_id: metric_values[metric_id] for metric_id in ordered_ids}
    submission.update(
        {
            "dataset_version": DATASET_VERSION,
            "split": split["label"],
            "case_set_id": split["case_set_id"],
            "split_sha256": split["sha256"],
            "metric_values": metric_values,
        }
    )
    submission["evaluation"]["reference_version"] = EVALUATOR_VERSION
    submission["profile_data"].update({"case_count": len(case_ids), "case_set_id": split["case_set_id"]})
    submission["approval"] = {
        "status": "prototype",
        "note": "Structural fixture for the closed DrivAerML candidate; no metric or score is an approved result.",
    }
    submission["note"] = (
        "Illustrative structural fixture migrated to the official split IDs and candidate DrivAerML metric/profile vocabulary. "
        "It is not a recomputation from native fields. The four score values are zero placeholders because the nine "
        "physics-null denominators are not yet published, so this row is ineligible for ranking or citation."
    )

    evidence_path = directory / submission["evaluation"]["evidence_file"]
    evidence = load_json(evidence_path)
    evidence.update(
        {
            "split_id": submission["split_id"],
            "reference_version": EVALUATOR_VERSION,
            "metric_values": metric_values,
            "profile_index_sha256": sha256_file(index_path),
            "notes": "Structural dummy evidence for the closed DrivAerML candidate; not computed from public fields and not scientifically rankable.",
        }
    )
    write_json(evidence_path, evidence)
    submission["evaluation"]["evidence_sha256"] = sha256_file(evidence_path)
    write_json(submission_path, submission)


def main() -> int:
    for path, expected in (
        (PROPOSAL_ROOT / "native-source-pin.json", SOURCE_PIN_SHA256),
        (PROPOSAL_ROOT / "owner-published-splits.json", SPLIT_MANIFEST_SHA256),
    ):
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"proposal source digest changed for {path}: {actual}")

    profile = build_profile_definition()
    profile_path = BENCHMARK_ROOT / "autocfd5-profiles-v8.json"
    write_json(profile_path, profile)
    split_entries = write_splits()
    specification = build_specification(split_entries, profile_path, profile)
    write_json(BENCHMARK_ROOT / "submission-spec.json", specification)
    update_manifest(specification, profile)
    directories = sorted(path.parent for path in SUBMISSIONS_ROOT.glob("*/submission.json"))
    for directory in directories:
        migrate_submission(directory, specification, profile)
        print(f"migrated {directory.relative_to(ROOT)}")
    print(
        f"updated closed DrivAerML candidate with {len(split_entries)} official splits, "
        f"{len(specification['metrics'])} metrics, and {len(directories)} prototype fixtures"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
