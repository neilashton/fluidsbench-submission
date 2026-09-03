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

The commands and Full360 reproducibility evidence below retain the native
profile-v1 workflow. An additive compact profile-v2 path is documented
separately later in this file; it does not alter or supersede that evidence.

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

## Additive compact profile-v2 Full360 exercise

The compact path is an inactive, unpublished maintainer-local candidate for
profile plots and profile R2 payloads only. Full native-surface Cp scoring,
wall-shear scoring, exact force integration, and exact pitching-moment
integration are unchanged and still consume the complete native surface
prediction. The compact representation does not make the native field outputs
optional.

Compact packages state this provenance boundary explicitly: the retained
dataset-evaluator revision applies only to the native-v1 base field, force, and
noncompact scoring path, while the compact-v2 implementation remains an
unbound worktree candidate with no code revision or implementation-manifest
digest. A future freeze must replace those null bindings explicitly.

Evaluator-owned support remains outside the participant package. It owns the
physical cut geometry and connected-graph topology, a frozen maximum of 128 Cp
samples per physical graph placed uniformly in physical arc length, and the
velocity coordinates, validity mask, weights, and ordering. A participant case
artifact contains exactly prediction values: `cp_q_delta` and scalar `float32`
`velocity_speed_over_u_inf`. See the candidate
[`native-profile-format-v2.json`](../../benchmark-specs/hiliftaeroml/native-profile-format-v2.json),
the
[`compact-cp-representation-decision-v1.json`](../../benchmark-specs/hiliftaeroml/compact-cp-representation-decision-v1.json),
and the
[`compact-cp-representation-audit-v1.md`](../../benchmark-specs/hiliftaeroml/compact-cp-representation-audit-v1.md).

With authorized Full360 native outputs and native-profile truth, materialize
one local evaluator-support release:

```bash
python scripts/materialize_hiliftaeroml_compact_profile_support.py \
  --submission-spec benchmark-specs/hiliftaeroml/submission-spec.json \
  --split benchmark-specs/hiliftaeroml/splits/full.json \
  --surface-outputs-root /path/to/native/surface/per-case/outputs \
  --volume-outputs-root /path/to/native/volume/per-case/outputs \
  --source-truth-release /path/to/hiliftaeroml-native-profile-truth-v1-candidate \
  --output-root /path/to/hiliftaeroml-compact-profile-support-v2-candidate
```

That output is evaluator-owned and must not be copied into the submission.
Pass it to the assembler and validator instead of the native-v1 truth flag:

For this path, add a top-level `compact_evaluation` object containing the
exact compact assembler `command` and RFC3339 `generated_at` time. The
assembler uses that record only in compact mode and preserves the existing
native-v1 `evaluation` record. The checked-in Full360 configuration shows both.

```bash
python scripts/assemble_hiliftaeroml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --native-aggregate /path/to/native/aggregate \
  --native-surface-outputs /path/to/native/surface/per-case/outputs \
  --native-volume-outputs /path/to/native/volume/per-case/outputs \
  --native-receipts /path/to/native/per-case/receipts \
  --candidate-compact-profile-support-release /path/to/hiliftaeroml-compact-profile-support-v2-candidate \
  --output /path/to/hiliftaeroml-my-model-compact-v2

python scripts/validate_submission.py \
  --candidate-dry-run \
  --candidate-compact-profile-support-release /path/to/hiliftaeroml-compact-profile-support-v2-candidate \
  /path/to/hiliftaeroml-my-model-compact-v2
```

The compact assembler has a hard 15,000,000-byte limit on the sum of regular
files in the assembled package. Passing that limit, deterministic archive
checks, and local validation is not publication, activation, owner approval,
or evidence for any case set beyond this Full360 exercise. The native-v1
workflow and its retained package hashes above remain unchanged.

The retained Full360 compact exercise completed two independent 360-case
assemblies. Both 14,420,587-byte package trees passed candidate dry-run
validation over 5,400 profile series and compared equal recursively. Their
independent 403-member ZIPs are each 11,514,743 bytes and byte-identical, with
SHA-256
`7a0c0842c34ecef9b67ed2e1d06fb979a10316f151e695c8038fbd96090bc066`.
That is a 99.4915% size reduction from the retained native-v1 ZIP. The exact
inactive-candidate receipt is
[`compact-profile-full360-validation-v1.json`](../../benchmark-specs/hiliftaeroml/compact-profile-full360-validation-v1.json).

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
