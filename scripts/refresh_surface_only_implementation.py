#!/usr/bin/env python3
"""Bind the additive surface-only evaluator to exact source bytes."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ("ahmedml", "windsorml", "hiliftaeroml")
FILES = (
    "reference/prediction_scope.py",
    "reference/scores.py",
    "reference/ahmedml/evaluator.py",
    "reference/ahmedml/dataset_scorer.py",
    "reference/ahmedml/regional_aggregate.py",
    "reference/ahmedml/pre_release.py",
    "reference/windsorml/evaluator.py",
    "reference/windsorml/dataset_scorer.py",
    "reference/windsorml/profiles.py",
    "reference/hiliftaeroml/compact_profiles.py",
    "reference/hiliftaeroml/compact_profile_evaluator.py",
    "reference/hiliftaeroml/regional_aggregate.py",
    "reference/drivaerml/methodology.py",
    "scripts/assemble_ahmedml_schema_v3_candidate.py",
    "scripts/assemble_ahmedml_schema_v3_dev_fixture.py",
    "scripts/assemble_hiliftaeroml_schema_v3_candidate.py",
    "scripts/validate_submission.py",
    "scripts/build_windsorml_submission_spec.py",
    "schemas/v1/hiliftaeroml-compact-profile-chunk.schema.json",
    "schemas/v1/profile-index.schema.json",
    "schemas/v3/submission.schema.json",
    "schemas/v3/evaluation-evidence.schema.json",
    *(f"benchmark-specs/{dataset}/methodology-contract.json" for dataset in DATASETS),
    "benchmark-specs/hiliftaeroml/methodology-prediction-scopes-v1.json",
)
MANIFEST = "reference/aerodynamic-surface-only-implementation-v1.json"


def encoded(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = encoded(
        {
            "schema": "aerodynamic-surface-only-implementation-v1",
            "version": "aerodynamic-surface-only-v1",
            "activation_effect": "none",
            "datasets": list(DATASETS),
            "unavailable_component_metric_ids": [
                "volume_velocity_rel_l2",
                "volume_pressure_rel_l2",
                "velocity_profile_r2",
            ],
            "unavailable_component_score": 0.0,
            "component_weight_renormalization": False,
            "maximum_overall_score": 60.0,
            "artifacts": [
                {
                    "file": name,
                    "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
                }
                for name in sorted(FILES)
            ],
        }
    )
    binding = {
        "version": "aerodynamic-surface-only-v1",
        "file": MANIFEST,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    if args.check:
        if (ROOT / MANIFEST).read_bytes() != payload:
            raise SystemExit("surface-only implementation binding is stale")
    else:
        (ROOT / MANIFEST).write_bytes(payload)
    for dataset in DATASETS:
        path = ROOT / "benchmark-specs" / dataset / "submission-spec.json"
        specification = json.loads(path.read_text())
        if args.check:
            if (
                specification["scoring_support"].get(
                    "surface_only_implementation_binding"
                )
                != binding
            ):
                raise SystemExit(
                    f"{dataset}: surface-only implementation binding is stale"
                )
        else:
            specification["scoring_support"]["surface_only_implementation_binding"] = (
                binding
            )
            path.write_bytes(encoded(specification))
    print(
        "surface-only implementation binding verified"
        if args.check
        else "surface-only implementation binding refreshed"
    )


if __name__ == "__main__":
    main()
