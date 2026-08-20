#!/usr/bin/env python3
"""Evaluate exactly the real run_1 and run_44 candidate pilot cases.

This is a fail-closed orchestration example.  It reuses the repository's core
and AutoCFD5 candidate evaluator entry points, always reconstructs the pinned
multipart VTU byte stream, and never downloads or generates scientific data.
The DrivAerML scoring contract remains closed, so the command writes candidate
evidence only and never writes ``submission.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from reference.drivaerml.diagnostic_evaluator import (  # noqa: E402
    DrivAerDiagnosticEvaluatorError,
)
from reference.drivaerml.evaluator import (  # noqa: E402
    DrivAerCandidateEvaluatorError,
    validate_native_source_contract,
)
from reference.drivaerml.native_surface import DrivAerNativeSurfaceError  # noqa: E402
from reference.drivaerml.prediction_chunks import PredictionChunkError  # noqa: E402
from reference.drivaerml.source import (  # noqa: E402
    NativeSourceError,
    load_native_source_pin,
)
from scripts.build_drivaerml_cp_case_support import CpCaseSupportError  # noqa: E402
from scripts.evaluate_drivaerml_candidate_case import run as _run_core_case  # noqa: E402
from scripts.evaluate_drivaerml_candidate_diagnostics import (  # noqa: E402
    DEFAULT_PROFILE,
    run as _run_diagnostic_case,
)


INPUT_SCHEMA = "drivaerml-run1-run44-reference-inputs-v2"
OUTPUT_SCHEMA = "drivaerml-run1-run44-reference-evidence-v2"
OUTPUT_STATUS = "candidate_pilot_evidence_not_official_submission"
REQUIRED_CASE_PART_COUNTS = {"run_1": 2, "run_44": 3}
PREDICTION_SUPPORT_IDS = ("surface_native_cells", "volume_native_cells")
CASE_INPUT_KEYS = frozenset(
    {
        "case_id",
        "surface_area_npy",
        "surface_prediction_manifest",
        "volume_prediction_manifest",
        "cp_support_json",
        "velocity_mapping_json",
        "velocity_receipt_json",
    }
)


class RealReferenceDriverError(ValueError):
    """Raised before or during a real candidate pilot orchestration."""


@dataclass(frozen=True)
class RealCaseInputs:
    case_id: str
    surface_area_npy: Path
    surface_prediction_manifest: Path
    volume_prediction_manifest: Path
    cp_support_json: Path
    velocity_mapping_json: Path
    velocity_receipt_json: Path


@dataclass(frozen=True)
class _PredictionEvidenceIdentity:
    manifest_sha256: str
    chunk_sha256: tuple[str, ...]
    entity_count: int


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RealReferenceDriverError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _sha256_file(path: Path, *, chunk_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as source:
        while block := source.read(chunk_bytes):
            digest.update(block)
    return digest.hexdigest()


def _sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RealReferenceDriverError(f"{label} must be a lowercase SHA-256")
    return value


def _positive_evidence_count(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RealReferenceDriverError(f"{label} must be a positive integer")
    return value


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RealReferenceDriverError(f"{label} must be an object")
    return value


def _generated_evidence_document(
    path: Path,
    identity: dict[str, object],
    *,
    case_id: str,
    label: str,
) -> dict[str, Any]:
    """Reload one generated output and bind it to the writer's identity."""

    source = _regular_file(path, label)
    expected_sha256 = _sha256(identity.get("sha256"), f"{label} SHA-256")
    expected_size = _positive_evidence_count(
        identity.get("byte_size"), f"{label} byte_size"
    )
    initial_sha256 = _sha256_file(source)
    if initial_sha256 != expected_sha256 or source.stat().st_size != expected_size:
        raise RealReferenceDriverError(
            f"{label} differs from the evaluator writer identity"
        )
    try:
        document = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except RealReferenceDriverError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RealReferenceDriverError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict) or document.get("case_id") != case_id:
        raise RealReferenceDriverError(f"{label} case identity mismatch")
    if _sha256_file(source) != initial_sha256:
        raise RealReferenceDriverError(f"{label} changed while it was reloaded")
    return document


def _prediction_evidence_identities(
    document: dict[str, Any],
    *,
    case_id: str,
    diagnostic: bool,
) -> dict[str, _PredictionEvidenceIdentity]:
    """Extract the prediction identities common to core and diagnostics."""

    if diagnostic:
        root = _mapping(
            document.get("sparse_gather_evidence"),
            f"{case_id} diagnostic sparse_gather_evidence",
        )
        records = {
            "surface_native_cells": root.get("surface_prediction"),
            "volume_native_cells": root.get("volume_prediction"),
        }
    else:
        root = _mapping(
            document.get("prediction_inputs"),
            f"{case_id} core prediction_inputs",
        )
        records = {
            support_id: root.get(support_id)
            for support_id in PREDICTION_SUPPORT_IDS
        }

    result: dict[str, _PredictionEvidenceIdentity] = {}
    for support_id in PREDICTION_SUPPORT_IDS:
        record = _mapping(
            records[support_id], f"{case_id}/{support_id} prediction evidence"
        )
        chunks = record.get("chunk_sha256")
        if not isinstance(chunks, list) or not chunks:
            raise RealReferenceDriverError(
                f"{case_id}/{support_id} prediction evidence has no chunk identities"
            )
        chunk_sha256 = tuple(
            _sha256(value, f"{case_id}/{support_id} chunk SHA-256")
            for value in chunks
        )
        chunk_count = _positive_evidence_count(
            record.get("chunk_count"), f"{case_id}/{support_id} chunk_count"
        )
        if chunk_count != len(chunk_sha256):
            raise RealReferenceDriverError(
                f"{case_id}/{support_id} chunk count differs from its identities"
            )
        result[support_id] = _PredictionEvidenceIdentity(
            manifest_sha256=_sha256(
                record.get("manifest_sha256"),
                f"{case_id}/{support_id} manifest SHA-256",
            ),
            chunk_sha256=chunk_sha256,
            entity_count=_positive_evidence_count(
                record.get("total_row_count" if diagnostic else "entity_count"),
                f"{case_id}/{support_id} entity count",
            ),
        )
    return result


def _regular_file(path: Path | str, label: str) -> Path:
    candidate = Path(path).expanduser()
    try:
        if candidate.is_symlink():
            raise RealReferenceDriverError(f"{label} must not be a symlink")
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise RealReferenceDriverError(f"{label} does not exist: {candidate}") from error
    if not resolved.is_file():
        raise RealReferenceDriverError(f"{label} must be a regular file")
    return resolved


def _config_file(config_directory: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise RealReferenceDriverError(f"{label} must be a non-empty path string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_directory / path
    return _regular_file(path, label)


def load_case_inputs(
    path: Path | str,
) -> tuple[Path, str, tuple[RealCaseInputs, ...]]:
    """Load a closed two-case config and preflight every declared input file."""

    source = _regular_file(path, "case-input config")
    try:
        source_bytes = source.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        document = json.loads(
            source_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except RealReferenceDriverError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RealReferenceDriverError("case-input config is not valid JSON") from error
    if not isinstance(document, dict) or set(document) != {"schema", "cases"}:
        raise RealReferenceDriverError(
            "case-input config must contain exactly 'schema' and 'cases'"
        )
    if document["schema"] != INPUT_SCHEMA:
        raise RealReferenceDriverError(f"case-input schema must equal {INPUT_SCHEMA!r}")
    rows = document["cases"]
    if not isinstance(rows, list) or len(rows) != len(REQUIRED_CASE_PART_COUNTS):
        raise RealReferenceDriverError("case-input config must contain exactly two cases")
    parsed: dict[str, RealCaseInputs] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != CASE_INPUT_KEYS:
            missing = sorted(CASE_INPUT_KEYS - set(row) if isinstance(row, dict) else CASE_INPUT_KEYS)
            unknown = sorted(set(row) - CASE_INPUT_KEYS if isinstance(row, dict) else [])
            raise RealReferenceDriverError(
                f"cases[{index}] has a closed schema; missing={missing}, unknown={unknown}"
            )
        case_id = row["case_id"]
        if not isinstance(case_id, str) or case_id not in REQUIRED_CASE_PART_COUNTS:
            raise RealReferenceDriverError("the only permitted cases are run_1 and run_44")
        if case_id in parsed:
            raise RealReferenceDriverError(f"duplicate case {case_id}")
        values: dict[str, Path] = {
            key: _config_file(source.parent, row[key], f"{case_id}.{key}")
            for key in sorted(CASE_INPUT_KEYS - {"case_id"})
        }
        parsed[case_id] = RealCaseInputs(case_id=case_id, **values)
    if set(parsed) != set(REQUIRED_CASE_PART_COUNTS):
        raise RealReferenceDriverError("case-input config must cover run_1 and run_44")
    return (
        source,
        source_sha256,
        tuple(parsed[case_id] for case_id in REQUIRED_CASE_PART_COUNTS),
    )


def _positive_integer(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if value < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-inputs", type=Path, required=True)
    parser.add_argument("--native-source-pin", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--autocfd5-profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--maximum-prediction-chunk-rows",
        type=_positive_integer,
        default=1_000_000,
    )
    parser.add_argument(
        "--io-chunk-bytes",
        type=_positive_integer,
        default=8 * 1024 * 1024,
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return _parser().parse_args(argv)


def _preflight(
    args: argparse.Namespace,
) -> tuple[Any, Path, str, tuple[RealCaseInputs, ...]]:
    config_path, config_sha256, cases = load_case_inputs(args.case_inputs)
    pin_path = _regular_file(args.native_source_pin, "native-source pin")
    profile_path = _regular_file(args.autocfd5_profile, "AutoCFD5 profile")
    dataset_root = Path(args.dataset_root).expanduser().resolve()
    if not dataset_root.is_dir():
        raise RealReferenceDriverError("dataset root must be an existing directory")
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise RealReferenceDriverError(f"output must not already exist: {output}")
    pin = load_native_source_pin(pin_path)
    validate_native_source_contract(pin)
    for case_id, expected_parts in REQUIRED_CASE_PART_COUNTS.items():
        if len(pin.case(case_id).volume_parts) != expected_parts:
            raise RealReferenceDriverError(
                f"pinned {case_id} must contain exactly {expected_parts} volume parts"
            )
        pin.resolve(case_id, dataset_root)
    args.native_source_pin = pin_path
    args.dataset_root = dataset_root
    args.autocfd5_profile = profile_path
    args.output = output
    return pin, config_path, config_sha256, cases


def run(args: argparse.Namespace) -> dict[str, object]:
    """Run both evaluator paths in a staged directory, then publish evidence."""

    pin, config_path, config_sha256, cases = _preflight(args)
    output: Path = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}.", dir=output.parent
    ) as staging_text:
        staging = Path(staging_text)
        case_results: list[dict[str, object]] = []
        for case_inputs in cases:
            case_directory = staging / "cases" / case_inputs.case_id
            core_output = case_directory / "core-evaluation.json"
            diagnostic_output = case_directory / "diagnostic-evaluation.json"
            core_identity = _run_core_case(
                SimpleNamespace(
                    case_id=case_inputs.case_id,
                    native_source_pin=args.native_source_pin,
                    dataset_root=args.dataset_root,
                    monolithic_vtu=None,
                    multipart=True,
                    surface_area_npy=case_inputs.surface_area_npy,
                    surface_prediction_manifest=(
                        case_inputs.surface_prediction_manifest
                    ),
                    volume_prediction_manifest=case_inputs.volume_prediction_manifest,
                    output=core_output,
                    maximum_prediction_chunk_rows=(
                        args.maximum_prediction_chunk_rows
                    ),
                    io_chunk_bytes=args.io_chunk_bytes,
                )
            )
            diagnostic_identity = _run_diagnostic_case(
                SimpleNamespace(
                    case_id=case_inputs.case_id,
                    native_source_pin=args.native_source_pin,
                    dataset_root=args.dataset_root,
                    autocfd5_profile=args.autocfd5_profile,
                    cp_support_json=case_inputs.cp_support_json,
                    velocity_mapping_json=case_inputs.velocity_mapping_json,
                    velocity_receipt_json=case_inputs.velocity_receipt_json,
                    surface_prediction_manifest=(
                        case_inputs.surface_prediction_manifest
                    ),
                    volume_prediction_manifest=case_inputs.volume_prediction_manifest,
                    multipart=True,
                    monolithic_vtu=None,
                    output=diagnostic_output,
                    maximum_prediction_chunk_rows=(
                        args.maximum_prediction_chunk_rows
                    ),
                    io_chunk_bytes=args.io_chunk_bytes,
                )
            )
            core_document = _generated_evidence_document(
                core_output,
                core_identity,
                case_id=case_inputs.case_id,
                label=f"{case_inputs.case_id} core evidence",
            )
            diagnostic_document = _generated_evidence_document(
                diagnostic_output,
                diagnostic_identity,
                case_id=case_inputs.case_id,
                label=f"{case_inputs.case_id} diagnostic evidence",
            )
            core_prediction_identities = _prediction_evidence_identities(
                core_document,
                case_id=case_inputs.case_id,
                diagnostic=False,
            )
            diagnostic_prediction_identities = _prediction_evidence_identities(
                diagnostic_document,
                case_id=case_inputs.case_id,
                diagnostic=True,
            )
            if core_prediction_identities != diagnostic_prediction_identities:
                raise RealReferenceDriverError(
                    f"{case_inputs.case_id} core and diagnostic evaluations used "
                    "different prediction manifest, chunk, or entity identities"
                )
            case_results.append(
                {
                    "case_id": case_inputs.case_id,
                    "pinned_volume_part_count": len(
                        pin.case(case_inputs.case_id).volume_parts
                    ),
                    "transport": "verified_ordered_multipart_byte_stream",
                    "cross_evaluator_prediction_identity_verified": True,
                    "core_evidence": {
                        "file": core_output.relative_to(staging).as_posix(),
                        **core_identity,
                    },
                    "diagnostic_evidence": {
                        "file": diagnostic_output.relative_to(staging).as_posix(),
                        **diagnostic_identity,
                    },
                }
            )
        if _sha256_file(config_path) != config_sha256:
            raise RealReferenceDriverError(
                "case-input config changed after it was parsed"
            )
        receipt: dict[str, object] = {
            "schema": OUTPUT_SCHEMA,
            "schema_version": 2,
            "status": OUTPUT_STATUS,
            "official_submission": False,
            "scoring_contract_active": False,
            "owner_scientific_approval": False,
            "independent_participant_dry_run": False,
            "downloads_performed": False,
            "fabricated_scientific_results": False,
            "native_source_pin_sha256": _sha256_file(args.native_source_pin),
            "case_input_config_sha256": config_sha256,
            "volume_weighting": "one_per_native_cell",
            "geometric_cell_volume_weights_used": False,
            "cases": case_results,
        }
        receipt_path = staging / "validation-receipt.json"
        receipt_path.write_text(
            json.dumps(
                receipt,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        if output.exists():
            raise RealReferenceDriverError(f"output appeared during run: {output}")
        if _sha256_file(config_path) != config_sha256:
            raise RealReferenceDriverError(
                "case-input config changed before evidence publication"
            )
        os.replace(staging, output)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        receipt = run(args)
    except (
        CpCaseSupportError,
        DrivAerCandidateEvaluatorError,
        DrivAerDiagnosticEvaluatorError,
        DrivAerNativeSurfaceError,
        NativeSourceError,
        PredictionChunkError,
        RealReferenceDriverError,
        OSError,
    ) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "cases": [case["case_id"] for case in receipt["cases"]],
                "receipt": str(args.output.resolve() / "validation-receipt.json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CASE_INPUT_KEYS",
    "INPUT_SCHEMA",
    "OUTPUT_SCHEMA",
    "OUTPUT_STATUS",
    "REQUIRED_CASE_PART_COUNTS",
    "RealCaseInputs",
    "RealReferenceDriverError",
    "load_case_inputs",
    "main",
    "parse_args",
    "run",
]
