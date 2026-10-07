# AirfRANS FluidsBench schema-v3 candidate package

This directory holds the config template for assembling an AirfRANS
schema-v3 candidate submission, plus one concrete example
(`transolverpp-full-v1-candidate-config.json`) used to build the
`transolverpp-full-v1` package under `submissions/airfrans/`.

AirfRANS remains closed for real submissions
(`benchmark-specs/airfrans/submission-spec.json` has
`scoring_support.status: owner_review_required` and
`submissions_open: false`), so nothing built with this tooling is an
accepted result. `scripts/validate_submission.py --contributor-stage`
will still report failures tracing back to that closed status (missing
official scoring-support manifest binding, dataset not marked
`"official"`, no leaderboard entry for the profile ground truth) — all
three require dataset-owner action before these candidates can be accepted.

The registered dev references now bind the verified candidate profile-truth
release `airfrans-native-profile-truth-v1-candidate`, rather than the extraction
definition. Their configs carry the same immutable manifest SHA-256.
The assembler still rejects definition-based ground-truth bindings.
[The pre-release registration](../../benchmark-specs/airfrans/pre-release/README.md)
records the downloaded artifact checks, reproduced profile scores and exact
package hashes. It permits unranked dev inspection while official intake stays
closed. Submitter attribution and CC-BY-4.0 are retained as confirmed in the PR
handover. Submitted metrics and profile predictions are unchanged.

## Pipeline

Predictions become a candidate package in four steps. The first two
need the pinned `airfrans`/PyVista/VTK stack
(`requirements-airfrans-evaluator.txt`); the third is pure numpy and
reuses the repository's generic evaluator; the fourth is packaging only.

### 1. Ground-truth scoring support (once per dataset, not per model)

```bash
python scripts/build_airfrans_scoring_support.py \
  --dataset-root /path/to/AirfRANS/Dataset \
  --output /path/to/airfrans-native-ground-truth-v1-candidate
```

For every case in the official split, computes point-dual physical
weights (`reference/airfrans/geometry.py`: mass-lumped dual-cell area on
the 2D domain, dual-segment length on the airfoil curve — the first use
of point-dual weighting in this repo, since every other dataset
publishes cell-associated fields instead) alongside the ground-truth
velocity, pressure, wall shear, and forces, all read directly from the
pinned `airfrans` library. No prediction is involved, so this release
is reusable across every future AirfRANS submission. It is large
(hundreds of MB for the Full split); keep it outside the repository,
the way the produced `transolverpp-full-v1-candidate-config.json`
example does.

### 2. Per-submission field derivation (once per model)

```bash
python scripts/derive_airfrans_predicted_fields.py \
  --dataset-root /path/to/AirfRANS/Dataset \
  --predictions-dir /path/to/packed-model-predictions \
  --scoring-support-manifest /path/to/airfrans-native-ground-truth-v1-candidate/manifest.json \
  --submission-id my-model-full-v1 \
  --output /path/to/my-model-predicted-fields
```

Injects the model's predicted velocity/pressure into the same
`airfrans.Simulation` object used for ground truth and lets the library
compute the same derived quantities (wall shear, forces, curve
pressure) from the prediction. `--predictions-dir` expects one
`<case_id>.npz` per case with `velocity`, `pressure`,
`internal_points`, and `airfoil_points` arrays in unchanged native
point order. `pack_native_predictions.py` in this directory is a
template for producing them: only its `load_raw_prediction` function is
model-specific, and it stops (rather than interpolating) if the model's
points are not in native order. Writes a `kind: scored_predictions`
manifest directly consumable by `reference.evaluate_predictions`.

### 3. Metric scoring

```bash
python scripts/finalize_airfrans_metrics.py \
  --support-manifest /path/to/airfrans-native-ground-truth-v1-candidate/manifest.json \
  --case-set standard \
  --prediction-manifest /path/to/my-model-predicted-fields/manifest.json \
  --submission-id my-model-full-v1 \
  --split-id full \
  --profile-score /path/to/velocity-profile-score.json \
  --output /path/to/metrics-cases.json
```

This calls the repository's existing generic evaluator
(`reference/evaluate_predictions.py`), which already implements every
reduction AirfRANS needs (relative-L2/L1, per-geometry-then-macro-average,
and the all-test-cases R²/MAE aggregation the force metrics use) —
nothing AirfRANS-specific was added there. `finalize_airfrans_metrics.py`
only adds what that generic pipeline can't know on its own: it folds in
`velocity_profile_r2` (from the existing
`examples/airfrans-profile-extraction/extract.py` + `score.py`
pipeline) and computes the composite scores
(`overall_score`/`field_score`/`force_score`/`diagnostic_score`) from
`benchmark-specs/airfrans/submission-spec.json`'s own declarations.

### 4. Package assembly

Copy `package-config.template.json` outside the repository and replace
every `__REPLACE_WITH_...__` token with the submitted method's real
methodology (architecture, parameter counts, training/checkpoint
details, measured compute) and submitter identity.

Set `release_bindings.profile_ground_truth.release_id` and `manifest_sha256`
from the actual profile ground-truth release manifest used for scoring.
`submission-spec.json#profile_definition` describes how to extract profiles;
its ID and hash cannot be used as the ground-truth release binding.

List what's still unresolved without writing output:

```bash
python scripts/assemble_airfrans_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --list-blockers
```

Once resolved, assemble the package and run the repository validator:

```bash
python scripts/assemble_airfrans_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --scoring-support-manifest /path/to/airfrans-native-ground-truth-v1-candidate/manifest.json \
  --metrics-cases /path/to/metrics-cases.json \
  --predicted-profiles-dir /path/to/predicted-profiles \
  --profile-score /path/to/velocity-profile-score.json \
  --output submissions/airfrans/my-model-full-v1

python scripts/validate_submission.py --contributor-stage submissions/airfrans/my-model-full-v1
```

The assembler writes `submission.json`, `evaluation-evidence.json`,
`discretization.json` + `discretization/cases.jsonl`,
`metrics/cases.json`, and `profiles/index.json` + per-case chunks. It
never writes `approval`, `maintainer-validation.json`, or
`prediction-artifact-checks.json` — those are maintainer-only records.

### Rescoring after a scoring-specification change

When `submission-spec.json` changes its composite weights and
`evaluation_reference_version`, an assembled package keeps valid base
metrics but carries stale derived scores. Regenerate only the derived
values (`overall_score` and the group scores) and their hashes, without
re-running inference or the evaluator:

```bash
python scripts/rescore_airfrans_candidate.py --check --package-dir submissions/airfrans/my-model-full-v1
python scripts/rescore_airfrans_candidate.py --package-dir submissions/airfrans/my-model-full-v1
```

The validator also requires the scoring-support manifest to carry the
spec's `evaluation_reference_version`. If the manifest has been re-stamped
for the new version, add `--scoring-support-manifest
/path/to/<release>/manifest.json` to rebind its SHA-256 in
`discretization.json`, `metrics/cases.json`, `evaluation-evidence.json` and
`submission.json`.

The script refuses a package whose metric values or hashes disagree, and
leaves every base metric, per-case record and profile unchanged.

### Profile-truth release (maintainer step)

The ground-truth profiles behind `velocity_profile_r2` are packaged once, as a
candidate profile-truth release in the HiLiftAeroML layout (manifest, master
index, case records, chunks, one thin index per split, provenance and
receipt). Cases shared by several splits are stored once, and each truth file
is kept byte for byte as written by
`examples/airfrans-profile-extraction/extract.py`:

```bash
python scripts/export_airfrans_profile_truth.py \
  --source full=/path/to/full/reference-profiles \
  --source aoa_extrapolation=/path/to/aoa/reference-profiles \
  --scoring-support-manifest full=/path/to/airfrans-native-ground-truth-v1-candidate/manifest.json \
  --scoring-support-manifest aoa_extrapolation=/path/to/airfrans-native-ground-truth-aoa-v1-candidate/manifest.json \
  --extractor-commit <commit of the extract.py that produced the truth> \
  --output /path/to/airfrans-native-profile-truth-v1-candidate

python scripts/validate_airfrans_profile_truth.py \
  --release /path/to/airfrans-native-profile-truth-v1-candidate \
  --source-replay --dataset-root /path/to/AirfRANS/Dataset --python /path/to/eval-env/bin/python
```

Rerun the exporter with `--check` to compare every byte of an existing
release. Packaging does not publish the release or open submissions.
