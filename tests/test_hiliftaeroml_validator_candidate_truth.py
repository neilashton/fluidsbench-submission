from __future__ import annotations

from pathlib import Path

from scripts import validate_submission as validator


def _submission() -> dict:
    return {
        "schema_version": "3.0",
        "submission_id": "hilift-candidate-test",
        "dataset_id": "hiliftaeroml",
        "split_id": "full",
        "case_set_id": "caseset-test",
        "methodology": {"record_kind": "submitter_reported"},
        "evaluation": {},
        "reproducibility": {
            "contract_version": "open-reproducibility-3.0",
        },
        "profile_data": {
            "profile_ground_truth_release_id": "candidate-truth-v1",
            "profile_ground_truth_manifest_sha256": "a" * 64,
        },
        "metric_values": {
            "cp_cut_r2": 0.5,
            "velocity_profile_r2": 0.75,
        },
    }


def _case_metrics() -> dict:
    return {
        "cases": [
            {
                "case_id": "case-a",
                "nonspatial_metric_values": {
                    "cp_cut_r2": 0.25,
                    "velocity_profile_r2": 0.5,
                },
            },
            {
                "case_id": "case-b",
                "nonspatial_metric_values": {
                    "cp_cut_r2": 0.75,
                    "velocity_profile_r2": 1.0,
                },
            },
        ]
    }


def _scores() -> dict[str, dict[str, float]]:
    return {
        "case-a": {"cp_cut_r2": 0.25, "velocity_profile_r2": 0.5},
        "case-b": {"cp_cut_r2": 0.75, "velocity_profile_r2": 1.0},
    }


def test_hidden_profile_scores_bind_per_case_and_macro_aggregates() -> None:
    errors: list[str] = []
    validator._validate_hilift_native_profile_score_bindings(
        errors.append,
        submission=_submission(),
        case_metrics=_case_metrics(),
        recomputed_scores=_scores(),
    )
    assert errors == []


def test_hidden_profile_score_mismatches_are_rejected() -> None:
    submission = _submission()
    submission["metric_values"]["velocity_profile_r2"] = 0.7
    case_metrics = _case_metrics()
    case_metrics["cases"][0]["nonspatial_metric_values"]["cp_cut_r2"] = 0.2
    errors: list[str] = []
    validator._validate_hilift_native_profile_score_bindings(
        errors.append,
        submission=submission,
        case_metrics=case_metrics,
        recomputed_scores=_scores(),
    )
    joined = "\n".join(errors)
    assert "case-a nonspatial_metric_values.cp_cut_r2" in joined
    assert "metric_values.velocity_profile_r2" in joined


def test_candidate_truth_release_is_rejected_outside_candidate_mode() -> None:
    errors, totals = validator.validate_many(
        [],
        candidate_profile_truth_release=Path("/tmp/inactive-candidate-truth"),
    )
    assert errors == [
        "--candidate-profile-truth-release requires --candidate-dry-run"
    ]
    assert totals == {"submissions": 0, "cases": 0, "series": 0}


def test_candidate_reproducibility_uses_candidate_truth_declaration() -> None:
    submission = _submission()
    dataset_spec = {
        "status": "owner_review_required",
        "profile_definition": {
            "profile_ground_truth": {
                "status": "not_published",
                "release_id": None,
                "manifest_sha256": None,
            },
            "candidate_dry_run_profile_ground_truth": {
                "status": "complete_candidate_not_published",
                "release_id": "candidate-truth-v1",
                "manifest_sha256": "a" * 64,
            },
        },
    }
    manifest = {
        "data_release": {
            "profile_ground_truth": {
                "release_id": "unrelated-active-truth",
                "manifest_sha256": "b" * 64,
            }
        }
    }
    errors: list[str] = []
    validator.validate_open_reproducibility(
        errors.append,
        Path("/tmp/does-not-exist"),
        submission,
        {"status": "submitted_evaluation"},
        manifest,
        dataset_spec,
        {"index_file": "does-not-exist.json"},
        contributor_stage=False,
        candidate_dry_run=True,
    )
    assert not [error for error in errors if "profile_ground_truth" in error]


def test_unpublished_public_truth_closes_hilift_native_profile_intake(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    submission = {
        "submission_id": "hilift-candidate-test",
        "dataset_id": "hiliftaeroml",
        "split_id": "full",
        "case_set_id": "caseset-test",
        "profile_data": {
            "format": validator.HILIFT_PROFILE_FORMAT,
            "index_file": "profiles/index.json",
            "case_count": 1,
            "case_set_id": "caseset-test",
        },
    }
    dataset_spec = {
        "profile_definition": {
            "profile_ground_truth": {
                "status": "not_published",
                "release_id": None,
                "manifest_sha256": None,
            },
            "candidate_dry_run_profile_ground_truth": {
                "release_id": "candidate-truth-v1",
                "manifest_sha256": "a" * 64,
            },
        }
    }
    split_entry = {"index_file": "splits/full.json"}

    public_errors: list[str] = []
    validator.validate_profiles(
        public_errors.append,
        tmp_path,
        submission,
        dataset_spec,
        split_entry,
    )
    assert "native profile intake is closed" in "\n".join(public_errors)

    candidate_errors: list[str] = []
    validator.validate_profiles(
        candidate_errors.append,
        tmp_path,
        submission,
        dataset_spec,
        split_entry,
        candidate_dry_run=True,
    )
    assert "explicit local candidate profile-truth release" in "\n".join(
        candidate_errors
    )
