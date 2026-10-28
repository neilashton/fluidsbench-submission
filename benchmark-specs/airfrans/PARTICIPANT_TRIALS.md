# AirfRANS participant trial record

[Return to the quickstart](QUICKSTART.md).

## Completed participant trials

Emanuele Tamburini completed the container workflow with existing Transolver++
predictions for **Full (200 cases)** in [PR #68](https://github.com/neilashton/fluidsbench-submission/pull/68)
and **AoA extrapolation (196 cases)** in [PR #69](https://github.com/neilashton/fluidsbench-submission/pull/69).
He reported successful support-cache reuse, validation, field/profile extraction,
interruption and resume after 6 Full cases and 5 AoA cases, packaging with
`--checkpoint`, and package/contributor validation. The submitted metrics and
profiles match the retained inference results (overall scores 53.41 and 40.61).
These trials reused existing inference runs; they did not retrain the model.

The AoA package was separately approved for the dev leaderboard in
[PR #70](https://github.com/neilashton/fluidsbench-submission/pull/70).
It replaces the older prototype-contract display entry; the original package
remains in history. Approval checked submitted data and did not rerun the model
or independently recompute base metrics from full fields.

Scarce has automated workflow and retained-package validation, but no equivalent
completed participant trial is recorded here. Reynolds and production intake
remain closed. Prediction export remains model-specific: supply exactly the
four native arrays documented above before running the evaluator.
