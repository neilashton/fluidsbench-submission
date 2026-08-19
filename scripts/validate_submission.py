#!/usr/bin/env python3
"""Validate FluidsBench submission metadata and profile chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference.scores import composite_overall_score, legacy_aero_scores
from reference.weightings import evaluator_weighting

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover - exercised by the command's dependency check
    Draft202012Validator = None
    FormatChecker = None


MANIFEST_PATH = ROOT / "leaderboard" / "manifest.json"
SCHEMA_ROOT = ROOT / "schemas"
OPEN_REPRODUCIBILITY_CONTRACTS = {
    "2.0": "open-reproducibility-2.0",
    "3.0": "open-reproducibility-3.0",
}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def manifest_with_benchmark_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    """Overlay benchmark-owned contract fields onto generated manifest metadata.

    The compact leaderboard manifest is generated output, while each dataset's
    submission specification is the source of truth for accepted metric IDs,
    ranking, metric equations, and scoring-support status.  Applying this small
    overlay before validation prevents a changed specification from being
    rejected solely because the generated manifest has not yet been rebuilt.

    Presentation-only metric metadata (labels, descriptions, groups, and display
    precision) remains owned by the leaderboard manifest.  A newly introduced
    metric therefore still needs a corresponding presentation definition there.
    """

    updated = deepcopy(manifest)
    definitions = {
        definition.get("id"): definition
        for definition in updated.get("metric_definitions", [])
        if isinstance(definition, dict) and isinstance(definition.get("id"), str)
    }
    for dataset in updated.get("datasets", []):
        slug = dataset.get("slug")
        if not isinstance(slug, str):
            continue
        spec_path = ROOT / "benchmark-specs" / slug / "submission-spec.json"
        if not spec_path.is_file():
            continue
        specification = load_json(spec_path)
        metrics = [
            metric
            for metric in specification.get("metrics", [])
            if isinstance(metric, dict) and isinstance(metric.get("id"), str)
        ]
        dataset["metric_ids"] = [metric["id"] for metric in metrics]
        if isinstance(specification.get("ranking"), dict):
            dataset["ranking"] = deepcopy(specification["ranking"])
        composite = specification.get("overall_score_composite")
        if isinstance(composite, dict):
            dataset["overall_score_composite"] = deepcopy(composite)
        else:
            dataset.pop("overall_score_composite", None)
        scoring_support = specification.get("scoring_support")
        if isinstance(scoring_support, dict):
            dataset["scoring_support"] = {
                key: deepcopy(value)
                for key, value in scoring_support.items()
                if key != "manifest_file"
            }
        for metric in metrics:
            definition = definitions.get(metric["id"])
            if definition is None:
                continue
            for key in ("unit", "direction", "kind", "equation"):
                if key in metric:
                    definition[key] = deepcopy(metric[key])
    return updated


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def json_path(parts: list[Any]) -> str:
    result = "$"
    for part in parts:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result


def schema_errors(value: Any, schema_name: str, *, schema_version: str = "v1") -> list[str]:
    if Draft202012Validator is None:
        return ["Python dependency jsonschema is missing; run: python3 -m pip install -r requirements.txt"]
    schema = load_json(SCHEMA_ROOT / schema_version / schema_name)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{json_path(list(error.absolute_path))}: {error.message}"
        for error in sorted(validator.iter_errors(value), key=lambda item: json_path(list(item.absolute_path)))
    ]


def safe_submission_path(
    add: Any,
    directory: Path,
    filename: Any,
    *,
    label: str,
) -> Path | None:
    """Resolve a declared package file without allowing absolute paths or traversal."""

    if not isinstance(filename, str) or not filename:
        add(f"{label} must be a non-empty relative file path")
        return None
    relative = Path(filename)
    if relative.is_absolute() or ".." in relative.parts:
        add(f"{label} must stay inside the submission directory")
        return None
    candidate = directory / relative
    try:
        if not candidate.resolve().is_relative_to(directory.resolve()):
            add(f"{label} must stay inside the submission directory")
            return None
    except OSError as error:
        add(f"cannot resolve {label}: {error}")
        return None
    return candidate


def load_json_lines(add: Any, path: Path, *, label: str) -> list[dict[str, Any]]:
    """Load strict UTF-8 JSON Lines while retaining useful source line errors."""

    records: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not raw_line.strip():
                    add(f"{label} line {line_number} must not be blank")
                    continue
                try:
                    value = json.loads(raw_line)
                except json.JSONDecodeError as error:
                    add(f"{label} line {line_number} is not valid JSON: {error.msg}")
                    continue
                if not isinstance(value, dict):
                    add(f"{label} line {line_number} must be a JSON object")
                    continue
                records.append(value)
    except (OSError, UnicodeError) as error:
        add(f"cannot read {label}: {error}")
    return records


def validate_domain_semantics(add: Any, domain: Any, *, label: str) -> None:
    if not isinstance(domain, dict) or domain.get("kind") != "axis_aligned_box":
        return
    minimum = domain.get("minimum")
    maximum = domain.get("maximum")
    if (
        not isinstance(minimum, list)
        or not isinstance(maximum, list)
        or len(minimum) != len(maximum)
        or not minimum
    ):
        add(f"{label} axis-aligned bounding-box dimensions must match")
        return
    if any(
        not is_number(lower) or not is_number(upper) or lower >= upper
        for lower, upper in zip(minimum, maximum)
    ):
        add(f"{label} axis-aligned bounding-box minimum must be less than maximum")


def submission_files(paths: list[Path] | None = None) -> list[Path]:
    if not paths:
        return sorted((ROOT / "submissions").glob("*/*/submission.json"))
    result: list[Path] = []
    for raw_path in paths:
        path = raw_path.resolve()
        if path.is_dir():
            candidate = path / "submission.json"
            if candidate.exists():
                result.append(candidate)
            else:
                result.extend(sorted(path.glob("*/submission.json")))
        else:
            result.append(path)
    return sorted(set(result))


def split_entry(dataset: dict[str, Any], split_id: str) -> dict[str, Any] | None:
    return next((split for split in dataset.get("splits", []) if split.get("id") == split_id), None)


def validate_metadata(
    add: Any,
    path: Path,
    submission: dict[str, Any],
    dataset: dict[str, Any],
    split: dict[str, Any],
) -> None:
    expected_parent = ROOT / "submissions" / dataset["slug"] / submission["submission_id"]
    if path.parent != expected_parent:
        add(f"submission.json must be stored at {expected_parent.relative_to(ROOT)}/submission.json")
    if submission.get("dataset") != dataset["name"]:
        add(f"dataset must be {dataset['name']!r} for dataset_id {dataset['slug']!r}")
    if submission.get("split") != split["name"]:
        add(f"split must be {split['name']!r} for split_id {split['id']!r}")
    if submission.get("model_type") not in submission.get("model_types", []):
        add("model_type must also appear in model_types")

    regime = submission.get("training_regime")
    target = submission.get("target_data_used")
    pretrained = submission.get("external_pretraining")
    pretraining_data = submission.get("pretraining_data", [])
    if regime == "from_scratch":
        if pretrained or pretraining_data:
            add("from_scratch requires external_pretraining=false and an empty pretraining_data list")
        if target != "official_train":
            add("from_scratch requires target_data_used=official_train")
    elif regime == "pretrained_zero_shot":
        if not pretrained or not pretraining_data:
            add("pretrained_zero_shot requires external_pretraining=true and named pretraining_data")
        if target != "none":
            add("pretrained_zero_shot requires target_data_used=none")
    elif regime == "pretrained_official_train":
        if not pretrained or not pretraining_data:
            add("pretrained_official_train requires external_pretraining=true and named pretraining_data")
        if target != "official_train":
            add("pretrained_official_train requires target_data_used=official_train")
    elif regime == "other" and not submission.get("training_regime_explanation", "").strip():
        add("training_regime=other requires training_regime_explanation")

    for key in ("paper_url", "code_url"):
        value = submission.get(key, "")
        if value and (not isinstance(value, str) or urlparse(value).scheme not in {"http", "https"}):
            add(f"{key} must be empty or use http/https")
    try:
        date.fromisoformat(submission.get("submitted_at", ""))
    except (TypeError, ValueError):
        add("submitted_at must be an ISO date in YYYY-MM-DD form")


def validate_metrics(add: Any, submission: dict[str, Any], dataset: dict[str, Any], manifest: dict[str, Any]) -> None:
    values = submission.get("metric_values", {})
    expected_ids = set(dataset.get("metric_ids", []))
    actual_ids = set(values)
    missing = sorted(expected_ids - actual_ids)
    unknown = sorted(actual_ids - expected_ids)
    if missing:
        add(f"metric_values is missing: {', '.join(missing)}")
    if unknown:
        add(f"metric_values contains unknown metrics: {', '.join(unknown)}")
    definitions = {definition["id"]: definition for definition in manifest["metric_definitions"]}
    for metric_id, value in values.items():
        if not is_number(value):
            add(f"metric_values.{metric_id} must be a finite number")
            continue
        definition = definitions.get(metric_id, {})
        if definition.get("kind") in {"error", "score"} and value < 0:
            add(f"metric_values.{metric_id} cannot be negative")
        if definition.get("kind") == "score" and value > 100:
            add(f"metric_values.{metric_id} cannot exceed 100")
        if definition.get("kind") == "r2" and value > 1:
            add(f"metric_values.{metric_id} cannot exceed 1")

    aggregate = dataset.get("metric_aggregate")
    if isinstance(aggregate, dict):
        source_values = [values.get(metric_id) for metric_id in aggregate.get("source_metric_ids", [])]
        target = values.get(aggregate.get("metric_id"))
        if is_number(target) and source_values and all(is_number(value) for value in source_values):
            expected = sum(source_values) / len(source_values)
            if not math.isclose(target, expected, rel_tol=0.0, abs_tol=aggregate.get("tolerance", 1e-6)):
                add(f"metric_values.{aggregate['metric_id']} must equal the declared source-metric mean")

    expected_scores = None
    composite = dataset.get("overall_score_composite")
    if isinstance(composite, dict):
        components = composite.get("components")
        component_ids = (
            [component.get("metric_id") for component in components if isinstance(component, dict)]
            if isinstance(components, list)
            else []
        )
        target_metric_id = composite.get("metric_id")
        if (
            composite.get("operation") != "weighted_component_scores"
            or not isinstance(components, list)
            or not components
            or len(component_ids) != len(components)
            or not isinstance(target_metric_id, str)
            or target_metric_id not in expected_ids
            or any(not isinstance(metric_id, str) or metric_id not in expected_ids for metric_id in component_ids)
        ):
            add("dataset overall_score_composite does not reference a valid target and component metric set")
        elif all(
            isinstance(metric_id, str) and is_number(values.get(metric_id))
            for metric_id in component_ids
        ):
            try:
                expected = composite_overall_score(values, composite)
            except (KeyError, TypeError, ValueError) as exc:
                add(f"dataset overall_score_composite is invalid: {exc}")
            else:
                tolerance = composite.get("tolerance", 1e-6)
                if not is_number(tolerance) or tolerance < 0:
                    add("dataset overall_score_composite requires a metric_id and non-negative tolerance")
                elif not is_number(values.get(target_metric_id)) or not math.isclose(
                    values[target_metric_id], expected, rel_tol=0.0, abs_tol=tolerance
                ):
                    add(f"metric_values.{target_metric_id} does not match its declared composite equation")
    if dataset.get("submission_format") == "legacy_external_aero" and all(
        is_number(values.get(metric_id))
        for metric_id in {"cd_r2", "cl_r2", "velocity_profile_r2", "cp_cut_r2"}
    ):
        try:
            expected_scores = legacy_aero_scores(values)
        except (KeyError, TypeError, ValueError):
            pass
    if expected_scores is not None:
        for metric_id, expected in expected_scores.items():
            if not is_number(values.get(metric_id)) or not math.isclose(
                values[metric_id], expected, rel_tol=0.0, abs_tol=1e-6
            ):
                add(f"metric_values.{metric_id} does not match its declared score equation")


def scoring_support_manifest_path(
    add: Any,
    dataset_spec: dict[str, Any],
    submission: dict[str, Any],
) -> Path | None:
    """Locate the repository copy of the benchmark-owned scoring-support manifest."""

    binding = dataset_spec.get("scoring_support")
    if not isinstance(binding, dict):
        add("schema v3 requires scoring_support in the benchmark specification")
        return None
    manifest_file = binding.get("manifest_file")
    dataset_directory = ROOT / "benchmark-specs" / submission["dataset_id"]
    if isinstance(manifest_file, str) and manifest_file:
        relative = Path(manifest_file)
        if relative.is_absolute() or ".." in relative.parts:
            add("benchmark scoring_support.manifest_file must remain inside its dataset specification")
            return None
        return dataset_directory / relative

    release_id = binding.get("release_id")
    matches = []
    for candidate in dataset_directory.glob("scoring-support/**/manifest.json"):
        try:
            value = load_json(candidate)
        except (OSError, json.JSONDecodeError):
            continue
        if value.get("release_id") == release_id:
            matches.append(candidate)
    if len(matches) != 1:
        add(
            "benchmark scoring_support must provide manifest_file or identify exactly one local "
            f"manifest for release_id={release_id!r}"
        )
        return None
    return matches[0]


def validate_v3_scoring_support(
    add: Any,
    submission: dict[str, Any],
    dataset_spec: dict[str, Any],
    split_spec_entry: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Validate and load the fixed public spatial scoring support used by schema v3."""

    declared = submission["scoring_support"]
    owner_binding = dataset_spec.get("scoring_support", {})
    owner_status = owner_binding.get("status")
    submissions_open = owner_binding.get("submissions_open")
    if owner_status != "official" or submissions_open is not True:
        reason = owner_binding.get("closed_reason") or "dataset-owner approval is incomplete"
        add(
            "schema v3 submissions are closed for this dataset's scoring support: "
            f"status={owner_status!r}, submissions_open={submissions_open!r}; {reason}"
        )
    required_owner_fields = (
        "release_id",
        "manifest_file",
        "manifest_url",
        "manifest_sha256",
    )
    missing_owner_fields = [
        key
        for key in required_owner_fields
        if not isinstance(owner_binding.get(key), str) or not owner_binding[key].strip()
    ]
    if missing_owner_fields:
        add(
            "benchmark scoring_support is incomplete; missing: "
            f"{', '.join(missing_owner_fields)}"
        )
    owner_approval = owner_binding.get("owner_approval")
    if owner_status == "official" and (
        not isinstance(owner_approval, dict)
        or any(
            not isinstance(owner_approval.get(key), str) or not owner_approval[key].strip()
            for key in ("approved_by", "approved_at", "pull_request_url")
        )
    ):
        add("official benchmark scoring_support requires complete dataset-owner approval metadata")
    for key in ("release_id", "manifest_url", "manifest_sha256"):
        if declared.get(key) != owner_binding.get(key):
            add(f"scoring_support.{key} must match the benchmark specification")
    if declared.get("status") != owner_status:
        add("scoring_support.status must match the benchmark specification")

    manifest_path = scoring_support_manifest_path(add, dataset_spec, submission)
    if manifest_path is None:
        return None, None
    if not manifest_path.is_file():
        add(f"missing scoring-support manifest: {manifest_path.relative_to(ROOT)}")
        return None, None
    if sha256_file(manifest_path) != declared["manifest_sha256"]:
        add("scoring-support manifest does not match scoring_support.manifest_sha256")
    try:
        support_manifest = load_json(manifest_path)
    except (OSError, json.JSONDecodeError) as error:
        add(f"cannot read scoring-support manifest: {error}")
        return None, None
    for error in schema_errors(
        support_manifest,
        "manifest.schema.json",
        schema_version="scoring-support/v1",
    ):
        add(f"scoring-support manifest {error}")

    manifest_identities = {
        "release_id": declared["release_id"],
        "dataset_id": submission["dataset_id"],
        "dataset_version": submission["dataset_version"],
        "evaluation_reference_version": submission["evaluation"]["reference_version"],
    }
    for key, expected in manifest_identities.items():
        if support_manifest.get(key) != expected:
            add(f"scoring-support manifest {key} must equal {expected!r}")
    if support_manifest.get("status") != "official":
        add("schema v3 submissions require an official scoring-support manifest")
    if owner_status == "official" and support_manifest.get("owner_approval") != owner_approval:
        add("scoring-support manifest owner_approval must match the benchmark specification")

    dataset_metrics = {
        metric.get("id"): metric
        for metric in dataset_spec.get("metrics", [])
        if isinstance(metric, dict) and isinstance(metric.get("id"), str)
    }
    support_aggregations = {
        "per_geometry_then_macro_average",
        "flatten_all_aligned_field_values",
        "all_test_cases",
        "benchmark_field_rrmse_across_cases",
        "benchmark_scalar_rrmse_across_cases",
    }
    required_bound_metric_ids = {
        metric_id
        for metric_id, metric in dataset_metrics.items()
        if metric.get("aggregation") in support_aggregations
    }

    def expected_reduction(metric_id: str, metric: dict[str, Any]) -> str | None:
        aggregation = metric.get("aggregation")
        if aggregation in {
            "benchmark_field_rrmse_across_cases",
            "benchmark_scalar_rrmse_across_cases",
        }:
            return "dataset_reference"
        if metric_id.endswith("_rel_l1"):
            return "relative_l1_percent"
        if metric_id.endswith("_rel_l2"):
            return "relative_l2_percent"
        if metric_id.endswith("_rrmse"):
            return "dataset_reference"
        if metric_id.endswith("_rmse"):
            return "rmse"
        if metric_id.endswith("_mse"):
            return "mse"
        if metric_id.endswith("_mae"):
            return "mae"
        if metric_id.endswith("_r2"):
            return "r2"
        return None

    bound_metric_ids: list[str] = []
    required_artifact_roles: dict[str, set[str]] = {}
    for support in support_manifest.get("supports", []):
        if not isinstance(support, dict):
            continue
        support_id = support.get("id")
        quantities = [
            quantity for quantity in support.get("quantities", []) if isinstance(quantity, dict)
        ]
        quantity_ids = [quantity.get("id") for quantity in quantities]
        if len(quantity_ids) != len(set(quantity_ids)):
            add(f"scoring support {support_id!r} quantity IDs must be unique")
        for quantity in quantities:
            component_ids = [
                component.get("id")
                for component in quantity.get("components", [])
                if isinstance(component, dict)
            ]
            if len(component_ids) != len(set(component_ids)):
                add(
                    f"scoring support {support_id!r}/{quantity.get('id')!r} component IDs "
                    "must be unique"
                )
        for binding in support.get("metric_bindings", []):
            if not isinstance(binding, dict):
                continue
            metric_id = binding.get("metric_id")
            bound_metric_ids.append(metric_id)
            metric = dataset_metrics.get(metric_id)
            if metric is None:
                add(f"scoring support {support_id!r} binds unknown metric_id {metric_id!r}")
                continue
            if binding.get("quantity_id") not in quantity_ids:
                add(
                    f"scoring support {support_id!r} metric {metric_id!r} references "
                    "an unknown quantity"
                )
            if binding.get("aggregation") != metric.get("aggregation"):
                add(
                    f"scoring support {support_id!r} metric {metric_id!r} aggregation "
                    "must match the dataset specification"
                )
            if binding.get("dataset_weighting") != metric.get("weighting"):
                add(
                    f"scoring support {support_id!r} metric {metric_id!r} "
                    "dataset_weighting must match the dataset specification"
                )
            expected = expected_reduction(metric_id, metric)
            if expected is None:
                add(
                    f"dataset metric {metric_id!r} requires an explicit supported "
                    "scoring reduction"
                )
            elif binding.get("reduction") != expected:
                add(
                    f"scoring support {support_id!r} metric {metric_id!r} reduction "
                    f"must be {expected!r}"
                )
            expected_weighting = evaluator_weighting(metric.get("weighting"))
            if binding.get("weighting") != expected_weighting:
                add(
                    f"scoring support {support_id!r} metric {metric_id!r} weighting "
                    f"must be {expected_weighting!r}"
                )
            expected_case_evidence = (
                "aggregate_only"
                if expected in {"r2", "dataset_reference"}
                else "metric_value"
            )
            if binding.get("case_evidence") != expected_case_evidence:
                add(
                    f"scoring support {support_id!r} metric {metric_id!r} "
                    f"case_evidence must be {expected_case_evidence!r}"
                )
            if expected == "dataset_reference":
                reference_rule = binding.get("reference_rule", {})
                if (
                    reference_rule.get("id") != metric.get("aggregation")
                    or reference_rule.get("version")
                    != dataset_spec.get("evaluation_reference_version")
                ):
                    add(
                        f"scoring support {support_id!r} metric {metric_id!r} "
                        "must pin the dataset aggregation rule and evaluator version"
                    )
            scalar_aggregation = metric.get("aggregation") in {
                "all_test_cases",
                "benchmark_scalar_rrmse_across_cases",
            }
            if scalar_aggregation and support.get("domain") != "scalar_case":
                add(
                    f"scoring support {support_id!r} metric {metric_id!r} "
                    "requires a scalar_case support"
                )
            if not scalar_aggregation and support.get("domain") == "scalar_case":
                add(
                    f"scoring support {support_id!r} metric {metric_id!r} "
                    "cannot use a scalar_case support"
                )
        location = support.get("location_definition", {})
        roles = {
            value
            for key, value in location.items()
            if key in {"artifact_role", "target_artifact_role"}
            and isinstance(value, str)
        }
        weight_rule = location.get("weight_rule", {})
        if isinstance(weight_rule, dict) and isinstance(weight_rule.get("artifact_role"), str):
            roles.add(weight_rule["artifact_role"])
        required_artifact_roles[support_id] = roles
    if len(bound_metric_ids) != len(set(bound_metric_ids)):
        add("each scoring-support metric may be bound only once")
    bound_metric_id_set = {
        metric_id for metric_id in bound_metric_ids if isinstance(metric_id, str)
    }
    if bound_metric_id_set != required_bound_metric_ids:
        add(
            "scoring-support metric bindings must exactly cover dataset field and "
            "case-scalar metrics; "
            f"missing={sorted(required_bound_metric_ids - bound_metric_id_set)}, "
            f"unexpected={sorted(bound_metric_id_set - required_bound_metric_ids)}"
        )

    case_set_entry = next(
        (
            entry
            for entry in support_manifest.get("case_sets", [])
            if isinstance(entry, dict) and entry.get("id") == submission["case_set_id"]
        ),
        None,
    )
    if case_set_entry is None:
        add(f"scoring-support manifest does not define case_set_id {submission['case_set_id']!r}")
        return support_manifest, None
    index_file = case_set_entry.get("index_file")
    if not isinstance(index_file, str) or not index_file:
        add("scoring-support case set must declare index_file")
        return support_manifest, None
    relative = Path(index_file)
    if relative.is_absolute() or ".." in relative.parts:
        add("scoring-support case-set index_file must remain beside the manifest")
        return support_manifest, None
    case_index_path = manifest_path.parent / relative
    if not case_index_path.is_file():
        add(f"missing scoring-support case index: {case_index_path.relative_to(ROOT)}")
        return support_manifest, None
    if sha256_file(case_index_path) != case_set_entry.get("index_sha256"):
        add("scoring-support case index does not match its manifest digest")
    try:
        case_index = load_json(case_index_path)
    except (OSError, json.JSONDecodeError) as error:
        add(f"cannot read scoring-support case index: {error}")
        return support_manifest, None
    for error in schema_errors(
        case_index,
        "case-index.schema.json",
        schema_version="scoring-support/v1",
    ):
        add(f"scoring-support case index {error}")
    case_index_identities = {
        "release_id": declared["release_id"],
        "dataset_id": submission["dataset_id"],
        "case_set_id": submission["case_set_id"],
    }
    for key, expected in case_index_identities.items():
        if case_index.get(key) != expected:
            add(f"scoring-support case index {key} must equal {expected!r}")
    if case_index.get("case_count") != split_spec_entry.get("case_count"):
        add("scoring-support case index case_count must match the benchmark split")

    support_ids = [
        support.get("id")
        for support in support_manifest.get("supports", [])
        if isinstance(support, dict) and isinstance(support.get("id"), str)
    ]
    if len(support_ids) != len(set(support_ids)):
        add("scoring-support manifest support IDs must be unique")
    loaded_cases: list[dict[str, Any]] = []
    indexed_case_ids: list[str] = []
    referenced_files: set[str] = set()
    for chunk_entry in case_index.get("chunks", []):
        if not isinstance(chunk_entry, dict):
            continue
        filename = chunk_entry.get("file")
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).is_absolute()
            or ".." in Path(filename).parts
        ):
            add(f"invalid scoring-support chunk filename: {filename!r}")
            continue
        if filename in referenced_files:
            add(f"scoring-support case index references {filename!r} more than once")
            continue
        referenced_files.add(filename)
        chunk_path = case_index_path.parent / filename
        if not chunk_path.is_file():
            add(f"missing scoring-support case chunk: {chunk_path.relative_to(ROOT)}")
            continue
        if sha256_file(chunk_path) != chunk_entry.get("sha256"):
            add(f"scoring-support case chunk {filename} does not match its index digest")
        try:
            chunk = load_json(chunk_path)
        except (OSError, json.JSONDecodeError) as error:
            add(f"cannot read scoring-support case chunk {filename}: {error}")
            continue
        for error in schema_errors(
            chunk,
            "case-chunk.schema.json",
            schema_version="scoring-support/v1",
        ):
            add(f"scoring-support case chunk {filename} {error}")
        for key, expected in case_index_identities.items():
            if chunk.get(key) != expected:
                add(f"scoring-support case chunk {filename} {key} must equal {expected!r}")
        chunk_cases = [case for case in chunk.get("cases", []) if isinstance(case, dict)]
        chunk_case_ids = [case.get("case_id") for case in chunk_cases]
        if chunk_case_ids != chunk_entry.get("case_ids"):
            add(f"scoring-support case chunk {filename} order differs from its index entry")
        if len(chunk_cases) != chunk_entry.get("case_count"):
            add(f"scoring-support case chunk {filename} count differs from its index entry")
        indexed_case_ids.extend(chunk_entry.get("case_ids", []))
        loaded_cases.extend(chunk_cases)
        for case in chunk_cases:
            observed_supports: set[str] = set()
            for instance in case.get("support_instances", []):
                if not isinstance(instance, dict):
                    continue
                support_id = instance.get("support_id")
                if support_id in observed_supports:
                    add(
                        f"scoring-support case {case.get('case_id')} contains duplicate "
                        f"support_id {support_id!r}"
                    )
                observed_supports.add(support_id)
                if support_id not in support_ids:
                    add(
                        f"scoring-support case {case.get('case_id')} references unknown "
                        f"support_id {support_id!r}"
                    )
                roles = [
                    artifact.get("role")
                    for artifact in instance.get("artifacts", [])
                    if isinstance(artifact, dict)
                ]
                if len(roles) != len(set(roles)):
                    add(
                        f"scoring-support case {case.get('case_id')}/{support_id} "
                        "artifact roles must be unique"
                    )
                missing_roles = sorted(required_artifact_roles.get(support_id, set()) - set(roles))
                if missing_roles:
                    add(
                        f"scoring-support case {case.get('case_id')}/{support_id} is missing "
                        f"required artifact roles: {missing_roles}"
                    )
            missing_supports = sorted(set(support_ids) - observed_supports)
            if missing_supports:
                add(
                    f"scoring-support case {case.get('case_id')} is missing support "
                    f"instances: {missing_supports}"
                )
    if len(loaded_cases) != case_index.get("case_count"):
        add("scoring-support loaded case count does not match the case index")
    if len(indexed_case_ids) != len(set(indexed_case_ids)):
        add("scoring-support case IDs must be unique across chunks")
    split_path = ROOT / "benchmark-specs" / submission["dataset_id"] / split_spec_entry["index_file"]
    if split_path.is_file():
        expected_case_ids = load_json(split_path).get("case_ids", [])
        if indexed_case_ids != expected_case_ids:
            missing = sorted(set(expected_case_ids) - set(indexed_case_ids))
            unexpected = sorted(set(indexed_case_ids) - set(expected_case_ids))
            add(
                "scoring-support case coverage differs from the benchmark split; "
                f"missing={missing[:5]}, unexpected={unexpected[:5]}"
            )
    actual_chunk_files = {
        path.relative_to(case_index_path.parent).as_posix()
        for path in case_index_path.parent.rglob("chunk-*.json")
    }
    if actual_chunk_files != referenced_files:
        add(
            "scoring-support case-index directory contains unindexed chunks: "
            f"{sorted(actual_chunk_files - referenced_files)}"
        )
    case_index["_loaded_cases"] = loaded_cases
    return support_manifest, case_index


def validate_v3_case_metrics(
    add: Any,
    directory: Path,
    submission: dict[str, Any],
    split_case_ids: list[str],
    support_manifest: dict[str, Any] | None,
    support_case_index: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate the per-case metric evidence and its aggregate scalar binding."""

    declaration = submission["case_metrics"]
    path = safe_submission_path(
        add,
        directory,
        declaration["file"],
        label="case_metrics.file",
    )
    if path is None:
        return None
    if not path.is_file():
        add(f"missing case metrics: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
        return None
    if sha256_file(path) != declaration["sha256"]:
        add("case-metrics file does not match case_metrics.sha256")
    try:
        case_metrics = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        add(f"cannot read case metrics: {error}")
        return None
    for error in schema_errors(case_metrics, "case-metrics.schema.json", schema_version="v3"):
        add(f"{declaration['file']} {error}")

    identities = {
        "submission_id": submission["submission_id"],
        "dataset_id": submission["dataset_id"],
        "split_id": submission["split_id"],
        "case_set_id": submission["case_set_id"],
        "scoring_support_release_id": submission["scoring_support"]["release_id"],
        "scoring_support_manifest_sha256": submission["scoring_support"]["manifest_sha256"],
    }
    for key, expected in identities.items():
        if case_metrics.get(key) != expected:
            add(f"{declaration['file']} {key} must equal {expected!r}")
    if declaration.get("case_count") != len(split_case_ids):
        add(f"case_metrics.case_count must be {len(split_case_ids)} for this split")
    if case_metrics.get("case_count") != declaration.get("case_count"):
        add("case-metrics case_count must equal submission.json case_metrics.case_count")
    if case_metrics.get("metric_values") != submission.get("metric_values"):
        add("case-metrics metric_values must exactly match submission.json")

    cases = case_metrics.get("cases", [])
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if case_ids != split_case_ids:
        missing = sorted(set(split_case_ids) - set(case_ids))
        unexpected = sorted(set(case_ids) - set(split_case_ids))
        add(
            "case-metrics case order differs from the benchmark split; "
            f"missing={missing[:5]}, unexpected={unexpected[:5]}"
        )

    expected_instances: dict[str, dict[str, int]] = {}
    if isinstance(support_case_index, dict):
        for case in support_case_index.get("_loaded_cases", support_case_index.get("cases", [])):
            if not isinstance(case, dict):
                continue
            expected_instances[case.get("case_id")] = {
                instance.get("support_id"): instance.get("entity_count")
                for instance in case.get("support_instances", [])
                if isinstance(instance, dict)
                and isinstance(instance.get("support_id"), str)
                and isinstance(instance.get("entity_count"), int)
            }

    bound_metrics: dict[str, str] = {}
    bound_metric_bindings: dict[str, dict[str, Any]] = {}
    extrapolation_policies: dict[str, str] = {}
    if isinstance(support_manifest, dict):
        for support in support_manifest.get("supports", []):
            if not isinstance(support, dict):
                continue
            support_id = support.get("id")
            if isinstance(support_id, str):
                extrapolation_policies[support_id] = support.get("extrapolation_policy")
            for binding in support.get("metric_bindings", []):
                if isinstance(binding, str):
                    bound_metrics[binding] = support_id
                elif isinstance(binding, dict):
                    metric_id = binding.get("metric_id") or binding.get("id")
                    if isinstance(metric_id, str):
                        bound_metrics[metric_id] = support_id
                        bound_metric_bindings[metric_id] = binding

    bound_metrics_by_support: dict[str, set[str]] = {}
    for metric_id, support_id in bound_metrics.items():
        if bound_metric_bindings.get(metric_id, {}).get("case_evidence") == "metric_value":
            bound_metrics_by_support.setdefault(support_id, set()).add(metric_id)
    per_case_values: dict[str, list[float]] = {
        metric_id: []
        for metric_id, binding in bound_metric_bindings.items()
        if binding.get("case_evidence") == "metric_value"
    }
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        expected_for_case = expected_instances.get(case_id, {})
        observed_support_ids: set[str] = set()
        for support in case.get("supports", []):
            if not isinstance(support, dict):
                continue
            support_id = support.get("support_id")
            if not isinstance(support_id, str):
                continue
            if support_id in observed_support_ids:
                add(f"{declaration['file']} {case_id} contains duplicate support_id {support_id!r}")
            observed_support_ids.add(support_id)
            if support_id not in expected_for_case:
                add(
                    f"{declaration['file']} {case_id} contains unexpected "
                    f"support_id {support_id!r}"
                )
            support_count = support.get("support_count")
            scored_count = support.get("scored_count")
            coverage = support.get("coverage_fraction")
            expected_count = expected_for_case.get(support_id)
            if expected_count is not None and support_count != expected_count:
                add(
                    f"{declaration['file']} {case_id}/{support_id} support_count must equal "
                    "the fixed scoring-support entity_count"
                )
            if isinstance(support_count, int) and isinstance(scored_count, int):
                if scored_count != support_count:
                    add(f"{declaration['file']} {case_id}/{support_id} must score every support entity")
                calculated = scored_count / support_count if support_count else 0.0
                if is_number(coverage) and not math.isclose(
                    coverage,
                    calculated,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    add(
                        f"{declaration['file']} {case_id}/{support_id} coverage_fraction "
                        "does not match scored_count/support_count"
                    )
            if not is_number(coverage) or not math.isclose(coverage, 1.0, rel_tol=0.0, abs_tol=1e-12):
                add(f"{declaration['file']} {case_id}/{support_id} requires coverage_fraction=1.0")
            if support.get("unmapped_count") != 0:
                add(f"{declaration['file']} {case_id}/{support_id} requires unmapped_count=0")
            if (
                extrapolation_policies.get(support_id) == "forbidden"
                and support.get("extrapolated_count") != 0
            ):
                add(
                    f"{declaration['file']} {case_id}/{support_id} forbids extrapolated scoring values"
                )
            weight_coverage = support.get("weight_coverage_fraction")
            if not is_number(weight_coverage) or not math.isclose(
                weight_coverage,
                1.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                add(f"{declaration['file']} {case_id}/{support_id} requires weight_coverage_fraction=1.0")
            metric_values = support.get("metric_values", {})
            observed_metric_ids = set(metric_values) if isinstance(metric_values, dict) else set()
            expected_metric_ids = bound_metrics_by_support.get(support_id, set())
            if observed_metric_ids != expected_metric_ids:
                missing_metrics = sorted(expected_metric_ids - observed_metric_ids)
                unexpected_metrics = sorted(observed_metric_ids - expected_metric_ids)
                add(
                    f"{declaration['file']} {case_id}/{support_id} metric IDs must "
                    "exactly match the official support bindings; "
                    f"missing={missing_metrics}, unexpected={unexpected_metrics}"
                )
            expected_statistics_ids = {
                metric_id
                for metric_id in expected_metric_ids
                if bound_metric_bindings.get(metric_id, {}).get("reduction")
                == "relative_l2_percent"
            }
            metric_statistics = support.get("metric_sufficient_statistics", {})
            observed_statistics_ids = (
                set(metric_statistics) if isinstance(metric_statistics, dict) else set()
            )
            if observed_statistics_ids != expected_statistics_ids:
                missing_statistics = sorted(
                    expected_statistics_ids - observed_statistics_ids
                )
                unexpected_statistics = sorted(
                    observed_statistics_ids - expected_statistics_ids
                )
                add(
                    f"{declaration['file']} {case_id}/{support_id} relative-L2 "
                    "sufficient-statistic IDs must exactly match the official "
                    f"support bindings; missing={missing_statistics}, "
                    f"unexpected={unexpected_statistics}"
                )
            for metric_id, statistics in (
                metric_statistics.items() if isinstance(metric_statistics, dict) else []
            ):
                if not isinstance(statistics, dict):
                    continue
                binding = bound_metric_bindings.get(metric_id, {})
                expected_identity = {
                    "reduction": "relative_l2_percent",
                    "weighting": binding.get("weighting"),
                    "dataset_weighting": binding.get("dataset_weighting"),
                }
                for key, expected in expected_identity.items():
                    if statistics.get(key) != expected:
                        add(
                            f"{declaration['file']} {case_id}/{support_id} "
                            f"metric_sufficient_statistics.{metric_id}.{key} "
                            f"must equal {expected!r}"
                        )
                entity_count = statistics.get("entity_count")
                if isinstance(support_count, int) and entity_count != support_count:
                    add(
                        f"{declaration['file']} {case_id}/{support_id} "
                        f"metric_sufficient_statistics.{metric_id}.entity_count "
                        "must equal support_count"
                    )
                total_weight = statistics.get("total_weight")
                if (
                    binding.get("weighting") == "uniform"
                    and isinstance(entity_count, int)
                    and is_number(total_weight)
                    and not math.isclose(
                        float(total_weight),
                        float(entity_count),
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                ):
                    add(
                        f"{declaration['file']} {case_id}/{support_id} "
                        f"metric_sufficient_statistics.{metric_id}.total_weight "
                        "must equal entity_count for uniform weighting"
                    )
                numerator = statistics.get("numerator")
                denominator = statistics.get("denominator")
                metric_value = (
                    metric_values.get(metric_id)
                    if isinstance(metric_values, dict)
                    else None
                )
                if (
                    is_number(numerator)
                    and float(numerator) >= 0
                    and is_number(denominator)
                    and float(denominator) > 0
                    and is_number(metric_value)
                ):
                    calculated_value = 100.0 * math.sqrt(
                        float(numerator) / float(denominator)
                    )
                    if not math.isclose(
                        float(metric_value),
                        calculated_value,
                        rel_tol=1e-12,
                        abs_tol=1e-12,
                    ):
                        add(
                            f"{declaration['file']} {case_id}/{support_id} "
                            f"metric_values.{metric_id} must equal "
                            "100*sqrt(numerator/denominator) from its sufficient "
                            "statistics"
                        )
            for metric_id, value in metric_values.items():
                expected_support_id = bound_metrics.get(metric_id)
                if expected_support_id is None:
                    add(
                        f"{declaration['file']} {case_id} contains unknown "
                        f"metric {metric_id!r}"
                    )
                elif expected_support_id != support_id:
                    add(
                        f"{declaration['file']} {case_id} metric {metric_id!r} belongs to "
                        f"support {expected_support_id!r}, not {support_id!r}"
                    )
                if metric_id in per_case_values and is_number(value):
                    per_case_values[metric_id].append(float(value))
        missing_supports = sorted(set(expected_for_case) - observed_support_ids)
        if missing_supports:
            add(f"{declaration['file']} {case_id} is missing scoring supports: {missing_supports}")

    for metric_id, values in per_case_values.items():
        if len(values) != len(split_case_ids):
            add(f"{declaration['file']} metric {metric_id!r} must have one value per test case")
            continue
        if (
            bound_metric_bindings.get(metric_id, {}).get("aggregation")
            != "per_geometry_then_macro_average"
        ):
            continue
        submitted_value = submission.get("metric_values", {}).get(metric_id)
        expected_value = sum(values) / len(values)
        if is_number(submitted_value) and not math.isclose(
            submitted_value,
            expected_value,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            add(
                f"metric_values.{metric_id} must equal the macro-average of its submitted "
                "per-case values"
            )
    return case_metrics


def validate_v3_discretization(
    add: Any,
    directory: Path,
    submission: dict[str, Any],
    split_case_ids: list[str],
    support_manifest: dict[str, Any] | None,
    support_case_index: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Validate the spatial summary and ordered per-evaluation-case JSONL records."""

    declaration = submission["spatial_discretization"]
    path = safe_submission_path(
        add,
        directory,
        declaration["file"],
        label="spatial_discretization.file",
    )
    if path is None:
        return None, []
    if not path.is_file():
        add(
            f"missing discretization summary: "
            f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"
        )
        return None, []
    if sha256_file(path) != declaration["sha256"]:
        add("discretization.json does not match spatial_discretization.sha256")
    try:
        summary = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        add(f"cannot read discretization summary: {error}")
        return None, []
    for error in schema_errors(summary, "discretization.schema.json", schema_version="v3"):
        add(f"{declaration['file']} {error}")
    identities = {
        "submission_id": submission["submission_id"],
        "dataset_id": submission["dataset_id"],
        "split_id": submission["split_id"],
        "scoring_support_release_id": submission["scoring_support"]["release_id"],
        "scoring_support_manifest_sha256": submission["scoring_support"]["manifest_sha256"],
    }
    for key, expected in identities.items():
        if summary.get(key) != expected:
            add(f"{declaration['file']} {key} must equal {expected!r}")

    def validate_representation(label: str, representation: Any) -> None:
        if not isinstance(representation, dict) or representation.get("used") is not True:
            return
        entity_counts = representation.get("entity_counts", [])
        entities = [
            entry.get("entity")
            for entry in entity_counts
            if isinstance(entry, dict)
        ]
        if len(entities) != len(set(entities)):
            add(f"{declaration['file']} {label} entity count names must be unique")
        for entry in entity_counts:
            if not isinstance(entry, dict):
                continue
            count = entry.get("count", {})
            if count.get("kind") == "per_case":
                ordered_values = (
                    count.get("minimum"),
                    count.get("median"),
                    count.get("maximum"),
                )
                if all(is_number(value) for value in ordered_values) and not (
                    ordered_values[0] <= ordered_values[1] <= ordered_values[2]
                ):
                    add(
                        f"{declaration['file']} {label}/{entry.get('entity')} requires "
                        "minimum <= median <= maximum"
                    )
        native = representation.get("native_comparison", {})
        if native.get("status") == "reported":
            native_entities = [
                entry.get("entity")
                for entry in native.get("native_entity_counts", [])
                if isinstance(entry, dict)
            ]
            fraction_entities = [
                entry.get("entity")
                for entry in native.get("fractions", [])
                if isinstance(entry, dict)
            ]
            if len(native_entities) != len(set(native_entities)):
                add(f"{declaration['file']} {label} native entity names must be unique")
            if len(fraction_entities) != len(set(fraction_entities)):
                add(f"{declaration['file']} {label} native fraction entity names must be unique")
            if set(native_entities) != set(entities) or set(fraction_entities) != set(entities):
                add(
                    f"{declaration['file']} {label} native counts and fractions "
                    "must cover exactly the reported entity count names"
                )
            for fraction_entry in native.get("fractions", []):
                if not isinstance(fraction_entry, dict):
                    continue
                fraction = fraction_entry.get("fraction", {})
                ordered_values = (
                    fraction.get("minimum"),
                    fraction.get("median"),
                    fraction.get("maximum"),
                )
                if (
                    fraction.get("kind") == "per_case"
                    and all(is_number(value) for value in ordered_values)
                    and not (ordered_values[0] <= ordered_values[1] <= ordered_values[2])
                ):
                    add(
                        f"{declaration['file']} {label}/{fraction_entry.get('entity')} native "
                        "fraction requires minimum <= median <= maximum"
                    )
            counts_by_entity = {
                entry.get("entity"): entry.get("count", {})
                for entry in entity_counts
                if isinstance(entry, dict)
            }
            native_counts_by_entity = {
                entry.get("entity"): entry.get("count", {})
                for entry in native.get("native_entity_counts", [])
                if isinstance(entry, dict)
            }
            fractions_by_entity = {
                entry.get("entity"): entry.get("fraction", {})
                for entry in native.get("fractions", [])
                if isinstance(entry, dict)
            }
            for entity in set(entities):
                count = counts_by_entity.get(entity, {})
                native_count = native_counts_by_entity.get(entity, {})
                fraction = fractions_by_entity.get(entity, {})
                if (
                    count.get("kind") == "fixed"
                    and native_count.get("kind") == "fixed"
                    and fraction.get("kind") == "fixed"
                    and native_count.get("value")
                ):
                    expected_fraction = count["value"] / native_count["value"]
                    if not math.isclose(
                        fraction.get("value", math.nan),
                        expected_fraction,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    ):
                        add(
                            f"{declaration['file']} {label}/{entity} native fraction "
                            "must equal count/native_count"
                        )
        validate_domain_semantics(
            add,
            representation.get("domain"),
            label=f"{declaration['file']} {label}",
        )

    for name, representation in summary.get("training", {}).items():
        validate_representation(f"training.{name}", representation)
    inference_summary = summary.get("inference", {})
    validate_representation("inference.surface_input", inference_summary.get("surface_input"))
    validate_representation("inference.volume_input", inference_summary.get("volume_input"))
    summary_inputs: dict[str, dict[str, Any]] = {}
    for input_name in ("surface_input", "volume_input"):
        representation = inference_summary.get(input_name, {})
        if not isinstance(representation, dict) or representation.get("used") is not True:
            continue
        case_record_id = representation.get("case_record_id")
        if not isinstance(case_record_id, str) or not case_record_id:
            add(
                f"{declaration['file']} inference.{input_name}.case_record_id "
                "is required when the input is used"
            )
            continue
        if case_record_id in summary_inputs:
            add(f"{declaration['file']} inference case-record input IDs must be unique")
        summary_inputs[case_record_id] = representation
    summary_direct_outputs = inference_summary.get("direct_outputs", [])
    summary_output_ids = [
        output.get("id") for output in summary_direct_outputs if isinstance(output, dict)
    ]
    if len(summary_output_ids) != len(set(summary_output_ids)):
        add(f"{declaration['file']} inference direct-output IDs must be unique")
    for output in summary_direct_outputs:
        if isinstance(output, dict):
            validate_representation(
                f"inference.direct_outputs[{output.get('id')}]",
                output.get("representation"),
            )
    summary_mappings = inference_summary.get("mappings", [])
    summary_mapping_supports = [
        mapping.get("support_id") for mapping in summary_mappings if isinstance(mapping, dict)
    ]
    if len(summary_mapping_supports) != len(set(summary_mapping_supports)):
        add(f"{declaration['file']} inference mapping support IDs must be unique")
    official_supports = {
        support.get("id"): support
        for support in (support_manifest or {}).get("supports", [])
        if isinstance(support, dict) and isinstance(support.get("id"), str)
    }
    for mapping in summary_mappings:
        if not isinstance(mapping, dict):
            continue
        support_id = mapping.get("support_id")
        source_output_id = mapping.get("source_output_id")
        official = official_supports.get(support_id)
        if official is None:
            add(f"{declaration['file']} mapping references unknown support_id {support_id!r}")
        elif mapping.get("extrapolation_policy") != official.get("extrapolation_policy"):
            add(
                f"{declaration['file']} mapping {support_id!r} extrapolation policy must "
                "match the official support"
            )
        if source_output_id not in summary_output_ids:
            add(
                f"{declaration['file']} mapping {support_id!r} source_output_id is not a "
                "declared direct output"
            )
        if mapping.get("unmapped_fraction") != 0:
            add(f"{declaration['file']} mapping {support_id!r} requires unmapped_fraction=0")
        if (
            mapping.get("extrapolation_policy") == "forbidden"
            and mapping.get("extrapolated_fraction") != 0
        ):
            add(f"{declaration['file']} mapping {support_id!r} forbids extrapolated values")
    missing_summary_mappings = sorted(set(official_supports) - set(summary_mapping_supports))
    if missing_summary_mappings:
        add(
            f"{declaration['file']} inference is missing mappings for official supports: "
            f"{missing_summary_mappings}"
        )

    case_manifest = summary.get("case_manifest", {})
    case_path = safe_submission_path(
        add,
        directory,
        case_manifest.get("file"),
        label="discretization case_manifest.file",
    )
    if case_path is None:
        return summary, []
    if not case_path.is_file():
        add(
            f"missing discretization case records: "
            f"{case_path.relative_to(ROOT) if case_path.is_relative_to(ROOT) else case_path}"
        )
        return summary, []
    if sha256_file(case_path) != case_manifest.get("sha256"):
        add("discretization case records do not match case_manifest.sha256")
    records = load_json_lines(add, case_path, label=case_manifest.get("file", "discretization cases"))
    official_support_ids = {
        support.get("id")
        for support in (support_manifest or {}).get("supports", [])
        if isinstance(support, dict) and isinstance(support.get("id"), str)
    }
    extrapolation_policies = {
        support.get("id"): support.get("extrapolation_policy")
        for support in (support_manifest or {}).get("supports", [])
        if isinstance(support, dict) and isinstance(support.get("id"), str)
    }
    expected_support_counts = {
        case.get("case_id"): {
            instance.get("support_id"): instance.get("entity_count")
            for instance in case.get("support_instances", [])
            if isinstance(instance, dict)
        }
        for case in (support_case_index or {}).get("_loaded_cases", [])
        if isinstance(case, dict)
    }
    for line_number, record in enumerate(records, start=1):
        for error in schema_errors(record, "discretization-case.schema.json", schema_version="v3"):
            add(f"{case_manifest.get('file')} line {line_number} {error}")
        record_identities = {
            "submission_id": submission["submission_id"],
            "dataset_id": submission["dataset_id"],
            "split_id": submission["split_id"],
        }
        for key, expected in record_identities.items():
            if record.get(key) != expected:
                add(f"{case_manifest.get('file')} line {line_number} {key} must equal {expected!r}")
        inference = record.get("inference", {})
        inputs = inference.get("inputs", [])
        direct_outputs = inference.get("direct_outputs", [])
        input_ids = [item.get("id") for item in inputs if isinstance(item, dict)]
        output_ids = [item.get("id") for item in direct_outputs if isinstance(item, dict)]
        if len(input_ids) != len(set(input_ids)):
            add(f"{case_manifest.get('file')} {record.get('case_id')} inference input IDs must be unique")
        if len(output_ids) != len(set(output_ids)):
            add(
                f"{case_manifest.get('file')} {record.get('case_id')} direct-output IDs must be unique"
            )
        if input_ids != list(summary_inputs):
            add(
                f"{case_manifest.get('file')} {record.get('case_id')} inference input IDs "
                "must exactly match the used summary inputs in declared order"
            )
        if output_ids != summary_output_ids:
            add(
                f"{case_manifest.get('file')} {record.get('case_id')} direct-output IDs "
                "must exactly match the summary outputs in declared order"
            )
        for item in [*inputs, *direct_outputs]:
            if not isinstance(item, dict):
                continue
            validate_domain_semantics(
                add,
                item.get("domain"),
                label=f"{case_manifest.get('file')} {record.get('case_id')}/{item.get('id')}",
            )
        case_mappings = inference.get("mappings", [])
        case_mapping_supports = [
            mapping.get("support_id")
            for mapping in case_mappings
            if isinstance(mapping, dict)
        ]
        if len(case_mapping_supports) != len(set(case_mapping_supports)):
            add(
                f"{case_manifest.get('file')} {record.get('case_id')} mapping "
                "support IDs must be unique"
            )
        if set(case_mapping_supports) != official_support_ids:
            add(
                f"{case_manifest.get('file')} {record.get('case_id')} mappings "
                "must cover exactly the official supports"
            )
        for mapping in case_mappings:
            if not isinstance(mapping, dict):
                continue
            label = f"{record.get('case_id')}/{mapping.get('support_id')}"
            support_id = mapping.get("support_id")
            if support_id not in official_support_ids:
                add(f"{case_manifest.get('file')} {label} references an unknown official support")
            if mapping.get("source_output_id") not in output_ids:
                add(f"{case_manifest.get('file')} {label} source_output_id is not a direct output")
            support_count = mapping.get("support_count")
            scored = mapping.get("scored_count")
            unmapped = mapping.get("unmapped_count")
            extrapolated = mapping.get("extrapolated_count")
            coverage = mapping.get("final_coverage_fraction")
            expected_count = expected_support_counts.get(record.get("case_id"), {}).get(support_id)
            if expected_count is not None and support_count != expected_count:
                add(f"{case_manifest.get('file')} {label} support_count must match the official case support")
            if scored != support_count:
                add(f"{case_manifest.get('file')} {label} scored_count must equal support_count")
            if unmapped != 0:
                add(f"{case_manifest.get('file')} {label} requires unmapped_count=0")
            if not is_number(coverage) or not math.isclose(coverage, 1.0, rel_tol=0.0, abs_tol=1e-12):
                add(f"{case_manifest.get('file')} {label} requires final_coverage_fraction=1.0")
            if isinstance(scored, int) and isinstance(unmapped, int) and scored < 0:
                add(f"{case_manifest.get('file')} {label} scored_count cannot be negative")
            if isinstance(extrapolated, int) and extrapolated < 0:
                add(f"{case_manifest.get('file')} {label} extrapolated_count cannot be negative")
            if extrapolation_policies.get(support_id) == "forbidden" and extrapolated != 0:
                add(f"{case_manifest.get('file')} {label} forbids extrapolated scoring values")

    case_ids = [record.get("case_id") for record in records]
    if case_manifest.get("case_count") != len(split_case_ids):
        add(f"discretization case_manifest.case_count must be {len(split_case_ids)} for this split")
    if len(records) != case_manifest.get("case_count"):
        add("discretization case record count does not match case_manifest.case_count")
    if case_ids != split_case_ids:
        missing = sorted(set(split_case_ids) - set(case_ids))
        unexpected = sorted(set(case_ids) - set(split_case_ids))
        add(
            "discretization case order differs from the benchmark split; "
            f"missing={missing[:5]}, unexpected={unexpected[:5]}"
        )

    def validate_case_representation_counts(
        representation_id: str,
        representation: dict[str, Any],
        *,
        collection: str,
        description: str,
    ) -> None:
        expected_entities = [
            entry.get("entity")
            for entry in representation.get("entity_counts", [])
            if isinstance(entry, dict)
        ]
        values_by_entity: dict[str, list[int]] = {
            entity: [] for entity in expected_entities if isinstance(entity, str)
        }
        native = representation.get("native_comparison", {})
        native_reported = native.get("status") == "reported"
        native_values_by_entity: dict[str, list[int]] = {
            entity: [] for entity in expected_entities if isinstance(entity, str)
        }
        fraction_values_by_entity: dict[str, list[float]] = {
            entity: [] for entity in expected_entities if isinstance(entity, str)
        }
        matched_cases = 0
        for record in records:
            matching = next(
                (
                    item
                    for item in record.get("inference", {}).get(collection, [])
                    if isinstance(item, dict) and item.get("id") == representation_id
                ),
                None,
            )
            if matching is None:
                continue
            matched_cases += 1
            observed_entities = [
                entry.get("entity")
                for entry in matching.get("entity_counts", [])
                if isinstance(entry, dict)
            ]
            if observed_entities != expected_entities:
                add(
                    f"{case_manifest.get('file')} {record.get('case_id')} "
                    f"{description} {representation_id!r} entity IDs must exactly "
                    "match the summary in declared order"
                )
            for entity in values_by_entity:
                matching_entity = next(
                    (
                        entry
                        for entry in matching.get("entity_counts", [])
                        if isinstance(entry, dict) and entry.get("entity") == entity
                    ),
                    None,
                )
                if isinstance(matching_entity, dict) and isinstance(
                    matching_entity.get("count"), int
                ):
                    values_by_entity[entity].append(matching_entity["count"])
            observed_native_entities = [
                entry.get("entity")
                for entry in matching.get("native_entity_counts", [])
                if isinstance(entry, dict)
            ]
            observed_fraction_entities = [
                entry.get("entity")
                for entry in matching.get("native_fractions", [])
                if isinstance(entry, dict)
            ]
            if not native_reported:
                if observed_native_entities or observed_fraction_entities:
                    add(
                        f"{case_manifest.get('file')} {record.get('case_id')} "
                        f"{description} {representation_id!r} native counts and fractions "
                        "must be omitted unless the summary reports a native comparison"
                    )
                continue
            if (
                observed_native_entities != expected_entities
                or observed_fraction_entities != expected_entities
            ):
                add(
                    f"{case_manifest.get('file')} {record.get('case_id')} "
                    f"{description} {representation_id!r} native entity and fraction IDs "
                    "must exactly match the summary in declared order"
                )
            for entity in native_values_by_entity:
                native_entry = next(
                    (
                        entry
                        for entry in matching.get("native_entity_counts", [])
                        if isinstance(entry, dict) and entry.get("entity") == entity
                    ),
                    None,
                )
                fraction_entry = next(
                    (
                        entry
                        for entry in matching.get("native_fractions", [])
                        if isinstance(entry, dict) and entry.get("entity") == entity
                    ),
                    None,
                )
                count_entry = next(
                    (
                        entry
                        for entry in matching.get("entity_counts", [])
                        if isinstance(entry, dict) and entry.get("entity") == entity
                    ),
                    None,
                )
                native_count = (
                    native_entry.get("count")
                    if isinstance(native_entry, dict)
                    else None
                )
                fraction = (
                    fraction_entry.get("fraction")
                    if isinstance(fraction_entry, dict)
                    else None
                )
                reported_count = (
                    count_entry.get("count")
                    if isinstance(count_entry, dict)
                    else None
                )
                if isinstance(native_count, int):
                    native_values_by_entity[entity].append(native_count)
                if is_number(fraction):
                    fraction_values_by_entity[entity].append(float(fraction))
                if (
                    isinstance(reported_count, int)
                    and isinstance(native_count, int)
                    and native_count > 0
                    and is_number(fraction)
                    and not math.isclose(
                        float(fraction),
                        reported_count / native_count,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                ):
                    add(
                        f"{case_manifest.get('file')} {record.get('case_id')} "
                        f"{description} {representation_id!r}/{entity!r} native fraction "
                        "must equal count/native_count"
                    )
        if matched_cases != len(records):
            add(
                f"{case_manifest.get('file')} {description} {representation_id!r} "
                "must be reported for every case"
            )

        def validate_summaries(
            entries: Any,
            *,
            value_key: str,
            observed: dict[str, list[int]] | dict[str, list[float]],
            value_label: str,
        ) -> None:
            for entity_entry in entries:
                if not isinstance(entity_entry, dict):
                    continue
                entity = entity_entry.get("entity")
                values = observed.get(entity, [])
                if len(values) != len(records):
                    add(
                        f"{case_manifest.get('file')} {description} "
                        f"{representation_id!r}/{entity!r} {value_label} "
                        "must be reported for every case"
                    )
                    continue
                value_summary = entity_entry.get(value_key, {})
                if value_summary.get("kind") == "fixed":
                    if any(
                        not math.isclose(
                            float(value),
                            float(value_summary.get("value", math.nan)),
                            rel_tol=0.0,
                            abs_tol=1e-12,
                        )
                        for value in values
                    ):
                        add(
                            f"{declaration['file']} {description} "
                            f"{representation_id!r}/{entity!r} fixed {value_label} "
                            "does not match case records"
                        )
                elif value_summary.get("kind") == "per_case":
                    calculated = {
                        "minimum": min(values),
                        "median": median(values),
                        "maximum": max(values),
                    }
                    if any(
                        not is_number(value_summary.get(key))
                        or not math.isclose(
                            float(value_summary[key]),
                            float(value),
                            rel_tol=0.0,
                            abs_tol=1e-12,
                        )
                        for key, value in calculated.items()
                    ):
                        add(
                            f"{declaration['file']} {description} "
                            f"{representation_id!r}/{entity!r} per-case {value_label} "
                            "summary does not match case records"
                        )

        validate_summaries(
            representation.get("entity_counts", []),
            value_key="count",
            observed=values_by_entity,
            value_label="count",
        )
        if native_reported:
            validate_summaries(
                native.get("native_entity_counts", []),
                value_key="count",
                observed=native_values_by_entity,
                value_label="native count",
            )
            validate_summaries(
                native.get("fractions", []),
                value_key="fraction",
                observed=fraction_values_by_entity,
                value_label="native fraction",
            )

    for input_id, representation in summary_inputs.items():
        validate_case_representation_counts(
            input_id,
            representation,
            collection="inputs",
            description="inference input",
        )
    for output in summary_direct_outputs:
        if not isinstance(output, dict):
            continue
        validate_case_representation_counts(
            output.get("id"),
            output.get("representation", {}),
            collection="direct_outputs",
            description="direct output",
        )
    return summary, records


def validate_v3_prediction_metadata(
    add: Any,
    directory: Path,
    submission: dict[str, Any],
    split_case_ids: list[str],
    *,
    contributor_stage: bool,
) -> dict[str, Any] | None:
    """Validate optional prediction declarations/checks without downloading artifacts."""

    artifacts = submission.get("prediction_artifacts", [])
    artifact_ids = [artifact.get("artifact_id") for artifact in artifacts if isinstance(artifact, dict)]
    if len(artifact_ids) != len(set(artifact_ids)):
        add("prediction_artifacts artifact_id values must be unique")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        label = f"prediction_artifacts[{artifact.get('artifact_id')!r}]"
        if artifact.get("support_release_id") != submission["scoring_support"]["release_id"]:
            add(f"{label}.support_release_id must match scoring_support.release_id")
        if artifact.get("support_manifest_sha256") != submission["scoring_support"]["manifest_sha256"]:
            add(f"{label}.support_manifest_sha256 must match scoring_support.manifest_sha256")
        if artifact.get("split_id") != submission["split_id"]:
            add(f"{label}.split_id must match submission split_id")
        coverage = artifact.get("coverage", {})
        if coverage.get("expected_case_count") != len(split_case_ids):
            add(f"{label}.coverage.expected_case_count must match the benchmark split")
        case_ids = coverage.get("case_ids")
        if case_ids is not None:
            expected_subset_order = [case_id for case_id in split_case_ids if case_id in set(case_ids)]
            if case_ids != expected_subset_order:
                add(f"{label}.coverage.case_ids must be a unique subset in benchmark split order")
            if coverage.get("case_count") != len(case_ids):
                add(f"{label}.coverage.case_count must equal the number of listed case_ids")
        if coverage.get("kind") == "complete_split":
            if coverage.get("case_count") != len(split_case_ids):
                add(f"{label} complete_split coverage must include every benchmark case")
            if case_ids is not None and case_ids != split_case_ids:
                add(f"{label} complete_split case_ids must match the exact benchmark split")

    checks_path = directory / "prediction-artifact-checks.json"
    if not checks_path.exists():
        return None
    if contributor_stage:
        add("contributors must not add prediction-artifact-checks.json")
        return None
    try:
        checks = load_json(checks_path)
    except (OSError, json.JSONDecodeError) as error:
        add(f"cannot read prediction-artifact-checks.json: {error}")
        return None
    for error in schema_errors(
        checks,
        "prediction-artifact-checks.schema.json",
        schema_version="v3",
    ):
        add(f"prediction-artifact-checks.json {error}")
    if checks.get("submission_id") != submission["submission_id"]:
        add("prediction-artifact-checks.json submission_id must match submission.json")
    declared_by_id = {
        artifact["artifact_id"]: artifact
        for artifact in artifacts
        if isinstance(artifact, dict) and isinstance(artifact.get("artifact_id"), str)
    }
    checked_ids: set[str] = set()
    for check in checks.get("checks", []):
        if not isinstance(check, dict):
            continue
        artifact_id = check.get("artifact_id")
        if artifact_id in checked_ids:
            add(f"prediction-artifact-checks.json contains duplicate artifact_id {artifact_id!r}")
        checked_ids.add(artifact_id)
        declared = declared_by_id.get(artifact_id)
        if declared is None:
            add(f"prediction-artifact-checks.json references undeclared artifact_id {artifact_id!r}")
            continue
        if check.get("repository_revision") != declared.get("revision"):
            add(f"prediction check {artifact_id!r} repository_revision must match the declaration")
        if check.get("manifest_sha256") != declared.get("manifest_sha256"):
            add(f"prediction check {artifact_id!r} manifest_sha256 must match the declaration")
        if check.get("expected_case_count") != len(split_case_ids):
            add(f"prediction check {artifact_id!r} expected_case_count must match the benchmark split")
        checked_case_count = check.get("checked_case_count")
        if isinstance(checked_case_count, int) and checked_case_count > len(split_case_ids):
            add(f"prediction check {artifact_id!r} checked_case_count exceeds the benchmark split")
        recomputed_case_count = check.get("recomputed_case_count")
        if (
            isinstance(recomputed_case_count, int)
            and isinstance(checked_case_count, int)
            and recomputed_case_count > checked_case_count
        ):
            add(
                f"prediction check {artifact_id!r} recomputed_case_count "
                "cannot exceed checked_case_count"
            )
        recomputation = check.get("metric_recomputation")
        status = check.get("status")
        if recomputation == "not_performed":
            if recomputed_case_count != 0:
                add(
                    f"prediction check {artifact_id!r} not_performed requires "
                    "recomputed_case_count=0"
                )
            if status == "metrics_recomputed":
                add(
                    f"prediction check {artifact_id!r} status metrics_recomputed "
                    "requires partial or performed metric_recomputation"
                )
        elif recomputation == "partial":
            if (
                not isinstance(recomputed_case_count, int)
                or not 0 < recomputed_case_count < len(split_case_ids)
            ):
                add(
                    f"prediction check {artifact_id!r} partial metric recomputation "
                    "requires 1..expected_case_count-1 recomputed cases"
                )
            if status != "metrics_recomputed":
                add(
                    f"prediction check {artifact_id!r} partial metric recomputation "
                    "requires status metrics_recomputed"
                )
        elif recomputation == "performed":
            if recomputed_case_count != len(split_case_ids):
                add(
                    f"prediction check {artifact_id!r} performed metric recomputation "
                    "requires the complete benchmark split"
                )
            if status != "metrics_recomputed":
                add(
                    f"prediction check {artifact_id!r} performed metric recomputation "
                    "requires status metrics_recomputed"
                )
            if declared.get("coverage", {}).get("kind") != "complete_split":
                add(
                    f"prediction check {artifact_id!r} performed metric recomputation "
                    "requires a complete_split prediction artifact"
                )
    return checks


def validate_evaluation_evidence(
    add: Any, directory: Path, submission: dict[str, Any]
) -> dict[str, Any] | None:
    evaluation = submission["evaluation"]
    filename = evaluation["evidence_file"]
    if Path(filename).name != filename:
        add("evaluation.evidence_file must be a filename in the submission directory")
        return None
    evidence_path = directory / filename
    if not evidence_path.is_file():
        display_path = evidence_path.relative_to(ROOT) if evidence_path.is_relative_to(ROOT) else evidence_path
        add(f"missing evaluation evidence: {display_path}")
        return None
    if sha256_file(evidence_path) != evaluation["evidence_sha256"]:
        add("evaluation-evidence.json does not match evaluation.evidence_sha256")
    try:
        evidence = load_json(evidence_path)
    except (OSError, json.JSONDecodeError) as error:
        add(f"cannot read evaluation evidence: {error}")
        return None
    evidence_schema_directory = {
        "1.0": "v1",
        "2.0": "v2",
        "3.0": "v3",
    }[submission["schema_version"]]
    for error in schema_errors(
        evidence,
        "evaluation-evidence.schema.json",
        schema_version=evidence_schema_directory,
    ):
        add(f"evaluation-evidence.json {error}")

    identities = {
        "submission_id": submission["submission_id"],
        "dataset_id": submission["dataset_id"],
        "split_id": submission["split_id"],
        "reference_version": evaluation["reference_version"],
        "command": evaluation["command"],
    }
    for key, expected in identities.items():
        if evidence.get(key) != expected:
            add(f"evaluation-evidence.json {key} must equal {expected!r}")
    if submission.get("schema_version") == "3.0":
        reproducibility = submission.get("reproducibility", {})
        structured_code = (
            reproducibility.get("code")
            if isinstance(reproducibility, dict)
            else None
        )
        if isinstance(structured_code, dict):
            expected_revision = structured_code.get("commit")
            if evidence.get("code_revision") != expected_revision:
                add(
                    "evaluation-evidence.json code_revision must equal the full "
                    "reproducibility.code.commit"
                )
        elif "code_revision" in evidence:
            add(
                "evaluation-evidence.json code_revision requires "
                "reproducibility.code"
            )
    elif evidence.get("code_revision") != evaluation["code_revision"]:
        add(
            "evaluation-evidence.json code_revision must equal "
            f"{evaluation['code_revision']!r}"
        )
    if submission.get("schema_version") in {"2.0", "3.0"}:
        open_track_identities = {
            "dataset_version": submission["dataset_version"],
            "split_sha256": submission["split_sha256"],
            "case_set_id": submission["case_set_id"],
            "profile_ground_truth_release_id": submission["profile_data"]["profile_ground_truth_release_id"],
            "profile_ground_truth_manifest_sha256": submission["profile_data"][
                "profile_ground_truth_manifest_sha256"
            ],
        }
        for key, expected in open_track_identities.items():
            if evidence.get(key) != expected:
                add(f"evaluation-evidence.json {key} must equal {expected!r}")
    if submission.get("schema_version") == "3.0":
        v3_bindings = {
            "scoring_support_release_id": submission["scoring_support"]["release_id"],
            "scoring_support_manifest_sha256": submission["scoring_support"]["manifest_sha256"],
            "discretization_sha256": submission["spatial_discretization"]["sha256"],
            "case_metrics_sha256": submission["case_metrics"]["sha256"],
        }
        for key, expected in v3_bindings.items():
            if evidence.get(key) != expected:
                add(f"evaluation-evidence.json {key} must equal {expected!r}")
    if evidence.get("metric_values") != submission.get("metric_values"):
        add("evaluation-evidence.json metric_values must exactly match submission.json")

    profile_index_path = directory / submission["profile_data"]["index_file"]
    if profile_index_path.is_file() and evidence.get("profile_index_sha256") != sha256_file(profile_index_path):
        add("evaluation-evidence.json profile_index_sha256 does not match profiles/index.json")
    return evidence


def validate_open_reproducibility(
    add: Any,
    directory: Path,
    submission: dict[str, Any],
    evidence: dict[str, Any] | None,
    manifest: dict[str, Any],
    dataset_spec: dict[str, Any],
    split_spec_entry: dict[str, Any],
    *,
    contributor_stage: bool,
) -> None:
    """Validate declared open artifacts and submitted data without executing a model."""

    if evidence is None:
        return
    evidence_status = evidence.get("status")
    approval = submission.get("approval")
    approval_status = approval.get("status") if isinstance(approval, dict) else None
    reproducibility = submission.get("reproducibility")
    submission_schema_version = submission.get("schema_version")
    if submission_schema_version in {"2.0", "3.0"} and (directory / "maintainer-replay.json").exists():
        add("maintainer-replay.json is not part of the open-reproducibility contract")

    if contributor_stage:
        if evidence_status != "submitted_evaluation":
            add("contributor-stage packages require evaluation-evidence.status=submitted_evaluation")
        if submission_schema_version != "3.0":
            add(
                "new contributor-stage submitted_evaluation packages require submission "
                "schema_version=3.0"
            )
        if approval is not None:
            add("contributors must leave approval absent; maintainers add it only after submitted-data validation")
        if (directory / "maintainer-validation.json").exists():
            add("contributors must not add maintainer-validation.json")

    if evidence_status == "prototype_dummy_data":
        if approval_status != "prototype":
            add("prototype_dummy_data evidence requires approval.status=prototype")
        if reproducibility is not None:
            add("prototype dummy data must not claim the open reproducibility contract")
        if submission.get("schema_version") != "1.0":
            add("prototype dummy data must use the historical submission schema_version=1.0")
        return

    if evidence_status != "submitted_evaluation":
        return

    if approval_status == "prototype":
        add("submitted_evaluation evidence cannot use approval.status=prototype")
    if submission_schema_version not in {"2.0", "3.0"}:
        add("real submitted data requires submission schema_version=2.0 or 3.0")
    if approval_status not in {None, "approved"}:
        add("a real contributor submission must remain unapproved until maintainer validation")
    if contributor_stage and approval_status == "approved":
        add("contributor-stage submissions cannot set approval.status=approved; maintainers add approval after validation")

    expected_contract = OPEN_REPRODUCIBILITY_CONTRACTS.get(submission_schema_version)
    if not isinstance(reproducibility, dict):
        add(
            f"submitted_evaluation evidence requires reproducibility.contract_version="
            f"{expected_contract!r}"
        )
        return

    if reproducibility.get("contract_version") != expected_contract:
        add(f"reproducibility.contract_version must be {expected_contract!r}")
    code = reproducibility.get("code")
    evaluation = submission.get("evaluation", {})
    if submission_schema_version == "3.0":
        if isinstance(code, dict):
            if submission.get("code_url") != code.get("repository_url"):
                add("code_url must equal reproducibility.code.repository_url")
            if evaluation.get("code_revision") != code.get("commit"):
                add(
                    "evaluation.code_revision must equal the full "
                    "reproducibility.code.commit"
                )
        else:
            if "code_url" in submission:
                add("code_url requires reproducibility.code")
            if "code_revision" in evaluation:
                add("evaluation.code_revision requires reproducibility.code")
    else:
        code_repository_url = (
            code.get("repository_url")
            if isinstance(code, dict)
            else None
        )
        code_commit = code.get("commit") if isinstance(code, dict) else None
        if submission.get("code_url") != code_repository_url:
            add("code_url must equal reproducibility.code.repository_url")
        if evaluation.get("code_revision") != code_commit:
            add(
                "evaluation.code_revision must equal the full "
                "reproducibility.code.commit"
            )
    if dataset_spec.get("status") != "official":
        add("submitted_evaluation evidence requires an official dataset specification")

    ground_truth = manifest.get("data_release", {}).get("profile_ground_truth", {})
    submitted_profile_ground_truth = submission.get("profile_data", {})
    if submitted_profile_ground_truth.get("profile_ground_truth_release_id") != ground_truth.get("release_id"):
        add("profile_data.profile_ground_truth_release_id must match the leaderboard manifest")
    if submitted_profile_ground_truth.get("profile_ground_truth_manifest_sha256") != ground_truth.get("manifest_sha256"):
        add("profile_data.profile_ground_truth_manifest_sha256 must match the leaderboard manifest")

    split_path = ROOT / "benchmark-specs" / submission["dataset_id"] / split_spec_entry["index_file"]
    if split_path.is_file():
        split_index = load_json(split_path)
        if split_index.get("case_id_status") != "official":
            add("submitted_evaluation evidence requires an official public split index")

    if approval_status != "approved":
        if (directory / "maintainer-validation.json").exists():
            add("maintainer-validation.json is only allowed with maintainer approval")
        return

    validation_metadata = approval.get("validation") if isinstance(approval, dict) else None
    if not isinstance(validation_metadata, dict):
        add("approval.status=approved requires approval.validation")
        return
    validation_filename = validation_metadata.get("evidence_file")
    if validation_filename != "maintainer-validation.json":
        add("approval.validation.evidence_file must be maintainer-validation.json")
        return
    validation_path = directory / validation_filename
    if not validation_path.is_file():
        add("approval.status=approved requires maintainer-validation.json")
        return
    if sha256_file(validation_path) != validation_metadata.get("evidence_sha256"):
        add("maintainer-validation.json does not match approval.validation.evidence_sha256")
    try:
        validation = load_json(validation_path)
    except (OSError, json.JSONDecodeError) as error:
        add(f"cannot read maintainer validation evidence: {error}")
        return
    for error in schema_errors(
        validation,
        "maintainer-validation.schema.json",
        schema_version="v3" if submission_schema_version == "3.0" else "v2",
    ):
        add(f"maintainer-validation.json {error}")

    for key in ("submission_id", "dataset_id", "split_id", "case_set_id"):
        if validation.get(key) != submission.get(key):
            add(f"maintainer-validation.json {key} must equal {submission.get(key)!r}")
    if validation.get("reference_version") != submission.get("evaluation", {}).get("reference_version"):
        add("maintainer-validation.json reference_version must match evaluation.reference_version")
    if validation.get("contract_version") != reproducibility.get("contract_version"):
        add("maintainer-validation.json contract_version must match reproducibility.contract_version")

    validation_ground_truth_fields = {
        "profile_ground_truth_release_id": "release_id",
        "profile_ground_truth_manifest_sha256": "manifest_sha256",
    }
    for validation_key, manifest_key in validation_ground_truth_fields.items():
        submitted_value = submitted_profile_ground_truth.get(validation_key)
        if validation.get(validation_key) != submitted_value:
            add(f"maintainer-validation.json {validation_key} must match submission profile_data")
        if validation.get(validation_key) != ground_truth.get(manifest_key):
            add(f"maintainer-validation.json {validation_key} must match the leaderboard manifest")

    try:
        submitted_date = date.fromisoformat(submission["submitted_at"])
        validation_date = datetime.fromisoformat(str(validation["validated_at"]).replace("Z", "+00:00")).date()
        approved_date = date.fromisoformat(approval["approved_at"])
        if not submitted_date <= validation_date <= approved_date:
            add("submission, maintainer validation, and approval dates must be chronological")
    except (KeyError, TypeError, ValueError):
        pass  # JSON Schema reports malformed or missing date values.

    reviewed_submission = dict(submission)
    reviewed_submission.pop("approval", None)
    if validation.get("reviewed_submission_sha256") != canonical_json_sha256(reviewed_submission):
        add("maintainer-validation.json reviewed_submission_sha256 does not match submission metadata")

    if validation.get("evaluation_evidence_sha256") != submission.get("evaluation", {}).get("evidence_sha256"):
        add("maintainer-validation.json evaluation_evidence_sha256 does not match submission metadata")

    profile_index_path = directory / submission["profile_data"]["index_file"]
    if profile_index_path.is_file():
        if validation.get("profile_index_sha256") != sha256_file(profile_index_path):
            add("maintainer-validation.json profile_index_sha256 does not match the submitted profile index")
    if submission_schema_version == "3.0":
        validation_v3_bindings = {
            "scoring_support_release_id": submission["scoring_support"]["release_id"],
            "scoring_support_manifest_sha256": submission["scoring_support"]["manifest_sha256"],
            "discretization_sha256": submission["spatial_discretization"]["sha256"],
            "case_metrics_sha256": submission["case_metrics"]["sha256"],
        }
        for key, expected in validation_v3_bindings.items():
            if validation.get(key) != expected:
                add(f"maintainer-validation.json {key} must match submission metadata")


def validate_profiles(
    add: Any,
    directory: Path,
    submission: dict[str, Any],
    dataset_spec: dict[str, Any],
    split_spec_entry: dict[str, Any],
) -> dict[str, int]:
    index_path = directory / submission["profile_data"]["index_file"]
    if not index_path.is_file():
        add(f"missing profile index: {index_path.relative_to(ROOT)}")
        return {"cases": 0, "series": 0}
    try:
        index = load_json(index_path)
    except (OSError, json.JSONDecodeError) as error:
        add(f"cannot read profile index: {error}")
        return {"cases": 0, "series": 0}
    for error in schema_errors(index, "profile-index.schema.json"):
        add(f"profiles/index.json {error}")

    identities = {
        "submission_id": submission["submission_id"],
        "dataset_id": submission["dataset_id"],
        "split_id": submission["split_id"],
        "case_set_id": submission["case_set_id"],
        "case_count": submission["profile_data"]["case_count"],
    }
    for key, expected in identities.items():
        if index.get(key) != expected:
            add(f"profiles/index.json {key} must equal {expected!r}")

    split_path = ROOT / "benchmark-specs" / submission["dataset_id"] / split_spec_entry["index_file"]
    if not split_path.is_file():
        add(f"missing benchmark split index: {split_path.relative_to(ROOT)}")
        return {"cases": 0, "series": 0}
    split_index = load_json(split_path)
    if sha256_file(split_path) != split_spec_entry["sha256"]:
        add("benchmark split index does not match submission-spec.json sha256")
    if split_index.get("dataset_id") != submission["dataset_id"]:
        add("benchmark split index dataset_id does not match submission.json")
    if split_index.get("split_id") != submission["split_id"]:
        add("benchmark split index split_id does not match submission.json")
    if split_index.get("case_set_id") != split_spec_entry.get("case_set_id"):
        add("benchmark split index case_set_id does not match submission-spec.json")
    if split_index.get("case_id_status") != split_spec_entry.get("case_id_status"):
        add("benchmark split index case_id_status does not match submission-spec.json")
    if split_index.get("case_count") != split_spec_entry.get("case_count"):
        add("benchmark split index case_count does not match submission-spec.json")
    if submission.get("split_sha256") != split_spec_entry["sha256"]:
        add("split_sha256 does not match the benchmark split index")
    expected_case_ids = split_index["case_ids"]
    if submission["profile_data"]["case_count"] != len(expected_case_ids):
        add(f"profile_data.case_count must be {len(expected_case_ids)} for this split")
    if submission["profile_data"].get("case_set_id") != split_index.get("case_set_id"):
        add("profile_data.case_set_id does not match the benchmark split index")
    if submission.get("case_set_id") != split_index.get("case_set_id"):
        add("case_set_id does not match the benchmark split index")
    if submission["profile_data"].get("case_set_id") != submission.get("case_set_id"):
        add("profile_data.case_set_id must equal submission case_set_id")

    panels = {panel["id"]: panel for panel in dataset_spec["profile_panels"]}
    indexed_case_ids: list[str] = []
    loaded_case_ids: list[str] = []
    series_count = 0
    referenced_files: set[str] = set()
    for chunk_entry in index.get("chunks", []):
        filename = chunk_entry.get("file", "")
        if not filename or Path(filename).name != filename:
            add(f"invalid profile chunk filename: {filename!r}")
            continue
        if filename in referenced_files:
            add(f"profile index references {filename} more than once")
            continue
        referenced_files.add(filename)
        indexed_case_ids.extend(chunk_entry.get("case_ids", []))
        chunk_path = index_path.parent / filename
        if not chunk_path.is_file():
            add(f"missing profile chunk: {chunk_path.relative_to(ROOT)}")
            continue
        if sha256_file(chunk_path) != chunk_entry.get("sha256"):
            add(f"{filename} does not match its index sha256")
        try:
            chunk = load_json(chunk_path)
        except (OSError, json.JSONDecodeError) as error:
            add(f"cannot read {filename}: {error}")
            continue
        for error in schema_errors(chunk, "profile-chunk.schema.json"):
            add(f"profiles/{filename} {error}")
        chunk_case_ids = [case.get("case_id") for case in chunk.get("cases", []) if isinstance(case, dict)]
        if chunk_case_ids != chunk_entry.get("case_ids"):
            add(f"{filename} case order does not match profiles/index.json")
        loaded_case_ids.extend(chunk_case_ids)

        for case in chunk.get("cases", []):
            if not isinstance(case, dict):
                continue
            provided: list[tuple[str, str, str]] = []
            for series in case.get("series", []):
                if not isinstance(series, dict):
                    continue
                panel_id = series.get("panel_id")
                panel = panels.get(panel_id)
                station_id = series.get("station_id")
                quantity_id = series.get("quantity_id")
                key = (panel_id, station_id, quantity_id)
                if key in provided:
                    add(f"{case.get('case_id')} contains duplicate series {key}")
                provided.append(key)
                if panel is None:
                    add(f"{case.get('case_id')} has unknown panel_id {panel_id!r}")
                    continue
                if station_id not in panel["station_ids"]:
                    add(f"{case.get('case_id')}/{panel_id} has unknown station_id {station_id!r}")
                if quantity_id not in panel["quantity_ids"]:
                    add(f"{case.get('case_id')}/{panel_id} has unknown quantity_id {quantity_id!r}")
                coordinates = series.get("coordinate", [])
                predictions = series.get("prediction", [])
                if not isinstance(coordinates, list) or not isinstance(predictions, list):
                    add(f"{case.get('case_id')}/{panel_id}/{station_id}/{quantity_id} arrays must be JSON lists")
                    continue
                if len(coordinates) != len(predictions):
                    add(f"{case.get('case_id')}/{panel_id}/{station_id}/{quantity_id} coordinate and prediction lengths differ")
                if len(coordinates) < panel.get("minimum_points", 2):
                    add(f"{case.get('case_id')}/{panel_id}/{station_id}/{quantity_id} has too few points")
                if any(not is_number(value) for value in coordinates):
                    add(f"{case.get('case_id')}/{panel_id}/{station_id}/{quantity_id} coordinates must be finite numbers")
                elif any(right <= left for left, right in zip(coordinates, coordinates[1:])):
                    add(f"{case.get('case_id')}/{panel_id}/{station_id}/{quantity_id} coordinates must be strictly increasing")
                if any(not is_number(value) for value in predictions):
                    add(f"{case.get('case_id')}/{panel_id}/{station_id}/{quantity_id} predictions must be finite numbers")
                series_count += 1
            provided_set = set(provided)
            for panel_id, panel in panels.items():
                if not panel.get("required", True):
                    continue
                expected = {
                    (panel_id, station_id, quantity_id)
                    for station_id in panel["station_ids"]
                    for quantity_id in panel["quantity_ids"]
                }
                missing = sorted(expected - provided_set)
                if missing:
                    add(f"{case.get('case_id')} is missing required profile series: {missing}")

    if indexed_case_ids != expected_case_ids:
        missing = sorted(set(expected_case_ids) - set(indexed_case_ids))
        unexpected = sorted(set(indexed_case_ids) - set(expected_case_ids))
        add(f"profile index case coverage differs from the benchmark split; missing={missing[:5]}, unexpected={unexpected[:5]}")
    if loaded_case_ids != indexed_case_ids:
        add("loaded profile chunk cases do not match the profile index")
    actual_chunk_files = {path.name for path in index_path.parent.glob("chunk-*.json")}
    if actual_chunk_files != referenced_files:
        add(f"profile directory contains unindexed chunks: {sorted(actual_chunk_files - referenced_files)}")
    return {"cases": len(loaded_case_ids), "series": series_count}


def validate_submission_file(
    path: Path,
    manifest: dict[str, Any] | None = None,
    *,
    contributor_stage: bool = False,
) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    stats = {"cases": 0, "series": 0}
    prefix = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)

    def add(message: str) -> None:
        errors.append(f"{prefix}: {message}")

    try:
        submission = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        add(f"cannot read submission JSON: {error}")
        return errors, stats
    submission_schema_version = submission.get("schema_version")
    schema_directory = {"1.0": "v1", "2.0": "v2", "3.0": "v3"}.get(submission_schema_version)
    if schema_directory is None:
        add("schema_version must be '1.0', '2.0', or '3.0'")
        return errors, stats
    for error in schema_errors(
        submission,
        "submission.schema.json",
        schema_version=schema_directory,
    ):
        add(error)
    if errors:
        return errors, stats

    if manifest is None:
        manifest = manifest_with_benchmark_contract(load_json(MANIFEST_PATH))
    dataset = next((item for item in manifest["datasets"] if item["slug"] == submission["dataset_id"]), None)
    if dataset is None:
        add(f"unknown dataset_id {submission['dataset_id']!r}")
        return errors, stats
    split = split_entry(dataset, submission["split_id"])
    if split is None:
        add(f"unknown split_id {submission['split_id']!r} for {dataset['name']}")
        return errors, stats
    spec_path = ROOT / "benchmark-specs" / dataset["slug"] / "submission-spec.json"
    if not spec_path.is_file():
        add(f"missing benchmark specification: {spec_path.relative_to(ROOT)}")
        return errors, stats
    dataset_spec = load_json(spec_path)
    if dataset_spec.get("dataset_id") != submission["dataset_id"]:
        add("benchmark specification dataset_id does not match submission.json")
        return errors, stats
    if dataset_spec.get("ranking") != dataset.get("ranking"):
        add("benchmark specification ranking policy does not match the leaderboard manifest")
    spec_split = next((item for item in dataset_spec["splits"] if item["id"] == split["id"]), None)
    if spec_split is None:
        add(f"benchmark specification does not define split {split['id']!r}")
        return errors, stats

    validate_metadata(add, path, submission, dataset, split)
    if submission.get("dataset_version") != dataset_spec.get("dataset_version"):
        add(f"dataset_version must equal {dataset_spec.get('dataset_version')!r} from the benchmark specification")
    if submission.get("evaluation", {}).get("reference_version") != dataset_spec.get("evaluation_reference_version"):
        add(
            "evaluation.reference_version must equal the evaluator release declared by the benchmark specification"
        )
    validate_metrics(add, submission, dataset, manifest)
    if submission_schema_version == "3.0":
        split_path = ROOT / "benchmark-specs" / submission["dataset_id"] / spec_split["index_file"]
        split_case_ids: list[str] = []
        if split_path.is_file():
            try:
                split_index = load_json(split_path)
            except (OSError, json.JSONDecodeError) as error:
                add(f"cannot read benchmark split index for schema v3 evidence: {error}")
            else:
                split_case_ids = split_index.get("case_ids", [])
                if not isinstance(split_case_ids, list) or any(
                    not isinstance(case_id, str) for case_id in split_case_ids
                ):
                    add("benchmark split index case_ids must be a string array")
                    split_case_ids = []
        support_manifest, support_case_index = validate_v3_scoring_support(
            add,
            submission,
            dataset_spec,
            spec_split,
        )
        validate_v3_case_metrics(
            add,
            path.parent,
            submission,
            split_case_ids,
            support_manifest,
            support_case_index,
        )
        validate_v3_discretization(
            add,
            path.parent,
            submission,
            split_case_ids,
            support_manifest,
            support_case_index,
        )
        validate_v3_prediction_metadata(
            add,
            path.parent,
            submission,
            split_case_ids,
            contributor_stage=contributor_stage,
        )
    evidence = validate_evaluation_evidence(add, path.parent, submission)
    validate_open_reproducibility(
        add,
        path.parent,
        submission,
        evidence,
        manifest,
        dataset_spec,
        spec_split,
        contributor_stage=contributor_stage,
    )
    stats = validate_profiles(add, path.parent, submission, dataset_spec, spec_split)
    return errors, stats


def validate_many(
    paths: list[Path] | None = None,
    *,
    contributor_stage: bool = False,
    manifest: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, int]]:
    files = submission_files(paths)
    if not files:
        return ["no submission.json files found"], {"submissions": 0, "cases": 0, "series": 0}
    manifest = manifest_with_benchmark_contract(manifest or load_json(MANIFEST_PATH))
    errors: list[str] = []
    totals = {"submissions": len(files), "cases": 0, "series": 0}
    seen_ids: dict[str, Path] = {}
    for path in files:
        current_errors, stats = validate_submission_file(path, manifest, contributor_stage=contributor_stage)
        errors.extend(current_errors)
        totals["cases"] += stats["cases"]
        totals["series"] += stats["series"]
        try:
            submission_id = load_json(path).get("submission_id")
        except (OSError, json.JSONDecodeError):
            continue
        if submission_id in seen_ids:
            errors.append(f"{path.relative_to(ROOT)}: duplicate submission_id also used by {seen_ids[submission_id].relative_to(ROOT)}")
        elif submission_id:
            seen_ids[submission_id] = path
    return errors, totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="submission directories or submission.json files")
    parser.add_argument(
        "--contributor-stage",
        action="store_true",
        help="reject maintainer approval/validation metadata in contributor-authored packages",
    )
    parser.add_argument(
        "--prediction-check",
        choices=("metadata",),
        help=(
            "validate optional prediction-artifact declarations/check records without downloading "
            "remote artifacts"
        ),
    )
    args = parser.parse_args()
    errors, totals = validate_many(args.paths or None, contributor_stage=args.contributor_stage)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"Validation failed with {len(errors)} error(s).", file=sys.stderr)
        return 1
    message = (
        f"PASS {totals['submissions']} submission(s), {totals['cases']} test cases, "
        f"and {totals['series']} profile series."
    )
    if args.prediction_check == "metadata":
        message += " Prediction-artifact metadata checked; no remote artifacts were downloaded."
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
