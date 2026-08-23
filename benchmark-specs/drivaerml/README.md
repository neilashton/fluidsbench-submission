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

The native surface-area weights are now public in that same pinned Hugging Face
release. The authoritative `surface_cell_areas/manifest.json` has SHA-256
`1401c7e80bd86f3aa2d640289db9b088ce1e0825327e18eeb1ab2852de04323e`
and binds 484 `run_N/boundary_cell_area_N.npy` payloads to 4,159,517,910 raw
boundary polygons. FluidsBench uses those published arrays directly and does
not regenerate areas during evaluation.

For every selected case:

1. Read every native surface polygon from `run_N/boundary_N.vtp` as `CellData`.
   Predict `pMeanTrim` and all three components of `wallShearStressMeanTrim` in
   raw VTK cell order. Use `run_N/boundary_cell_area_N.npy` for the primary
   area-weighted reductions; the equal-polygon values are mandatory secondary
   results. Verify each payload against the public manifest and its case record;
   never apply it to a reordered, remeshed, triangulated, or STL surface.
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
4. Run the reference evaluator locally to derive per-case `Cd`, `Cl`,
   `CmPitch`, and report-only `Clf`/`Clr` by integrating the predicted surface
   pressure and wall shear with the defined constant-reference convention.
   Submit those coefficients and their required metrics in the result JSON. The
   per-case `metrics/cases.json` entry uses `force_coefficients` with `cd`,
   `cl`, `cm_pitch`, `clf`, and `clr`; the last two remain report-only. The
   authoritative truth is `force_mom_constref_all.csv`; per-case
   `run_N/force_mom_constref_N.csv` files are convenience mirrors that must
   replay the matching aggregate row.
5. Use the same evaluator to extract the diagnostics defined in
   [`drivaerml-diagnostics-v9.json`](drivaerml-diagnostics-v9.json): 16 AutoCFD5
   velocity lines on the candidate 10 mm grid and four continuous Cp cuts:
   upperbody centreline (`y=0`), underbody centreline (`y=0`), sidewall
   (`z=0.15 m`), and front-left wheelhouse (`y=-0.6 m`). Once the contract is
   activated, the ranked velocity metric will be global R2 with equal total
   weight for every case and line and normalized trapezoidal arc-length weight
   within each line. Continuous Cp-cut R2 is a separate ranked component with
   equal total weight for every case and cut and normalized native
   cut-intersection segment-length weight within each cut. The corresponding
   RMSE values remain report-only diagnostics. Submit the complete
   evaluator-produced coordinate and prediction arrays for all 16 velocity
   profiles and all four Cp cuts in the normal FluidsBench profile JSON.

The 209 discrete Cp probes are not part of the DrivAerML submission or scoring
contract. Participants do not submit probe outputs or probe-mapping support,
and no discrete-probe metric is calculated. The combined v8 registry and
existing 209-probe mapping artifacts are retained only as inactive,
non-normative research evidence. This exclusion does not apply to the four
continuous Cp cuts, which the participant's local frozen evaluator will derive
from its native surface `pMeanTrim` prediction. Participants provide no extra
Cp field in the VTP, but do include the derived continuous-cut series in their
submitted profile JSON.

The participant runs the frozen reference evaluator locally and submits its
derived JSON values. Sharing the complete native prediction fields is optional
under the repository-wide reproducibility policy. A maintainer may optionally
audit a shared, revision-pinned artifact, but native-field sharing and
maintainer recomputation are neither participant requirements nor activation
gates.

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
three independently ranked field-integrated coefficients, the velocity
profiles with weight 0.15, and the continuous Cp cuts with weight 0.10. The
four field errors use `clip(100 * (1 - error/cap), 0, 100)` with fixed caps of
15% surface pressure, 20% wall shear, 12% volume velocity, and 15% volume
pressure. Force and profile R2 values use `100 * clip(R2, 0, 1)`. The component
weights preserve a 50% field, 25% force, and 25% profile split. `Clf`, `Clr`,
and all RMSE values remain mandatory report-only diagnostics and receive no
duplicate composite weight.

The complete machine-readable source of truth is
[`submission-spec.json`](submission-spec.json). Candidate evidence and its
eligibility status are indexed in [`evidence/README.md`](evidence/README.md);
history and paper-parity definitions remain in [`proposal/`](proposal/). The
exact work still needed before opening submissions is tracked in
[`ACTIVATION_CHECKLIST.md`](ACTIVATION_CHECKLIST.md).

## Prototype leaderboard fixtures

The ten checked-in DrivAerML leaderboard rows can be regenerated with:

```bash
python3 scripts/generate_drivaerml_leaderboard_fixtures.py
python3 scripts/manage_leaderboard.py build
```

The generator uses every official test case and writes all 16 AutoCFD5 lines
on the exact station-specific 10 mm candidate grids (3,756 velocity samples per
case). It also writes dense, case-varying arc-length arrays for all four
continuous Cp cuts. Because the immutable native Cp-cut support is still an
activation gate, those cut coordinates and every profile value are explicitly
analytical CFD-like display data, not extracted DrivAerML truth or model
predictions. Diagnostic RMSE and R2 metrics are recomputed from the generated
curves, the Cp error is dimensionally tied to the pressure-field fixture
through `Cp = 2 pMeanTrim / 38.889^2`, and force R2 is tied to the exact pinned
force table through
[`force-r2-truth-statistics.json`](force-r2-truth-statistics.json). The
displayed bounded scores are therefore internally consistent, while all rows
remain labelled non-rankable prototype data.

The candidate evaluator's all-484 native-surface force replay is recorded in
[`evidence/force-replay-all484.json`](evidence/force-replay-all484.json). This
passing implementation evidence does not constitute owner approval or open
submissions.

The path-free native-volume evidence now includes both the original two-case
implementation pilot and the strict
[`all-484 equal-cell primary audit`](evidence/native-volume-equal-cell-primary-all484.json).
The latter verifies all 978 pinned segments and 68,949,662,110 native cells,
including exact field shape/order, finite values, complete coverage, and two
independent chunk partitions. It is not a model result or scoring baseline.
This audit supplies the complete volume-field weighting evidence
because the contract uses equal native cells only.

The earlier all-484 discrete-probe candidate sweep and its review artifacts
remain indexed in [`evidence/README.md`](evidence/README.md) for research
provenance only. They are not participant instructions, submission artifacts,
or scoring support, and their unresolved rows do not block a submission
contract that otherwise becomes eligible. Exact immutable native extraction
support for the four continuous Cp cuts is still pending and remains a separate
activation requirement.

The prescribed 1, 2, 5, and 10 mm profile study can be checked with
[`proposal/PROFILE_RESOLUTION_CONVERGENCE_INPUT.md`](proposal/PROFILE_RESOLUTION_CONVERGENCE_INPUT.md).
The prediction-based reference command described there can verify complete
native chunk manifests, stream the pinned multipart `UMeanTrim` truth, and
construct the loss tensor itself. Reduced case pilots always remain
ineligible; owner-review eligibility additionally requires the exact ordered
484-case scope and the pending immutable owner validity-mask binding.
Activation evidence still requires complete all-case velocity mappings and
genuine outputs from at least three distinct trained models. Those model
predictions are not currently available and remain an owner input; publishing
their complete native fields is not required. No real-model sensitivity result
is claimed. The bounded-score sensitivity review and bootstrap remain pending
until the evaluator is frozen.

FluidsBench contributors can follow the bounded-memory native-mesh and closed
candidate package workflow in
[`PARTICIPANT_GUIDE.md`](PARTICIPANT_GUIDE.md). AutoCFD5 is used there only as
the provenance for the 16 velocity-line definitions; it is not a second
submission target. The candidate release hand-off is recorded in
[`candidate-release-bindings.json`](candidate-release-bindings.json); its
unresolved owner-release tokens are blockers and are never copied into the
active `submission-spec.json`. The hand-off may hash-bind the complete local
`drivaerml-diagnostics-v10.json` file while those owner fields remain
unresolved; that partial hand-off is integrity evidence only and neither
activates v10 nor makes a participant package ready. A one-command synthetic
two-part/three-part dry run is provided under
[`examples/drivaerml-candidate-native-chunks/`](../../examples/drivaerml-candidate-native-chunks/);
it is an ineligible transport and packaging fixture, not an official
DrivAerML submission. Candidate native-volume support generation uses the exact
receipt-compatible runtime Python 3.12.13 and NumPy 2.2.6. Surface and velocity
evidence remains pinned to VTK 9.5.2.
