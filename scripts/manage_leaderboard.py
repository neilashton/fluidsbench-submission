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

        diagnostics = entry.get("diagnostics")
        if not isinstance(diagnostics, dict):
            errors.append(f"{name} diagnostics must be an object")
            continue
        stations = diagnostics.get("cp_stations")
        if not isinstance(stations, list) or not stations:
            errors.append(f"{name} diagnostics.cp_stations must be a non-empty array")
            continue
        station_ids = [station.get("id") for station in stations]
        if any(not station_id for station_id in station_ids) or len(station_ids) != len(set(station_ids)):
            errors.append(f"{name} Cp station IDs must be present and unique")
        for station in stations:
            for key in ("label", "x_label", "description", "basis", "source_url"):
                if not isinstance(station.get(key), str) or not station[key].strip():
                    errors.append(f"{name} Cp station {station.get('id')!r} requires {key}")
            if station.get("basis") not in {"published_validation_trace", "fluidsbench_benchmark_trace"}:
                errors.append(f"{name} Cp station {station.get('id')!r} has an unsupported basis")

    return errors


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

    for key in BASE_METRICS:
        value = submission.get(key)
        if not is_number(value):
            add(f"{key} must be a finite number")
        elif key.endswith(("_l1", "_l2")) and value < 0:
            add(f"{key} cannot be negative")
        elif key.startswith("r2_") or key.endswith("_r2"):
            if value > 1:
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

    diagnostics = submission.get("diagnostics")
    if not isinstance(diagnostics, dict):
        add("diagnostics must be an object")
    else:
        for key in ("cp_cuts", "velocity_profiles"):
            if not isinstance(diagnostics.get(key), list):
                add(f"diagnostics.{key} must be an array")

        cp_cuts = diagnostics.get("cp_cuts")
        if isinstance(cp_cuts, list):
            required_station_ids = {
                station["id"] for station in dataset.get("diagnostics", {}).get("cp_stations", [])
            }
            provided_station_ids = [
                cut.get("station_id") for cut in cp_cuts if isinstance(cut, dict)
            ]
            duplicate_station_ids = {
                station_id
                for station_id in provided_station_ids
                if station_id and provided_station_ids.count(station_id) > 1
            }
            valid_provided_station_ids = {
                station_id for station_id in provided_station_ids if isinstance(station_id, str) and station_id
            }
            missing_station_ids = required_station_ids - valid_provided_station_ids
            unknown_station_ids = valid_provided_station_ids - required_station_ids
            if missing_station_ids:
                add(f"diagnostics.cp_cuts is missing stations: {', '.join(sorted(missing_station_ids))}")
            if unknown_station_ids:
                add(f"diagnostics.cp_cuts has unknown stations: {', '.join(sorted(unknown_station_ids))}")
            if duplicate_station_ids:
                add(f"diagnostics.cp_cuts has duplicate stations: {', '.join(sorted(duplicate_station_ids))}")

            for index, cut in enumerate(cp_cuts):
                if not isinstance(cut, dict):
                    add(f"diagnostics.cp_cuts[{index}] must be an object")
                    continue
                for key in ("case_id", "cut_id", "station_id"):
                    if not isinstance(cut.get(key), str) or not cut[key].strip():
                        add(f"diagnostics.cp_cuts[{index}].{key} must be a non-empty string")
                values = cut.get("values")
                if not isinstance(values, list) or not values:
                    add(f"diagnostics.cp_cuts[{index}].values must be a non-empty array")
                    continue
                for point_index, point in enumerate(values):
                    if not isinstance(point, dict) or not is_number(point.get("x")) or not is_number(point.get("cp")):
                        add(
                            f"diagnostics.cp_cuts[{index}].values[{point_index}] "
                            "must contain finite numeric x and cp values"
                        )

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
        rows[dataset["name"]] = [load_json(path) for path in paths]
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
    for key in ("schema_version", "generated_at", "metric_catalog", "datasets"):
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
