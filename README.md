# fluidsbench-submission

Submission repository for the FluidsBench leaderboard.

The live leaderboard is here: [FluidsBench leaderboard](https://neilashton.github.io/fluidsbench/).

Dataset-specific benchmark details, required prediction files, metric definitions, and any dataset-specific notes live on
the main FluidsBench website. Start from the [dataset pages](https://neilashton.github.io/fluidsbench/datasets/) before
preparing a submission.

## What gets submitted

A submission is a JSON file containing:

- submission metadata, such as model name, one or more model types, training regime, submitter name, institution, paper URL, and code URL
- the dataset and split being evaluated
- scalar leaderboard metrics, including relative field errors, dimensional field MAE/RMSE, absolute force or moment
  coefficient errors, force R2 values, velocity-profile R2, and Cp-cut R2
- compact diagnostic curve data for selected Cp cuts and velocity profiles

Each dataset has its own folder under `submissions/`:

```text
submissions/
  ahmedml/
  drivaerml/
  drivaernetplusplus/
  windsorml/
  hiliftaeroml/
  airfrans/
```

Approved submissions are summarized into generated leaderboard feeds:

```text
leaderboard/
  manifest.json
  all.json
  datasets/
    ahmedml.json
    drivaerml.json
    ...
```

`leaderboard/manifest.json` tells the website which dataset-specific leaderboard files to load. `leaderboard/all.json`
is the combined feed. The root `leaderboard.json` is kept temporarily for backwards compatibility while the website
moves to manifest-based loading.

## How to submit

1. Read the relevant dataset page on the main FluidsBench website:
   [FluidsBench datasets](https://neilashton.github.io/fluidsbench/datasets/).
2. Run the relevant benchmark/evaluator for that dataset.
3. Create one JSON file under `submissions/<dataset-slug>/`.
4. Use a clear `submission_id`, for example `my-lab-ahmedml-modelname-v1`.
5. Run the validator before opening a PR.
6. Open a pull request to this repository with your submission file.
7. A maintainer reviews the submission. Once approved, the leaderboard feed is regenerated and the result appears on
   the [FluidsBench leaderboard](https://neilashton.github.io/fluidsbench/).

TODO: confirm whether external submitters should target `main` directly or a staging branch first.

## Submission format

The current dummy examples show the intended shape:

- [`submissions/ahmedml/dummy-ahmedml-flowformer-v1.json`](submissions/ahmedml/dummy-ahmedml-flowformer-v1.json)
- [`submissions/drivaerml/dummy-drivaerml-meshoperator-v1.json`](submissions/drivaerml/dummy-drivaerml-meshoperator-v1.json)
- [`submissions/drivaernetplusplus/dummy-drivaernetplusplus-surfacegnn-v1.json`](submissions/drivaernetplusplus/dummy-drivaernetplusplus-surfacegnn-v1.json)
- [`submissions/windsorml/dummy-windsorml-wakenet-v1.json`](submissions/windsorml/dummy-windsorml-wakenet-v1.json)
- [`submissions/hiliftaeroml/dummy-hiliftaeroml-liftoperator-v1.json`](submissions/hiliftaeroml/dummy-hiliftaeroml-liftoperator-v1.json)
- [`submissions/airfrans/dummy-airfrans-airfoiloperator-v1.json`](submissions/airfrans/dummy-airfrans-airfoiloperator-v1.json)

At minimum, each submission should include:

Use `model_types` for the model category list. `model_type` is kept as the primary category for backwards compatibility
with older tooling; it should usually match the first entry in `model_types`.

Use `split` to identify the benchmark split that was evaluated. The leaderboard displays the human-readable split names
below, and `leaderboard/manifest.json` stores the same split names with canonical IDs and train/validation/test counts.

Current AhmedML split values:

- `Full`
- `Medium`
- `Scarce`
- `Super scarce`
- `Geometry`
- `High drag`
- `Low drag`
- `Image wake`

Current DrivAerML split values:

- `Full`
- `Medium`
- `Scarce`
- `Super scarce`
- `Geometry`
- `High drag`
- `Low drag`
- `Rear separation`

Current AirfRANS split values:

- `Full`
- `Scarce`
- `Reynolds extrapolation`
- `AoA extrapolation`

Current HiLiftAeroML split values:

- `Full`
- `Medium`
- `Scarce`
- `Super scarce`
- `Geometry`
- `Geometry medium`
- `Geometry scarce`
- `Geometry super scarce`
- `AoA 4`
- `AoA 12`
- `AoA 22`
- `AoA extrapolation`
- `Deflection`
- `Stall`

Use `training_regime` to describe whether the submission was trained only on the official dataset training split or used
external pretraining. Allowed values are:

- `from_scratch`: trained without external pretraining
- `pretrained_zero_shot`: pretrained externally and evaluated without target dataset training data
- `pretrained_official_train`: pretrained externally and then used the official benchmark training split
- `other`: anything that does not fit the above categories

Use `target_data_used` to clarify the target benchmark data used by the submission. Current values are `official_train`,
`none`, and `other`.

```json
{
  "submission_id": "todo-unique-submission-id",
  "model": "TODO model name",
  "model_type": "TODO primary model type",
  "model_types": ["TODO primary model type", "TODO optional second model type"],
  "training_regime": "from_scratch",
  "target_data_used": "official_train",
  "external_pretraining": false,
  "pretraining_data": [],
  "dataset": "TODO dataset name",
  "split": "TODO split name",
  "submitter_name": "TODO person, lab, or company",
  "institution": "TODO institution",
  "paper_url": "TODO optional paper URL",
  "code_url": "TODO optional code URL",
  "surface_pressure_l2": 0.0,
  "surface_pressure_l1": 0.0,
  "surface_tau_l2": 0.0,
  "surface_tau_l1": 0.0,
  "volume_velocity_l2": 0.0,
  "volume_velocity_l1": 0.0,
  "volume_pressure_l2": 0.0,
  "volume_pressure_l1": 0.0,
  "r2_cd": 0.0,
  "r2_cl": 0.0,
  "velocity_profile_r2": 0.0,
  "cp_cut_r2": 0.0,
  "dimensional_field_errors": {
    "surface_pressure": {"mae": 0.0, "rmse": 0.0},
    "surface_wall_shear": {"mae": 0.0, "rmse": 0.0},
    "volume_velocity": {"mae": 0.0, "rmse": 0.0},
    "volume_pressure": {"mae": 0.0, "rmse": 0.0}
  },
  "absolute_coefficient_errors": {
    "c_drag": 0.0,
    "c_lift": 0.0
  },
  "diagnostics": {
    "cp_cuts": [],
    "velocity_profiles": []
  }
}
```

The enabled dimensional fields and coefficient errors are dataset-specific. `leaderboard/manifest.json` is authoritative:
its `metric_catalog` defines labels, SI display units, precision, and weighting, while each dataset's `metrics` object
lists the IDs that must be present. HiLiftAeroML currently also requires `absolute_coefficient_errors.c_pitch`.

The evaluator must compute dimensional metrics after undoing model normalization and converting predictions and targets
to the SI unit declared in the manifest. Submitted values must be evaluator outputs; they must not be inferred from the
relative errors.

For coefficient value `C` across `N` evaluated cases, the reported absolute error is mean absolute error:

```text
MAE(C) = (1 / N) sum_i |C_pred,i - C_true,i|
```

For field `q`, `w_ij` is face area for surface quantities or cell volume for volume quantities. Scalar fields use the
absolute point error; vector fields use the Euclidean magnitude of the error vector. Cases are weighted equally:

```text
MAE(q)  = (1 / N) sum_i [sum_j w_ij ||q_pred,ij - q_true,ij|| / sum_j w_ij]
RMSE(q) = sqrt((1 / N) sum_i [sum_j w_ij ||q_pred,ij - q_true,ij||^2 / sum_j w_ij])
```

## Validation

Validate all source submissions and confirm the generated feeds are synchronized:

```bash
python3 scripts/manage_leaderboard.py check
```

Validate one proposed submission before opening a PR:

```bash
python3 scripts/manage_leaderboard.py validate submissions/<dataset-slug>/<submission>.json
```

Maintainers regenerate all dataset feeds, `leaderboard/all.json`, the compatibility `leaderboard.json`, counts, and
timestamps with:

```bash
python3 scripts/manage_leaderboard.py build
```

The validator checks:

- required metadata and scalar metrics
- dataset names, dataset folders, and manifest-defined splits
- finite numeric values and allowed metric ranges
- every dataset-required dimensional field MAE/RMSE and coefficient MAE
- the presence of Cp-cut and velocity-profile diagnostic arrays

## Review process

A maintainer will review each PR before it is merged. The review is expected to check:

- the submitted files match the required schema
- the submitted metrics are reproducible from the provided evaluator outputs
- the dataset-specific instructions on the FluidsBench website were followed
- the diagnostic Cp and velocity-profile data are present where required
- paper/code links and submitter metadata are appropriate for publication on the leaderboard

After approval, maintainers regenerate the `leaderboard/` feeds and merge the PR. The website reads the approved feed and
updates the public leaderboard.

TODO: add exact maintainer checklist and automation details.

## Related links

- [FluidsBench leaderboard](https://neilashton.github.io/fluidsbench/)
- [FluidsBench dataset pages](https://neilashton.github.io/fluidsbench/datasets/)
- [AhmedML dataset page](https://neilashton.github.io/fluidsbench/datasets/ahmedml/)
- [DrivAerML dataset page](https://neilashton.github.io/fluidsbench/datasets/drivaerml/)
- [DrivAerNet++ dataset page](https://neilashton.github.io/fluidsbench/datasets/drivaernetplusplus/)
- [WindsorML dataset page](https://neilashton.github.io/fluidsbench/datasets/windsorml/)
- [HiLiftAeroML dataset page](https://neilashton.github.io/fluidsbench/datasets/hiliftaeroml/)
- [AirfRANS dataset page](https://neilashton.github.io/fluidsbench/datasets/airfrans/)

## License

TODO: confirm whether all submitted metadata and diagnostic data are covered by the repository license.

See [LICENSE](LICENSE).
