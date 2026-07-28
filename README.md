# fluidsbench-submission

Submission repository and approved-data feed for the [FluidsBench leaderboard](https://fluidsbench.org/).

> FluidsBench is currently a work in progress. The `dev` branch, split indexes, submissions, metrics, and profile curves are
> prototype dummy data and are not approved benchmark results.

## Responsibilities

FluidsBench follows the versioned [`open-reproducibility-3.0`](OPEN_REPRODUCIBILITY.md) track. Evaluation ground truth and case
IDs are public. The submission process deliberately separates four responsibilities:

1. Dataset owners publish an immutable canonical scoring support: the exact public locations, weights, quantities, case set, and
   coverage rules used for comparisons.
2. Participants run their own model, create predictions, map them to that support, calculate per-case and aggregate metrics, and
   create the required profiles and spatial-discretization records. They also publish the exact source code, model artifact, locked
   environment, and artifact documentation.
3. Participants must run the FluidsBench contributor-stage validator before opening a pull request. Their package remains
   unapproved and is not included in the public feed.
4. A maintainer validates the submitted files, hash chain, exact case/support coverage, and metadata, then approves the package for
   publication.

FluidsBench does not execute the submitted code or model, regenerate predictions, or recompute base metrics from full prediction
fields as part of required approval. It plots and tabulates the submitter-created values and compares them with the fixed public
ground truth. Optional prediction sharing and optional maintainer checks are recorded separately and do not affect approval, rank,
citation eligibility, or promotion eligibility.

## Submission directory

Create one directory under the matching dataset:

```text
submissions/<dataset-id>/<submission-id>/
  submission.json
  evaluation-evidence.json
  discretization.json
  discretization/
    cases.jsonl
  metrics/
    cases.json
  prediction-artifact-checks.json # optional, maintainer-owned
  maintainer-validation.json   # added only by maintainers during approval
  profiles/
    index.json
    chunk-000.json
    chunk-001.json
```

Use lowercase letters, numbers, and hyphens for the globally unique `submission-id`. Do not edit generated files under
`leaderboard/` directly.

New submissions use schema v3. The material under [`examples/v3-template/`](examples/v3-template/) demonstrates the fixed-support
and prediction-manifest formats; dataset-specific submission templates can be completed only after the dataset owner marks its
scoring support `official` and opens submissions. Existing directories under `submissions/` are historical v1 prototype fixtures,
and [`examples/v2-template/`](examples/v2-template/) is retained only to interpret historical v2 packages.

## 1. Calculate metrics

Read the selected dataset's page on the [FluidsBench website](https://fluidsbench.org/datasets/) and its machine-readable
specification under [`benchmark-specs/`](benchmark-specs/). The specification lists accepted splits, required metric IDs, units,
directions, profile panels, stations, and quantities.

The equations, edge cases, fixed-support joins, and NumPy reference implementations are documented in
[`reference/README.md`](reference/README.md). Participants create keyed predictions using their own inference pipeline. The
reference evaluator joins those predictions to the benchmark-owned support IDs and fixed public ground truth, checks exact coverage,
and produces the metric evidence. Mapping or interpolation to the scoring support is part of the submitted evaluation pipeline, so
its error is included in the result.

```python
from reference.metrics import relative_l2

pressure_l2_percent = relative_l2(
    ground_truth_pressure,
    predicted_pressure,
    weights=surface_face_areas,
)
```

Run the executable reference example with:

```bash
python3 -m reference.example_calculation
```

## 2. Prepare metrics, spatial metadata, and profiles

`submission.json` contains model, submitter, training, dataset, split, aggregate metrics, scoring-support, spatial-discretization,
case-metric, profile-index, evaluation, and open-artifact metadata. New submissions must match
[`schemas/v3/submission.schema.json`](schemas/v3/submission.schema.json). Historical approved schema-v2 packages remain readable and
publishable, but the contributor-stage validator rejects new v2 packages because they lack mandatory v3 evidence.

The required `evaluation` object records the FluidsBench reference version, the contributor's evaluation-code revision, the exact
command used, and the SHA-256 checksum of `evaluation-evidence.json`. The evidence file repeats the command and submitted metric
values and binds the dataset version, split digest, case set, scoring-support manifest, spatial report, per-case metrics,
profile-index checksum, and exact public profile-ground-truth release. New submissions use
[`schemas/v3/evaluation-evidence.schema.json`](schemas/v3/evaluation-evidence.schema.json). This evidence is not a replacement for
scientific review and does not contain full surface or volume fields.

Every new package also declares `reproducibility.contract_version=open-reproducibility-3.0`, public evaluation-only data use, an
HTTPS code repository pinned to a full commit, an HTTPS model artifact pinned by SHA-256, an open licence for code, model, and
submitted result data, a hashed container or lockfile, and public artifact documentation. See
[`OPEN_REPRODUCIBILITY.md`](OPEN_REPRODUCIBILITY.md) for the complete
eligibility and validation policy.

The required `metrics/cases.json` records every test case, canonical support, support/scored counts, complete count and weight
coverage, unmapped/extrapolated counts, and per-case metric values. Its aggregate `metric_values` must exactly match
`submission.json`; macro-averaged spatial metrics are recalculated from its case values by the validator. Global R2 and published
dataset-reference RRMSE values are explicitly `aggregate_only`: the generic evaluator calculates them from complete prediction
arrays, while normal package validation checks their identities and rule bindings without pretending to recompute them.

The required `discretization.json` distinguishes training input, training supervision, inference input, direct model output, and the
mapping to each canonical support. `discretization/cases.jsonl` records actual evaluation-case counts and mapping coverage. This lets
methods use sparse points, grids, participant meshes, or native meshes without requiring inference on every native location, while
still requiring a prediction at every official scoring location after the declared mapping. When a native-resolution comparison is
reported, each case supplies its model/native counts and fraction; the validator reconciles those records with the fixed or
minimum/median/maximum summary and verifies `fraction = model_count / native_count`.

Contributors leave `approval` absent and must not add `maintainer-validation.json` or
`prediction-artifact-checks.json`. After submitted-data validation, maintainers add
the separately hashed validation record and `approval.status=approved`. Prototype packages use `approval.status=prototype`; the feed
builder publishes only prototype and maintainer-approved rows, so an unapproved source package cannot appear on the leaderboard.

Sharing full or example prediction fields is optional. When used, `prediction_artifacts` points to a revision-pinned public Hugging
Face dataset manifest. A maintainer may add one `prediction-artifact-checks.json` index recording accessibility, format, or explicit
metric-recomputation checks. Normal CI validates metadata and local hashes only and never downloads multi-gigabyte artifacts.

Profile data is kept out of the scalar leaderboard feed. Each chunk contains a manageable group of test geometries using compact
parallel arrays:

```json
{
  "case_id": "ahmedml_geometry_test_0001",
  "series": [
    {
      "panel_id": "pressure_profiles",
      "station_id": "upper_body_centerline",
      "quantity_id": "cp",
      "coordinate": [0.0, 0.5, 1.0],
      "prediction": [0.72, -0.31, 0.04]
    }
  ]
}
```

Use roughly 20-30 geometries per chunk. Coordinates must be finite, unique, and strictly increasing. Every required case,
panel, station, and quantity is declared by the dataset specification and split index. The profile schemas are:

- [`schemas/v1/profile-index.schema.json`](schemas/v1/profile-index.schema.json)
- [`schemas/v1/profile-chunk.schema.json`](schemas/v1/profile-chunk.schema.json)

New maintainer validation records must match
[`schemas/v3/maintainer-validation.schema.json`](schemas/v3/maintainer-validation.schema.json).

For schema v3, `profile_data.profile_ground_truth_release_id` and
`profile_data.profile_ground_truth_manifest_sha256` must exactly match `data_release.profile_ground_truth` in the leaderboard
manifest. The same values are repeated in the submitter-authored evaluation evidence and the maintainer validation record.

The profile index records the SHA-256 checksum and case IDs for each chunk. Normal JSON is used so pull requests remain readable;
hosting can compress it during delivery.

## 3. Validate and submit

Create a Python environment and install the two validation/reference dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Validate one directory:

```bash
python3 scripts/validate_submission.py --contributor-stage submissions/ahmedml/my-model-v1
```

Validate every source submission and verify that generated feeds are synchronized:

```bash
python3 scripts/manage_leaderboard.py check
```

The validator checks JSON schemas, exact public split and fixed-support coverage, case-metric aggregation, spatial counts and
domains, declared mappings, evaluation-evidence identities and checksums, profile coverage, coordinate ordering, array lengths,
finite values, split/chunk hashes, pinned open-artifact metadata, and approval lifecycle rules. It does not execute the model,
download optional remote predictions, or recompute submitted base metrics.

After validation:

1. Commit exactly one new submission directory. Do not modify schemas, specifications, validators, workflows, generated feeds, or
   existing submissions in the same pull request; a new result version uses a new globally unique submission ID.
2. Open a pull request against `main` once FluidsBench announces that the dataset is accepting real submissions.
3. Complete the pull request checklist and resolve all automated validation failures.
4. Maintainers review scientific provenance, public-evaluation-use eligibility, metadata, submitted values, licences, and artifact
   accessibility, then merge the contributor package while it is still unapproved and absent from public feeds.
5. A maintainer can run the **Maintainer approve and regenerate** workflow with the exact submission path, validator/approver
   identities, validation timestamp, and approval date. It creates the validation record, binds the resulting draft PR URL,
   rebuilds and verifies the compact feeds, and opens the protected-branch PR. The final merge remains manual.
6. Optional prediction checks use the separate **Check optional prediction artifact metadata** workflow. Their presence or outcome
   is descriptive and never changes approval or claim eligibility.

External pull requests are restricted to one entirely new submission directory. Maintainers may deliberately apply the restricted
`trusted-maintenance` label to allow a reviewed external repository-maintenance contribution; validation/approval changes must still
come from a maintainer-owned branch.

## Generated leaderboard feeds

Source submissions are converted into release-specific compact scalar feeds. Prototype releases contain only explicitly marked
prototype rows; official releases contain only validated and approved submitted-data rows:

```text
leaderboard/
  manifest.json
  datasets/<dataset-id>.json
  all.json
  claims/
    index.json
    <dataset-id>/<split-id>/<submission-id>.json
leaderboard.json
```

The website loads the selected scalar dataset lazily. Profile arrays are not copied into these feeds; each row contains a relative
profile index path, and the browser fetches only the selected geometry's chunk.

`leaderboard/manifest.json` also publishes the data-release identifier, generation time, source reference, contract version,
licence scope, archive URL, immutable asset base, SHA-256 digest of the complete scalar feed, and the expected release ID and
manifest digest for the public profile ground truth. Every feed row carries the SHA-256 digest of its profile index. Prototype
releases use `archive_url: null`; an official release must provide an immutable HTTPS archive URL plus asset-base and interactive
release-view URLs containing the release ID. The separate full `source_commit` records repository provenance without creating a
self-referential commit hash.

Official `asset_base_url` and `release_view_url` values are clean HTTPS directory bases: their final path segment is exactly the
safe lowercase release ID, they end in `/`, and they contain no query or fragment. Official builds preserve the manifest's explicit
timezone-qualified generation timestamp. If generated claims already exist for that official release ID, the builder refuses any
changed feed digest, ranking contract, claim set, or published claim metadata; a new release requires a new ID and matching URL
bases. This makes result permalinks and relative release-asset URLs identical across Python, JavaScript, archives, and CDNs.

Ranks are release records, not live-page claims. They are calculated within exactly one release, dataset, and split using the
dataset's declared ranking metric and its published decimal precision. Values are rounded in decimal with `decimal_half_up`, then
competition-ranked (`1, 2, 2, 4`); the rounded value is also the displayed value, so two visibly equal results cannot receive
different ranks. The feed publishes the raw value, rounded/display value, rank, ranked-result count, and tie count in each row's
`ranking` object.

Every release also generates one machine-readable result-claim record per feed row. The claims index hashes every record, and the
release manifest hashes the index. Each record identifies the release, result, ranking scope and policy, feed digest, source
submission, evaluation evidence, and profile-index bindings. Schema-v3 claims additionally bind the scoring-support identity and
URL, spatial report, spatial case records, and per-case metric evidence; a recorded optional prediction check is also hashed.
Official records additionally bind maintainer validation and provide an immutable result permalink based on
`data_release.release_view_url`; `archive_url` remains the separate DOI or data-archive landing page. Each claim's exact byte URL is
its repository-relative `leaderboard/claims/...` path under the immutable
`data_release.asset_base_url`. The build chain is deliberately one-way: ranked feed, feed digest, claim records, claims-index
digest, then manifest pin.

`bindings.result` identifies the exact-byte-hashed complete feed and the row's zero-based array index. A verifier hashes the feed
bytes, loads that indexed row, and compares its identity, ranking, eligibility, and artifact bindings with the claim. This avoids
language-dependent JSON number canonicalization while retaining a byte-for-byte release link.

The generated-artifact checker also verifies that `record_count` and `eligible_record_count` equal the claim-index contents; these
cross-field equalities are semantic checks beyond what the portable JSON Schema expresses.

Prototype claim records remain useful for testing the interface, but explicitly set academic-citation and promotion eligibility to
false and have no immutable permalink. Official records state that validation covered submitted data only. Prediction sharing and
optional check status are published as separate descriptive fields and do not change eligibility. The schemas are
[`schemas/releases/result-claim.schema.json`](schemas/releases/result-claim.schema.json) and
[`schemas/releases/claim-index.schema.json`](schemas/releases/claim-index.schema.json).

Maintainers rebuild and verify feeds with:

```bash
python3 scripts/manage_leaderboard.py build
python3 scripts/manage_leaderboard.py check
```

## Prototype split indexes

Current split indexes are marked `prototype_generated`. They preserve the dummy leaderboard's declared test counts but are not
official dataset case lists. Dataset owners must replace them with approved immutable case IDs and change the status to `official`
before real submissions are accepted. A submission records the exact split-index SHA-256 so later split changes are detectable.

## License

Repository code and published leaderboard metadata are covered by the [Apache License 2.0](LICENSE). Each real submission declares
an open `reproducibility.result_data_license_spdx` for its contributed profile values and result material; submitters must have the
right to provide them under that licence. Upstream datasets and model artifacts retain their own declared licences. Official
submissions must use publicly accessible code and model artifacts under one of the explicitly allowed open SPDX identifiers in the
v3 submission schema. See the category-specific lists in [`OPEN_REPRODUCIBILITY.md`](OPEN_REPRODUCIBILITY.md); proprietary and
unrecognised licence values fail validation.
