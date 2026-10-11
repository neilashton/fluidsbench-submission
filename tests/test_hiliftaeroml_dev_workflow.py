"""Disposable workflow fixtures are never published as model results."""

import copy
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pytest

from reference.hiliftaeroml import dev_release, dev_support
from reference.hiliftaeroml.compact_profile_evaluator import (
    write_compact_support_release,
)
from reference.hiliftaeroml.compact_profiles import (
    compact_case_metadata,
    encode_compact_predictions,
    score_compact_profiles,
    write_compact_prediction_npz,
)
from reference.hiliftaeroml.pre_release import GENUINE_INFERENCE_ATTESTATION
from reference.scores import composite_overall_score, composite_component_group_scores
from scripts import assemble_hiliftaeroml_schema_v3_candidate as assembler
from scripts import validate_submission as validator, manage_leaderboard as manager
from scripts import register_hiliftaeroml_pre_release as registrar
from tests.test_hiliftaeroml_compact_profile_evaluator import (
    _make_varying_native_case,
    _support_from_native,
    CASE_ID,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmark-specs/hiliftaeroml/submission-spec.json"
ID = "hiliftaeroml-synthetic-workflow-test-v1"


def load(path):
    return json.loads(path.read_text())


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def package(tmp_path, monkeypatch):
    """Fresh full 36-case split with synthetic profile support and predictions.

    Retained field/load evidence supplies the orthogonal schema-v3 fixture;
    profile scores are calculated afresh against a real synthetic support bundle.
    Only the benchmark support digest is replaced in this isolated test root.
    """
    root = tmp_path / "repo"
    dataset = root / "benchmark-specs/hiliftaeroml"
    shutil.copytree(SPEC.parent, dataset)
    source = ROOT / "submissions/hiliftaeroml/hiliftaeroml-transolver-aoa4-candidate-v1"
    directory = root / "submissions/hiliftaeroml" / ID
    shutil.copytree(source, directory)
    old_id = source.name
    for path in directory.rglob("*"):
        if path.suffix in {".json", ".jsonl"}:
            path.write_text(path.read_text().replace(old_id, ID))
    spec = load(dataset / "submission-spec.json")
    submission = load(directory / "submission.json")
    index = load(directory / "profiles/index.json")
    case_ids = [cid for chunk in index["chunks"] for cid in chunk["case_ids"]]
    outputs = tmp_path / "native"
    hashes = _make_varying_native_case(outputs)
    support = _support_from_native(outputs, hashes)
    support_root = tmp_path / "compact-support"
    digest = write_compact_support_release(
        release_root=support_root,
        case_ids=case_ids,
        case_sets={submission["case_set_id"]: case_ids},
        supports={cid: support for cid in case_ids},
        source_artifact_sha256={cid: hashes[CASE_ID] for cid in case_ids},
        source_profile_truth_release_id=submission["profile_data"][
            "profile_ground_truth_release_id"
        ],
        source_profile_truth_manifest_sha256=submission["profile_data"][
            "profile_ground_truth_manifest_sha256"
        ],
    )
    monkeypatch.setattr(dev_support, "SUPPORT_MANIFEST_SHA256", digest)
    monkeypatch.setenv("FLUIDSBENCH_HILIFT_PROFILE_SUPPORT", str(support_root))
    spec["profile_definition"]["candidate_dry_run_evaluator_support"][
        "manifest_sha256"
    ] = digest
    write(dataset / "submission-spec.json", spec)
    metadata = compact_case_metadata(support)
    prediction = encode_compact_predictions(
        support=support,
        cp_prediction=support["cp_truth"] + 0.025,
        velocity_speed_over_u_inf=support["velocity_truth_speed_over_uinf"] + 0.01,
    )
    scores = score_compact_profiles(prediction, support=support, metadata=metadata)
    for chunk_descriptor in index["chunks"]:
        chunk_path = directory / "profiles" / chunk_descriptor["file"]
        chunk = load(chunk_path)
        for case in chunk["cases"]:
            case.update(copy.deepcopy(metadata))
            artifact = directory / "profiles" / case["artifact"]["file"]
            artifact.unlink()
            case["artifact"]["sha256"] = write_compact_prediction_npz(
                artifact, prediction, support=support, metadata=metadata
            )
            case["artifact"]["byte_size"] = artifact.stat().st_size
        # Profile JSON is required to use the canonical compact encoding.
        chunk_path.write_bytes(assembler.canonical_json_bytes(chunk))
        chunk_descriptor["sha256"] = sha(chunk_path)
    index["evaluator_support_manifest_sha256"] = digest
    (directory / "profiles/index.json").write_bytes(
        assembler.canonical_json_bytes(index)
    )
    binding = {
        "status": "frozen_dev_candidate",
        "activation_effect": "none",
        "code_revision": "1" * 40,
        "implementation_manifest_sha256": "2" * 64,
        "base_dataset_evaluator_scope": "native_v1_base_field_force_and_noncompact_scoring_only",
    }
    monkeypatch.setattr(
        dev_release, "implementation_binding", lambda root=ROOT: copy.deepcopy(binding)
    )
    submission["profile_data"].update(
        evaluator_support_manifest_sha256=digest,
        compact_profile_implementation_binding=binding,
    )
    submission["model"] = "Synthetic integration fixture; never a model result"
    submission["note"] = (
        "TEST ONLY: retained field fixture plus synthetic profiles. Never publish."
    )
    submission["result_revision"]["series_id"] = ID
    submission["methodology"]["record_kind"] = "submitter_reported"
    submission["metric_values"].update(scores)
    submission["metric_values"]["overall_score"] = composite_overall_score(
        submission["metric_values"], spec["overall_score_composite"]
    )
    submission["metric_values"].update(
        composite_component_group_scores(
            submission["metric_values"],
            spec["overall_score_composite"],
            spec["component_score_groups"],
        )
    )
    metrics = load(directory / "metrics/cases.json")
    for case in metrics["cases"]:
        case["nonspatial_metric_values"].update(scores)
    metrics["metric_values"] = submission["metric_values"]
    write(directory / "metrics/cases.json", metrics)
    discretization = load(directory / "discretization.json")
    discretization["case_manifest"]["sha256"] = sha(
        directory / "discretization/cases.jsonl"
    )
    write(directory / "discretization.json", discretization)
    evidence = load(directory / "evaluation-evidence.json")
    evidence.update(
        compact_profile_implementation_binding=binding,
        metric_values=submission["metric_values"],
        notes=GENUINE_INFERENCE_ATTESTATION,
        profile_index_sha256=sha(directory / "profiles/index.json"),
        case_metrics_sha256=sha(directory / "metrics/cases.json"),
        discretization_sha256=sha(directory / "discretization.json"),
    )
    submission["case_metrics"]["sha256"] = evidence["case_metrics_sha256"]
    submission["spatial_discretization"]["sha256"] = evidence["discretization_sha256"]
    if "regional_diagnostics" in submission:
        submission["regional_diagnostics"]["sha256"] = sha(
            directory / "regional-diagnostics.json"
        )
        evidence["regional_diagnostics_sha256"] = submission["regional_diagnostics"][
            "sha256"
        ]
    write(directory / "evaluation-evidence.json", evidence)
    submission["evaluation"]["evidence_sha256"] = sha(
        directory / "evaluation-evidence.json"
    )
    write(directory / "submission.json", submission)
    manifest = validator.manifest_with_benchmark_contract(
        load(ROOT / "leaderboard/manifest.json")
    )
    write(root / "leaderboard/manifest.json", manifest)
    monkeypatch.setattr(validator, "ROOT", root)
    monkeypatch.setattr(validator, "MANIFEST_PATH", root / "leaderboard/manifest.json")
    monkeypatch.setattr(manager, "ROOT", root)
    monkeypatch.setattr(registrar, "ROOT", root)
    registry = dataset / "pre-release-reference-registry.json"
    monkeypatch.setattr(registrar, "DEFAULT_REGISTRY", registry)
    return root, directory / "submission.json", manifest, registry, support_root


def test_new_dev_package_scores_registers_and_enters_feed(package):
    root, path, manifest, registry, support = package
    assert validator.validate_submission_file(
        path, manifest, contributor_stage=True, dev_intake=True
    ) == ([], {"cases": 36, "series": 540})
    assert not manager.source_rows_by_dataset(manifest)["HiLiftAeroML"]
    result = registrar.register(
        path, registry_path=registry, write=True, profile_support_release=support
    )
    assert result["status"] == "registered"
    assert validator.validate_submission_file(path, manifest)[0] == []
    rows = manager.source_rows_by_dataset(manifest)["HiLiftAeroML"]
    assert len(rows) == 1 and rows[0]["record_type"] == "pre_release_reference"
    assert (
        registrar.register(
            path, registry_path=registry, write=True, profile_support_release=support
        )["status"]
        == "already_registered_exactly"
    )
    assert validator.validate_submission_file(path, manifest, contributor_stage=True)[0]
    (path.parent / "unexpected.txt").write_text("Changed after registration")
    assert validator.validate_submission_file(path, manifest)[0]
    assert not manager.source_rows_by_dataset(manifest)["HiLiftAeroML"]


def test_fresh_package_cannot_bypass_support_or_main_boundary(package, monkeypatch):
    _, path, manifest, _, support = package
    assert validator.validate_submission_file(path, manifest, contributor_stage=True)[0]
    wrong_manifest = copy.deepcopy(manifest)
    wrong_manifest["data_release"]["source_ref"] = "main"
    errors, _ = validator.validate_submission_file(
        path, wrong_manifest, dev_intake=True
    )
    assert any("prototype dev release" in error for error in errors)
    (support / "manifest.json").chmod(0o600)
    (support / "manifest.json").write_text("{}")
    errors, _ = validator.validate_submission_file(path, manifest, dev_intake=True)
    assert any("manifest differs" in error for error in errors)


def test_rehashed_false_profile_score_is_rejected(package):
    _, path, manifest, _, _ = package
    submission = load(path)
    metrics = load(path.parent / "metrics/cases.json")
    metrics["cases"][0]["nonspatial_metric_values"]["cp_cut_r2"] -= 0.05
    write(path.parent / "metrics/cases.json", metrics)
    submission["case_metrics"]["sha256"] = sha(path.parent / "metrics/cases.json")
    evidence = load(path.parent / "evaluation-evidence.json")
    evidence["case_metrics_sha256"] = submission["case_metrics"]["sha256"]
    write(path.parent / "evaluation-evidence.json", evidence)
    submission["evaluation"]["evidence_sha256"] = sha(
        path.parent / "evaluation-evidence.json"
    )
    write(path, submission)
    errors, _ = validator.validate_submission_file(path, manifest, dev_intake=True)
    assert any("hidden-truth recomputation" in error for error in errors)


def test_dev_config_fills_owner_fields_and_checks_actual_checkpoint_bytes(
    tmp_path, monkeypatch
):
    config = load(
        ROOT / "examples/hiliftaeroml-v3-candidate/package-config.template.json"
    )
    resolved = dev_release.resolve_config(config, load(SPEC))
    assert not any(
        "release_bindings" in item["path"]
        for item in assembler.unresolved_tokens(resolved)
    )
    config["participant"]["methodology"]["checkpoints"] = [
        {"id": "model", "sha256": "a" * 64}
    ]
    cfg = tmp_path / "config.json"
    write(cfg, config)
    checkpoint = tmp_path / "model.bin"
    checkpoint.write_bytes(b"wrong checkpoint")
    monkeypatch.setattr(dev_release, "implementation_binding", lambda: {})
    with pytest.raises(ValueError, match="bytes differ"):
        assembler.assemble_package(
            config_path=cfg,
            specification_path=SPEC,
            native_aggregate_root=tmp_path,
            native_outputs_root=tmp_path,
            native_receipts_root=tmp_path,
            profile_support_release_root=tmp_path,
            output_path=tmp_path / "package",
            dev_intake=True,
            checkpoint_paths={"model": checkpoint},
        )
    assert not (tmp_path / "package").exists()


@pytest.mark.parametrize(
    "member", ["../escape", "/absolute", "a/../escape", "a\\escape"]
)
def test_support_archive_rejects_unsafe_paths(tmp_path, member):
    archive = tmp_path / "support.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(member, b"x")
    with pytest.raises(ValueError, match="unsafe"):
        dev_support.extract_archive(archive, tmp_path / "output", expected_bytes=1)


def test_support_archive_rejects_expansion_mismatch(tmp_path):
    archive = tmp_path / "support.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("manifest.json", b"{}")
    with pytest.raises(ValueError, match="byte count"):
        dev_support.extract_archive(archive, tmp_path / "output", expected_bytes=1)


def test_support_download_rejects_checksum_before_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("FLUIDSBENCH_HILIFT_PROFILE_SUPPORT", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(
        dev_support,
        "load_release",
        lambda root: {
            "support_transport": {
                "url": "https://example.com/support.zip",
                "size_bytes": 3,
                "sha256": "0" * 64,
                "expanded_bytes": 3,
            }
        },
    )
    monkeypatch.setattr(
        dev_support.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"bad")
    )
    with pytest.raises(ValueError, match="SHA-256 differs"):
        dev_support.resolve_support(root=tmp_path)
    assert not list((tmp_path / "cache").rglob("manifest.json"))
