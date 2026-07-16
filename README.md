# fluidsbench-submission

Submission repository and approved-data feed for the [FluidsBench leaderboard](https://fluidsbench.org/leaderboard/).

> FluidsBench is currently a work in progress. The `dev` branch, split indexes, submissions, metrics, and profile curves are
> prototype dummy data and are not approved benchmark results.

## Responsibilities

The submission process deliberately separates three responsibilities:

1. Participants calculate metrics from their own predictions and ground truth. FluidsBench publishes exact equations and
   array-level NumPy references under [`reference/`](reference/), but does not prescribe a model output format or data loader.
2. Participants create `submission.json` and the required profile chunks using their own code. FluidsBench publishes schemas,
   dataset specifications, directions, and examples; there is no mandatory packaging tool.
3. Participants must run the FluidsBench validator before opening a pull request. GitHub Actions runs the same validator again.

The validator proves that a package is complete, internally consistent, and correctly formatted. Because full prediction fields
are not submitted, it cannot independently prove that a participant's base metric values were calculated from those predictions.

## Submission directory

Create one directory under the matching dataset:

```text
submissions/<dataset-id>/<submission-id>/
  submission.json
  evaluation-evidence.json
  profiles/
    index.json
    chunk-000.json
    chunk-001.json
```

Use lowercase letters, numbers, and hyphens for the globally unique `submission-id`. Do not edit generated files under
`leaderboard/` directly.

A complete prototype example is available at
[`submissions/ahmedml/transolver/`](submissions/ahmedml/transolver/). A short annotated example is under [`examples/`](examples/).

## 1. Calculate metrics

Read the selected dataset's page on the [FluidsBench website](https://fluidsbench.org/datasets/) and its machine-readable
specification under [`benchmark-specs/`](benchmark-specs/). The specification lists accepted splits, required metric IDs, units,
directions, profile panels, stations, and quantities.

The equations, edge cases, and NumPy reference implementations are documented in
[`reference/README.md`](reference/README.md). Participants can call those functions with aligned arrays or reproduce the same
equations in another language. They remain responsible for loading data, restoring dimensional values, aligning predictions with
ground truth, applying dataset masks, and extracting profiles.

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

## 2. Prepare metadata and profiles

`submission.json` contains model, submitter, training, dataset, split, aggregate metric, profile-index, and evaluation metadata. It must match
[`schemas/v1/submission.schema.json`](schemas/v1/submission.schema.json).

The required `evaluation` object records the FluidsBench reference version, the contributor's evaluation-code revision, the exact
command used, and the SHA-256 checksum of `evaluation-evidence.json`. The evidence file repeats the command and submitted metric
values and records the profile-index checksum, creating a tamper-evident link between the evaluation provenance, reported scalars,
and profile package. It is not a
replacement for scientific review and does not contain full surface or volume fields.

Contributors should leave `approval` absent. During review, maintainers add `approval.status=approved`, the reviewer, approval date,
and pull-request URL. Prototype packages use `approval.status=prototype`; the feed builder publishes only those two statuses, so a
merged but unapproved source package cannot appear on the leaderboard.

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
python3 scripts/validate_submission.py submissions/ahmedml/my-model-v1
```

Validate every source submission and verify that generated feeds are synchronized:

```bash
python3 scripts/manage_leaderboard.py check
```

The validator checks JSON schemas, exact split case coverage, metric IDs and ranges, training metadata consistency, evaluation
evidence identity and checksums, profile coverage, coordinate ordering, array lengths, finite values, split hashes, chunk hashes,
and derived score arithmetic.

After validation:

1. Commit only your submission directory.
2. Open a pull request against `main` once FluidsBench announces that the dataset is accepting real submissions.
3. Complete the pull request checklist and resolve all automated validation failures.
4. Maintainers review the scientific provenance, metadata, metrics, profile definitions, and retained calculation evidence.
5. A maintainer records the approval metadata, rebuilds the compact feeds, and merges the pull request.

## Generated leaderboard feeds

Approved source submissions are converted into compact scalar feeds:

```text
leaderboard/
  manifest.json
  datasets/<dataset-id>.json
  all.json
leaderboard.json
```

The website loads the selected scalar dataset lazily. Profile arrays are not copied into these feeds; each row contains a relative
profile index path, and the browser fetches only the selected geometry's chunk.

`leaderboard/manifest.json` also publishes the data-release identifier, generation time, source reference, and SHA-256 digest of
the complete scalar feed. Official releases should replace the moving preview reference with an immutable source commit or tag.

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

Repository code and published submission metadata are covered by the [Apache License 2.0](LICENSE). Submitters must have the right
to publish the metadata and profile values included in their pull request. Dataset and model artifacts retain their own licenses.
