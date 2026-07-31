# Submission examples

New submissions use schema v3. Start with the synthetic [`v3-template/`](v3-template/) to understand the submission, evaluation
evidence, canonical scoring support, per-case metrics and sufficient statistics, spatial report, optional prediction artifact,
profiles, maintainer validation, and internal SHA-256 bindings. It is a format fixture, not an official dataset result; use the
selected dataset's official support release and specification when submissions open.

A real dataset specification pins its original public field-bearing files and requires one mapped prediction for every official
entity in every case. It also identifies whether fields are point-, node-, face-, or cell-associated and supplies the authoritative
area, length, volume, or cell-area weights. The guidance distinguishes three-dimensional surfaces and flow domains, two-dimensional
flow domains,
two-dimensional surface manifolds embedded in three dimensions, and one-dimensional boundary curves.

Methods may perform inference in chunks or on another internal representation. Relative-L2 chunks are combined by adding their
numerators and denominators, entity counts, and total weights before calculating the complete-case value; chunk-level L2 values are
never averaged. Surface, two-dimensional surface-manifold, or boundary-curve results report area or length weighting as primary
and an unweighted result as secondary.
Volume or two-dimensional-domain results report an unweighted result as primary and volume or area weighting as secondary. Complete
case values are macro-averaged across the test set.

[`v2-template/`](v2-template/) is retained to interpret previously approved schema-v2 packages. The contributor-stage validator
does not accept it as a new submission.

[`profile-chunk.example.json`](profile-chunk.example.json) demonstrates the compact case/series representation with Cp, Cf, and
velocity profiles. It is intentionally abridged and is not a complete benchmark split.

For a historical v1 prototype directory that passes the dummy-data validator, inspect the AhmedML
[`transolver`](../submissions/ahmedml/transolver/) submission. It includes all prototype case IDs, chunk checksums, required
pressure stations, optional velocity stations, metadata, and scalar metrics. Do not use it as a real-submission template.

Participants may generate equivalent JSON with Python, MATLAB, Julia, C++, or another language. The schema and final values matter;
the code does not need to follow the example implementation. Public code, a pinned model, a locked environment, and artifact
documentation are optional. If supplied, their URLs, versions, hashes, and licences must satisfy the open reproducibility contract.

The submitter supplies all prediction, result, spatial, and profile data. Sharing the complete prediction fields is optional.
Contributor-stage validation checks the package but does not approve it. Maintainers validate the submitted files and hashes before
approval; FluidsBench does not execute any shared model artifact as part of required approval.
