# fluidsbench-submission

Submission repository and approved-data feed for the [FluidsBench leaderboard](https://neilashton.github.io/fluidsbench/).

Read the [dataset pages](https://neilashton.github.io/fluidsbench/datasets/) before preparing a result. They define the
evaluation files, split rules, metrics, units, and diagnostic stations for each dataset.

## What gets submitted

One JSON file is submitted under the matching dataset folder:

```text
submissions/
  ahmedml/
  airfrans/
  blendednet/
  drivaerml/
  drivaernetplusplus/
  hiliftaeroml/
  rotor37/
  vki-ls59/
  windsorml/
```

Every file includes:

- model, submitter, training, dataset, split, parameter-count, paper, and code metadata
- evaluator-produced metric values required by that dataset
- the compact profile arrays required by that dataset's `diagnostic_panels`

The manifest is authoritative. For each dataset, it declares:

- `splits`: exact accepted split names and case counts
- `metric_ids`: ordered metrics displayed in the table and charts
- `ranking`: the primary metric and whether higher or lower is better
- `diagnostic_panels`: submitted array keys, quantities, coordinates, stations, and required coverage
- `submission_format`: either the existing external-aerodynamics shape or direct `metric_values`

## How to submit

1. Read the relevant [FluidsBench dataset specification](https://neilashton.github.io/fluidsbench/datasets/).
2. Run the official dataset evaluator and its validator script.
3. Create one JSON file under `submissions/<dataset-slug>/`.
4. Give it a globally unique `submission_id`, such as `my-lab-rotor37-model-v1`.
5. Run the repository validator.
6. Open a pull request with the source submission file and the evaluator evidence requested by the dataset page.
7. A maintainer reviews reproducibility, metadata, metrics, and diagnostic coverage.
8. After approval, a maintainer rebuilds the generated feeds and merges the PR. The website then reads the approved
   dataset feed through `leaderboard/manifest.json`.

TODO: confirm whether external PRs should target `main` directly or a staging branch first.

## Common metadata

```json
{
  "submission_id": "todo-unique-id",
  "model": "TODO model name",
  "model_type": "Neural operator",
  "model_types": ["Neural operator", "Transformer"],
  "training_regime": "from_scratch",
  "target_data_used": "official_train",
  "external_pretraining": false,
  "pretraining_data": [],
  "dataset": "TODO exact manifest dataset name",
  "split": "TODO exact manifest split name",
  "parameter_count": 0.0,
  "submitter_name": "TODO person, lab, or company",
  "institution": "TODO institution",
  "paper_url": "",
  "code_url": "",
  "submitted_at": "YYYY-MM-DD"
}
```

`model_types` can contain more than one architecture category. `model_type` remains the primary category for compatibility
and should normally equal the first `model_types` value.

Allowed `training_regime` values are:

- `from_scratch`: no external pretraining
- `pretrained_zero_shot`: external pretraining, no target-dataset training data
- `pretrained_official_train`: external pretraining followed by the official target training split
- `other`: a regime not covered above

The deliberately excluded categories are `pretrained_finetuned` and `pretrained_linear_probe`. Use
`pretrained_official_train` when a pretrained model is trained with the official benchmark training split.

## Dataset splits

The exact accepted values are in `leaderboard/manifest.json`. In particular:

VKI-LS59:

```text
train, train_500, train_250, train_125, train_64, train_32, train_16, train_8
```

VKI reduced sets use the first N entries of the published training index sequence and share the 168-case test set.

Rotor37:

```text
train_1000, train_500, train_250, train_125, train_64, train_32, train_16, train_8
```

Rotor37 reduced sets use the official non-contiguous index selections and share the 200-case test set. Do not replace
those selections with the first N cases.

BlendedNet:

```text
geometry_holdout
```

The published release groups cases by geometry. Its train/validation pool contains 8,830 cases from 999 geometries; the
fixed 870-case test set uses 100 entirely distinct geometries.

## Metric formats

### Dataset-driven `metric_values`

VKI-LS59, Rotor37, and BlendedNet use a direct metric map:

```json
{
  "metric_values": {
    "total_error": 0.025,
    "rotor_pressure_rrmse": 0.031,
    "rotor_pressure_rel_l2": 3.2,
    "rotor_pressure_rel_l1": 2.3,
    "rotor_pressure_r2": 0.98,
    "rotor_pressure_mae": 1200.0,
    "rotor_pressure_rmse": 1700.0
  }
}
```

The object must contain every ID listed in that dataset's `metric_ids`. The dummy examples show the complete shape:

- [`submissions/vki-ls59/dummy-vki-ls59-train.json`](submissions/vki-ls59/dummy-vki-ls59-train.json)
- [`submissions/rotor37/dummy-rotor37-train_1000.json`](submissions/rotor37/dummy-rotor37-train_1000.json)
- [`submissions/blendednet/dummy-blendednet-geometry-holdout.json`](submissions/blendednet/dummy-blendednet-geometry-holdout.json)

The primary PLAID quantities are:

```text
RRMSE_field = sqrt((1/n) sum_i [((1/N_i) ||f_pred,i-f_ref,i||_2^2) / ||f_ref,i||_inf^2])
RRMSE_scalar = sqrt((1/n) sum_i [|s_pred,i-s_ref,i|^2 / |s_ref,i|^2])
total_error = (1/m) sum_j RRMSE_j
```

Additional common metrics are:

```text
L1_rel(%) = 100 sum_i w_i |y_pred,i-y_ref,i| / sum_i w_i |y_ref,i|
L2_rel(%) = 100 sqrt(sum_i w_i (y_pred,i-y_ref,i)^2) / sqrt(sum_i w_i y_ref,i^2)
R2 = 1 - sum_i (y_ref,i-y_pred,i)^2 / sum_i (y_ref,i-mean(y_ref))^2
MAE_weighted = sum_i w_i |y_pred,i-y_ref,i| / sum_i w_i
RMSE_weighted = sqrt(sum_i w_i (y_pred,i-y_ref,i)^2 / sum_i w_i)
MAE_unweighted = (1/N) sum_i |y_pred,i-y_ref,i|
RMSE_unweighted = sqrt((1/N) sum_i (y_pred,i-y_ref,i)^2)
```

For external-aerodynamics field metrics, `w_i` is face area for surface quantities and cell volume for volume quantities.
Metrics explicitly described as unweighted use the corresponding `1/N` equation.

Rotor37 dimensional errors use `kg/m^3`, `Pa`, `K`, and `kg/s` where applicable. Compression ratio and efficiency are
dimensionless. VKI-LS59 dimensional MAE/RMSE are not accepted until a canonical public denormalization and unit convention
has been fixed.

BlendedNet ranks the arithmetic mean of the relative L2 errors for `Cp`, `Cfx`, and `Cfz`. It also reports MSE, MAE,
relative L1, relative L2, and R2 for those surface coefficients, plus MAE and R2 for integrated `CD`, `CL`, and `CMy`.
These native aerodynamic coefficients are dimensionless; the benchmark does not relabel them as dimensional fields.

### Existing external-aerodynamics format

AhmedML, AirfRANS, DrivAerML, DrivAerNet++, HiLiftAeroML, and WindsorML retain their existing scalar fields,
`dimensional_field_errors`, and `absolute_coefficient_errors`. During feed generation, the build script converts these to
the same public `metric_values` map consumed by the frontend.

See an existing complete example:

- [`submissions/ahmedml/dummy-ahmedml-flowformer-v1.json`](submissions/ahmedml/dummy-ahmedml-flowformer-v1.json)
- [`submissions/hiliftaeroml/dummy-hiliftaeroml-liftoperator-v1.json`](submissions/hiliftaeroml/dummy-hiliftaeroml-liftoperator-v1.json)

## Diagnostic arrays

Diagnostics are dataset-driven. Each manifest panel defines:

- `data_key`: the array name under `diagnostics`
- `x_keys`: accepted coordinate keys
- `quantities`: quantity IDs and accepted value keys
- `stations`: exact required station IDs

Each submitted series has this generic form:

```json
{
  "case_id": "evaluator-case-id",
  "station_id": "manifest-station-id",
  "quantity_id": "manifest-quantity-id",
  "values": [
    {"x_over_c": 0.0, "pressure_ratio": 0.98},
    {"x_over_c": 1.0, "pressure_ratio": 1.42}
  ]
}
```

VKI-LS59 uses `surface_profiles` for `M_iso` on `pressure_side` and `suction_side`, and `flow_profiles` for normalized
velocity at `outlet_plane_2`.

Rotor37 uses `blade_profiles` for pressure ratio at `span_10`, `span_50`, and `span_90`. It uses
`blade_thermo_profiles` for temperature and density ratios at the same stations. Rotor37 has no submitted velocity-profile
diagnostic.

BlendedNet uses `cp_cuts` and `skin_friction_profiles` at three `prototype_*` surface cuts. They are required for
interface and pipeline testing, but remain explicitly illustrative until the evaluator fixes canonical extraction
locations and tolerances. BlendedNet does not publish volume velocity fields, so no velocity-profile diagnostic is
invented.

The reference or ground-truth curves are not submitted here. They are owned by the FluidsBench website repository under
`assets/data/diagnostic-ground-truth/`.

## Validation

Validate one proposed file:

```bash
python3 scripts/manage_leaderboard.py validate submissions/<dataset-slug>/<submission>.json
```

Validate every source submission and verify generated feeds:

```bash
python3 scripts/manage_leaderboard.py check
```

Maintainers regenerate the manifest counts, dataset feeds, combined feed, and compatibility feed with:

```bash
python3 scripts/manage_leaderboard.py build
```

The validator checks required metadata, dataset folder, split name, complete metric IDs, numeric ranges, and every required
diagnostic station/quantity pair.

## Generated feeds

```text
leaderboard/
  manifest.json
  all.json
  datasets/
    ahmedml.json
    ...
    blendednet.json
    rotor37.json
    vki-ls59.json
leaderboard.json
```

The website loads the selected dataset feed lazily through `leaderboard/manifest.json`. Generated public rows always include
`metric_values`, so the website contains no dataset-specific score-row mapping. The root `leaderboard.json` remains only for
backwards compatibility.

## Review process

Maintainers should verify that:

- the official dataset split and evaluator were used
- metrics are reproducible from submitted evaluator evidence
- every manifest metric is present with the declared unit and direction
- every required diagnostic station/quantity series is complete
- model, pretraining, submitter, paper, and code metadata are suitable for publication

After approval, run `build`, run `check`, and merge the source and generated feed changes together.

TODO: add dataset evaluator packages and exact maintainer evidence checklists.

## Related links

- [FluidsBench leaderboard](https://neilashton.github.io/fluidsbench/)
- [FluidsBench dataset pages](https://neilashton.github.io/fluidsbench/datasets/)
- [VKI-LS59 dataset page](https://neilashton.github.io/fluidsbench/datasets/vki-ls59/)
- [Rotor37 dataset page](https://neilashton.github.io/fluidsbench/datasets/rotor37/)
- [BlendedNet dataset page](https://neilashton.github.io/fluidsbench/datasets/blendednet/)

## License

TODO: confirm whether all submitted metadata and diagnostic data are covered by the repository license.

See [LICENSE](LICENSE).
