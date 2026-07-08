# fluidsbench-submission

Submission repository for the FluidsBench leaderboard.

The live leaderboard is here: [FluidsBench leaderboard](https://neilashton.github.io/fluidsbench/).

Dataset-specific benchmark details, required prediction files, metric definitions, and any dataset-specific notes live on
the main FluidsBench website. Start from the [dataset pages](https://neilashton.github.io/fluidsbench/datasets/) before
preparing a submission.

## What gets submitted

A submission is a JSON file containing:

- submission metadata, such as model name, one or more model types, submitter name, institution, paper URL, and code URL
- the dataset and split being evaluated
- scalar leaderboard metrics, such as L1/L2 field errors, force R2 values, velocity-profile R2, and Cp-cut R2
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

```json
{
  "submission_id": "todo-unique-submission-id",
  "model": "TODO model name",
  "model_type": "TODO primary model type",
  "model_types": ["TODO primary model type", "TODO optional second model type"],
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
  "diagnostics": {
    "cp_cuts": [],
    "velocity_profiles": []
  }
}
```

TODO: replace this with the final JSON schema once the validator is fixed.

## Validation

TODO: add the final validator command.

Expected validator responsibilities:

- check that required fields are present
- check that the dataset and split are valid
- check that metric values are numeric and within expected ranges
- check that Cp and velocity diagnostic arrays use the required case IDs, cut IDs, station IDs, coordinates, and units
- check that no large binary files are committed to this repository

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
