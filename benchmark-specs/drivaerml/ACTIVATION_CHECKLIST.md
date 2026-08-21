# DrivAerML activation checklist

This checklist separates the participant contract that is now defined from the
benchmark-owned evidence still needed before AutoCFD5 entrants should submit
official leaderboard results.

## Complete in the candidate

- The 484-case Hugging Face release is pinned by revision and per-file source
  inventory.
- All eight owner-published train/validation/test partitions are recognized as
  official, ordered, hash-bound, and use real `run_N` IDs.
- Surface predictions use native VTP `CellData`; volume predictions use native
  reconstructed VTU `CellData`. Both scalar and three-component target arrays are
  explicit.
- Per-case surface polygon areas are public and bound to the identical native
  polygon order. Surface primary metrics are area-weighted and secondary metrics
  are equal-polygon.
- Volume metrics use one equal weight per native cell. No geometric cell-volume
  array or volume-weighted secondary metric is required.
- The multipart VTU rule covers all 978 parts, including the ten three-part cases,
  and the inference/chunk reduction rule is explicit.
- The constant-reference force convention and field-integration equations are
  explicit. The authoritative tables provide `Cd`, `Cl`, `Clf`, and `Clr`
  columns. Candidate `CmPitch` truth is derived algebraically as
  `(Clf-Clr)/2`; accepting that derived moment as the benchmark convention
  remains pending owner scientific approval. `Clf`/`Clr` remain report-only.
- The submission-facing `drivaerml-diagnostics-v9.json` registry defines 16
  velocity lines and the four retained continuous Cp cuts. The combined v8
  registry and the 209-probe and 15-panel Cp registries are retained only as
  inactive research records; discrete Cp probes are excluded from participant
  submissions, evaluation, scoring, and activation.
- Four continuous Cp cuts remain in scope: upperbody centreline, underbody
  centreline, sidewall at `z=0.15 m`, and front-left wheelhouse at
  `y=-0.6 m`. Their extraction and scoring support are distinct from the
  excluded discrete probes and remain an activation task.
- The nine component weights and unclipped physics-null skill transform are
  executable in the reference score code: velocity profiles retain weight
  0.15 and the distinct continuous Cp-cut component retains weight 0.10.
  Pending scores cannot silently fall back to the old bounded caps.
- Prototype packages, generated feeds, and leaderboard panels use the new metric,
  split, and profile vocabulary while remaining ineligible dummy data.

## Candidate validation evidence completed

- The native pressure-plus-wall-shear force evaluator replayed all 484 cases
  against the authoritative aggregate table and every per-case mirror. All
  coefficients passed the `1e-6` absolute tolerance; the largest full-case
  versus chunked difference was `8.33e-17`. The same run audited all
  4,159,517,910 fixed surface-area entries without regenerating them. See
  [`evidence/force-replay-all484.json`](evidence/force-replay-all484.json)
  (SHA-256 `631cd02c3a4215b254489652c1d93dfd781ecdb9478ff1ab11f24294743e8a17`).
- The candidate native-volume audit reconstructed and checked `run_1` (two
  parts) and `run_44` (three parts): 103,499,978,583 pinned bytes, five exact
  segments, 349,274,643 points, and 310,848,384 native cells. Both required
  `CellData` fields had exact tuple/component counts, finite values, declared
  units, and complete raw-cell coverage. Two independent chunk partitions
  agreed within `1.48e-16` for additive statistics and `3.56e-15` for metrics.
  This directly exercises the contract's equal-cell volume weighting. The
  compact aggregate does not by itself prove the reader's retained-descriptor
  mechanism or bind an exact generating Git commit. See
  [`evidence/native-volume-run1-run44-equal-cell-primary-pilot.json`](evidence/native-volume-run1-run44-equal-cell-primary-pilot.json)
  (SHA-256 `d009b6ac708fa320d21492b4cc44fc846b61e99b445836b5dedc704a934592d7`).
- The same fail-closed native-volume audit then passed all 484 pinned cases:
  474 two-part and 10 three-part VTUs, all 978 verified segments,
  22,932,775,011,362 source bytes, and 68,949,662,110 native cells. It retained
  exact `CellData` association, tuple/component counts, finite values, declared
  units, raw-cell order, and complete duplicate-free coverage. Its two chunk
  partitions agreed within `2.22e-16` for additive statistics and `5.69e-14`
  for metrics. The all-zero prediction is an invariance fixture, not a model or
  physics-null result. No geometric volume-weight input is required.
  See [`evidence/native-volume-equal-cell-primary-all484.json`](evidence/native-volume-equal-cell-primary-all484.json)
  (SHA-256 `bda42a125ffb4d6484756e77ac7e495974f39d4bce3e663154322e9e560827c7`)
  and its path-free
  [`provenance manifest`](evidence/native-volume-equal-cell-primary-all484-provenance.json)
  (SHA-256 `b5ffe2234bb1597cf041ff5d97458f3d0d6e81db7a30591a7e26f51ebc032fde`).
- A deterministic candidate-v7 velocity containing-cell pilot completed for
  the pinned `run_1` two-part volume and `run_44` three-part volume. The compact
  aggregate accounts for all 134,768 requested assignments across 16 lines and
  the 1, 2, 5, and 10 mm grids, and hash-binds complete duplicate-free external
  row-level files: 130,279 rows are valid and all 4,489 invalid rows remain
  explicit there (4,476 no-closure rows and 13 fail-closed native-cell
  evaluation rows). A separate process reproduced the `run_1` receipt and all
  four mapping files byte-for-byte. See
  [`evidence/velocity-mapping-run1-run44-candidate-v7-pilot.json`](evidence/velocity-mapping-run1-run44-candidate-v7-pilot.json)
  (SHA-256 `91a7bb4cb7b7c6167c3577f62745021409c93cebc6b2685a57cdfe1debc06d76`)
  and its path-free
  [`provenance manifest`](evidence/velocity-run1-run44-candidate-v7-pilot-provenance.json)
  (SHA-256 `be785d01618584691a60bba9faa8125376ac788dae1cfeeaf763e97fc7ff767e`).
  This is geometry-only implementation evidence, not all-case or tolerance-
  replay evidence; it uses no model checkpoint or prediction fields and makes
  no convergence, model-ordering, validity-mask, approval, or scoring claim.
- The candidate real-reference driver passed on the pinned real `run_1` and
  `run_44` inputs using exact two- and three-part native-volume transport. Its
  deterministic all-zero fixture has complete duplicate-free native-cell
  coverage: 20 surface chunks cover 18,903,869 polygons and 312 volume chunks
  cover 310,848,384 cells. The run consumed the fixed surface-area arrays,
  historical candidate discrete-probe Cp supports, and 10 mm velocity mappings,
  used one equal weight per native volume cell, and verified identical
  prediction artifacts across the core and diagnostic evaluators. The probe
  input records what that historical fixture consumed; it is not current Cp-cut
  support, a submission requirement, or a scoring dependency. See the
  byte-identical
  [`validation receipt`](evidence/real-reference-driver-run1-run44-candidate-v7-pilot.json)
  (SHA-256 `da80aebb11eb18d3bb66b7a968a94e9a779a6e60f5413ef73d2fbd6485d76572`)
  and its path-free
  [`provenance manifest`](evidence/real-reference-driver-run1-run44-candidate-v7-pilot-provenance.json)
  (SHA-256 `24fd18d70098e5943959c8f37e2cd0ade211322e0785734d0dd035200db8fff2`).
  The zero values test transport and reduction only; they are not a trained
  model, physics-null baseline, participant dry run, or scientific result.
- The hardened Cp research sweep covered all 484 cases and retained all
  101,156 case/probe rows: 100,281 valid and 875 explicitly invalid. Its source
  inventory covers 364,568,214 raw STL facets, and the 488-page external review
  atlas keeps every failure visible. The mapping, inventory, and compact atlas
  manifest are hash-bound under [`evidence/README.md`](evidence/README.md).
  Following the owner decision on 2026-08-21, these artifacts are retained only
  as inactive research evidence. They are not submission or scoring support,
  and their invalid rows and lack of visual sign-off are not activation
  blockers.

## Required before submissions open

1. Obtain owner scientific approval of the completed candidate all-case native
   array evidence. The all-484 volume replay now covers association, tuple and
   component counts, finite values, declared units, stable raw IDs, complete
   coverage, and chunk invariance. The all-484 surface force replay separately
   binds native surface fields and fixed-area ordering. Owner approval of the
   pressure gauge, wall-shear sign, exclusion policy, and the combined evidence
   remains pending.
2. Promote the implemented and tested candidate dataset loader/evaluator into a
   frozen production evaluator. Before activation, it must bind every schema-v3
   nonspatial metric value to dataset-specific validation and publish
   a normalized immutable scoring-support digest. The current candidate covers
   native VTP, reconstructed VTU, fixed area inputs, fields, forces, and
   diagnostic profiles; its all-case equal-cell volume replay and chunk golden
   evidence are complete. Final validation now fails closed unless the
   maintainer receipt matches a benchmark-owned frozen evaluator version and
   immutable Git revision; that binding remains deliberately pending with no
   revision while the evaluator is still a candidate. The remaining production
   gates are not complete. The explicit two-case
   [`real_reference_driver.py`](../../examples/drivaerml-candidate-native-chunks/real_reference_driver.py)
   execution subgate is now complete on the pinned real `run_1` and `run_44`
   inputs, with its validation receipt and provenance indexed above. That
   fixture does not freeze the evaluator, publish an immutable scoring-support
   digest, validate all 484 cases through this driver, or confer owner approval;
   this production-evaluator gate therefore remains open.
3. Obtain dataset-owner scientific review of the completed all-484 force replay
   and its tolerance choices. The numerical replay, mirror checks, axle-load
   closure, fixed-area audit, and chunk-invariance evidence are complete at the
   path above; owner approval is not.
4. Publish and hash every case/line containing-cell assignment for the 16 velocity
   profiles. Run the prescribed 1, 2, 5, and 10 mm convergence study and method
   ordering test before retaining 10 mm as the ranked grid. All 2, 5, and 10 mm
   comparisons against the 1 mm reference must pass; a passing 10 mm result
   cannot hide a failed finer candidate. The hash-bound two-case candidate-v7
   pilot now accounts for complete explicit mapping rows in hash-bound external
   files for `run_1` and `run_44` at the primary 1 micrometre geometric
   tolerance, including fail-closed invalid rows and separate-process
   determinism. It does not cover the remaining 482 cases, the required
   0.5/1/2 micrometre replay, prediction convergence, or method ordering. The
   candidate `1e-3` steradian polyhedron-
   classification tolerance now has explicit fail-closed semantics: boundary
   distance is tested first, winding totals within `1e-3` of `0` or `4*pi` are
   outside or inside respectively, and every intermediate or non-finite result
   is unresolved. It remains pending the all-case replay and owner scientific
   approval. Before convergence can be owner-review eligible, publish one
   immutable 1 mm master validity mask covering all 18,109,344
   case/line/sample keys, derive the 2, 5, and 10 mm masks only by strides 2,
   5, and 10, and publish included, excluded, and unresolved counts and hashes.
   Only `inside_morphed_solid` and `outside_released_fluid_domain` may be owner
   exclusions; every other sample must map, every required line must retain
   positive included arc length, and unresolved rows must be zero. The current
   mask binding is empty/pending, so no pilot `no_native_cell...` or cell-
   evaluation failure is an approved exclusion. Bind the mask SHA-256 into the
   evaluator evidence and version the profile-display schema so excluded rows
   carry explicit validity and reason fields rather than fabricated numeric
   placeholders. The
   candidate prediction-based reducer now verifies complete native chunk manifests,
   streams pinned multipart `UMeanTrim` truth, separates geometric assignment
   invariance from loss/method-order convergence, and refuses owner-review
   eligibility for any reduced pilot. Its synthetic tests are not real-model
   evidence. Complete all-case assignments, the genuine prediction artifacts,
   and the real convergence replay remain outstanding. The current reducer is
   bounded-memory but single-process and non-resumable; immutable per-case
   worker receipts plus strict restartable aggregation remain an execution-
   hardening gate before the all-484, five-method replay.
5. Define, publish, and hash the case-specific extraction support for exactly
   four continuous Cp cuts: upperbody centreline (`y=0`), underbody centreline
   (`y=0`), sidewall (`z=0.15 m`), and front-left wheelhouse (`y=-0.6 m`).
   Freeze their plane-intersection tolerance, curve segmentation,
   anatomical-component inclusion rules, coordinate and orientation,
   branch/degeneracy handling, deterministic realization of the fixed
   equal-case/equal-cut native-segment-length-weighted RMSE, and all-case truth
   hashes. Prove tolerance stability and chunk invariance; no resampled Cp grid
   or separate cut-resolution study is part of this definition. This gate
   concerns continuous cuts only;
   the 209 discrete probes, their atlas, and their 875 invalid mappings are
   inactive research evidence and are not part of the gate.
6. After the evaluator is frozen, evaluate the physics-null predictions for every
   split and component and publish the nine finite positive `B_j` denominators.
   Then run the nearest-training-design control, genuine three-real-model
   sensitivity study, and paired 10,000-replicate bootstrap specified by the
   proposal. Predictions from three distinct trained model artifacts are not
   currently available and remain an explicit owner input; no sensitivity result
   is claimed. The null denominators and bootstrap are also blocked until the
   evaluator is frozen.
7. Freeze an immutable scoring-support release and profile-ground-truth release,
   add the publication-validation receipt, bind schema-v3 nonspatial values to
   the frozen dataset-specific evaluator, update the candidate evaluator and
   dataset versions to immutable release IDs, and change the composite status to
   `active` with its nine baseline errors. Include the frozen four-cut Cp
   support, but keep the 209-probe artifacts outside that release.
8. Run at least one end-to-end schema-v3 dry-run submission from an independent
   AutoCFD5 participant. After dataset-owner review, set scoring support to
   `official` and only then set `submissions_open` to `true`.

Until all eight steps pass, the format is suitable for implementation and dry-run
feedback, but not for official workshop ranking or citation.
