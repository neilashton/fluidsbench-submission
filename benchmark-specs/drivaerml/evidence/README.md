# DrivAerML candidate evidence index

This directory contains implementation evidence and diagnostic pilot records
for the closed DrivAerML candidate contract. Presence here does not make an
artifact official scoring support, owner-approved evidence, or an accepted
submission. Repository-relative proposal, profile, and evidence paths in the
machine contract resolve from `benchmark-specs/drivaerml/`; upstream dataset
paths instead resolve within the pinned `neashton/drivaerml` release.
The same file identities and non-activation status are available to tooling in
[`manifest.json`](manifest.json).

| Artifact | SHA-256 | Scope and eligibility |
| --- | --- | --- |
| [`force-replay-all484.json`](force-replay-all484.json) | `631cd02c3a4215b254489652c1d93dfd781ecdb9478ff1ab11f24294743e8a17` | Passing candidate evaluator replay for all 484 cases, including fixed-area audit and chunk invariance. Dataset-owner scientific approval remains pending; this does not activate scoring. |
| [`native-volume-run1-run44-equal-cell-primary-pilot.json`](native-volume-run1-run44-equal-cell-primary-pilot.json) | `d009b6ac708fa320d21492b4cc44fc846b61e99b445836b5dedc704a934592d7` | Two-case implementation evidence for multipart reconstruction, native fields, raw order, complete coverage, and equal-cell primary metric invariance. It excludes physical-volume weights, covers only `run_1` and `run_44`, and is not scoring support. |
| [`cp-mapping-all484-hardened.json`](cp-mapping-all484-hardened.json) | `634e95279a2fb1078b3547616f29ddfc0a38ffe03f0b487fa0688be95aadbe81` | Complete candidate sweep over 484 cases and all 101,156 case/probe rows. It retains 100,281 valid rows and all 875 invalid rows with explicit reasons. Owner visual sign-off is false and public-scoring eligibility is false. |
| [`cp-stl-inventory-all484-hardened.json`](cp-stl-inventory-all484-hardened.json) | `cd4e1788a633196524b11f9d5f8868df05b71b11fed7fdf86892678c9cf41676` | Complete candidate named-STL inventory for 484 cases: 364,568,214 raw facets, 23,716 named solids, and 68,902,520,476 source bytes. It is deliberately separate from the native-source pin and is not scoring support. |
| [`cp-owner-review-atlas-all484-hardened.manifest.json`](cp-owner-review-atlas-all484-hardened.manifest.json) | `6a72536911010bdb741586018d1a13887f19756e135e8d35e6ea2da4b9fc7c4c` | Compact manifest for the external 488-page candidate review atlas. It covers all 484 cases and retains all 101,156 rows, including 875 invalid rows and 999 review-flagged rows. The external PDF is hash-bound as `e133fa14b6150c6f60590d19ba9b590072da0b758a19383976739c0f0fce654e`; neither visual sign-off nor scientific approval is claimed, and this does not activate scoring. |
| [`volume-cell-types-run_1-pilot.json`](volume-cell-types-run_1-pilot.json) | `63f4c794807fd4d327d2e5017db585b41047c758e1ca9eeb4d22f2010817092e` | Diagnostic-only native-cell inventory for `run_1`; it is not a volume-weight definition or positivity result. The mesh contains 6,349,119 `vtkPolyhedron` cells. |
| [`volume-cell-types-run_44-pilot.json`](volume-cell-types-run_44-pilot.json) | `4f3a1cc6bf1c4010daf4a94c2bdf56cc9fb4a684e8cb2610dce6f00bcf482f71` | Diagnostic-only native-cell inventory for `run_44`; it is not a volume-weight definition or positivity result. The mesh contains 7,509,644 `vtkPolyhedron` cells. |
| [`cp-mapping-run1-run44-pilot.json`](cp-mapping-run1-run44-pilot.json) | `7200e6a97356b8edffa9e7eb1cd22fe31d79daf8551a7a9405273a6c5591a0ea` | Discovery-only two-case Cp pilot. The file declares itself incomplete with `public_evidence_eligible=false` and `public_scoring_support_eligible=false`. It records seven invalid mappings, omits 482 official cases, and has no owner visual sign-off. It is implementation diagnostics, not scoring support. |
| [`cp-stl-inventory-run1-run44-pilot.json`](cp-stl-inventory-run1-run44-pilot.json) | `db2b4031bf0051a51c4709f90e11eaee8b3886b858ce96649aa381778c9c5b0a` | Discovery-only two-case named-STL inventory. The file declares itself incomplete with `public_evidence_eligible=false` and `public_scoring_support_eligible=false`. It is not the required all-case source inventory. |

## Current blockers

No accepted deterministic physical-volume weight array or aggregate exists.
The current VTK 9.5.2 `vtkCellSizeFilter` volume-only candidate did not pass the
strict requirement for one positive finite value per native cell on the real
pilot. The cell-type files above describe the mixed meshes only; they do not
validate a weight algorithm. Selecting and approving an algorithm or fallback
is an outstanding owner scientific decision.

The all-case Cp candidate sweep, source inventory, truth replay, and review
atlas are now hash-bound above. They do not resolve the 875 explicit invalid
rows or confer owner visual sign-off. The owner must review the atlas, approve
the disposition of every invalid or review-flagged row, and freeze an immutable
support release before these artifacts can be used for public scoring. The
two-case pilots remain discovery records only and must not be promoted.

## Provenance limits

The force aggregate was produced by
`scripts/audit_drivaerml_force_case.py` and
`scripts/aggregate_drivaerml_force_replay.py`. The native-volume aggregate was
produced by `scripts/audit_drivaerml_native_volume_case.py` and
`scripts/aggregate_drivaerml_native_volume_audits.py`. The Cp files were
produced by the candidate Cp builder, strict aggregator, and
`scripts/build_drivaerml_cp_owner_review_atlas.py`; the cell-type files were
produced by `scripts/audit_drivaerml_volume_cell_types.py`.

Current candidate source readers include retained-descriptor identity checks,
but the compact aggregate JSON files cannot by themselves demonstrate that
runtime mechanism. They record source hashes, dependency information where
available, and per-case receipt hashes, but the corresponding per-case receipts
and an exact generating Git commit are not bundled in this directory. The
20,883,275-byte atlas PDF is also external; only its SHA-256, page count, and
complete compact review manifest are committed. Those limits prevent the
directory alone from serving as an independently replayable immutable
scoring-support release.
