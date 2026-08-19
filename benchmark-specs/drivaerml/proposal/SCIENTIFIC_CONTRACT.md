# DrivAerML benchmark contract proposed for scientific review

Status: **owner policy decisions recorded; activation validation required;
submissions remain closed**

Prepared: 2026-08-19

Scope: the public `neashton/drivaerml` release pinned in this directory

## Decision in one paragraph

The proposed canonical FluidsBench task evaluates predictions on a frozen raw
support: all native released surface polygons from VTP `CellData` and a
finite-volume-aligned candidate consisting of all VTU `CellData` volume cells.
The owner must still confirm that the volume arrays are the un-interpolated
solver carrier before activation. Models may resample, interpolate, or use point
representations internally, but their predictions must be returned once for
every frozen canonical entity. The benchmark reports both physical-measure and
equal-entity errors, calculated per case and then macro-averaged. The proposed
composite selects physical-area weighting for surface fields and the existing
repository equal-cell default for volume fields, while reporting the
cell-volume-weighted view beside it; activation remains conditional on the
declared baseline/model sensitivity study. AB-UPT and GeoTransolver are
preserved as explicitly different literature tracks because they do not use the
same volume support. No profile, cut, force integration, exclusion mask, or
overall composite becomes official until its complete definition and a golden
reference calculation are approved.

## Why this is the review-grade choice

The raw association is not universal across automotive datasets. It must be
read from each pinned dataset rather than inferred from a model architecture.
Only the DrivAerML, AB-UPT, and GeoTransolver rows below are bound to immutable
sources in this proposal. AhmedML, WindsorML, and HiLiftAeroML are contextual
local raw-file audits from 2026-08-18; they motivate dataset-specific handling
but are not normative evidence until their exact release revisions and audit
manifests are added.

| Evidence | Surface used | Volume used | Consequence |
|---|---|---|---|
| DrivAerML raw CFD release | VTP `CellData` polygons | VTU exposes both `CellData` and `PointData`; the latter is used by one paper pipeline | The two volume associations are different supports and cannot share one score; CellData provenance still needs owner confirmation |
| AB-UPT on DrivAerML | cell centres carrying VTP `CellData` | cell centres carrying VTU cell fields | Cell-based precedent, but published volume metrics use a random subset rather than every cell |
| GeoTransolver on DrivAerML | VTP `CellData` polygons | every raw VTU `PointData` vertex | Valid literature representation, but not the same support as the proposed cell benchmark |
| AhmedML contextual local audit (release pin not included) | VTP `CellData` polygons | VTU `CellData` cells | Example of a cell/cell raw-data contract |
| WindsorML contextual local audit (release pin not included) | VTU `PointData` surface vertices | VTU `CellData` volume cells | Example showing that even related datasets can need different surface and volume associations |
| HiLiftAeroML contextual local audit (release pin not included) | boundary-VTU `PointData` | volume-VTU `PointData`, with an owner-declared validity mask | Example showing that point support and exclusions are appropriate only when the source data and owner contract require them |

DrivAerML was solved with an OpenFOAM finite-volume method and its dataset paper
describes approximately 8.8 million surface cells and 160 million volume cells
per case. This makes a cell-based track the strongest FVM-aligned candidate and
avoids privileging AB-UPT, GeoTransolver, or the model being prepared for
submission. It is still a proposal, not proof that every released CellData array
is an un-interpolated solver field; that provenance is an activation blocker.

## Immutable public release

- Dataset: `neashton/drivaerml`
- Hugging Face Git revision:
  `7a5c0948ce27be709b1116a3a190f806e7a8f79f`
- Public cases: 484 (`run_1` to `run_500`, excluding the 16 IDs recorded in
  `native-source-pin.json`)
- Canonical source pin SHA-256:
  `4fc9077f8f23f4994c98f4d0e7a17aef7b998de4c996638e3a8a616b6d923fdd`
- Owner-published split manifest SHA-256:
  `032a2e9f88926d9218a1943b51e650135cc78683cad6b0a38f3cf4f9dfba647d`
- Surface-area manifest SHA-256:
  `1401c7e80bd86f3aa2d640289db9b088ce1e0825327e18eeb1ab2852de04323e`

Each reconstructed volume is the byte concatenation of its ordered `.00.part`,
`.01.part`, and, for ten cases, `.02.part` files. The ordered part paths, sizes,
and SHA-256 object identities in `native-source-pin.json` define the logical
VTU exactly; similarly named unparted alternatives are not canonical.

## Canonical support and identity

### Surface

- Source: `run_<N>/boundary_<N>.vtp` at the pinned revision.
- Association: VTK `CellData`.
- Entities: every native polygon, in raw VTK cell order.
- Stable ID: `(run_<N>, raw_vtk_cell_id)`.
- Interchange coordinate: polygon cell centre computed by the benchmark loader.
- Physical weight: the owner-published deterministic polygon area. The public
  area file has one little-endian float32 value per raw VTK cell and the same
  tuple order.
- The scoring support must pin the area algorithm and version, numeric tolerance,
  positivity/finiteness checks, and source-to-area tuple-count check.

### Volume

- Source: the reconstructed `run_<N>/volume_<N>.vtu` at the pinned revision.
- Association: VTK `CellData`.
- Entities: every finite-volume cell, in raw VTK cell order.
- Stable ID: `(run_<N>, raw_vtk_cell_id)`.
- Interchange coordinate: cell centre computed by the benchmark loader.
- Physical weight: cell volume computed by the approved FluidsBench loader from
  the exact pinned mesh and published in the scoring support.
- Before activation, the owner must confirm the CellData provenance. The support
  must also pin the polyhedron-volume algorithm and version, orientation/absolute
  volume convention, numeric tolerance, positivity/finiteness checks, and
  per-case aggregate QA.

Coordinates are audit information, not identity. A submission cannot align
entities by nearest-neighbour coordinate matching. Chunk boundaries are also not
part of the scientific support; they are only a memory-management detail.

## Required field targets

| ID | Raw array | Components | Raw meaning |
|---|---|---:|---|
| `surface_pressure` | surface `pMeanTrim` | 1 | relative kinematic pressure |
| `surface_wall_shear` | surface `wallShearStressMeanTrim` | 3 | wall-shear-stress vector |
| `volume_velocity` | volume `UMeanTrim` | 3 | mean velocity vector |
| `volume_pressure` | volume `pMeanTrim` | 1 | relative kinematic pressure |

The dataset defines `pMeanTrim` as kinematic pressure, `p/rho_inf`, and fixes the
pressure reference to `p_ref=0 Pa` at `(x,y,z)=(80,10,10) m` on the outlet
boundary. That gauge and `rho_inf=1 kg/m^3` are part of the proposed contract.
The scoring-support audit must verify that every case uses this convention.
Kinematic pressure is reported in `m^2/s^2`; a conversion to pascals must be a
separately named, explicitly density-scaled metric.

The raw wall-shear vector is a required prediction target and is the
time-averaged OpenFOAM wall-shear-stress field: kinematic traction in
`m^2/s^2`, defined using the patch normal into the fluid domain. Convert it to
dynamic traction only by multiplying by `rho_inf`. Field comparison uses the
raw stored vector without a sign transformation. The field-derived body-force
sign is fixed separately below by replay against the public force table.

The release also contains `CpMeanTrim` and `CptMeanTrim`. They must not both be
called “pressure” without qualification. `CpMeanTrim` is the static pressure
coefficient; `CptMeanTrim` is the total pressure coefficient used by the AB-UPT
volume-pressure paper result. The canonical target above is static
`pMeanTrim`; a future coefficient target must have a separate metric ID and an
owner-verified conversion. The proposed AutoCFD tap diagnostic supplies that
separate metric ID and deterministically derives
`Cp=2*pMeanTrim/(38.889 m/s)^2`; it does not add a separately submitted field.
Kinematic pressure must not be labelled as pascals.

For vector fields, the error at an entity is the norm of the component-wise
error vector. A difference between predicted and true vector magnitudes is not a
substitute because it can conceal direction error.

## Reductions and aggregation

For each case and target, accumulate the following over the complete support:

\[
E_{2,w}=100\sqrt{\frac{\sum_i w_i\lVert\hat y_i-y_i\rVert_2^2}
                              {\sum_i w_i\lVert y_i\rVert_2^2}},
\qquad
E_{2,1}=100\sqrt{\frac{\sum_i \lVert\hat y_i-y_i\rVert_2^2}
                              {\sum_i \lVert y_i\rVert_2^2}}.
\]

- `w_i` is polygon area on the surface and cell volume in the flow domain.
- The physical-measure result is the continuum-norm view.
- The equal-entity result is mandatory and reported beside it. It captures the
  resolution-weighted view and provides continuity with unweighted literature.
- Physical-measure and equal-entity MAE and RMSE are mandatory diagnostics,
  particularly for pressure fields whose relative denominator can be small or
  gauge-sensitive.
- Every case-level relative-L2 truth denominator must be finite and strictly
  positive. A zero or nonfinite denominator is a benchmark-support error; the
  case may not be silently omitted, pooled, or replaced by zero.
- Any nonfinite prediction on a required valid entity is a hard submission
  error. Any nonfinite truth value, coordinate, or required weight is a hard
  benchmark-support error.

For either `w_i` equal to the physical weight or one, the absolute diagnostics
are

\[
\operatorname{MAE}_w=\frac{\sum_iw_i\lVert\hat y_i-y_i\rVert_2}{\sum_iw_i},
\qquad
\operatorname{RMSE}_w=\sqrt{\frac{\sum_iw_i\lVert\hat y_i-y_i\rVert_2^2}
                                  {\sum_iw_i}}.
\]

For a scalar, the norm is absolute value; for a vector, it is the Euclidean norm
of the component-wise error. The result has the source target's unit: `m/s` for
velocity and `m^2/s^2` for both kinematic pressure and the raw kinematic
wall-shear vector.

- Compute each complete case first, then take the arithmetic mean of the case
  values. Do not pool large cases with small cases.
- With chunked evaluation, sum the additive numerators, denominators, counts,
  and weights across all chunks before applying a square root or division. Never
  average chunk-local norms.
- The activation release must additionally pin the binary64 accumulator,
  raw-entity/block merge order, and full-case-versus-chunked acceptance
  tolerance. Until that numeric replay is published, chunk invariance is an
  activation claim rather than a completed implementation.

The physical and equal-entity results answer different questions and neither may
be omitted. The owner-approved composite remains inactive until reference
baselines establish its distributions and the declared sensitivity review
confirms that one ranking is stable enough to publish. The present prototype
error caps and composite are not proposed for promotion.

FluidsBench's current generic rule nominates the equal-cell volume result as
primary, whereas a physical weighting approximates a continuum-domain norm and
equal-cell weighting deliberately emphasizes refined mesh regions. This
proposal requires both and does not override that repository-wide policy. A
physical-volume velocity norm can be dominated by the nearly uniform far field,
while a relative pressure norm can have a small denominator there. The baseline
sensitivity review must show both views and the absolute diagnostics before the
maintainers approve any ranking or dataset-specific exception. Any near-body or
wake-only score would require a separate owner-published geometric region; no
hidden crop is permitted.

## Case splits

Use the owner-published split lists in `owner-published-splits.json`:

| Track | Train | Validation | Test |
|---|---:|---:|---:|
| `full` | 400 | 34 | 50 |
| `medium` | 133 | 34 | 50 |
| `scarce` | 67 | 34 | 50 |
| `super_scarce` | 11 | 34 | 50 |
| `geometry` | 339 | 48 | 97 |
| `high_drag` | 339 | 48 | 97 |
| `low_drag` | 339 | 48 | 97 |
| `rear_separation` | 339 | 48 | 97 |

The `full` 400/34/50 IDs reproduce the AB-UPT seed-42 split. The other public
tracks are also owner-published and should keep their exact IDs and ordering.
Public test fields are evaluation-only: they cannot be used for fitting,
checkpoint selection, hyperparameter selection, manual tuning, or preprocessing
statistics.

GeoTransolver's drag-aware 436/48 split is a separate legacy paper split. It is
not silently substituted for an owner-published FluidsBench split.

## Paper-parity results

Paper-parity scores are useful reference results, but their namespace must state
their support, split, reduction, and coverage.

### AB-UPT literature parity

- Exact public `full` 400/34/50 split.
- Surface: all native VTP cells.
- Volume: VTU cells randomly subsampled to approximately the surface-cell count,
  repeated ten times—not the full native volume.
- Unweighted relative L2 per case, then case macro-average.
- Volume `p_v` means total pressure coefficient, not static `pMeanTrim`.
- Force values integrate dense surface predictions using polygon areas and
  normals and geometry-specific `A_ref`.

Its published field numbers must be labelled “AB-UPT sampled-cell literature
result” and must not be placed in the canonical full-volume column. This is not
yet an executable parity contract: the exact random-subsample generator, seeds,
and aggregation of the ten stochastic evaluations must be pinned first.

### GeoTransolver parity

- Exact legacy 436-train/48-held-out drag-aware split pinned to the published
  PhysicsNeMo-CFD lists.
- Surface: all native VTP `CellData` polygons.
- Volume: all raw VTU `PointData` vertices. For example, the audited
  paper-pipeline run 112 Zarr support has 159,899,850 entries, exactly matching
  raw VTU points rather than its 142,143,167 cells.
- Unweighted relative L1 per case, then case macro-average.
- Full support is inferred in chunks, reassembled, and scored once.

Its published field numbers must be labelled “GeoTransolver PointData parity.”
To claim reproduction of those published vector numbers, the parity evaluator
must use the released implementation's entity error
`abs(norm(prediction)-norm(truth))`. That magnitude-only formula must be named
explicitly and must not replace component-wise vector error in the canonical
benchmark.

## Forces and coefficients

Direct scalar prediction and force reconstructed from predicted fields are two
different tasks and must have different metric IDs.

The pinned release contains two scientifically distinct candidate truth
conventions:

- `force_mom_all.csv`: geometry-specific reference area and length; this measures
  aerodynamic efficiency and is consistent with the AB-UPT force calculation;
  and
- `force_mom_constref_all.csv`: constant `A_ref=2.17 m^2` and
  `L_ref=2.78618 m`; this retains geometry-size effects under one normalization.

No directly predicted scalar-force submission metric is frozen yet. For forces
reconstructed from the submitted surface fields, however, the proposed
composite selects the constant AutoCFD convention: rank `Cd` and `Cl` from
`force_mom_constref_all.csv` using `A_ref=2.17 m^2`. The geometry-specific
`force_mom_all.csv` result remains a separately named, unranked AB-UPT/
aerodynamic-efficiency diagnostic. The two conventions must never be mixed
between cases because they answer different design questions.

The pinned constant-reference aggregate table has exact columns
`run,cd,cl,clf,clr,cs`. It contains 484 finite rows and exactly one integer
`run` for every public case; join `run=N` to `case_id=run_N`. Ranked `Cd` and
`Cl` truth comes from the lowercase `cd` and `cl` columns and is dimensionless.
Reject missing, duplicate, non-integer, nonfinite, unexpected, or
manifest-extraneous run IDs rather than dropping or positionally aligning them.

The freestream values are `U_inf=38.889 m/s` and `rho_inf=1 kg/m^3`; drag is
the x direction and lift is the z direction. For each native polygon, let
`c_f` be the arithmetic mean of its vertex coordinates and form
`A_f=0.5*sum_i((v_i-c_f) cross (v_(i+1)-c_f))` in released connectivity order.
Using every native polygon exactly once, calculate
`F=rho_inf*sum_f(pMeanTrim_f*A_f-wallShearStressMeanTrim_f*|A_f|)`, then
`Cd=F_x/(0.5*rho_inf*U_inf^2*A_ref)` and
`Cl=F_z/(0.5*rho_inf*U_inf^2*A_ref)`. Run 1 reproduces the pinned rounded
`Cd/Cl` within `4.33e-8/1.53e-9`; activation requires both absolute differences
to be at most `1e-6` in every public case. Per-case `geo_ref_<run>.csv`
identities are needed only to activate the separately reported geometry-
specific-reference diagnostic. Do not call a scale-free force R-squared
calculation a fully specified coefficient calculation.

## Validity, exclusions, profiles, and cuts

- No submitter may infer an exclusion mask from target values. In particular,
  zero pressure is not by itself invalid.
- Before release, the benchmark owner must audit every required array in all 484
  cases for finite values and tuple-count consistency.
- Any exclusion must be published in the scoring support with `case_id`, raw
  entity ID, coordinates, reason, construction version, and source identity.
  The same frozen mask applies to every submission.
- The present prototype profile and Cp-cut station names do not include a full
  extraction and ground-truth contract and are not supported by AB-UPT or
  GeoTransolver scoring. Do not score those placeholders. They may be replaced
  by the separately versioned AutoCFD proposal below only after its exact
  coordinates, tolerance, extraction, ordering, quantities, truth hashes, and
  validation support are published and activated.
- The exact nominal AutoCFD4/5 pressure taps and velocity lines, together with
  fixed proposed FluidsBench sampling, reduction, and composite semantics, are
  now recorded in `AUTOCFD_DIAGNOSTICS_COMPOSITE_PROPOSAL.md` and its five CSV
  registries. They remain non-activating because the case-specific surrogate
  mapping, resolution-convergence audit, truth release, and validation gates
  listed there are not yet complete.

## Approval blockers

FluidsBench must not activate this proposal until one pull request supplies and
owner-approves all of the following:

1. an all-case VTK inventory proving required array association, tuple count,
   component count, finiteness, units, pressure gauge, wall-shear sign, and the
   provenance of CellData versus PointData;
2. stable surface and volume entity IDs, exact coordinates, surface areas, and
   volume-cell weights bound to the immutable source files, with pinned geometry
   algorithms, tolerances, and QA checks;
3. a declared exclusion policy and, if needed, a public stable-ID mask;
4. golden calculations for scalar and vector field reductions, including
   chunk-invariance tests, plus the reference profile locator and all-case
   AutoCFD profile/Cp support replay;
5. an all-484-case replay of the now-explicit force integration formula against
   the public constant-reference force file, plus chunk-invariance tests and,
   if the distinct directly predicted scalar task is ever activated, explicit
   target columns, reductions, and edge behavior;
6. official split index files generated from the pinned owner manifest;
7. the nearest-training-design donor map and golden donor-to-target transfer,
   the frozen bootstrap index artifact, and evidence from the declared
   baseline/model sensitivity analysis that the owner-approved composite is
   stable enough for a single ranking; and
8. dataset-owner approval of the immutable scoring-support manifest and
   evaluator release.

## Primary sources

- [DrivAerML dataset paper](https://arxiv.org/html/2408.11969)
- [AB-UPT paper](https://openreview.net/forum?id=nwQ8nitlTZ)
- [AB-UPT release used for the audit](https://github.com/Emmi-AI/anchored-branched-universal-physics-transformers/tree/2211068fd58600c52ed38de692f020e2d2b7c987)
- [AB-UPT DrivAerML cell-field loader](https://github.com/Emmi-AI/anchored-branched-universal-physics-transformers/blob/2211068fd58600c52ed38de692f020e2d2b7c987/src/drivaerml_dataset.py)
- [GeoTransolver paper](https://arxiv.org/html/2512.20399)
- [GeoTransolver PhysicsNeMo release used for the audit](https://github.com/NVIDIA/physicsnemo/tree/43de886be3e623758a1798d45fee5da44e21c335/examples/cfd/external_aerodynamics/transformer_models)
- [GeoTransolver full-support inference implementation](https://github.com/NVIDIA/physicsnemo/blob/43de886be3e623758a1798d45fee5da44e21c335/examples/cfd/external_aerodynamics/transformer_models/src/inference_on_zarr.py)
- [GeoTransolver preprocessing release](https://github.com/NVIDIA/physicsnemo-curator/tree/6d6d98e4a427353fbf2933601b398ee998d4314f/examples/external_aerodynamics)
- [GeoTransolver DrivAerML split release](https://github.com/NVIDIA/physicsnemo-cfd/tree/0612ec4ed54484a47bfa134eda7b3b012a607624/workflows/benchmarking/drivaer_ml_files)
- [OpenFOAM wall-shear-stress field definition](https://doc.openfoam.com/2306/tools/post-processing/function-objects/field/wallShearStress/)
- [AhmedML dataset paper](https://arxiv.org/html/2407.20801)
- [WindsorML dataset paper](https://arxiv.org/html/2407.19320)
