# Schema v3 synthetic template

This directory demonstrates the FluidsBench v3 structure with two tiny
synthetic cases. Its fictional dataset, owner approval, support, and result
are internally consistent so the complete contract can be tested. It is only
a format and evaluator fixture, not a recognized FluidsBench dataset, result,
or artifact check.

The benchmark-owned chain is:

```text
support/manifest.json
  -> support/case-sets/standard/index.json
  -> support/case-sets/standard/chunk-000.json
  -> ground-truth tables
```

The evaluator joins prediction rows to the benchmark tables by exact
`support_id`. It rejects missing, duplicate, and unknown IDs. Coordinates,
weights, and ground truth always come from `support/`; they are never taken
from, interpolated by, or resampled from the prediction artifact.

Run the synthetic calculation from the repository root:

```bash
python3 -m reference.evaluate_predictions \
  --support-manifest examples/v3-template/support/manifest.json \
  --case-set standard \
  --prediction-manifest examples/v3-template/predictions/manifest.json \
  --submission-id synthetic-open-model-v1 \
  --split-id default \
  --output /tmp/fluidsbench-synthetic-case-metrics.json
```

`submission.json`, `evaluation-evidence.json`, `discretization.json`,
`metrics/cases.json`, and `maintainer-validation.json` show the required hash
bindings. `prediction-artifact-checks.json` is deliberately maintainer-owned;
a submitter may declare a pinned public Hugging Face prediction artifact but
must not declare its own check status.

The synthetic `submission.json` also demonstrates optional public code,
model, environment, and artifact-documentation metadata. A real v3 submission
may omit those optional fields without affecting eligibility. If included,
they remain subject to the schema's version, digest, URL, and licence checks.
