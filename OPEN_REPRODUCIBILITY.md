# Open reproducibility contract

FluidsBench uses the versioned `open-reproducibility-2.0` contract for real leaderboard results. Evaluation case IDs and ground
truth are public. The submitter supplies every reported scalar value and every prediction/profile value. FluidsBench validates the
submitted package, publishes its values in tables and plots, and displays submitted profiles against the pinned public ground truth.

FluidsBench does **not** execute the submitted model or code, regenerate predictions, or recompute base metrics from full prediction
fields. Approval means only that the submitted data passed the published validation and review process.

Every release manifest records this identifier as `data_release.reproducibility_contract_version`. Prototype dummy packages remain
on the historical submission schema and are visibly marked as prototypes. They are never approved results.

## Public evaluation-data policy

Public evaluation data may be used only to calculate the final submitted result. It must not be used for model fitting, early
stopping, checkpoint or model selection, hyperparameter selection, architecture selection, manual result tuning, or preprocessing
statistics. A real submission records `reproducibility.public_test_data_use="evaluation_only"` as an explicit declaration.

If any public evaluation data influenced the model or its configuration, the result is not eligible for an official ranking under
this contract. The submitter must disclose that use rather than make the `evaluation_only` declaration.

## Submitter-supplied data and open artifacts

A real `submitted_evaluation` package uses `schemas/v2/submission.schema.json` and includes:

- all scalar metric values and every required prediction/profile series;
- `evaluation-evidence.json` using schema v2, whose checksum binds the submitter-declared evaluation command, scalar values,
  dataset version, split digest, case set, profile index, and public profile-ground-truth comparison release;
- `reproducibility.contract_version`: exactly `open-reproducibility-2.0`;
- `access`: exactly `public`;
- `public_test_data_use`: exactly `evaluation_only`;
- an open result-data licence identifier covering submitted profiles and result metadata;
- a public HTTPS source-code repository, a full 40- or 64-character commit ID, and its open licence identifier;
- a public HTTPS model-artifact archive, its SHA-256 digest, and its open licence identifier;
- a public, hashed container or dependency lockfile; and
- public HTTPS artifact documentation.

The v2 schema accepts only these explicit open SPDX identifiers:

- result data: `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `ODC-BY-1.0`, or `ODbL-1.0`;
- code: `Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `MPL-2.0`, `EPL-2.0`, or the listed GPL,
  LGPL, and AGPL identifiers in `schemas/v2/submission.schema.json`; and
- model artifact: `Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `MPL-2.0`, `CC0-1.0`, `CC-BY-4.0`, or
  `CC-BY-SA-4.0`.

`PROPRIETARY` and arbitrary unrecognised strings are rejected. A missing licence can be proposed for the policy in a separate
repository-maintenance change; it must not be smuggled into an individual result package.

The code, model, environment, and documentation are required for openness, inspection, and reuse by the community. Their inclusion
does not imply that FluidsBench ran them. URLs must work without credentials. Maintainers review the declared access and licences;
the package hashes identify the exact submitted and referenced bytes.

The contributor leaves `approval` absent and does not add `maintainer-validation.json`.

```json
{
  "$schema": "https://fluidsbench.org/schemas/v2/submission.schema.json",
  "schema_version": "2.0",
  "reproducibility": {
    "contract_version": "open-reproducibility-2.0",
    "access": "public",
    "public_test_data_use": "evaluation_only",
    "result_data_license_spdx": "CC-BY-4.0",
    "code": {
      "repository_url": "https://github.com/example/model",
      "commit": "0123456789abcdef0123456789abcdef01234567",
      "license_spdx": "Apache-2.0"
    },
    "model_artifact": {
      "url": "https://example.org/releases/model-v1.tar.zst",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "license_spdx": "Apache-2.0"
    },
    "environment": {
      "kind": "lockfile",
      "url": "https://example.org/releases/model-v1.lock",
      "sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
    },
    "artifact_documentation_url": "https://github.com/example/model/blob/0123456789abcdef0123456789abcdef01234567/ARTIFACTS.md"
  },
  "profile_data": {
    "format": "fluidsbench-profile-chunks-v1",
    "index_file": "profiles/index.json",
    "case_count": 50,
    "case_set_id": "standard",
    "profile_ground_truth_release_id": "replace-with-release-id",
    "profile_ground_truth_manifest_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  }
}
```

The values above illustrate the structure only; they are not usable artifacts. CI validates the contributor package with:

```bash
python3 scripts/validate_submission.py --contributor-stage submissions/<dataset-id>/<submission-id>
```

The submitter copies the two `profile_ground_truth_*` values from `leaderboard/manifest.json` into `submission.profile_data` and the
v2 evaluation-evidence file. The validator requires both files to match each other and the manifest. This identifies the exact
public profile comparison data; it does not imply that profile ground truth contains the full fields used for submitted scalar
metrics.

Passing contributor validation means that the package is structurally complete and internally consistent. It does not approve the
result, establish that the supplied artifacts generated the supplied values, or include the package in the public leaderboard feed.

## Maintainer validation and approval

Maintainers review the submission and run the repository validator over the submitter-supplied files. Validation covers schemas,
identities, exact public split coverage, metric IDs and ranges, declared derived-score arithmetic, profile structure, finite values,
and the hash chain from the metadata through the evaluation evidence, profile index, and profile chunks. Maintainers also review
public artifact access, declared licences, and eligibility under the public evaluation-data policy.

The maintainer records this in `maintainer-validation.json`, which matches
`schemas/v2/maintainer-validation.schema.json`. It binds:

- the submission, dataset, split, case set, and evaluator/reference version;
- the exact public profile-ground-truth release and manifest digest declared by the submitter and used as the profile comparison
  basis;
- the validating maintainer and time;
- the canonical digest of contributor-authored submission metadata;
- the evaluation-evidence and submitted profile-index digests; and
- the explicit scope `submitted_data_only`, with model execution and base-metric recomputation recorded as `not_performed`.

A maintainer-owned approval change hashes that validation record under `approval.validation`, records the approver, approval date,
and pull-request URL, and rebuilds the feed. The associated pull request should use the `maintainer-validation` label for an obvious
audit trail. The approving and validating maintainer may be the same person, including when FluidsBench has a sole maintainer.

An approval is specific to the declared dataset version, public split digest, open-reproducibility contract version, code commit,
model digest, environment digest, evaluator/reference version, scalar values, profile bytes, and public ground-truth release.
Changing any of these requires a new submission ID and a new validation and approval.

The official scalar release is served from an immutable asset base containing its release ID; its separate full source-commit field
records repository provenance without a self-referential hash. Its manifest pins the complete scalar feed digest, every submitted
profile-index digest, and the release ID and manifest digest of the public profile ground truth. The
ground-truth manifest then pins every case-set index, and each index pins its chunks. Academic exports are enabled only after the
browser verifies these byte-level links.

The builder preserves an official release's explicit publication timestamp and treats an existing generated claim index as a seal:
changed feed or claim bytes cannot be rebuilt under the same release ID and URLs. Publishing changed contents requires a new safe
release ID with matching release-view and asset-base path segments.

For each feed row the release builder also publishes a hash-pinned result-claim record. It preserves the result's competition rank
within that exact release, dataset, and split, using the displayed metric precision, and binds the claim to the feed row and the
available submission, evaluation, profile, and maintainer-validation records. `data_release.release_view_url` identifies the
immutable interactive release snapshot; `data_release.archive_url` separately identifies the DOI or data-archive landing page.
Later releases may assign a different rank without changing the historical claim. Prototype claim records are explicitly ineligible
for academic citation and promotion.

## Contract changes and historical schemas

Version 2.0 replaces the former model-execution design. Historical v1 schema files remain in the repository so old prototype
records can still be interpreted, but v1 packages cannot become real or approved results. Real packages must use submission schema
2.0 and the `open-reproducibility-2.0` contract.

Clarifications that do not change eligibility or required fields may retain the identifier. Any material change to artifacts,
submitted-data validation, or comparison semantics receives a new contract version. Existing approved records retain the contract
version under which they were validated.
