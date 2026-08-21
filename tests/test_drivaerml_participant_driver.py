from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
DRIVER_PATH = (
    ROOT
    / "examples"
    / "drivaerml-candidate-native-chunks"
    / "reference_driver.py"
)
REAL_DRIVER_PATH = (
    ROOT
    / "examples"
    / "drivaerml-candidate-native-chunks"
    / "real_reference_driver.py"
)
CLEAN_REPOSITORY_IDENTITY = {
    "git_metadata_available": True,
    "git_revision": "a" * 40,
    "tracked_worktree_clean": True,
}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DrivAerMLParticipantDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.driver = load_module(
            DRIVER_PATH, "drivaerml_candidate_native_chunk_driver"
        )
        cls.real_driver = load_module(
            REAL_DRIVER_PATH, "drivaerml_run1_run44_reference_driver"
        )

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_demo_is_schema_valid_chunk_invariant_and_truthfully_ineligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            receipt = self.driver.run_demo(output)
            self.assertEqual(receipt["status"], "candidate_demo_valid")
            self.assertEqual(
                [(case["case_id"], case["transport"]["part_count"]) for case in receipt["cases"]],
                [("run_1", 2), ("run_44", 3)],
            )
            for case in receipt["cases"]:
                self.assertTrue(
                    case["inference_chunks"]["complete_duplicate_free_coverage"]
                )
                self.assertTrue(
                    case["inference_chunks"]["independent_of_transport_part_boundaries"]
                )
                self.assertTrue(case["full_case_vs_chunked"]["pressure"]["passed"])
                self.assertTrue(case["full_case_vs_chunked"]["velocity"]["passed"])
            self.assertFalse(receipt["claims"]["uses_real_drivaerml_data"])
            self.assertTrue(
                receipt["claims"]["schema_v3_dummy_submission_generated"]
            )
            self.assertFalse(
                receipt["claims"]["official_drivaerml_submission_generated"]
            )
            self.assertFalse(
                receipt["claims"]["eligible_for_leaderboard_or_scientific_claims"]
            )
            self.assertFalse(receipt["claims"]["independent_participant_dry_run"])
            self.assertEqual(
                receipt["observed_candidate_contract"]["scoring_support_status"],
                "owner_review_required",
            )
            self.assertFalse(
                receipt["observed_candidate_contract"]["submissions_open"]
            )
            submission = json.loads(
                (output / "submission.json").read_text(encoding="utf-8")
            )
            self.assertEqual(submission["schema_version"], "3.0")
            self.assertEqual(submission["dataset_id"], "synthetic-drivaerml-shaped")
            self.assertTrue(submission["submission_id"].startswith("synthetic-"))
            self.assertNotEqual(submission["dataset_id"], "drivaerml")
            self.assertNotIn("approval", submission)
            self.assertIn("INELIGIBLE SYNTHETIC FIXTURE", submission["note"])
            self.assertIn(
                "candidate status applies only",
                submission["note"].lower(),
            )
            support = json.loads(
                (output / "support" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(support["status"], "candidate")
            self.assertEqual(
                submission["scoring_support"]["manifest_sha256"],
                self.sha256(output / "support" / "manifest.json"),
            )
            self.assertEqual(
                submission["evaluation"]["evidence_sha256"],
                self.sha256(output / "evaluation-evidence.json"),
            )
            self.assertEqual(
                submission["spatial_discretization"]["sha256"],
                self.sha256(output / "discretization.json"),
            )
            self.assertEqual(
                submission["case_metrics"]["sha256"],
                self.sha256(output / "metrics" / "cases.json"),
            )
            prediction_manifest_path = output / "predictions" / "manifest.json"
            prediction_artifacts = submission["prediction_artifacts"]
            self.assertEqual(len(prediction_artifacts), 1)
            self.assertEqual(
                prediction_artifacts[0]["manifest_file"],
                "predictions/manifest.json",
            )
            self.assertEqual(
                prediction_artifacts[0]["manifest_sha256"],
                self.sha256(prediction_manifest_path),
            )
            self.assertEqual(
                prediction_artifacts[0]["support_manifest_sha256"],
                self.sha256(output / "support" / "manifest.json"),
            )
            prediction_manifest = json.loads(
                prediction_manifest_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                prediction_artifacts[0]["artifact_id"],
                prediction_manifest["artifact_id"],
            )
            self.assertEqual(prediction_manifest["kind"], "scored_predictions")
            self.assertIn(
                "v3/submission.schema.json", receipt["schema_checks"]
            )
            self.assertIn(
                "v3/discretization-case.schema.json", receipt["schema_checks"]
            )

            metrics = json.loads(
                (output / "metrics" / "cases.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metrics["case_count"], 2)
            self.assertEqual(
                [case["case_id"] for case in metrics["cases"]],
                ["run_1", "run_44"],
            )
            self.assertEqual(
                set(metrics["metric_values"]),
                {
                    "volume_pressure_rel_l2",
                    "volume_velocity_rel_l2",
                },
            )
            synthetic_support = support["supports"][0]
            self.assertEqual(
                synthetic_support["location_definition"]["weight_rule"],
                {"kind": "uniform"},
            )
            self.assertEqual(
                {
                    binding["metric_id"]: (
                        binding["weighting"], binding["dataset_weighting"]
                    )
                    for binding in synthetic_support["metric_bindings"]
                },
                {
                    "volume_pressure_rel_l2": (
                        "uniform",
                        "volume_cells_equal",
                    ),
                    "volume_velocity_rel_l2": (
                        "uniform",
                        "volume_cells_equal",
                    ),
                },
            )

    def test_synthetic_driver_adversarially_requires_real_candidate_closed(self) -> None:
        candidate_path = ROOT / "benchmark-specs" / "drivaerml" / "submission-spec.json"
        closed = json.loads(candidate_path.read_text(encoding="utf-8"))
        self.driver._assert_closed_real_drivaerml_candidate(closed)
        mutations = (
            ("dataset_id", "synthetic-drivaerml-shaped"),
            ("status", "active"),
            ("scoring_support.status", "official"),
            ("scoring_support.submissions_open", True),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = json.loads(json.dumps(closed))
                if field.startswith("scoring_support."):
                    changed["scoring_support"][field.split(".", 1)[1]] = value
                else:
                    changed[field] = value
                with self.assertRaisesRegex(
                    ValueError, "exact closed, owner-review-required state"
                ):
                    self.driver._assert_closed_real_drivaerml_candidate(changed)

    def test_cli_is_one_command_and_refuses_a_nonempty_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            completed = subprocess.run(
                [sys.executable, str(DRIVER_PATH), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(
                "CANDIDATE DEMO VALID: synthetic DrivAerML-shaped",
                completed.stdout,
            )
            candidate_validation = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate_submission.py",
                    "--candidate-dry-run",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(candidate_validation.returncode, 1)
            self.assertIn("unknown dataset_id", candidate_validation.stderr)

            repeated = subprocess.run(
                [sys.executable, str(DRIVER_PATH), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn("output directory is not empty", repeated.stderr)

    def test_real_driver_help_describes_candidate_only_multipart_run(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(REAL_DRIVER_PATH), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("run_1 and run_44", completed.stdout)
        self.assertIn("--case-inputs", completed.stdout)
        for obsolete_option in (
            "--volume-weight-npy",
            "--volume-weight-receipt",
            "--volume-weight-aggregate",
            "--pilot-volume-weight-aggregate-sha256",
            "--allow-incomplete-volume-weight-pilot",
        ):
            self.assertNotIn(obsolete_option, completed.stdout)
        self.assertIn("never writes ``submission.json``", completed.stdout)

    def _real_driver_fixture(self, root: Path) -> tuple[Path, SimpleNamespace]:
        input_file = root / "input.dat"
        input_file.write_bytes(b"fixture")
        profile_file = root / "autocfd5-profiles-v8.json"
        profile_file.write_bytes(
            (
                ROOT
                / "benchmark-specs"
                / "drivaerml"
                / "autocfd5-profiles-v8.json"
            ).read_bytes()
        )
        cases = []
        for case_id in ("run_1", "run_44"):
            row = {"case_id": case_id}
            for key in self.real_driver.CASE_INPUT_KEYS - {"case_id"}:
                row[key] = input_file.name
            cases.append(row)
        config = root / "case-inputs.json"
        config.write_text(
            json.dumps(
                {"schema": self.real_driver.INPUT_SCHEMA, "cases": cases},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        dataset = root / "dataset"
        dataset.mkdir()
        args = SimpleNamespace(
            case_inputs=config,
            native_source_pin=input_file,
            dataset_root=dataset,
            autocfd5_profile=profile_file,
            output=root / "result",
            maximum_prediction_chunk_rows=17,
            io_chunk_bytes=4096,
        )
        return config, args

    @staticmethod
    def _fake_preflight_pin():
        records = {}
        for case_id, part_count, surface_count, volume_count in (
            ("run_1", 2, 11, 13),
            ("run_44", 3, 17, 19),
        ):
            records[case_id] = SimpleNamespace(
                boundary=SimpleNamespace(
                    sha256=hashlib.sha256(
                        f"{case_id}/boundary".encode("utf-8")
                    ).hexdigest()
                ),
                surface_cell_area=SimpleNamespace(element_count=surface_count),
                native_cell_count=volume_count,
                volume_parts=tuple(
                    SimpleNamespace(
                        sha256=hashlib.sha256(
                            f"{case_id}/part/{index}".encode("utf-8")
                        ).hexdigest()
                    )
                    for index in range(part_count)
                ),
            )

        class FakePin:
            def case(self, case_id):
                return records[case_id]

            def resolve(self, case_id, dataset_root):
                return SimpleNamespace(case_id=case_id, dataset_root=dataset_root)

        return FakePin()

    @staticmethod
    def _fake_real_evidence(
        kind: str,
        case_id: str,
        *,
        native_source_pin_sha256: str,
        autocfd5_profile_sha256: str,
        diagnostic_manifest_mismatch: bool = False,
    ) -> dict[str, object]:
        identities: dict[str, dict[str, object]] = {}
        for support_id, entity_count in (
            ("surface_native_cells", 2),
            ("volume_native_cells", 3),
        ):
            manifest_seed = f"{case_id}/{support_id}/manifest"
            if diagnostic_manifest_mismatch and support_id == "volume_native_cells":
                manifest_seed += "/mismatch"
            identities[support_id] = {
                "manifest_sha256": hashlib.sha256(
                    manifest_seed.encode("utf-8")
                ).hexdigest(),
                "chunk_sha256": [
                    hashlib.sha256(
                        f"{case_id}/{support_id}/chunk-0".encode("utf-8")
                    ).hexdigest()
                ],
                "chunk_count": 1,
                "entity_count": entity_count,
            }
        if kind == "core":
            return {
                "schema": "drivaerml-candidate-case-evaluation-v2",
                "schema_version": 2,
                "case_id": case_id,
                "source": {
                    "native_source_pin_sha256": native_source_pin_sha256,
                    "surface_native": {"vtk_version": "9.5.2"},
                },
                "prediction_inputs": identities,
            }
        return {
            "schema": "drivaerml-autocfd5-case-diagnostics-candidate-v1",
            "schema_version": 1,
            "case_id": case_id,
            "mapping_inputs": {
                "cp_support": {
                    "profile_sha256": autocfd5_profile_sha256,
                },
                "velocity_10mm": {
                    "profile_sha256": autocfd5_profile_sha256,
                },
            },
            "sparse_gather_evidence": {
                "surface_prediction": {
                    **identities["surface_native_cells"],
                    "total_row_count": identities["surface_native_cells"][
                        "entity_count"
                    ],
                },
                "volume_prediction": {
                    **identities["volume_native_cells"],
                    "total_row_count": identities["volume_native_cells"][
                        "entity_count"
                    ],
                },
            },
        }

    def test_real_driver_orchestrates_exact_two_and_three_part_cases(self) -> None:
        class FakePin:
            def case(self, case_id):
                count = {"run_1": 2, "run_44": 3}[case_id]
                return SimpleNamespace(volume_parts=tuple(object() for _ in range(count)))

            def resolve(self, case_id, dataset_root):
                return SimpleNamespace(case_id=case_id, dataset_root=dataset_root)

        calls: list[tuple[str, str, bool]] = []

        def fake_evaluator(kind):
            def run(args):
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(
                        self._fake_real_evidence(
                            kind,
                            args.case_id,
                            native_source_pin_sha256=self.sha256(
                                args.native_source_pin
                            ),
                            autocfd5_profile_sha256=(
                                self.real_driver.EXPECTED_PROFILE_SHA256
                                if kind == "core"
                                else self.sha256(args.autocfd5_profile)
                            ),
                        )
                    )
                    + "\n",
                    encoding="utf-8",
                )
                calls.append((kind, args.case_id, args.multipart))
                return {
                    "sha256": self.sha256(args.output),
                    "byte_size": args.output.stat().st_size,
                }

            return run

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, args = self._real_driver_fixture(root)
            self.assertEqual(
                self.real_driver.INPUT_SCHEMA,
                "drivaerml-run1-run44-reference-inputs-v2",
            )
            self.assertEqual(
                json.loads(config.read_text(encoding="utf-8"))["schema"],
                self.real_driver.INPUT_SCHEMA,
            )
            self.assertEqual(
                self.real_driver.CASE_INPUT_KEYS,
                {
                    "case_id",
                    "surface_area_npy",
                    "surface_prediction_manifest",
                    "volume_prediction_manifest",
                    "cp_support_json",
                    "velocity_mapping_json",
                    "velocity_receipt_json",
                },
            )
            self.assertNotIn("volume_weight", config.read_text(encoding="utf-8"))
            with (
                patch.object(
                    self.real_driver,
                    "_repository_identity",
                    return_value=CLEAN_REPOSITORY_IDENTITY,
                ),
                patch.object(
                    self.real_driver,
                    "load_native_source_pin",
                    return_value=FakePin(),
                ),
                patch.object(
                    self.real_driver,
                    "validate_native_source_contract",
                    return_value=self.sha256(args.native_source_pin),
                ),
                patch.object(
                    self.real_driver,
                    "_preflight_case_inputs",
                    return_value={},
                ),
                patch.object(
                    self.real_driver, "_run_core_case", fake_evaluator("core")
                ),
                patch.object(
                    self.real_driver,
                    "_run_diagnostic_case",
                    fake_evaluator("diagnostic"),
                ),
            ):
                receipt = self.real_driver.run(args)
            self.assertEqual(
                calls,
                [
                    ("core", "run_1", True),
                    ("diagnostic", "run_1", True),
                    ("core", "run_44", True),
                    ("diagnostic", "run_44", True),
                ],
            )
            self.assertEqual(
                [case["pinned_volume_part_count"] for case in receipt["cases"]],
                [2, 3],
            )
            self.assertFalse(receipt["official_submission"])
            self.assertFalse(receipt["downloads_performed"])
            self.assertEqual(
                receipt["schema"], "drivaerml-run1-run44-reference-evidence-v3"
            )
            self.assertEqual(receipt["schema_version"], 3)
            self.assertEqual(receipt["volume_weighting"], "one_per_native_cell")
            self.assertFalse(receipt["geometric_cell_volume_weights_used"])
            self.assertEqual(
                receipt["case_input_config_sha256"], self.sha256(config)
            )
            self.assertEqual(
                receipt["autocfd5_profile_sha256"],
                self.real_driver.EXPECTED_PROFILE_SHA256,
            )
            self.assertEqual(
                receipt["evaluator_binding"]["reference_version"],
                "drivaerml-evaluator-v2-candidate",
            )
            self.assertFalse(receipt["evaluator_binding"]["frozen_release"])
            self.assertEqual(
                receipt["runtime"],
                {
                    "python": self.real_driver.platform.python_version(),
                    "numpy": self.real_driver.np.__version__,
                    "vtk": "9.5.2",
                    "byte_order": sys.byteorder,
                },
            )
            self.assertEqual(
                receipt["evaluator_binding"]["repository_url"],
                "https://github.com/neilashton/fluidsbench-submission",
            )
            self.assertFalse(receipt["complete_484_case_split_evaluated"])
            self.assertFalse(receipt["public_scoring_support_eligible"])
            self.assertEqual(
                set(
                    receipt["evaluator_binding"][
                        "implementation_files_sha256"
                    ]
                ),
                set(self.real_driver.IMPLEMENTATION_FILES),
            )
            for relative_path, digest in receipt["evaluator_binding"][
                "implementation_files_sha256"
            ].items():
                self.assertEqual(digest, self.sha256(ROOT / relative_path))
            repository = receipt["evaluator_binding"]["repository"]
            self.assertTrue(repository["git_metadata_available"])
            self.assertRegex(repository["git_revision"], r"^[0-9a-f]{40}$")
            self.assertEqual(repository, CLEAN_REPOSITORY_IDENTITY)
            self.assertIsInstance(repository["tracked_worktree_clean"], bool)
            for obsolete_field in (
                "volume_weight_aggregate_sha256",
                "volume_weight_receipt_sha256",
                "pilot_incomplete_volume_weight_aggregate",
            ):
                self.assertNotIn(obsolete_field, receipt)
            self.assertTrue(
                all(
                    case["cross_evaluator_prediction_identity_verified"]
                    for case in receipt["cases"]
                )
            )
            self.assertTrue((args.output / "validation-receipt.json").is_file())
            self.assertFalse((args.output / "submission.json").exists())

    def test_real_driver_preflights_every_cp_support_before_core(self) -> None:
        for bad_case, expected_cp_calls in (
            ("run_1", ["run_1"]),
            ("run_44", ["run_1", "run_44"]),
        ):
            with self.subTest(bad_case=bad_case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, args = self._real_driver_fixture(root)
                cp_calls: list[str] = []

                def fake_cp_loader(path, *, case_id, **kwargs):
                    cp_calls.append(case_id)
                    if case_id == bad_case:
                        raise self.real_driver.DrivAerDiagnosticEvaluatorError(
                            f"bad {case_id} Cp support"
                        )
                    resolved = Path(path).resolve()
                    return SimpleNamespace(
                        path=resolved,
                        sha256=self.sha256(resolved),
                    )

                with (
                    patch.object(
                        self.real_driver,
                        "_repository_identity",
                        return_value=CLEAN_REPOSITORY_IDENTITY,
                    ),
                    patch.object(
                        self.real_driver,
                        "load_native_source_pin",
                        return_value=self._fake_preflight_pin(),
                    ),
                    patch.object(
                        self.real_driver,
                        "validate_native_source_contract",
                        return_value=self.sha256(args.native_source_pin),
                    ),
                    patch.object(
                        self.real_driver,
                        "load_strict_cp_case_support",
                        side_effect=fake_cp_loader,
                    ),
                    patch.object(self.real_driver, "_run_core_case") as core,
                    patch.object(
                        self.real_driver, "_run_diagnostic_case"
                    ) as diagnostic,
                ):
                    with self.assertRaisesRegex(
                        self.real_driver.DrivAerDiagnosticEvaluatorError,
                        f"bad {bad_case} Cp support",
                    ):
                        self.real_driver.run(args)
                self.assertEqual(cp_calls, expected_cp_calls)
                core.assert_not_called()
                diagnostic.assert_not_called()
                self.assertFalse(args.output.exists())

    def test_real_driver_preflights_later_velocity_support_before_core(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, args = self._real_driver_fixture(root)
            pin = self._fake_preflight_pin()
            cp_calls: list[str] = []
            velocity_calls: list[str] = []

            def fake_cp_loader(path, *, case_id, **kwargs):
                cp_calls.append(case_id)
                resolved = Path(path).resolve()
                return SimpleNamespace(
                    path=resolved,
                    sha256=self.sha256(resolved),
                    boundary_polygon_count=(
                        pin.case(case_id).surface_cell_area.element_count
                    ),
                )

            def fake_velocity_loader(
                artifact_path, receipt_path, *, case_id, **kwargs
            ):
                velocity_calls.append(case_id)
                if case_id == "run_44":
                    raise self.real_driver.DrivAerDiagnosticEvaluatorError(
                        "bad run_44 velocity support"
                    )
                artifact = Path(artifact_path).resolve()
                receipt = Path(receipt_path).resolve()
                return SimpleNamespace(
                    artifact_path=artifact,
                    artifact_sha256=self.sha256(artifact),
                    receipt_path=receipt,
                    receipt_sha256=self.sha256(receipt),
                    native_cell_count=pin.case(case_id).native_cell_count,
                )

            with (
                patch.object(
                    self.real_driver,
                    "_repository_identity",
                    return_value=CLEAN_REPOSITORY_IDENTITY,
                ),
                patch.object(
                    self.real_driver,
                    "load_native_source_pin",
                    return_value=pin,
                ),
                patch.object(
                    self.real_driver,
                    "validate_native_source_contract",
                    return_value=self.sha256(args.native_source_pin),
                ),
                patch.object(
                    self.real_driver,
                    "load_strict_cp_case_support",
                    side_effect=fake_cp_loader,
                ),
                patch.object(
                    self.real_driver,
                    "load_strict_velocity_10mm_mapping",
                    side_effect=fake_velocity_loader,
                ),
                patch.object(self.real_driver, "_run_core_case") as core,
                patch.object(
                    self.real_driver, "_run_diagnostic_case"
                ) as diagnostic,
            ):
                with self.assertRaisesRegex(
                    self.real_driver.DrivAerDiagnosticEvaluatorError,
                    "bad run_44 velocity support",
                ):
                    self.real_driver.run(args)
            self.assertEqual(cp_calls, ["run_1", "run_44"])
            self.assertEqual(velocity_calls, ["run_1", "run_44"])
            core.assert_not_called()
            diagnostic.assert_not_called()
            self.assertFalse(args.output.exists())

    def test_real_driver_compact_preflight_binds_mapping_and_manifest_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, args = self._real_driver_fixture(root)
            config_document = json.loads(config.read_text(encoding="utf-8"))
            for row in config_document["cases"]:
                for key in self.real_driver.CASE_INPUT_KEYS - {"case_id"}:
                    case_input = root / f"{row['case_id']}-{key}.dat"
                    case_input.write_bytes(
                        f"{row['case_id']}/{key}".encode("utf-8")
                    )
                    row[key] = case_input.name
            config.write_text(
                json.dumps(config_document, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            pin = self._fake_preflight_pin()
            pin_sha256 = self.sha256(args.native_source_pin)
            with (
                patch.object(
                    self.real_driver,
                    "load_native_source_pin",
                    return_value=pin,
                ),
                patch.object(
                    self.real_driver,
                    "validate_native_source_contract",
                    return_value=pin_sha256,
                ),
            ):
                preflight = self.real_driver._preflight(args)

            cp_calls: list[str] = []
            velocity_calls: list[str] = []
            expected_manifests = [
                (
                    case_id,
                    support_id,
                    (
                        pin.case(case_id).surface_cell_area.element_count
                        if support_id == "surface_native_cells"
                        else pin.case(case_id).native_cell_count
                    ),
                )
                for case_id in ("run_1", "run_44")
                for support_id in (
                    "surface_native_cells",
                    "volume_native_cells",
                )
            ]
            manifest_calls: list[tuple[str, str, int]] = []

            def fake_cp_loader(
                path, *, autocfd5_profile, case_id, expected_boundary_sha256
            ):
                cp_calls.append(case_id)
                self.assertEqual(
                    Path(autocfd5_profile), preflight.autocfd5_profile_path
                )
                self.assertEqual(
                    expected_boundary_sha256, pin.case(case_id).boundary.sha256
                )
                resolved = Path(path).resolve()
                return SimpleNamespace(
                    path=resolved,
                    sha256=self.sha256(resolved),
                    boundary_polygon_count=(
                        pin.case(case_id).surface_cell_area.element_count
                    ),
                )

            def fake_velocity_loader(
                artifact_path,
                receipt_path,
                *,
                autocfd5_profile,
                case_id,
                expected_source_pin_sha256,
                expected_source_part_sha256,
            ):
                velocity_calls.append(case_id)
                self.assertEqual(
                    Path(autocfd5_profile), preflight.autocfd5_profile_path
                )
                self.assertEqual(expected_source_pin_sha256, pin_sha256)
                self.assertEqual(
                    expected_source_part_sha256,
                    tuple(part.sha256 for part in pin.case(case_id).volume_parts),
                )
                artifact = Path(artifact_path).resolve()
                receipt = Path(receipt_path).resolve()
                return SimpleNamespace(
                    artifact_path=artifact,
                    artifact_sha256=self.sha256(artifact),
                    receipt_path=receipt,
                    receipt_sha256=self.sha256(receipt),
                    native_cell_count=pin.case(case_id).native_cell_count,
                )

            def fake_manifest_loader(path):
                case_id, support_id, count = expected_manifests[len(manifest_calls)]
                manifest_calls.append((case_id, support_id, count))
                resolved = Path(path).resolve()
                return SimpleNamespace(
                    path=resolved,
                    sha256=self.sha256(resolved),
                    case_id=case_id,
                    support_id=support_id,
                    total_row_count=count,
                )

            with (
                patch.object(
                    self.real_driver,
                    "load_strict_cp_case_support",
                    side_effect=fake_cp_loader,
                ),
                patch.object(
                    self.real_driver,
                    "load_strict_velocity_10mm_mapping",
                    side_effect=fake_velocity_loader,
                ),
                patch.object(
                    self.real_driver,
                    "load_prediction_chunk_manifest",
                    side_effect=fake_manifest_loader,
                ),
            ):
                retained = self.real_driver._preflight_case_inputs(preflight)

            self.assertEqual(cp_calls, ["run_1", "run_44"])
            self.assertEqual(velocity_calls, ["run_1", "run_44"])
            self.assertEqual(manifest_calls, expected_manifests)
            expected_retained_paths = {
                getattr(case, field)
                for case in preflight.cases
                for field in (
                    "cp_support_json",
                    "velocity_mapping_json",
                    "velocity_receipt_json",
                    "surface_prediction_manifest",
                    "volume_prediction_manifest",
                )
            }
            self.assertEqual(
                set(retained),
                expected_retained_paths,
            )
            for path, (_, digest) in retained.items():
                self.assertEqual(digest, self.sha256(path))

    def test_real_driver_requires_clean_identifiable_git_checkout(self) -> None:
        for identity, message in (
            (
                {
                    "git_metadata_available": False,
                    "git_revision": None,
                    "tracked_worktree_clean": None,
                },
                "identifiable Git checkout",
            ),
            (
                {
                    "git_metadata_available": True,
                    "git_revision": "a" * 40,
                    "tracked_worktree_clean": False,
                },
                "clean tracked Git worktree",
            ),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(
                self.real_driver.RealReferenceDriverError, message
            ):
                self.real_driver._require_clean_evidence_repository(identity)

    def test_real_driver_rejects_case_input_config_mutation(self) -> None:
        class FakePin:
            def case(self, case_id):
                count = {"run_1": 2, "run_44": 3}[case_id]
                return SimpleNamespace(
                    volume_parts=tuple(object() for _ in range(count))
                )

            def resolve(self, case_id, dataset_root):
                return SimpleNamespace(case_id=case_id, dataset_root=dataset_root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, args = self._real_driver_fixture(root)
            mutated = False

            def fake_core(run_args):
                nonlocal mutated
                run_args.output.parent.mkdir(parents=True, exist_ok=True)
                run_args.output.write_text(
                    json.dumps(
                        self._fake_real_evidence(
                            "core",
                            run_args.case_id,
                            native_source_pin_sha256=self.sha256(
                                run_args.native_source_pin
                            ),
                            autocfd5_profile_sha256=(
                                self.real_driver.EXPECTED_PROFILE_SHA256
                            ),
                        )
                    )
                    + "\n",
                    encoding="utf-8",
                )
                if not mutated:
                    config.write_text(
                        config.read_text(encoding="utf-8") + "\n",
                        encoding="utf-8",
                    )
                    mutated = True
                return {
                    "sha256": self.sha256(run_args.output),
                    "byte_size": run_args.output.stat().st_size,
                }

            def fake_diagnostic(run_args):
                run_args.output.parent.mkdir(parents=True, exist_ok=True)
                run_args.output.write_text(
                    json.dumps(
                        self._fake_real_evidence(
                            "diagnostic",
                            run_args.case_id,
                            native_source_pin_sha256=self.sha256(
                                run_args.native_source_pin
                            ),
                            autocfd5_profile_sha256=self.sha256(
                                run_args.autocfd5_profile
                            ),
                        )
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return {
                    "sha256": self.sha256(run_args.output),
                    "byte_size": run_args.output.stat().st_size,
                }

            with (
                patch.object(
                    self.real_driver,
                    "_repository_identity",
                    return_value=CLEAN_REPOSITORY_IDENTITY,
                ),
                patch.object(
                    self.real_driver,
                    "load_native_source_pin",
                    return_value=FakePin(),
                ),
                patch.object(
                    self.real_driver,
                    "validate_native_source_contract",
                    return_value=self.sha256(args.native_source_pin),
                ),
                patch.object(
                    self.real_driver,
                    "_preflight_case_inputs",
                    return_value={},
                ),
                patch.object(self.real_driver, "_run_core_case", fake_core),
                patch.object(
                    self.real_driver,
                    "_run_diagnostic_case",
                    fake_diagnostic,
                ),
            ):
                with self.assertRaisesRegex(
                    self.real_driver.RealReferenceDriverError,
                    "case-input config changed after it was parsed",
                ):
                    self.real_driver.run(args)
            self.assertTrue(mutated)
            self.assertFalse(args.output.exists())

    def test_real_driver_rejects_wrong_case_set_before_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _ = self._real_driver_fixture(root)
            document = json.loads(config.read_text(encoding="utf-8"))
            document["cases"][1]["case_id"] = "run_2"
            config.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                self.real_driver.RealReferenceDriverError,
                "only permitted cases are run_1 and run_44",
            ):
                self.real_driver.load_case_inputs(config)

    def test_real_driver_rejects_native_source_pin_mutation(self) -> None:
        class FakePin:
            def case(self, case_id):
                count = {"run_1": 2, "run_44": 3}[case_id]
                return SimpleNamespace(
                    volume_parts=tuple(object() for _ in range(count))
                )

            def resolve(self, case_id, dataset_root):
                return SimpleNamespace(case_id=case_id, dataset_root=dataset_root)

        mutated = False

        def fake_evaluator(kind):
            def run(run_args):
                nonlocal mutated
                run_args.output.parent.mkdir(parents=True, exist_ok=True)
                pin_sha256 = self.sha256(run_args.native_source_pin)
                profile_sha256 = (
                    self.real_driver.EXPECTED_PROFILE_SHA256
                    if kind == "core"
                    else self.sha256(run_args.autocfd5_profile)
                )
                run_args.output.write_text(
                    json.dumps(
                        self._fake_real_evidence(
                            kind,
                            run_args.case_id,
                            native_source_pin_sha256=pin_sha256,
                            autocfd5_profile_sha256=profile_sha256,
                        )
                    )
                    + "\n",
                    encoding="utf-8",
                )
                if (
                    kind == "diagnostic"
                    and run_args.case_id == "run_44"
                    and not mutated
                ):
                    run_args.native_source_pin.write_bytes(b"mutated pin")
                    mutated = True
                return {
                    "sha256": self.sha256(run_args.output),
                    "byte_size": run_args.output.stat().st_size,
                }

            return run

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, args = self._real_driver_fixture(root)
            initial_pin_sha256 = self.sha256(args.native_source_pin)
            with (
                patch.object(
                    self.real_driver,
                    "_repository_identity",
                    return_value=CLEAN_REPOSITORY_IDENTITY,
                ),
                patch.object(
                    self.real_driver,
                    "load_native_source_pin",
                    return_value=FakePin(),
                ),
                patch.object(
                    self.real_driver,
                    "validate_native_source_contract",
                    return_value=initial_pin_sha256,
                ),
                patch.object(
                    self.real_driver,
                    "_preflight_case_inputs",
                    return_value={},
                ),
                patch.object(
                    self.real_driver,
                    "_run_core_case",
                    fake_evaluator("core"),
                ),
                patch.object(
                    self.real_driver,
                    "_run_diagnostic_case",
                    fake_evaluator("diagnostic"),
                ),
            ):
                with self.assertRaisesRegex(
                    self.real_driver.RealReferenceDriverError,
                    "native-source pin changed after it was parsed",
                ):
                    self.real_driver.run(args)
            self.assertTrue(mutated)
            self.assertFalse(args.output.exists())

    def test_real_driver_rejects_cross_evaluator_prediction_mismatch(self) -> None:
        class FakePin:
            def case(self, case_id):
                count = {"run_1": 2, "run_44": 3}[case_id]
                return SimpleNamespace(
                    volume_parts=tuple(object() for _ in range(count))
                )

            def resolve(self, case_id, dataset_root):
                return SimpleNamespace()

        def fake_evaluator(kind, *, mismatch=False):
            def run(args):
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(
                        self._fake_real_evidence(
                            kind,
                            args.case_id,
                            native_source_pin_sha256=self.sha256(
                                args.native_source_pin
                            ),
                            autocfd5_profile_sha256=(
                                self.real_driver.EXPECTED_PROFILE_SHA256
                                if kind == "core"
                                else self.sha256(args.autocfd5_profile)
                            ),
                            diagnostic_manifest_mismatch=mismatch,
                        )
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return {
                    "sha256": self.sha256(args.output),
                    "byte_size": args.output.stat().st_size,
                }

            return run

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, args = self._real_driver_fixture(root)
            with (
                patch.object(
                    self.real_driver,
                    "_repository_identity",
                    return_value=CLEAN_REPOSITORY_IDENTITY,
                ),
                patch.object(
                    self.real_driver,
                    "load_native_source_pin",
                    return_value=FakePin(),
                ),
                patch.object(
                    self.real_driver,
                    "validate_native_source_contract",
                    return_value=self.sha256(args.native_source_pin),
                ),
                patch.object(
                    self.real_driver,
                    "_preflight_case_inputs",
                    return_value={},
                ),
                patch.object(
                    self.real_driver,
                    "_run_core_case",
                    fake_evaluator("core"),
                ),
                patch.object(
                    self.real_driver,
                    "_run_diagnostic_case",
                    fake_evaluator("diagnostic", mismatch=True),
                ),
            ):
                with self.assertRaisesRegex(
                    self.real_driver.RealReferenceDriverError,
                    "different prediction manifest, chunk, or entity identities",
                ):
                    self.real_driver.run(args)
            self.assertFalse(args.output.exists())

    def test_real_driver_failure_leaves_no_partial_output(self) -> None:
        class FakePin:
            def case(self, case_id):
                count = {"run_1": 2, "run_44": 3}[case_id]
                return SimpleNamespace(volume_parts=tuple(object() for _ in range(count)))

            def resolve(self, case_id, dataset_root):
                return SimpleNamespace()

        def fake_core(args):
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(
                    self._fake_real_evidence(
                        "core",
                        args.case_id,
                        native_source_pin_sha256=self.sha256(
                            args.native_source_pin
                        ),
                        autocfd5_profile_sha256=(
                            self.real_driver.EXPECTED_PROFILE_SHA256
                        ),
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            return {
                "sha256": self.sha256(args.output),
                "byte_size": args.output.stat().st_size,
            }

        def fake_diagnostic(args):
            if args.case_id == "run_44":
                raise self.real_driver.RealReferenceDriverError("injected failure")
            args.output.write_text(
                json.dumps(
                    self._fake_real_evidence(
                        "diagnostic",
                        args.case_id,
                        native_source_pin_sha256=self.sha256(
                            args.native_source_pin
                        ),
                        autocfd5_profile_sha256=self.sha256(
                            args.autocfd5_profile
                        ),
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            return {
                "sha256": self.sha256(args.output),
                "byte_size": args.output.stat().st_size,
            }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, args = self._real_driver_fixture(root)
            with (
                patch.object(
                    self.real_driver,
                    "_repository_identity",
                    return_value=CLEAN_REPOSITORY_IDENTITY,
                ),
                patch.object(
                    self.real_driver,
                    "load_native_source_pin",
                    return_value=FakePin(),
                ),
                patch.object(
                    self.real_driver,
                    "validate_native_source_contract",
                    return_value=self.sha256(args.native_source_pin),
                ),
                patch.object(
                    self.real_driver,
                    "_preflight_case_inputs",
                    return_value={},
                ),
                patch.object(self.real_driver, "_run_core_case", fake_core),
                patch.object(
                    self.real_driver, "_run_diagnostic_case", fake_diagnostic
                ),
            ):
                with self.assertRaisesRegex(
                    self.real_driver.RealReferenceDriverError, "injected failure"
                ):
                    self.real_driver.run(args)
            self.assertFalse(args.output.exists())


if __name__ == "__main__":
    unittest.main()
