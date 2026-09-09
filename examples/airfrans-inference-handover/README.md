# AirfRANS inference handover

This is a convenient handover between a model author and the FluidsBench
maintainers while AirfRANS submissions are closed. It is not a new submission
schema, an official scoring-support release, or a benchmark approval.

The model author runs inference and supplies the predictions and experiment
records. Maintainers can then extract profiles, implement/check the agreed
field and force evaluation, and assemble the schema-v3 result and PR.
Equivalent complete outputs can be adapted by agreement; this helper avoids
asking the model author to produce FluidsBench JSON.

## 1. Select the checkpoint and split

Start with **Full (200 evaluation cases)**. AoA extrapolation has **196** and
should use its own checkpoint/training-regime declaration and output directory.
An existing checkpoint can be used if its training and selection respect that
split. Do not select a checkpoint using the evaluation results.

From the repository root, generate the list directly from the checksum-bound
official split file:

```bash
python3 -m reference.airfrans_handover list-cases --split-id full > full-cases.txt
python3 -m reference.airfrans_handover list-cases --split-id aoa_extrapolation > aoa-cases.txt
```

Record the checkpoint checksum before inference, the run command, environment,
device count, wall time and aggregate device time. State whether preprocessing
and mapping are included and record their costs. Retain the original config
and logs; the [experiment notes](experiment-notes.md) list the information
needed for methodology and spatial records.

## 2. Export model predictions for each case

Create one `<case_id>.npz` file per case in a split-specific directory, with
these five arrays. Only NumPy is needed to write them.

| Array | Shape | Meaning |
| --- | --- | --- |
| `velocity` | `(N, 2)` | Predicted Cartesian Ux, Uy in m/s at every internal VTU point |
| `pressure` | `(N,)` | Predicted kinematic pressure p in m²/s² at those points |
| `airfoil_pressure` | `(M,)` | Predicted kinematic pressure p at every aerofoil VTP point |
| `internal_points` | `(N, 3)` | Unmodified native VTU coordinates in the same order as velocity and pressure |
| `airfoil_points` | `(M, 3)` | Unmodified native VTP coordinates in the same order as airfoil pressure |

`N` and `M` vary by case. Preserve the full original point order, including
native points with coincident coordinates; do not sort, deduplicate or round
the coordinates. Undo training normalization before export. These are
Cartesian velocities, not velocities divided by freestream speed. Pressure
is kinematic pressure, not pascals or Cp. The supplied pressure must come
from the model, including at the airfoil boundary.

If the model uses a subset, grid or different mesh, map its output to every
required native point, then export aligned arrays. Record the mapping,
unmapped/extrapolated counts and actual model/native point counts per case.
Do not substitute reference values for missing predictions. A boundary
pressure derived from the model's internal pressure is acceptable, but record
the exact correspondence or mapping. Do not assume `Simulation.airfoil_*`
arrays share the VTP file's point order; verify or restore native file order.

The following variables represent **your model predictions after mapping**:

```python
from pathlib import Path
from reference.airfrans_handover import write_case

write_case(
    Path("transolverpp-full"),
    case_id,
    velocity=predicted_velocity_native,       # (N, 2)
    pressure=predicted_pressure_native,       # (N,)
    airfoil_pressure=predicted_airfoil_pressure_native,  # (M,)
    internal_points=original_internal_points, # (N, 3), aligned with predictions
    airfoil_points=original_airfoil_points,   # (M, 3), aligned with predictions
)
```

The helper checks array shapes, real numeric types and finite values, and
refuses to overwrite an existing case. It does not run the model, normalize
fields, interpolate, infer units, or fill predictions from ground truth.
The `velocity` key also works directly with the existing
[profile extractor](../airfrans-profile-extraction/README.md).

## 3. Check and hand over

Either party can run this check using the existing pinned
[AirfRANS extraction environment](../airfrans-profile-extraction/requirements.txt):

```bash
python3 -m reference.airfrans_handover check \
  --split-id full \
  --predictions-root transolverpp-full \
  --dataset-root /path/to/AirfRANS/Dataset \
  --report full-handover-check.json
```

Choose a new report filename for each run. The check requires the exact full
split; a one-case export fails coverage. It checks all five arrays, compares
coordinates and their ordering with the local original meshes, and records
prediction/source-file hashes and point counts. The report does not prove
units, correct association of field values, model provenance, or scientific
accuracy; these depend on the export code and records. Local source hashes
are recorded for review, not certified as an approved support release.

Transfer the case files, check report if available, and experiment records
to the maintainers through an agreed file transfer. Public hosting of the
full fields or checkpoint is optional; large arrays need not be committed
to the submission Git repository. No profile chunks, submission JSON or
author-created PR are needed for this handover.

## Maintainer work after the handover

- Extract all eight profiles and calculate the balanced score with the pinned
  extractor/scorer; retain each station/component's raw and bounded R².
- Complete and review native supports, weights and evaluator bindings; compute
  field, wall-shear and force metrics and their required evidence.
- Assemble methodology, spatial records, per-case statistics, profile chunks,
  checksums and the schema-v3 package using the author's actual records.
- Obtain dataset-owner approval before official validation/publication.

The current AirfRANS specification is still `owner_review_required`, with
`submissions_open=false` and no bound candidate manifest. Neither this helper
nor a successful array check removes those outstanding release requirements.
