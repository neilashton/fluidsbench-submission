#!/usr/bin/env python3
"""Aggregate deterministic DrivAerML native-cell volume-weight receipts.

Complete mode is the default and requires exactly one generator receipt for
all 484 immutable public cases.  A partial pilot is accepted only when the
caller explicitly lists every intended pilot case with ``--pilot-case``; its
output is permanently labelled incomplete and non-public.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference.drivaerml.volume_weights import (  # noqa: E402
    DEFAULT_COPY_CHUNK_SIZE,
    DEFAULT_SOURCE_VERIFICATION_CHUNK_BYTES,
    RECEIPT_SCHEMA,
    RECEIPT_SCHEMA_VERSION,
    algorithm_settings,
)


DEFAULT_NATIVE_SOURCE_PIN = (
    ROOT / "benchmark-specs" / "drivaerml" / "proposal" / "native-source-pin.json"
)
OFFICIAL_NATIVE_SOURCE_PIN_SHA256 = (
    "4fc9077f8f23f4994c98f4d0e7a17aef7b998de4c996638e3a8a616b6d923fdd"
)
OFFICIAL_REVISION = "7a5c0948ce27be709b1116a3a190f806e7a8f79f"
OFFICIAL_UNAVAILABLE_RUNS = frozenset(
    {167, 211, 218, 221, 248, 282, 291, 295, 316, 325, 329, 364, 370, 376, 403, 473}
)
OFFICIAL_CASE_IDS = tuple(
    f"run_{run_number}"
    for run_number in range(1, 501)
    if run_number not in OFFICIAL_UNAVAILABLE_RUNS
)

PINNED_VERSIONS = {
    "python": "3.12.13",
    "numpy": "2.2.6",
    "vtk": "9.5.2",
    "vtk_source": "vtk version 9.5.2",
}
PINNED_ALGORITHM = algorithm_settings()
PINNED_ALGORITHM_SHA256 = hashlib.sha256(
    json.dumps(PINNED_ALGORITHM, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
).hexdigest()

_CASE_RE = re.compile(r"run_([1-9][0-9]*)")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_WINDOWS_ABSOLUTE_RE = re.compile(r"[A-Za-z]:[\\/]")


class VolumeWeightAggregateError(ValueError):
    """Raised when volume-weight receipt coverage or content is invalid."""


def sha256_file(path: Path, *, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_bytes):
            digest.update(block)
    return digest.hexdigest()


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VolumeWeightAggregateError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except VolumeWeightAggregateError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VolumeWeightAggregateError(f"cannot read valid {label} JSON: {path}") from error
    if not isinstance(value, dict):
        raise VolumeWeightAggregateError(f"{label} must be a JSON object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VolumeWeightAggregateError(f"{label} must be an object")
    return value


def _exact_keys(
    value: object, expected: Iterable[str], label: str
) -> Mapping[str, Any]:
    result = _mapping(value, label)
    expected_set = set(expected)
    if set(result) != expected_set:
        missing = sorted(expected_set - set(result))
        unexpected = sorted(set(result) - expected_set)
        raise VolumeWeightAggregateError(
            f"{label} keys differ from schema "
            f"(missing={missing}, unexpected={unexpected})"
        )
    return result


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise VolumeWeightAggregateError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise VolumeWeightAggregateError(f"{label} must be an integer >= {minimum}")
    return value


def _finite(value: object, label: str, *, positive: bool = False) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise VolumeWeightAggregateError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise VolumeWeightAggregateError(f"{label} must be finite")
    if positive and result <= 0.0:
        raise VolumeWeightAggregateError(f"{label} must be strictly positive")
    return result


def _sha256(value: object, label: str) -> str:
    result = _string(value, label)
    if _SHA256_RE.fullmatch(result) is None:
        raise VolumeWeightAggregateError(f"{label} must be a lowercase SHA-256 digest")
    return result


def _case_number(case_id: str) -> int:
    match = _CASE_RE.fullmatch(case_id)
    if match is None:
        raise VolumeWeightAggregateError(f"invalid canonical case ID {case_id!r}")
    return int(match.group(1))


def _ordered_cases(case_ids: Sequence[str], label: str) -> tuple[str, ...]:
    result = tuple(_string(case_id, label) for case_id in case_ids)
    if not result:
        raise VolumeWeightAggregateError(f"{label} cannot be empty")
    for case_id in result:
        _case_number(case_id)
    if len(result) != len(set(result)):
        raise VolumeWeightAggregateError(f"{label} must be unique")
    if tuple(sorted(result, key=_case_number)) != result:
        raise VolumeWeightAggregateError(f"{label} must use increasing run-number order")
    return result


def _relative_path(value: object, label: str) -> str:
    result = _string(value, label).replace("\\", "/")
    if (
        result.startswith("/")
        or _WINDOWS_ABSOLUTE_RE.match(result)
        or ".." in result.split("/")
    ):
        raise VolumeWeightAggregateError(f"{label} must be a relative public path")
    return result


def _basename(value: object, label: str, *, suffix: str) -> str:
    result = _relative_path(value, label)
    if "/" in result or not result.endswith(suffix):
        raise VolumeWeightAggregateError(f"{label} must be a basename ending in {suffix}")
    return result


def _validate_pin(
    path: Path,
    *,
    official_case_ids: tuple[str, ...],
    expected_pin_sha256: str | None,
) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]], str]:
    digest = sha256_file(path)
    if expected_pin_sha256 is not None and digest != expected_pin_sha256:
        raise VolumeWeightAggregateError(
            "native source pin SHA-256 mismatch: "
            f"expected {expected_pin_sha256}, got {digest}"
        )
    pin = _read_json(path, "native source pin")
    if pin.get("schema") != "drivaerml-fluidsbench-public-native-source-pin-v1":
        raise VolumeWeightAggregateError("unexpected native source pin schema")
    if pin.get("schema_version") != 1:
        raise VolumeWeightAggregateError("unexpected native source pin schema_version")
    repository = _exact_keys(
        pin.get("repository"),
        {"provider", "repo_id", "repo_type", "revision"},
        "native source pin repository",
    )
    if dict(repository) != {
        "provider": "Hugging Face Hub",
        "repo_id": "neashton/drivaerml",
        "repo_type": "dataset",
        "revision": OFFICIAL_REVISION,
    }:
        raise VolumeWeightAggregateError("native source repository identity is not frozen")

    cases = pin.get("cases")
    if not isinstance(cases, list) or len(cases) != len(official_case_ids):
        raise VolumeWeightAggregateError("native source pin case count is not exact")
    by_case: dict[str, Mapping[str, Any]] = {}
    ordered_ids: list[str] = []
    volume_part_count = 0
    for position, value in enumerate(cases):
        case = _mapping(value, f"native source pin case {position}")
        case_id = _string(case.get("case_id"), "native source pin case_id")
        if case_id in by_case:
            raise VolumeWeightAggregateError(f"duplicate native source case {case_id}")
        run_number = _integer(case.get("run_number"), f"{case_id} run_number", minimum=1)
        if run_number != _case_number(case_id):
            raise VolumeWeightAggregateError(f"{case_id} run_number differs from case ID")
        volume = _exact_keys(
            case.get("volume"),
            {
                "assembly",
                "identity_contract",
                "logical_path_after_assembly",
                "part_count",
                "parts",
                "total_size_bytes",
            },
            f"{case_id} volume pin",
        )
        logical_path = _relative_path(
            volume["logical_path_after_assembly"], f"{case_id} logical volume path"
        )
        if logical_path != f"{case_id}/volume_{run_number}.vtu":
            raise VolumeWeightAggregateError(f"{case_id} logical volume path is not canonical")
        parts = volume["parts"]
        if not isinstance(parts, list) or len(parts) not in {2, 3}:
            raise VolumeWeightAggregateError(f"{case_id} must contain two or three VTU parts")
        if volume["part_count"] != len(parts):
            raise VolumeWeightAggregateError(f"{case_id} volume part_count is inconsistent")
        part_size_sum = 0
        for part_index, raw_part in enumerate(parts):
            part = _mapping(raw_part, f"{case_id} volume part {part_index}")
            if part.get("part_index") != part_index:
                raise VolumeWeightAggregateError(f"{case_id} volume part order is invalid")
            part_path = _relative_path(
                part.get("path"), f"{case_id} volume part {part_index} path"
            )
            if part_path != f"{logical_path}.{part_index:02d}.part":
                raise VolumeWeightAggregateError(f"{case_id} volume part path is invalid")
            _sha256(
                part.get("lfs_sha256"), f"{case_id} volume part {part_index} SHA-256"
            )
            part_size_sum += _integer(
                part.get("size_bytes"),
                f"{case_id} volume part {part_index} size",
                minimum=1,
            )
        if volume["total_size_bytes"] != part_size_sum:
            raise VolumeWeightAggregateError(f"{case_id} total volume size is inconsistent")
        volume_part_count += len(parts)
        by_case[case_id] = case
        ordered_ids.append(case_id)
    if tuple(ordered_ids) != official_case_ids:
        raise VolumeWeightAggregateError("native source pin case order/set is not exact")

    scope = _mapping(pin.get("case_scope"), "native source pin case_scope")
    if scope.get("case_count") != len(official_case_ids):
        raise VolumeWeightAggregateError("native source pin case_scope count is inconsistent")
    if official_case_ids == OFFICIAL_CASE_IDS:
        if (
            scope.get("run_number_min") != 1
            or scope.get("run_number_max") != 500
            or scope.get("unavailable_or_held_back_run_numbers")
            != sorted(OFFICIAL_UNAVAILABLE_RUNS)
        ):
            raise VolumeWeightAggregateError("official 484-case scope is not exact")
        totals = _mapping(pin.get("totals"), "native source pin totals")
        if (
            totals.get("logical_volume_count") != len(OFFICIAL_CASE_IDS)
            or totals.get("volume_part_file_count") != volume_part_count
            or totals.get("reconstructed_volume_bytes")
            != sum(
                int(_mapping(case["volume"], "volume")["total_size_bytes"])
                for case in by_case.values()
            )
        ):
            raise VolumeWeightAggregateError("official volume totals are inconsistent")
    return pin, by_case, digest


def _validate_reader_audit(value: object, case_id: str) -> dict[str, Any]:
    audit = _exact_keys(
        value,
        {
            "disabled_point_array_count",
            "disabled_point_arrays",
            "disabled_cell_array_count",
            "disabled_cell_arrays",
        },
        f"{case_id} reader_audit",
    )
    result: dict[str, Any] = {}
    for kind in ("point", "cell"):
        arrays = audit[f"disabled_{kind}_arrays"]
        if (
            not isinstance(arrays, list)
            or any(not isinstance(name, str) or not name for name in arrays)
            or len(arrays) != len(set(arrays))
        ):
            raise VolumeWeightAggregateError(
                f"{case_id} disabled {kind} arrays must be unique strings"
            )
        count = _integer(
            audit[f"disabled_{kind}_array_count"],
            f"{case_id} disabled {kind} array count",
        )
        if count != len(arrays):
            raise VolumeWeightAggregateError(
                f"{case_id} disabled {kind} array count is inconsistent"
            )
        result[f"disabled_{kind}_array_count"] = count
        result[f"disabled_{kind}_arrays"] = arrays
    if not {"pMeanTrim", "UMeanTrim"}.issubset(result["disabled_cell_arrays"]):
        raise VolumeWeightAggregateError(
            f"{case_id} geometry reader did not disable required CellData arrays"
        )
    return result


def _validate_native_source_binding(
    value: object,
    *,
    case_id: str,
    pinned_case: Mapping[str, Any],
    pin_sha256: str,
    repository: Mapping[str, Any],
) -> dict[str, Any]:
    binding = _exact_keys(
        value,
        {"pin", "case_id", "logical_volume", "verification"},
        f"{case_id} native_source_binding",
    )
    pin = _exact_keys(
        binding["pin"],
        {"sha256", "repository_id", "repository_revision"},
        f"{case_id} native source pin binding",
    )
    if _sha256(pin["sha256"], f"{case_id} bound pin SHA-256") != pin_sha256:
        raise VolumeWeightAggregateError(
            f"{case_id} receipt is bound to a different native-source pin"
        )
    if (
        pin["repository_id"] != repository["repo_id"]
        or pin["repository_revision"] != repository["revision"]
    ):
        raise VolumeWeightAggregateError(
            f"{case_id} receipt repository identity is not pinned"
        )
    if binding["case_id"] != case_id:
        raise VolumeWeightAggregateError(
            f"{case_id} native source binding has a different case_id"
        )

    volume_pin = _mapping(pinned_case.get("volume"), f"{case_id} volume pin")
    logical = _exact_keys(
        binding["logical_volume"],
        {"path", "size_bytes", "ordered_verified_segments"},
        f"{case_id} logical volume binding",
    )
    logical_path = _relative_path(logical["path"], f"{case_id} logical volume path")
    if logical_path != volume_pin["logical_path_after_assembly"]:
        raise VolumeWeightAggregateError(
            f"{case_id} receipt logical volume path is not pinned"
        )
    logical_size = _integer(
        logical["size_bytes"], f"{case_id} logical volume size", minimum=1
    )
    if logical_size != volume_pin["total_size_bytes"]:
        raise VolumeWeightAggregateError(
            f"{case_id} receipt logical volume size is not pinned"
        )

    raw_segments = logical["ordered_verified_segments"]
    pinned_parts = volume_pin["parts"]
    if not isinstance(raw_segments, list) or len(raw_segments) != len(pinned_parts):
        raise VolumeWeightAggregateError(
            f"{case_id} receipt must verify every ordered pinned volume segment"
        )
    segments: list[dict[str, int | str]] = []
    for part_index, (raw_segment, raw_part) in enumerate(
        zip(raw_segments, pinned_parts, strict=True)
    ):
        segment = _exact_keys(
            raw_segment,
            {"part_index", "size_bytes", "sha256"},
            f"{case_id} verified segment {part_index}",
        )
        part = _mapping(raw_part, f"{case_id} pinned part {part_index}")
        verified_index = _integer(
            segment["part_index"],
            f"{case_id} verified segment {part_index} index",
        )
        if verified_index != part_index:
            raise VolumeWeightAggregateError(
                f"{case_id} verified segment order/index is not exact"
            )
        size = _integer(
            segment["size_bytes"],
            f"{case_id} verified segment {part_index} size",
            minimum=1,
        )
        digest = _sha256(
            segment["sha256"],
            f"{case_id} verified segment {part_index} SHA-256",
        )
        if size != part["size_bytes"] or digest != part["lfs_sha256"]:
            raise VolumeWeightAggregateError(
                f"{case_id} verified segment {part_index} is not pinned"
            )
        segments.append(
            {"part_index": verified_index, "size_bytes": size, "sha256": digest}
        )

    verification = _exact_keys(
        binding["verification"],
        {"method", "timing", "vtk_input", "post_vtk_fstat"},
        f"{case_id} source verification declaration",
    )
    expected_verification = {
        "method": "exact_ordered_segment_size_and_sha256",
        "timing": "completed_before_vtk_geometry_reader",
        "vtk_input": "retained_verified_file_descriptor",
        "post_vtk_fstat": "unchanged",
    }
    if dict(verification) != expected_verification:
        raise VolumeWeightAggregateError(
            f"{case_id} source verification method/timing is not exact"
        )
    return {
        "pin": {
            "sha256": pin_sha256,
            "repository_id": repository["repo_id"],
            "repository_revision": repository["revision"],
        },
        "case_id": case_id,
        "logical_volume": {
            "path": logical_path,
            "size_bytes": logical_size,
            "ordered_verified_segments": segments,
        },
        "verification": expected_verification,
    }


def _validate_receipt(
    receipt: Mapping[str, Any],
    *,
    receipt_sha256: str,
    pinned_case: Mapping[str, Any],
    pin_sha256: str,
    repository: Mapping[str, Any],
) -> dict[str, Any]:
    expected_root_keys = {
        "schema",
        "schema_version",
        "status",
        "case_id",
        "native_source_binding",
        "output",
        "versions",
        "algorithm",
        "execution",
        "reader_audit",
    }
    _exact_keys(receipt, expected_root_keys, "volume-weight receipt")
    if (
        receipt["schema"] != RECEIPT_SCHEMA
        or receipt["schema_version"] != RECEIPT_SCHEMA_VERSION
    ):
        raise VolumeWeightAggregateError("unexpected volume-weight receipt schema")
    if receipt["status"] != "candidate_exact_native_source_verified_before_vtk":
        raise VolumeWeightAggregateError("volume-weight receipt status is not exact")
    case_id = _string(receipt["case_id"], "volume-weight receipt case_id")
    if pinned_case.get("case_id") != case_id:
        raise VolumeWeightAggregateError(f"receipt {case_id} differs from pinned case")
    source_binding = _validate_native_source_binding(
        receipt["native_source_binding"],
        case_id=case_id,
        pinned_case=pinned_case,
        pin_sha256=pin_sha256,
        repository=repository,
    )

    versions = _exact_keys(
        receipt["versions"], PINNED_VERSIONS, f"{case_id} versions"
    )
    if dict(versions) != PINNED_VERSIONS:
        raise VolumeWeightAggregateError(f"{case_id} dependency versions are not pinned")
    if receipt["algorithm"] != PINNED_ALGORITHM:
        raise VolumeWeightAggregateError(f"{case_id} algorithm settings are not exact")
    execution = _exact_keys(
        receipt["execution"],
        {"copy_chunk_size", "source_verification_chunk_bytes"},
        f"{case_id} execution",
    )
    if execution["copy_chunk_size"] != DEFAULT_COPY_CHUNK_SIZE:
        raise VolumeWeightAggregateError(f"{case_id} copy_chunk_size is not pinned")
    if (
        execution["source_verification_chunk_bytes"]
        != DEFAULT_SOURCE_VERIFICATION_CHUNK_BYTES
    ):
        raise VolumeWeightAggregateError(
            f"{case_id} source_verification_chunk_bytes is not pinned"
        )
    reader_audit = _validate_reader_audit(receipt["reader_audit"], case_id)

    output = _exact_keys(
        receipt["output"],
        {
            "file",
            "dtype",
            "shape",
            "size_bytes",
            "sha256",
            "cell_count",
            "volume_sum_m3",
            "volume_min_m3",
            "volume_max_m3",
        },
        f"{case_id} output",
    )
    output_file = _basename(
        output["file"], f"{case_id} output volume weights", suffix=".npy"
    )
    if output["dtype"] != "<f8":
        raise VolumeWeightAggregateError(f"{case_id} output dtype must be <f8")
    cell_count = _integer(output["cell_count"], f"{case_id} cell_count", minimum=1)
    if output["shape"] != [cell_count]:
        raise VolumeWeightAggregateError(f"{case_id} output shape/count are inconsistent")
    output_size = _integer(
        output["size_bytes"], f"{case_id} output size", minimum=1
    )
    if output_size != 128 + 8 * cell_count:
        raise VolumeWeightAggregateError(f"{case_id} NPY size/count are inconsistent")
    output_sha256 = _sha256(output["sha256"], f"{case_id} output SHA-256")
    volume_sum = _finite(
        output["volume_sum_m3"], f"{case_id} volume sum", positive=True
    )
    volume_min = _finite(
        output["volume_min_m3"], f"{case_id} volume minimum", positive=True
    )
    volume_max = _finite(
        output["volume_max_m3"], f"{case_id} volume maximum", positive=True
    )
    if volume_min > volume_max:
        raise VolumeWeightAggregateError(f"{case_id} volume minimum exceeds maximum")
    lower = volume_min * cell_count
    upper = volume_max * cell_count
    if not math.isfinite(lower) or not math.isfinite(upper):
        raise VolumeWeightAggregateError(
            f"{case_id} count/minimum/maximum product is non-finite"
        )
    tolerance = max(abs(volume_sum), abs(lower), abs(upper)) * 1.0e-12
    if volume_sum < lower - tolerance or volume_sum > upper + tolerance:
        raise VolumeWeightAggregateError(
            f"{case_id} volume sum is inconsistent with count/minimum/maximum"
        )

    return {
        "case_id": case_id,
        "receipt_sha256": receipt_sha256,
        "native_source_binding": source_binding,
        "output": {
            "file": output_file,
            "dtype": "<f8",
            "shape": [cell_count],
            "cell_count": cell_count,
            "size_bytes": output_size,
            "sha256": output_sha256,
            "volume_sum_m3": volume_sum,
            "volume_min_m3": volume_min,
            "volume_max_m3": volume_max,
        },
        "reader_audit": reader_audit,
    }


def _assert_no_absolute_paths(value: object, label: str = "evidence") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_no_absolute_paths(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_absolute_paths(item, f"{label}[{index}]")
    elif isinstance(value, str):
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or _WINDOWS_ABSOLUTE_RE.match(value):
            raise VolumeWeightAggregateError(f"{label} contains an absolute path")


def aggregate_volume_weight_receipts(
    *,
    native_source_pin_path: Path,
    receipt_paths: Sequence[Path],
    pilot_case_ids: Sequence[str] | None = None,
    official_case_ids: Sequence[str] = OFFICIAL_CASE_IDS,
    expected_pin_sha256: str | None = OFFICIAL_NATIVE_SOURCE_PIN_SHA256,
) -> dict[str, Any]:
    """Validate receipts and return deterministic complete or pilot evidence.

    The CLI uses the production defaults.  ``official_case_ids`` and
    ``expected_pin_sha256`` are injectable only for small synthetic tests.
    """

    official_cases = _ordered_cases(official_case_ids, "official case IDs")
    pin, pinned_cases, pin_sha256 = _validate_pin(
        Path(native_source_pin_path),
        official_case_ids=official_cases,
        expected_pin_sha256=expected_pin_sha256,
    )
    repository = _mapping(pin["repository"], "native source pin repository")
    pilot = pilot_case_ids is not None
    if pilot:
        expected_cases = _ordered_cases(pilot_case_ids or (), "pilot case IDs")
        if not set(expected_cases).issubset(official_cases):
            raise VolumeWeightAggregateError("pilot cases must be official pinned cases")
        if expected_cases == official_cases:
            raise VolumeWeightAggregateError(
                "pilot mode must be a strict subset; omit --pilot-case for complete mode"
            )
    else:
        expected_cases = official_cases

    receipts_by_case: dict[str, dict[str, Any]] = {}
    for raw_path in receipt_paths:
        path = Path(raw_path)
        receipt_sha256 = sha256_file(path)
        receipt = _read_json(path, "volume-weight receipt")
        case_id = _string(receipt.get("case_id"), "volume-weight receipt case_id")
        if case_id in receipts_by_case:
            raise VolumeWeightAggregateError(f"duplicate volume-weight receipt for {case_id}")
        if case_id not in pinned_cases:
            raise VolumeWeightAggregateError(f"unexpected volume-weight receipt case {case_id}")
        receipts_by_case[case_id] = _validate_receipt(
            receipt,
            receipt_sha256=receipt_sha256,
            pinned_case=pinned_cases[case_id],
            pin_sha256=pin_sha256,
            repository=repository,
        )
    if set(receipts_by_case) != set(expected_cases):
        missing = sorted(set(expected_cases) - set(receipts_by_case), key=_case_number)
        unexpected = sorted(set(receipts_by_case) - set(expected_cases), key=_case_number)
        raise VolumeWeightAggregateError(
            "volume-weight receipts must cover the requested case set exactly once "
            f"(missing={missing}, unexpected={unexpected})"
        )
    records = [receipts_by_case[case_id] for case_id in expected_cases]

    try:
        aggregate_volume_sum = math.fsum(
            row["output"]["volume_sum_m3"] for row in records
        )
    except OverflowError as error:
        raise VolumeWeightAggregateError("aggregate volume sum overflowed") from error
    if not math.isfinite(aggregate_volume_sum) or aggregate_volume_sum <= 0.0:
        raise VolumeWeightAggregateError("aggregate volume sum must be finite and positive")
    evidence: dict[str, Any] = {
        "schema": "drivaerml-volume-cell-weight-receipt-aggregate-v1",
        "mode": "partial_pilot" if pilot else "complete",
        "status": (
            "incomplete_non_public_pilot"
            if pilot
            else "complete_all_official_cases_candidate_evidence"
        ),
        "complete": not pilot,
        "public_evidence_eligible": not pilot,
        "activation_status": "does_not_activate_scoring_contract",
        "case_count": len(records),
        "official_case_count": len(official_cases),
        "omitted_official_case_count": len(official_cases) - len(records),
        "case_order": "native_source_pin_increasing_run_number",
        "source": {
            "dataset": {
                "provider": repository["provider"],
                "repo_id": repository["repo_id"],
                "revision": repository["revision"],
            },
            "native_source_pin": {
                "schema": pin["schema"],
                "sha256": pin_sha256,
            },
            "assembled_vtu_identity": (
                "exact_ordered_part_segment_size_and_sha256_verified_before_vtk"
            ),
        },
        "dependencies": dict(PINNED_VERSIONS),
        "algorithm": {
            "sha256": PINNED_ALGORITHM_SHA256,
            "settings": PINNED_ALGORITHM,
            "execution": {
                "copy_chunk_size": DEFAULT_COPY_CHUNK_SIZE,
                "source_verification_chunk_bytes": (
                    DEFAULT_SOURCE_VERIFICATION_CHUNK_BYTES
                ),
            },
        },
        "aggregate": {
            "cell_count": sum(row["output"]["cell_count"] for row in records),
            "source_vtu_size_bytes": sum(
                row["native_source_binding"]["logical_volume"]["size_bytes"]
                for row in records
            ),
            "output_size_bytes": sum(row["output"]["size_bytes"] for row in records),
            "volume_sum_m3": aggregate_volume_sum,
            "volume_min_m3": min(row["output"]["volume_min_m3"] for row in records),
            "volume_max_m3": max(row["output"]["volume_max_m3"] for row in records),
            "all_outputs_dtype": "<f8",
            "all_outputs_one_dimensional": True,
            "all_values_strictly_positive_finite": True,
        },
        "cases": records,
    }
    if pilot:
        evidence["pilot_warning"] = (
            "incomplete subset; not a public scoring-support manifest or activation artifact"
        )
    _assert_no_absolute_paths(evidence)
    return evidence


def write_evidence(path: Path, evidence: Mapping[str, Any]) -> None:
    """Write stable compact JSON with one terminal newline."""

    _assert_no_absolute_paths(evidence)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--native-source-pin", type=Path, default=DEFAULT_NATIVE_SOURCE_PIN
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--pilot-case",
        action="append",
        help=(
            "explicit partial-pilot case ID; repeat for every intended case. "
            "Any use makes output incomplete and non-public"
        ),
    )
    parser.add_argument(
        "receipts",
        type=Path,
        nargs="+",
        help="one generate_volume_weights JSON receipt per requested case",
    )
    args = parser.parse_args()
    evidence = aggregate_volume_weight_receipts(
        native_source_pin_path=args.native_source_pin,
        receipt_paths=args.receipts,
        pilot_case_ids=args.pilot_case,
    )
    write_evidence(args.output, evidence)
    print(
        json.dumps(
            {
                "case_count": evidence["case_count"],
                "mode": evidence["mode"],
                "status": evidence["status"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
