from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import scripts.assemble_hiliftaeroml_schema_v3_candidate as assembler


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmark-specs" / "hiliftaeroml"
SPECIFICATION = DATASET / "submission-spec.json"
TEMPLATE = ROOT / "examples" / "hiliftaeroml-v3-candidate" / "package-config.template.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def descriptor(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": digest(path),
        "size_bytes": path.stat().st_size,
    }


def input_hashes(*, surface_loads: str = "0" * 64) -> dict[str, str]:
    result = {key: "0" * 64 for key in assembler.NATIVE_CASE_INPUT_SHA256_KEYS}
    result["surface_loads"] = surface_loads
    return result


def write_surface_load_case(root: Path, case_id: str, value: dict) -> tuple[Path, str]:
    stream = root / case_id / "surface_submission_stream"
    load_path = stream / "surface_loads.json"
    value = dict(value)
    value["case_id"] = case_id
    if value.get("status") == "complete":
        result = value["result"]
        result.update(
            {
                "schema_id": assembler.EXACT_SURFACE_LOAD_RESULT_SCHEMA,
                "status": "complete",
                "algorithm_id": assembler.EXACT_SURFACE_LOAD_ALGORITHM_ID,
                "force_basis_id": assembler.EXACT_SURFACE_FORCE_BASIS_ID,
                "pitch_moment_basis_id": assembler.EXACT_SURFACE_PITCH_BASIS_ID,
                "input_basis_id": assembler.EXACT_SURFACE_INPUT_BASIS_ID,
                "output_basis_id": assembler.EXACT_SURFACE_OUTPUT_BASIS_ID,
                "pressure_convention_id": (
                    assembler.EXACT_SURFACE_PRESSURE_CONVENTION_ID
                ),
                "weight_support_id": f"test-support:{case_id}",
                "coverage": {"point_count": 3, "chunk_count": 1},
                "reference": {
                    "q_inf": 5.0,
                    "q_ref": 4.0,
                    "qinf_to_qref_scale": 1.25,
                },
            }
        )
        for side_name in ("prediction", "truth"):
            result["loads"][side_name]["total"][
                "pitch_moment_quadrature"
            ] = "exact_degree2"
    value["run_fingerprint"] = hashlib.sha256(case_id.encode("ascii")).hexdigest()
    write_json(load_path, value)
    write_json(
        stream / "summary.json",
        {
            "summary_schema_version": assembler.SURFACE_SUMMARY_SCHEMA_VERSION,
            "status": "complete",
            "case_id": case_id,
            "run_fingerprint": value["run_fingerprint"],
            "number_of_points": 3,
            "load_metric_area_reconciliation": {"status": "pass"},
            "auxiliary_artifacts": {"surface_loads": descriptor(load_path)},
        },
    )
    return load_path, digest(load_path)


def test_specification_binds_the_native_profile_contract_but_not_fake_truth() -> None:
    specification = load(SPECIFICATION)
    profile = specification["profile_definition"]
    contract = DATASET / profile["file"]
    assert profile["status"] == "candidate_owner_review_required"
    assert profile["contract_id"] == assembler.PROFILE_CONTRACT_ID
    assert profile["format"] == assembler.PROFILE_FORMAT
    assert profile["sha256"] == digest(contract) == assembler.PROFILE_CONTRACT_SHA256
    assert profile["profile_ground_truth"] == {
        "status": "not_published",
        "release_id": None,
        "manifest_sha256": None,
    }
    candidate_truth = profile["candidate_dry_run_profile_ground_truth"]
    assert candidate_truth == {
        "status": "complete_candidate_not_published",
        "usage": "maintainer_local_candidate_dry_run_only",
        "release_id": "hiliftaeroml-native-profile-truth-v1-candidate",
        "manifest_sha256": (
            "3e20b857e12055e16f1d248d125b8df62a3669c604411dc67322fe98d9ab4477"
        ),
        "binding_file": "candidate-profile-truth-binding.json",
        "binding_sha256": (
            "11deb05bb29d98149c72712aef571b9be4de543cd69d5d6a1ef68b5bd53f7b93"
        ),
    }
    binding = DATASET / candidate_truth["binding_file"]
    assert digest(binding) == candidate_truth["binding_sha256"]
    assert load(binding)["activation"] == {
        "owner_approval_complete": False,
        "published": False,
        "submissions_opened": False,
        "candidate_validation_may_change_activation": False,
    }


def test_all_official_split_labels_resolve_to_the_exact_eight_case_sets() -> None:
    specification = load(SPECIFICATION)
    assert len(specification["splits"]) == 14
    observed_case_sets: dict[str, list[str]] = {}
    for declared in specification["splits"]:
        split, case_ids, index = assembler._find_split(
            specification, SPECIFICATION, declared["id"]
        )
        assert split == declared
        assert index["case_ids"] == case_ids
        assert len(case_ids) == declared["case_count"]
        previous = observed_case_sets.setdefault(declared["case_set_id"], case_ids)
        assert previous == case_ids
    assert len(observed_case_sets) == 8


def test_release_native_contract_is_case_set_generic_and_surface_v7() -> None:
    assert assembler.NATIVE_ARTIFACT_SCHEMA == (
        "hiliftaeroml-transolver-case-set-aggregate-artifacts-v1"
    )
    assert assembler.NATIVE_RESULT_SCHEMA == (
        "hiliftaeroml-transolver-case-set-results-v1"
    )
    assert assembler.NATIVE_CASE_METRICS_SCHEMA == (
        "hiliftaeroml-transolver-case-set-case-metrics-v1"
    )
    assert assembler.NATIVE_AUXILIARY_SCHEMA == (
        "hiliftaeroml-transolver-case-set-auxiliary-summary-v1"
    )
    assert assembler.NATIVE_RECEIPT_SCHEMA == (
        "hiliftaeroml-transolver-case-receipt-v1"
    )
    assert assembler.SURFACE_SUMMARY_SCHEMA_VERSION == 7
    assert assembler.VOLUME_SUMMARY_SCHEMA_VERSION == 2


def test_blocker_inspection_is_read_only_and_reports_owner_gates() -> None:
    result = assembler.inspect_blockers(
        config_path=TEMPLATE,
        specification_path=SPECIFICATION,
        native_aggregate_root=None,
        native_outputs_root=None,
        native_receipts_root=None,
    )
    gates = {blocker["gate"] for blocker in result["blockers"]}
    assert result["status"] == "blocked"
    assert result["blocker_count"] == len(result["blockers"])
    assert "configuration_token" in gates
    assert "frozen_evaluator_revision" in gates
    assert "profile_ground_truth_release" in gates
    assert "split" in gates
    assert result["note"] == "No package is written by blocker inspection."


def test_package_config_envelope_is_exact_and_typed() -> None:
    config = load(TEMPLATE)
    assert assembler._validate_config_envelope(config) == (10, True)
    unresolved_paths = {item["path"] for item in assembler.unresolved_tokens(config)}
    assert not any("profile_ground_truth" in path for path in unresolved_paths)
    assert any("evaluator.code_revision" in path for path in unresolved_paths)
    config["unexpected"] = True
    with pytest.raises(assembler.HiLiftPackageAssemblyError, match="unexpected"):
        assembler._validate_config_envelope(config)
    del config["unexpected"]
    config["profile_cases_per_chunk"] = "10"
    with pytest.raises(assembler.HiLiftPackageAssemblyError, match="positive integer"):
        assembler._validate_config_envelope(config)


def test_force_gate_refuses_unavailable_case_without_imputation(tmp_path: Path) -> None:
    complete_id = "geo_LHC001_AoA_4"
    unavailable_id = "geo_LHC002_AoA_6"
    complete = {
        "status": "complete",
        "result": {
            "status": "complete",
            "loads": {
                "prediction": {
                    "total": {"cd": 0.1, "cl": 1.0, "cm_body_y": -0.2}
                },
                "truth": {
                    "total": {"cd": 0.2, "cl": 1.1, "cm_body_y": -0.1}
                },
            },
        },
    }
    unavailable = {
        "status": "unavailable_validated_exception",
        "reason_code": "published_truth_load_reproduction_failed_strict_tolerance",
    }
    case_records = {}
    for index, (case_id, value) in enumerate(
        ((complete_id, complete), (unavailable_id, unavailable))
    ):
        _, load_digest = write_surface_load_case(tmp_path, case_id, value)
        case_records[case_id] = {
            "case_id": case_id,
            "full_case_index": index,
            "input_sha256": input_hashes(surface_loads=load_digest),
        }
    with pytest.raises(assembler.HiLiftPackageAssemblyError) as caught:
        assembler._load_complete_loads(
            case_ids=[complete_id, unavailable_id],
            outputs_root=tmp_path,
            case_records=case_records,
        )
    message = str(caught.value)
    assert unavailable_id in message
    assert "published_truth_load_reproduction_failed_strict_tolerance" in message
    assert "imputation and zero-fill are forbidden" in message


def test_force_gate_rejects_cross_case_swapped_complete_loads(tmp_path: Path) -> None:
    case_ids = ["geo_LHC001_AoA_4", "geo_LHC002_AoA_6"]
    case_records = {}
    paths = []
    for index, case_id in enumerate(case_ids):
        value = {
            "status": "complete",
            "result": {
                "status": "complete",
                "loads": {
                    "prediction": {
                        "total": {
                            "cd": 0.1 + index,
                            "cl": 1.0 + index,
                            "cm_body_y": -0.2,
                        }
                    },
                    "truth": {
                        "total": {
                            "cd": 0.2 + index,
                            "cl": 1.1 + index,
                            "cm_body_y": -0.1,
                        }
                    },
                },
            },
        }
        path, load_digest = write_surface_load_case(tmp_path, case_id, value)
        paths.append(path)
        case_records[case_id] = {
            "case_id": case_id,
            "full_case_index": index,
            "input_sha256": input_hashes(surface_loads=load_digest),
        }
    assert set(
        assembler._load_complete_loads(
            case_ids=case_ids,
            outputs_root=tmp_path,
            case_records=case_records,
        )
    ) == set(case_ids)
    first, second = (path.read_bytes() for path in paths)
    paths[0].write_bytes(second)
    paths[1].write_bytes(first)
    with pytest.raises(
        assembler.HiLiftPackageAssemblyError,
        match="SHA-256 differs from the aggregate case binding",
    ):
        assembler._load_complete_loads(
            case_ids=case_ids,
            outputs_root=tmp_path,
            case_records=case_records,
        )


def test_force_scoring_requires_surface_summary_v7(tmp_path: Path) -> None:
    case_id = "geo_LHC001_AoA_4"
    value = {
        "status": "complete",
        "result": {
            "loads": {
                side: {
                    "total": {"cd": 0.1, "cl": 1.0, "cm_body_y": -0.2}
                }
                for side in ("prediction", "truth")
            }
        },
    }
    _, load_digest = write_surface_load_case(tmp_path, case_id, value)
    summary_path = (
        tmp_path / case_id / "surface_submission_stream" / "summary.json"
    )
    summary = load(summary_path)
    summary["summary_schema_version"] = (
        assembler.LEGACY_SURFACE_SUMMARY_SCHEMA_VERSION
    )
    write_json(summary_path, summary)
    with pytest.raises(
        assembler.HiLiftPackageAssemblyError,
        match="requires release-ready surface summary schema 7",
    ):
        assembler._load_complete_loads(
            case_ids=[case_id],
            outputs_root=tmp_path,
            case_records={
                case_id: {
                    "case_id": case_id,
                    "input_sha256": input_hashes(surface_loads=load_digest),
                }
            },
        )


def test_force_scoring_rejects_nonexact_pitch_basis(tmp_path: Path) -> None:
    case_id = "geo_LHC001_AoA_4"
    value = {
        "status": "complete",
        "result": {
            "loads": {
                side: {
                    "total": {"cd": 0.1, "cl": 1.0, "cm_body_y": -0.2}
                }
                for side in ("prediction", "truth")
            }
        },
    }
    load_path, _ = write_surface_load_case(tmp_path, case_id, value)
    loads = load(load_path)
    loads["result"]["pitch_moment_basis_id"] = "legacy-vertex-lumped"
    write_json(load_path, loads)
    summary_path = load_path.parent / "summary.json"
    summary = load(summary_path)
    summary["auxiliary_artifacts"]["surface_loads"] = descriptor(load_path)
    write_json(summary_path, summary)
    with pytest.raises(
        assembler.HiLiftPackageAssemblyError,
        match="pitch_moment_basis_id differs",
    ):
        assembler._load_complete_loads(
            case_ids=[case_id],
            outputs_root=tmp_path,
            case_records={
                case_id: {
                    "case_id": case_id,
                    "input_sha256": input_hashes(
                        surface_loads=digest(load_path)
                    ),
                }
            },
        )


def test_force_scoring_requires_surface_load_case_binding(tmp_path: Path) -> None:
    case_id = "geo_LHC001_AoA_4"
    value = {
        "status": "complete",
        "result": {
            "loads": {
                side: {
                    "total": {"cd": 0.1, "cl": 1.0, "cm_body_y": -0.2}
                }
                for side in ("prediction", "truth")
            }
        },
    }
    load_path, _ = write_surface_load_case(tmp_path, case_id, value)
    loads = load(load_path)
    del loads["case_id"]
    write_json(load_path, loads)
    summary_path = load_path.parent / "summary.json"
    summary = load(summary_path)
    summary["auxiliary_artifacts"]["surface_loads"] = descriptor(load_path)
    write_json(summary_path, summary)
    with pytest.raises(
        assembler.HiLiftPackageAssemblyError,
        match="surface-load summary/case/hash binding differs",
    ):
        assembler._load_complete_loads(
            case_ids=[case_id],
            outputs_root=tmp_path,
            case_records={
                case_id: {
                    "case_id": case_id,
                    "input_sha256": input_hashes(
                        surface_loads=digest(load_path)
                    ),
                }
            },
        )


def test_force_scoring_closes_summary_coverage_and_area_reconciliation(
    tmp_path: Path,
) -> None:
    case_id = "geo_LHC001_AoA_4"
    value = {
        "status": "complete",
        "result": {
            "loads": {
                side: {
                    "total": {"cd": 0.1, "cl": 1.0, "cm_body_y": -0.2}
                }
                for side in ("prediction", "truth")
            }
        },
    }
    load_path, load_digest = write_surface_load_case(tmp_path, case_id, value)
    case_records = {
        case_id: {
            "case_id": case_id,
            "input_sha256": input_hashes(surface_loads=load_digest),
        }
    }
    summary_path = load_path.parent / "summary.json"
    summary = load(summary_path)
    summary["number_of_points"] = 4
    write_json(summary_path, summary)
    with pytest.raises(
        assembler.HiLiftPackageAssemblyError,
        match="coverage differs from the surface summary point count",
    ):
        assembler._load_complete_loads(
            case_ids=[case_id],
            outputs_root=tmp_path,
            case_records=case_records,
        )

    summary["number_of_points"] = 3
    summary["load_metric_area_reconciliation"] = {"status": "failed"}
    write_json(summary_path, summary)
    with pytest.raises(
        assembler.HiLiftPackageAssemblyError,
        match="load/metric area reconciliation did not pass",
    ):
        assembler._load_complete_loads(
            case_ids=[case_id],
            outputs_root=tmp_path,
            case_records=case_records,
        )


def test_receipt_chain_binds_summaries_and_every_consumed_profile_file(
    tmp_path: Path,
) -> None:
    case_id = "geo_LHC001_AoA_4"
    surface_outputs = tmp_path / "surface-outputs"
    volume_outputs = tmp_path / "volume-outputs"
    receipts = tmp_path / "receipts"
    surface = surface_outputs / case_id / "surface_submission_stream"
    volume = volume_outputs / case_id / "volume_submission_stream"
    paths = {
        "surface_support": surface / "submission_support_score.json",
        "surface_regional": surface / "regional_diagnostics.json",
        "surface_loads": surface / "surface_loads.json",
        "cp_profile_metrics": surface / "cp_profile_metrics.json",
        "cp_cut_values": surface / "cp_cut_values.npz",
        "volume_support": volume / "submission_support_score.json",
        "volume_regional": volume / "regional_diagnostics.json",
        "velocity_profile_metrics": volume / "velocity_profile_metrics.json",
        "velocity_profiles": volume / "velocity_profiles.npz",
    }
    for artifact_id, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"retained-{case_id}-{artifact_id}".encode("ascii"))
    surface_run = "1" * 64
    volume_run = "2" * 64
    surface_summary = {
        "summary_schema_version": assembler.SURFACE_SUMMARY_SCHEMA_VERSION,
        "status": "complete",
        "case_id": case_id,
        "run_fingerprint": surface_run,
        "submission_artifacts": {
            "submission_support_score": descriptor(paths["surface_support"]),
            "regional_diagnostics": descriptor(paths["surface_regional"]),
        },
        "auxiliary_artifacts": {
            "surface_loads": descriptor(paths["surface_loads"]),
            "cp_profile_metrics": descriptor(paths["cp_profile_metrics"]),
            "cp_cut_values": descriptor(paths["cp_cut_values"]),
        },
    }
    volume_summary = {
        "summary_schema_version": 2,
        "status": "complete",
        "case_id": case_id,
        "run_fingerprint": volume_run,
        "submission_artifacts": {
            "submission_support_score": descriptor(paths["volume_support"]),
            "regional_diagnostics": descriptor(paths["volume_regional"]),
        },
        "artifacts": {
            "velocity_profile_metrics": descriptor(
                paths["velocity_profile_metrics"]
            ),
            "velocity_profiles": descriptor(paths["velocity_profiles"]),
        },
    }
    surface_summary_path = surface / "summary.json"
    volume_summary_path = volume / "summary.json"
    write_json(surface_summary_path, surface_summary)
    write_json(volume_summary_path, volume_summary)

    contracts = tmp_path / "contracts" / case_id
    raw_contract = contracts / "raw_id_sequences.json"
    truth_contract = contracts / "truth_supports.json"
    write_json(raw_contract, {"case_id": case_id, "kind": "raw"})
    write_json(truth_contract, {"case_id": case_id, "kind": "truth"})
    receipt = {
        "schema_id": assembler.NATIVE_RECEIPT_SCHEMA,
        "status": "complete",
        "case_id": case_id,
        "case_set_id": "caseset-test",
        "case_set_sha256": "a" * 64,
        "case_index": 0,
        "campaign_content_fingerprint": "b" * 64,
        "contracts": {
            "raw_id_sequences": descriptor(raw_contract),
            "truth_supports": descriptor(truth_contract),
        },
        "domains": {
            "surface": {
                "run_fingerprint": surface_run,
                "summary": descriptor(surface_summary_path),
                "submission_support_score": descriptor(paths["surface_support"]),
                "regional_diagnostics": descriptor(paths["surface_regional"]),
                "surface_load_diagnostic": {
                    "artifact": descriptor(paths["surface_loads"])
                },
            },
            "volume": {
                "run_fingerprint": volume_run,
                "summary": descriptor(volume_summary_path),
                "submission_support_score": descriptor(paths["volume_support"]),
                "regional_diagnostics": descriptor(paths["volume_regional"]),
            },
        },
    }
    receipt["content_fingerprint"] = assembler._canonical_fingerprint(receipt)
    receipt_path = receipts / f"{case_id}.json"
    write_json(receipt_path, receipt)
    inputs = input_hashes(surface_loads=digest(paths["surface_loads"]))
    inputs.update(
        {
            "receipt": digest(receipt_path),
            "raw_contract": digest(raw_contract),
            "truth_contract": digest(truth_contract),
            "surface_support": digest(paths["surface_support"]),
            "surface_regional": digest(paths["surface_regional"]),
            "volume_support": digest(paths["volume_support"]),
            "volume_regional": digest(paths["volume_regional"]),
        }
    )
    records = {
        case_id: {
            "case_id": case_id,
            "case_index": 0,
            "input_sha256": inputs,
        }
    }
    result = assembler._verify_native_receipts(
        receipts_root=receipts,
        outputs_root=None,
        surface_outputs_root=surface_outputs,
        volume_outputs_root=volume_outputs,
        case_ids=[case_id],
        case_set_id="caseset-test",
        case_set_sha256="a" * 64,
        case_records=records,
    )
    assert result == {
        case_id: {
            artifact_id: digest(paths[artifact_id])
            for artifact_id in (
                "cp_profile_metrics",
                "cp_cut_values",
                "velocity_profile_metrics",
                "velocity_profiles",
            )
        }
    }
    retained = paths["velocity_profiles"].read_bytes()
    paths["velocity_profiles"].write_bytes(b"X" + retained[1:])
    with pytest.raises(assembler.HiLiftPackageAssemblyError, match="SHA-256 differs"):
        assembler._verify_native_receipts(
            receipts_root=receipts,
            outputs_root=None,
            surface_outputs_root=surface_outputs,
            volume_outputs_root=volume_outputs,
            case_ids=[case_id],
            case_set_id="caseset-test",
            case_set_sha256="a" * 64,
            case_records=records,
        )


def test_native_output_root_cli_preserves_shared_shorthand_and_allows_split() -> None:
    shared = Path("shared")
    assert assembler._resolve_native_output_roots(outputs_root=shared) == {
        "surface": shared,
        "volume": shared,
    }
    split = assembler._resolve_native_output_roots(
        outputs_root=None,
        surface_outputs_root=Path("surface"),
        volume_outputs_root=Path("volume"),
    )
    assert split == {
        "surface": Path("surface"),
        "volume": Path("volume"),
    }
    with pytest.raises(
        assembler.HiLiftPackageAssemblyError,
        match="missing volume",
    ):
        assembler._resolve_native_output_roots(
            outputs_root=None,
            surface_outputs_root=Path("surface"),
        )
    args = assembler.build_parser().parse_args(
        [
            "--config",
            "config.json",
            "--native-surface-outputs",
            "surface",
            "--native-volume-outputs",
            "volume",
        ]
    )
    assert args.native_outputs is None
    assert args.native_surface_outputs == Path("surface")
    assert args.native_volume_outputs == Path("volume")


def make_native_aggregate(
    root: Path,
    *,
    case_ids: list[str] | None = None,
    case_set_id: str = "caseset-test",
    case_set_sha256: str = "a" * 64,
) -> None:
    case_ids = case_ids or ["geo_LHC001_AoA_4"]
    case_count = len(case_ids)
    documents = {
        "submission_results.json": {
            "schema_id": assembler.NATIVE_RESULT_SCHEMA,
            "status": "complete_closed_candidate",
            "case_set_id": case_set_id,
            "case_set_sha256": case_set_sha256,
            "case_count": case_count,
            "case_order_sha256": assembler._canonical_sha256(case_ids),
        },
        "case_metrics.json": {
            "schema_id": assembler.NATIVE_CASE_METRICS_SCHEMA,
            "status": "complete",
            "case_set_id": case_set_id,
            "case_set_sha256": case_set_sha256,
            "case_count": case_count,
            "case_order": case_ids,
            "cases": [
                {
                    "case_id": case_id,
                    "case_index": case_index,
                    "input_sha256": input_hashes(),
                }
                for case_index, case_id in enumerate(case_ids)
            ],
        },
        "auxiliary_summary.json": {
            "schema_id": assembler.NATIVE_AUXILIARY_SCHEMA,
            "status": "complete",
            "case_set_id": case_set_id,
            "case_set_sha256": case_set_sha256,
            "case_count": case_count,
        },
        "regional_diagnostics_aggregate.json": {
            "schema_id": assembler.NATIVE_REGIONAL_SCHEMA,
            "status": "complete_report_only",
            "case_set_id": case_set_id,
            "case_set_sha256": case_set_sha256,
            "case_count": case_count,
        },
    }
    for filename, value in documents.items():
        write_json(root / filename, value)
    artifact = {
        "schema_id": assembler.NATIVE_ARTIFACT_SCHEMA,
        "status": "complete",
        "case_set_id": case_set_id,
        "case_set_sha256": case_set_sha256,
        "case_count": case_count,
        "artifacts": {
            filename: {"sha256": digest(root / filename)} for filename in documents
        },
    }
    artifact["content_fingerprint"] = assembler._canonical_fingerprint(artifact)
    write_json(root / "artifact_manifest.json", artifact)


def refresh_native_artifact(root: Path) -> None:
    artifact_path = root / "artifact_manifest.json"
    artifact = load(artifact_path)
    artifact["artifacts"] = {
        filename: {"sha256": digest(root / filename)}
        for filename in sorted(
            assembler.NATIVE_AGGREGATE_FILES - {"artifact_manifest.json"}
        )
    }
    artifact.pop("content_fingerprint", None)
    artifact["content_fingerprint"] = assembler._canonical_fingerprint(artifact)
    write_json(artifact_path, artifact)


def make_legacy_full360_aggregate(
    root: Path, *, case_ids: list[str], case_set_sha256: str
) -> None:
    make_native_aggregate(
        root,
        case_ids=case_ids,
        case_set_id=assembler.LEGACY_FULL360_CASE_SET_ID,
        case_set_sha256=case_set_sha256,
    )
    schema_updates = {
        "submission_results.json": assembler.LEGACY_NATIVE_RESULT_SCHEMA,
        "case_metrics.json": assembler.LEGACY_NATIVE_CASE_METRICS_SCHEMA,
        "auxiliary_summary.json": assembler.LEGACY_NATIVE_AUXILIARY_SCHEMA,
    }
    for filename, schema_id in schema_updates.items():
        value = load(root / filename)
        value["schema_id"] = schema_id
        if filename == "case_metrics.json":
            value.pop("case_count")
            for record in value["cases"]:
                record["full_case_index"] = record.pop("case_index")
        elif filename == "auxiliary_summary.json":
            value["status"] = "complete_with_partial_report_only_load_coverage"
            value.pop("case_set_sha256")
        write_json(root / filename, value)
    artifact = load(root / "artifact_manifest.json")
    artifact["schema_id"] = assembler.LEGACY_NATIVE_ARTIFACT_SCHEMA
    artifact.pop("case_set_sha256")
    artifact.pop("case_count")
    write_json(root / "artifact_manifest.json", artifact)
    refresh_native_artifact(root)


def test_generic_native_aggregate_accepts_all_eight_case_sets_and_14_aliases(
    tmp_path: Path,
) -> None:
    specification = load(SPECIFICATION)
    observed: set[str] = set()
    for declared in specification["splits"]:
        split, case_ids, index = assembler._find_split(
            specification, SPECIFICATION, declared["id"]
        )
        aggregate = tmp_path / split["case_set_id"]
        if split["case_set_id"] not in observed:
            observed.add(split["case_set_id"])
            make_native_aggregate(
                aggregate,
                case_ids=case_ids,
                case_set_id=split["case_set_id"],
                case_set_sha256=index["case_set_sha256"],
            )
        documents = assembler._verify_native_aggregate(
            aggregate_root=aggregate,
            case_ids=case_ids,
            case_set_id=split["case_set_id"],
            case_set_sha256=index["case_set_sha256"],
        )
        assert documents["case_metrics.json"]["case_order"] == case_ids
    assert len(observed) == 8


def test_retained_legacy_full360_aggregate_has_a_bounded_reader(
    tmp_path: Path,
) -> None:
    specification = load(SPECIFICATION)
    split, case_ids, index = assembler._find_split(
        specification, SPECIFICATION, "full"
    )
    make_legacy_full360_aggregate(
        tmp_path,
        case_ids=case_ids,
        case_set_sha256=index["case_set_sha256"],
    )
    documents = assembler._verify_native_aggregate(
        aggregate_root=tmp_path,
        case_ids=case_ids,
        case_set_id=split["case_set_id"],
        case_set_sha256=index["case_set_sha256"],
    )
    assert (
        documents["artifact_manifest.json"]["schema_id"]
        == assembler.LEGACY_NATIVE_ARTIFACT_SCHEMA
    )


def test_native_aggregate_inventory_hashes_and_case_order_are_retained(
    tmp_path: Path,
) -> None:
    case_id = "geo_LHC001_AoA_4"
    make_native_aggregate(tmp_path, case_ids=[case_id])
    documents = assembler._verify_native_aggregate(
        aggregate_root=tmp_path,
        case_ids=[case_id],
        case_set_id="caseset-test",
        case_set_sha256="a" * 64,
    )
    assert set(documents) == assembler.NATIVE_AGGREGATE_FILES
    (tmp_path / "unexpected-directory").mkdir()
    with pytest.raises(assembler.HiLiftPackageAssemblyError, match="inventory"):
        assembler._verify_native_aggregate(
            aggregate_root=tmp_path,
            case_ids=[case_id],
            case_set_id="caseset-test",
            case_set_sha256="a" * 64,
        )
    (tmp_path / "unexpected-directory").rmdir()
    cases = load(tmp_path / "case_metrics.json")
    cases["case_order"] = ["geo_LHC002_AoA_6"]
    write_json(tmp_path / "case_metrics.json", cases)
    artifact = load(tmp_path / "artifact_manifest.json")
    artifact["artifacts"]["case_metrics.json"]["sha256"] = digest(
        tmp_path / "case_metrics.json"
    )
    del artifact["content_fingerprint"]
    artifact["content_fingerprint"] = assembler._canonical_fingerprint(artifact)
    write_json(tmp_path / "artifact_manifest.json", artifact)
    with pytest.raises(assembler.HiLiftPackageAssemblyError, match="case order"):
        assembler._verify_native_aggregate(
            aggregate_root=tmp_path,
            case_ids=[case_id],
            case_set_id="caseset-test",
            case_set_sha256="a" * 64,
        )
