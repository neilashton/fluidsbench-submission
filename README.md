# fluidsbench-submission

Submission repository and approved-data feed for the [FluidsBench leaderboard](https://fluidsbench.org/).

> FluidsBench is currently a work in progress. The `dev` branch, split indexes, submissions, metrics, and profile curves are
> prototype dummy data and are not approved benchmark results.

## Responsibilities

FluidsBench follows the versioned [`open-reproducibility-2.0`](OPEN_REPRODUCIBILITY.md) track. Evaluation ground truth and case
IDs are public. The submission process deliberately separates four responsibilities:

1. Participants calculate metrics from their own predictions and ground truth. FluidsBench publishes exact equations and
   array-level NumPy references under [`reference/`](reference/), but does not prescribe a model output format or data loader.
2. Participants supply all scalar results and prediction/profile data, and publish the exact source code, model artifact, locked
   environment, and artifact documentation.
3. Participants must run the FluidsBench contributor-stage validator before opening a pull request. Their package remains
   unapproved and is not included in the public feed.
4. A maintainer validates the submitted files, hashes, required coverage, and metadata, then approves the package for publication.

FluidsBench does not execute the submitted code or model, regenerate predictions, or recompute base metrics from full prediction
fields. It plots and tabulates the submitter-supplied values and compares submitted profiles with the pinned public ground truth.
Approval means only that the submitted data passed the published validation and review process.

## Submission directory

Create one directory under the matching dataset:

```text
submissions/<dataset-id>/<submission-id>/
  submission.json
  evaluation-evidence.json
  maintainer-validation.json   # added only by maintainers during approval
  profiles/
    index.json
    chunk-000.json
    chunk-001.json
```

Use lowercase letters, numbers, and hyphens for the globally unique `submission-id`. Do not edit generated files under
`leaderboard/` directly.

Start a real submission from the complete, schema-valid
[`examples/v2-template/`](examples/v2-template/) file set. Existing directories under `submissions/` are historical v1 prototype
fixtures for the dummy leaderboard and must not be copied as real-submission templates.

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

`submission.json` contains model, submitter, training, dataset, split, aggregate metric, profile-index, evaluation, and open-artifact metadata. Real submissions must match
[`schemas/v2/submission.schema.json`](schemas/v2/submission.schema.json). Historical prototype packages remain on schema v1 and
cannot become approved results.

The required `evaluation` object records the FluidsBench reference version, the contributor's evaluation-code revision, the exact
command used, and the SHA-256 checksum of `evaluation-evidence.json`. The evidence file repeats the command and submitted metric
values and binds the dataset version, split digest, case set, profile-index checksum, and exact public profile-ground-truth release,
creating a tamper-evident link between the evaluation provenance, reported scalars, profile package, and comparison basis. Real
submissions use [`schemas/v2/evaluation-evidence.schema.json`](schemas/v2/evaluation-evidence.schema.json). This evidence is not a
replacement for scientific review and does not contain full surface or volume fields.

Every real package also declares `reproducibility.contract_version=open-reproducibility-2.0`, public evaluation-only data use, an
HTTPS code repository pinned to a full commit, an HTTPS model artifact pinned by SHA-256, an open licence for code, model, and
submitted result data, a hashed container or lockfile, and public artifact documentation. See
[`OPEN_REPRODUCIBILITY.md`](OPEN_REPRODUCIBILITY.md) for the complete
eligibility and validation policy.

Contributors leave `approval` absent and must not add `maintainer-validation.json`. After submitted-data validation, maintainers add
the separately hashed validation record and `approval.status=approved`. Prototype packages use `approval.status=prototype`; the feed
builder publishes only prototype and maintainer-approved rows, so an unapproved source package cannot appear on the leaderboard.

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

Maintainer validation records must match
[`schemas/v2/maintainer-validation.schema.json`](schemas/v2/maintainer-validation.schema.json).

For schema v2, `profile_data.profile_ground_truth_release_id` and
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

The validator checks JSON schemas, exact public split case coverage, metric IDs and ranges, training metadata consistency,
evaluation evidence identity and checksums, profile coverage, coordinate ordering, array lengths, finite values, split hashes,
chunk hashes, derived score arithmetic, pinned open-artifact metadata, and approval/validation lifecycle rules. It does not execute
the model or independently recompute submitted base metrics.

After validation:

1. Commit exactly one new submission directory. Do not modify schemas, specifications, validators, workflows, generated feeds, or
   existing submissions in the same pull request; a new result version uses a new globally unique submission ID.
2. Open a pull request against `main` once FluidsBench announces that the dataset is accepting real submissions.
3. Complete the pull request checklist and resolve all automated validation failures.
4. Maintainers review scientific provenance, public-evaluation-use eligibility, metadata, submitted values, licences, and artifact
   accessibility, then merge the contributor package while it is still unapproved and absent from public feeds.
5. From a maintainer-owned branch, run submitted-data validation and add `maintainer-validation.json`. This record pins the public
   ground-truth release used as the comparison basis and explicitly records that model execution and metric recomputation were not
   performed.
6. Open a separate pull request that adds approval metadata and rebuilds the compact feeds. Mark it `maintainer-validation` for
   auditability. The same maintainer may validate and approve the submission.

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
leaderboard.json
```

The website loads the selected scalar dataset lazily. Profile arrays are not copied into these feeds; each row contains a relative
profile index path, and the browser fetches only the selected geometry's chunk.

`leaderboard/manifest.json` also publishes the data-release identifier, generation time, source reference, contract version,
licence scope, archive URL, immutable asset base, SHA-256 digest of the complete scalar feed, and the expected release ID and
manifest digest for the public profile ground truth. Every feed row carries the SHA-256 digest of its profile index. Prototype
releases use `archive_url: null`; an official release must provide an immutable HTTPS archive URL and an asset base pinned to the
full source commit.

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
v2 submission schema. See the category-specific lists in [`OPEN_REPRODUCIBILITY.md`](OPEN_REPRODUCIBILITY.md); proprietary and
unrecognised licence values fail validation.
