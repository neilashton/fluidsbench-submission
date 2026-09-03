# HiLiftAeroML FluidsBench schema-v3 candidate package

This directory contains both a reusable configuration template and the
concrete Full360 Transolver candidate configuration.  Neither file is a
submission, scoring-support release, or accepted leaderboard result.
HiLiftAeroML remains a closed owner-review candidate.  Strings beginning with
`__REPLACE_` and `__UNRESOLVED_HILIFTAEROML_` are machine-detectable blockers
rather than illustrative release identities.

`transolver-full360-candidate-config.json` records the real retained Table 5
epoch-1000 Transolver replay.  Its `evaluation.command` is executable from the
FluidsBench repository root once all referenced campaign products exist and
targets the canonical `package-a` directory.  The evaluator `code_revision` is
pinned to `68899f780d96b70f2badb5658971c87af0b17172`, the immutable
implementation commit recorded by the repository binding.  This freeze permits
only controlled maintainer-local candidate dry runs; do not replace it with
another working-tree revision.  It does not open submissions, approve the
candidate, or publish profile truth.

The package adapter consumes evaluator-native per-case products directly.  It
recomputes Cp and velocity profile R2 from prediction-only chunks joined to an
explicitly supplied local hidden-truth candidate; it does not rewrite case
identities, fill missing cases, or synthesize unavailable loads.  It accepts
every official HiLiftAeroML split in `submission-spec.json`; the 14 public
split labels map to the exact eight retained case sets.

Copy `package-config.template.json` outside the repository and replace the
participant fields with the submitted method's actual record.  The structured
methodology must describe the architecture and exact parameter count, all four
required surface/volume outputs, data handling and training stages, the raw
loaded checkpoint-file hashes, and measured complete-split inference compute.
`parameter_count_millions` is derived from the exact total parameter count and
must not be supplied separately.

Before attempting assembly, inspect all owner, configuration, and native gates
without writing output:

```bash
python scripts/assemble_hiliftaeroml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --native-aggregate /path/to/native/aggregate \
  --native-surface-outputs /path/to/native/surface/per-case/outputs \
  --native-volume-outputs /path/to/native/volume/per-case/outputs \
  --native-receipts /path/to/native/per-case/receipts \
  --candidate-profile-truth-release /path/to/hiliftaeroml-native-profile-truth-v1-candidate \
  --list-blockers
```

The completed profile-ground-truth candidate is repository-bound for this
maintainer-local dry run, but remains unpublished, unapproved, and inactive.
Supplying its local release path does not open public profile intake.  The
evaluator revision is frozen for this maintainer-local dry run.  Public
activation remains blocked on benchmark-owner approval, public profile-truth
publication, and the other activation-checklist gates.  Force and overall
scores still require exact complete truth-load coverage for every selected
case.  An `unavailable_validated_exception` is reported as a blocker;
imputation, zero-fill, case omission, and partial force/overall scores are
forbidden.

Once the required local candidate inputs and every evaluator-native case
product are complete, assemble a participant-owned directory:

```bash
python scripts/assemble_hiliftaeroml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --native-aggregate /path/to/native/aggregate \
  --native-surface-outputs /path/to/native/surface/per-case/outputs \
  --native-volume-outputs /path/to/native/volume/per-case/outputs \
  --native-receipts /path/to/native/per-case/receipts \
  --candidate-profile-truth-release /path/to/hiliftaeroml-native-profile-truth-v1-candidate \
  --output /path/to/hiliftaeroml-my-model-v1

python scripts/validate_submission.py \
  --candidate-dry-run \
  --candidate-profile-truth-release /path/to/hiliftaeroml-native-profile-truth-v1-candidate \
  /path/to/hiliftaeroml-my-model-v1
```

When both domains genuinely share one parent, `--native-outputs` remains a
backward-compatible shorthand. Do not use it when a corrected surface replay
is paired with retained volume outputs.

Build two independent archives and require byte identity before retaining the
submission ZIP:

```bash
python scripts/build_hiliftaeroml_submission_zip.py \
  /path/to/hiliftaeroml-my-model-v1 \
  /path/to/hiliftaeroml-my-model-v1.build-a.zip

python scripts/build_hiliftaeroml_submission_zip.py \
  /path/to/hiliftaeroml-my-model-v1 \
  /path/to/hiliftaeroml-my-model-v1.build-b.zip

cmp --silent \
  /path/to/hiliftaeroml-my-model-v1.build-a.zip \
  /path/to/hiliftaeroml-my-model-v1.build-b.zip
sha256sum \
  /path/to/hiliftaeroml-my-model-v1.build-a.zip \
  /path/to/hiliftaeroml-my-model-v1.build-b.zip
```

The two SHA-256 values must match. Archive members are sorted and receive
fixed timestamps, permissions, and compression settings; symbolic links and
non-regular source entries are rejected.

The commissioned Full360 Transolver replay completed this procedure over all
360 ordered cases. Both independently assembled 763-file packages passed the
candidate validator and had logical-tree SHA-256
`9c02d241eaf2ea6deecd4181816ed690d664b10f6eea0c2db4e5880aa2b1a0ab`.
Both 2,264,458,600-byte, 763-member ZIP builds had SHA-256
`a8dfd6ffbe6d103bc1a3123f6e6f756bacf960f92acc7079237b443bbbb62504`.
The resulting headline values were 69.15276784043088 overall,
48.167429082451235 for fields, 99.52105782630258 for forces,
80.75515537051848 for diagnostics, 0.9636931485730299 for Cp-cut R2, and
0.7034571571266213 for velocity-profile R2. This is reproducibility evidence
for a closed candidate only: it did not approve or activate the evaluator,
publish hidden truth, open submissions, upload or publish the package, or
create a public or private leaderboard entry.

The output uses the same FluidsBench schema-v3 submission, evidence,
case-metrics, scoring-support, and discretization envelopes as DrivAerML.  Its
profile payload is necessarily HiLift-specific: Cp is retained as disconnected
physical cut graphs with branch/segment topology, while velocity retains the
exact five stations (`B.2`, `B.3`, `C.1`, `C.2`, `C.3`), 801 rows per station,
and explicit invalid gaps.  Deterministic prediction-only NPZ artifacts exclude
all truth/reference arrays.  Their reported per-case and macro profile scores
are independently recomputed by the candidate validator against the inactive
hidden-truth release.  Optional regional diagnostics are report-only,
zero-weight evidence and cannot change official metrics or the overall score.

The adapter writes atomically and refuses an existing output path.  It creates
no `approval`, `maintainer-validation.json`, or
`prediction-artifact-checks.json`; those are benchmark-maintainer records.
Every consumed per-case artifact is fail-closed against the retained chain
`aggregate artifact manifest -> case metrics input hash -> case receipt ->
surface/volume summary -> artifact descriptor`; a missing receipt, swapped
case file, stale summary, path/size mismatch, or digest mismatch blocks output.
