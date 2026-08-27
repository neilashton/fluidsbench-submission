from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from reference.drivaerml.dataset_scorer import (
    CandidateDatasetEvaluation,
    DrivAerDatasetScorerError,
    RELATIVE_PROFILE_CONTRACT_ID,
    RELATIVE_PROFILE_CONTRACT_SHA256,
    RELATIVE_PROFILE_FORMAT,
    RELATIVE_PROFILE_SCHEMA_VERSION,
    _relative_profile_expected_keys,
    schema_v3_relative_profile_chunks_candidate_adapter,
    validate_schema_v3_relative_profile_chunk_candidate,
    write_schema_v3_profile_chunks_candidate,
)
from scripts.validate_submission import sha256_file, validate_profiles


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def sample_count(station_id: str) -> int:
    station = station_id.removeprefix("autocfd5_").upper()
    if station.startswith("V"):
        return 201
    if station.startswith("U"):
        return 301
    if station == "L1":
        return 651
    return 31


def constant_interval_end(station_id: str) -> float:
    station = station_id.removeprefix("autocfd5_").upper()
    if station.startswith("V"):
        return 2.0
    if station.startswith("U"):
        return 3.0
    if station == "L1":
        return 6.5
    return {
        "R1": 0.300000876107,
        "R2": 0.300000877067,
        "R3": 0.300000591286,
    }[station]


def namespaced_series() -> list[dict]:
    result: list[dict] = []
    canonical_cp_digests: dict[str, str] = {}
    for panel_id, family_id, station_id, quantity_id, representation in (
        _relative_profile_expected_keys()
    ):
        relative = family_id in {
            "drivaerml-velocity-relative-v3",
            "drivaerml_cp_relative_v1",
        }
        common = {
            "panel_id": panel_id,
            "family_id": family_id,
            "placement_mode": "relative" if relative else "constant",
            "station_id": station_id,
            "quantity_id": quantity_id,
            "scoring_role": "report_only" if relative else "inherits_parent_candidate",
            "representation": representation,
            "placement_receipt_identity_sha256": digest(
                f"receipt:{family_id}:{station_id}"
            ),
        }
        if representation == "shared_alias":
            shared_id = {
                "upperbody_centerline": "drivaerml-cp-upperbody-centerline-y0-v1",
                "underbody_centerline": "drivaerml-cp-underbody-centerline-y0-v1",
            }[station_id]
            common["shared_support_ref"] = {
                "shared_support_id": shared_id,
                "canonical_family_id": "drivaerml_cp_constant_v1",
                "canonical_station_id": station_id,
                "canonical_support_identity_sha256": canonical_cp_digests[station_id],
            }
        else:
            support_digest = digest(f"support:{family_id}:{station_id}")
            common["support_identity_sha256"] = support_digest
            if family_id == "drivaerml_cp_constant_v1" and station_id in {
                "upperbody_centerline",
                "underbody_centerline",
            }:
                canonical_cp_digests[station_id] = support_digest
            if panel_id == "velocity_profiles":
                count = sample_count(station_id)
                if relative:
                    coordinates = [index / (count - 1) for index in range(count)]
                    common.update(
                        {
                            "coordinate_id": "normalized_arc_length",
                            "coordinate_unit": "1",
                        }
                    )
                else:
                    end = constant_interval_end(station_id)
                    coordinates = [end * index / (count - 1) for index in range(count)]
                    common.update(
                        {"coordinate_id": "distance_m", "coordinate_unit": "m"}
                    )
                common["coordinate"] = coordinates
                common["prediction"] = [0.5] * count
            else:
                common.update(
                    {
                        "coordinate_id": "arc_length_m",
                        "coordinate_unit": "m",
                        "coordinate": [0.0, 1.0],
                        "prediction": [0.1, 0.2],
                    }
                )
        result.append(common)
    return result


def chunk(case_id: str = "run_1") -> dict:
    return {
        "schema_version": RELATIVE_PROFILE_SCHEMA_VERSION,
        "contract_id": RELATIVE_PROFILE_CONTRACT_ID,
        "contract_sha256": RELATIVE_PROFILE_CONTRACT_SHA256,
        "cases": [{"case_id": case_id, "series": namespaced_series()}],
    }


class DrivAerMLRelativeProfileTests(unittest.TestCase):
    def test_contract_schema_and_closed_scoring_policy_are_bound(self) -> None:
        bindings = json.loads(
            (ROOT / "benchmark-specs" / "drivaerml" / "candidate-release-bindings.json").read_text()
        )
        contract_path = (
            ROOT
            / "benchmark-specs"
            / "drivaerml"
            / bindings["relative_diagnostics_v3"]["file"]
        )
        self.assertEqual(sha256_file(contract_path), RELATIVE_PROFILE_CONTRACT_SHA256)
        contract = json.loads(contract_path.read_text())
        self.assertFalse(contract["activation_by_this_file"])
        self.assertEqual(
            contract["scoring_and_rollout"]["constant_family_policy"], "unchanged"
        )
        self.assertEqual(
            contract["scoring_and_rollout"]["relative_composite_weight"], 0.0
        )
        self.assertEqual(
            contract["status"],
            "candidate_report_only_support_manifest_publication_and_activation_pending",
        )
        self.assertEqual(
            contract["activation_gates"],
            {
                "all_484_velocity_placement_manifest_bound": False,
                "all_484_velocity_mapping_manifest_bound": False,
                "all_484_cp_manifest_bound": False,
                "genuine_model_sensitivity_review_complete": False,
                "owner_scientific_approval": False,
                "immutable_evaluator_revision_bound": False,
            },
        )
        self.assertEqual(bindings["relative_support"]["status"], "unresolved")
        velocity_contract = contract["support_implementation_bindings"][
            "relative_velocity_v3"
        ]["mapping_all484_manifest"]
        velocity_handoff = bindings["relative_support"][
            "velocity_mapping_manifest"
        ]
        self.assertEqual(
            velocity_contract["producer_path"], velocity_handoff["producer_file"]
        )
        self.assertTrue(
            velocity_handoff["manifest_sha256"].startswith(
                "__UNRESOLVED_DRIVAERML_"
            )
        )
        cp_contract = contract["support_implementation_bindings"][
            "relative_cp_v1"
        ]["cp_all484_manifest"]
        cp_handoff = bindings["relative_support"]["cp_manifest"]
        self.assertEqual(cp_contract["producer_path"], cp_handoff["producer_file"])
        self.assertTrue(
            cp_handoff["manifest_sha256"].startswith("__UNRESOLVED_DRIVAERML_")
        )
        placement_contract = contract["support_implementation_bindings"][
            "relative_velocity_v3"
        ]["placement_all484_manifest"]
        placement_handoff = bindings["relative_support"][
            "velocity_placement_manifest"
        ]
        self.assertEqual(
            placement_contract["producer_path"], placement_handoff["producer_file"]
        )
        self.assertTrue(
            placement_handoff["manifest_sha256"].startswith(
                "__UNRESOLVED_DRIVAERML_"
            )
        )

    def test_complete_namespaced_chunk_passes_schema_and_semantics(self) -> None:
        document = chunk()
        schema = json.loads(
            (ROOT / "schemas" / "v1" / "drivaerml-relative-profile-chunk.schema.json").read_text()
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(document)), [])
        normalized = validate_schema_v3_relative_profile_chunk_candidate(document)
        self.assertEqual(len(normalized["cases"][0]["series"]), 40)
        aliases = [
            series
            for series in normalized["cases"][0]["series"]
            if series["representation"] == "shared_alias"
        ]
        self.assertEqual(len(aliases), 2)

    def test_semantics_reject_stale_velocity_families_and_alias_identity_mismatch(self) -> None:
        for stale_family in (
            "drivaerml-velocity-relative-v1",
            "drivaerml-velocity-relative-v2",
        ):
            with self.subTest(stale_family=stale_family):
                stale = chunk()
                relative_velocity = next(
                    series
                    for series in stale["cases"][0]["series"]
                    if series["family_id"] == "drivaerml-velocity-relative-v3"
                )
                relative_velocity["family_id"] = stale_family
                with self.assertRaisesRegex(DrivAerDatasetScorerError, "undeclared"):
                    validate_schema_v3_relative_profile_chunk_candidate(stale)

        mismatched = chunk()
        alias = next(
            series
            for series in mismatched["cases"][0]["series"]
            if series["representation"] == "shared_alias"
        )
        alias["shared_support_ref"]["canonical_support_identity_sha256"] = digest(
            "wrong-canonical-support"
        )
        with self.assertRaisesRegex(DrivAerDatasetScorerError, "alias identity differs"):
            validate_schema_v3_relative_profile_chunk_candidate(mismatched)

        drifted = chunk()
        constant_velocity = next(
            series
            for series in drifted["cases"][0]["series"]
            if series["family_id"] == "drivaerml-autocfd5-constant-v1"
        )
        constant_velocity["coordinate"][1] += 1.0e-4
        with self.assertRaisesRegex(
            DrivAerDatasetScorerError, "preserve the frozen constant coordinate grid"
        ):
            validate_schema_v3_relative_profile_chunk_candidate(drifted)

        incomplete = chunk()
        incomplete["cases"][0]["series"].pop()
        with self.assertRaisesRegex(DrivAerDatasetScorerError, "exactly 40"):
            validate_schema_v3_relative_profile_chunk_candidate(incomplete)

    def test_adapter_writes_40_series_per_case_without_changing_legacy_writer(self) -> None:
        evaluation = CandidateDatasetEvaluation(
            {
                "split": {
                    "split_id": "full",
                    "case_set_id": "standard",
                    "case_ids": ["run_1", "run_2"],
                }
            }
        )
        package = schema_v3_relative_profile_chunks_candidate_adapter(
            evaluation,
            submission_id="relative-profile-test",
            namespaced_series_by_case={
                "run_1": namespaced_series(),
                "run_2": namespaced_series(),
            },
            cases_per_chunk=1,
        )
        self.assertEqual(package.index["format"], RELATIVE_PROFILE_FORMAT)
        with tempfile.TemporaryDirectory() as temporary:
            receipt = write_schema_v3_profile_chunks_candidate(
                package, Path(temporary) / "profiles"
            )
        self.assertEqual(receipt["case_count"], 2)
        self.assertEqual(receipt["series_count"], 80)

    def test_submission_validator_is_fail_closed_until_benchmark_gate_is_ready(self) -> None:
        evaluation = CandidateDatasetEvaluation(
            {
                "split": {
                    "split_id": "full",
                    "case_set_id": "standard",
                    "case_ids": ["run_1"],
                }
            }
        )
        package = schema_v3_relative_profile_chunks_candidate_adapter(
            evaluation,
            submission_id="relative-profile-test",
            namespaced_series_by_case={"run_1": namespaced_series()},
        )
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            directory = temporary_root / "submissions" / "drivaerml" / "relative-profile-test"
            write_schema_v3_profile_chunks_candidate(package, directory / "profiles")
            split_path = temporary_root / "benchmark-specs" / "drivaerml" / "splits" / "full.json"
            split = {
                "schema_version": "1.0",
                "dataset_id": "drivaerml",
                "split_id": "full",
                "case_set_id": "standard",
                "case_id_status": "official",
                "case_count": 1,
                "case_ids": ["run_1"],
            }
            write_json(split_path, split)
            submission = {
                "submission_id": "relative-profile-test",
                "dataset_id": "drivaerml",
                "split_id": "full",
                "case_set_id": "standard",
                "split_sha256": sha256_file(split_path),
                "profile_data": {
                    "format": RELATIVE_PROFILE_FORMAT,
                    "index_file": "profiles/index.json",
                    "case_count": 1,
                    "case_set_id": "standard",
                },
            }
            split_entry = {
                "index_file": "splits/full.json",
                "sha256": sha256_file(split_path),
                "case_set_id": "standard",
                "case_id_status": "official",
                "case_count": 1,
            }
            ready_spec = {
                "profile_panels": [],
                "relative_diagnostics": {
                    "status": "candidate_support_ready",
                    "profile_format_enabled": True,
                    "contract": {"sha256": RELATIVE_PROFILE_CONTRACT_SHA256},
                },
            }
            errors: list[str] = []
            with patch("scripts.validate_submission.ROOT", temporary_root):
                stats = validate_profiles(
                    errors.append,
                    directory,
                    submission,
                    ready_spec,
                    split_entry,
                )
            self.assertEqual(errors, [])
            self.assertEqual(stats, {"cases": 1, "series": 40})

            pending_spec = copy.deepcopy(ready_spec)
            pending_spec["relative_diagnostics"].update(
                {"status": "support_pending", "profile_format_enabled": False}
            )
            errors = []
            with patch("scripts.validate_submission.ROOT", temporary_root):
                validate_profiles(
                    errors.append,
                    directory,
                    submission,
                    pending_spec,
                    split_entry,
                )
            self.assertIn("relative profile format is closed", "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
