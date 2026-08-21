# DrivAerML submission contract

The reviewed proposal is now the participant-facing candidate contract.
It uses the exact public DrivAerML release and the eight owner-published splits,
but submissions remain closed while the benchmark-owned evaluator and reference
artifacts complete their final scientific validation. Existing rows are clearly
labelled structural dummy fixtures and are not rankable results.

## Public data and split use

The source dataset is `neashton/drivaerml` at immutable revision
`7a5c0948ce27be709b1116a3a190f806e7a8f79f`. Each file in [`splits/`](splits/)
contains the exact ordered training, validation, and test case IDs from the
owner-published manifest. Test fields are public but evaluation-only: they must
not be used for fitting, tuning, checkpoint selection, manual selection, or
preprocessing statistics.

For every selected case:

1. Read every native surface polygon from `run_N/boundary_N.vtp` as `CellData`.
   Predict `pMeanTrim` and all three components of `wallShearStressMeanTrim` in
   raw VTK cell order. Use `run_N/boundary_cell_area_N.npy` for the primary
   area-weighted reductions; the equal-polygon values are mandatory secondary
   results.
2. Reconstruct the actual `run_N/volume_N.vtu` by byte-concatenating the exact
   ordered part list in [`proposal/native-source-pin.json`](proposal/native-source-pin.json).
   Ten cases have a `.02.part`, so code must not assume two parts. Predict
   `UMeanTrim` and `pMeanTrim` for every native `CellData` cell in raw VTK order.
   Score volume fields with one equal weight per native cell; no geometric
   cell-volume array or volume-weighted secondary metric is required.
3. Inference may process native entities in bounded-memory chunks. Each chunk
   must retain the raw native cell IDs and the chunks must form one complete,
   duplicate-free partition of the case. Sum additive numerators, denominators,
   counts, and weights across chunks; calculate one case metric only after the
   complete case is represented. Never average chunk-local L1, L2, MAE, or RMSE
   values.
4. Derive `Cd`, `Cl`, and `CmPitch` by integrating submitted surface pressure and
   wall shear with the defined constant-reference convention. The authoritative
   truth is `force_mom_constref_all.csv`; per-case
   `run_N/force_mom_constref_N.csv` files are convenience mirrors that must
   replay the matching aggregate row.
5. Extract the AutoCFD5 diagnostics defined in
   [`autocfd5-profiles-v8.json`](autocfd5-profiles-v8.json): 16 velocity lines on
   the candidate 10 mm grid and 209 unique pressure probes shown through 15
   ordered display panels. Once the contract is activated, the ranked velocity
   error will be the equal-case,
   equal-line mean of arc-length trapezoidal RMSE for `|U|/Uinf`. The ranked
   pressure error will be the equal-case mean of RMSE across 209 unique probes;
   probes repeated between display panels count only once in that ranked value.

Velocity validity is benchmark-owned support. Only coordinates confirmed to be
inside the morphed solid or outside the released fluid domain may be excluded.
Every other coordinate must map deterministically to a native volume cell or
the affected line, and therefore that case's ranked velocity component, is
unavailable. Every row remains explicit: the evaluator never snaps, silently
omits, interpolates, extrapolates, or bridges across an excluded point. The
candidate `1e-3` steradian polyhedron test is an angular numerical tolerance,
separate from the `1e-6 m` boundary tolerance; intermediate solid-angle results
fail closed. The all-case mask, tolerance replay, and owner approval are still
pending.

The primary leaderboard definition has nine components: four global fields,
three independently ranked field-integrated coefficients, the velocity profiles,
and the Cp probes. Each component uses unclipped physics-null skill
`100 * (1 - E/B)`, so a method worse than the null reference keeps a negative
score. `Clf` and `Clr` remain mandatory report-only diagnostics because they are
dependent on `Cl` and `CmPitch` and must not receive duplicate composite weight.

The complete machine-readable source of truth is
[`submission-spec.json`](submission-spec.json). Candidate evidence and its
eligibility status are indexed in [`evidence/README.md`](evidence/README.md);
history and paper-parity definitions remain in [`proposal/`](proposal/). The
exact work still needed before opening submissions is tracked in
[`ACTIVATION_CHECKLIST.md`](ACTIVATION_CHECKLIST.md).

The candidate evaluator's all-484 native-surface force replay is recorded in
[`evidence/force-replay-all484.json`](evidence/force-replay-all484.json). This
passing implementation evidence does not constitute owner approval or open
submissions.

The path-free native-volume evidence now includes both the original two-case
implementation pilot and the strict
[`all-484 equal-cell primary audit`](evidence/native-volume-equal-cell-primary-all484.json).
The latter verifies all 978 pinned segments and 68,949,662,110 native cells,
including exact field shape/order, finite values, complete coverage, and two
independent chunk partitions. It is not a model result or physics-null
baseline. This audit supplies the complete volume-field weighting evidence
because the contract uses equal native cells only.

The all-484 Cp candidate sweep retains every one of the 101,156 case/probe rows:
100,281 are valid and 875 are explicitly invalid. Its mapping, named-STL
inventory, truth replay, and compact atlas manifest are indexed in
[`evidence/README.md`](evidence/README.md). The invalid rows and review flags
still require owner disposition and visual sign-off, so these artifacts are not
official scoring support and cannot make a submission eligible.

The prescribed 1, 2, 5, and 10 mm profile study can be checked with
[`proposal/PROFILE_RESOLUTION_CONVERGENCE_INPUT.md`](proposal/PROFILE_RESOLUTION_CONVERGENCE_INPUT.md).
The prediction-based maintainer command described there verifies complete
native chunk manifests, streams the pinned multipart `UMeanTrim` truth, and
constructs the loss tensor itself. Reduced case pilots always remain
ineligible; owner-review eligibility additionally requires the exact ordered
484-case scope and the pending immutable owner validity-mask binding.
Activation evidence still requires complete all-case velocity mappings and
genuine predictions from at least three distinct trained model artifacts. Those
model predictions are not currently available and remain an owner input; no
real-model sensitivity result is claimed. Physics-null denominators and the
bootstrap remain blocked until the evaluator is frozen.

AutoCFD contributors can follow the bounded-memory native-mesh workflow in the
[`PARTICIPANT_GUIDE.md`](PARTICIPANT_GUIDE.md). A one-command synthetic
two-part/three-part dry run is provided under
[`examples/drivaerml-candidate-native-chunks/`](../../examples/drivaerml-candidate-native-chunks/);
it is an ineligible transport and packaging fixture, not an official
DrivAerML submission. Candidate native-volume support generation uses the exact
receipt-compatible runtime Python 3.12.13 and NumPy 2.2.6. Surface, Cp, and
velocity evidence remains pinned to VTK 9.5.2.
