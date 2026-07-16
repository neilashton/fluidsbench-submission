# Benchmark submission specifications

Each dataset directory contains a machine-readable `submission-spec.json` and one split index per accepted leaderboard split.
The specification lists the required scalar metrics and profile panel, station, and quantity IDs. The validator consumes these
same files, so the written instructions and automated checks use one contract.

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
