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
| [`native-volume-equal-cell-primary-all484.json`](native-volume-equal-cell-primary-all484.json) | `bda42a125ffb4d6484756e77ac7e495974f39d4bce3e663154322e9e560827c7` | Passing all-484 audit of 978 pinned VTU segments, native `CellData`, tuple/component counts, finite values, declared units, raw-cell order and complete duplicate-free coverage. Two chunk partitions agree within `2.22e-16` for additive statistics and `5.69e-14` for metrics. This is equal-cell primary evidence only, not a physical-volume-weight artifact, physics-null baseline, model result, or scoring support. |
| [`native-volume-equal-cell-primary-all484-provenance.json`](native-volume-equal-cell-primary-all484-provenance.json) | `b5ffe2234bb1597cf041ff5d97458f3d0d6e81db7a30591a7e26f51ebc032fde` | Path-free provenance for the all-484 audit: exact committed generator revision and source hashes, Python/NumPy runtime, launcher hash, scheduler scope, aggregate hash, and a canonical digest over all 484 external case-receipt identities. It does not turn the audit into scoring support or bundle the 10.7 MB receipt set. |
| [`volume-weight-vtk-run_1-failure-diagnostic.json`](volume-weight-vtk-run_1-failure-diagnostic.json) | `aa2a209cafbd598930bfbe2dd1a73e8c06108188aff69c30841bfc46bfe7927e` | Hash-bound fail-closed record for the rejected VTK 9.5.2 physical-volume candidate on `run_1`. Cell count and raw order were preserved, but raw cell ID 124,707,859 was a `vtkWedge` with volume `-9.740389723427085e-13 m^3`; no array or success receipt was published. This is rejection evidence, not scoring support. |
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
strict requirement for one positive finite value per native cell on `run_1`.
It preserved all 147,449,586 cells and exact raw IDs and found no non-finite or
zero values, but it produced one negative signed volume for a `vtkWedge`. The
hash-bound failure diagnostic records the exact algorithm, environment, source
snapshot, invalid cell, and external-log identity. It also records that no
array or success receipt was published and that no absolute value, mask, or
epsilon replacement was applied. The cell-type files above describe the mixed
meshes only; they do not validate a weight algorithm. Selecting and approving
a scientifically justified algorithm and raw-order mapping is an outstanding
owner decision.

The all-case Cp candidate sweep, source inventory, truth replay, and review
atlas are now hash-bound above. They do not resolve the 875 explicit invalid
rows or confer owner visual sign-off. The owner must review the atlas, approve
the disposition of every invalid or review-flagged row, and freeze an immutable
support release before these artifacts can be used for public scoring. The
two-case pilots remain discovery records only and must not be promoted.

## Provenance limits

The force aggregate was produced by
`scripts/audit_drivaerml_force_case.py` and
`scripts/aggregate_drivaerml_force_replay.py`. Both native-volume aggregates
were produced by `scripts/audit_drivaerml_native_volume_case.py` and
`scripts/aggregate_drivaerml_native_volume_audits.py`; the complete aggregate
strictly revalidated all 484 case receipts and was reproduced byte-for-byte.
Its companion provenance file binds the exact Git revision, runtime, launcher,
and the ordered hashes of the external case receipts.
The Cp files were
produced by the candidate Cp builder, strict aggregator, and
`scripts/build_drivaerml_cp_owner_review_atlas.py`; the cell-type files were
produced by `scripts/audit_drivaerml_volume_cell_types.py`. The physical-volume
failure diagnostic records an execution of the hash-bound
`reference/drivaerml/volume_weights.py` snapshot. Its 1,128-byte stderr log is
external and is bound by SHA-256 in the diagnostic; no generated weight array
or success receipt exists.

Current candidate source readers include retained-descriptor identity checks,
but compact aggregate JSON cannot by itself demonstrate that runtime mechanism.
The all-484 equal-cell audit now has a companion manifest binding its exact
generating Git commit, runtime, launcher, and ordered receipt identities; the
10.7 MB per-case receipt set remains external. Other candidate aggregates have
only the provenance recorded in their own files. The 20,883,275-byte atlas PDF
is also external; only its SHA-256, page count, and complete compact review
manifest are committed. Those limits prevent this directory alone from serving
as an independently replayable immutable scoring-support release.
