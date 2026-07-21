# Open reproducibility contract

FluidsBench uses the versioned `open-reproducibility-1.0` contract for real leaderboard results. Evaluation case IDs and
ground truth are public. An approved result must be reproducible from public, pinned artifacts by a maintainer who is independent
of the submitter.

Every release manifest records this identifier as `data_release.reproducibility_contract_version`.

Prototype dummy packages are exempt from this contract and remain visibly marked as prototypes. They are never approved results.

## Public evaluation-data policy

Public evaluation data may be used only to calculate the final submitted result. It must not be used for model fitting, early
stopping, checkpoint or model selection, hyperparameter selection, architecture selection, manual result tuning, or preprocessing
statistics. A real submission records `reproducibility.public_test_data_use="evaluation_only"` as an explicit declaration.

If any public evaluation data influenced the model or its configuration, the result is not eligible for an official ranking under
this contract. The submitter must disclose that use rather than make the `evaluation_only` declaration.

## Required contributor artifacts

A real `submitted_evaluation` package includes a `reproducibility` object with:

- `contract_version`: exactly `open-reproducibility-1.0`;
- `access`: exactly `public`;
- `public_test_data_use`: exactly `evaluation_only`;
- an open result-data licence identifier covering submitted profiles and result metadata;
- a public HTTPS source-code repository, a full 40- or 64-character commit ID, and its open licence identifier;
- a public HTTPS model-artifact archive, its SHA-256 digest, and its open licence identifier;
- a public, hashed container or dependency lockfile; and
- public HTTPS replay instructions.

The source repository must contain everything required to load the public dataset, reconstruct preprocessing, load the declared
model artifact, run inference, and calculate the submitted metrics and profiles. URLs must work without credentials. The SHA-256
digests identify the exact bytes replayed; maintainers also review whether the declared code and model licences permit public use,
inspection, modification, and redistribution.

The contributor leaves `approval` absent and does not add `maintainer-replay.json`.

```json
{
  "reproducibility": {
    "contract_version": "open-reproducibility-1.0",
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
    "replay_instructions_url": "https://github.com/example/model/blob/0123456789abcdef0123456789abcdef01234567/REPRODUCE.md"
  }
}
```

The values above illustrate the structure only; they are not usable artifacts. CI validates this stage with:

```bash
python3 scripts/validate_submission.py --contributor-stage submissions/<dataset-id>/<submission-id>
```

Passing contributor validation means the package is structurally complete and eligible for replay. It does not mean FluidsBench
has reproduced or approved the result, and an unapproved package is not included in the public leaderboard feed.

## Independent maintainer replay

After eligibility review, the contributor package is merged while still unapproved and absent from public feeds. An independent
maintainer then downloads the declared public artifacts, verifies their digests and licences, and follows the replay instructions
in a clean environment. The maintainer records the actual replay command and output in `maintainer-replay.json`, including:

- the replaying maintainer and a conflict-of-interest disclosure;
- the exact code, model, and environment identities;
- independently calculated metric values and an absolute comparison tolerance no greater than `0.001`;
- the canonical digest of all contributor-authored submission metadata; and
- separate SHA-256 values for the submitted and replay-generated profile indexes.

The replay record also identifies the exact evaluator/reference release declared by the dataset specification. A dataset cannot
accept a real submission until its official specification pins that evaluator release.

Version 1.0 requires the replay-generated profile index to match the submitted index exactly. This deliberately strict rule keeps
profile provenance unambiguous; a future contract version may define a numeric profile comparison if cross-platform serialization
proves impractical.

The person approving a result may be different from the person who performed the replay. Neither may be the named submitter. A
protected maintainer workflow on a maintainer-owned branch hashes `maintainer-replay.json`, adds that hash under
`approval.replay`, records the approval metadata, rebuilds the feed, and merges the result. The follow-up pull request uses the
`maintainer-replay` label for auditability; normal schema, replay, and feed validation still runs.

An approval is specific to the declared dataset version, public split digest, open-reproducibility contract version, code commit,
model digest, environment digest, evaluator version, metrics, and profiles. Changing any of them requires a new replay and approval.

The official scalar release is served from an asset base containing its full source commit. Its manifest pins the complete scalar
feed digest, every submitted profile-index digest, and the release ID and manifest digest of the public profile ground truth. The
ground-truth manifest then pins every case-set index, and each index pins its chunks. Academic exports are enabled only after the
browser verifies these byte-level links.

## Contract changes

Fields and validation rules may be clarified without changing the identifier, but any change that alters eligibility, required
artifacts, or replay comparison semantics receives a new contract version. Existing approved records retain the contract version
under which they were replayed.
