# WindsorML schema-v3 candidate workflow

Use the current upstream **`dev`** branch. This workflow packages genuine model
inference for development review; official intake remains closed. Read the
[data, split and physics contract](../../benchmark-specs/windsorml/README.md)
first. Daniel's end-to-end trial is to run this workflow with his own model and
checkpoint on one complete declared split, then open a PR targeting `dev`.

## 1. Configure the actual method

```bash
python -m pip install -r requirements.txt
cp examples/windsorml-v3-candidate/package-config.template.json /path/to/package-config.json
```

Replace every `__REPLACE_...__` value with actual method, training, compute,
checkpoint, and spatial discretization records. Use a new globally unique
submission ID. Keep the supplied release bindings unchanged. Declare every
checkpoint actually loaded; the assembler checks its local bytes against the
methodology SHA-256. Publishing checkpoint files is optional.

```bash
python scripts/assemble_windsorml_schema_v3_candidate.py \
  --config /path/to/package-config.json --list-unresolved
```

The inference attestation must be accurate: all prediction values must come
from the declared model inference, without generating them from evaluation
truth. Validation verifies artifacts and declarations; it does not prove that
the model was executed.

## 2. Predict and evaluate every required case

Read the ordered list from `benchmark-specs/windsorml/splits/<split-id>.json`.
The `full` test set has **35** available cases, not 36. Produce predictions for
every original surface point and volume cell in native source order.

Use one prediction manifest per case and domain. Each has this structure
(shown for surface; replace symbolic values with actual counts and digests):

```json
{
  "format": "windsorml-native-prediction-chunks-candidate",
  "format_version": 1,
  "artifact_role": "local_evaluator_input_not_official_submission_artifact",
  "case_id": "run_7",
  "support_id": "windsorml_surface_native_points",
  "association": "PointData",
  "total_row_count": "ACTUAL_NATIVE_POINT_COUNT",
  "field_components": {"cpavg": 1, "cfxavg": 1, "cfyavg": 1, "cfzavg": 1},
  "chunks": [{
    "chunk_index": 0, "file": "chunk-00000.npz", "sha256": "ACTUAL_FILE_SHA256",
    "row_count": "ACTUAL_CHUNK_ROWS", "raw_cell_id_start": 0,
    "raw_cell_id_stop": "EXCLUSIVE_STOP"
  }]
}
```

NPZ chunks contain `raw_cell_id` (int64) and each named scalar prediction field
(float32 or float64). Despite its historical name, `raw_cell_id` indexes
**points for surface** and **cells for volume**. Use consecutive IDs starting
at zero, contiguous non-overlapping chunks, at most 1,000,000 rows per chunk,
and complete coverage. For volume use support `windsorml_volume_native_cells`,
association `CellData`, and scalar fields `velocityxavg`, `velocityyavg`,
`velocityzavg`, `pressureavg`. Prediction manifests and NPZ files stay local;
the package retains their hashes.

Run once per required case:

```bash
python scripts/evaluate_windsorml_candidate_case.py \
  --case-id run_7 --dataset-root /path/to/windsorml \
  --surface-manifest /path/to/predictions/run_7/surface/manifest.json \
  --volume-manifest /path/to/predictions/run_7/volume/manifest.json \
  --output /path/to/evidence/run_7.json
```

The CLI automatically loads the pinned source identity and profile support.
It checks complete native coverage and derives field metrics, forces, and all
fixed and relative profiles. No manually supplied truth manifest or generated
support sidecars are needed for evaluation.

Optionally retain the split reduction:

```bash
python scripts/score_windsorml_candidate_dataset.py \
  --split-id full --case-evidence-directory /path/to/evidence \
  --output /path/to/dataset-evidence.json
```

## 3. Assemble and validate

Create one discretization JSONL record per case, in exact split order, with
actual inference input, direct-output and mapping counts. Follow
[`discretization-case.schema.json`](../../schemas/v3/discretization-case.schema.json)
and the [spatial record reference](../../docs/RESULT_FORMAT.md).
The package-config `spatial_discretization` contains the corresponding training
and inference summaries. Include mappings for both native supports, force
support `windsorml-force-coefficients-v1`, and all four family IDs from
`profile-definition-v2.json`. Profiles and forces are evaluator-derived mappings
from the surface or volume output; all support coverage must equal 1.

```bash
python scripts/assemble_windsorml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --case-evidence-directory /path/to/evidence \
  --discretization-cases /path/to/cases.jsonl \
  --checkpoint my-model=/path/to/model.pt \
  --output submissions/windsorml/windsorml-my-model-full-v1

python scripts/validate_submission.py --dev-intake --contributor-stage \
  submissions/windsorml/windsorml-my-model-full-v1
```

Use one `--checkpoint ID=PATH` for each actual checkpoint ID in the method
record. Optional `--dataset-evidence` must equal a fresh reduction. The assembler
always recomputes the split metrics and binds profiles, sufficient statistics,
discretization, and evaluation evidence; never hand-edit generated hashes.
It refuses an existing output directory, leaving earlier results intact.

The assembler automatically downloads and verifies the global profile-truth
manifest pinned by `leaderboard/manifest.json`. For offline use:

```bash
python scripts/fetch_profile_ground_truth.py --output /path/to/profile-truth-manifest.json
```

Transfer those unchanged bytes and pass
`--profile-ground-truth-manifest /path/to/profile-truth-manifest.json` during
assembly. The compact prediction package contains 16 series per case, with
exact native-derived coordinates and 128 predictions per series.

## 4. Open the development PR

Commit only `submissions/windsorml/<new-submission-id>/` and target **`dev`**.
Do not add approval metadata, edit the registry, or regenerate feeds. CI chooses
`--dev-intake` for a PR targeting `dev`. Passing intake allows review and merge
without altering the contributor's package. It does not publish a row.

## 5. Maintainer: show the reviewed result on dev

After reviewing Daniel's real-model package, inspect and register its exact
binding, then regenerate the feed:

```bash
python scripts/register_windsorml_pre_release.py \
  submissions/windsorml/windsorml-my-model-full-v1/submission.json
python scripts/register_windsorml_pre_release.py --register \
  submissions/windsorml/windsorml-my-model-full-v1/submission.json
python scripts/manage_leaderboard.py build --dev-intake
python scripts/manage_leaderboard.py check --dev-intake
```

Commit the registry and generated feeds in a maintainer PR to `dev`. The review
leaderboard reads submission `dev` automatically. The row is a pre-release
reference, without citation or promotion eligibility. No production release
or official approval is created. Changed package bytes invalidate registration.
Confirm the row, six field errors, force metrics, and all fixed/relative profile
comparisons in the dev viewer. This publication step is normal review, not a
manual repair of the submitted files.
