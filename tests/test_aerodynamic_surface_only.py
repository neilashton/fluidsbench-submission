"""Scope regressions using complete case evidence and actual profile artifacts."""

import contextlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from reference.prediction_scope import UNAVAILABLE_COMPONENTS, unavailable_metrics
from reference.scores import composite_component_group_scores, composite_overall_score
from scripts.validate_submission import schema_errors, validate_metrics

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ("ahmedml", "windsorml", "hiliftaeroml")


def spec(dataset):
    return json.loads(
        (ROOT / "benchmark-specs" / dataset / "submission-spec.json").read_text()
    )


@pytest.mark.parametrize("dataset", DATASETS)
def test_scope_scores_and_raw_metric_validation(dataset):
    contract = spec(dataset)
    declaration = contract["overall_score_composite"]
    all_ids = {metric["id"] for metric in contract["metrics"]}
    excluded = unavailable_metrics(dataset, all_ids)
    values = {metric_id: 0.0 for metric_id in all_ids - excluded}
    for component in declaration["components"]:
        if component["metric_id"] not in excluded:
            values[component["metric_id"]] = (
                1.0 if component["transform"] == "bounded_quality" else 0.0
            )
    values.update(
        composite_component_group_scores(
            values,
            declaration,
            contract["component_score_groups"],
            fixed_zero_component_ids=UNAVAILABLE_COMPONENTS,
        )
    )
    values["overall_score"] = composite_overall_score(
        values, declaration, fixed_zero_component_ids=UNAVAILABLE_COMPONENTS
    )
    assert values["overall_score"] == pytest.approx(60)
    assert values["field_score"] == pytest.approx(50)
    assert values["diagnostic_score"] == pytest.approx(40)
    assert values["force_score"] == pytest.approx(100)
    dataset_contract = {**contract, "metric_ids": sorted(all_ids)}
    submission = {
        "dataset_id": dataset,
        "prediction_scope": "surface_only",
        "metric_values": values,
    }
    errors = []
    validate_metrics(
        errors.append,
        submission,
        dataset_contract,
        {"metric_definitions": contract["metrics"]},
    )
    assert errors == []
    values["surface_pressure_rel_l2"] = 7.5
    assert composite_overall_score(
        values, declaration, fixed_zero_component_ids=UNAVAILABLE_COMPONENTS
    ) == pytest.approx(52.5)
    values["volume_pressure_rel_l2"] = 0.0
    errors.clear()
    validate_metrics(
        errors.append,
        submission,
        dataset_contract,
        {"metric_definitions": contract["metrics"]},
    )
    assert any("omit unavailable raw metrics" in error for error in errors)
    values.pop("volume_pressure_rel_l2")
    values.pop("cp_cut_r2")
    errors.clear()
    validate_metrics(
        errors.append,
        submission,
        dataset_contract,
        {"metric_definitions": contract["metrics"]},
    )
    assert any("cp_cut_r2" in error and "missing" in error for error in errors)


@pytest.mark.parametrize("dataset", ("ahmedml", "windsorml"))
def test_surface_split_reduction_requires_complete_cp_and_rejects_volume(
    tmp_path, dataset
):
    if dataset == "ahmedml":
        from reference.ahmedml.dataset_scorer import (
            AhmedMLDatasetScorerError,
            score_candidate_dataset,
        )
        from tests.test_ahmedml_dataset_scorer import _write_full_evidence

        error_type = AhmedMLDatasetScorerError
        evidence = tmp_path / "cases"
        case_ids = _write_full_evidence(evidence)
    else:
        from reference.windsorml.dataset_scorer import (
            WindsorMLDatasetScorerError,
            score_candidate_dataset,
        )
        from tests.test_windsorml_dataset_scorer import write_evidence

        error_type = WindsorMLDatasetScorerError
        evidence = tmp_path
        case_ids = write_evidence(evidence, field_error=0, force_error=0)
    for case_id in case_ids:
        path = evidence / f"{case_id}.json"
        value = json.loads(path.read_text())
        value["prediction_scope"] = "surface_only"
        if dataset == "ahmedml":
            value["metric_values"] = {
                key: raw
                for key, raw in value["metric_values"].items()
                if key not in UNAVAILABLE_COMPONENTS
            }
            value["profiles"]["series"] = value["profiles"]["series"][:3]
        else:
            value.pop("volume")
            value["profiles"]["families"] = {
                key: raw
                for key, raw in value["profiles"]["families"].items()
                if "_cp_" in key
            }
        path.write_text(json.dumps(value))
    kwargs = dict(
        submission_specification=ROOT
        / "benchmark-specs"
        / dataset
        / "submission-spec.json",
        split_id="full",
        case_evidence_directory=evidence,
        prediction_scope="surface_only",
    )
    result = score_candidate_dataset(**kwargs).to_json()
    assert result["metric_values"]["overall_score"] == pytest.approx(60)
    assert not unavailable_metrics(dataset, result["metric_values"])
    first = evidence / f"{case_ids[0]}.json"
    value = json.loads(first.read_text())
    original = json.loads(first.read_text())
    if dataset == "ahmedml":
        value["metric_values"]["volume_pressure_rel_l2"] = 0
    else:
        value["volume"] = {"metrics": {"volume_pressure_rel_l2": 0}}
    first.write_text(json.dumps(value))
    with pytest.raises(error_type, match="unavailable|volume"):
        score_candidate_dataset(**kwargs)
    if dataset == "ahmedml":
        original["profiles"]["series"].pop()
    else:
        original["profiles"]["families"]["windsorml_cp_constant_v1"].pop()
    first.write_text(json.dumps(original))
    with pytest.raises(error_type, match="series|station"):
        score_candidate_dataset(**kwargs)


def test_ahmed_surface_evaluator_never_opens_volume(tmp_path, monkeypatch):
    pytest.importorskip("vtk")
    import reference.ahmedml.evaluator as evaluator
    from reference.ahmedml.support import load_case_support
    from reference.drivaerml.retained_file import RetainedVerifiedFile
    from tests.test_ahmedml_evaluator import make_fixture

    identity, support_path, surface, volume = make_fixture(tmp_path)
    support = load_case_support(support_path, source_identity=identity)

    # The production mmap uses Linux descriptor paths. Read the same retained,
    # checksum-verified surface array through its handle for this portable fixture.
    @contextlib.contextmanager
    def verified_surface_array(support, role):
        assert not role.startswith("volume_")
        artifact = support.artifact(role)
        with RetainedVerifiedFile.open(artifact.path, label=role) as retained:
            assert retained.sha256() == artifact.sha256
            retained.handle.seek(0)
            yield np.load(retained.handle, allow_pickle=False)
            retained.assert_unchanged(context="during test array consumption")

    monkeypatch.setattr(evaluator, "open_support_array", verified_surface_array)
    (tmp_path / "run_1" / "volume_1.vtu").unlink()
    shutil.rmtree(volume.parent)
    result = evaluator.evaluate_candidate_case(
        case_id="run_1",
        dataset_root=tmp_path,
        source_identity=identity,
        case_support=support,
        surface_prediction_manifest=surface,
        prediction_scope="surface_only",
    ).to_json()
    assert set(result["prediction_inputs"]) == {"surface"}
    assert set(result["field_statistics"]) == {"surface_pressure", "surface_wall_shear"}
    assert len(result["profiles"]["series"]) == 3
    assert all(raw == pytest.approx(0) for raw in result["metric_values"].values())
    with pytest.raises(
        evaluator.AhmedMLCandidateEvaluatorError, match="forbids volume"
    ):
        evaluator.evaluate_candidate_case(
            case_id="run_1",
            dataset_root=tmp_path,
            source_identity=identity,
            case_support=support,
            surface_prediction_manifest=surface,
            volume_prediction_manifest=volume,
            prediction_scope="surface_only",
        )


def test_hilift_cp_only_compact_artifact_round_trip_without_volume(tmp_path):
    from reference.hiliftaeroml.compact_profile_evaluator import (
        CompactProfileEvaluationError,
        build_compact_profile_directory,
        score_compact_profile_directory,
    )
    from tests.test_hiliftaeroml_compact_profile_evaluator import (
        CASE_ID,
        CASE_SET_ID,
        SPLIT_ID,
        SUBMISSION_ID,
        _make_release,
    )

    outputs = tmp_path / "native"
    release, manifest_sha, hashes = _make_release(tmp_path, outputs)
    shutil.rmtree(outputs / CASE_ID / "volume_submission_stream")
    hashes = {
        CASE_ID: {
            key: value
            for key, value in hashes[CASE_ID].items()
            if key.startswith("cp_")
        }
    }
    destination = tmp_path / "profiles"
    kwargs = dict(
        submission_id=SUBMISSION_ID,
        split_id=SPLIT_ID,
        case_set_id=CASE_SET_ID,
        support_release_root=release,
        support_manifest_sha256=manifest_sha,
        prediction_scope="surface_only",
    )
    _, scores = build_compact_profile_directory(
        **kwargs,
        case_ids=[CASE_ID],
        outputs_root=None,
        surface_outputs_root=outputs,
        profiles_root=destination,
        expected_case_artifact_sha256=hashes,
    )
    assert set(scores[CASE_ID]) == {"cp_cut_r2"}
    chunk = json.loads((destination / "chunk-000.json").read_text())
    assert schema_errors(chunk, "hiliftaeroml-compact-profile-chunk.schema.json") == []
    index = json.loads((destination / "index.json").read_text())
    assert schema_errors(index, "profile-index.schema.json") == []
    assert "volume_velocity" not in chunk["cases"][0]
    with np.load(
        destination / chunk["cases"][0]["artifact"]["file"], allow_pickle=False
    ) as arrays:
        assert arrays.files == ["cp_q_delta"]
    assert (
        score_compact_profile_directory(
            **kwargs, profiles_root=destination, expected_case_ids=[CASE_ID]
        )
        == scores
    )
    with pytest.raises(CompactProfileEvaluationError):
        score_compact_profile_directory(
            **{**kwargs, "prediction_scope": "surface_and_volume"},
            profiles_root=destination,
            expected_case_ids=[CASE_ID],
        )


@pytest.mark.parametrize(
    "dataset,surface_id,volume_id",
    [
        (
            "ahmedml",
            "ahmedml-surface-native-cells-v1",
            "ahmedml-volume-native-cells-v1",
        ),
        (
            "windsorml",
            "windsorml_surface_native_points",
            "windsorml_volume_native_cells",
        ),
        ("hiliftaeroml", "surface-native-points-v1", "volume-native-valid-points-v1"),
    ],
)
def test_case_validator_accepts_surface_coverage_and_rejects_missing_or_fabricated_support(
    tmp_path, dataset, surface_id, volume_id
):
    import hashlib
    from copy import deepcopy

    from scripts.validate_submission import validate_v3_case_metrics

    case_ids = ["case-001", "case-002"]
    field_ids = ("surface_pressure_rel_l2", "surface_wall_shear_rel_l2")

    def binding(metric_id):
        return {
            "metric_id": metric_id,
            "quantity_id": "pressure" if "pressure" in metric_id else "wall_shear",
            "reduction": "relative_l2_percent",
            "weighting": "support_weights",
            "dataset_weighting": "surface_face_area",
            "aggregation": "per_geometry_then_macro_average",
            "case_evidence": "metric_value",
        }

    support_manifest = {
        "supports": [
            {
                "id": surface_id,
                "domain": "surface",
                "extrapolation_policy": "forbidden",
                "metric_bindings": [binding(metric_id) for metric_id in field_ids],
            },
            {
                "id": volume_id,
                "domain": "volume",
                "extrapolation_policy": "forbidden",
                "metric_bindings": [binding("volume_pressure_rel_l2")],
            },
        ]
    }
    support_index = {
        "_loaded_cases": [
            {
                "case_id": case_id,
                "support_instances": [
                    {"support_id": surface_id, "entity_count": 2},
                    {"support_id": volume_id, "entity_count": 3},
                ],
            }
            for case_id in case_ids
        ]
    }
    if dataset == "hiliftaeroml":
        support_manifest["supports"].append(
            {
                "id": "aerodynamic-case-coefficients-v1",
                "domain": "scalar_case",
                "extrapolation_policy": "forbidden",
                "metric_bindings": [
                    {
                        "metric_id": metric_id,
                        "quantity_id": metric_id,
                        "reduction": "mae",
                        "weighting": "uniform",
                        "dataset_weighting": "case_equal",
                        "aggregation": "all_test_cases",
                        "case_evidence": "metric_value",
                    }
                    for metric_id in ("c_drag_mae", "c_lift_mae", "c_pitch_mae")
                ],
            }
        )
        for case in support_index["_loaded_cases"]:
            case["support_instances"].append(
                {"support_id": "aerodynamic-case-coefficients-v1", "entity_count": 1}
            )
    values = {metric_id: 0.0 for metric_id in field_ids}
    if dataset == "hiliftaeroml":
        values.update(
            cd_r2=1.0, cl_r2=1.0, c_drag_mae=0.0, c_lift_mae=0.0, c_pitch_mae=0.0
        )
    submission = {
        "submission_id": "surface-coverage-test",
        "dataset_id": dataset,
        "split_id": "full",
        "case_set_id": "surface-test",
        "prediction_scope": "surface_only",
        "scoring_support": {
            "release_id": "surface-test-support",
            "manifest_sha256": "a" * 64,
        },
        "case_metrics": {"file": "cases.json", "sha256": "0" * 64, "case_count": 2},
        "metric_values": values,
    }
    cases = []
    for index, case_id in enumerate(case_ids):
        case = {
            "case_id": case_id,
            "supports": [
                {
                    "support_id": surface_id,
                    "support_count": 2,
                    "scored_count": 2,
                    "coverage_fraction": 1.0,
                    "weight_coverage_fraction": 1.0,
                    "unmapped_count": 0,
                    "extrapolated_count": 0,
                    "metric_values": {key: 0.0 for key in field_ids},
                    "metric_sufficient_statistics": {
                        key: {
                            "reduction": "relative_l2_percent",
                            "weighting": "support_weights",
                            "dataset_weighting": "surface_face_area",
                            "numerator": 0.0,
                            "denominator": 1.0,
                            "entity_count": 2,
                            "total_weight": 2.0,
                        }
                        for key in field_ids
                    },
                }
            ],
        }
        if dataset == "hiliftaeroml":
            case["force_coefficients"] = {
                prefix + name: float(index + 1)
                for prefix in ("predicted_", "truth_")
                for name in ("c_drag", "c_lift", "c_pitch")
            }
            case["nonspatial_metric_values"] = {
                "c_drag_mae": 0.0,
                "c_lift_mae": 0.0,
                "c_pitch_mae": 0.0,
            }
        if dataset == "hiliftaeroml":
            case["supports"].append(
                {
                    "support_id": "aerodynamic-case-coefficients-v1",
                    "support_count": 1,
                    "scored_count": 1,
                    "coverage_fraction": 1.0,
                    "weight_coverage_fraction": 1.0,
                    "unmapped_count": 0,
                    "extrapolated_count": 0,
                    "metric_values": dict(case["nonspatial_metric_values"]),
                    "metric_sufficient_statistics": {},
                }
            )
        cases.append(case)
    document = {
        "$schema": "https://fluidsbench.org/schemas/v3/case-metrics.schema.json",
        "schema_version": "1.0",
        "submission_id": submission["submission_id"],
        "dataset_id": dataset,
        "split_id": "full",
        "case_set_id": "surface-test",
        "scoring_support_release_id": "surface-test-support",
        "scoring_support_manifest_sha256": "a" * 64,
        "case_count": 2,
        "metric_values": values,
        "cases": cases,
    }
    path = tmp_path / "cases.json"

    def validate(value):
        payload = json.dumps(value).encode()
        path.write_bytes(payload)
        submission["case_metrics"]["sha256"] = hashlib.sha256(payload).hexdigest()
        errors = []
        validate_v3_case_metrics(
            errors.append,
            tmp_path,
            submission,
            case_ids,
            support_manifest,
            support_index,
        )
        return errors

    assert validate(document) == []
    missing = deepcopy(document)
    missing["cases"][0]["supports"].clear()
    assert any("missing scoring supports" in error for error in validate(missing))
    fabricated = deepcopy(document)
    fabricated["cases"][0]["supports"].append(
        {**cases[0]["supports"][0], "support_id": volume_id}
    )
    assert any("unexpected support_id" in error for error in validate(fabricated))
