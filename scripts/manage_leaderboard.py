#!/usr/bin/env python3
"""Validate source submissions and build compact public leaderboard feeds."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

if __package__:
    from .validate_submission import load_json, sha256_file, submission_files, validate_many
else:
    from validate_submission import load_json, sha256_file, submission_files, validate_many


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "leaderboard" / "manifest.json"


def release_contract_errors(manifest: dict[str, Any]) -> list[str]:
    """Return release-level provenance errors that must block an official feed."""

    release = manifest.get("data_release", {})
    errors: list[str] = []
    if release.get("status") not in {"prototype_dummy_data", "official"}:
        errors.append("leaderboard/manifest.json data_release.status must be prototype_dummy_data or official")
    if release.get("reproducibility_contract_version") != "open-reproducibility-1.0":
        errors.append(
            "leaderboard/manifest.json data_release.reproducibility_contract_version must be "
            "open-reproducibility-1.0"
        )
    license_metadata = release.get("license")
    if not isinstance(license_metadata, dict) or any(
        not isinstance(license_metadata.get(key), str) or not license_metadata[key].strip()
        for key in ("spdx_id", "name", "url", "scope")
    ):
        errors.append("leaderboard/manifest.json data_release.license must define spdx_id, name, url, and scope")
    archive_url = release.get("archive_url")
    if release.get("status") != "prototype_dummy_data" and (
        not isinstance(archive_url, str) or not archive_url.startswith("https://")
    ):
        errors.append("an official data release requires an immutable HTTPS data_release.archive_url")
    source_commit = release.get("source_commit")
    if release.get("status") == "official" and not (
        isinstance(source_commit, str) and re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", source_commit)
    ):
        errors.append("an official data release requires a full immutable data_release.source_commit")
    asset_base_url = release.get("asset_base_url")
    if not isinstance(asset_base_url, str) or not asset_base_url.startswith("https://"):
        errors.append("leaderboard/manifest.json data_release.asset_base_url must be an HTTPS URL")
    elif release.get("status") == "official" and source_commit not in asset_base_url:
        errors.append("an official data_release.asset_base_url must contain the immutable source_commit")
    profile_ground_truth = release.get("profile_ground_truth")
    if not isinstance(profile_ground_truth, dict) or any(
        not isinstance(profile_ground_truth.get(key), str) or not profile_ground_truth[key].strip()
        for key in ("release_id", "manifest_url", "manifest_sha256")
    ):
        errors.append(
            "leaderboard/manifest.json data_release.profile_ground_truth must define release_id, manifest_url, and manifest_sha256"
        )
    elif not profile_ground_truth["manifest_url"].startswith("https://") or not re.fullmatch(
        r"[a-f0-9]{64}", profile_ground_truth["manifest_sha256"]
    ):
        errors.append("data_release.profile_ground_truth requires an HTTPS manifest_url and lowercase SHA-256 digest")
    if archive_url is not None and (not isinstance(archive_url, str) or not archive_url.startswith("https://")):
        errors.append("data_release.archive_url must be null or an HTTPS URL")
    return errors


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def json_bytes(value: Any) -> bytes:
    return f"{json.dumps(value, indent=2, ensure_ascii=True)}\n".encode()


def source_rows_by_dataset(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows = {dataset["name"]: [] for dataset in manifest["datasets"]}
    release_status = manifest.get("data_release", {}).get("status")
    allowed_approval_status = "prototype" if release_status == "prototype_dummy_data" else "approved"
    for path in submission_files():
        submission = load_json(path)
        if submission.get("approval", {}).get("status") != allowed_approval_status:
            continue
        row = deepcopy(submission)
        row.pop("$schema", None)
        row["parameter_count"] = row.get("parameter_count_millions")
        row["profile_data"]["index_file"] = str(
            (path.parent / row["profile_data"]["index_file"]).relative_to(ROOT)
        )
        profile_index_path = ROOT / row["profile_data"]["index_file"]
        if profile_index_path.is_file():
            row["profile_data"]["index_sha256"] = sha256_file(profile_index_path)
        if allowed_approval_status == "approved":
            replay_metadata = submission["approval"]["replay"]
            replay_path = path.parent / replay_metadata["evidence_file"]
            replay = load_json(replay_path)
            row["maintainer_replay"] = {
                "status": replay["status"],
                "contract_version": replay["contract_version"],
                "reference_version": replay["reference_version"],
                "replayed_by": replay["replayed_by"],
                "replayed_at": replay["replayed_at"],
                "metric_abs_tolerance": replay["metric_abs_tolerance"],
                "reviewed_submission_sha256": replay["reviewed_submission_sha256"],
                "submitted_profile_index_sha256": replay["submitted_profile_index_sha256"],
                "replayed_profile_index_sha256": replay["replayed_profile_index_sha256"],
                "independence": replay["independence"],
                "evidence_file": str(replay_path.relative_to(ROOT)),
                "evidence_sha256": replay_metadata["evidence_sha256"],
            }
        rows[submission["dataset"]].append(row)
    return rows


def latest_submission_date(rows: list[dict[str, Any]]) -> str:
    valid_dates = []
    for row in rows:
        try:
            valid_dates.append(date.fromisoformat(row.get("submitted_at", "")).isoformat())
        except ValueError:
            continue
    return max(valid_dates, default=date.today().isoformat())


def expected_outputs(
    manifest: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    updated_manifest = deepcopy(manifest)
    rows_by_dataset = source_rows_by_dataset(updated_manifest)
    all_rows: list[dict[str, Any]] = []
    latest_dates: list[str] = []
    for dataset in updated_manifest["datasets"]:
        rows = rows_by_dataset[dataset["name"]]
        latest = latest_submission_date(rows)
        dataset["submission_count"] = len(rows)
        dataset["updated_at"] = latest
        latest_dates.append(latest)
        all_rows.extend(rows)
    latest_global = max(latest_dates, default=date.today().isoformat())
    updated_manifest["generated_at"] = generated_at or manifest.get("generated_at") or f"{latest_global}T00:00:00Z"
    updated_manifest["submission_schema_version"] = "1.0"
    release = updated_manifest.setdefault("data_release", {})
    release["generated_at"] = updated_manifest["generated_at"]
    feed_sha256 = hashlib.sha256(json_bytes(all_rows)).hexdigest()
    if release.get("status") == "prototype_dummy_data":
        release["id"] = f"prototype-dev-{latest_global}-{feed_sha256[:12]}"
    release["feed_sha256"] = feed_sha256
    return updated_manifest, rows_by_dataset, all_rows


def build(manifest: dict[str, Any]) -> None:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    updated_manifest, rows_by_dataset, all_rows = expected_outputs(manifest, generated_at=generated_at)
    for dataset in updated_manifest["datasets"]:
        write_json(ROOT / dataset["file"], rows_by_dataset[dataset["name"]])
    write_json(ROOT / updated_manifest["all_file"], all_rows)
    write_json(ROOT / "leaderboard.json", all_rows)
    write_json(MANIFEST_PATH, updated_manifest)


def check_generated_feeds(manifest: dict[str, Any]) -> list[str]:
    expected_manifest, rows_by_dataset, all_rows = expected_outputs(manifest)
    errors = []
    for dataset in expected_manifest["datasets"]:
        path = ROOT / dataset["file"]
        if not path.exists() or load_json(path) != rows_by_dataset[dataset["name"]]:
            errors.append(f"{path.relative_to(ROOT)} is not synchronized with source submissions")
    for path_value in (expected_manifest["all_file"], "leaderboard.json"):
        path = ROOT / path_value
        if not path.exists() or load_json(path) != all_rows:
            errors.append(f"{path.relative_to(ROOT)} is not synchronized with source submissions")
    for key in (
        "schema_version",
        "submission_schema_version",
        "generated_at",
        "data_release",
        "metric_catalog",
        "metric_definitions",
        "training_regimes",
        "datasets",
    ):
        if manifest.get(key) != expected_manifest.get(key):
            errors.append(f"leaderboard/manifest.json has stale {key}")
    return errors


def print_errors(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate submission directories")
    validate_parser.add_argument("paths", nargs="*", type=Path)
    subparsers.add_parser("build", help="validate and regenerate all leaderboard feeds")
    subparsers.add_parser("check", help="validate submissions and verify generated feeds")
    args = parser.parse_args()

    paths = getattr(args, "paths", None) or None
    errors, totals = validate_many(paths)
    if errors:
        return print_errors(errors)
    manifest = load_json(MANIFEST_PATH)
    errors = release_contract_errors(manifest)
    if errors:
        return print_errors(errors)
    if args.command == "build":
        build(manifest)
        print(f"Built compact leaderboard feeds from {totals['submissions']} validated submissions.")
    elif args.command == "check":
        errors = check_generated_feeds(manifest)
        if errors:
            return print_errors(errors)
        print(
            f"Validated {totals['submissions']} submissions, {totals['cases']} cases, and "
            f"{totals['series']} profile series; generated feeds are synchronized."
        )
    else:
        print(
            f"Validated {totals['submissions']} submissions, {totals['cases']} cases, and "
            f"{totals['series']} profile series."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
