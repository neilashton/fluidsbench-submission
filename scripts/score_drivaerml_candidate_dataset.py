#!/usr/bin/env python3
"""Reduce one complete official DrivAerML split to candidate evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference.drivaerml.dataset_scorer import (  # noqa: E402
    DrivAerDatasetScorerError,
    evaluate_candidate_dataset,
    schema_v3_case_metrics_candidate_adapter,
    write_candidate_dataset_evidence,
    write_schema_v3_case_metrics_candidate,
)


DEFAULT_SPECIFICATION = ROOT / "benchmark-specs" / "drivaerml" / "submission-spec.json"


def _json_files(directory: Path, label: str) -> tuple[Path, ...]:
    root = directory.expanduser().resolve()
    if not root.is_dir():
        raise DrivAerDatasetScorerError(f"{label} is not a directory")
    paths = tuple(sorted(root.glob("run_*.json"), key=lambda item: item.name))
    if not paths:
        raise DrivAerDatasetScorerError(f"{label} contains no run_N.json files")
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-id", required=True)
    parser.add_argument("--core-evidence-dir", required=True, type=Path)
    parser.add_argument("--diagnostic-evidence-dir", required=True, type=Path)
    parser.add_argument("--force-truth", required=True, type=Path)
    parser.add_argument(
        "--submission-specification", type=Path, default=DEFAULT_SPECIFICATION
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--schema-v3-case-metrics-output",
        type=Path,
        help=(
            "Optional candidate-only schema-v3 case-metrics adapter. This does "
            "not produce submission.json or activate scoring support."
        ),
    )
    parser.add_argument("--submission-id")
    parser.add_argument("--candidate-support-release-id")
    parser.add_argument("--candidate-support-manifest-sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adapter_arguments = (
        args.submission_id,
        args.candidate_support_release_id,
        args.candidate_support_manifest_sha256,
    )
    if args.schema_v3_case_metrics_output is None and any(
        value is not None for value in adapter_arguments
    ):
        raise DrivAerDatasetScorerError(
            "schema-v3 adapter identity arguments require "
            "--schema-v3-case-metrics-output"
        )
    if args.schema_v3_case_metrics_output is not None and any(
        value is None for value in adapter_arguments
    ):
        raise DrivAerDatasetScorerError(
            "schema-v3 adapter output requires --submission-id, "
            "--candidate-support-release-id and "
            "--candidate-support-manifest-sha256"
        )
    evaluation = evaluate_candidate_dataset(
        submission_specification=args.submission_specification,
        split_id=args.split_id,
        force_truth_csv=args.force_truth,
        core_case_evidence=_json_files(args.core_evidence_dir, "core evidence directory"),
        diagnostic_case_evidence=_json_files(
            args.diagnostic_evidence_dir, "diagnostic evidence directory"
        ),
    )
    result: dict[str, object] = {
        "dataset_evidence": write_candidate_dataset_evidence(evaluation, args.output)
    }
    if args.schema_v3_case_metrics_output is not None:
        adapter = schema_v3_case_metrics_candidate_adapter(
            evaluation,
            submission_id=args.submission_id,
            candidate_support_release_id=args.candidate_support_release_id,
            candidate_support_manifest_sha256=args.candidate_support_manifest_sha256,
        )
        result["schema_v3_case_metrics_candidate"] = (
            write_schema_v3_case_metrics_candidate(
                adapter, args.schema_v3_case_metrics_output
            )
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
