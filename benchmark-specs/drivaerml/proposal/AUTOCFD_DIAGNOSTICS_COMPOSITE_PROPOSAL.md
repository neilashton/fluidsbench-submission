# AutoCFD diagnostics and composite proposal for DrivAerML

Status: **candidate for owner review; not an active benchmark contract**

Prepared: 2026-08-19

## Authoritative AutoCFD inputs

- AutoCFD5 Case 2 description, 23 February 2026:
  `https://autocfd5.s3.eu-west-1.amazonaws.com/test-cases/case2/AutoCFD5_Case2_Intro_260223.pdf`
  (`sha256:2308a7e11202eeadc4f4080b4d5703af89207ddf342ede86f16aeaf90e3f67a7`)
- AutoCFD5 DrivAer result template v8:
  `https://autocfd5.s3.eu-west-1.amazonaws.com/test-cases/case2/AutoCFD5_DrivAer_Result_Template_v8.xlsm`
  (`sha256:5c7e04e5ccd7190b4f81173a3e5dcde09b9e25a9d91fdb866d48beab2e1e8960`)

The current guide marks these diagnostic definitions as unchanged from
AutoCFD4.

## What AutoCFD actually defines

AutoCFD asks for static `Cp` at 209 discrete surface-pressure taps. These are
not continuous, uniformly sampled Cp cuts. The exact unique probe IDs and
nominal baseline-geometry XYZ coordinates are recorded in
`autocfd_cp_taps_nominal.csv`. The input sheet stores them in 13 source/PID
families. The AutoCFD plotting sheet rearranges the same 209 probes into 15
named plotting sequences and reuses eight probes between plots; that 217-row
plot membership and ordering is recorded in
`autocfd_cp_panel_membership.csv`.

The v8 workbook has one internal inconsistency that needs owner confirmation:
its hidden plotting sheet swaps the `y` coordinates attached to underbody probe
IDs 623 and 629 relative to the mandatory `Surface Data 2a/2b` input tables.
The registries treat the mandatory input tables as authoritative
(`623: y=-0.590 m`, `629: y=-0.360 m`) while retaining the plotting order.

AutoCFD also asks for normalized velocity magnitude, `|U|/U_inf`, along all 16
lines `V1`-`V6`, `U1`-`U6`, `L1`, and `R1`-`R3`. Their exact start and end XYZ
coordinates, converted from millimetres to metres without changing the DrivAer
CAD frame, are recorded in `autocfd_velocity_lines_nominal.csv`. Eleven lines
have wind-tunnel correlation data; the other five remain mandatory columns in
the AutoCFD result template and must not be described as experimentally
supported.

AutoCFD does not define a fixed velocity-profile resolution. It permits each
participant to choose a point count sufficient to represent the profile. A
fixed grid is therefore a FluidsBench addition required for reproducible
scoring, not an AutoCFD rule.

## Candidate FluidsBench sampling and extraction

Use endpoint-inclusive, equal-arc sampling at a nominal 10 mm spacing:

| Lines | Count per line | Nominal spacing |
|---|---:|---:|
| `V1`-`V6` | 201 | 0.01 m |
| `U1`-`U6` | 301 | 0.01 m |
| `L1` | 651 | 0.01 m |
| `R1`-`R3` | 31 | approximately 0.01 m |

This gives 3,756 nominal samples per case. For endpoints `a` and `b` and count
`N`, sample `k` is `a + k(b-a)/(N-1)`. Build a 1 mm reference support first
(37,416 samples per case), then audit 2, 5, and 10 mm. Freeze the coarsest
global spacing that changes aggregate profile loss by no more than 0.5%, every
case-macro loss by no more than 1%, and method-order Kendall tau by less than
0.01 relative to 1 mm. The table and CSV record 10 mm as the candidate, not as
an AutoCFD-prescribed or already approved resolution.

For the proposed native `CellData` track, the benchmark-owned extractor locates
the native volume cell containing each valid velocity sample and takes
`UMeanTrim` from that cell before forming `|U|/38.889`. A point on a cell face
uses the smallest raw VTK cell ID as a deterministic tie-break. Samples inside
the morphed solid or outside the released fluid domain are marked by an
owner-published validity mask; a submitter may not create or alter that mask.
The scoring support publishes XYZ, distance from the line start, validity,
source raw cell ID, value, and hashes for every case.

The 209 Cp coordinates belong to the baseline AutoCFD geometry and generally do
not lie on a morphed DrivAerML surface. The scientifically preferred mapping is
to propagate every probe through the original ANSA morph used to make each
case. If that correspondence is unavailable, the fallback is an
owner-approved, surface-component-constrained closest-polygon projection with
published mapped XYZ, raw polygon ID, projection distance, QA tolerance, and
invalid reason. Plain fixed world XYZ is not a valid surface sampling rule for
the morphed cases.

## Diagnostic reductions

- `velocity_profile_nrmse`: dimensionless RMSE of `|U|/U_inf` along each line
  using arc-length trapezoidal weights, then an equal mean over the 16 lines,
  then an equal mean over cases. Also report the 11-line experimental-parity
  subset and every individual line.
- `cp_probe_rmse`: dimensionless RMSE over the 209 unique taps in each case,
  then an equal mean over cases. Also report each of the 15 plotting panels and
  a panel-macro sensitivity result.
- R-squared remains a secondary literature diagnostic only. It is not the
  ranked profile statistic because flattened R-squared changes with sampling
  density and is unstable for nearly flat individual profiles.

All profile predictions must come from the same model and checkpoint as the
submitted native field predictions. The evaluator recomputes these diagnostics
from benchmark truth rather than trusting submitter-supplied scalar summaries.

## Candidate overall score

Keep the broader FluidsBench utility allocation: 50% global fields, 25%
field-integrated engineering quantities, and 25% AutoCFD local diagnostics.
Within those branches use the existing 60/40 priority:

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

Do not use the prototype error caps or ranked flattened R-squared. For each
component `j`, compute the approved raw error `E_j` and the same error `B_j` for
a frozen physics-null prediction, then use

`S_j = 100 * (1 - E_j / B_j)`.

The null is zero surface/volume pressure, zero wall shear, freestream volume
velocity `(U_inf,0,0)`, velocity-profile ratio one, zero `Cp`, and zero `Cd` and
`Cl`. Negative scores remain negative for ranking because they mean worse than
the declared null; a clipped 0-100 value may be displayed but must not determine
rank. `Cd` and `Cl` in the composite are integrated from the submitted surface
fields using the frozen force contract. Separately predicted scalar forces are
reported but cannot enter the composite.

Publish all eight raw errors and component skills, the three 0.50/0.25/0.25
branch scores, the overall score, and equal-case bootstrap confidence intervals.
Do not activate the overall score until field-integrated force replay matches
the pinned source force files and weight/cap-free baseline sensitivity is tested
with a null baseline, nearest-training-geometry baseline, and several real model
architectures.

## Owner decisions still required

1. Confirm whether the retained ANSA morph workflow can export the 209
   case-specific probe positions. If not, approve the constrained projection
   fallback and its QA tolerance.
2. Confirm the v8 input-table coordinates for underbody probes 623 and 629 in
   light of the hidden plotting-sheet swap documented above.
3. Confirm that all 16 mandatory AutoCFD velocity lines enter the CFD/ML score,
   with the 11 experimentally supported lines also reported separately.
4. Approve the 50/25/25 multi-scale utility statement and its 60/40 priorities;
   otherwise publish the three branch leaderboards without a single overall
   rank.
