#!/usr/bin/env python3
"""Generate the retained DrivAerML relative-v3 per-series identity index.

This release-maintainer tool intentionally reads the producer workspace.  The
ordinary submission validator reads only its retained output and never needs
the producer workspace or network access.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any, Mapping


DATASET_REVISION = "7a5c0948ce27be709b1116a3a190f806e7a8f79f"
NATIVE_SOURCE_PIN_SHA256 = (
    "4fc9077f8f23f4994c98f4d0e7a17aef7b998de4c996638e3a8a616b6d923fdd"
)
CONTRACT_ID = "drivaerml-relative-diagnostics-v3-candidate"
VELOCITY_FAMILY = "drivaerml-velocity-relative-v3"
CP_FAMILY = "drivaerml_cp_relative_v1"
VELOCITY_STATIONS = (
    "V1", "V2", "V3", "V4", "V5", "V6",
    "U1", "U2", "U3", "U4", "U5", "U6",
    "L1", "R1", "R2", "R3",
)
CP_ALIAS_STATIONS = ("upperbody_centerline", "underbody_centerline")
CP_MOVING_STATIONS = (
    "sidewall_front_wheelhouse_relative",
    "front_left_wheelhouse_relative",
)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ZERO_SHA256 = "0" * 64

MANIFESTS = {
    "velocity_placement": {
        "producer_path": (
            "velocity_support_v3/production_campaign_v1/aggregate/"
            "relative-velocity-v3-production-all484-inputs-v1.json"
        ),
        "retained_path": (
            "benchmark-specs/drivaerml/support/relative-v3/manifests/"
            "velocity-placement-all484-v1.json"
        ),
        "sha256": "70627d6af9e6b254739b29d54d856b470d6152066e09a1097ebe20c034179925",
        "schema": "drivaerml-relative-velocity-v3-production-input-manifest-v1",
        "schema_version": 1,
    },
    "velocity_mapping": {
        "producer_path": (
            "velocity_mapping_v3/aggregate/"
            "relative-velocity-v3-mapping-all484-v1.json"
        ),
        "retained_path": (
            "benchmark-specs/drivaerml/support/relative-v3/manifests/"
            "velocity-mapping-all484-v1.json"
        ),
        "sha256": "9b88c36e2268bf72c9baec9418ef2d9afc9faba1d98c9c12ed73b79e683a6a3d",
        "schema": "drivaerml-velocity-relative-v3-mapping-aggregate-v1",
        "schema_version": 1,
    },
    "cp": {
        "producer_path": (
            "cp_support/campaign_v3/aggregate_v3/all484/"
            "relative-cp-native-support-manifest-v3.json"
        ),
        "retained_path": (
            "benchmark-specs/drivaerml/support/relative-v3/manifests/"
            "cp-native-support-all484-v3.json"
        ),
        "sha256": "4e6a4c3495ea4938895868162480dcb20b5bbea42114c94013a2c76e26128c90",
        "schema": "drivaerml-relative-cp-native-support-manifest-v3",
        "schema_version": 3,
    },
}


class IndexError(ValueError):
    """Raised when producer evidence does not replay exactly."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def cp_canonical_bytes(value: object) -> bytes:
    """Replay the Cp producer's canonical JSON convention (including LF)."""

    return canonical_bytes(value) + b"\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def regular(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise IndexError(f"{label} must be a non-symlink regular file: {path}")
    return path


def load_json(path: Path, label: str) -> dict[str, Any]:
    regular(path, label)
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IndexError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise IndexError(f"{label} must be a JSON object")
    return value


def digest(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise IndexError(f"{label} must be a lowercase SHA-256")
    if value == ZERO_SHA256:
        raise IndexError(f"{label} must not be the all-zero sentinel")
    return value


def exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise IndexError(
            f"{label} keys differ (missing={sorted(expected - set(value))}, "
            f"unexpected={sorted(set(value) - expected)})"
        )


def manifest_document(
    repo_root: Path,
    producer_root: Path,
    role: str,
) -> dict[str, Any]:
    binding = MANIFESTS[role]
    producer_path = regular(
        producer_root / str(binding["producer_path"]), f"{role} producer manifest"
    )
    retained_path = regular(
        repo_root / str(binding["retained_path"]), f"{role} retained manifest"
    )
    producer_bytes = producer_path.read_bytes()
    retained_bytes = retained_path.read_bytes()
    if producer_bytes != retained_bytes:
        raise IndexError(f"{role} retained bytes differ from producer bytes")
    actual = sha256_bytes(retained_bytes)
    if actual != binding["sha256"]:
        raise IndexError(f"{role} manifest SHA-256 differs: {actual}")
    document = load_json(retained_path, f"{role} retained manifest")
    if (
        document.get("schema") != binding["schema"]
        or document.get("schema_version") != binding["schema_version"]
        or document.get("dataset_id") != "drivaerml"
        or document.get("public_dataset_revision") != DATASET_REVISION
    ):
        raise IndexError(f"{role} manifest declaration differs")
    return document


def case_rows(document: Mapping[str, object], role: str) -> list[dict[str, Any]]:
    raw = document.get("cases")
    if not isinstance(raw, list) or not all(isinstance(row, dict) for row in raw):
        raise IndexError(f"{role} cases must be an object array")
    rows = [dict(row) for row in raw]
    identifiers = [row.get("case_id") for row in rows]
    if len(rows) != 484 or len(set(identifiers)) != 484:
        raise IndexError(f"{role} must contain exactly 484 unique cases")
    return rows


def official_case_ids(repo_root: Path) -> list[str]:
    path = regular(
        repo_root / "benchmark-specs/drivaerml/proposal/native-source-pin.json",
        "official native-source pin",
    )
    if sha256_file(path) != NATIVE_SOURCE_PIN_SHA256:
        raise IndexError("official native-source pin SHA-256 differs")
    document = load_json(path, "official native-source pin")
    raw = document.get("cases")
    if not isinstance(raw, list) or not all(isinstance(row, dict) for row in raw):
        raise IndexError("official native-source pin cases differ")
    result = [row.get("case_id") for row in raw]
    if (
        len(result) != 484
        or len(set(result)) != 484
        or not all(isinstance(value, str) for value in result)
    ):
        raise IndexError("official native-source pin case coverage differs")
    return result  # type: ignore[return-value]


def profile_coordinate_hashes(csv_path: Path) -> dict[str, str]:
    regular(csv_path, "velocity coordinate CSV")
    hashers = {station: hashlib.sha256() for station in VELOCITY_STATIONS}
    counts = {station: 0 for station in VELOCITY_STATIONS}
    with csv_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        expected_fields = [
            "family_id", "placement_mode", "profile_id", "sample_index",
            "point_count", "line_fraction", "distance_m", "x_m", "y_m", "z_m",
        ]
        if reader.fieldnames != expected_fields:
            raise IndexError("velocity coordinate CSV header differs")
        for row in reader:
            station = row["profile_id"]
            if station not in hashers:
                raise IndexError(f"velocity coordinate CSV station differs: {station!r}")
            if row["family_id"] != VELOCITY_FAMILY or row["placement_mode"] != "relative":
                raise IndexError("velocity coordinate CSV namespace differs")
            if int(row["sample_index"]) != counts[station]:
                raise IndexError(f"velocity coordinate CSV {station} order differs")
            hashers[station].update(struct.pack(
                ">ddd", float(row["x_m"]), float(row["y_m"]), float(row["z_m"])
            ))
            counts[station] += 1
    expected_counts = {
        **{station: 201 for station in VELOCITY_STATIONS[:6]},
        **{station: 301 for station in VELOCITY_STATIONS[6:12]},
        "L1": 651,
        "R1": 31,
        "R2": 31,
        "R3": 31,
    }
    if counts != expected_counts:
        raise IndexError(f"velocity coordinate CSV counts differ: {counts}")
    return {station: hashers[station].hexdigest() for station in VELOCITY_STATIONS}


def velocity_series(
    producer_root: Path,
    case_id: str,
    placement_row: Mapping[str, object],
    mapping_row: Mapping[str, object],
) -> list[dict[str, str]]:
    case_root = producer_root / "velocity_support_v3/production_campaign_v1/cases" / case_id
    receipt_path = regular(
        case_root / f"{case_id}-relative-v3-velocity-receipt.json",
        f"{case_id} velocity placement receipt",
    )
    csv_path = regular(
        case_root / f"{case_id}-relative-v3-velocity-10mm-coordinates.csv",
        f"{case_id} velocity coordinate CSV",
    )
    receipt_sha = sha256_file(receipt_path)
    coordinate_sha = sha256_file(csv_path)
    if (
        receipt_sha != digest(placement_row.get("receipt_sha256"), f"{case_id} placement receipt")
        or receipt_sha != digest(
            mapping_row.get("placement_receipt_sha256"), f"{case_id} mapping placement receipt"
        )
        or coordinate_sha != digest(
            placement_row.get("coordinates_sha256"), f"{case_id} placement coordinates"
        )
        or coordinate_sha != digest(
            mapping_row.get("coordinate_csv_sha256"), f"{case_id} mapping coordinates"
        )
    ):
        raise IndexError(f"{case_id} velocity placement/mapping binding differs")
    receipt = load_json(receipt_path, f"{case_id} velocity placement receipt")
    profiles = receipt.get("profiles")
    if (
        receipt.get("schema") != "drivaerml-relative-velocity-v3-case-receipt-v1"
        or receipt.get("case_id") != case_id
        or receipt.get("family_id") != VELOCITY_FAMILY
        or receipt.get("placement_mode") != "relative"
        or receipt.get("profile_count") != 16
        or not isinstance(profiles, list)
        or [profile.get("profile_id") for profile in profiles if isinstance(profile, dict)]
        != list(VELOCITY_STATIONS)
    ):
        raise IndexError(f"{case_id} velocity receipt declaration differs")
    replayed = profile_coordinate_hashes(csv_path)
    result: list[dict[str, str]] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            raise IndexError(f"{case_id} velocity profile must be an object")
        station = profile["profile_id"]
        support_sha = digest(
            profile.get("coordinates_binary64_be_sha256"),
            f"{case_id}/{station} velocity support identity",
        )
        if support_sha != replayed[station]:
            raise IndexError(f"{case_id}/{station} velocity support identity does not replay")
        result.append({
            "family_id": VELOCITY_FAMILY,
            "station_id": station,
            "representation": "materialized",
            "support_identity_sha256": support_sha,
            "placement_receipt_identity_sha256": receipt_sha,
        })
    return result


def replay_cp_identity(document: Mapping[str, object], field: str, label: str) -> str:
    body = dict(document)
    identity = body.pop(field, None)
    if not isinstance(identity, dict):
        raise IndexError(f"{label} identity object differs")
    value = digest(identity.get("sha256"), f"{label} identity")
    if value != sha256_bytes(cp_canonical_bytes(body)):
        raise IndexError(f"{label} identity does not replay")
    return value


def cp_series(
    producer_root: Path,
    case_id: str,
    aggregate_row: Mapping[str, object],
) -> list[dict[str, str]]:
    case_root = producer_root / "cp_support/campaign_v3/native_support_v3/cases" / case_id
    support_path = regular(case_root / "relative-case-support.json", f"{case_id} Cp support")
    placement_path = regular(case_root / "placement-receipt.json", f"{case_id} Cp placement receipt")
    artifact_receipt_path = regular(case_root / "receipt.json", f"{case_id} Cp artifact receipt")
    artifact_receipt_sha = sha256_file(artifact_receipt_path)
    if artifact_receipt_sha != digest(
        aggregate_row.get("relative_case_receipt_sha256"), f"{case_id} Cp artifact receipt"
    ):
        raise IndexError(f"{case_id} Cp aggregate artifact receipt differs")
    artifact_receipt = load_json(artifact_receipt_path, f"{case_id} Cp artifact receipt")
    artifacts = artifact_receipt.get("artifacts")
    if not isinstance(artifacts, dict):
        raise IndexError(f"{case_id} Cp artifact bindings differ")
    for name, path in (
        ("relative-case-support.json", support_path),
        ("placement-receipt.json", placement_path),
    ):
        binding = artifacts.get(name)
        if not isinstance(binding, dict) or binding.get("sha256") != sha256_file(path):
            raise IndexError(f"{case_id} Cp {name} byte binding differs")
    placement = load_json(placement_path, f"{case_id} Cp placement receipt")
    if (
        placement.get("schema") != "drivaerml-relative-cp-placement-receipt-v1"
        or placement.get("schema_version") != 1
        or placement.get("case_id") != case_id
        or placement.get("family_id") != CP_FAMILY
        or placement.get("placement_mode") != "relative"
    ):
        raise IndexError(f"{case_id} Cp placement receipt declaration differs")
    placement_identity = replay_cp_identity(
        placement, "receipt_identity", f"{case_id} Cp placement receipt"
    )
    support_envelope = load_json(support_path, f"{case_id} Cp support")
    identities = support_envelope.get("identities")
    support = support_envelope.get("support")
    if (
        support_envelope.get("envelope_schema")
        != "drivaerml-relative-cp-case-support-envelope-v1"
        or not isinstance(identities, dict)
        or not isinstance(support, dict)
        or support.get("schema") != "drivaerml-relative-cp-case-support-v1"
        or support.get("schema_version") != 1
        or support.get("case_id") != case_id
        or support.get("family_id") != CP_FAMILY
    ):
        raise IndexError(f"{case_id} Cp support declaration differs")
    case_support_identity = digest(
        identities.get("case_support_sha256"), f"{case_id} Cp case support"
    )
    if (
        case_support_identity != sha256_bytes(cp_canonical_bytes(support))
        or case_support_identity
        != digest(aggregate_row.get("relative_case_support_sha256"), f"{case_id} Cp aggregate support")
    ):
        raise IndexError(f"{case_id} Cp case support identity does not replay")
    aliases = support.get("centerline_aliases")
    moving = support.get("moving_cuts")
    if not isinstance(aliases, list) or not isinstance(moving, list):
        raise IndexError(f"{case_id} Cp station arrays differ")
    if [row.get("station_id") for row in aliases if isinstance(row, dict)] != list(CP_ALIAS_STATIONS):
        raise IndexError(f"{case_id} Cp alias station order differs")
    if [row.get("station_id") for row in moving if isinstance(row, dict)] != list(CP_MOVING_STATIONS):
        raise IndexError(f"{case_id} Cp moving station order differs")
    result: list[dict[str, str]] = []
    for alias in aliases:
        if not isinstance(alias, dict):
            raise IndexError(f"{case_id} Cp alias must be an object")
        station = alias["station_id"]
        result.append({
            "family_id": CP_FAMILY,
            "station_id": station,
            "representation": "shared_alias",
            "support_identity_sha256": digest(
                alias.get("canonical_cut_support_sha256"),
                f"{case_id}/{station} canonical Cp support",
            ),
            "placement_receipt_identity_sha256": placement_identity,
        })
    for cut in moving:
        if not isinstance(cut, dict):
            raise IndexError(f"{case_id} Cp moving cut must be an object")
        station = cut["station_id"]
        cut_body = dict(cut)
        support_identity = digest(
            cut_body.pop("support_identity_sha256", None),
            f"{case_id}/{station} moving Cp support",
        )
        if support_identity != sha256_bytes(cp_canonical_bytes(cut_body)):
            raise IndexError(f"{case_id}/{station} moving Cp support identity does not replay")
        result.append({
            "family_id": CP_FAMILY,
            "station_id": station,
            "representation": "materialized",
            "support_identity_sha256": support_identity,
            "placement_receipt_identity_sha256": placement_identity,
        })
    return result


def generate(repo_root: Path, producer_root: Path) -> dict[str, object]:
    manifests = {
        role: manifest_document(repo_root, producer_root, role) for role in MANIFESTS
    }
    official = official_case_ids(repo_root)
    placement_rows = case_rows(manifests["velocity_placement"], "velocity placement")
    mapping_rows = case_rows(manifests["velocity_mapping"], "velocity mapping")
    cp_rows = case_rows(manifests["cp"], "Cp support")
    for label, rows in (
        ("velocity placement", placement_rows),
        ("velocity mapping", mapping_rows),
        ("Cp support", cp_rows),
    ):
        if [row["case_id"] for row in rows] != official:
            raise IndexError(f"{label} does not cover the exact ordered official case set")
    cases: list[dict[str, object]] = []
    for case_id, placement_row, mapping_row, cp_row in zip(
        official, placement_rows, mapping_rows, cp_rows, strict=True
    ):
        series = velocity_series(producer_root, case_id, placement_row, mapping_row)
        series.extend(cp_series(producer_root, case_id, cp_row))
        if len(series) != 20:
            raise IndexError(f"{case_id} relative series count differs")
        keys = [(row["family_id"], row["station_id"]) for row in series]
        if len(set(keys)) != 20:
            raise IndexError(f"{case_id} relative series keys are not unique")
        cases.append({"case_id": case_id, "series": series})
    source_bindings = {
        "public_dataset": {
            "repository": "neashton/drivaerml",
            "revision": DATASET_REVISION,
            "native_source_pin_path": "benchmark-specs/drivaerml/proposal/native-source-pin.json",
            "native_source_pin_sha256": NATIVE_SOURCE_PIN_SHA256,
        },
        "manifests": [
            {
                "role": role,
                "path": str(binding["retained_path"]),
                "sha256": str(binding["sha256"]),
                "schema": str(binding["schema"]),
                "schema_version": int(binding["schema_version"]),
            }
            for role, binding in MANIFESTS.items()
        ],
        "producer_identity_fields": {
            "relative_velocity_support": "profiles[].coordinates_binary64_be_sha256",
            "relative_velocity_placement_receipt": "sha256(exact placement receipt bytes)",
            "relative_cp_moving_support": "support.moving_cuts[].support_identity_sha256",
            "relative_cp_shared_alias_support": (
                "support.centerline_aliases[].canonical_cut_support_sha256"
            ),
            "relative_cp_placement_receipt": "receipt_identity.sha256",
        },
    }
    return {
        "schema": "drivaerml-relative-series-support-index-v1",
        "schema_version": 1,
        "dataset_id": "drivaerml",
        "contract_id": CONTRACT_ID,
        "scope": "relative_families_only",
        "case_count": 484,
        "series_per_case": 20,
        "source_bindings": source_bindings,
        "cases": cases,
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--producer-root",
        type=Path,
        required=True,
        help="root of the completed DrivAerML relative-diagnostics producer workspace",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="FluidsBench checkout root (default: inferred from this script)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "benchmark-specs/drivaerml/support/relative-v3/"
            "series-support-index.json"
        ),
        help="retained index path, relative to --repo-root unless absolute",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild in memory and fail unless the retained bytes match exactly",
    )
    return parser.parse_args()


def main() -> int:
    values = arguments()
    repo_root = values.repo_root.expanduser().resolve()
    producer_root = values.producer_root.expanduser().resolve()
    output = values.output
    if not output.is_absolute():
        output = repo_root / output
    encoded = canonical_bytes(generate(repo_root, producer_root)) + b"\n"
    if values.check:
        regular(output, "retained relative support index")
        if output.read_bytes() != encoded:
            raise IndexError("retained relative support index differs from producer evidence")
        print(f"PASS {output} sha256={sha256_bytes(encoded)}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    print(f"WROTE {output} sha256={sha256_bytes(encoded)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
