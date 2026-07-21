# Submission examples

[`profile-chunk.example.json`](profile-chunk.example.json) demonstrates the compact case/series representation with Cp, Cf, and
velocity profiles. It is intentionally abridged and is not a complete benchmark split.

For a complete directory that passes the validator, inspect the dummy AhmedML
[`transolver`](../submissions/ahmedml/transolver/) submission. It includes all prototype case IDs, chunk checksums, required
pressure stations, optional velocity stations, metadata, and scalar metrics.

Participants may generate equivalent JSON with Python, MATLAB, Julia, C++, or another language. The schema and final values matter;
the code does not need to follow the example implementation, but a real submission must publish its exact code, pinned model,
locked environment, and replay instructions under the open reproducibility contract.

Contributor-stage validation checks the generated package but does not approve it. An independent maintainer must load the public
model artifact and reproduce the result before approval.
