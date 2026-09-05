# HiLiftAeroML compact-v2 package assembly

Compact profile-v2 is the official and only HiLiftAeroML profile submission
representation. The benchmark-wide scoring support and owner-approval gates
remain closed, so this workflow is currently for coordinated maintainer dry
runs. It does not upload a result or create a leaderboard entry.

The package adapter consumes complete evaluator-native surface and volume
outputs, their case-set aggregate, receipt chain, and a benchmark-owned
compact-v2 evaluator-support release. It emits a deterministic schema-v3
directory whose profile artifacts contain only:

- `cp_q_delta`: `int16` quantized Cp deltas, reset at evaluator-owned branch
  boundaries; and
- `velocity_speed_over_u_inf`: scalar `float32` values for evaluator-selected
  valid rows.

Geometry, topology, masks, weights, ordering support, and truth stay outside
the participant package. Earlier HiLift profile package formats are rejected.
The contract is
[`native-profile-format-v2.json`](../../benchmark-specs/hiliftaeroml/native-profile-format-v2.json).

## Prepare the configuration

Copy `package-config.template.json` outside the repository and replace every
participant token with the method's real metadata. Record the architecture,
exact parameter count, required surface and volume outputs, data handling,
training stages, loaded checkpoint hashes, and measured inference compute.
The single top-level `evaluation` object must contain the exact assembler
command and its RFC3339 `generated_at` time.

`transolver-full360-candidate-config.json` is the retained resolved Full360
dry-run example. Its evaluator revision is historical evidence, not permission
to open intake or substitute a working-tree revision.

## Inspect, assemble, and validate

First inspect every configuration, release, aggregate, force, and provenance
gate without writing output:

```bash
python scripts/assemble_hiliftaeroml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --native-aggregate /path/to/native/case-set-aggregate \
  --native-surface-outputs /path/to/native/surface/per-case/outputs \
  --native-volume-outputs /path/to/native/volume/per-case/outputs \
  --native-receipts /path/to/native/case-receipts \
  --profile-support-release /path/to/hiliftaeroml-compact-profile-support-v2-candidate \
  --list-blockers
```

When inspection reports `ready_for_full_assembly_validation`, create a new
output directory. The path must not already exist:

```bash
python scripts/assemble_hiliftaeroml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --native-aggregate /path/to/native/case-set-aggregate \
  --native-surface-outputs /path/to/native/surface/per-case/outputs \
  --native-volume-outputs /path/to/native/volume/per-case/outputs \
  --native-receipts /path/to/native/case-receipts \
  --profile-support-release /path/to/hiliftaeroml-compact-profile-support-v2-candidate \
  --output /path/to/hiliftaeroml-my-model-v2

python scripts/validate_submission.py \
  --candidate-dry-run \
  --profile-support-release /path/to/hiliftaeroml-compact-profile-support-v2-candidate \
  /path/to/hiliftaeroml-my-model-v2
```

When both domains genuinely share one parent, `--native-outputs` is shorthand
for the two domain-specific output arguments. Do not use it when surface and
volume products came from different receipt-bound replays.

The assembler writes atomically, refuses an existing output path, and enforces
a 15,000,000-byte limit on the complete package tree. A passing dry run proves
only local structural and score recomputation validity; it does not publish
support, approve the evaluator, or open submissions.

## Build the deterministic ZIP

Build twice and require byte identity:

```bash
python scripts/build_hiliftaeroml_submission_zip.py \
  /path/to/hiliftaeroml-my-model-v2 \
  /path/to/hiliftaeroml-my-model-v2.build-a.zip

python scripts/build_hiliftaeroml_submission_zip.py \
  /path/to/hiliftaeroml-my-model-v2 \
  /path/to/hiliftaeroml-my-model-v2.build-b.zip

cmp --silent \
  /path/to/hiliftaeroml-my-model-v2.build-a.zip \
  /path/to/hiliftaeroml-my-model-v2.build-b.zip
sha256sum \
  /path/to/hiliftaeroml-my-model-v2.build-a.zip \
  /path/to/hiliftaeroml-my-model-v2.build-b.zip
```

The checked-in Full360 reference demonstrates this official representation
over all 360 ordered Full cases. Its exact size, identity, metrics, and
lifecycle evidence are recorded in
[`compact-profile-full360-validation-v1.json`](../../benchmark-specs/hiliftaeroml/compact-profile-full360-validation-v1.json).
That reference does not establish published evaluator support for the other
case sets.

Maintainers who need to rebuild evaluator support can use
`scripts/materialize_hiliftaeroml_compact_profile_support.py` with the exact
split, complete native outputs, and authorized internal source-truth release.
The resulting support directory is benchmark-owned and must never be copied
into the participant ZIP.
