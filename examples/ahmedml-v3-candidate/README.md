# AhmedML schema-v3 genuine-inference candidate

This directory is a reusable configuration template, not a submission. The
AhmedML native evaluator remains a closed owner-review candidate and public
submissions are not open. Development candidate PRs are accepted against `dev`.
The assembler creates an unapproved candidate package
for any of the eight official split labels only after all placeholder tokens,
checkpoint hashes, complete evaluator evidence, and spatial records agree.

The genuine-inference path is separate from
`assemble_ahmedml_schema_v3_dev_fixture.py`. It does not accept
`prototype_fixture` methodology and never reads fixture provenance. It requires
an explicit attestation that every prediction was produced by actual model
inference and not generated from evaluation truth, and verifies the local bytes
of every checkpoint named by the methodology record.

<a id="inputs"></a>

Use the shared [hardware and compute fields](../../METHODOLOGY.md#hardware-and-compute)
for each training stage and inference campaign, including GPU model and allocation counts.

## Inputs and blockers

Copy `package-config.template.json` outside the repository and replace every
`__REPLACE_...__` value with the actual method record. The fixed release
bindings must continue to equal the repository candidate; do not invent or
silently update them. Check unresolved values without touching evaluator data:

```bash
python scripts/assemble_ahmedml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --list-unresolved
```

For each case in the selected split, first run the candidate evaluator against
the complete surface and volume native-order prediction manifests:

```bash
python scripts/evaluate_ahmedml_candidate_case.py \
  --case-id run_N \
  --dataset-root /path/to/ahmedml-public-revision-02688c7 \
  --case-support /path/to/local-support/run_N/manifest.json \
  --surface-prediction-manifest /path/to/predictions/run_N/surface/manifest.json \
  --volume-prediction-manifest /path/to/predictions/run_N/volume/manifest.json \
  --output /path/to/case-evidence/run_N.json
```

The prediction transport may be chunked, but it must cover every native cell
exactly once and preserve native order. The evaluator derives all field scores,
Cd/Cl, three moving-geometry Cp cuts, four moving-geometry wake profiles, and
surface/volume regional diagnostics from those same fields. Participant-authored
profile values are not accepted.

Create one JSONL spatial record per case in exact split order. Each record uses
the schema-v3 discretization-case format and reports the actual model input,
direct-output, and mapping counts. Reusing native meshes, sampling model points,
or mapping predictions back to native cells must be described rather than
silently normalized by the assembler.

<a id="assemble-and-validate"></a>

## Commands: assemble and validate

```bash
python scripts/assemble_ahmedml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --case-evidence-directory /path/to/case-evidence \
  --dataset-evidence /path/to/optional-retained-split-reduction.json \
  --discretization-cases /path/to/discretization/cases.jsonl \
  --checkpoint surface-model=/path/to/surface/model_best.pt \
  --checkpoint volume-model=/path/to/volume/model_best.pt \
  --output submissions/ahmedml/ahmedml-my-model-full-v1

python scripts/validate_submission.py \
  --dev-intake --contributor-stage \
  submissions/ahmedml/ahmedml-my-model-full-v1
```

The assembler automatically downloads the exact profile-ground-truth manifest pinned by
`leaderboard/manifest.json` and verifies its SHA-256 and release ID. No maintainer-supplied
file is required. For an offline evaluator, download it once on a connected machine:

```bash
python scripts/fetch_profile_ground_truth.py --output /path/to/profile-ground-truth/manifest.json
```

Then pass `--profile-ground-truth-manifest /path/to/profile-ground-truth/manifest.json`
to the assembler. Keep the bytes unchanged; reformatting JSON changes its checksum.

Use exactly one `--checkpoint ID=PATH` for each methodology checkpoint ID. A
single joint model needs one argument; separate surface and volume models need
two. The optional retained dataset evidence is compared byte-for-data with a
fresh reduction; the assembler always recomputes the split from per-case
evidence.

## Outputs

The output contains prediction-only profile chunks with exactly seven series
per case and 128 values per series, complete per-case sufficient statistics,
discretization evidence, and zero-weight regional diagnostics. It contains no
`approval`, maintainer validation, or official claim.

## Submit the development candidate

1. Update your fork from the upstream `dev` branch before assembling the package.
2. Run the assembler and `--dev-intake --contributor-stage` validator above.
3. Commit only `submissions/ahmedml/<submission-id>/` and open a PR targeting **`dev`**.
4. Complete the contributor checklist and let the normal PR checks run.

CI selects development intake automatically for PRs targeting `dev`. A passing candidate
can be reviewed and merged without changing its package, registering it, modifying
specifications, or regenerating feeds. It stays unapproved and out of the leaderboard.
`main` continues to require an official open release. `--candidate-dry-run` remains
available for isolated local evaluation checks, but is not the contributor PR command.

## Optional dev-only pre-release registration

Maintainer-only registration can expose a reviewed candidate on the dev feed. This is a separate optional publication step, not a submission prerequisite. Candidate intake alone does not publish or approve the result.

<details>
<summary>Inspect or register an immutable pre-release binding</summary>

After the package passes the candidate dry run and is stored at its conventional
repository path, inspect its proposed exact binding:

```bash
python scripts/register_ahmedml_pre_release.py \
  submissions/ahmedml/ahmedml-my-model-full-v1/submission.json
```

The proposal pins the submission, every declared artifact, all checkpoint
digests, split/case/profile coverage, and a logical hash of every package file.
It changes nothing. A maintainer can append that exact reviewed binding with:

```bash
python scripts/register_ahmedml_pre_release.py \
  --register \
  submissions/ahmedml/ahmedml-my-model-full-v1/submission.json

python scripts/manage_leaderboard.py build --dev-intake
```

Registration affects only the prototype dev feed. The resulting row is labeled
`pre_release_reference`, remains non-citable and non-promotable, and disappears
from an official feed unless it later follows the separate owner approval
workflow. Any changed package byte invalidates the registration.

</details>
