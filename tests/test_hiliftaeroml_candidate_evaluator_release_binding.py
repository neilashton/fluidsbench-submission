from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "benchmark-specs" / "hiliftaeroml"
BINDING_PATH = DATASET_ROOT / "candidate-evaluator-release-binding.json"
TOKEN_PREFIX = "__UNRESOLVED_HILIFTAEROML_"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unresolved_tokens(value: object) -> list[str]:
    if isinstance(value, dict):
        return [
            token
            for child in value.values()
            for token in unresolved_tokens(child)
        ]
    if isinstance(value, list):
        return [token for child in value for token in unresolved_tokens(child)]
    if (
        isinstance(value, str)
        and value != TOKEN_PREFIX
        and value.startswith(TOKEN_PREFIX)
    ):
        return [value]
    return []


def load_binding() -> dict:
    value = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_candidate_binding_is_nonactivating_and_fail_closed() -> None:
    binding = load_binding()
    assert binding["schema"] == (
        "hiliftaeroml-fluidsbench-candidate-evaluator-release-binding-v1"
    )
    assert binding["schema_version"] == 1
    assert binding["status"] == "prepared_evidence_bound_revision_unresolved"
    assert binding["activation_effect"] == "none"
    assert binding["dataset_id"] == "hiliftaeroml"
    assert binding["unresolved_token_prefix"] == TOKEN_PREFIX

    gates = binding["activation_gates"]
    assert gates["force_truth_policy_selected"] is True
    assert gates["force_coefficient_normalization_selected"] is True
    assert gates["force_truth_policy_implemented_in_native_evaluator"] is False
    assert gates["full_360_force_and_overall_replay_complete"] is False
    assert gates["evaluator_implementation_manifest_complete"] is False
    assert gates["immutable_evaluator_revision_bound"] is False
    assert gates["owner_scientific_approval"] is False
    assert gates["public_profile_truth_published"] is False
    assert gates["submissions_open"] is False

    tokens = unresolved_tokens(binding)
    assert set(tokens) == {
        "__UNRESOLVED_HILIFTAEROML_EVALUATOR_CODE_REVISION__",
        "__UNRESOLVED_HILIFTAEROML_NATIVE_EVALUATOR_CODE_REVISION__",
        "__UNRESOLVED_HILIFTAEROML_FORCE_POLICY_IMPLEMENTATION_EVIDENCE_SHA256__",
        "__UNRESOLVED_HILIFTAEROML_EVALUATOR_RUNTIME_LOCK_SHA256__",
        "__UNRESOLVED_HILIFTAEROML_EVALUATOR_IMPLEMENTATION_MANIFEST_SHA256__",
        "__UNRESOLVED_HILIFTAEROML_OWNER_APPROVAL_RECORD_SHA256__",
    }


def test_retained_evidence_hashes_match_repository_bytes() -> None:
    binding = load_binding()
    evidence = binding["retained_evidence_bindings"]
    assert len({item["id"] for item in evidence}) == len(evidence)
    assert len({item["file"] for item in evidence}) == len(evidence)
    for item in evidence:
        relative = Path(item["file"])
        assert not relative.is_absolute()
        assert ".." not in relative.parts
        path = DATASET_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert sha256_file(path) == item["sha256"]


def test_force_policy_preserves_perfect_prediction_and_complete_case_scoring() -> None:
    policy = load_binding()["force_truth_policy"]
    assert policy["scored_truth_source"] == (
        "canonical_reintegration_of_native_surface_truth_fields_for_every_case"
    )
    assert policy["coefficient_normalization"] == "case_qRef_from_ref_values_csv"
    assert policy["monitor_comparison_protocol"] == (
        "hilift-native-truth-vs-monitor-ci95-v1"
    )
    assert policy["current_native_pitching_moment_status"] == (
        "vertex_lumped_diagnostic_not_acceptable_as_claimed_exact_scored_cm"
    )
    assert policy["perfect_surface_prediction_must_receive_perfect_load_metrics"] is True
    assert policy["case_exclusion_or_downweighting_permitted"] is False
    assert policy["per_case_tolerance_inflation_permitted"] is False
    assert policy["published_force_moment_csv_role"] == (
        "released_reference_and_provenance_diagnostic; six documented "
        "mean-coefficient rows are canonical surface-integrated overrides"
    )
    assert len(policy["historical_public_monitor_mismatch_case_ids"]) == 5
    assert policy["historical_outside_current_union_monitor_mismatch_case_ids"] == [
        "geo_LHC129_AoA_4"
    ]
    assert policy["surface_reintegration_value_substitution_case_count"] == 6


def test_force_release_is_bound_separately_from_unchanged_vtu_archives() -> None:
    release = load_binding()["dataset_force_release_binding"]
    assert release["status"] == "published_and_remote_sha256_verified"
    assert release["release_revision"] == (
        "bbec30bcfc6103309c1375c5228b3ad0a586bfaf"
    )
    assert release["release_tag"] == "force-mom-overrides-v1.1"
    assert release["pre_update_revision"] == (
        "dd186e13724f39fc94186308519748cca32399eb"
    )
    assert release["pre_update_tag"] == "force-mom-monitor-v1"
    assert release["archive_source_inventory_revision"] == (
        "1c266d3869bc2968ff97d2107c9c3919be03ed32"
    )
    assert release["archive_source_objects_changed"] is False
    assert release["manifest"] == {
        "file": "force_mom_surface_overrides_v1.json",
        "sha256": "ccdb8e4f9f26176fd5eef8c87efbef5f1a9a211335d37694dcd8c1278a414f2f",
    }
    assert release["aggregate"]["changed_rows"] == 6
    assert release["aggregate"]["unchanged_rows"] == 1794
    assert len(release["per_case_csv_sha256"]) == 6


def test_external_audits_are_bound_but_not_misrepresented_as_final_freeze() -> None:
    external = load_binding()["external_audit_bindings"]
    moment = external["exact_moment_all_1800"]
    assert moment["status"] == "complete_validation_passed"
    assert moment["case_count"] == 1800
    assert moment["fluidsbench_union_case_count"] == 1355
    assert moment["published_coefficients_modified"] is False
    assert moment["source_fields_modified"] is False

    full = external["transolver_full_360_legacy_native_aggregate"]
    assert full["case_count"] == 360
    assert full["force_score_computed"] is False
    assert full["overall_score_computed"] is False
    assert full["acceptable_as_final_freeze_evidence"] is False
