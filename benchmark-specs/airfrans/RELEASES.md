# AirfRANS approved dev release drafts

**Development only:** the contract is approved, and the artifacts are prepared
and validated. No GitHub release has been published, no release locking is
enabled, and neither `main` nor the production site is changed. Proposed release
URLs are reserved destinations and do not yet serve downloads. Drafts can be
corrected and regenerated during review.

The first approved evaluation draft covers Full and Scarce (the same ordered
200-case evaluation set) and AoA extrapolation (196 cases). Its native field,
curve, force, and lossless profile truth covers 355 unique cases. Reynolds
extrapolation remains unpublished and closed; 318 of its 496 cases are outside
this release's case universe.

Neil Ashton approved publication of the existing scoring contract and these
support/truth releases on 7 October 2026. The approval covers the declared
physical/equal-entity reductions, vector semantics, additive chunk reductions,
equal-case aggregation, force coefficients, boundary-layer extraction, bounded
profile R2, and the existing overall-score weights and caps.

The draft prepares a separately versioned approved contract. The active
prototype specification and existing pre-release reference packages retain
their historical identities. Switching real contributor intake to the official
contract requires a separate dev submission trial and activation change. No
participant result is approved or ranked by this publication.

The release binding, approval record, local artifact validation, proposed download
URLs, and SHA-256 digests are recorded under `releases/`. Participant prediction
fields and model inference were not rerun as part of truth publication. Native
support artifacts and lossless profile arrays retain their verified handover
bytes; changed release metadata is independently hash-bound.

## Proposed release identities

- Contract: [`airfrans-evaluation-v1`](releases/airfrans-evaluation-v1/airfrans/submission-spec.json).
- Dataset version: `airfrans-native-v1`.
- Evaluator version: `airfrans-scoring-v2`; the scientific implementation is
  pinned to `b320575e35d6f61f94ac852fdb084dec080e4ecb`.
- Native scoring support: [airfrans-native-support-v1](https://github.com/neilashton/fluidsbench-submission/releases/tag/airfrans-native-support-v1).
- Lossless profile truth: [airfrans-native-profile-truth-v1](https://github.com/neilashton/fluidsbench-submission/releases/tag/airfrans-native-profile-truth-v1).
- Approval: [PR #47](https://github.com/neilashton/fluidsbench-submission/pull/47),
  with the exact release bindings in [`official-release-binding.json`](official-release-binding.json).

The score weights are unchanged: curve pressure 15%, curve wall shear 10%,
domain velocity 15%, domain pressure 10%, drag R2 15%, lift R2 10%, and boundary
layer profile R2 25%. Field caps remain 15, 20, 12, and 15 respectively. Curve
primary errors use native dual lengths; domain primary errors use equal native
nodes. Alternate equal-entity/physical-weight errors remain diagnostics. The
four profile stations, two Cartesian quantities, and 1,001 samples per series
remain bound to `airfrans-boundary-layer-v1`.

## Install and verify locally; public downloads are pending

Use the source repository on this dev branch. Local prepared asset directories
contain `SHA256SUMS`; check it before extracting. Public downloads and tags are
pending a separate publication decision. The support assets include their JSON
schemas so the draft can be audited with its own schema version.

Extract `support-metadata.tar.gz` and `native-tables.tar` into the same empty
directory. The resulting `manifest.json`, `case-sets/`, and `tables/` constitute
the installed support release. Archive-backed artifact descriptors bind both
the archive digest and each individual member digest. The evaluator reads only
verified installed members and performs no automatic network fetch.

```bash
python scripts/publish_airfrans_official_release.py --verify-native /path/to/installed/support
```

Extract `profile-truth.tar.gz` into a different empty directory, then validate:

```bash
python scripts/validate_airfrans_profile_truth.py --release /path/to/installed/profile-truth
```

Native publication validation loads 1,188 support instances across the two
ordered case sets (396 case references, 355 unique cases). Full profile-truth
validation checks all 355 lossless case artifacts and their source-mesh,
extractor, runtime, case-set, and hash bindings. CI checks the committed metadata
graph and publication receipt without downloading the large arrays.

The approved contract is staged separately while the active prototype
contract retains historical fixtures. Real contributors must wait for the dev
intake activation change, which will select the official release and run the
complete contributor-to-maintainer approval trial. Reynolds support is absent
from the official contract and cannot be submitted under these release IDs.
