# Benchmark submission specifications

Each dataset directory contains a machine-readable `submission-spec.json` and one split index per accepted leaderboard split.
The specification lists the required scalar metrics and profile panel, station, and quantity IDs. The validator consumes these
same files, so the written instructions and automated checks use one contract.

Each official specification pins `evaluation_reference_version` to an immutable FluidsBench reference release. Submission and
maintainer-validation records must identify that exact release. The reference defines how submitters calculate their values;
FluidsBench does not rerun the submitted model or recompute base metrics from full prediction fields.

Schema v2 evaluation evidence also repeats the dataset version, split SHA-256, case-set ID, and exact public profile-ground-truth
release ID and manifest SHA-256 from the submission. This binds the submitted scalar/profile package to its declared evaluation and
profile comparison basis; it does not claim that profile ground truth covers the full fields used for scalar metrics.

All official split case IDs and evaluation ground truth are public. The evaluation data may be used only for final evaluation,
never for fitting, model or checkpoint selection, hyperparameter selection, manual tuning, or preprocessing statistics. Real
submissions make the machine-readable `public_test_data_use=\"evaluation_only\"` declaration defined by
[`../OPEN_REPRODUCIBILITY.md`](../OPEN_REPRODUCIBILITY.md).

Split indexes marked `official` contain dataset-owner-approved case IDs. Indexes marked `prototype_generated` preserve the
current dummy leaderboard's declared test count but are not suitable for real submissions. Dataset owners must replace those IDs,
set the status to `official`, and review the resulting SHA-256 value before FluidsBench opens that split for submissions.

Field metrics use the equations and edge-case behaviour in [`../reference/`](../reference/). The default field reduction is a
per-geometry metric followed by a macro-average across test geometries. A dataset specification must explicitly document any
different reduction, including the published VKI-LS59 and Rotor37 RRMSE reductions.

Each metric's `aggregation` and `weighting` fields make the reduction explicit. `per_geometry_then_macro_average` gives every
test geometry equal influence; `flatten_all_aligned_field_values` evaluates one reduction over all aligned samples;
`all_test_cases` gives scalar cases equal weight; the two `benchmark_*_rrmse_across_cases` values use the exact RRMSE equations in
the reference documentation. Derived metrics list either `derived_score_equation` or `derived_arithmetic_mean`.
