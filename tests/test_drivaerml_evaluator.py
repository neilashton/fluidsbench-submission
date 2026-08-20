from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np

from reference.drivaerml.evaluator import (
    CANDIDATE_STATUS,
    DrivAerCandidateEvaluatorError,
    NativeSourceContract,
    SOURCE_BOUND_VOLUME_WEIGHT_STATUS,
    _evaluate_surface_chunks,
    audit_fixed_volume_weight_file,
    audit_source_bound_volume_weight_file,
    evaluate_candidate_case,
    write_candidate_case_evidence,
)
from reference.drivaerml.native_surface import (
    NativeSurface,
    audit_fixed_surface_area_file,
)
from reference.drivaerml.prediction_chunks import (
    CANDIDATE_ARTIFACT_ROLE,
    CANDIDATE_FORMAT,
    load_prediction_chunk_manifest,
)
from reference.drivaerml.source import (
    index_inline_binary_vtk_xml,
    load_native_source_pin,
    open_verified_multipart,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(8192):
            digest.update(block)
    return digest.hexdigest()


def _encoded(payload: bytes) -> bytes:
    return base64.b64encode(struct.pack("<Q", len(payload)) + payload)


def _volume_document(
    pressure: np.ndarray,
    velocity: np.ndarray,
) -> bytes:
    return b"".join(
        [
            b'<VTKFile type="UnstructuredGrid" version="0.1" ',
            b'byte_order="LittleEndian" header_type="UInt64">',
            b'<UnstructuredGrid><Piece NumberOfPoints="1" NumberOfCells="',
            str(len(pressure)).encode("ascii"),
            b'"><CellData>',
            b'<DataArray type="Float32" Name="pMeanTrim" format="binary">',
            _encoded(np.asarray(pressure, dtype="<f4").tobytes()),
            b'</DataArray>',
            b'<DataArray type="Float32" Name="UMeanTrim" ',
            b'NumberOfComponents="3" format="binary">',
            _encoded(np.asarray(velocity, dtype="<f4").tobytes()),
            b'</DataArray></CellData></Piece></UnstructuredGrid></VTKFile>',
        ]
    )


def _write_prediction_manifest(
    root: Path,
    *,
    case_id: str,
    support_id: str,
    raw_partitions: tuple[int, ...],
    fields: dict[str, np.ndarray],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    chunks: list[dict[str, object]] = []
    start = 0
    for chunk_index, row_count in enumerate(raw_partitions):
        stop = start + row_count
        relative = Path("chunks") / f"chunk-{chunk_index:05d}.npz"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {
            "raw_cell_id": np.arange(start, stop, dtype=np.int64),
            **{name: value[start:stop] for name, value in fields.items()},
        }
        np.savez(path, **arrays)
        chunks.append(
            {
                "chunk_index": chunk_index,
                "file": relative.as_posix(),
                "sha256": _sha256_file(path),
                "row_count": row_count,
                "raw_cell_id_start": start,
                "raw_cell_id_stop": stop,
            }
        )
        start = stop
    field_components = {
        name: 1 if value.ndim == 1 else int(value.shape[1])
        for name, value in fields.items()
    }
    document = {
        "format": CANDIDATE_FORMAT,
        "format_version": 1,
        "artifact_role": CANDIDATE_ARTIFACT_ROLE,
        "case_id": case_id,
        "support_id": support_id,
        "association": "CellData",
        "total_row_count": start,
        "field_components": field_components,
        "chunks": chunks,
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


class SyntheticCase:
    entity_count = 5

    def __init__(self, root: Path) -> None:
        self.root = root
        run_root = root / "run_1"
        run_root.mkdir(parents=True)

        boundary_path = run_root / "boundary_1.vtp"
        boundary_path.write_bytes(b"synthetic boundary identity for evaluator tests")
        boundary_sha = _sha256_file(boundary_path)

        points: list[list[float]] = []
        connectivity: list[int] = []
        offsets = [0]
        areas = []
        for raw_id in range(self.entity_count):
            base = 1.0 + 0.2 * raw_id
            first = len(points)
            points.extend(
                [
                    [3.0 * raw_id, 0.0, 0.0],
                    [3.0 * raw_id + base, 0.0, 0.0],
                    [3.0 * raw_id, 1.0, 0.0],
                ]
            )
            connectivity.extend([first, first + 1, first + 2])
            offsets.append(len(connectivity))
            areas.append(0.5 * base)
        surface_pressure = np.asarray([2.0, 2.5, 3.0, 3.5, 4.0], dtype=np.float32)
        surface_shear = np.column_stack(
            (
                np.linspace(0.1, 0.5, self.entity_count),
                np.linspace(-0.2, 0.2, self.entity_count),
                np.linspace(0.3, 0.7, self.entity_count),
            )
        ).astype(np.float32)
        self.surface = NativeSurface(
            vtk_owner=None,
            source_path=boundary_path.resolve(),
            boundary_sha256=boundary_sha,
            points_m=np.asarray(points, dtype=np.float64),
            connectivity=np.asarray(connectivity, dtype=np.int64),
            offsets=np.asarray(offsets, dtype=np.int64),
            pressure_m2_per_s2=surface_pressure,
            wall_shear_m2_per_s2=surface_shear,
            available_point_arrays=(),
            available_cell_arrays=("pMeanTrim", "wallShearStressMeanTrim"),
            vtk_version="synthetic-no-vtk",
        )
        area_path = run_root / "boundary_cell_area_1.npy"
        np.save(area_path, np.asarray(areas, dtype="<f4"), allow_pickle=False)
        area_sha = _sha256_file(area_path)

        self.volume_pressure = np.asarray(
            [1.0, -1.5, 2.25, 3.5, -0.75], dtype=np.float32
        )
        self.volume_velocity = np.column_stack(
            (
                np.linspace(10.0, 14.0, self.entity_count),
                np.linspace(-1.0, 1.0, self.entity_count),
                np.linspace(0.5, 2.5, self.entity_count),
            )
        ).astype(np.float32)
        volume = _volume_document(self.volume_pressure, self.volume_velocity)
        split = len(volume) // 2 + 7
        parts = (volume[:split], volume[split:])
        part_records = []
        for part_index, payload in enumerate(parts):
            part_path = run_root / f"volume_1.vtu.{part_index:02d}.part"
            part_path.write_bytes(payload)
            part_records.append(
                {
                    "part_index": part_index,
                    "path": f"run_1/{part_path.name}",
                    "size_bytes": len(payload),
                    "lfs_sha256": _sha256_bytes(payload),
                }
            )

        pin_document = {
            "schema": "drivaerml-fluidsbench-public-native-source-pin-v1",
            "schema_version": 1,
            "repository": {
                "provider": "Hugging Face Hub",
                "repo_id": "neashton/drivaerml",
                "repo_type": "dataset",
                "revision": "7a5c0948ce27be709b1116a3a190f806e7a8f79f",
            },
            "case_scope": {
                "case_count": 1,
                "run_number_min": 1,
                "run_number_max": 1,
                "unavailable_or_held_back_run_numbers": [],
            },
            "cases": [
                {
                    "case_id": "run_1",
                    "run_number": 1,
                    "boundary": {
                        "path": "run_1/boundary_1.vtp",
                        "size_bytes": boundary_path.stat().st_size,
                        "lfs_sha256": boundary_sha,
                    },
                    "surface_cell_area": {
                        "path": "run_1/boundary_cell_area_1.npy",
                        "size_bytes": area_path.stat().st_size,
                        "lfs_sha256": area_sha,
                        "dtype": "<f4",
                        "element_count": self.entity_count,
                        "source_boundary_sha256": boundary_sha,
                    },
                    "volume": {
                        "assembly": (
                            "byte concatenation of parts in listed order, with no "
                            "delimiter or transformation"
                        ),
                        "identity_contract": (
                            "ordered (path,size_bytes,lfs_sha256) tuples; no "
                            "assembled-file SHA-256 is asserted"
                        ),
                        "logical_path_after_assembly": "run_1/volume_1.vtu",
                        "part_count": 2,
                        "parts": part_records,
                        "total_size_bytes": len(volume),
                    },
                }
            ],
            "totals": {
                "boundary_file_count": 1,
                "boundary_bytes": boundary_path.stat().st_size,
                "surface_cell_area_file_count": 1,
                "surface_cell_area_bytes": area_path.stat().st_size,
                "logical_volume_count": 1,
                "volume_part_file_count": 2,
                "reconstructed_volume_bytes": len(volume),
            },
        }
        pin_path = root / "native-source-pin.json"
        pin_path.write_text(json.dumps(pin_document), encoding="utf-8")
        self.pin = load_native_source_pin(pin_path)
        self.source_contract = NativeSourceContract(
            pin_sha256=_sha256_file(pin_path),
            repository_id="neashton/drivaerml",
            repository_revision="7a5c0948ce27be709b1116a3a190f806e7a8f79f",
            volume_weight_aggregate_sha256="c" * 64,
        )
        self.case = self.pin.case("run_1")
        self.resolved = self.pin.resolve("run_1", root)
        self.surface_areas = audit_fixed_surface_area_file(
            self.surface,
            area_path,
            expected_area_sha256=area_sha,
            source_boundary_sha256=boundary_sha,
        )

        volume_weight_path = root / "volume_cell_volume_1.npy"
        np.save(
            volume_weight_path,
            np.asarray([0.4, 0.7, 1.1, 1.6, 2.3], dtype="<f8"),
            allow_pickle=False,
        )
        self.unbound_volume_weights = audit_fixed_volume_weight_file(
            self.case,
            volume_weight_path,
            expected_sha256=_sha256_file(volume_weight_path),
            expected_entity_count=self.entity_count,
        )
        self.volume_weight_path = volume_weight_path
        native_cell_types = {
            "dtype": "uint8",
            "shape": [self.entity_count],
            "order": "zero_based_raw_vtk_cell_order",
            "payload_sha256": _sha256_bytes(bytes([10]) * self.entity_count),
            "histogram": [
                {
                    "vtk_cell_type_id": 10,
                    "vtk_cell_type_name": "vtkTetra",
                    "cell_count": self.entity_count,
                }
            ],
        }
        per_vtk_cell_type = (
            {
                "vtk_cell_type_id": 10,
                "vtk_cell_type_name": "vtkTetra",
                "cell_count": self.entity_count,
                "volume_sum_m3": self.unbound_volume_weights.volume_sum_m3,
                "volume_min_m3": self.unbound_volume_weights.volume_min_m3,
                "volume_max_m3": self.unbound_volume_weights.volume_max_m3,
            },
        )
        type_manifest_sha256 = _sha256_bytes(
            json.dumps(
                [
                    {
                        "case_id": "run_1",
                        "payload_sha256": native_cell_types["payload_sha256"],
                    }
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        self.volume_weights = replace(
            self.unbound_volume_weights,
            binding_status=SOURCE_BOUND_VOLUME_WEIGHT_STATUS,
            native_source_pin_sha256=self.source_contract.pin_sha256,
            receipt_sha256="b" * 64,
            aggregate_sha256="c" * 64,
            aggregate_complete=True,
            algorithm_sha256="d" * 64,
            native_cell_types=native_cell_types,
            per_vtk_cell_type=per_vtk_cell_type,
            aggregate_native_cell_type_payload_manifest_sha256=(
                type_manifest_sha256
            ),
            aggregate_per_vtk_cell_type=(
                {**per_vtk_cell_type[0], "case_count": 1},
            ),
        )

        raw = np.arange(self.entity_count, dtype=np.float64)
        self.surface_predictions = {
            "pMeanTrim": (surface_pressure + np.where(raw % 2 == 0, 0.2, -0.1)).astype(
                np.float32
            ),
            "wallShearStressMeanTrim": (
                surface_shear
                + np.column_stack((0.01 * raw, -0.02 * raw, 0.03 + 0.005 * raw))
            ).astype(np.float32),
        }
        self.volume_predictions = {
            "pMeanTrim": (
                self.volume_pressure + np.where(raw % 2 == 0, -0.15, 0.25)
            ).astype(np.float32),
            "UMeanTrim": (
                self.volume_velocity
                + np.column_stack((0.05 * raw, 0.1 - 0.02 * raw, -0.04 * raw))
            ).astype(np.float32),
        }

    def manifests(
        self,
        name: str,
        partition: tuple[int, ...],
        *,
        case_id: str = "run_1",
    ) -> tuple[Path, Path]:
        surface = _write_prediction_manifest(
            self.root / "predictions" / name / "surface",
            case_id=case_id,
            support_id="surface_native_cells",
            raw_partitions=partition,
            fields=self.surface_predictions,
        )
        volume = _write_prediction_manifest(
            self.root / "predictions" / name / "volume",
            case_id=case_id,
            support_id="volume_native_cells",
            raw_partitions=partition,
            fields=self.volume_predictions,
        )
        return surface, volume


class DrivAerMLCandidateEvaluatorTests(unittest.TestCase):
    def evaluate(
        self,
        fixture: SyntheticCase,
        surface_manifest: Path,
        volume_manifest: Path,
        *,
        maximum_rows: int = 10,
    ):
        stream = open_verified_multipart(
            fixture.resolved, verification_chunk_size=13
        )
        self.addCleanup(stream.close)
        index = index_inline_binary_vtk_xml(stream, scan_chunk_size=11)
        return evaluate_candidate_case(
            case_id="run_1",
            native_source_pin=fixture.pin,
            native_surface=fixture.surface,
            fixed_surface_areas=fixture.surface_areas,
            volume_stream=stream,
            volume_vtk_index=index,
            fixed_volume_weights=fixture.volume_weights,
            surface_prediction_manifest=surface_manifest,
            volume_prediction_manifest=volume_manifest,
            maximum_prediction_chunk_rows=maximum_rows,
            hash_chunk_bytes=17,
            validation_block_rows=2,
            encoded_chunk_bytes=7,
            source_contract=fixture.source_contract,
        )

    def test_full_and_chunked_manifests_are_metric_and_force_invariant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = SyntheticCase(Path(directory))
            full_manifests = fixture.manifests("full", (5,))
            chunk_manifests = fixture.manifests("chunked", (2, 1, 2))
            full = self.evaluate(fixture, *full_manifests)
            chunked = self.evaluate(fixture, *chunk_manifests)

            self.assertEqual(len(full.metric_values), 24)
            self.assertEqual(full.case_id, "run_1")
            self.assertEqual(full.surface_entity_count, 5)
            self.assertEqual(full.volume_entity_count, 5)
            self.assertEqual(full.surface_chunk_count, 1)
            self.assertEqual(chunked.surface_chunk_count, 3)
            for metric_id, value in full.metric_values.items():
                self.assertTrue(
                    np.isclose(
                        value,
                        chunked.metric_values[metric_id],
                        rtol=2e-15,
                        atol=1e-15,
                    ),
                    metric_id,
                )
            for coefficient in ("Cd", "Cl", "Cs", "CmPitch", "Clf", "Clr"):
                self.assertTrue(
                    np.isclose(
                        float(full.force_coefficients[coefficient]),
                        float(chunked.force_coefficients[coefficient]),
                        rtol=0.0,
                        atol=1e-15,
                    ),
                    coefficient,
                )
            self.assertEqual(
                full.metric_sufficient_statistics["surface_pressure_rel_l2"][
                    "dataset_weighting"
                ],
                "surface_face_area",
            )
            self.assertEqual(
                full.metric_sufficient_statistics["volume_pressure_rel_l2"][
                    "dataset_weighting"
                ],
                "volume_cells_equal",
            )
            self.assertEqual(
                full.volume_native_array_audits["UMeanTrim"]["tuple_count"], 5
            )
            area_audit = full.surface_area_audit["native_geometry_order_audit"]
            self.assertTrue(area_audit["raw_order_correspondence_verified"])
            self.assertEqual(area_audit["entity_count"], 5)
            self.assertLessEqual(
                area_audit["maximum_relative_difference"], 6.0e-8
            )

    def test_permuted_fixed_surface_areas_fail_geometry_order_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SyntheticCase(root)
            bad_path = root / "permuted_surface_areas.npy"
            np.save(
                bad_path,
                np.asarray(fixture.surface_areas.values_m2)[::-1].copy(),
                allow_pickle=False,
            )
            bad_areas = audit_fixed_surface_area_file(
                fixture.surface,
                bad_path,
                expected_area_sha256=_sha256_file(bad_path),
                source_boundary_sha256=fixture.surface.boundary_sha256,
            )
            surface_manifest, _ = fixture.manifests("permuted-areas", (2, 3))
            with self.assertRaisesRegex(
                ValueError,
                "published surface area differs from native polygon",
            ):
                _evaluate_surface_chunks(
                    load_prediction_chunk_manifest(surface_manifest),
                    fixture.surface,
                    bad_areas,
                    hash_chunk_bytes=17,
                    validation_block_rows=2,
                )
            bad_areas.close()

    def test_source_bound_weights_require_exact_all_receipt_replay(self) -> None:
        from scripts.aggregate_drivaerml_volume_weights import (
            DEFAULT_COPY_CHUNK_SIZE,
            DEFAULT_SOURCE_VERIFICATION_CHUNK_BYTES,
            PINNED_ALGORITHM,
            PINNED_VERSIONS,
            RECEIPT_SCHEMA,
            RECEIPT_SCHEMA_VERSION,
            aggregate_volume_weight_receipts,
            write_evidence,
        )
        from reference.drivaerml.volume_weights import implementation_file_records
        from reference.drivaerml.volume_weights import PINNED_ENVIRONMENT_BINDING

        committed_patcher = mock.patch(
            "scripts.aggregate_drivaerml_volume_weights."
            "_committed_implementation_file_records",
            return_value=implementation_file_records(),
        )
        committed_patcher.start()
        self.addCleanup(committed_patcher.stop)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SyntheticCase(root)
            weights = fixture.unbound_volume_weights
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "schema_version": RECEIPT_SCHEMA_VERSION,
                "status": "candidate_exact_native_source_verified_before_vtk",
                "case_id": "run_1",
                "implementation_binding": {
                    "git_revision": "c" * 40,
                    "worktree_clean": True,
                    "files": implementation_file_records(),
                },
                "environment_binding": PINNED_ENVIRONMENT_BINDING,
                "native_source_binding": {
                    "pin": {
                        "sha256": fixture.source_contract.pin_sha256,
                        "repository_id": fixture.source_contract.repository_id,
                        "repository_revision": (
                            fixture.source_contract.repository_revision
                        ),
                    },
                    "case_id": "run_1",
                    "logical_volume": {
                        "path": "run_1/volume_1.vtu",
                        "size_bytes": fixture.case.volume_total_size_bytes,
                        "ordered_verified_segments": [
                            {
                                "part_index": part.part_index,
                                "size_bytes": part.size_bytes,
                                "sha256": part.sha256,
                            }
                            for part in fixture.case.volume_parts
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
                    "file": fixture.volume_weight_path.name,
                    "dtype": "<f8",
                    "shape": [weights.entity_count],
                    "size_bytes": fixture.volume_weight_path.stat().st_size,
                    "sha256": weights.sha256,
                    "cell_count": weights.entity_count,
                    "volume_sum_m3": weights.volume_sum_m3,
                    "volume_min_m3": weights.volume_min_m3,
                    "volume_max_m3": weights.volume_max_m3,
                    "per_vtk_cell_type": [
                        {
                            "vtk_cell_type_id": 10,
                            "vtk_cell_type_name": "vtkTetra",
                            "cell_count": weights.entity_count,
                            "volume_sum_m3": weights.volume_sum_m3,
                            "volume_min_m3": weights.volume_min_m3,
                            "volume_max_m3": weights.volume_max_m3,
                        }
                    ],
                },
                "native_cell_types": {
                    "dtype": "uint8",
                    "shape": [weights.entity_count],
                    "order": "zero_based_raw_vtk_cell_order",
                    "payload_sha256": _sha256_bytes(
                        bytes([10]) * weights.entity_count
                    ),
                    "histogram": [
                        {
                            "vtk_cell_type_id": 10,
                            "vtk_cell_type_name": "vtkTetra",
                            "cell_count": weights.entity_count,
                        }
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
                    "disabled_point_arrays": ["syntheticPointArray"],
                    "disabled_cell_array_count": 3,
                    "disabled_cell_arrays": [
                        "pMeanTrim",
                        "UMeanTrim",
                        "syntheticCellArray",
                    ],
                },
            }
            receipt_path = root / "run_1-volume-weight-receipt.json"
            receipt_path.write_text(
                json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            aggregate = aggregate_volume_weight_receipts(
                native_source_pin_path=fixture.pin.source_path,
                receipt_paths=(receipt_path,),
                official_case_ids=("run_1",),
                expected_pin_sha256=fixture.source_contract.pin_sha256,
            )
            aggregate_path = root / "volume-weight-aggregate.json"
            write_evidence(aggregate_path, aggregate)
            aggregate_sha256 = _sha256_file(aggregate_path)
            source_contract = replace(
                fixture.source_contract,
                volume_weight_aggregate_sha256=aggregate_sha256,
            )
            bound = audit_source_bound_volume_weight_file(
                fixture.case,
                fixture.volume_weight_path,
                native_source_pin=fixture.pin,
                receipt_jsons=(receipt_path,),
                aggregate_json=aggregate_path,
                expected_aggregate_sha256=aggregate_sha256,
                expected_entity_count=fixture.entity_count,
                source_contract=source_contract,
            )
            self.assertEqual(
                bound.binding_status, SOURCE_BOUND_VOLUME_WEIGHT_STATUS
            )
            self.assertTrue(bound.aggregate_complete)
            self.assertEqual(bound.aggregate_sha256, aggregate_sha256)
            self.assertEqual(
                bound.native_cell_types, receipt["native_cell_types"]
            )
            self.assertEqual(
                list(bound.per_vtk_cell_type),
                receipt["output"]["per_vtk_cell_type"],
            )
            self.assertEqual(
                bound.aggregate_native_cell_type_payload_manifest_sha256,
                aggregate["aggregate"][
                    "native_cell_type_payload_manifest_sha256"
                ],
            )
            self.assertEqual(
                list(bound.aggregate_per_vtk_cell_type),
                aggregate["aggregate"]["per_vtk_cell_type"],
            )

            aggregate["aggregate"]["cell_count"] += 1
            write_evidence(aggregate_path, aggregate)
            tampered_sha256 = _sha256_file(aggregate_path)
            with self.assertRaisesRegex(
                DrivAerCandidateEvaluatorError, "strict all-receipt replay"
            ):
                audit_source_bound_volume_weight_file(
                    fixture.case,
                    fixture.volume_weight_path,
                    native_source_pin=fixture.pin,
                    receipt_jsons=(receipt_path,),
                    aggregate_json=aggregate_path,
                    expected_aggregate_sha256=tampered_sha256,
                    expected_entity_count=fixture.entity_count,
                    source_contract=replace(
                        source_contract,
                        volume_weight_aggregate_sha256=tampered_sha256,
                    ),
                )

    def test_compact_evidence_is_deterministic_and_truthfully_candidate_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SyntheticCase(root)
            manifests = fixture.manifests("chunked", (2, 3))
            evaluation = self.evaluate(fixture, *manifests)
            first = root / "first.json"
            second = root / "second.json"
            first_receipt = write_candidate_case_evidence(evaluation, first)
            second_receipt = write_candidate_case_evidence(evaluation, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_receipt["sha256"], second_receipt["sha256"])
            self.assertNotIn(b"\n ", first.read_bytes())
            payload = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], CANDIDATE_STATUS)
            self.assertFalse(payload["official_submission"])
            self.assertTrue(
                payload["coverage"]["surface"][
                    "complete_gap_free_duplicate_free"
                ]
            )
            self.assertEqual(
                payload["source"]["volume_weights"]["dtype"], "<f8"
            )

    def test_case_support_count_chunk_limit_and_weight_binding_reject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SyntheticCase(root)
            surface, volume = fixture.manifests("valid", (2, 3))
            wrong_case_surface, _ = fixture.manifests(
                "wrong-case", (2, 3), case_id="run_2"
            )
            with self.assertRaisesRegex(
                DrivAerCandidateEvaluatorError, "case_id differs"
            ):
                self.evaluate(fixture, wrong_case_surface, volume)

            with self.assertRaisesRegex(
                DrivAerCandidateEvaluatorError, "expected prediction support_id"
            ):
                self.evaluate(fixture, volume, surface)

            short_surface = _write_prediction_manifest(
                root / "predictions" / "short" / "surface",
                case_id="run_1",
                support_id="surface_native_cells",
                raw_partitions=(2, 2),
                fields={name: value[:4] for name, value in fixture.surface_predictions.items()},
            )
            with self.assertRaisesRegex(
                DrivAerCandidateEvaluatorError, "differs from native count"
            ):
                self.evaluate(fixture, short_surface, volume)

            with self.assertRaisesRegex(
                DrivAerCandidateEvaluatorError, "exceeds maximum_prediction_chunk_rows"
            ):
                self.evaluate(fixture, surface, volume, maximum_rows=2)

            bad_weights = replace(fixture.volume_weights, case_id="run_2")
            stream = open_verified_multipart(fixture.resolved)
            self.addCleanup(stream.close)
            index = index_inline_binary_vtk_xml(stream)
            with self.assertRaisesRegex(
                DrivAerCandidateEvaluatorError, "fixed volume weights differ"
            ):
                evaluate_candidate_case(
                    case_id="run_1",
                    native_source_pin=fixture.pin,
                    native_surface=fixture.surface,
                    fixed_surface_areas=fixture.surface_areas,
                    volume_stream=stream,
                    volume_vtk_index=index,
                    fixed_volume_weights=bad_weights,
                    surface_prediction_manifest=surface,
                    volume_prediction_manifest=volume,
                    source_contract=fixture.source_contract,
                )

            with self.assertRaisesRegex(
                DrivAerCandidateEvaluatorError, "not eligible source-bound"
            ):
                evaluate_candidate_case(
                    case_id="run_1",
                    native_source_pin=fixture.pin,
                    native_surface=fixture.surface,
                    fixed_surface_areas=fixture.surface_areas,
                    volume_stream=stream,
                    volume_vtk_index=index,
                    fixed_volume_weights=fixture.unbound_volume_weights,
                    surface_prediction_manifest=surface,
                    volume_prediction_manifest=volume,
                    source_contract=fixture.source_contract,
                )

    def test_prediction_hash_and_verified_volume_stream_reject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SyntheticCase(root)
            surface, volume = fixture.manifests("valid", (2, 3))
            surface_document = json.loads(surface.read_text(encoding="utf-8"))
            surface_document["chunks"][0]["sha256"] = "0" * 64
            surface.write_text(json.dumps(surface_document), encoding="utf-8")
            with self.assertRaisesRegex(
                DrivAerCandidateEvaluatorError, "SHA-256 mismatch"
            ):
                self.evaluate(fixture, surface, volume)

            index_stream = open_verified_multipart(fixture.resolved)
            self.addCleanup(index_stream.close)
            index = index_inline_binary_vtk_xml(index_stream)
            with self.assertRaisesRegex(
                DrivAerCandidateEvaluatorError, "volume_stream must come from"
            ):
                evaluate_candidate_case(
                    case_id="run_1",
                    native_source_pin=fixture.pin,
                    native_surface=fixture.surface,
                    fixed_surface_areas=fixture.surface_areas,
                    volume_stream=object(),  # type: ignore[arg-type]
                    volume_vtk_index=index,
                    fixed_volume_weights=fixture.volume_weights,
                    surface_prediction_manifest=surface,
                    volume_prediction_manifest=volume,
                    source_contract=fixture.source_contract,
                )

    def test_fixed_weight_and_area_mutation_after_audit_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SyntheticCase(root)

            with fixture.volume_weight_path.open("ab") as destination:
                destination.write(b"changed-after-volume-weight-audit")
            with self.assertRaisesRegex(
                DrivAerCandidateEvaluatorError, "changed after volume-weight audit"
            ):
                fixture.volume_weights.assert_source_unchanged(
                    context="after volume-weight audit"
                )

            area_path = root / "run_1" / "boundary_cell_area_1.npy"
            replacement = root / "replacement-area.npy"
            np.save(
                replacement,
                np.full(fixture.entity_count, 99.0, dtype="<f4"),
                allow_pickle=False,
            )
            os.replace(replacement, area_path)
            with self.assertRaisesRegex(
                ValueError, "changed after surface-area audit"
            ):
                fixture.surface_areas.assert_source_unchanged(
                    context="after surface-area audit"
                )


if __name__ == "__main__":
    unittest.main()
