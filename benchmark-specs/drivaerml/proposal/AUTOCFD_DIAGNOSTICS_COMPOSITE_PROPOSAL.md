# AutoCFD diagnostics and composite proposal for DrivAerML

Status: **owner decisions recorded; implementation-validation proposal; not an
active benchmark contract**

Prepared: 2026-08-19

## Authoritative AutoCFD inputs

- AutoCFD5 Case 2 description, 23 February 2026:
  `https://autocfd5.s3.eu-west-1.amazonaws.com/test-cases/case2/AutoCFD5_Case2_Intro_260223.pdf`
  (`sha256:2308a7e11202eeadc4f4080b4d5703af89207ddf342ede86f16aeaf90e3f67a7`)
- AutoCFD5 DrivAer result template v8:
  `https://autocfd5.s3.eu-west-1.amazonaws.com/test-cases/case2/AutoCFD5_DrivAer_Result_Template_v8.xlsm`
  (`sha256:5c7e04e5ccd7190b4f81173a3e5dcde09b9e25a9d91fdb866d48beab2e1e8960`)
- AutoCFD5 Case 2a baseline surface:
  `https://autocfd5.s3.eu-west-1.amazonaws.com/test-cases/case2/DrivAer_Notchback_baseline_geometry.stl.gz`
  (`sha256:ef04c7964530f32a8c805efd8c26364f8e63ee508084292295ab0b15d828001f`)

The current guide marks these diagnostic definitions as unchanged from
AutoCFD4.

The derived registries are pinned as follows: velocity lines
`sha256:6eb1528034e27a75ab1949551d58c8a161331bf6d343ca7fb4324f0800ca4d12`,
expanded 10 mm velocity samples
`sha256:5f1bcf84a633aa6bfdd776764c3295d5d624ef0b6c3649f67de446281ae5ba97`,
unique Cp taps
`sha256:2c1e216ef5693b26d43b9b4f55586ca35516224af0ad874987e5902c67f08e6f`,
and Cp panel membership
`sha256:6e288077b8b87e0c5d8d77c1050b07e4b5dd155a8e4fad8815ce4b0581995538`.
The candidate tap-to-component review atlas is
`sha256:b4ef9270f2633f2bd3d271e18de23f93e8da3398d67fbc34e77271fb37cbce66`.

## What AutoCFD actually defines

AutoCFD asks for static `Cp` at 209 discrete surface-pressure taps. These are
not continuous, uniformly sampled Cp cuts. The exact unique probe IDs and
nominal baseline-geometry XYZ coordinates are recorded in
`autocfd_cp_taps_nominal.csv`. The input sheet stores them in 13 source/PID
families. The AutoCFD plotting sheet rearranges the same 209 probes into 15
named plotting sequences and reuses eight probes between plots; that 217-row
plot membership and ordering is recorded in
`autocfd_cp_panel_membership.csv`.

The v8 workbook has one internal inconsistency: its hidden plotting sheet swaps
the `y` coordinates attached to underbody probe IDs 623 and 629 relative to the
mandatory `Surface Data 2a/2b` input tables. The benchmark owner decided on
2026-08-19 that the mandatory input tables are authoritative. The registries
therefore use `623: y=-0.590 m` and `629: y=-0.360 m` while retaining the
plotting order.

AutoCFD also asks for normalized velocity magnitude, `|U|/U_inf`, along all 16
lines `V1`-`V6`, `U1`-`U6`, `L1`, and `R1`-`R3`. Their exact start and end XYZ
coordinates, converted from millimetres to metres without changing the DrivAer
CAD frame, are recorded in `autocfd_velocity_lines_nominal.csv`. Eleven lines
have wind-tunnel correlation data; the other five remain mandatory columns in
the AutoCFD result template and must not be described as experimentally
supported. The benchmark owner decided on 2026-08-19 that all 16 lines enter
the ranked CFD/ML diagnostic, with the experimentally supported 11-line subset
reported separately. That subset label records AutoCFD experimental
availability at those baseline locations; DrivAerML ranking still compares ML
against the released CFD truth for each morph and must not be presented as
per-morph experimental validation.

All coordinates are metres in the released DrivAer CAD frame: the origin is at
the front-wheel axle, `+x` is downstream/freestream and drag, `y=0` is the
longitudinal symmetry plane, `+z` is upward, and the road is
`z=-0.3176 m`. Use `U_inf=38.889 m/s` in `+x`; do not rotate, translate, or
case-normalize the AutoCFD coordinates.

AutoCFD does not define a fixed velocity-profile resolution. It permits each
participant to choose a point count sufficient to represent the profile. The
v8 input sheet provides 1,001 data rows per line, but this is capacity rather
than a prescribed spacing. A fixed grid is therefore a FluidsBench addition
required for reproducible scoring, not an AutoCFD rule.

## Frozen proposed FluidsBench sampling and extraction

Use endpoint-inclusive, equal-arc sampling at a nominal 10 mm spacing:

| Lines | Count per line | Nominal spacing |
|---|---:|---:|
| `V1`-`V6` | 201 | 0.01 m |
| `U1`-`U6` | 301 | 0.01 m |
| `L1` | 651 | 0.01 m |
| `R1`-`R3` | 31 | approximately 0.01 m |

This gives exactly 3,756 samples per case and keeps the longest line (`L1`, 651
samples) within the 1,001-row AutoCFD template capacity. For endpoints `a` and
`b` and count `N`, sample `k` is `a + k(b-a)/(N-1)`. The proposed v1 scoring
grid is 10 mm; it is a FluidsBench reproducibility choice and must not be
described as AutoCFD-prescribed. All 3,756 resulting coordinates and distances
are expanded in `autocfd_velocity_samples_10mm.csv` so evaluator
implementations need not reproduce decimal rounding independently.

Before activation, build a 1 mm reference support (37,416 samples per case) and
audit nested 2, 5, and 10 mm grids. The proposed 10 mm grid passes only if it
changes aggregate profile loss by no more than 0.5%, every case-macro loss by
no more than 1%, every case-line loss by no more than 2%, and method-order
Kendall tau-b remains at least 0.99 relative to 1 mm. For candidate spacing
`h`, define a relative change as `|L_h-L_1mm|/L_1mm`. If `L_1mm <= 1e-12`,
require absolute agreement within `1e-12` instead. Apply the 0.5% limit to the
final case/line macro loss, the 1% limit to each case's 16-line macro loss, and
the 2% limit to each case-line loss. Compute Kendall tau-b on the final method
scores, declaring score differences at most `1e-12` tied. Pin the method set
before the study: the physics null, nearest-training-design-vector control,
and at least three distinct trained model/checkpoint submissions. Failure leaves the
diagnostic unranked until a new version globally adopts the coarsest finer grid
that passes; it must not silently change an active contract.

For the Kendall calculation, rank methods by their final `E_profile` values
(equivalently by profile skill with one frozen positive `B_profile`), never by
the eight-component overall composite.

For the proposed native `CellData` track, the benchmark-owned extractor locates
every native volume cell whose closure contains each valid velocity sample and
takes `UMeanTrim` from the smallest raw VTK cell ID before forming
`|U|/38.889`. Use a `1e-6 m` absolute closure tolerance; pre-activation replay
must additionally show that 0.5 and 2 micrometre tolerances do not alter any
non-face assignment or ranked result. This is an explicit zeroth-order
finite-volume reconstruction, applied identically to truth and prediction. The
released meshes contain hexahedra, polyhedra, wedges, pyramids, and tetrahedra,
so the owner extractor must support all five; it must not assume an all-hex
mesh or rely on an implementation-defined `vtkProbeFilter` face tie-break.
The exact candidate-discovery and closure kernel, dependency revision, and
candidate-count semantics are not yet frozen: activation requires a published,
hashed reference evaluator plus golden all-case assignment and tolerance
replays. The rules above are therefore proposed selection semantics, not a
claim that an executable locator is already released.
Samples inside the morphed solid or outside the released fluid domain are
marked by an owner-published validity mask; there is no snapping or
extrapolation, and a submitter may not create or alter that mask. The scoring
support publishes XYZ, distance from the line start, validity/reason, source
raw cell ID, candidate count, geometric tolerance, value, and hashes for every
case. A separately reported PointData-interpolated trace is a sensitivity
diagnostic only.

For profile reduction, let `q=|U|/U_inf`, `e_k=q_pred,k-q_true,k`, and
`ds_k=s_(k+1)-s_k`. For case `c` and line `l`, let `A_cl` contain only edges
whose two endpoints are valid, and calculate

`R_cl = sqrt(sum_(k in A_cl) ds_k*(e_k^2+e_(k+1)^2)/2 /
             sum_(k in A_cl) ds_k)`.

Never bridge an invalid gap. Every case/line must retain positive contributing
length; otherwise the profile component remains unranked pending an
owner-reviewed support correction. The ranked profile error is
`E_profile = mean_c(mean_l(R_cl))`, with all 16 lines and cases weighted
equally. This is an RMSE of an already freestream-normalized quantity, not an
RMSE divided by a second data-dependent normalizer.

The 209 Cp coordinates belong to the baseline AutoCFD geometry and generally do
not lie on a morphed DrivAerML surface. Propagating every probe through the
original ANSA morph would be scientifically preferable, but the benchmark
owner reported on 2026-08-19 that the retained case-specific probe
correspondence is not believed to be available. Plain fixed world XYZ and
unrestricted nearest-VTP projection are therefore invalid surface-sampling
rules for the morphed cases.

The proposed reproducible surrogate is:

1. Derive a candidate primary anatomical solid for every nominal tap by
   projecting it onto the pinned official AutoCFD baseline STL, then require
   owner visual sign-off before freezing it. Map baseline names to the 49-name
   vocabulary observed in the pinned `run_1/drivaer_1.stl` and expected, but
   not yet proven, in every public `run_N/drivaer_N.stl`; the baseline
   `Body_Fascia_front_1_lower_lip` is merged into DrivAerML
   `BodyFasciafront1`. The resulting 209-row owner-review atlas is
   `autocfd_cp_tap_component_registry.csv`.
2. In each case, project the tap only onto that permitted named STL solid.
   Never fall back to an unrestricted surface. Preserve the exact physical cut
   where one exists: `y=0` for upperbody/underbody centreline, `z=0.150 m` for
   sidewall/rear-end 150 mm, `z=0.500 m` for rear-end 500 mm, and the declared
   per-probe `y` or `z` plane for the wheelhouse. Window/pillar/trunk and
   off-centre detailed-underbody points use constrained three-dimensional
   closest projection. The atlas explicitly stores `projection_mode`,
   `cut_axis`, and `cut_value_m` for every probe; do not infer them from labels.
   For a cut, intersect every permitted triangle with the exact plane and
   choose the closest point on the resulting line segments. Otherwise choose
   the closest point on the permitted triangles. Let `d_min` be the minimum
   candidate distance; all
   candidates with `d <= d_min + 1e-6 m` form the tie set, from which select
   the smallest raw STL triangle ID, defined as the zero-based global `facet`
   order in the ASCII file. Classify a vertex as lying on a cut plane when the
   absolute value of its signed distance is at most `1e-9 m`. A crossing yields
   its closed segment or point; a fully coplanar triangle contributes the
   entire closed triangle.
   Choose the closest point on that union before applying the distance tie.
3. Bridge that mapped STL point to the native boundary VTP. Require distance
   at most 2 mm and absolute normal dot product at least
   `cos(30 deg)=0.8660254037844387`;
   discard candidates failing either filter, and flag selected bridge distances
   over 0.5 mm for visual review. Order the remaining candidates by distance,
   then decreasing normal agreement, then smallest raw VTK polygon ID. As
   above, the distance tie set is every candidate within `1e-6 m` of `d_min`;
   normal-agreement values within `1e-12` are tied. Recompute the STL facet unit
   normal from its ordered-vertex cross product. For a VTP polygon with released
   connectivity-order vertices `v_i`, use the unit area vector
   `normalize(sum_i(v_i cross v_(i+1)))`, with cyclic indexing. A facet or
   polygon whose unnormalized area-vector magnitude is at most `1e-15 m^2` is
   degenerate and invalid. The absolute normal dot product deliberately makes
   orientation reversal irrelevant.
4. Publish nominal and mapped XYZ, primary solid, STL triangle, nominal
   displacement, normals, native raw polygon ID, bridge distance/agreement,
   validity/reason, source hashes, and any owner override for every case/tap.

The atlas columns prefixed `component_assignment_` record the unrestricted
three-dimensional baseline nearest-triangle audit used only to select and
review the candidate anatomical component. They are not outputs of the row's
declared cut or closest-point rule and must never be copied into scoring
support. The declared rule is executed afresh on every pinned case STL; its
rule-specific point, triangle, distance, and bridge result are separate
per-case support fields.

The explicit per-case projection-rule families are:

| AutoCFD PID / points | Projection rule |
|---|---|
| 600 and 610 | component-constrained cut at `y=0` |
| 601 and 611 | component-constrained cut at `z=0.150 m` |
| 614 | component-constrained cut at `z=0.500 m` |
| 624 points 1 and 8-17 | front-wheelhouse cut at `y=-0.750 m` |
| 624 points 2, 7, and 18-26 | front-wheelhouse cut at `y=-0.600 m` |
| 624 points 3-6 | front-wheelhouse cut at each probe's nominal `z` |
| 625 points 1-21 | detailed-underbody centreline cut at `y=0` |
| 602-604, 612, 613, 615, and 625 points 22-34 | component-constrained 3-D closest point |

The automated baseline component-assignment audit places all 209 taps on
plausible wetted vehicle components: none maps to a domain, artificial control
surface, tyre, rim, brake, wheel support, plinth, powertrain, or exhaust
component. No first/
second component gap is within 0.1 mm (the minimum is 1.542456 mm). Of the 209,
205 component-assignment nearest points lie within 1 mm of the official STL.
Probes 625, 626, 552, and 553 have component-assignment offsets of 5.000633,
4.902647, 2.754784, and 1.543416 mm respectively; probe 120 is the only other
offset above 0.5 mm, at 0.983322 mm. These flags are recorded in the atlas and
every row remains `pending_visual_signoff`; the audit does not substitute for
owner review or rule-specific projection.

At the selected native polygon, derive both truth and prediction from the same
canonical surface-pressure field:

`Cp = 2 * pMeanTrim / (38.889 m/s)^2`.

Do not require a separately predicted `CpMeanTrim` array. On all 8,828,095
native polygons in `run_1`, this transform reproduces the released
`CpMeanTrim` with maximum absolute difference `4.694e-7` and RMSE
`1.698e-8`; repeat and publish that replay over all 484 cases before activation,
requiring a maximum absolute difference no greater than `1e-6` in every case.
The diagnostic remains inactive if any case fails. The released `CpMeanTrim`
remains a source QA array, not a second model target.

Tyres, rims, brakes, wheel supports, mirrors, door handles, and artificial
`CTRL_SURFACE_*` patches are globally excluded unless the frozen atlas
explicitly assigns a probe to one of them. The normative mapping gates are:
the declared component must exist; the declared projection must return a
finite, nondegenerate candidate; the 2 mm bridge and 30-degree normal filters
must pass; the selected raw polygon must be unique after the fixed tie rules;
and nominal displacement must not exceed `0.278618 m` (10% of the 2.78618 m
reference wheelbase). Displacement above `0.2089635 m` (7.5% wheelbase) is a
mandatory owner-review flag. Side, symmetry, panel-order, mirrored-pair, and
duplicate/collapse summaries are non-normative owner-review diagnostics in
this proposal: they may not change validity or selection unless a later
version publishes exact equations, tolerances, and outcomes.

Every one of the 209 mappings must be valid for every ranked case. A failed
mapping is repaired only before activation by an immutable owner-override row
keyed by `(case_id, autocfd_probe_id)` and containing replacement mapping IDs
and coordinates, reason, author, version, and source hashes; otherwise the Cp
component remains unranked. An active support version is never edited in
place. This construction must be described as a
reproducible AutoCFD-location surrogate on each morph, not as the original
material tap transported through ANSA.

## Diagnostic reductions

- `velocity_profile_uinf_rmse`: dimensionless RMSE of `|U|/U_inf` along each line
  using arc-length trapezoidal weights, then an equal mean over the 16 lines,
  then an equal mean over cases. Also report the 11-line experimental-parity
  subset and every individual line.
- `cp_probe_rmse`: for `e_ci=Cp_pred,ci-Cp_truth,ci`, calculate
  `R_c=sqrt(sum_(i=1)^209 e_ci^2/209)` and then `mean_c(R_c)`. For panel `p`,
  calculate the same per-case RMSE over its ordered membership rows and report
  `mean_c(R_cp)`; the panel-macro sensitivity is
  `mean_c(mean_(p=1)^15(R_cp))`. Each of the eight probes reused between panels
  contributes once in every panel containing it, but only once in the ranked
  209-unique-probe metric.
- R-squared remains a secondary literature diagnostic only. It is not the
  ranked profile statistic because flattened R-squared changes with sampling
  density and is unstable for nearly flat individual profiles.

All profile predictions must come from the same model and checkpoint as the
submitted native field predictions. The benchmark reference evaluator run at
the contributor stage recomputes these diagnostics from benchmark truth rather
than trusting manually supplied scalar summaries; this does not imply that a
FluidsBench maintainer reruns the model or downloads its complete predictions.
AutoCFD supplies the diagnostic locations and panel conventions; the ranked
truth is the released DrivAerML CFD for each morphology, not the baseline
AutoCFD wind-tunnel measurements.

## Owner-approved overall-score structure

The benchmark owner approved on 2026-08-19 the broader FluidsBench utility
allocation: 50% global fields, 25% field-integrated engineering quantities, and
25% AutoCFD local diagnostics. Within those branches use the existing 60/40
priority:

| Component | Weight |
|---|---:|
| native surface pressure field | 0.15 |
| native surface wall-shear field | 0.10 |
| native volume velocity field | 0.15 |
| native volume pressure field | 0.10 |
| field-integrated `Cd` | 0.15 |
| field-integrated `Cl` | 0.10 |
| 16 AutoCFD velocity profiles | 0.15 |
| 209 AutoCFD Cp probes | 0.10 |

The raw component errors are fixed as follows:

- surface pressure and wall shear: arithmetic mean over cases of the complete
  case area-weighted relative L2 defined in `SCIENTIFIC_CONTRACT.md`;
- volume velocity and pressure: arithmetic mean over cases of the complete
  case equal-native-cell relative L2, preserving the current repository-wide
  volume default; publish the cell-volume-weighted result beside it;
- field-integrated `Cd` and `Cl`: equal-case RMSE of the coefficients integrated
  from the submitted surface fields using the constant AutoCFD convention
  `A_ref=2.17 m^2`, `rho_inf=1 kg/m^3`, and `U_inf=38.889 m/s`, with drag in
  `+x` and lift in `+z`. Thus `Cd=F_x/(0.5*rho_inf*U_inf^2*A_ref)` and
  `Cl=F_z/(0.5*rho_inf*U_inf^2*A_ref)`. Report the geometry-specific-reference
  coefficients separately as an unranked AB-UPT/aerodynamic-efficiency view;
- velocity profiles: the equal-case/equal-line arc-weighted RMSE defined above;
  and
- Cp probes: the equal-case 209-unique-probe RMSE defined above.

The pinned constant-reference truth table has the exact header
`run,cd,cl,clf,clr,cs`, 484 finite rows, and one unique integer `run` for each
public case. Join `run=N` to `case_id=run_N` without positional matching; the
ranked dimensionless targets are lowercase columns `cd` and `cl`. A missing,
duplicate, non-integer, nonfinite, unexpected, or manifest-extraneous run is a
hard evaluator error. The 16 known held-back run numbers are absent by design.

Do not use the prototype error caps or ranked flattened R-squared. For each
component `j`, compute that raw error `E_j` and the identical reduction `B_j`
for a frozen physics-null prediction, then use

`S_j = 100 * (1 - E_j / B_j)`.

The null is zero surface/volume pressure, zero wall shear, freestream volume
velocity `(U_inf,0,0)`, velocity-profile ratio one, zero `Cp`, and zero `Cd` and
`Cl`. Negative scores remain negative for ranking because they mean worse than
the declared null; a clipped 0-100 value may be displayed but must not determine
rank. `Cd` and `Cl` in the composite are integrated from the submitted surface
fields using that constant-reference force contract. If a separately versioned
direct-scalar force task is later activated, report it separately; it cannot
enter this composite. For every native boundary polygon `f`, let `c_f` be the
arithmetic mean of its vertex coordinates and define the
released-connectivity-order oriented area vector

`A_f = 0.5 * sum_i((v_i-c_f) cross (v_(i+1)-c_f))`.

With `p_f=pMeanTrim_f` and `tau_f=wallShearStressMeanTrim_f`, use every native
polygon exactly once and compute

`F = rho_inf * sum_f(p_f*A_f - tau_f*|A_f|)`.

Both stored fields are kinematic (`m^2/s^2`), so multiplication by `rho_inf`
produces dynamic force. A run-1 replay over all 8,828,095 polygons gives
`Cd=0.310924656699` and `Cl=0.069382211528`, versus pinned rounded truth
`0.3109247` and `0.06938221` (absolute differences `4.33e-8` and `1.53e-9`).
Before activation, require every public case to reproduce both coefficients
within absolute `1e-6`; do not activate if that all-case replay fails. Each
`B_j` must be finite and strictly positive; otherwise that component and the
overall composite remain unranked.

Publish all eight raw errors and component skills, the three 0.50/0.25/0.25
branch scores, the overall score, and equal-case bootstrap confidence intervals.
Compute each branch as the normalized weighted mean of its component skills;
the overall score is equivalently `sum_j(w_j*S_j)` over the eight table rows.
Bootstrap replicates resample cases and recompute both `E_j` and `B_j` on each
replicate. Use 10,000 paired case-bootstrap replicates with seed `20260819`, one
shared resampled case-index vector across every method and component within a
replicate, and the two-sided 2.5/97.5 percentile interval. Order evaluated
cases by ascending integer `run`, then generate the row-major `(10000,n_cases)`
index matrix with NumPy 2.2.6 `Generator(PCG64(20260819))` and its `integers`
method using `low=0`, `high=n_cases`, `size=(10000,n_cases)`, `dtype=int64`,
and `endpoint=False`. Use NumPy percentile
`method="linear"` (Hyndman-Fan type 7) and publish the generated index matrix or
its canonical serialization and SHA-256 before activation.

The nearest-training control used in sensitivity analysis is the
**nearest-training-design-vector** control; it is benchmark-owned, unranked,
and not a submission method. Read `geo_parameters_all.csv` from the pinned
dataset revision (SHA-256
`2d4e8b3f166d1facab2a38821af2c3cc1dbba47cfbb7bf0814e3e0bf1fe3e829`),
join `run_N` to integer `Run=N`, strip ASCII whitespace from headers, and use
these 16 columns in order: `Vehicle_Length`, `Vehicle_Width`, `Vehicle_Height`,
`Front_Overhang`, `Front_Planview`, `Hood_Angle`, `Approach_Angle`,
`Windscreen_Angle`, `Greenhouse_Tapering`, `Backlight_Angle`,
`Decklid_Height`, `Rearend_tapering`, `Rear_Overhang`,
`Rear_Diffusor_Angle`, `Vehicle_Ride_Height`, and `Vehicle_Pitch`.

For each evaluated split, the donor pool is exactly that split's declared
training list. Compute each descriptor's training-pool mean and population
standard deviation (`ddof=0`); missing/nonfinite values or a nonpositive scale
are hard errors. Select the training case minimizing the sum of squared
descriptor differences divided by those 16 variances, breaking an exact tie by
smallest integer `Run`. Validation/test cases and force or flow statistics never
enter fitting or selection. Publish and hash the resulting
`(split_id,target_case_id,donor_case_id,distance_squared)` map.

That donor map does not yet define a full-composite prediction because native
meshes differ. Raw VTK IDs must never be copied between cases. This control
remains an activation gate until a benchmark-owned donor-to-target surface and
volume field-transfer operator, support-validity policy, and golden replay are
published.

Do not activate the overall score until field-integrated force replay matches
the pinned source force files and weight/cap-free baseline sensitivity is tested
with a null baseline, the nearest-training-design-vector control after its
transfer contract is frozen, and several real model architectures.

## Owner decisions recorded on 2026-08-19

1. Treat case-specific ANSA-morphed pressure-probe positions as unavailable
   unless a retained mapping is subsequently recovered; implement and validate
   the benchmark-owned constrained-projection route.
2. Treat the mandatory v8 input tables as authoritative for underbody probes
   623 and 629.
3. Rank all 16 mandatory AutoCFD velocity lines and additionally report the
   experimentally supported 11-line subset.
4. Use the 50/25/25 multi-scale allocation and the 60/40 priorities within each
   branch for the overall composite.

## Remaining implementation gates

These are reproducibility and validation tasks, not unresolved benchmark-owner
policy questions:

1. Complete owner visual sign-off of the generated 209-row Cp anatomy atlas,
   especially wheelhouse, detailed-underbody, and window/frame or trunk seams;
   pin the exact `run_N/drivaer_N.stl` identity for all 484 public cases, then
   generate and audit the mapped support for all of them.
2. Complete the 1/2/5/10 mm profile-resolution convergence study and verify the
   frozen proposed 10 mm grid satisfies the declared activation criteria.
3. Publish and hash the reference containing-cell implementation for all five
   released cell types, then golden-replay every profile assignment and
   tolerance-sensitivity result.
4. Replay the now-explicit native force integration over all 484 cases and
   require the declared absolute `1e-6` `Cd`/`Cl` tolerance, plus chunk-
   invariance tests.
5. Generate versioned golden truth and scoring support for the 209 probes and
   16 lines, with checksums, source raw IDs, validity masks, and deterministic
   evaluator replay tests.
6. Compute the physics-null denominators and run the declared null,
   nearest-training-design-vector (after its transfer contract), and real-model
   sensitivity checks before enabling the composite for ranking.
