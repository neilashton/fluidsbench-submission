# DrivAerNet++ pressure-profile station definitions (PROPOSED — pending validation)

Status: **draft for owner + maintainer review.** The four stations below are declared in
`submission-spec.json` (`profile_panels[0].station_ids`) but previously had no reproducible
geometric definition. This document proposes one. None of these definitions is validated on
public data yet; the panel therefore stays `required: false`, and profile ground truth must
not ship until each station passes the extraction checks on representative cases from every
configuration family (`E_S_*`, `F_S_*`, `N_S_*`, `F_D_WM_WW`).

## Shared conventions

- Source data: `SurfacePressureVTK/DrivAer_<ID>.vtk` (Dataverse doi:10.7910/DVN/K7PWNJ v1.0),
  PointData `p` (kinematic pressure, m²/s²), coordinates in metres.
- Pressure quantity: `cp`, defined as `Cp = p / (0.5 · U∞²) = p / 450`, dimensionless
  (U∞ = 30 m/s per the dataset simulation conditions).
- Per-design reference frame: `x_min`, `x_max`, `z_min` from the axis-aligned bounding box of
  the case's own surface mesh; car length `L = x_max − x_min`; all stations use coordinates
  normalized by `L` so morphed designs are comparable.
- Symmetry-plane tolerance: a point belongs to the centreline band when `|y| ≤ 2e-3 · L`.
  (DrivAerNet++ meshes are full-width; the band selects the discrete points nearest y = 0.)
- Surface-side classification uses the outward point normal `n` (area-weighted average of
  incident polygon normals, polygons oriented as stored): upper body `n_z > 0.2`,
  underbody `n_z < −0.2`, rear base `n_x > 0.5`.
- Sampling: select band points, classify, project onto the station coordinate, sort strictly
  ascending, average duplicate coordinates, and emit at least 2 points. Interpolation between
  discrete samples is linear in the station coordinate. No extrapolation.

## Stations

### 1. `upper_body_centerline`
- Geometry: centreline band (`|y| ≤ 2e-3·L`) ∩ upper surface (`n_z > 0.2`).
- Coordinate: `x/L` with `x̂ = (x − x_min)/L`, strictly increasing (front bumper → rear edge
  of roof/decklid).
- Captures stagnation, hood, windshield, roof, and rear-screen pressure development.

### 2. `underbody_centerline`
- Geometry: centreline band ∩ underbody (`n_z < −0.2`).
- Coordinate: `x/L`, strictly increasing.
- Note: for the `F_D_WM_WW` (detailed-underbody) family this trace crosses underbody
  components; the extraction must keep only points on the outer wetted surface (largest
  connected component of the band). Validation must confirm this rule on at least one
  detailed-underbody case.

### 3. `front_wheelhouse`
- Geometry: the body-side wheel-arch rim trace. Per design: wheel centre `c = (c_x, c_y, c_z)`
  and radius `R` from the bounding box of the front-wheel surface patch; cutting plane
  `y = c_y` intersected with the body (non-wheel) surface, restricted to points within
  `1.6 · R` of `c` in the x–z plane.
- Coordinate: polar angle `θ` around `c` in the x–z plane, mapped to `s = θ/(2π) ∈ [0, 1)`
  measured from the forward horizontal direction, increasing over the arch (counter-clockwise
  viewed from +y), strictly increasing.
- This is the most geometry-sensitive station: if the wheel patch cannot be isolated
  deterministically from the released surface files across all configurations
  (WW / WWC / WWS), **the recommended fallback is to drop this station** rather than ship an
  ambiguous definition.

### 4. `rear_body_centerline`
- Geometry: centreline band ∩ rear base (`n_x > 0.5`), i.e. the rear-facing base surface.
- Coordinate: `ẑ = (z − z_min)/L`, strictly increasing (bottom of base → top of base).
- Captures the base-pressure distribution that dominates pressure drag differences between
  estateback / fastback / notchback families.

## Validation checks required before any station becomes ground truth

1. Extraction succeeds and is visually sane on ≥ 2 cases from each configuration family.
2. The selected point count per station is stable (no empty or single-point traces).
3. Duplicate-coordinate handling and strict ordering verified.
4. `Cp` values reproduce hand-computed `p/450` at spot-checked points.
5. The station-selection thresholds (`2e-3·L`, `n_z ±0.2`, `n_x 0.5`, `1.6·R`) are either
   confirmed or re-tuned, and the final values are frozen in the extraction script alongside
   its SHA-256.
