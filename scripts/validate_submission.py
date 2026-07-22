#!/usr/bin/env python3
"""Validate FluidsBench submission metadata and profile chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference.scores import LEGACY_ERROR_WEIGHTS, legacy_aero_scores

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover - exercised by the command's dependency check
    Draft202012Validator = None
    FormatChecker = None


MANIFEST_PATH = ROOT / "leaderboard" / "manifest.json"
SCHEMA_ROOT = ROOT / "schemas"
OPEN_REPRODUCIBILITY_CONTRACT = "open-reproducibility-2.0"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


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

    if dataset.get("submission_format") == "legacy_external_aero" and all(
        is_number(values.get(metric_id))
        for metric_id in set(LEGACY_ERROR_WEIGHTS) | {"cd_r2", "cl_r2", "velocity_profile_r2", "cp_cut_r2"}
    ):
        for metric_id, expected in legacy_aero_scores(values).items():
            if not is_number(values.get(metric_id)) or not math.isclose(
                values[metric_id], expected, rel_tol=0.0, abs_tol=1e-6
            ):
                add(f"metric_values.{metric_id} does not match its declared score equation")


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
    evidence_schema_directory = "v2" if submission.get("schema_version") == "2.0" else "v1"
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
        "code_revision": evaluation["code_revision"],
        "command": evaluation["command"],
    }
    for key, expected in identities.items():
        if evidence.get(key) != expected:
            add(f"evaluation-evidence.json {key} must equal {expected!r}")
    if submission.get("schema_version") == "2.0":
        v2_identities = {
            "dataset_version": submission["dataset_version"],
            "split_sha256": submission["split_sha256"],
            "case_set_id": submission["case_set_id"],
            "profile_ground_truth_release_id": submission["profile_data"]["profile_ground_truth_release_id"],
            "profile_ground_truth_manifest_sha256": submission["profile_data"][
                "profile_ground_truth_manifest_sha256"
            ],
        }
        for key, expected in v2_identities.items():
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
    """Enforce open artifacts and submitted-data validation without executing a model."""

    if evidence is None:
        return
    evidence_status = evidence.get("status")
    approval = submission.get("approval")
    approval_status = approval.get("status") if isinstance(approval, dict) else None
    reproducibility = submission.get("reproducibility")
    if submission.get("schema_version") == "2.0" and (directory / "maintainer-replay.json").exists():
        add("maintainer-replay.json is not part of the open-reproducibility-2.0 contract")

    if contributor_stage:
        if evidence_status != "submitted_evaluation":
            add("contributor-stage packages require evaluation-evidence.status=submitted_evaluation")
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
    if submission.get("schema_version") != "2.0":
        add("real submitted data requires submission schema_version=2.0")
    if approval_status not in {None, "approved"}:
        add("a real contributor submission must remain unapproved until maintainer validation")
    if contributor_stage and approval_status == "approved":
        add("contributor-stage submissions cannot set approval.status=approved; maintainers add approval after validation")

    if not isinstance(reproducibility, dict):
        add(
            f"submitted_evaluation evidence requires reproducibility.contract_version="
            f"{OPEN_REPRODUCIBILITY_CONTRACT!r}"
        )
        return

    if reproducibility.get("contract_version") != OPEN_REPRODUCIBILITY_CONTRACT:
        add(f"reproducibility.contract_version must be {OPEN_REPRODUCIBILITY_CONTRACT!r}")
    code = reproducibility.get("code", {})
    code_repository_url = code.get("repository_url") if isinstance(code, dict) else None
    code_commit = code.get("commit") if isinstance(code, dict) else None
    if submission.get("code_url") != code_repository_url:
        add("code_url must equal reproducibility.code.repository_url")
    if submission.get("evaluation", {}).get("code_revision") != code_commit:
        add("evaluation.code_revision must equal the full reproducibility.code.commit")
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
        schema_version="v2",
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
    schema_directory = {"1.0": "v1", "2.0": "v2"}.get(submission_schema_version)
    if schema_directory is None:
        add("schema_version must be '1.0' for historical prototypes or '2.0' for real submissions")
        return errors, stats
    for error in schema_errors(
        submission,
        "submission.schema.json",
        schema_version=schema_directory,
    ):
        add(error)
    if errors:
        return errors, stats

    manifest = manifest or load_json(MANIFEST_PATH)
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
) -> tuple[list[str], dict[str, int]]:
    files = submission_files(paths)
    if not files:
        return ["no submission.json files found"], {"submissions": 0, "cases": 0, "series": 0}
    manifest = load_json(MANIFEST_PATH)
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
    args = parser.parse_args()
    errors, totals = validate_many(args.paths or None, contributor_stage=args.contributor_stage)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"Validation failed with {len(errors)} error(s).", file=sys.stderr)
        return 1
    print(
        f"PASS {totals['submissions']} submission(s), {totals['cases']} test cases, "
        f"and {totals['series']} profile series."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
