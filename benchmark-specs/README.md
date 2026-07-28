# Benchmark submission specifications

Each dataset directory contains a machine-readable `submission-spec.json` and one split index per accepted leaderboard split.
The specification lists the required scalar metrics and profile panel, station, and quantity IDs. It also declares the canonical
scoring-support status and identity. The validator consumes these same files, so the written instructions and automated checks use
one contract.

Each official specification pins `evaluation_reference_version` to an immutable FluidsBench reference release. Submission and
maintainer-validation records must identify that exact release. The reference defines how submitters calculate their values;
FluidsBench does not rerun the submitted model or recompute base metrics from full prediction fields.

Schema-v3 evaluation evidence repeats the dataset version, split SHA-256, case-set ID, scoring-support release and manifest
SHA-256, spatial-report SHA-256, per-case-metric SHA-256, and exact public profile-ground-truth release ID and manifest SHA-256 from
the submission. This binds the submitted package to its declared evaluation and comparison basis.

All official split case IDs and evaluation ground truth are public. The evaluation data may be used only for final evaluation,
never for fitting, model or checkpoint selection, hyperparameter selection, manual tuning, or preprocessing statistics. Real
submissions make the machine-readable `public_test_data_use=\"evaluation_only\"` declaration defined by
[`../OPEN_REPRODUCIBILITY.md`](../OPEN_REPRODUCIBILITY.md).

Split indexes marked `official` contain dataset-owner-approved case IDs. Indexes marked `prototype_generated` preserve the
current dummy leaderboard's declared test count but are not suitable for real submissions. Dataset owners must replace those IDs,
set the status to `official`, and review the resulting SHA-256 value before FluidsBench opens that split for submissions.

The `scoring_support` object uses one of four statuses:

- `official`: the dataset owner approved the manifest and case set and `submissions_open` may be true;
- `owner_review_required`: a concrete proposal exists but the dataset owner has not approved it;
- `prototype`: format or evaluator development only; or
- `retired`: preserved for historical interpretation and closed to new submissions.

Every closed status supplies `closed_reason`. Only an `official`, owner-approved release with `submissions_open=true` can accept a
schema-v3 result. The manifest pins its case-set index; the index pins every chunk; and chunks locate or hash the benchmark-owned
coordinates, weights, ground truth, and stable IDs. The validator requires its cases to match the accepted split exactly.

Dataset support is approved independently. A dataset collaborator changes only their dataset directory in one pull request:

1. replace prototype split IDs with the ordered official evaluation case IDs, set each `case_id_status` to `official`, and update
   the split counts and SHA-256 values;
2. add the dataset's scoring-support manifest, case-set indexes, chunks, and any small local support artifacts;
3. set `scoring_support.status` to `official`, add the immutable release ID, repository-relative manifest path, public HTTPS
   manifest URL, manifest SHA-256, and their name/date/pull-request URL under `owner_approval`; if support artifacts are remote or
   require dataset-specific loading, also add the pinned `publication_validation` receipt produced by that loader;
4. keep `submissions_open=false` while the scientific contract is under review, then set it to `true` only when that dataset is
   ready to receive v3 result pull requests; and
5. run `python scripts/validate_scoring_supports.py`.

That command validates only the releases declared by each specification. For an official dataset it schema-checks the manifest,
follows and hashes the manifest → case-index → chunk chain, checks local artifact hashes, and requires every case set to match its
ordered official split exactly. It also requires the manifest's metric bindings to cover exactly the field and case-scalar metrics
in `submission-spec.json`, including reduction, weighting, aggregation, evidence mode, and evaluator-version pins. A complete local
materialized-table release is smoke-loaded case by case. A remote or dataset-specific release instead requires a committed receipt
pinning the validator file/digest, manifest digest, normalized-support digest, case/support counts, reviewer, timestamp, and pull
request. Other datasets may remain `owner_review_required` and closed. A collaborator's approving pull request is the durable
scientific approval record; FluidsBench's protected-branch maintainer still performs the final merge.

Field metrics use the equations and edge-case behaviour in [`../reference/`](../reference/). The default field reduction is a
per-geometry metric followed by a macro-average across test geometries. A dataset specification must explicitly document any
different reduction, including the published VKI-LS59 and Rotor37 RRMSE reductions.

Each metric's `aggregation` and `weighting` fields make the reduction explicit. `per_geometry_then_macro_average` gives every
test geometry equal influence; `flatten_all_aligned_field_values` evaluates one reduction over all aligned samples;
`all_test_cases` gives scalar cases equal weight; the two `benchmark_*_rrmse_across_cases` values use the exact RRMSE equations in
the reference documentation. Derived metrics list either `derived_score_equation` or `derived_arithmetic_mean`.

Each specification also publishes the leaderboard `ranking` contract: metric ID, direction, decimal places, decimal rounding rule,
and competition-ranking method. The decimal places must equal that metric's display digits in the release manifest. FluidsBench
rounds the submitter-supplied ranking value with decimal half-up rounding before both display and comparison, and assigns equal
rounded values the same competition rank (`1, 2, 2, 4`). Rank scope is always one immutable release, dataset, and split; filters or
later submissions do not rewrite a historical rank.
