# DrivAerML candidate participant guide

This guide describes the proposed native-mesh workflow for AutoCFD and
FluidsBench contributors. The contract is still a closed candidate:
`submissions_open` is `false`. The bounded composite equation is active and can
produce implementation-feedback scores, but no package made with these
instructions is an official leaderboard submission yet.

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

## 4. Run the reference evaluator locally

Use the candidate evaluator for implementation feedback now and, after
activation, run the exact owner-approved frozen evaluator locally. Do not
substitute hand-calculated force conventions or independently defined profile
extraction. The evaluator integrates the participant's native surface pressure
and wall shear to produce per-case `Cd`, `Cl`, `CmPitch`, and report-only
`Clf`/`Clr`, together with their submitted metrics. It uses the approved
mappings and extraction support to produce the complete JSON series for the 16
AutoCFD5 velocity profiles and the four FluidsBench continuous Cp cuts. Include
those derived coefficients, metrics, and profile series in the submission
package. This keeps truth and predictions on the same geometry, raw IDs, force
convention, validity masks, and reductions.

For schema v3, each case in `metrics/cases.json` carries the evaluator-produced
prediction object `force_coefficients` with exactly `cd`, `cl`, `cm_pitch`,
`clf`, and `clr`. The first three are ranked independently; `clf` and `clr` are
report-only closure evidence.

`force_mom_constref_all.csv` is the canonical force-truth table. The per-case
`run_N/force_mom_constref_N.csv` files remain supported mirrors only after the
evaluator proves that each row agrees exactly with the aggregate table. This
does not change any target value or score; it provides one hash-bound source of
truth while retaining the per-case files for convenient local processing.

The submission-facing
[`drivaerml-diagnostics-v9.json`](drivaerml-diagnostics-v9.json) registry contains 16
velocity lines and four continuous Cp cuts: upperbody centreline (`y=0`),
underbody centreline (`y=0`), sidewall (`z=0.15 m`), and front-left wheelhouse
(`y=-0.6 m`). All-case velocity mappings and their resolution study are still
pending. Exact immutable native extraction support for the four Cp cuts is also
pending. Contributors must not invent replacements for either official
support.

The four continuous Cp cuts remain a ranked component with composite weight
0.10; the velocity profiles retain weight 0.15. The evaluator derives every cut
from native surface `pMeanTrim`. Participants therefore do not add a Cp-cut
field to the VTP or predict a second Cp representation, but they do submit the
evaluator-produced Cp-cut coordinate and prediction arrays in the normal
FluidsBench profile JSON.

The ranked profile metrics are global R2 values, not macro-averaged RMSE. Each
case and each required line or cut receives equal total weight. Within a
velocity line, samples use normalized trapezoidal arc-length support; within a
Cp cut, samples use normalized native intersection-segment-length support. A
single global weighted truth mean is then used for each profile family. This
prevents the 651-sample L1 velocity line from outweighing a 31-sample R line.
The corresponding equal-case/equal-line and equal-case/equal-cut RMSE values
remain report-only diagnostics.

The four field components use fixed bounded-error caps of 15% for surface
pressure, 20% for wall shear, 12% for volume velocity, and 15% for volume
pressure. `Cd`, `Cl`, `CmPitch`, velocity-profile, and Cp-cut R2 use bounded
quality scores `100 * clip(R2, 0, 1)`. The nine weights total 50% fields, 25%
forces, and 25% profiles.

Only the 209 discrete Cp probes are excluded. Participants do not submit probe
outputs, probe mappings, or probe-specific support, and no discrete-probe
metric is calculated. The combined v8 registry and existing 209-probe files in
the proposal and evidence directories are retained only as inactive,
non-normative research records.

Participants run the evaluator over their complete native `UMeanTrim`
prediction and do not create or modify velocity-profile validity masks. The
frozen evaluator will apply the owner-published mask and containing-cell
assignments and emit the JSON profile series to include in the package. Only
`inside_morphed_solid` and `outside_released_fluid_domain` are permitted owner
exclusion reasons. An unresolved containing-cell or cell-evaluation failure is
not an automatic exclusion: it makes the required line unavailable until the
support is corrected. Owner-excluded coordinates remain explicit and remove
only their point and adjacent trapezoidal edges; gaps are never bridged. No
mask has yet been approved, so the current candidate evaluator conservatively
makes a velocity result unavailable when a mapping row is invalid.

## 5. Install and run the candidate tools

The complete native-VTK candidate evaluator is currently supported on Linux
only, including Linux HPC nodes and Linux containers or WSL. Its retained-file
protections rely on Linux descriptor-filesystem semantics and are not yet
validated on native macOS or Windows. JSON/schema and profile-package checks
may run on other platforms, but official evaluator evidence must be generated
on Linux until cross-platform support is implemented and tested.

The generic repository checks use `requirements.txt`. The exact recommended
stack for the complete VTK-based DrivAerML evidence workflow is defined in
[`requirements-drivaerml-evaluator.txt`](../../requirements-drivaerml-evaluator.txt):
Python 3.12.13, NumPy 2.2.6, and VTK 9.5.2. Runtime enforcement differs by
workflow. Velocity-assignment generation rejects a Python, NumPy, or VTK
version mismatch. The native-surface reader rejects a VTK version other than
9.5.2, and its evidence records the dependency identities available to that
path. Force replay records its Python, NumPy, and VTK versions but does not
reject a different Python patch or NumPy version. The bounded XML equal-cell
volume audit does not invoke VTK or compute cell volumes; it records its
Python/NumPy runtime for provenance, while the strict aggregate validates the
v2 schema and source identities. Use the exact recommended stack when
reproducing the complete candidate evidence workflow.

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
three-part byte concatenation, raw-ID chunk coverage, additive reduction, and
full-versus-chunked invariance for the two surface and two volume fields. Its
dummy schema-v3 package mirrors the current participant shape: area-weighted
and equal-polygon surface metrics, equal-cell volume metrics, coherent force
coefficients, all four Cp cuts, all sixteen AutoCFD5 velocity profiles, and all
32 non-score candidate metrics. Its small transport payloads and support
tables are JSON, not VTK, and its force/profile values are synthetic; it does
not claim real DrivAerML extraction, force integration, reconstruction, model
results, or official scoring support.

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

For a complete selected split, the dataset reducer writes both the case metrics
and the standard profile chunks from the participant's evaluator evidence:

```bash
.venv-drivaerml/bin/python scripts/score_drivaerml_candidate_dataset.py \
  --split-id <official-split-id> \
  --core-evidence-dir /path/to/core-case-evidence \
  --diagnostic-evidence-dir /path/to/diagnostic-case-evidence \
  --force-truth /path/to/force_mom_constref_all.csv \
  --output /path/to/package/evaluation-evidence.json \
  --schema-v3-case-metrics-output /path/to/package/metrics/cases.json \
  --schema-v3-profile-output-dir /path/to/package/profiles \
  --submission-id <submission-id> \
  --candidate-support-release-id <published-candidate-release-id> \
  --candidate-support-manifest-sha256 <64-character-sha256>
```

Profile packaging fails closed unless every test case contains all four Cp-cut
series followed by all 16 velocity-profile series. While the Cp-cut extraction
support remains unpublished, this command may produce candidate dataset and
case-metric evidence but must refuse the complete profile output; it never
fills missing curves with placeholders.

## 6. Package through schema v3 only after activation

The candidate tools produce deterministic local evaluation evidence, not an
official `submission.json`. Once the owner publishes immutable official
scoring support and opens DrivAerML submissions, run the frozen evaluator and
package the selected split, model/checkpoint provenance, per-case force
coefficients and metrics, complete profile JSON, case evidence, and aggregate
metrics through the repository's normal schema-v3 contributor process. The
profile JSON must cover every required case and contain all 16 velocity series
and all four continuous Cp-cut series. The official evaluator and support
release IDs and hashes must match exactly.

Sharing complete native prediction fields is optional under the repository's
normal reproducibility policy. If a contributor shares them, the declaration
must use a revision-pinned artifact and a hash-bound manifest. A maintainer may
optionally audit or recompute values from that artifact and record the result in
maintainer-owned metadata. Participants must not create or edit
`prediction-artifact-checks.json` or `maintainer-validation.json`. Neither a
shared native-field artifact nor a maintainer recomputation is a participant
submission requirement or an activation gate; the submitted JSON generated by
the frozen evaluator remains the required result payload.

Until then, use this workflow for implementation feedback and reproducibility
review only. Do not describe a candidate dry run as an accepted submission,
independent participant validation, or owner scientific approval.
