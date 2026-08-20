from __future__ import annotations

import copy
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from scripts.aggregate_drivaerml_volume_weights import (
    DEFAULT_COPY_CHUNK_SIZE,
    DEFAULT_SOURCE_VERIFICATION_CHUNK_BYTES,
    PINNED_ALGORITHM,
    PINNED_ALGORITHM_SHA256,
    PINNED_ENVIRONMENT_BINDING,
    PINNED_VERSIONS,
    RECEIPT_SCHEMA,
    RECEIPT_SCHEMA_VERSION,
    VolumeWeightAggregateError,
    aggregate_volume_weight_receipts,
    sha256_file,
    write_evidence,
)
from reference.drivaerml.volume_weights import implementation_file_records


CASE_IDS = ("run_1", "run_44")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


class DrivAerMLVolumeWeightAggregateTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pin = self._make_pin()
        self.pin_path = self.root / "native-source-pin.json"
        _write_json(self.pin_path, self.pin)
        self.implementation_binding = {
            "git_revision": "c" * 40,
            "worktree_clean": True,
            "files": implementation_file_records(),
        }
        committed_patcher = mock.patch(
            "scripts.aggregate_drivaerml_volume_weights."
            "_committed_implementation_file_records",
            return_value=copy.deepcopy(self.implementation_binding["files"]),
        )
        committed_patcher.start()
        self.addCleanup(committed_patcher.stop)
        self.receipt_paths: list[Path] = []
        for position, case_id in enumerate(CASE_IDS):
            path = self.root / f"{case_id}-volume-weight-receipt.json"
            _write_json(path, self._make_receipt(case_id, position))
            self.receipt_paths.append(path)

    def _make_pin(self) -> dict[str, object]:
        cases = []
        for position, case_id in enumerate(CASE_IDS):
            run_number = int(case_id.removeprefix("run_"))
            part_sizes = [1000 + position, 700 + position]
            if case_id == "run_44":
                part_sizes.append(300)
            logical_path = f"{case_id}/volume_{run_number}.vtu"
            parts = [
                {
                    "part_index": part_index,
                    "path": f"{logical_path}.{part_index:02d}.part",
                    "size_bytes": size,
                    "lfs_sha256": str(position + part_index + 1) * 64,
                }
                for part_index, size in enumerate(part_sizes)
            ]
            cases.append(
                {
                    "case_id": case_id,
                    "run_number": run_number,
                    "volume": {
                        "assembly": (
                            "byte concatenation of parts in listed order, "
                            "with no delimiter or transformation"
                        ),
                        "identity_contract": (
                            "ordered (path,size_bytes,lfs_sha256) tuples; "
                            "no assembled-file SHA-256 is asserted"
                        ),
                        "logical_path_after_assembly": logical_path,
                        "part_count": len(parts),
                        "parts": parts,
                        "total_size_bytes": sum(part_sizes),
                    },
                }
            )
        return {
            "schema": "drivaerml-fluidsbench-public-native-source-pin-v1",
            "schema_version": 1,
            "repository": {
                "provider": "Hugging Face Hub",
                "repo_id": "neashton/drivaerml",
                "repo_type": "dataset",
                "revision": "7a5c0948ce27be709b1116a3a190f806e7a8f79f",
            },
            "case_scope": {"case_count": len(CASE_IDS)},
            "cases": cases,
        }

    def _make_receipt(self, case_id: str, position: int) -> dict[str, object]:
        run_number = int(case_id.removeprefix("run_"))
        pinned = self.pin["cases"][position]  # type: ignore[index]
        cell_count = 10 + 2 * position
        interior = (4.0 + position) / (cell_count - 2)
        values = np.asarray(
            [0.1, *([interior] * (cell_count - 2)), 0.9], dtype="<f8"
        )
        cell_types = bytes([10] * (cell_count - 1) + [42])
        total = math.fsum([float(np.sum(values, dtype=np.float64))])
        output_path = self.root / f"volume_cell_volume_{run_number}.npy"
        np.save(output_path, values, allow_pickle=False)
        return {
            "schema": RECEIPT_SCHEMA,
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "status": "candidate_exact_native_source_verified_before_vtk",
            "case_id": case_id,
            "implementation_binding": copy.deepcopy(self.implementation_binding),
            "environment_binding": copy.deepcopy(PINNED_ENVIRONMENT_BINDING),
            "native_source_binding": {
                "pin": {
                    "sha256": sha256_file(self.pin_path),
                    "repository_id": "neashton/drivaerml",
                    "repository_revision": (
                        "7a5c0948ce27be709b1116a3a190f806e7a8f79f"
                    ),
                },
                "case_id": case_id,
                "logical_volume": {
                    "path": pinned["volume"][  # type: ignore[index]
                        "logical_path_after_assembly"
                    ],
                    "size_bytes": pinned["volume"][  # type: ignore[index]
                        "total_size_bytes"
                    ],
                    "ordered_verified_segments": [
                        {
                            "part_index": part["part_index"],
                            "size_bytes": part["size_bytes"],
                            "sha256": part["lfs_sha256"],
                        }
                        for part in pinned["volume"]["parts"]  # type: ignore[index]
                    ],
                },
                "verification": {
                    "method": "exact_ordered_segment_size_and_sha256",
                    "timing": "completed_before_vtk_geometry_reader",
                    "vtk_input": "retained_verified_file_descriptor",
                    "post_vtk_fstat": "unchanged",
                },
            },
            "output": {
                "file": f"volume_cell_volume_{run_number}.npy",
                "dtype": "<f8",
                "shape": [cell_count],
                "size_bytes": 128 + 8 * cell_count,
                "sha256": sha256_file(output_path),
                "cell_count": cell_count,
                "volume_sum_m3": total,
                "volume_min_m3": 0.1,
                "volume_max_m3": 0.9,
                "per_vtk_cell_type": [
                    {
                        "vtk_cell_type_id": 10,
                        "vtk_cell_type_name": "vtkTetra",
                        "cell_count": cell_count - 1,
                        "volume_sum_m3": total - 0.9,
                        "volume_min_m3": 0.1,
                        "volume_max_m3": interior,
                    },
                    {
                        "vtk_cell_type_id": 42,
                        "vtk_cell_type_name": "vtkPolyhedron",
                        "cell_count": 1,
                        "volume_sum_m3": 0.9,
                        "volume_min_m3": 0.9,
                        "volume_max_m3": 0.9,
                    },
                ],
            },
            "native_cell_types": {
                "dtype": "uint8",
                "shape": [cell_count],
                "order": "zero_based_raw_vtk_cell_order",
                "payload_sha256": hashlib.sha256(cell_types).hexdigest(),
                "histogram": [
                    {
                        "vtk_cell_type_id": 10,
                        "vtk_cell_type_name": "vtkTetra",
                        "cell_count": cell_count - 1,
                    },
                    {
                        "vtk_cell_type_id": 42,
                        "vtk_cell_type_name": "vtkPolyhedron",
                        "cell_count": 1,
                    },
                ],
            },
            "versions": dict(PINNED_VERSIONS),
            "algorithm": PINNED_ALGORITHM,
            "execution": {
                "copy_chunk_size": DEFAULT_COPY_CHUNK_SIZE,
                "source_verification_chunk_bytes": (
                    DEFAULT_SOURCE_VERIFICATION_CHUNK_BYTES
                ),
            },
            "reader_audit": {
                "disabled_point_array_count": 1,
                "disabled_point_arrays": ["pointDebug"],
                "disabled_cell_array_count": 3,
                "disabled_cell_arrays": ["pMeanTrim", "UMeanTrim", "cellDebug"],
            },
        }

    def _aggregate(
        self,
        receipt_paths: list[Path] | None = None,
        *,
        pilot_case_ids: tuple[str, ...] | None = None,
    ) -> dict[str, object]:
        return aggregate_volume_weight_receipts(
            native_source_pin_path=self.pin_path,
            receipt_paths=self.receipt_paths if receipt_paths is None else receipt_paths,
            pilot_case_ids=pilot_case_ids,
            official_case_ids=CASE_IDS,
            expected_pin_sha256=None,
        )

    def _receipt(self, position: int) -> dict[str, object]:
        return json.loads(self.receipt_paths[position].read_text(encoding="utf-8"))

    def _rewrite(self, position: int, receipt: dict[str, object]) -> None:
        _write_json(self.receipt_paths[position], receipt)

    def test_complete_output_is_deterministic_compact_and_path_free(self) -> None:
        evidence = self._aggregate(list(reversed(self.receipt_paths)))
        self.assertEqual(evidence["mode"], "complete")
        self.assertTrue(evidence["complete"])
        self.assertTrue(evidence["public_evidence_eligible"])
        self.assertEqual(evidence["case_count"], 2)
        self.assertEqual(evidence["omitted_official_case_count"], 0)
        self.assertEqual(
            [row["case_id"] for row in evidence["cases"]], list(CASE_IDS)
        )
        self.assertEqual(evidence["aggregate"]["cell_count"], 22)
        self.assertEqual(evidence["aggregate"]["output_size_bytes"], 432)
        self.assertEqual(evidence["aggregate"]["volume_sum_m3"], 11.0)
        self.assertEqual(
            [
                (row["vtk_cell_type_id"], row["cell_count"], row["case_count"])
                for row in evidence["aggregate"]["per_vtk_cell_type"]
            ],
            [(10, 20, 2), (42, 2, 2)],
        )
        expected_type_manifest = [
            {
                "case_id": case_id,
                "payload_sha256": self._receipt(position)["native_cell_types"][
                    "payload_sha256"
                ],
            }
            for position, case_id in enumerate(CASE_IDS)
        ]
        self.assertEqual(
            evidence["aggregate"][
                "native_cell_type_payload_manifest_sha256"
            ],
            hashlib.sha256(
                json.dumps(
                    expected_type_manifest,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        )
        self.assertEqual(evidence["algorithm"]["sha256"], PINNED_ALGORITHM_SHA256)
        self.assertEqual(
            evidence["implementation_binding"], self.implementation_binding
        )
        self.assertEqual(
            evidence["environment_binding"], PINNED_ENVIRONMENT_BINDING
        )
        self.assertEqual(
            evidence["source"]["native_source_pin"]["sha256"],
            sha256_file(self.pin_path),
        )
        for position, row in enumerate(evidence["cases"]):
            self.assertEqual(
                row["receipt_sha256"], sha256_file(self.receipt_paths[position])
            )

        serialized = json.dumps(evidence, sort_keys=True)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("/tmp/", serialized)
        first = self.root / "first.json"
        second = self.root / "second.json"
        write_evidence(first, evidence)
        write_evidence(second, self._aggregate())
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertNotIn(b"\n ", first.read_bytes())

    def test_partial_pilot_requires_explicit_cases_and_is_non_public(self) -> None:
        with self.assertRaisesRegex(VolumeWeightAggregateError, "missing=.*run_44"):
            self._aggregate([self.receipt_paths[0]])

        evidence = self._aggregate(
            [self.receipt_paths[0]], pilot_case_ids=("run_1",)
        )
        self.assertEqual(evidence["mode"], "partial_pilot")
        self.assertEqual(evidence["status"], "incomplete_non_public_pilot")
        self.assertFalse(evidence["complete"])
        self.assertFalse(evidence["public_evidence_eligible"])
        self.assertEqual(evidence["omitted_official_case_count"], 1)
        self.assertIn("not a public", evidence["pilot_warning"])

        with self.assertRaisesRegex(VolumeWeightAggregateError, "strict subset"):
            self._aggregate(self.receipt_paths, pilot_case_ids=CASE_IDS)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "official pinned"):
            self._aggregate(
                [self.receipt_paths[0]], pilot_case_ids=("run_999",)
            )

    def test_missing_duplicate_and_unexpected_receipts_fail_closed(self) -> None:
        with self.assertRaisesRegex(VolumeWeightAggregateError, "duplicate"):
            self._aggregate([self.receipt_paths[0], self.receipt_paths[0]])

        receipt = self._receipt(1)
        receipt["case_id"] = "run_999"
        self._rewrite(1, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "unexpected"):
            self._aggregate()

    def test_source_pin_logical_identity_segments_and_versions_are_exact(self) -> None:
        receipt = self._receipt(0)
        receipt["native_source_binding"]["logical_volume"]["path"] = (
            "run_1/volume_2.vtu"
        )
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "path is not pinned"):
            self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        receipt["native_source_binding"]["logical_volume"]["size_bytes"] += 1
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "size is not pinned"):
            self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        receipt["native_source_binding"]["logical_volume"][
            "ordered_verified_segments"
        ][0]["sha256"] = "f" * 64
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "segment 0 is not pinned"):
            self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        receipt["native_source_binding"]["pin"]["sha256"] = "e" * 64
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "different native-source pin"):
            self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        receipt["versions"]["numpy"] = "2.5.2"
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "versions are not pinned"):
            self._aggregate()

    def test_legacy_size_only_receipt_is_not_silently_accepted(self) -> None:
        receipt = self._make_receipt("run_1", 0)
        receipt.pop("native_source_binding")
        receipt["source_vtu"] = {
            "file": "volume_1.vtu",
            "size_bytes": self.pin["cases"][0]["volume"]["total_size_bytes"],
        }
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(
            VolumeWeightAggregateError, "native_source_binding"
        ):
            self._aggregate()

    def test_algorithm_execution_and_reader_audit_must_be_exact(self) -> None:
        receipt = self._receipt(0)
        receipt["algorithm"]["cell_size_filter"]["compute_area"] = True
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "algorithm settings"):
            self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        receipt["execution"]["copy_chunk_size"] = 999
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "copy_chunk_size"):
            self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        receipt["execution"]["source_verification_chunk_bytes"] = 999
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(
            VolumeWeightAggregateError, "source_verification_chunk_bytes"
        ):
            self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        receipt["reader_audit"]["disabled_cell_arrays"] = ["pMeanTrim"]
        receipt["reader_audit"]["disabled_cell_array_count"] = 1
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "required CellData"):
            self._aggregate()

    def test_implementation_binding_is_exact_current_clean_and_identical(self) -> None:
        mutations = (
            ("extra", True, "keys differ from schema"),
            ("git_revision", "unresolved", "resolved 40-hex"),
            ("worktree_clean", False, "recorded clean"),
        )
        for key, value, message in mutations:
            with self.subTest(key=key):
                receipt = self._make_receipt("run_1", 0)
                receipt["implementation_binding"][key] = value
                self._rewrite(0, receipt)
                with self.assertRaisesRegex(VolumeWeightAggregateError, message):
                    self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        receipt["implementation_binding"]["files"][0]["sha256"] = "f" * 64
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(
            VolumeWeightAggregateError, "differs from the current frozen"
        ):
            self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        receipt["implementation_binding"]["files"][0]["path"] = (
            "reference/drivaerml/not-the-source.py"
        )
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(
            VolumeWeightAggregateError, "differs from the current frozen"
        ):
            self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        self._rewrite(0, receipt)
        second = self._make_receipt("run_44", 1)
        second["implementation_binding"] = {
            **self.implementation_binding,
            "git_revision": "d" * 40,
        }
        self._rewrite(1, second)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "identical"):
            self._aggregate()

    def test_environment_binding_is_exact(self) -> None:
        receipt = self._make_receipt("run_1", 0)
        receipt["environment_binding"]["vtk_wheel"]["sha256"] = "f" * 64
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "environment binding"):
            self._aggregate()

    def test_recorded_revision_blobs_must_match_receipt_hashes(self) -> None:
        mismatched = copy.deepcopy(self.implementation_binding["files"])
        mismatched[0]["sha256"] = "f" * 64
        with mock.patch(
            "scripts.aggregate_drivaerml_volume_weights."
            "_committed_implementation_file_records",
            return_value=mismatched,
        ), self.assertRaisesRegex(
            VolumeWeightAggregateError, "differ from git show"
        ):
            self._aggregate()

    def test_output_dtype_shape_size_hash_and_positive_statistics_are_strict(self) -> None:
        mutations = (
            ("dtype", ">f8", "dtype must be <f8"),
            ("shape", [9], "shape/count"),
            ("size_bytes", 999, "NPY size/count"),
            ("sha256", "not-a-hash", "lowercase SHA-256"),
            ("volume_min_m3", 0.0, "strictly positive"),
            ("volume_max_m3", float("inf"), "finite"),
            ("volume_sum_m3", 100.0, "sum is inconsistent"),
        )
        for key, value, message in mutations:
            with self.subTest(key=key):
                receipt = self._make_receipt("run_1", 0)
                receipt["output"][key] = value
                self._rewrite(0, receipt)
                with self.assertRaisesRegex(VolumeWeightAggregateError, message):
                    self._aggregate()

    def test_cell_type_histogram_hash_and_per_type_statistics_are_strict(self) -> None:
        mutations = (
            (
                lambda receipt: receipt["native_cell_types"].__setitem__(
                    "payload_sha256", "not-a-hash"
                ),
                "cell-type payload SHA-256.*lowercase SHA-256",
            ),
            (
                lambda receipt: receipt["native_cell_types"]["histogram"][0].__setitem__(
                    "vtk_cell_type_id", 11
                ),
                "unsupported VTK cell type 11",
            ),
            (
                lambda receipt: receipt["native_cell_types"]["histogram"][0].__setitem__(
                    "cell_count", 1
                ),
                "histogram/count are inconsistent",
            ),
            (
                lambda receipt: receipt["output"]["per_vtk_cell_type"][0].__setitem__(
                    "cell_count", 1
                ),
                "differs from input histogram",
            ),
            (
                lambda receipt: receipt["output"]["per_vtk_cell_type"][0].__setitem__(
                    "volume_sum_m3", 99.0
                ),
                "per-type volume sum is inconsistent",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                receipt = self._make_receipt("run_1", 0)
                mutate(receipt)
                self._rewrite(0, receipt)
                with self.assertRaisesRegex(VolumeWeightAggregateError, message):
                    self._aggregate()

    def test_actual_npy_bytes_and_statistics_are_replayed(self) -> None:
        output = self.root / "volume_cell_volume_1.npy"
        with output.open("r+b") as stream:
            stream.seek(-1, 2)
            final = stream.read(1)
            stream.seek(-1, 2)
            stream.write(bytes([final[0] ^ 1]))
        with self.assertRaisesRegex(VolumeWeightAggregateError, "bytes differ"):
            self._aggregate()

        receipt = self._make_receipt("run_1", 0)
        values = np.load(output, allow_pickle=False)
        values[1] += 0.01
        np.save(output, values, allow_pickle=False)
        receipt["output"]["sha256"] = sha256_file(output)
        self._rewrite(0, receipt)
        with self.assertRaisesRegex(VolumeWeightAggregateError, "statistics differ"):
            self._aggregate()

    def test_production_default_rejects_nonofficial_pin(self) -> None:
        with self.assertRaisesRegex(
            VolumeWeightAggregateError, "native source pin SHA-256 mismatch"
        ):
            aggregate_volume_weight_receipts(
                native_source_pin_path=self.pin_path,
                receipt_paths=self.receipt_paths,
            )


if __name__ == "__main__":
    unittest.main()
