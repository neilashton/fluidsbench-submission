# DrivAerML candidate participant guide

This guide describes the proposed native-mesh workflow for AutoCFD and
FluidsBench contributors. The contract is still a closed candidate:
`submissions_open` is `false`, the composite is inactive, and no package made
with these instructions is an official leaderboard submission yet.

## 1. Choose one official split

Choose exactly one JSON file in [`splits/`](splits/). Fit the model and every
learned or data-dependent preprocessing quantity using only that file's
`train_case_ids`. The `validation_case_ids` may be used only as the split
permits for model selection. The `case_ids` are public evaluation cases, but
their fields must not affect fitting, tuning, checkpoint choice, manual
selection, normalization, or other training statistics.

Record the split ID, ordered train/validation/test case lists, source dataset
revision, model commit, checkpoint hash, and preprocessing configuration.

## 2. Predict on the actual native supports

The source dataset is `neashton/drivaerml` at immutable revision
`7a5c0948ce27be709b1116a3a190f806e7a8f79f`. Resolve every case and multipart
file from [`proposal/native-source-pin.json`](proposal/native-source-pin.json),
not from directory discovery or a presumed run-number range.

For each evaluated case:

1. Read `run_N/boundary_N.vtp` without remeshing or triangulating it. Predict
   scalar `pMeanTrim` and three-component `wallShearStressMeanTrim` as native
   polygon `CellData` in zero-based raw VTK cell order.
2. Byte-concatenate the pinned `.00.part`, `.01.part`, and optional `.02.part`
   files in that exact order, with no delimiter or transformation. Ten cases
   have three parts. A seekable segmented reader may present the same logical
   bytes without writing a roughly 50 GB reconstructed VTU.
3. Read the reconstructed unstructured grid without remeshing. Predict scalar
   `pMeanTrim` and three-component `UMeanTrim` for every native volume
   `CellData` cell in zero-based raw VTK cell order.

Surface pressure and wall shear are kinematic quantities in `m^2/s^2`.
Volume pressure is in `m^2/s^2`, velocity is in `m/s`, coordinates are in
metres, and fixed surface weights are in `m^2`.

## 3. Use bounded native-cell chunks correctly

Inference chunks are independent of multipart byte-transport parts. A
prediction chunk contains a contiguous half-open raw-cell interval and the
corresponding fields. Across a case, the intervals must exactly partition
`[0, native_cell_count)` with no gap, overlap, duplicate, omission, remapping,
or extrapolation.

The candidate local evaluator accepts one manifest per case and support. Each
manifest identifies its count and SHA-256-bound NPZ chunks. Every NPZ contains
signed-int64 `raw_cell_id` and exactly these Float32 or Float64 arrays:

| Support | Required arrays |
| --- | --- |
| `surface_native_cells` | `pMeanTrim: [N]`, `wallShearStressMeanTrim: [N,3]` |
| `volume_native_cells` | `pMeanTrim: [N]`, `UMeanTrim: [N,3]` |

For bounded validation, each NPZ chunk may contain at most 512 MiB across the
sum of all archive members' declared uncompressed byte sizes; this is not a
limit on the compressed archive size. Both ZIP `ZIP_STORED` and `ZIP_DEFLATED`
compression are accepted. Its ZIP central directory may be at most 64 KiB and
each NPY header at most 4,096 bytes. Use C-contiguous, non-object arrays; split
larger predictions into more contiguous raw-cell intervals.

Chunking must not change a metric. For each complete case, add the weighted
squared-error numerator, weighted truth-square denominator, weighted absolute
error, entity count, and total weight across chunks. Apply square roots and
division only after the complete case is represented. Never average
chunk-local relative-L2, MAE, or RMSE values.

The primary surface metrics use the fixed published same-order polygon areas;
equal-polygon metrics are mandatory secondary values. The primary volume
metrics weight every native cell equally; no geometric cell-volume array or
volume-weighted secondary metric is required. The evaluator audits, but never
regenerates, the fixed surface-area inputs.

## 4. Let the evaluator derive engineering diagnostics

Submit native fields rather than hand-calculated force or profile values. The
candidate evaluator integrates submitted surface pressure and wall shear to
derive `Cd`, `Cl`, `CmPitch`, and report-only `Clf`/`Clr`. After activation, the
owner-approved frozen evaluator will use the approved mappings to derive
AutoCFD5 velocity profiles and Cp probes. This ensures truth and predictions use
the same geometry, raw IDs, force convention, validity masks, and reductions.

The current candidate definitions contain 16 velocity lines and 209 unique Cp
probes. All-case velocity mappings and their resolution study are still
pending. The candidate Cp sweep covers all 484 cases, but retains 875 explicit
invalid rows and is awaiting owner visual review and disposition. Neither
candidate mapping is immutable scoring support; contributors must not invent
their own replacements for official scoring.

## 5. Install and run the candidate tools

The generic repository checks use `requirements.txt`. The VTK-based DrivAerML
surface, force, Cp, and velocity geometry workflows use the exact optional stack in
[`requirements-drivaerml-evaluator.txt`](../../requirements-drivaerml-evaluator.txt):
Python 3.12.13, NumPy 2.2.6, and VTK 9.5.2. Those VTK geometry generators check
their declared versions; a different Python patch release is not compatible
with their evidence receipts. The bounded XML equal-cell volume audit does not
invoke VTK or compute cell volumes: it records its Python/NumPy runtime for
provenance, while the strict aggregate validates the v2 schema and source
identities. Use the exact optional stack when reproducing the complete candidate
evidence workflow.

```bash
python3.12 --version  # must print: Python 3.12.13
python3.12 -m venv .venv-drivaerml
.venv-drivaerml/bin/pip install -r requirements-drivaerml-evaluator.txt
.venv-drivaerml/bin/python -c \
  'import platform,numpy,vtk; print(platform.python_version(), numpy.__version__, vtk.vtkVersion.GetVTKVersion())'
# must print: 3.12.13 2.2.6 9.5.2
```

Run the small two-part/three-part teaching fixture with one command:

```bash
.venv-drivaerml/bin/python examples/drivaerml-candidate-native-chunks/reference_driver.py \
  --output /tmp/drivaerml-candidate-native-chunk-demo
```

The fixture is synthetic and explicitly ineligible. It proves ordered two- and
three-part byte concatenation, raw-ID chunk coverage, additive reduction,
full-versus-chunked invariance, and schema-v3 prediction/case-metric artifact
validation. Its small transport payloads are JSON, not VTK; it does not claim a
real DrivAerML reconstruction, result, or official scoring support.

The command performs the fixture's schema-v3 checks itself. Its deliberately
unregistered `synthetic-drivaerml-shaped` namespace is not accepted by the
repository's official-dataset semantic validator. That validator must remain
fail-closed for real DrivAerML packages until the owner activates the contract.

For a real case, first create or obtain candidate surface and volume prediction
manifests. The zero-field generator is a transport test only, never a model or
published baseline:

```bash
.venv-drivaerml/bin/python scripts/create_drivaerml_dummy_predictions.py \
  --case-id run_1 \
  --surface-count 8828095 \
  --volume-count 147449586 \
  --max-chunk-rows 1000000 \
  --output-root /tmp/drivaerml-run1-zero
```

The real-case interface consumes the actual native surface and reconstructed
volume plus prediction manifests. Volume errors are accumulated with one equal
weight per raw native cell:

```bash
.venv-drivaerml/bin/python scripts/evaluate_drivaerml_candidate_case.py \
  --case-id run_1 \
  --native-source-pin benchmark-specs/drivaerml/proposal/native-source-pin.json \
  --dataset-root /path/to/drivaerml \
  --monolithic-vtu /path/to/drivaerml/run_1/volume_1.vtu \
  --surface-area-npy /path/to/run_1/boundary_cell_area_1.npy \
  --surface-prediction-manifest /path/to/surface/manifest.json \
  --volume-prediction-manifest /path/to/volume/manifest.json \
  --output /tmp/run_1-candidate-evidence.json
```

Use `--multipart` instead of `--monolithic-vtu` when the pinned part files are
present below `--dataset-root`. The evaluator verifies raw native-cell coverage
and accumulates equal-cell sufficient statistics directly; participants do not
supply a geometric volume-weight file.

For the real two-case pilot, copy the example configuration and run
[`real_reference_driver.py`](../../examples/drivaerml-candidate-native-chunks/real_reference_driver.py).
It admits exactly pinned `run_1` and `run_44`, always uses their two- and
three-part streams respectively, calls the same core and diagnostic evaluator
entry points, and writes candidate evidence only. It never downloads data,
generates scientific support, or creates a submission.

## 6. Package through schema v3 only after activation

The candidate tools produce deterministic local evaluation evidence, not an
official `submission.json`. Once the owner publishes immutable official
scoring support and opens DrivAerML submissions, package the selected split,
model/checkpoint provenance, case evidence, profiles, and a revision-pinned
complete-split scored-prediction artifact through the repository's normal
schema-v3 contributor process. The official evaluator release IDs and hashes
must match exactly.

Contributors declare a revision-pinned, complete-split `scored_predictions`
artifact but do not create `prediction-artifact-checks.json`. A maintainer must
replay the native evaluator over that artifact and add the check: it binds the
exact case-metrics file, ordered force/velocity/Cp values, evaluator version
and code revision, and complete case count. Final validation also requires that
revision to match the benchmark-owned frozen evaluator binding exactly; the
candidate binding is deliberately still pending and has no frozen revision.
The later approval record hashes that maintainer-owned check. A
participant-edited scalar or receipt therefore fails validation. No genuine
full-split DrivAerML receipt exists yet.

Until then, use this workflow for implementation feedback and reproducibility
review only. Do not describe a candidate dry run as an accepted submission,
independent participant validation, or owner scientific approval.
