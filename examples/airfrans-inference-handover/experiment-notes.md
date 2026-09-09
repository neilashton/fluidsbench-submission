# Experiment records to accompany AirfRANS predictions

Existing configuration files and logs are preferable to retyping everything.
Identify which files answer each item below. Leave unknown historical facts
explicitly unknown for follow-up; do not estimate them as measured values.
Maintainers will turn these records into `submission.json.methodology` and
the spatial/evaluation records. Use a separate inference record per split.

## Model and implementation

- Model name, author/contact, institution and paper.
- Exact upstream Transolver++ commit; exact adaptation revision and any local
  patch against it. Public source sharing is optional.
- Architecture/configuration and component roles; exact total, per-component
  and submitter-trainable parameter counts, or runnable counting code.
- Input features and components, output channel order, and which outputs are
  direct versus derived from model predictions.
- Environment/package versions and exact inference/export command.

## Training and selected checkpoint

- Training regime and exact data lists; validation/selection data; external
  pretraining and all upstream/fine-tuning stages.
- Normalization statistics and how they were fitted and inverted; preprocessing
  and sampling used for training and inference.
- Loss and weighting; optimiser, learning rate and schedule; batch unit/size,
  gradient accumulation, epochs/steps, run count and random seeds.
- Hardware and maximum concurrent device count; measured training campaign
  wall time and total device-hours, with the scope of those measurements.
- Raw-file SHA-256 for **every checkpoint file actually loaded**, its role
  and the selection rule applied before evaluation. Checkpoint publication
  is optional. If the file can be shared privately, maintainers can hash it.

## Inference and mapping, separately for Full and AoA

- Exact checkpoint(s), split, case IDs and any failed/retried cases.
- Hardware, device count, complete-split wall time and total device-seconds;
  timing method, preprocessing/mapping costs, and any excluded stages.
- For each case: native internal/airfoil point counts; training and inference
  representations; actual inference-input and direct-output point counts.
- Any subsampling/chunking; mapping from direct output to native points,
  unmapped and extrapolated counts, and boundary-pressure correspondence.
- Confirmation that pressure and velocity were denormalized and placed in
  the supplied native coordinate order; describe any boundary conditions
  imposed during inference/postprocessing.
- Confirmation that evaluation cases/targets were not used for fitting,
  normalization-statistic fitting or checkpoint selection.

## Result metadata

- Display name for the result and intended split(s).
- Preferred allowed open result-data licence for the eventual public result
  package; see `OPEN_REPRODUCIBILITY.md`. Sharing the complete prediction
  fields, source or model files publicly remains optional.
