# Submission examples

For a real schema v2 submission, start with the complete [`v2-template/`](v2-template/) package. Its submission, evaluation
evidence, profiles, maintainer-validation example, and internal SHA-256 links are all schema-tested in CI.

[`profile-chunk.example.json`](profile-chunk.example.json) demonstrates the compact case/series representation with Cp, Cf, and
velocity profiles. It is intentionally abridged and is not a complete benchmark split.

For a historical v1 prototype directory that passes the dummy-data validator, inspect the AhmedML
[`transolver`](../submissions/ahmedml/transolver/) submission. It includes all prototype case IDs, chunk checksums, required
pressure stations, optional velocity stations, metadata, and scalar metrics. Do not use it as a real-submission template.

Participants may generate equivalent JSON with Python, MATLAB, Julia, C++, or another language. The schema and final values matter;
the code does not need to follow the example implementation, but a real submission must publish its exact code, pinned model,
locked environment, and artifact documentation under the open reproducibility contract.

The submitter supplies all result and profile data. Contributor-stage validation checks the generated package but does not approve
it. Maintainers validate the submitted files and hashes before approval; FluidsBench does not execute the public model artifact.
