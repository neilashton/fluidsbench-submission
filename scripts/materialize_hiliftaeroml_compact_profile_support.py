#!/usr/bin/env python3
"""Materialize one inactive evaluator-owned compact-profile support release.

The native evaluator outputs are used only for their validated support and
prediction ordering. Ground truth is joined exclusively from the separately
bound internal source-truth release. Output creation is exclusive and the
canonical manifest is written last by the reference evaluator release writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference.hiliftaeroml.compact_profile_evaluator import (  # noqa: E402
    COMPACT_PROFILE_CONTRACT_ID,
    COMPACT_PROFILE_CONTRACT_SHA256,
    COMPACT_SUPPORT_RELEASE_ID,
    COMPACT_SUPPORT_RELEASE_STATUS,
    COMPACT_SUPPORT_RELEASE_USAGE,
    CompactProfileEvaluationError,
    open_compact_support_release,
    write_compact_support_release,
)
from reference.hiliftaeroml.compact_profiles import (  # noqa: E402
    COMPACT_PROFILE_FORMAT,
    CP_POINTS_PER_GRAPH,
    CompactProfileError,
    build_compact_support,
)
from reference.hiliftaeroml.native_profile_evaluator import (  # noqa: E402
    CandidateTruthRelease,
    NativeProfileEvaluationError,
    _truth_case,
    _validate_cp_alignment,
    _validate_velocity_alignment,
    open_candidate_truth_release,
)
from reference.hiliftaeroml.native_profile_truth import (  # noqa: E402
    TRUTH_FORMAT,
    NativeProfileTruthError,
)
from reference.hiliftaeroml.native_profiles import (  # noqa: E402
    ROWS,
    SAFE_CASE_ID,
    NativeProfileError,
    load_json,
    sha256_file,
    validate_cp_source,
    validate_velocity_source,
)


CASE_SET_SHA256_RULE = "sha256(utf8(case_id + newline) in listed order)"


def _fail(message: str) -> None:
    raise CompactProfileEvaluationError(message)


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be an object")
    return value


def _require_sha(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} must be a lowercase SHA-256")
    return value


def _regular_directory(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        _fail(f"{label} must be a regular non-symlink directory: {path}")
    return path.resolve()


def _safe_declared_file(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be a non-empty relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        _fail(f"{label} must remain inside the benchmark-spec directory")
    resolved_root = root.resolve()
    unresolved = resolved_root / relative
    cursor = resolved_root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            _fail(f"{label} traverses a symlink")
    path = unresolved.resolve()
    if resolved_root not in path.parents or not path.is_file() or path.is_symlink():
        _fail(f"{label} must name a regular file inside the benchmark-spec directory")
    return path


def _case_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) != len(set(value)):
        _fail("benchmark split case_ids must be a non-empty unique list")
    for case_id in value:
        if not isinstance(case_id, str) or SAFE_CASE_ID.fullmatch(case_id) is None:
            _fail(f"benchmark split contains invalid case ID {case_id!r}")
    return tuple(value)


def _case_set_sha256(case_ids: Sequence[str]) -> str:
    payload = "".join(f"{case_id}\n" for case_id in case_ids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_benchmark_bindings(
    *, submission_spec_path: Path, split_path: Path
) -> tuple[
    dict[str, Any],
    str,
    dict[str, Any],
    str,
    tuple[str, ...],
    Mapping[str, Any],
    Path,
    Mapping[str, Any],
]:
    try:
        spec, spec_sha = load_json(submission_spec_path, label="submission spec")
        split, split_sha = load_json(split_path, label="benchmark split")
    except NativeProfileError as error:
        raise CompactProfileEvaluationError(str(error)) from error
    if spec.get("dataset_id") != "hiliftaeroml":
        _fail("submission spec dataset identity differs")
    expected_split_keys = {
        "schema_version",
        "dataset_id",
        "split_id",
        "case_set_id",
        "split_label",
        "case_id_status",
        "case_count",
        "case_set_sha256",
        "case_set_sha256_rule",
        "case_ids",
    }
    if set(split) != expected_split_keys:
        _fail("benchmark split keys differ")
    case_ids = _case_ids(split.get("case_ids"))
    if (
        split.get("schema_version") != "1.0"
        or split.get("dataset_id") != "hiliftaeroml"
        or split.get("case_id_status") != "official"
        or split.get("case_count") != len(case_ids)
        or split.get("case_set_sha256_rule") != CASE_SET_SHA256_RULE
        or split.get("case_set_sha256") != _case_set_sha256(case_ids)
    ):
        _fail("benchmark split identity, count, order, or case-set digest differs")

    split_declarations = spec.get("splits")
    if not isinstance(split_declarations, list):
        _fail("submission spec split declarations are absent")
    matches = [
        item
        for item in split_declarations
        if isinstance(item, Mapping) and item.get("id") == split.get("split_id")
    ]
    if len(matches) != 1:
        _fail("submission spec does not declare the selected split exactly once")
    declaration = matches[0]
    if set(declaration) != {
        "id",
        "label",
        "index_file",
        "case_count",
        "case_set_id",
        "case_id_status",
        "sha256",
    }:
        _fail("submission spec split declaration keys differ")
    declared_split_path = _safe_declared_file(
        submission_spec_path.parent,
        declaration.get("index_file"),
        "submission spec split index_file",
    )
    if declared_split_path != split_path.resolve():
        _fail("selected split path differs from the submission-spec declaration")
    if (
        declaration.get("label") != split.get("split_label")
        or declaration.get("case_count") != len(case_ids)
        or declaration.get("case_set_id") != split.get("case_set_id")
        or declaration.get("case_id_status") != "official"
        or declaration.get("sha256") != split_sha
    ):
        _fail("selected split differs from its submission-spec binding")

    compact = _require_mapping(
        spec.get("profile_definition"), "profile_definition"
    )
    contract_path = _safe_declared_file(
        submission_spec_path.parent,
        compact.get("file"),
        "compact profile contract file",
    )
    try:
        contract_sha = sha256_file(contract_path)
    except NativeProfileError as error:
        raise CompactProfileEvaluationError(str(error)) from error
    if (
        compact.get("status") != "official"
        or compact.get("contract_id") != COMPACT_PROFILE_CONTRACT_ID
        or compact.get("format") != COMPACT_PROFILE_FORMAT
        or compact.get("sha256") != COMPACT_PROFILE_CONTRACT_SHA256
        or contract_sha != COMPACT_PROFILE_CONTRACT_SHA256
    ):
        _fail("compact profile contract differs from the reference evaluator")
    support_declaration = _require_mapping(
        compact.get("candidate_dry_run_evaluator_support"),
        "candidate_dry_run_evaluator_support",
    )
    if set(support_declaration) != {
        "status",
        "usage",
        "release_id",
        "manifest_sha256",
    }:
        _fail("candidate evaluator-support declaration keys differ")
    if (
        support_declaration.get("status") != COMPACT_SUPPORT_RELEASE_STATUS
        or support_declaration.get("usage") != COMPACT_SUPPORT_RELEASE_USAGE
        or support_declaration.get("release_id") != COMPACT_SUPPORT_RELEASE_ID
    ):
        _fail("candidate evaluator-support declaration identity differs")
    declared_support_sha = support_declaration.get("manifest_sha256")
    if declared_support_sha is not None:
        _require_sha(
            declared_support_sha,
            "candidate evaluator-support manifest_sha256",
        )

    truth_declaration = _require_mapping(
        compact.get("candidate_dry_run_profile_ground_truth"),
        "candidate_dry_run_profile_ground_truth",
    )
    binding_path = _safe_declared_file(
        submission_spec_path.parent,
        truth_declaration.get("binding_file"),
        "candidate profile-truth binding file",
    )
    return (
        spec,
        spec_sha,
        split,
        split_sha,
        case_ids,
        support_declaration,
        binding_path,
        truth_declaration,
    )


class _StreamingCaseMaterializer:
    """Build at most one case support at a time for the release writer."""

    def __init__(
        self,
        *,
        case_ids: Sequence[str],
        surface_outputs_root: Path,
        volume_outputs_root: Path,
        truth_release: CandidateTruthRelease,
    ) -> None:
        self.case_ids = tuple(case_ids)
        self._case_set = set(self.case_ids)
        self._positions = {
            case_id: position
            for position, case_id in enumerate(self.case_ids, start=1)
        }
        self.surface_outputs_root = _regular_directory(
            surface_outputs_root, "surface native-output root"
        )
        self.volume_outputs_root = _regular_directory(
            volume_outputs_root, "volume native-output root"
        )
        self.truth_release = truth_release
        self._cached_case_id: str | None = None
        self._cached_support: dict[str, np.ndarray] | None = None
        self._cached_hashes: dict[str, str] | None = None

    @staticmethod
    def _stream(root: Path, case_id: str, name: str) -> Path:
        case_root = root / case_id
        stream = case_root / name
        if (
            case_root.is_symlink()
            or not case_root.is_dir()
            or stream.is_symlink()
            or not stream.is_dir()
        ):
            _fail(f"{case_id} native-output stream is absent or non-regular: {stream}")
        return stream

    def _build(self, case_id: str) -> None:
        if case_id not in self._case_set:
            raise KeyError(case_id)
        if self._cached_case_id == case_id:
            return
        # Drop the prior support before loading the next native case.  The two
        # Mapping views deliberately share this cache, so the writer can ask
        # for hashes and support without causing a second build.
        self._cached_case_id = None
        self._cached_support = None
        self._cached_hashes = None
        surface = self._stream(
            self.surface_outputs_root, case_id, "surface_submission_stream"
        )
        volume = self._stream(
            self.volume_outputs_root, case_id, "volume_submission_stream"
        )
        cp_arrays, cp_metadata = validate_cp_source(
            metrics_path=surface / "cp_profile_metrics.json",
            npz_path=surface / "cp_cut_values.npz",
        )
        cp_metadata["station_rows"] = list(ROWS)
        velocity_arrays, velocity_metadata = validate_velocity_source(
            case_id=case_id,
            metrics_path=volume / "velocity_profile_metrics.json",
            npz_path=volume / "velocity_profiles.npz",
        )
        record, truth_cp, truth_velocity = _truth_case(
            self.truth_release, case_id
        )
        _validate_cp_alignment(case_id, cp_arrays, cp_metadata, record)
        _validate_velocity_alignment(
            case_id,
            velocity_arrays,
            velocity_metadata,
            record,
            truth_velocity,
        )
        support = build_compact_support(
            cp_native=cp_arrays,
            truth_cp=truth_cp,
            velocity_native=velocity_arrays,
            truth_velocity_nd=truth_velocity,
        )
        self._cached_case_id = case_id
        self._cached_support = support
        self._cached_hashes = {
            "cp_profile_metrics": cp_metadata["source_metrics_sha256"],
            "cp_cut_values": cp_metadata["source_npz_sha256"],
            "velocity_profile_metrics": velocity_metadata[
                "source_metrics_sha256"
            ],
            "velocity_profiles": velocity_metadata["source_npz_sha256"],
        }
        print(
            f"compact-support {self._positions[case_id]}/{len(self.case_ids)} "
            f"{case_id}",
            file=sys.stderr,
            flush=True,
        )

    def support(self, case_id: str) -> Mapping[str, np.ndarray]:
        self._build(case_id)
        assert self._cached_support is not None
        return self._cached_support

    def source_hashes(self, case_id: str) -> Mapping[str, str]:
        self._build(case_id)
        assert self._cached_hashes is not None
        return self._cached_hashes


class _SupportView(Mapping[str, Mapping[str, np.ndarray]]):
    def __init__(self, source: _StreamingCaseMaterializer) -> None:
        self.source = source

    def __getitem__(self, case_id: str) -> Mapping[str, np.ndarray]:
        return self.source.support(case_id)

    def __iter__(self) -> Iterator[str]:
        return iter(self.source.case_ids)

    def __len__(self) -> int:
        return len(self.source.case_ids)


class _SourceHashView(Mapping[str, Mapping[str, str]]):
    def __init__(self, source: _StreamingCaseMaterializer) -> None:
        self.source = source

    def __getitem__(self, case_id: str) -> Mapping[str, str]:
        return self.source.source_hashes(case_id)

    def __iter__(self) -> Iterator[str]:
        return iter(self.source.case_ids)

    def __len__(self) -> int:
        return len(self.source.case_ids)


def materialize_compact_support_release(
    *,
    submission_spec_path: Path,
    split_path: Path,
    surface_outputs_root: Path,
    volume_outputs_root: Path,
    source_truth_release: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Build one exact split support release and return its binding receipt."""

    (
        _spec,
        spec_sha,
        split,
        split_sha,
        case_ids,
        support_declaration,
        binding_path,
        truth_declaration,
    ) = _load_benchmark_bindings(
        submission_spec_path=submission_spec_path,
        split_path=split_path,
    )
    try:
        truth_release = open_candidate_truth_release(
            release_root=source_truth_release,
            candidate_declaration=truth_declaration,
            expected_case_ids=case_ids,
            case_set_id=split["case_set_id"],
            binding_path=binding_path,
        )
    except NativeProfileEvaluationError as error:
        raise CompactProfileEvaluationError(str(error)) from error
    source_truth_release_id = truth_release.manifest.get("release_id")
    source_truth_manifest_sha = truth_declaration.get("manifest_sha256")
    if (
        source_truth_release_id != truth_declaration.get("release_id")
        or truth_release.manifest.get("format") != TRUTH_FORMAT
    ):
        _fail("opened source profile-truth release identity differs")
    source_truth_manifest_sha = _require_sha(
        source_truth_manifest_sha, "source profile-truth manifest SHA-256"
    )

    source = _StreamingCaseMaterializer(
        case_ids=case_ids,
        surface_outputs_root=surface_outputs_root,
        volume_outputs_root=volume_outputs_root,
        truth_release=truth_release,
    )
    try:
        manifest_sha = write_compact_support_release(
            release_root=output_root,
            case_ids=case_ids,
            case_sets={split["case_set_id"]: case_ids},
            supports=_SupportView(source),
            source_artifact_sha256=_SourceHashView(source),
            source_profile_truth_release_id=source_truth_release_id,
            source_profile_truth_manifest_sha256=source_truth_manifest_sha,
        )
    except (CompactProfileError, NativeProfileError) as error:
        raise CompactProfileEvaluationError(str(error)) from error
    declared_manifest_sha = support_declaration.get("manifest_sha256")
    if declared_manifest_sha is not None and manifest_sha != declared_manifest_sha:
        # The writer reached this path only after exclusively creating the
        # requested root.  Remove those newly produced, but incorrectly bound,
        # bytes rather than leaving a plausible-looking release behind.
        if output_root.is_dir() and not output_root.is_symlink():
            shutil.rmtree(output_root)
        _fail("materialized support manifest differs from its submission-spec pin")
    handle = open_compact_support_release(
        release_root=output_root,
        expected_manifest_sha256=manifest_sha,
        expected_case_ids=case_ids,
        case_set_id=split["case_set_id"],
    )
    if (
        handle.source_profile_truth_release_id != source_truth_release_id
        or handle.source_profile_truth_manifest_sha256
        != source_truth_manifest_sha
    ):
        _fail("materialized support source-truth binding differs")
    return {
        "status": COMPACT_SUPPORT_RELEASE_STATUS,
        "usage": COMPACT_SUPPORT_RELEASE_USAGE,
        "dataset_id": "hiliftaeroml",
        "evaluator_support_release_id": COMPACT_SUPPORT_RELEASE_ID,
        "evaluator_support_manifest_sha256": manifest_sha,
        "profile_contract_id": COMPACT_PROFILE_CONTRACT_ID,
        "profile_contract_sha256": COMPACT_PROFILE_CONTRACT_SHA256,
        "source_profile_truth_release_id": source_truth_release_id,
        "source_profile_truth_manifest_sha256": source_truth_manifest_sha,
        "submission_spec_sha256": spec_sha,
        "split_id": split["split_id"],
        "split_sha256": split_sha,
        "case_set_id": split["case_set_id"],
        "case_set_sha256": split["case_set_sha256"],
        "case_count": len(case_ids),
        "points_per_physical_graph": CP_POINTS_PER_GRAPH,
        "output_root": str(output_root.resolve()),
        "activation": {
            "owner_approval_complete": False,
            "published": False,
            "submissions_opened": False,
            "materialization_changes_activation": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--submission-spec", required=True, type=Path)
    result.add_argument("--split", required=True, type=Path)
    result.add_argument("--surface-outputs-root", required=True, type=Path)
    result.add_argument("--volume-outputs-root", required=True, type=Path)
    result.add_argument("--source-truth-release", required=True, type=Path)
    result.add_argument("--output-root", required=True, type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        receipt = materialize_compact_support_release(
            submission_spec_path=args.submission_spec,
            split_path=args.split,
            surface_outputs_root=args.surface_outputs_root,
            volume_outputs_root=args.volume_outputs_root,
            source_truth_release=args.source_truth_release,
            output_root=args.output_root,
        )
    except (
        CompactProfileEvaluationError,
        CompactProfileError,
        NativeProfileEvaluationError,
        NativeProfileTruthError,
        NativeProfileError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
