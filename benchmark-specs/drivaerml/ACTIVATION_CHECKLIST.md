# DrivAerML activation checklist

This checklist separates the participant contract that is now defined from the
benchmark-owned evidence still needed before AutoCFD5 entrants should submit
official leaderboard results.

## Complete in the candidate

- The 484-case Hugging Face release is pinned by revision and per-file source
  inventory.
- All eight owner-published train/validation/test partitions are active, ordered,
  hash-bound, and use real `run_N` IDs.
- Surface predictions use native VTP `CellData`; volume predictions use native
  reconstructed VTU `CellData`. Both scalar and three-component target arrays are
  explicit.
- Per-case surface polygon areas are public and bound to the identical native
  polygon order. Surface primary metrics are area-weighted and secondary metrics
  are equal-polygon.
- Volume primary metrics are equal-native-cell. Cell-volume-weighted secondary
  metrics are part of the required metric vocabulary.
- The multipart VTU rule covers all 978 parts, including the ten three-part cases,
  and the inference/chunk reduction rule is explicit.
- The constant-reference force convention, field-integration equations, `Cd`,
  `Cl`, `CmPitch`, and report-only `Clf`/`Clr` roles are explicit.
- The AutoCFD5 v8 registries define 16 velocity lines, 209 unique Cp probes, and
  15 pressure display panels.
- The nine component weights and unclipped physics-null skill transform are
  executable in the reference score code. Pending scores cannot silently fall
  back to the old bounded caps.
- Prototype packages, generated feeds, and leaderboard panels use the new metric,
  split, and profile vocabulary while remaining ineligible dummy data.

## Required before submissions open

1. Publish the deterministic per-native-cell volume array (or a frozen evaluator
   algorithm that produces it), with per-case counts, positive/finite checks,
   aggregate QA, hashes, dependency versions, and chunk-invariance golden tests.
2. Complete the all-case native array audit: association, tuple and component
   counts, finite values, units, pressure gauge, wall-shear sign convention,
   stable IDs, exclusions, and exact correspondence to the surface-area arrays.
3. Implement the dataset-specific scoring-support loader/evaluator for native VTP,
   reconstructed VTU, area/volume weights, fields, forces, and profiles. Publish
   full-case versus chunked golden tests and a normalized support digest.
4. Replay the explicit pressure-plus-wall-shear force integration for all 484
   cases against `force_mom_constref_all.csv`, including coefficient, moment,
   axle-load closure, tolerance, and chunk-invariance reports.
5. Publish and hash every case/line containing-cell assignment for the 16 velocity
   profiles. Run the prescribed 1, 2, 5, and 10 mm convergence study and method
   ordering test before retaining 10 mm as the ranked grid.
6. Publish and hash every case/probe Cp mapping, named-STL source inventory,
   bridge checks, overrides, and the all-case `Cp=2*pMeanTrim/Uinf^2` replay.
   Complete the owner visual atlas sign-off; no failed case or probe may be
   silently omitted.
7. Evaluate the frozen physics-null predictions for every split and component to
   publish the nine finite positive `B_j` denominators. Then run the nearest-
   training-design control, real-model sensitivity, and paired 10,000-replicate
   bootstrap specified by the proposal.
8. Freeze an immutable scoring-support release and profile-ground-truth release,
   add the publication-validation receipt, update the candidate evaluator and
   dataset versions to immutable release IDs, and change the composite status to
   `active` with its nine baseline errors.
9. Run at least one end-to-end schema-v3 dry-run submission from an independent
   AutoCFD5 participant. After dataset-owner review, set scoring support to
   `official` and only then set `submissions_open` to `true`.

Until all nine steps pass, the format is suitable for implementation and dry-run
feedback, but not for official workshop ranking or citation.
