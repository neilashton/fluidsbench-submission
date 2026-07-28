# Reference metric implementation

Participants own model inference, prediction dimensionalisation, any mapping from their native output to the canonical scoring
locations, and profile extraction. Benchmark-owned scoring-support files provide the exact ground-truth arrays, coordinates,
weights, and stable IDs used in the final comparison. [`evaluate_predictions.py`](evaluate_predictions.py) implements the bound
field, scalar, cross-case, and dataset-reference reductions after predictions have been joined to that support. It does not
prescribe a model's native input or output format.

## Fixed scoring support

For a schema-v3 result, the selected dataset specification points to one immutable, owner-approved scoring-support release. Its
hash chain defines the public case set and, for each support, the exact stable IDs, coordinates, physical weights, quantities,
components, ground-truth values, and coverage and extrapolation rules used for scoring.

The submitter creates keyed predictions and maps any native model output to those benchmark support IDs. The reference evaluator
uses benchmark-owned coordinates, weights, and ground truth, rejects missing, duplicate, or unknown IDs, and then writes
`metrics/cases.json`. It does not interpolate or resample either side of the comparison. Any interpolation, nearest-neighbour
transfer, projection, or direct query needed to reach the support must therefore happen in the submitter's evaluation code and be
declared in `discretization.json`.

The generic loader and synthetic executable example are in [`scoring_support.py`](scoring_support.py) and
[`evaluate_predictions.py`](evaluate_predictions.py). The loader currently handles safe local `materialized_table` JSON, CSV, and
NPZ artifacts; an official release may provide a reviewed dataset-specific implementation for another declared location mode.

```bash
python3 -m reference.evaluate_predictions \
  --support-manifest examples/v3-template/support/manifest.json \
  --case-set standard \
  --prediction-manifest examples/v3-template/predictions/manifest.json \
  --submission-id synthetic-open-model-v1 \
  --split-id default \
  --output /tmp/fluidsbench-synthetic-case-metrics.json
```

The evaluator follows each binding's published aggregation rule. Ordinary L1, L2, MAE, MSE, and RMSE field metrics produce
per-case evidence and are macro-averaged when the contract says so. Global R2 and the benchmark field/scalar RRMSE rules are
calculated from the complete cross-case arrays and are marked `aggregate_only`, so no misleading per-case surrogate is emitted.
The output also contains support counts, count and weight coverage, and unmapped and extrapolated counts. The repository validator
requires exact official case and support coverage and recalculates macro-averages from submitted per-case evidence. Aggregate-only
values remain submitter-created values bound to the exact rule and support release. Required approval validates the submitted
package but does not execute the model or regenerate its predictions.

Before approving a scoring-support proposal, a dataset owner can validate its local manifest, case-set index, chunks, artifact
paths and hashes, identities, support coverage, and normalized support digests with:

```bash
python3 -m reference.scoring_support \
  --manifest benchmark-specs/<dataset-id>/scoring-support/<release-id>/manifest.json \
  --case-set <case-set-id>
```

The command prints `PASS` only after the complete local chain has loaded successfully. Dataset-owner approval and the
`submission-spec.json` status change to `official` remain explicit review decisions; this command does not make that policy change.
The repository-wide `python3 scripts/validate_scoring_supports.py` gate additionally checks that every official manifest binds
exactly the executable metrics in its dataset specification. Releases using remote artifacts or a dataset-specific loader must
also commit a `publication_validation` receipt that pins the validator file and digest, manifest digest, normalized-support digest,
validated case/support counts, reviewer, timestamp, and approving pull request.

## Common equations

For ground truth \(y_i\), prediction \(\hat y_i\), and non-negative physical weights \(w_i\):

\[
\operatorname{MSE}_w = \frac{\sum_i w_i(\hat y_i-y_i)^2}{\sum_i w_i}
\]

\[
\operatorname{MAE}_w = \frac{\sum_i w_i |\hat y_i-y_i|}{\sum_i w_i}
\]

\[
\operatorname{RMSE}_w = \sqrt{\frac{\sum_i w_i(\hat y_i-y_i)^2}{\sum_i w_i}}
\]

\[
L_{1,\mathrm{rel}}(\%) = 100\frac{\sum_i w_i|\hat y_i-y_i|}{\sum_i w_i|y_i|}
\]

\[
L_{2,\mathrm{rel}}(\%) = 100\frac{\sqrt{\sum_i w_i(\hat y_i-y_i)^2}}{\sqrt{\sum_i w_i y_i^2}}
\]

\[
R^2_w = 1-\frac{\sum_i w_i(y_i-\hat y_i)^2}{\sum_i w_i(y_i-\bar y_w)^2},\qquad
\bar y_w=\frac{\sum_iw_i y_i}{\sum_iw_i}
\]

Surface metrics use face-area weights and volume metrics use cell-volume weights when those physical measures are part of the
dataset contract. Coefficient metrics normally use equal case weights. Dataset specifications state whether a metric is computed
globally or per geometry followed by a macro-average. Macro-averaging is the default for field metrics so each test geometry has
equal influence regardless of mesh resolution.

For per-geometry values \(m_k\), the macro-average over \(K\) test geometries is:

\[
\bar m = \frac{1}{K}\sum_{k=1}^{K}m_k
\]

Vector quantities must include every declared component. Apply the same physical weight to each component and flatten the
component axis before evaluating the norm unless the dataset specification states another reduction.

Inputs must be dimensional where the metric unit is dimensional. The functions reject empty arrays, non-finite numbers, negative
weights, zero total weight, zero relative-error denominators, and constant-ground-truth R2 rather than silently inventing a value.

VKI-LS59 and Rotor37 additionally use the following benchmark-specific RRMSE equations. For field case \(k\) with
\(N_k\) values:

\[
\operatorname{RRMSE}_{field} = \sqrt{\frac{1}{K}\sum_{k=1}^{K}
\frac{\lVert\hat{\mathbf y}_k-\mathbf y_k\rVert_2^2/N_k}{\lVert\mathbf y_k\rVert_\infty^2}}
\]

For scalar outputs:

\[
\operatorname{RRMSE}_{scalar} = \sqrt{\frac{1}{K}\sum_{k=1}^{K}
\frac{|\hat y_k-y_k|^2}{|y_k|^2}}
\]

## Benchmark scores

[`scores.py`](scores.py) implements the prototype external-aerodynamics score and arithmetic aggregate used by the turbine
datasets and BlendedNet. For the four field errors \(e_j\), caps \(c_j=(15,20,12,15)\), and weights
\(w_j=(0.15,0.10,0.15,0.10)\):

\[
S_{field}=\frac{\sum_j w_j\,\operatorname{clip}(100(1-e_j/c_j),0,100)}{0.50}
\]

\[
S_{force}=\frac{0.15\,\operatorname{clip}(R^2_{C_D},0,1)100+
0.10\,\operatorname{clip}(R^2_{C_L},0,1)100}{0.25}
\]

\[
S_{profile}=\frac{0.15\,\operatorname{clip}(R^2_{velocity},0,1)100+
0.10\,\operatorname{clip}(R^2_{C_p},0,1)100}{0.25}
\]

\[
S_{overall}=0.50S_{field}+0.25S_{force}+0.25S_{profile}
\]

These score caps and weights remain prototype policy until the dataset owners approve them. Dataset-specific aggregate metrics use
the unweighted arithmetic mean of the exact source metric IDs listed in `submission-spec.json`.

Run the array-level example from the repository root with:

```bash
python3 -m reference.example_calculation
```
