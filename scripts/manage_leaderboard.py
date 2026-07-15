#!/usr/bin/env python3
"""Validate source submissions and build the public leaderboard feeds."""

from __future__ import annotations

import argparse
import json
import math
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "leaderboard" / "manifest.json"
BASE_METRICS = (
    "surface_pressure_l2",
    "surface_pressure_l1",
    "surface_tau_l2",
    "surface_tau_l1",
    "volume_velocity_l2",
    "volume_velocity_l1",
    "volume_pressure_l2",
    "volume_pressure_l1",
    "r2_cd",
    "r2_cl",
    "velocity_profile_r2",
    "cp_cut_r2",
)

LEGACY_WEIGHTS = {
    "surface_pressure_rel_l2": 0.15,
    "surface_wall_shear_rel_l2": 0.10,
    "volume_velocity_rel_l2": 0.15,
    "volume_pressure_rel_l2": 0.10,
    "cd_r2": 0.15,
    "cl_r2": 0.10,
    "velocity_profile_r2": 0.15,
    "cp_cut_r2": 0.10,
}

LEGACY_ERROR_CAPS = {
    "surface_pressure_rel_l2": 15.0,
    "surface_wall_shear_rel_l2": 20.0,
    "volume_velocity_rel_l2": 12.0,
    "volume_pressure_rel_l2": 15.0,
}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def dataset_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries = manifest.get("datasets")
    if not isinstance(entries, list):
        raise ValueError("leaderboard/manifest.json must contain a datasets array")
    return entries


def dataset_by_name(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["name"]: entry for entry in dataset_entries(manifest)}


def catalog_by_id(manifest: dict[str, Any], group: str) -> dict[str, dict[str, Any]]:
    catalog = manifest.get("metric_catalog", {}).get(group, [])
    return {definition["id"]: definition for definition in catalog}


def enabled_metric_definitions(
    manifest: dict[str, Any], dataset: dict[str, Any], group: str
) -> list[dict[str, Any]]:
    catalog = catalog_by_id(manifest, group)
    enabled_ids = dataset.get("metrics", {}).get(group, [])
    missing = [metric_id for metric_id in enabled_ids if metric_id not in catalog]
    if missing:
        raise ValueError(
            f"{dataset.get('name', 'Unknown dataset')} references unknown {group}: {', '.join(missing)}"
        )
    return [catalog[metric_id] for metric_id in enabled_ids]


def metric_definitions_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    definitions = manifest.get("metric_definitions", [])
    return {
        definition["id"]: definition
        for definition in definitions
        if isinstance(definition, dict) and definition.get("id")
    }


def dataset_metric_definitions(
    manifest: dict[str, Any], dataset: dict[str, Any]
) -> list[dict[str, Any]]:
    definitions = metric_definitions_by_id(manifest)
    return [definitions[metric_id] for metric_id in dataset.get("metric_ids", []) if metric_id in definitions]


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    names: set[str] = set()
    slugs: set[str] = set()

    for group in ("dimensional_fields", "coefficient_errors"):
        definitions = manifest.get("metric_catalog", {}).get(group)
        if not isinstance(definitions, list) or not definitions:
            errors.append(f"metric_catalog.{group} must be a non-empty array")
            continue
        ids = [definition.get("id") for definition in definitions]
        if any(not metric_id for metric_id in ids) or len(ids) != len(set(ids)):
            errors.append(f"metric_catalog.{group} IDs must be present and unique")

    metric_definitions = manifest.get("metric_definitions")
    if not isinstance(metric_definitions, list) or not metric_definitions:
        errors.append("metric_definitions must be a non-empty array")
        metric_definitions = []
    metric_ids = [definition.get("id") for definition in metric_definitions if isinstance(definition, dict)]
    if any(not metric_id for metric_id in metric_ids) or len(metric_ids) != len(set(metric_ids)):
        errors.append("metric_definitions IDs must be present and unique")
    for definition in metric_definitions:
        if not isinstance(definition, dict):
            errors.append("each metric definition must be an object")
            continue
        for key in (
            "id",
            "label",
            "description",
            "group",
            "group_label",
            "column_group",
            "column_group_label",
            "direction",
        ):
            if not isinstance(definition.get(key), str) or not definition[key].strip():
                errors.append(f"metric definition {definition.get('id')!r} requires {key}")
        if definition.get("column_group") not in {"absolute", "relative", "integral", "scores"}:
            errors.append(f"metric definition {definition.get('id')!r} has invalid column_group")
        if definition.get("direction") not in {"higher", "lower"}:
            errors.append(f"metric definition {definition.get('id')!r} has invalid direction")
        if not isinstance(definition.get("digits"), int) or definition["digits"] < 0:
            errors.append(f"metric definition {definition.get('id')!r} requires non-negative integer digits")

    known_metric_ids = set(metric_ids)

    for entry in dataset_entries(manifest):
        name = entry.get("name")
        slug = entry.get("slug")
        if not name or name in names:
            errors.append(f"dataset name is missing or duplicated: {name!r}")
        if not slug or slug in slugs:
            errors.append(f"dataset slug is missing or duplicated: {slug!r}")
        names.add(name)
        slugs.add(slug)
        for group in ("dimensional_fields", "coefficient_errors"):
            try:
                enabled_metric_definitions(manifest, entry, group)
            except ValueError as error:
                errors.append(str(error))

        enabled_metric_ids = entry.get("metric_ids")
        if not isinstance(enabled_metric_ids, list) or not enabled_metric_ids:
            errors.append(f"{name} metric_ids must be a non-empty array")
        else:
            unknown_metric_ids = set(enabled_metric_ids) - known_metric_ids
            if unknown_metric_ids:
                errors.append(f"{name} references unknown metrics: {', '.join(sorted(unknown_metric_ids))}")
            if len(enabled_metric_ids) != len(set(enabled_metric_ids)):
                errors.append(f"{name} metric_ids must be unique")

        ranking = entry.get("ranking")
        if not isinstance(ranking, dict):
            errors.append(f"{name} ranking must be an object")
        else:
            if ranking.get("metric_id") not in set(enabled_metric_ids or []):
                errors.append(f"{name} ranking.metric_id must be enabled for the dataset")
            if ranking.get("direction") not in {"higher", "lower"}:
                errors.append(f"{name} ranking.direction must be higher or lower")

        aggregate = entry.get("metric_aggregate")
        if aggregate is not None:
            if not isinstance(aggregate, dict):
                errors.append(f"{name} metric_aggregate must be an object")
            else:
                source_ids = aggregate.get("source_metric_ids")
                if aggregate.get("metric_id") not in set(enabled_metric_ids or []):
                    errors.append(f"{name} metric_aggregate.metric_id must be enabled")
                if aggregate.get("operation") != "mean":
                    errors.append(f"{name} metric_aggregate.operation must be mean")
                if not isinstance(source_ids, list) or not source_ids:
                    errors.append(f"{name} metric_aggregate.source_metric_ids must be a non-empty array")
                elif set(source_ids) - set(enabled_metric_ids or []):
                    errors.append(f"{name} metric_aggregate contains metrics not enabled for the dataset")

        panels = entry.get("diagnostic_panels")
        if not isinstance(panels, list) or not panels:
            errors.append(f"{name} diagnostic_panels must be a non-empty array")
            continue
        panel_ids = [panel.get("id") for panel in panels if isinstance(panel, dict)]
        if any(not panel_id for panel_id in panel_ids) or len(panel_ids) != len(set(panel_ids)):
            errors.append(f"{name} diagnostic panel IDs must be present and unique")
        for panel in panels:
            if not isinstance(panel, dict):
                errors.append(f"{name} diagnostic panels must be objects")
                continue
            for panel_key in ("id", "title", "description", "data_key"):
                if not isinstance(panel.get(panel_key), str) or not panel[panel_key].strip():
                    errors.append(f"{name} diagnostic panel {panel.get('id')!r} requires {panel_key}")
            if not isinstance(panel.get("x_keys"), list) or not panel["x_keys"]:
                errors.append(f"{name} diagnostic panel {panel.get('id')!r} requires x_keys")
            quantities = panel.get("quantities")
            if not isinstance(quantities, list) or not quantities:
                errors.append(f"{name} diagnostic panel {panel.get('id')!r} requires quantities")
                quantities = []
            quantity_ids = [quantity.get("id") for quantity in quantities if isinstance(quantity, dict)]
            if any(not quantity_id for quantity_id in quantity_ids) or len(quantity_ids) != len(set(quantity_ids)):
                errors.append(f"{name} diagnostic panel {panel.get('id')!r} quantity IDs must be unique")
            for quantity in quantities:
                for quantity_key in ("id", "label", "y_label"):
                    if not isinstance(quantity.get(quantity_key), str) or not quantity[quantity_key].strip():
                        errors.append(
                            f"{name} diagnostic panel {panel.get('id')!r} quantity requires {quantity_key}"
                        )
                if not isinstance(quantity.get("y_keys"), list) or not quantity["y_keys"]:
                    errors.append(
                        f"{name} diagnostic panel {panel.get('id')!r} quantity {quantity.get('id')!r} requires y_keys"
                    )
            stations = panel.get("stations")
            if not isinstance(stations, list) or not stations:
                errors.append(f"{name} diagnostic panel {panel.get('id')!r} requires stations")
                stations = []
            station_ids = [station.get("id") for station in stations if isinstance(station, dict)]
            if any(not station_id for station_id in station_ids) or len(station_ids) != len(set(station_ids)):
                errors.append(f"{name} diagnostic panel {panel.get('id')!r} station IDs must be unique")
            for station in stations:
                for station_key in ("id", "label", "x_label", "description", "basis", "source_url"):
                    if not isinstance(station.get(station_key), str) or not station[station_key].strip():
                        errors.append(
                            f"{name} diagnostic panel {panel.get('id')!r} station requires {station_key}"
                        )
                if station.get("basis") not in {
                    "published_validation_trace",
                    "fluidsbench_benchmark_trace",
                }:
                    errors.append(
                        f"{name} diagnostic panel {panel.get('id')!r} station {station.get('id')!r} has unsupported basis"
                    )

    return errors


def first_numeric_value(value: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        candidate = value.get(key)
        if is_number(candidate):
            return candidate
    return None


def profile_quantity_id(profile: dict[str, Any], panel: dict[str, Any]) -> str | None:
    quantity_ids = [quantity["id"] for quantity in panel.get("quantities", [])]
    candidate = profile.get("quantity_id") or profile.get("quantity")
    if candidate in quantity_ids:
        return candidate
    return quantity_ids[0] if len(quantity_ids) == 1 else None


def validate_diagnostic_panels(
    add: Any,
    diagnostics: dict[str, Any],
    dataset: dict[str, Any],
) -> None:
    for panel in dataset.get("diagnostic_panels", []):
        data_key = panel["data_key"]
        profiles = diagnostics.get(data_key)
        if not isinstance(profiles, list):
            add(f"diagnostics.{data_key} must be an array")
            continue

        station_ids = {station["id"] for station in panel.get("stations", [])}
        quantity_ids = {quantity["id"] for quantity in panel.get("quantities", [])}
        quantity_by_id = {quantity["id"]: quantity for quantity in panel.get("quantities", [])}
        provided_pairs: list[tuple[str, str]] = []

        for index, profile in enumerate(profiles):
            if not isinstance(profile, dict):
                add(f"diagnostics.{data_key}[{index}] must be an object")
                continue
            for key in panel.get("required_series_fields", ["case_id", "station_id"]):
                if not isinstance(profile.get(key), str) or not profile[key].strip():
                    add(f"diagnostics.{data_key}[{index}].{key} must be a non-empty string")

            station_id = profile.get("station_id")
            quantity_id = profile_quantity_id(profile, panel)
            if station_id not in station_ids and not panel.get("allow_unlisted_stations", False):
                add(f"diagnostics.{data_key}[{index}] has unknown station {station_id!r}")
            if quantity_id not in quantity_ids:
                add(f"diagnostics.{data_key}[{index}] has unknown or missing quantity")
                continue
            if isinstance(station_id, str):
                provided_pairs.append((station_id, quantity_id))

            values = profile.get("values")
            if not isinstance(values, list) or not values:
                add(f"diagnostics.{data_key}[{index}].values must be a non-empty array")
                continue
            quantity = quantity_by_id[quantity_id]
            for point_index, point in enumerate(values):
                if (
                    not isinstance(point, dict)
                    or first_numeric_value(point, panel["x_keys"]) is None
                    or first_numeric_value(point, quantity["y_keys"]) is None
                ):
                    add(
                        f"diagnostics.{data_key}[{index}].values[{point_index}] must contain "
                        "a finite numeric diagnostic coordinate and value"
                    )

        duplicate_pairs = {pair for pair in provided_pairs if provided_pairs.count(pair) > 1}
        if duplicate_pairs:
            add(f"diagnostics.{data_key} has duplicate station and quantity series")
        if panel.get("required", True):
            expected_pairs = {(station_id, quantity_id) for station_id in station_ids for quantity_id in quantity_ids}
            missing_pairs = expected_pairs - set(provided_pairs)
            if missing_pairs:
                labels = ", ".join(f"{station}/{quantity}" for station, quantity in sorted(missing_pairs))
                add(f"diagnostics.{data_key} is missing station/quantity series: {labels}")


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def legacy_error_score(value: float, cap: float) -> float:
    return clamp(100.0 * (1.0 - value / cap), 0.0, 100.0)


def legacy_metric_values(submission: dict[str, Any]) -> dict[str, float]:
    if any(not is_number(submission.get(metric_id)) for metric_id in BASE_METRICS):
        return {}
    values = {
        "surface_pressure_rel_l2": float(submission["surface_pressure_l2"]),
        "surface_pressure_rel_l1": float(submission["surface_pressure_l1"]),
        "surface_wall_shear_rel_l2": float(submission["surface_tau_l2"]),
        "surface_wall_shear_rel_l1": float(submission["surface_tau_l1"]),
        "volume_velocity_rel_l2": float(submission["volume_velocity_l2"]),
        "volume_velocity_rel_l1": float(submission["volume_velocity_l1"]),
        "volume_pressure_rel_l2": float(submission["volume_pressure_l2"]),
        "volume_pressure_rel_l1": float(submission["volume_pressure_l1"]),
        "cd_r2": float(submission["r2_cd"]),
        "cl_r2": float(submission["r2_cl"]),
        "velocity_profile_r2": float(submission["velocity_profile_r2"]),
        "cp_cut_r2": float(submission["cp_cut_r2"]),
    }

    fields = submission.get("dimensional_field_errors")
    if not isinstance(fields, dict):
        fields = {}
    for field_id, statistics in fields.items():
        if not isinstance(statistics, dict):
            continue
        for statistic, value in statistics.items():
            if is_number(value):
                values[f"{field_id}_{statistic}"] = float(value)

    coefficients = submission.get("absolute_coefficient_errors")
    if not isinstance(coefficients, dict):
        coefficients = {}
    for coefficient_id, value in coefficients.items():
        if is_number(value):
            values[f"{coefficient_id}_mae"] = float(value)

    field_score = (
        LEGACY_WEIGHTS["surface_pressure_rel_l2"]
        * legacy_error_score(values["surface_pressure_rel_l2"], LEGACY_ERROR_CAPS["surface_pressure_rel_l2"])
        + LEGACY_WEIGHTS["surface_wall_shear_rel_l2"]
        * legacy_error_score(
            values["surface_wall_shear_rel_l2"], LEGACY_ERROR_CAPS["surface_wall_shear_rel_l2"]
        )
        + LEGACY_WEIGHTS["volume_velocity_rel_l2"]
        * legacy_error_score(values["volume_velocity_rel_l2"], LEGACY_ERROR_CAPS["volume_velocity_rel_l2"])
        + LEGACY_WEIGHTS["volume_pressure_rel_l2"]
        * legacy_error_score(values["volume_pressure_rel_l2"], LEGACY_ERROR_CAPS["volume_pressure_rel_l2"])
    ) / 0.5
    force_score = (
        LEGACY_WEIGHTS["cd_r2"] * clamp(values["cd_r2"], 0.0, 1.0) * 100.0
        + LEGACY_WEIGHTS["cl_r2"] * clamp(values["cl_r2"], 0.0, 1.0) * 100.0
    ) / 0.25
    diagnostic_score = (
        LEGACY_WEIGHTS["velocity_profile_r2"]
        * clamp(values["velocity_profile_r2"], 0.0, 1.0)
        * 100.0
        + LEGACY_WEIGHTS["cp_cut_r2"] * clamp(values["cp_cut_r2"], 0.0, 1.0) * 100.0
    ) / 0.25
    values.update(
        {
            "field_score": field_score,
            "force_score": force_score,
            "diagnostic_score": diagnostic_score,
            "overall_score": 0.5 * field_score + 0.25 * force_score + 0.25 * diagnostic_score,
        }
    )
    return values


def submission_metric_values(
    submission: dict[str, Any], dataset: dict[str, Any]
) -> dict[str, float]:
    if dataset.get("submission_format") == "metric_values":
        values = submission.get("metric_values")
        return dict(values) if isinstance(values, dict) else {}
    return legacy_metric_values(submission)


def public_submission_row(
    submission: dict[str, Any], dataset: dict[str, Any]
) -> dict[str, Any]:
    row = deepcopy(submission)
    row["metric_values"] = submission_metric_values(submission, dataset)
    return row


def validate_submission(
    path: Path, submission: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    prefix = str(path.relative_to(ROOT))
    datasets = dataset_by_name(manifest)
    dataset_name = submission.get("dataset")
    dataset = datasets.get(dataset_name)

    def add(message: str) -> None:
        errors.append(f"{prefix}: {message}")

    for key in ("submission_id", "model", "dataset", "split", "submitter_name"):
        if not isinstance(submission.get(key), str) or not submission[key].strip():
            add(f"{key} must be a non-empty string")

    if not dataset:
        add(f"dataset {dataset_name!r} is not present in the manifest")
        return errors

    if path.parent.name != dataset.get("slug"):
        add(f"file must be under submissions/{dataset.get('slug')}/")

    split_names = {split.get("name") for split in dataset.get("splits", [])}
    if split_names and submission.get("split") not in split_names:
        add(f"split {submission.get('split')!r} is not defined for {dataset_name}")

    if dataset.get("submission_format") != "metric_values":
        for key in BASE_METRICS:
            value = submission.get(key)
            if not is_number(value):
                add(f"{key} must be a finite number")
            elif key.endswith(("_l1", "_l2")) and value < 0:
                add(f"{key} cannot be negative")
            elif (key.startswith("r2_") or key.endswith("_r2")) and value > 1:
                add(f"{key} cannot exceed 1")

        fields = submission.get("dimensional_field_errors")
        if not isinstance(fields, dict):
            add("dimensional_field_errors must be an object")
        else:
            for definition in enabled_metric_definitions(manifest, dataset, "dimensional_fields"):
                metric_id = definition["id"]
                values = fields.get(metric_id)
                if not isinstance(values, dict):
                    add(f"dimensional_field_errors.{metric_id} must be an object")
                    continue
                for statistic in definition.get("statistics", []):
                    value = values.get(statistic)
                    if not is_number(value) or value < 0:
                        add(
                            f"dimensional_field_errors.{metric_id}.{statistic} "
                            "must be a finite non-negative number"
                        )

        coefficients = submission.get("absolute_coefficient_errors")
        if not isinstance(coefficients, dict):
            add("absolute_coefficient_errors must be an object")
        else:
            for definition in enabled_metric_definitions(manifest, dataset, "coefficient_errors"):
                metric_id = definition["id"]
                value = coefficients.get(metric_id)
                if not is_number(value) or value < 0:
                    add(
                        f"absolute_coefficient_errors.{metric_id} "
                        "must be a finite non-negative number"
                    )

    metric_values = submission_metric_values(submission, dataset)
    definitions = {
        definition["id"]: definition
        for definition in dataset_metric_definitions(manifest, dataset)
    }
    if (
        dataset.get("submission_format") == "metric_values"
        and not isinstance(submission.get("metric_values"), dict)
    ):
        add("metric_values must be an object")
    if dataset.get("submission_format") == "metric_values":
        unknown_metric_ids = set(metric_values) - set(dataset.get("metric_ids", []))
        if unknown_metric_ids:
            add(f"metric_values contains unknown metrics: {', '.join(sorted(unknown_metric_ids))}")
    for metric_id in dataset.get("metric_ids", []):
        value = metric_values.get(metric_id)
        definition = definitions.get(metric_id, {})
        if not is_number(value):
            add(f"metric_values.{metric_id} must be a finite number")
        elif definition.get("kind") in {"error", "score"} and value < 0:
            add(f"metric_values.{metric_id} cannot be negative")
        elif definition.get("kind") == "r2" and value > 1:
            add(f"metric_values.{metric_id} cannot exceed 1")

    aggregate = dataset.get("metric_aggregate")
    if isinstance(aggregate, dict):
        aggregate_value = metric_values.get(aggregate.get("metric_id"))
        source_values = [metric_values.get(metric_id) for metric_id in aggregate.get("source_metric_ids", [])]
        if is_number(aggregate_value) and source_values and all(is_number(value) for value in source_values):
            expected = sum(source_values) / len(source_values)
            tolerance = aggregate.get("tolerance", 1e-6)
            if abs(aggregate_value - expected) > tolerance:
                add(
                    f"metric_values.{aggregate['metric_id']} must equal the mean of "
                    f"metric_aggregate.source_metric_ids within {tolerance}"
                )

    diagnostics = submission.get("diagnostics")
    if not isinstance(diagnostics, dict):
        add("diagnostics must be an object")
    else:
        validate_diagnostic_panels(add, diagnostics, dataset)

    return errors


def source_files(manifest: dict[str, Any]) -> list[Path]:
    files: list[Path] = []
    for dataset in dataset_entries(manifest):
        files.extend(sorted((ROOT / "submissions" / dataset["slug"]).glob("*.json")))
    return files


def validate_paths(paths: list[Path], manifest: dict[str, Any]) -> list[str]:
    errors = validate_manifest(manifest)
    seen_ids: dict[str, Path] = {}
    for path in paths:
        try:
            submission = load_json(path)
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{path}: cannot read JSON: {error}")
            continue
        if not isinstance(submission, dict):
            errors.append(f"{path}: submission must be a JSON object")
            continue
        errors.extend(validate_submission(path, submission, manifest))
        submission_id = submission.get("submission_id")
        if submission_id in seen_ids:
            errors.append(
                f"{path.relative_to(ROOT)}: duplicate submission_id also used by "
                f"{seen_ids[submission_id].relative_to(ROOT)}"
            )
        elif submission_id:
            seen_ids[submission_id] = path
    return errors


def source_rows_by_dataset(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for dataset in dataset_entries(manifest):
        paths = sorted((ROOT / "submissions" / dataset["slug"]).glob("*.json"))
        rows[dataset["name"]] = [
            public_submission_row(load_json(path), dataset) for path in paths
        ]
    return rows


def latest_submission_date(rows: list[dict[str, Any]]) -> str:
    dates = [row.get("submitted_at") for row in rows if isinstance(row.get("submitted_at"), str)]
    valid_dates: list[str] = []
    for value in dates:
        try:
            date.fromisoformat(value)
            valid_dates.append(value)
        except ValueError:
            continue
    return max(valid_dates, default=date.today().isoformat())


def expected_outputs(
    manifest: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    updated_manifest = deepcopy(manifest)
    rows_by_dataset = source_rows_by_dataset(updated_manifest)
    all_rows: list[dict[str, Any]] = []
    latest_dates: list[str] = []

    for dataset in dataset_entries(updated_manifest):
        rows = rows_by_dataset[dataset["name"]]
        latest = latest_submission_date(rows)
        dataset["submission_count"] = len(rows)
        dataset["updated_at"] = latest
        latest_dates.append(latest)
        all_rows.extend(rows)

    latest_global = max(latest_dates, default=date.today().isoformat())
    updated_manifest["generated_at"] = f"{latest_global}T00:00:00Z"
    return updated_manifest, rows_by_dataset, all_rows


def build(manifest: dict[str, Any]) -> None:
    updated_manifest, rows_by_dataset, all_rows = expected_outputs(manifest)
    for dataset in dataset_entries(updated_manifest):
        write_json(ROOT / dataset["file"], rows_by_dataset[dataset["name"]])
    write_json(ROOT / updated_manifest["all_file"], all_rows)
    write_json(ROOT / "leaderboard.json", all_rows)
    write_json(MANIFEST_PATH, updated_manifest)


def check_generated_feeds(manifest: dict[str, Any]) -> list[str]:
    expected_manifest, rows_by_dataset, all_rows = expected_outputs(manifest)
    errors: list[str] = []
    for dataset in dataset_entries(expected_manifest):
        path = ROOT / dataset["file"]
        if not path.exists() or load_json(path) != rows_by_dataset[dataset["name"]]:
            errors.append(f"{path.relative_to(ROOT)} is not synchronized with source submissions")
    for path_value in (expected_manifest["all_file"], "leaderboard.json"):
        path = ROOT / path_value
        if not path.exists() or load_json(path) != all_rows:
            errors.append(f"{path.relative_to(ROOT)} is not synchronized with source submissions")
    for key in (
        "schema_version",
        "generated_at",
        "metric_catalog",
        "metric_definitions",
        "datasets",
    ):
        if manifest.get(key) != expected_manifest.get(key):
            errors.append(f"leaderboard/manifest.json has stale {key}")
    return errors


def print_errors(errors: list[str]) -> int:
    if not errors:
        return 0
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate submissions")
    validate_parser.add_argument("paths", nargs="*", type=Path)
    subparsers.add_parser("build", help="validate and regenerate all leaderboard feeds")
    subparsers.add_parser("check", help="validate submissions and verify generated feeds")
    args = parser.parse_args()

    manifest = load_json(MANIFEST_PATH)
    paths = [path.resolve() for path in getattr(args, "paths", [])] or source_files(manifest)
    errors = validate_paths(paths, manifest)
    if errors:
        return print_errors(errors)

    if args.command == "build":
        build(manifest)
        print(f"Built leaderboard feeds from {len(paths)} validated submissions.")
    elif args.command == "check":
        errors = check_generated_feeds(manifest)
        if errors:
            return print_errors(errors)
        print(f"Validated {len(paths)} submissions; generated feeds are synchronized.")
    else:
        print(f"Validated {len(paths)} submission file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
