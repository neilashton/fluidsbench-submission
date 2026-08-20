from __future__ import annotations

import copy
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from scripts.aggregate_drivaerml_native_volume_audits import (
    AGGREGATE_SCHEMA,
    CASE_AUDIT_SCHEMA,
    COMPARISON_CHUNK_CELLS,
    MAX_ADDITIVE_RELATIVE_DIFFERENCE,
    MAX_METRIC_ABSOLUTE_DIFFERENCE,
    PRIMARY_ALL_CASE_AUDIT_SCHEMA,
    PRIMARY_PILOT_AGGREGATE_SCHEMA,
    REFERENCE_CHUNK_CELLS,
    WEIGHT_AGGREGATE_SCHEMA,
    ZERO_PREDICTION_ROLE,
    NativeVolumeAuditAggregateError,
    aggregate_native_volume_audits,
    aggregate_native_volume_primary_all_case_audit,
    aggregate_native_volume_primary_pilot,
    sha256_file,
    write_evidence,
)


CASE_IDS = ("run_1", "run_44")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _difference_rows() -> dict[str, dict[str, float]]:
    return {
        name: {"absolute_difference": 0.0, "relative_difference": 0.0}
        for name in (
            "absolute_error",
            "squared_error",
            "squared_truth",
            "total_weight",
        )
    }


class NativeVolumeAuditFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.case_counts = {"run_1": 1_500_010, "run_44": 1_600_020}
        self.weight_sums = {"run_1": 2.0, "run_44": 2.25}
        self.pin = self._make_pin()
        self.pin_path = root / "native-source-pin.json"
        _write_json(self.pin_path, self.pin)
        self.pin_sha256 = sha256_file(self.pin_path)
        self.weight_aggregate = self._make_weight_aggregate()
        self.weight_aggregate_path = root / "volume-weight-aggregate.json"
        _write_json(self.weight_aggregate_path, self.weight_aggregate)
        self.receipt_paths: list[Path] = []
        for case_id in CASE_IDS:
            path = root / f"{case_id}-native-volume-audit.json"
            _write_json(path, self._make_receipt(case_id))
            self.receipt_paths.append(path)

    def _make_pin(self) -> dict[str, object]:
        cases: list[dict[str, object]] = []
        for case_id in CASE_IDS:
            run_number = int(case_id.removeprefix("run_"))
            part_count = 2 if case_id == "run_1" else 3
            part_payloads = [
                f"{case_id}-part-{index}".encode("ascii") * (23 + index)
                for index in range(part_count)
            ]
            logical_path = f"{case_id}/volume_{run_number}.vtu"
            boundary = f"{case_id}-boundary".encode("ascii")
            boundary_sha = _sha256_bytes(boundary)
            cases.append(
                {
                    "case_id": case_id,
                    "run_number": run_number,
                    "boundary": {
                        "path": f"{case_id}/boundary_{run_number}.vtp",
                        "size_bytes": len(boundary),
                        "lfs_sha256": boundary_sha,
                    },
                    "surface_cell_area": {
                        "path": f"{case_id}/boundary_cell_area_{run_number}.npy",
                        "size_bytes": 132,
                        "lfs_sha256": _sha256_bytes(
                            f"{case_id}-areas".encode("ascii")
                        ),
                        "dtype": "<f4",
                        "element_count": 1,
                        "source_boundary_sha256": boundary_sha,
                    },
                    "volume": {
                        "logical_path_after_assembly": logical_path,
                        "part_count": part_count,
                        "parts": [
                            {
                                "part_index": index,
                                "path": f"{logical_path}.{index:02d}.part",
                                "size_bytes": len(payload),
                                "lfs_sha256": _sha256_bytes(payload),
                            }
                            for index, payload in enumerate(part_payloads)
                        ],
                        "total_size_bytes": sum(map(len, part_payloads)),
                    },
                }
            )
        return {
            "schema": "drivaerml-fluidsbench-public-native-source-pin-v1",
            "schema_version": 1,
            "repository": {
                "provider": "Hugging Face Hub",
                "repo_id": "synthetic/drivaerml",
                "repo_type": "dataset",
                "revision": "a" * 40,
            },
            "case_scope": {
                "case_count": 2,
                "run_number_min": 1,
                "run_number_max": 44,
                "unavailable_or_held_back_run_numbers": list(range(2, 44)),
            },
            "cases": cases,
            "totals": {
                "boundary_file_count": 2,
                "boundary_bytes": sum(
                    case["boundary"]["size_bytes"] for case in cases
                ),
                "surface_cell_area_file_count": 2,
                "surface_cell_area_bytes": 264,
                "logical_volume_count": 2,
                "volume_part_file_count": 5,
                "reconstructed_volume_bytes": sum(
                    case["volume"]["total_size_bytes"] for case in cases
                ),
            },
        }

    def _case_pin(self, case_id: str) -> dict[str, object]:
        return next(case for case in self.pin["cases"] if case["case_id"] == case_id)

    def _source_binding(self, case_id: str) -> dict[str, object]:
        case = self._case_pin(case_id)
        return {
            "pin": {
                "sha256": self.pin_sha256,
                "repository_id": "synthetic/drivaerml",
                "repository_revision": "a" * 40,
            },
            "case_id": case_id,
            "logical_volume": {
                "path": case["volume"]["logical_path_after_assembly"],
                "size_bytes": case["volume"]["total_size_bytes"],
                "ordered_verified_segments": [
                    {
                        "part_index": part["part_index"],
                        "size_bytes": part["size_bytes"],
                        "sha256": part["lfs_sha256"],
                    }
                    for part in case["volume"]["parts"]
                ],
            },
            "verification": {
                "method": "exact_ordered_segment_size_and_sha256",
                "timing": "completed_before_vtk_geometry_reader",
                "vtk_input": "retained_verified_file_descriptor",
                "post_vtk_fstat": "unchanged",
            },
        }

    def _weight_output(self, case_id: str) -> dict[str, object]:
        run_number = int(case_id.removeprefix("run_"))
        count = self.case_counts[case_id]
        total = self.weight_sums[case_id]
        return {
            "file": f"volume_cell_volume_{run_number}.npy",
            "dtype": "<f8",
            "shape": [count],
            "cell_count": count,
            "size_bytes": 128 + 8 * count,
            "sha256": _sha256_bytes(f"{case_id}-weights".encode("ascii")),
            "volume_sum_m3": total,
            "volume_min_m3": 1.0e-6,
            "volume_max_m3": 2.0e-6,
        }

    def _make_weight_aggregate(self) -> dict[str, object]:
        cases = [
            {
                "case_id": case_id,
                "receipt_sha256": _sha256_bytes(
                    f"{case_id}-weight-receipt".encode("ascii")
                ),
                "native_source_binding": self._source_binding(case_id),
                "output": self._weight_output(case_id),
                "reader_audit": {},
            }
            for case_id in CASE_IDS
        ]
        outputs = [case["output"] for case in cases]
        return {
            "schema": WEIGHT_AGGREGATE_SCHEMA,
            "mode": "complete",
            "status": "complete_all_official_cases_candidate_evidence",
            "complete": True,
            "public_evidence_eligible": True,
            "activation_status": "does_not_activate_scoring_contract",
            "case_count": 2,
            "official_case_count": 2,
            "omitted_official_case_count": 0,
            "case_order": "native_source_pin_increasing_run_number",
            "source": {
                "dataset": {
                    "provider": "Hugging Face Hub",
                    "repo_id": "synthetic/drivaerml",
                    "revision": "a" * 40,
                },
                "native_source_pin": {
                    "schema": "drivaerml-fluidsbench-public-native-source-pin-v1",
                    "sha256": self.pin_sha256,
                },
                "assembled_vtu_identity": (
                    "exact_ordered_part_segment_size_and_sha256_verified_before_vtk"
                ),
            },
            "dependencies": {},
            "algorithm": {},
            "aggregate": {
                "cell_count": sum(output["cell_count"] for output in outputs),
                "source_vtu_size_bytes": sum(
                    self._case_pin(case_id)["volume"]["total_size_bytes"]
                    for case_id in CASE_IDS
                ),
                "output_size_bytes": sum(output["size_bytes"] for output in outputs),
                "volume_sum_m3": math.fsum(
                    output["volume_sum_m3"] for output in outputs
                ),
                "volume_min_m3": min(
                    output["volume_min_m3"] for output in outputs
                ),
                "volume_max_m3": max(
                    output["volume_max_m3"] for output in outputs
                ),
                "all_outputs_dtype": "<f8",
                "all_outputs_one_dimensional": True,
                "all_values_strictly_positive_finite": True,
            },
            "cases": cases,
        }

    def _field_audit(
        self,
        case_id: str,
        name: str,
        components: int,
        units: str,
    ) -> dict[str, object]:
        count = self.case_counts[case_id]
        minimum = [-float(index + 1) for index in range(components)]
        maximum = [float(index + 2) for index in range(components)]
        return {
            "name": name,
            "association": "CellData",
            "vtk_type": "Float32",
            "number_of_components": components,
            "tuple_count": count,
            "scalar_count": count * components,
            "decoded_payload_bytes": count * components * 4,
            "payload_sha256": _sha256_bytes(
                f"{case_id}-{name}-payload".encode("ascii")
            ),
            "finite": True,
            "minimum_by_component": minimum,
            "maximum_by_component": maximum,
            "units": units,
            "raw_id_start": 0,
            "raw_id_stop": count,
        }

    def _metric_pass(
        self,
        case_id: str,
        field_audit: dict[str, object],
        chunk_cells: int,
    ) -> dict[str, object]:
        count = self.case_counts[case_id]
        volume_sum = self.weight_sums[case_id]
        uniform = {
            "absolute_error": 2.0 * count,
            "squared_error": 4.0 * count,
            "squared_truth": 4.0 * count,
            "entity_count": count,
            "total_weight": float(count),
        }
        physical = {
            "absolute_error": 2.0 * volume_sum,
            "squared_error": 4.0 * volume_sum,
            "squared_truth": 4.0 * volume_sum,
            "entity_count": count,
            "total_weight": volume_sum,
        }
        metrics = {
            weighting: {
                "relative_l2_percent": 100.0,
                "mae": sums["absolute_error"] / sums["total_weight"],
                "rmse": math.sqrt(
                    sums["squared_error"] / sums["total_weight"]
                ),
            }
            for weighting, sums in (
                ("uniform", uniform),
                ("physical", physical),
            )
        }
        return {
            "field_name": field_audit["name"],
            "chunk_entities": chunk_cells,
            "source_payload_sha256": field_audit["payload_sha256"],
            "source_payload_bytes": field_audit["decoded_payload_bytes"],
            "entity_count": count,
            "component_count": field_audit["number_of_components"],
            "metrics": metrics,
            "additive_sums": {"uniform": uniform, "physical": physical},
        }

    def _metric_fixture(
        self,
        case_id: str,
        field_audit: dict[str, object],
    ) -> dict[str, object]:
        return {
            "prediction_role": ZERO_PREDICTION_ROLE,
            "reference_partition": self._metric_pass(
                case_id, field_audit, REFERENCE_CHUNK_CELLS
            ),
            "comparison_partition": self._metric_pass(
                case_id, field_audit, COMPARISON_CHUNK_CELLS
            ),
            "invariance": {
                "same_source_payload_sha256": True,
                "same_complete_entity_coverage": True,
                "additive_sums": {
                    "uniform": _difference_rows(),
                    "physical": _difference_rows(),
                },
                "maximum_additive_relative_difference": 0.0,
                "maximum_metric_absolute_difference": 0.0,
            },
        }

    def _make_receipt(self, case_id: str) -> dict[str, object]:
        case = self._case_pin(case_id)
        count = self.case_counts[case_id]
        p_audit = self._field_audit(case_id, "pMeanTrim", 1, "m^2/s^2")
        u_audit = self._field_audit(case_id, "UMeanTrim", 3, "m/s")
        offsets = ((10, 20, 100, 110), (120, 130, 250, 260))
        arrays = [
            {
                "array_index": index,
                "piece_index": 0,
                "association": "CellData",
                "name": name,
                "vtk_type": "Float32",
                "number_of_components": components,
                "format": "binary",
                "opening_tag_start": positions[0],
                "encoded_start": positions[1],
                "encoded_end": positions[2],
                "closing_tag_end": positions[3],
            }
            for index, (name, components, positions) in enumerate(
                (
                    ("pMeanTrim", 1, offsets[0]),
                    ("UMeanTrim", 3, offsets[1]),
                )
            )
        ]
        physical_path = str(self.root / f"assembled-{case_id}.vtu")
        running_offset = 0
        segments = []
        for part in case["volume"]["parts"]:
            segments.append(
                {
                    "label": (
                        f"{case_id}:monolithic-segment:{part['part_index']}"
                    ),
                    "path": physical_path,
                    "file_offset": running_offset,
                    "size_bytes": part["size_bytes"],
                    "sha256": part["lfs_sha256"],
                }
            )
            running_offset += part["size_bytes"]
        weight = self._weight_output(case_id)
        return {
            "schema": CASE_AUDIT_SCHEMA,
            "status": "passed_candidate_evaluator_case_audit",
            "case_id": case_id,
            "public_source": {
                "repository_id": "synthetic/drivaerml",
                "immutable_revision": "a" * 40,
                "logical_path": case["volume"]["logical_path_after_assembly"],
                "logical_size_bytes": case["volume"]["total_size_bytes"],
                "multipart_part_count": case["volume"]["part_count"],
                "verified_monolithic_segments": segments,
            },
            "vtk": {
                "dataset_type": "UnstructuredGrid",
                "version": "1.0",
                "byte_order": "LittleEndian",
                "header_type": "UInt64",
                "compressor": None,
                "piece": {
                    "piece_index": 0,
                    "number_of_points": count // 2,
                    "number_of_cells": count,
                    "number_of_verts": 0,
                    "number_of_lines": 0,
                    "number_of_strips": 0,
                    "number_of_polys": 0,
                },
                "data_arrays_in_raw_xml_order": arrays,
            },
            "required_cell_data": {
                "pMeanTrim": p_audit,
                "UMeanTrim": u_audit,
            },
            "units": {
                "coordinates": "m",
                "pMeanTrim": "m^2/s^2",
                "UMeanTrim": "m/s",
            },
            "raw_cell_order": "zero-based VTK Piece CellData tuple order, unchanged",
            "coverage": {
                "expected_raw_id_interval": [0, count],
                "validation": (
                    "each metric pass finalized exact gap-free duplicate-free coverage"
                ),
            },
            "volume_weights": {
                "path": str(self.root / weight["file"]),
                "sha256": weight["sha256"],
                "dtype": "<f8",
                "cell_count": count,
                "sum_m3": weight["volume_sum_m3"],
                "minimum_m3": weight["volume_min_m3"],
                "maximum_m3": weight["volume_max_m3"],
                "role": "fixed_same_order_cell_volume_secondary_weights",
                "status": "audited",
            },
            "metrics": {
                "pMeanTrim": self._metric_fixture(case_id, p_audit),
                "UMeanTrim": self._metric_fixture(case_id, u_audit),
            },
            "chunk_invariance_tolerances": {
                "maximum_additive_relative_difference": (
                    MAX_ADDITIVE_RELATIVE_DIFFERENCE
                ),
                "maximum_metric_absolute_difference": (
                    MAX_METRIC_ABSOLUTE_DIFFERENCE
                ),
            },
            "runtime": {
                "python": "3.12.13",
                "numpy": "2.2.6",
                "segment_verification_seconds": 1.0,
                "xml_index_seconds": 2.0,
                "volume_weight_audit_seconds": 3.0,
                "field_audit_and_dual_metric_seconds": 4.0,
                "total_seconds": 10.0,
            },
        }


class DrivAerMLNativeVolumeAuditAggregateTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = NativeVolumeAuditFixture(self.root)

    def aggregate(self, receipt_paths: list[Path] | None = None):
        return aggregate_native_volume_audits(
            native_source_pin_path=self.fixture.pin_path,
            volume_weight_aggregate_path=self.fixture.weight_aggregate_path,
            receipt_paths=(
                self.fixture.receipt_paths
                if receipt_paths is None
                else receipt_paths
            ),
        )

    def receipt(self, position: int) -> dict[str, object]:
        return json.loads(
            self.fixture.receipt_paths[position].read_text(encoding="utf-8")
        )

    def rewrite(self, position: int, receipt: dict[str, object]) -> None:
        _write_json(self.fixture.receipt_paths[position], receipt)

    def test_complete_aggregate_is_deterministic_path_free_and_counts_parts(self) -> None:
        evidence = self.aggregate(list(reversed(self.fixture.receipt_paths)))
        self.assertEqual(evidence["schema"], AGGREGATE_SCHEMA)
        self.assertEqual([row["case_id"] for row in evidence["cases"]], list(CASE_IDS))
        self.assertEqual(evidence["totals"]["case_count"], 2)
        self.assertEqual(evidence["totals"]["two_part_case_count"], 1)
        self.assertEqual(evidence["totals"]["three_part_case_count"], 1)
        self.assertEqual(evidence["totals"]["verified_segment_count"], 5)
        self.assertEqual(
            evidence["totals"]["native_cell_count"],
            sum(self.fixture.case_counts.values()),
        )
        self.assertFalse(evidence["fixture_semantics"]["physics_null_baseline"])
        self.assertEqual(
            evidence["fixture_semantics"]["prediction_role"],
            ZERO_PREDICTION_ROLE,
        )
        serialized = json.dumps(evidence, sort_keys=True)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("/tmp/", serialized)

        first = self.root / "aggregate-first.json"
        second = self.root / "aggregate-second.json"
        write_evidence(first, evidence)
        write_evidence(second, self.aggregate())
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertNotIn(b"\n ", first.read_bytes())

    def test_equal_cell_primary_pilot_is_explicit_path_free_and_weight_ineligible(self) -> None:
        case_id = "run_1"
        count = self.fixture.case_counts[case_id]
        self.fixture.weight_sums[case_id] = float(count)
        receipt = self.fixture._make_receipt(case_id)
        receipt["volume_weights"] = {
            "role": "unit_weights_for_equal_native_cell_primary_pilot",
            "status": "physical_secondary_not_exercised",
        }
        _write_json(self.fixture.receipt_paths[0], receipt)

        evidence = aggregate_native_volume_primary_pilot(
            native_source_pin_path=self.fixture.pin_path,
            receipt_paths=[self.fixture.receipt_paths[0]],
            selected_case_ids=(case_id,),
        )
        self.assertEqual(evidence["schema"], PRIMARY_PILOT_AGGREGATE_SCHEMA)
        self.assertFalse(evidence["public_scoring_support_eligible"])
        self.assertFalse(evidence["scope"]["complete_native_source_pin_scope"])
        self.assertEqual(evidence["totals"]["native_cell_count"], count)
        self.assertEqual(evidence["totals"]["two_part_case_count"], 1)
        self.assertEqual(evidence["totals"]["three_part_case_count"], 0)
        self.assertFalse(
            evidence["fixture_semantics"]["physical_volume_secondary_exercised"]
        )
        serialized = json.dumps(evidence, sort_keys=True)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("/tmp/", serialized)

        receipt["volume_weights"]["status"] = "audited"
        _write_json(self.fixture.receipt_paths[0], receipt)
        with self.assertRaisesRegex(
            NativeVolumeAuditAggregateError,
            "equal-cell pilot weight declaration is not exact",
        ):
            aggregate_native_volume_primary_pilot(
                native_source_pin_path=self.fixture.pin_path,
                receipt_paths=[self.fixture.receipt_paths[0]],
                selected_case_ids=(case_id,),
            )

    def test_equal_cell_primary_all_case_audit_is_complete_but_weight_ineligible(self) -> None:
        for position, case_id in enumerate(CASE_IDS):
            count = self.fixture.case_counts[case_id]
            self.fixture.weight_sums[case_id] = float(count)
            receipt = self.fixture._make_receipt(case_id)
            receipt["volume_weights"] = {
                "role": "unit_weights_for_equal_native_cell_primary_pilot",
                "status": "physical_secondary_not_exercised",
            }
            self.rewrite(position, receipt)

        evidence = aggregate_native_volume_primary_all_case_audit(
            native_source_pin_path=self.fixture.pin_path,
            receipt_paths=list(reversed(self.fixture.receipt_paths)),
        )
        self.assertEqual(evidence["schema"], PRIMARY_ALL_CASE_AUDIT_SCHEMA)
        self.assertEqual(
            evidence["status"], "passed_all_case_equal_cell_primary_audit"
        )
        self.assertTrue(evidence["scope"]["complete_native_source_pin_scope"])
        self.assertFalse(evidence["public_scoring_support_eligible"])
        self.assertEqual(evidence["totals"]["case_count"], len(CASE_IDS))
        self.assertFalse(
            evidence["fixture_semantics"]["physical_volume_secondary_exercised"]
        )
        self.assertIn("not claimed", evidence["audit_warning"])

    def test_missing_duplicate_and_extra_case_receipts_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            NativeVolumeAuditAggregateError, "missing=.*run_44"
        ):
            self.aggregate([self.fixture.receipt_paths[0]])
        with self.assertRaisesRegex(NativeVolumeAuditAggregateError, "duplicate"):
            self.aggregate(
                [
                    self.fixture.receipt_paths[0],
                    self.fixture.receipt_paths[0],
                    self.fixture.receipt_paths[1],
                ]
            )
        receipt = self.receipt(1)
        receipt["case_id"] = "run_999"
        self.rewrite(1, receipt)
        with self.assertRaisesRegex(NativeVolumeAuditAggregateError, "unexpected"):
            self.aggregate()

    def test_explicit_selected_subset_requires_matching_non_public_weight_pilot(self) -> None:
        partial = copy.deepcopy(self.fixture.weight_aggregate)
        partial["mode"] = "partial_pilot"
        partial["status"] = "incomplete_non_public_pilot"
        partial["complete"] = False
        partial["public_evidence_eligible"] = False
        partial["case_count"] = 1
        partial["omitted_official_case_count"] = 1
        partial["pilot_warning"] = "incomplete subset; not public"
        partial["cases"] = partial["cases"][:1]
        output = partial["cases"][0]["output"]
        case = self.fixture._case_pin("run_1")
        partial["aggregate"].update(
            {
                "cell_count": output["cell_count"],
                "source_vtu_size_bytes": case["volume"]["total_size_bytes"],
                "output_size_bytes": output["size_bytes"],
                "volume_sum_m3": output["volume_sum_m3"],
                "volume_min_m3": output["volume_min_m3"],
                "volume_max_m3": output["volume_max_m3"],
            }
        )
        _write_json(self.fixture.weight_aggregate_path, partial)
        evidence = aggregate_native_volume_audits(
            native_source_pin_path=self.fixture.pin_path,
            volume_weight_aggregate_path=self.fixture.weight_aggregate_path,
            receipt_paths=[self.fixture.receipt_paths[0]],
            selected_case_ids=("run_1",),
        )
        self.assertEqual(evidence["scope"]["selected_case_count"], 1)
        self.assertFalse(evidence["scope"]["complete_native_source_pin_scope"])
        self.assertEqual(evidence["totals"]["two_part_case_count"], 1)
        self.assertEqual(evidence["totals"]["three_part_case_count"], 0)

    def test_source_field_coverage_and_weight_tampering_are_rejected(self) -> None:
        mutations = (
            (
                "segment hash",
                lambda value: value["public_source"][
                    "verified_monolithic_segments"
                ][0].update(sha256="f" * 64),
                "segment 0 is not pinned",
            ),
            (
                "association",
                lambda value: value["required_cell_data"]["pMeanTrim"].update(
                    association="PointData"
                ),
                "association/type/components",
            ),
            (
                "finite",
                lambda value: value["required_cell_data"]["UMeanTrim"].update(
                    finite=False
                ),
                "association/type/components",
            ),
            (
                "coverage",
                lambda value: value["coverage"].update(
                    expected_raw_id_interval=[1, self.fixture.case_counts["run_1"]]
                ),
                "coverage evidence is incomplete",
            ),
            (
                "weight hash",
                lambda value: value["volume_weights"].update(sha256="e" * 64),
                "differs from v2 weight evidence",
            ),
        )
        for label, mutate, message in mutations:
            with self.subTest(label=label):
                receipt = self.fixture._make_receipt("run_1")
                mutate(receipt)
                self.rewrite(0, receipt)
                with self.assertRaisesRegex(NativeVolumeAuditAggregateError, message):
                    self.aggregate()

    def test_partition_role_and_invariance_thresholds_are_strict(self) -> None:
        receipt = self.receipt(0)
        receipt["metrics"]["pMeanTrim"]["prediction_role"] = (
            "physics_null_baseline"
        )
        self.rewrite(0, receipt)
        with self.assertRaisesRegex(
            NativeVolumeAuditAggregateError, "invariance fixture"
        ):
            self.aggregate()

        receipt = self.fixture._make_receipt("run_1")
        receipt["metrics"]["pMeanTrim"]["comparison_partition"][
            "chunk_entities"
        ] = REFERENCE_CHUNK_CELLS
        self.rewrite(0, receipt)
        with self.assertRaisesRegex(
            NativeVolumeAuditAggregateError, "partition binding"
        ):
            self.aggregate()

        receipt = self.fixture._make_receipt("run_1")
        receipt["chunk_invariance_tolerances"][
            "maximum_additive_relative_difference"
        ] = 1.0e-6
        self.rewrite(0, receipt)
        with self.assertRaisesRegex(
            NativeVolumeAuditAggregateError, "thresholds are not frozen"
        ):
            self.aggregate()

    def test_weight_aggregate_cross_binding_and_absolute_output_paths_reject(self) -> None:
        weight_evidence = copy.deepcopy(self.fixture.weight_aggregate)
        weight_evidence["cases"][0]["output"]["sha256"] = "d" * 64
        _write_json(self.fixture.weight_aggregate_path, weight_evidence)
        with self.assertRaisesRegex(
            NativeVolumeAuditAggregateError, "audited weight sha256 differs"
        ):
            self.aggregate()

        _write_json(
            self.fixture.weight_aggregate_path,
            self.fixture._make_weight_aggregate(),
        )
        evidence = self.aggregate()
        evidence["cases"][0]["source"]["logical_path"] = "/private/source.vtu"
        with self.assertRaisesRegex(
            NativeVolumeAuditAggregateError, "absolute path"
        ):
            write_evidence(self.root / "must-not-write.json", evidence)


if __name__ == "__main__":
    unittest.main()
