# DrivAerML FluidsBench schema-v3 candidate package

This directory is a configuration template, not a submission and not scoring
support. It deliberately contains `__REPLACE_...__` participant fields and
`__UNRESOLVED_DRIVAERML_...__` owner-release fields. Those strings are
machine-detectable blockers; they are not example hashes or release IDs.

Copy `package-config.template.json` outside the repository, fill the
participant fields, and use the immutable release values published by the
DrivAerML benchmark owner. Check what remains before attempting assembly:

```bash
python scripts/assemble_drivaerml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --list-unresolved
```

The token report does not validate repository bindings or evaluator outputs;
successful assembly is the authoritative readiness check. Once the
owner-release fields are published and the frozen evaluator produces
a complete `metrics/cases.json` and `profiles/` directory, assemble the
participant-owned files with:

```bash
python scripts/assemble_drivaerml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --case-metrics /path/to/metrics/cases.json \
  --profiles /path/to/profiles \
  --discretization-cases /path/to/discretization/cases.jsonl \
  --output /path/to/drivaerml-my-model-v1
```

The assembler derives dataset and split identities from the checked-in
DrivAerML specification, canonicalizes the participant files, creates the
hash-bound `submission.json`, `evaluation-evidence.json`, and
`discretization.json`, and schema-checks the result. It refuses unresolved
tokens, incomplete or reordered cases, missing metrics or profiles, mismatched
release bindings, and an existing output directory.

Evaluator-produced `metrics/cases.json` and `profiles/index.json` must already
carry the exact submission, split, case-set, and release identities supplied to
the evaluator; the assembler rejects conflicts instead of rewriting them. It
also verifies every source profile chunk against the evaluator's input index
before canonicalizing it. Only the participant-authored per-case
`discretization/cases.jsonl` may omit its repeated schema/submission/dataset/
split identity fields; the assembler inserts those fields and rejects any
conflicting value that is present.

The frozen evaluator Git revision is benchmark-owned and remains in the
scoring-support contract. The optional `evaluation.code_revision` field has a
different meaning: it identifies the participant's public model code. The
assembler omits it when `participant.reproducibility.code` is absent; when that
block is supplied, it copies the participant code commit into both submission
and evidence records.

The output contains no `approval`, `maintainer-validation.json`, or
`prediction-artifact-checks.json`; those are not contributor-owned records.
Complete native prediction artifacts are optional and are intentionally not
added by this initial assembler.
