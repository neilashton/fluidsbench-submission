"""Exact bindings for closed HiLiftAeroML genuine-inference reference packages.

This module deliberately does not decide whether a result is scientifically
valid or official.  It provides the small deterministic primitives used by
the maintainer-only dev registration path: an explicit inference attestation,
checkpoint identities, artifact hashes, and a logical hash of every file in a
candidate package.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "hiliftaeroml-pre-release-reference-registry-v1"
REGISTRY_STATUS = "closed_candidate_dev_only"
TREE_HASH_ALGORITHM = "sha256-posix-path-size-content-sha256-v1"
GENUINE_INFERENCE_ATTESTATION = (
    "Participant attests that every submitted prediction value was produced "
    "by actual model inference for the declared checkpoint(s), not generated "
    "from HiLiftAeroML evaluation ground truth. The assembler verified the local "
    "checkpoint bytes against the methodology SHA-256 declarations."
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class HiLiftAeroMLPreReleaseError(ValueError):
    """Raised when a package cannot receive an exact dev-only binding."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise HiLiftAeroMLPreReleaseError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_nonfinite(token: str) -> None:
    raise HiLiftAeroMLPreReleaseError(f"non-finite JSON value {token!r}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HiLiftAeroMLPreReleaseError(
            f"cannot read {label} {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise HiLiftAeroMLPreReleaseError(f"{label} must contain a JSON object")
    return value


def _safe_file(directory: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise HiLiftAeroMLPreReleaseError(f"{label} must be a non-empty relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise HiLiftAeroMLPreReleaseError(f"{label} must stay inside the package")
    path = directory / relative
    try:
        path.resolve().relative_to(directory.resolve())
    except (OSError, ValueError) as error:
        raise HiLiftAeroMLPreReleaseError(
            f"{label} must stay inside the package"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise HiLiftAeroMLPreReleaseError(f"{label} is not a retained regular file")
    return path


def checkpoint_sha256s(methodology: object) -> list[str]:
    """Return the sorted unique checkpoint digests from a method record."""

    if not isinstance(methodology, Mapping):
        raise HiLiftAeroMLPreReleaseError("methodology must be an object")
    checkpoints = methodology.get("checkpoints")
    if not isinstance(checkpoints, list) or not checkpoints:
        raise HiLiftAeroMLPreReleaseError(
            "methodology must declare at least one checkpoint"
        )
    values: list[str] = []
    for index, checkpoint in enumerate(checkpoints):
        digest = checkpoint.get("sha256") if isinstance(checkpoint, Mapping) else None
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise HiLiftAeroMLPreReleaseError(
                f"methodology checkpoint {index} has no lowercase SHA-256"
            )
        values.append(digest)
    # Two declared components may intentionally load the same immutable file.
    # submission.json binds the per-checkpoint mapping; the compact registry
    # retains the unique byte identities.
    return sorted(set(values))


def package_tree_binding(directory: Path) -> dict[str, Any]:
    """Hash every retained package file with a stable path/size/content rule."""

    directory = directory.resolve()
    if not directory.is_dir():
        raise HiLiftAeroMLPreReleaseError(
            f"package directory does not exist: {directory}"
        )
    records: list[tuple[str, int, str]] = []
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise HiLiftAeroMLPreReleaseError(
                f"package tree contains a symbolic link: {path.relative_to(directory)}"
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise HiLiftAeroMLPreReleaseError(
                f"package tree contains a non-regular entry: {path.relative_to(directory)}"
            )
        relative = path.relative_to(directory).as_posix()
        records.append((relative, path.stat().st_size, sha256_file(path)))
    if not records:
        raise HiLiftAeroMLPreReleaseError("package tree contains no files")
    digest = hashlib.sha256()
    for relative, size, content_digest in records:
        digest.update(f"{relative}\0{size}\0{content_digest}\n".encode("utf-8"))
    return {
        "algorithm": TREE_HASH_ALGORITHM,
        "sha256": digest.hexdigest(),
        "file_count": len(records),
        "total_bytes": sum(size for _relative, size, _digest in records),
    }


def _artifact_binding(directory: Path, file: object, label: str) -> dict[str, Any]:
    path = _safe_file(directory, file, label)
    return {
        "file": path.relative_to(directory).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def build_registry_entry(
    submission_path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Build one exact dev-only registration entry from a complete package."""

    repository_root = repository_root.resolve()
    submission_path = submission_path.resolve()
    try:
        relative_submission = submission_path.relative_to(repository_root).as_posix()
    except ValueError as error:
        raise HiLiftAeroMLPreReleaseError(
            "submission.json must be inside the repository"
        ) from error
    directory = submission_path.parent
    submission = _read_json(submission_path, "submission")
    submission_id = submission.get("submission_id")
    expected_path = f"submissions/hiliftaeroml/{submission_id}/submission.json"
    methodology = submission.get("methodology")
    scoring_support = submission.get("scoring_support")
    if (
        not isinstance(submission_id, str)
        or relative_submission != expected_path
        or submission.get("schema_version") != "3.0"
        or submission.get("dataset_id") != "hiliftaeroml"
        or submission.get("dataset") != "HiLiftAeroML"
        or submission.get("prediction_scope") != "surface_and_volume"
        or "approval" in submission
        or not isinstance(scoring_support, Mapping)
        or scoring_support.get("status") != "candidate"
        or not isinstance(methodology, Mapping)
        or methodology.get("record_kind") != "submitter_reported"
    ):
        raise HiLiftAeroMLPreReleaseError(
            "only a conventional unapproved HiLiftAeroML schema-v3 genuine-inference "
            "candidate can be registered"
        )

    evaluation = submission.get("evaluation")
    case_metrics = submission.get("case_metrics")
    profiles = submission.get("profile_data")
    spatial = submission.get("spatial_discretization")
    if not all(
        isinstance(value, Mapping)
        for value in (evaluation, case_metrics, profiles, spatial)
    ):
        raise HiLiftAeroMLPreReleaseError(
            "submission lacks one or more required schema-v3 artifact declarations"
        )
    artifacts = {
        "evaluation_evidence": _artifact_binding(
            directory, evaluation.get("evidence_file"), "evaluation evidence"
        ),
        "case_metrics": _artifact_binding(
            directory, case_metrics.get("file"), "case metrics"
        ),
        "profile_index": _artifact_binding(
            directory, profiles.get("index_file"), "profile index"
        ),
        "discretization": _artifact_binding(
            directory, spatial.get("file"), "discretization"
        ),
    }
    evidence = _read_json(
        directory / artifacts["evaluation_evidence"]["file"],
        "evaluation evidence",
    )
    if (
        evidence.get("status") != "submitted_evaluation"
        or evidence.get("submission_id") != submission_id
        or evidence.get("dataset_id") != "hiliftaeroml"
        or evidence.get("split_id") != submission.get("split_id")
        or evidence.get("case_set_id") != submission.get("case_set_id")
        or not isinstance(evidence.get("notes"), str)
        or not evidence["notes"].endswith(GENUINE_INFERENCE_ATTESTATION)
        or artifacts["evaluation_evidence"]["sha256"]
        != evaluation.get("evidence_sha256")
    ):
        raise HiLiftAeroMLPreReleaseError(
            "evaluation evidence identity, hash, or genuine-inference attestation differs"
        )
    discretization = _read_json(
        directory / artifacts["discretization"]["file"], "discretization"
    )
    case_manifest = discretization.get("case_manifest")
    if not isinstance(case_manifest, Mapping):
        raise HiLiftAeroMLPreReleaseError("discretization has no case manifest")
    artifacts["discretization_cases"] = _artifact_binding(
        directory, case_manifest.get("file"), "discretization case manifest"
    )
    if (
        artifacts["case_metrics"]["sha256"] != case_metrics.get("sha256")
        or artifacts["discretization"]["sha256"] != spatial.get("sha256")
        or artifacts["discretization_cases"]["sha256"] != case_manifest.get("sha256")
    ):
        raise HiLiftAeroMLPreReleaseError(
            "one or more package artifacts differ from their internal SHA-256 bindings"
        )
    profile_index = _read_json(
        directory / artifacts["profile_index"]["file"], "profile index"
    )
    case_count = case_metrics.get("case_count")
    if (
        isinstance(case_count, bool)
        or not isinstance(case_count, int)
        or case_count < 1
        or profile_index.get("case_count") != case_count
        or artifacts["profile_index"]["sha256"] != evidence.get("profile_index_sha256")
    ):
        raise HiLiftAeroMLPreReleaseError("package case counts are inconsistent")
    from reference.hiliftaeroml.dev_release import implementation_binding

    expected_binding = implementation_binding(repository_root)
    if (
        profiles.get("compact_profile_implementation_binding") != expected_binding
        or evidence.get("compact_profile_implementation_binding") != expected_binding
    ):
        raise HiLiftAeroMLPreReleaseError(
            "compact adapter implementation binding differs"
        )
    observed_case_ids = []
    chunks = profile_index.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise HiLiftAeroMLPreReleaseError("profile index contains no chunks")
    profile_root = (directory / artifacts["profile_index"]["file"]).parent
    for descriptor in chunks:
        chunk_path = _safe_file(profile_root, descriptor.get("file"), "profile chunk")
        if sha256_file(chunk_path) != descriptor.get("sha256"):
            raise HiLiftAeroMLPreReleaseError("profile chunk digest differs")
        chunk = _read_json(chunk_path, "profile chunk")
        cases = chunk.get("cases", [])
        if [case.get("case_id") for case in cases] != descriptor.get("case_ids"):
            raise HiLiftAeroMLPreReleaseError("profile chunk case order differs")
        for case in cases:
            observed_case_ids.append(case["case_id"])
            artifact = case.get("artifact", {})
            artifact_path = _safe_file(
                profile_root, artifact.get("file"), "compact predictions"
            )
            if sha256_file(artifact_path) != artifact.get(
                "sha256"
            ) or artifact_path.stat().st_size != artifact.get("byte_size"):
                raise HiLiftAeroMLPreReleaseError(
                    "compact prediction artifact binding differs"
                )
    if (
        len(observed_case_ids) != case_count
        or len(set(observed_case_ids)) != case_count
    ):
        raise HiLiftAeroMLPreReleaseError("profile package case inventory differs")
    series_count = 15 * case_count
    return {
        "status": "registered_pre_release_reference",
        "record_type": "pre_release_reference",
        "submission_id": submission_id,
        "submission_path": relative_submission,
        "submission_json_sha256": sha256_file(submission_path),
        "scope": {
            "split_id": submission.get("split_id"),
            "case_set_id": submission.get("case_set_id"),
            "case_count": case_count,
            "profile_series_count": series_count,
        },
        "inference_provenance": {
            "actual_model_inference": True,
            "evaluation_truth_generated_predictions": False,
            "methodology_record_kind": "submitter_reported",
            "checkpoint_sha256s": checkpoint_sha256s(methodology),
            "attestation": GENUINE_INFERENCE_ATTESTATION,
        },
        "artifacts": artifacts,
        "package_tree": package_tree_binding(directory),
        "claim_eligibility": {
            "academic_citation": False,
            "promotion": False,
        },
    }


__all__ = [
    "HiLiftAeroMLPreReleaseError",
    "GENUINE_INFERENCE_ATTESTATION",
    "REGISTRY_SCHEMA",
    "REGISTRY_STATUS",
    "TREE_HASH_ALGORITHM",
    "build_registry_entry",
    "checkpoint_sha256s",
    "package_tree_binding",
    "sha256_file",
]
