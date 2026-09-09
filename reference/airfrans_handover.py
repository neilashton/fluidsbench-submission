"""Collect and check native AirfRANS inference arrays before result assembly.

This is a collaborator handover helper, not the official benchmark evaluator.
It never reads ground-truth field values into prediction arrays.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = ROOT / "benchmark-specs" / "airfrans"
ARRAY_NAMES = {"velocity", "pressure", "airfoil_pressure", "internal_points", "airfoil_points"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_official_split(split_id: str) -> tuple[dict[str, Any], str]:
    spec = json.loads((SPEC_ROOT / "submission-spec.json").read_text())
    entry = next((item for item in spec["splits"] if item["id"] == split_id), None)
    if entry is None:
        raise ValueError(f"Unknown AirfRANS split: {split_id}")
    path = SPEC_ROOT / entry["index_file"]
    digest = sha256_file(path)
    if digest != entry["sha256"]:
        raise ValueError("Official split file does not match its specification checksum")
    split = json.loads(path.read_text())
    ids = split["case_ids"]
    if (
        split["case_id_status"] != "official"
        or split["split_id"] != split_id
        or len(ids) != entry["case_count"]
        or len(ids) != split["case_count"]
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Official split identity or case coverage is inconsistent")
    for case_id in ids:
        _check_case_id(case_id)
    return split, digest


def _check_case_id(case_id: str) -> None:
    if (
        not isinstance(case_id, str)
        or not case_id.startswith("airFoil2D_")
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for character in case_id)
    ):
        raise ValueError("case_id must be an AirfRANS case name, without a path")


def validate_arrays(arrays: dict[str, Any]) -> dict[str, np.ndarray]:
    if set(arrays) != ARRAY_NAMES:
        raise ValueError(
            f"Expected exactly {sorted(ARRAY_NAMES)}; "
            f"missing={sorted(ARRAY_NAMES - set(arrays))}, extra={sorted(set(arrays) - ARRAY_NAMES)}"
        )
    result = {}
    for name, value in arrays.items():
        array = np.asarray(value)
        if array.dtype.kind not in "fiu":
            raise ValueError(f"{name} must contain real numeric values, not {array.dtype}")
        if array.size == 0 or not np.isfinite(array).all():
            raise ValueError(f"{name} must be non-empty and contain only finite values")
        result[name] = array
    for name in ("internal_points", "airfoil_points"):
        if result[name].ndim != 2 or result[name].shape[1] != 3:
            raise ValueError(f"{name} must have shape (native_point_count, 3)")
    internal_count = len(result["internal_points"])
    airfoil_count = len(result["airfoil_points"])
    expected = {
        "velocity": (internal_count, 2),
        "pressure": (internal_count,),
        "airfoil_pressure": (airfoil_count,),
    }
    for name, shape in expected.items():
        if result[name].shape != shape:
            raise ValueError(f"{name} must have shape {shape}; observed {result[name].shape}")
    return result


def write_case(output_root: Path, case_id: str, **arrays: Any) -> Path:
    """Save supplied predictions and their aligned native coordinates, without overwriting.

    The caller must undo normalization and map predictions into original point
    order before this call. No ground-truth field is a default or fallback.
    """
    _check_case_id(case_id)
    checked = validate_arrays(arrays)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / f"{case_id}.npz"
    with path.open("xb") as handle:
        try:
            np.savez_compressed(handle, **checked)
        except Exception:
            path.unlink()
            raise
    return path


def read_mesh_points(path: Path) -> np.ndarray:
    try:
        import pyvista as pv
    except ImportError as error:
        raise RuntimeError(
            "Mesh checks require PyVista. Use the existing AirfRANS profile-extraction environment."
        ) from error
    return np.asarray(pv.read(path).points).copy()


def check_handover(predictions_root: Path, dataset_root: Path, split_id: str) -> dict[str, Any]:
    """Check full-split array coverage and coordinate identity against local meshes.

    Source hashes record the files actually checked; they do not certify an
    approved scoring-support release. Units and model provenance need review.
    """
    split, split_digest = load_official_split(split_id)
    errors = []
    records = []
    expected = set(split["case_ids"])
    predictions_root, dataset_root = Path(predictions_root), Path(dataset_root)
    observed = {path.stem for path in predictions_root.glob("*.npz")}
    if not predictions_root.is_dir():
        errors.append(f"Prediction directory does not exist: {predictions_root}")
    if not dataset_root.is_dir():
        errors.append(f"Dataset directory does not exist: {dataset_root}")
    for label, ids in (("missing", expected - observed), ("unexpected", observed - expected)):
        if ids:
            errors.append(f"{label} prediction cases: {', '.join(sorted(ids))}")
    for case_id in split["case_ids"]:
        if case_id not in observed:
            continue
        path = predictions_root / f"{case_id}.npz"
        internal = dataset_root / case_id / f"{case_id}_internal.vtu"
        airfoil = dataset_root / case_id / f"{case_id}_aerofoil.vtp"
        try:
            # Object arrays are forbidden; np.load must never unpickle a handover.
            with np.load(path, allow_pickle=False) as archive:
                if len(archive.files) != len(set(archive.files)):
                    raise ValueError("Archive contains duplicate array names")
                arrays = validate_arrays({name: archive[name] for name in archive.files})
            for name, mesh_path in (("internal_points", internal), ("airfoil_points", airfoil)):
                native = read_mesh_points(mesh_path)
                if not np.array_equal(arrays[name], native):
                    raise ValueError(
                        f"{name} does not exactly match the source mesh coordinates and point order; "
                        "export the original coordinates without rounding, and align predictions to them"
                    )
            records.append({
                "case_id": case_id,
                "prediction_file": path.name,
                "prediction_sha256": sha256_file(path),
                "internal_vtu_sha256": sha256_file(internal),
                "aerofoil_vtp_sha256": sha256_file(airfoil),
                "internal_point_count": len(arrays["internal_points"]),
                "airfoil_point_count": len(arrays["airfoil_points"]),
            })
        except (OSError, ValueError, KeyError, RuntimeError, EOFError, zipfile.BadZipFile) as error:
            errors.append(f"{case_id}: {error}")
    return {
        "format": "fluidsbench-airfrans-inference-handover-check-v1",
        "status": "failed" if errors else "complete_handover",
        "scope": "array_coverage_and_local_mesh_coordinate_identity_only",
        "benchmark_approval": False,
        "split_id": split_id,
        "case_set_id": split["case_set_id"],
        "split_sha256": split_digest,
        "submission_spec_sha256": sha256_file(SPEC_ROOT / "submission-spec.json"),
        "checker_sha256": sha256_file(Path(__file__)),
        "expected_case_count": len(expected),
        "checked_case_count": len(records),
        "cases": records,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    cases = commands.add_parser("list-cases", help="Print the hash-checked official inference case list")
    cases.add_argument("--split-id", required=True)
    check = commands.add_parser("check", help="Check one complete split of native prediction exports")
    check.add_argument("--split-id", required=True)
    check.add_argument("--predictions-root", type=Path, required=True)
    check.add_argument("--dataset-root", type=Path, required=True)
    check.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "list-cases":
            split, _ = load_official_split(args.split_id)
            print("\n".join(split["case_ids"]))
            return 0
        # Refuse to overwrite an existing report, prediction or source file.
        # Use a new report filename for a new check.
        with args.report.open("x", encoding="utf-8") as handle:
            report = check_handover(args.predictions_root, args.dataset_root, args.split_id)
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n")
        print(f"{report['status']}: {report['checked_case_count']}/{report['expected_case_count']} cases; {args.report}")
        for error in report["errors"]:
            print(error, file=sys.stderr)
        return 1 if report["errors"] else 0
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
