# Submission examples

[`profile-chunk.example.json`](profile-chunk.example.json) demonstrates the compact case/series representation with Cp, Cf, and
velocity profiles. It is intentionally abridged and is not a complete benchmark split.

For a complete directory that passes the validator, inspect the dummy AhmedML
[`transolver`](../submissions/ahmedml/transolver/) submission. It includes all prototype case IDs, chunk checksums, required
pressure stations, optional velocity stations, metadata, and scalar metrics.

Participants may generate equivalent JSON with Python, MATLAB, Julia, C++, or another language. The schema and final values matter;
the code used to produce them does not need to follow the example implementation.

The validator checks this package after it has been generated. It does not load a model checkpoint or calculate base metrics from
full fields, so contributors must retain enough evaluation evidence for the maintainers' scientific review.
