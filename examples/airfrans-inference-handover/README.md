# AirfRANS candidate submission guide

The model author prepares the complete candidate: inference, profile extraction,
metric calculation, schema-v3 packaging, contributor validation and a pull
request against `dev`. Maintainers can clarify the specification, review the
approach and help troubleshoot repository issues. Benchmark support publication
and final approval remain maintainer/dataset-owner responsibilities.

The steps below are practical suggestions for that workflow. The native NumPy
export helper is an optional intermediate format; an equivalent complete
prediction pipeline is also suitable. The final deliverable is the submission
package and its evidence. AirfRANS submissions remain closed pending support
and evaluator approval, so this guide supports preparation and review of an
unapproved candidate.

Use a full checkout of the latest `dev` branch of
[fluidsbench-submission](https://github.com/neilashton/fluidsbench-submission/tree/dev)
for packaging and validation, and record its exact commit. The attached
handover bundle contains a snapshot of the export/profile tools; it is not a
complete validator checkout or an approved scoring-support release.

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

## 3. Check the native predictions

Run this optional early check using the existing pinned
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

Retain the complete predictions for metric calculation, debugging and any
subsequent evaluator corrections. Public hosting of full fields or checkpoints
is optional; large arrays need not be committed to the submission repository.

## 4. Extract and score the profiles

Use the pinned [extractor and scorer](../airfrans-profile-extraction/README.md).
Install that example's exact requirements in a separate environment and run
commands from the repository root. First check one case, then process the
complete split. For the optional `.npz` layout above, a simple Full-split loop is:

```bash
mkdir -p work/full/predicted-profiles work/full/reference-profiles
while IFS= read -r case_id; do
  python3 examples/airfrans-profile-extraction/extract.py \
    --dataset-root /path/to/AirfRANS/Dataset \
    --case-name "$case_id" \
    --velocity-predictions "transolverpp-full/${case_id}.npz" \
    --output "work/full/predicted-profiles/${case_id}.json"
  python3 examples/airfrans-profile-extraction/extract.py \
    --dataset-root /path/to/AirfRANS/Dataset \
    --case-name "$case_id" \
    --output "work/full/reference-profiles/${case_id}.json"
done < full-cases.txt

python3 examples/airfrans-profile-extraction/score.py \
  --ground-truth work/full/reference-profiles/*.json \
  --predictions work/full/predicted-profiles/*.json \
  --split-id full \
  --output work/full/profile-score.json
```

Each case requires four stations, two Cartesian velocity components and 1,001
samples per profile. Retain the extractor's provenance and validity checks.
The score computes eight R² values across the complete split, bounds each to
`[0, 1]`, then averages them equally. Retain all eight raw and bounded values.
`--allow-partial` is for calibration only; omit it for a complete candidate.
Locally extracted reference profiles still need the benchmark's final truth
binding before they can serve as approved evaluation evidence.

## 5. Calculate all required metrics

Use the AirfRANS
[submission specification](https://github.com/neilashton/fluidsbench-submission/blob/dev/benchmark-specs/airfrans/submission-spec.json)
and [reference definitions](https://github.com/neilashton/fluidsbench-submission/blob/dev/reference/README.md).
The profile score is one part of the result. The current specification also
requires surface pressure and wall-shear errors, flow-domain velocity and
pressure errors, lift/drag statistics, and the derived component/overall scores.
Include the specified secondary and report-only quantities too.

Practical checks:

- Calculate wall shear and loads from model predictions using the agreed
  AirfRANS evaluator convention; record the code revision and all mappings.
- Use the prescribed native supports and physical weights. AirfRANS currently
  reports boundary length-weighted L2 as primary with an equal-point secondary,
  and flow-domain equal-point L2 as primary with an area-weighted secondary.
- For chunked inference, add error/reference sums, counts and weight totals
  before computing each complete-case relative L2. Then macro-average the
  complete-case field values. Do not average chunk-level L2 values.
- Retain per-case values and sufficient statistics for `metrics/cases.json`,
  plus the input hashes and evaluator provenance for `evaluation-evidence.json`.
- Raise unresolved support, pressure, shear or force conventions with the
  maintainers. Keep affected calculations provisional until those bindings
  are frozen; do not substitute DrivAerML or HiLiftAeroML definitions.

## 6. Assemble the schema-v3 package

Use the [v3 format example](https://github.com/neilashton/fluidsbench-submission/tree/dev/examples/v3-template)
and [repository workflow](https://github.com/neilashton/fluidsbench-submission/blob/dev/README.md).
The example contains synthetic values and is only a structural reference.
Historical AirfRANS dummy submissions are not templates for new real results.

Prepare one new submission directory per split, for example:

```text
submissions/airfrans/transolverpp-full-v1/
  submission.json
  evaluation-evidence.json
  metrics/cases.json
  discretization.json
  discretization/cases.jsonl
  profiles/index.json
  profiles/chunk-000.json
  ...
```

Populate methodology from your actual configuration and logs using the
[experiment checklist](experiment-notes.md) and
[methodology guide](https://github.com/neilashton/fluidsbench-submission/blob/dev/METHODOLOGY.md).
Include exact checkpoint/code identities, parameter counts, input/output and
normalization details, training settings, actual spatial counts/mappings, and
measured training/inference compute. Record unknown historical facts honestly.

Package all cases' extracted series as profile chunks and an index, preserving
the pinned station IDs, coordinates and sample counts. Compute the required
file SHA-256 bindings after writing the final files and update dependent hashes
whenever a referenced file changes. Do not copy synthetic support hashes or
maintainer approval records from the example.

## 7. Validate and open a draft PR against dev

In the full repository checkout, install its `requirements.txt`, then run:

```bash
python3 scripts/validate_submission.py --contributor-stage \
  submissions/airfrans/transolverpp-full-v1
```

Keep the command and output with the review notes, fix contributor-controlled
errors, and open a **draft PR against `dev`** for the candidate. Limit a result
PR to its one new submission directory; do not edit benchmark specifications,
validators, generated feeds or existing results to make it pass. Full can be
followed by AoA extrapolation in a separate PR.

The current AirfRANS specification is `owner_review_required`, with
`submissions_open=false` and no bound candidate manifest. Contributor-stage
validation therefore cannot certify a real AirfRANS submission yet. The
`--candidate-dry-run` option also requires a published, bound candidate support
release; it is not a bypass for the present missing bindings. Identify these
release blockers in the draft PR, ask maintainers to resolve them, and rerun
the applicable validation once the necessary release is available.

Maintainers review the package and manage final approval/publication. The
author remains responsible for producing the profiles, metrics, package and
contributor validation evidence.
