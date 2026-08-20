# DrivAerML submission contract

The reviewed proposal is now the active participant-facing candidate contract.
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
   Equal-cell reductions are primary and cell-volume-weighted reductions are
   mandatory secondary results.
3. Inference may process native entities in bounded-memory chunks. Each chunk
   must retain the raw native cell IDs and the chunks must form one complete,
   duplicate-free partition of the case. Sum additive numerators, denominators,
   counts, and weights across chunks; calculate one case metric only after the
   complete case is represented. Never average chunk-local L1, L2, MAE, or RMSE
   values.
4. Derive `Cd`, `Cl`, and `CmPitch` by integrating submitted surface pressure and
   wall shear with the frozen constant-reference convention. The authoritative
   truth is `force_mom_constref_all.csv`; per-case
   `run_N/force_mom_constref_N.csv` files are convenience mirrors that must
   replay the matching aggregate row.
5. Extract the AutoCFD5 diagnostics defined in
   [`autocfd5-profiles-v8.json`](autocfd5-profiles-v8.json): 16 velocity lines on
   the candidate 10 mm grid and 209 unique pressure probes shown through 15
   ordered display panels. The ranked velocity error is the equal-case,
   equal-line mean of arc-length trapezoidal RMSE for `|U|/Uinf`. The ranked
   pressure error is the equal-case mean of RMSE across 209 unique probes;
   probes repeated between display panels count only once in that ranked value.

The primary leaderboard definition has nine components: four global fields,
three independently ranked field-integrated coefficients, the velocity profiles,
and the Cp probes. Each component uses unclipped physics-null skill
`100 * (1 - E/B)`, so a method worse than the null reference keeps a negative
score. `Clf` and `Clr` remain mandatory report-only diagnostics because they are
dependent on `Cl` and `CmPitch` and must not receive duplicate composite weight.

The complete machine-readable source of truth is
[`submission-spec.json`](submission-spec.json). The history, evidence, and
paper-parity definitions remain in [`proposal/`](proposal/). The exact work still
needed before opening submissions is tracked in
[`ACTIVATION_CHECKLIST.md`](ACTIVATION_CHECKLIST.md).
