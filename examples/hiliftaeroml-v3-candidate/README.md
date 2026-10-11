# HiLiftAeroML compact-v2 candidate packaging

Compact-v2 is the sole selected participant profile representation. Public
submissions remain closed: immutable evaluator support publication, complete
implementation bindings, source pins, and release-specific owner approval are
still required. See the [participant guide](../../benchmark-specs/hiliftaeroml/PARTICIPANT_GUIDE.md)
for the fourteen training/evaluation labels, complete native-field requirements,
metrics, method records, and remaining gates.

The format contract and wire identifiers retain their historical `-candidate`
suffix. They are immutable identities, not the current lifecycle state. The
current [submission specification](../../benchmark-specs/hiliftaeroml/submission-spec.json)
selects that exact compact contract as official and rejects earlier native-v1
participant packages. Existing evaluator support, prediction bytes, validation
receipts, and all 23 registered previews remain unchanged.

## Development PR workflow

The dev adapter supports new, unapproved genuine-inference packages and a
maintainer registration command. Official intake remains closed. Use a fresh
checkout of `dev`; keep the historical example packages unchanged.

**Support distribution is pending.** The complete compact scoring-support
bundle is still required. Its exact manifest SHA-256 is
`7f946510cf8f63d05adaff4c91980d74f29c45ed7209b5a8f7e604e521cb823b`.
Until a download is bound in `benchmark-specs/hiliftaeroml/dev-release.json`,
provide its local directory through `FLUIDSBENCH_HILIFT_PROFILE_SUPPORT` or
`--profile-support-release`. This applies to the submitter and CI: a local
validation pass alone does not mean an external PR can pass on a clean runner.
The public browser plotting bundle cannot replace scoring support.

1. Copy `package-config.template.json` and complete the participant, method,
   checkpoint, compute, split and discretization fields. With `--dev-intake`,
   the assembler resolves the entire `release_bindings` object from the
   benchmark; do not fill owner hashes or evaluator revisions manually.
2. Run the native evaluator over the complete selected split. Retain its
   aggregate, per-case surface and volume outputs, and receipts. All four
   fields remain required. The compact adapter and SI export have their own
   immutable dev implementation binding, separate from the older native
   field/force evaluator revision.
3. Assemble and validate a new package, supplying every checkpoint actually
   loaded, using its methodology ID:

```bash
export FLUIDSBENCH_HILIFT_PROFILE_SUPPORT=/path/to/hiliftaeroml-compact-profile-support-v2-candidate

python scripts/assemble_hiliftaeroml_schema_v3_candidate.py \
  --dev-intake \
  --config /path/to/my-package-config.json \
  --native-aggregate /path/to/native/aggregate \
  --native-surface-outputs /path/to/native/surface/outputs \
  --native-volume-outputs /path/to/native/volume/outputs \
  --native-receipts /path/to/native/receipts \
  --checkpoint surface=/path/to/loaded-surface-checkpoint.pt \
  --checkpoint volume=/path/to/loaded-volume-checkpoint.pt \
  --output submissions/hiliftaeroml/my-method-v1

python scripts/validate_submission.py --dev-intake --contributor-stage \
  submissions/hiliftaeroml/my-method-v1
```

Use the actual checkpoint IDs from your method record; a shared model may have
one checkpoint and a sharded model may have more. Each raw file must match its
declared SHA-256. Add `--list-blockers` to inspect inputs without writing a
package. By using this mode, the submitter attests that the predictions came
from actual inference with the declared checkpoints. Byte verification identifies
files; it does not independently prove that inference was performed.

4. Commit only the new submission directory and open a PR targeting `dev`.
   CI validates complete coverage and independently recomputes compact profile
   scores against the exact support bundle. Contributors do not edit registries,
   generated feeds, approval records, or historical packages.

After contributor checks pass, a maintainer reviews the package and runs:

```bash
python scripts/register_hiliftaeroml_pre_release.py \
  submissions/hiliftaeroml/my-method-v1/submission.json --register
python scripts/manage_leaderboard.py build --dev-intake
python scripts/manage_leaderboard.py check --dev-intake
```

Commit the registry and generated feed changes on a maintainer branch based on
the contributor PR, then merge the reviewed changes into `dev`. Registration
binds every package file, checkpoint declaration and inference attestation.
Unregistered packages stay off the leaderboard; later edits invalidate their
registration. Registered rows appear only as non-citable dev references.
This requires no edits to validator source and does not approve an official result.

Daniel's independent trial should use a fresh checkout and a complete selected
split, then exercise the PR, registration and dev display sequence above. The
36-case single-AoA labels are complete splits when they match the model's
training regime; arbitrary subsets of a larger split are not accepted.

<a id="prepare-the-configuration-and-native-products"></a>

Use the shared [hardware and compute fields](../../METHODOLOGY.md#hardware-and-compute)
for each training stage and inference campaign, including GPU model and allocation counts.

## Inputs and blockers

Copy `package-config.template.json` outside this example directory and fill in
all participant and release fields. Preserve the selected split's exact case
order. Every unresolved placeholder is a blocker; never invent a release hash,
checkpoint digest, metric, or compute measurement.

Use the dataset evaluator to produce complete surface and volume predictions,
case-set aggregates, and per-case receipts. Both domains are required for every
case. The assembler verifies the chain from aggregate hashes through case
receipts and surface/volume summaries to each consumed artifact. The native
source-truth exporter remains an internal prerequisite for evaluator support,
not a participant package path.

The top-level `evaluation` object records the exact compact assembler command
and its RFC3339 `generated_at` time. There is one profile path. The retained
Transolver example configurations cover eleven labels; update their method,
checkpoint, timing, command, and provenance fields for your own run.

<a id="inspect-assemble-and-validate-locally"></a>

## Commands: inspect, assemble, and validate

Run from the repository root, using authorized evaluator-owned compact support:

```bash
python scripts/assemble_hiliftaeroml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --native-aggregate /path/to/native/aggregate \
  --native-surface-outputs /path/to/native/surface/per-case/outputs \
  --native-volume-outputs /path/to/native/volume/per-case/outputs \
  --native-receipts /path/to/native/per-case/receipts \
  --profile-support-release /path/to/hiliftaeroml-compact-profile-support-v2-candidate \
  --list-blockers

python scripts/assemble_hiliftaeroml_schema_v3_candidate.py \
  --config /path/to/package-config.json \
  --native-aggregate /path/to/native/aggregate \
  --native-surface-outputs /path/to/native/surface/per-case/outputs \
  --native-volume-outputs /path/to/native/volume/per-case/outputs \
  --native-receipts /path/to/native/per-case/receipts \
  --profile-support-release /path/to/hiliftaeroml-compact-profile-support-v2-candidate \
  --output /path/to/hiliftaeroml-my-method-v2

python scripts/validate_submission.py \
  --candidate-dry-run \
  --profile-support-release /path/to/hiliftaeroml-compact-profile-support-v2-candidate \
  /path/to/hiliftaeroml-my-method-v2
```

Do not bypass blockers. The output must not already exist. Repeating `--output`
exactly twice produces two independent packages while reusing one fully
validated support handle for the same ordered case set. The completed package
size is reported; there is no aggregate 15 MB cap because split sizes differ.
Per-file, shape, inventory, digest, and deterministic archive checks remain in
force.

## Outputs

Each case's NPZ contains exactly `cp_q_delta` and
`velocity_speed_over_u_inf`. Cp uses at most 128 samples per physical connected
graph, with evaluator-owned placement and fixed-int16 delta encoding. Velocity
uses the contract's lossless float32-bit transform stored as `uint8`. Coordinates,
topology, validity masks, weights, and truth remain in separate evaluator support.
Full native fields still determine field errors, forces, and pitching moment.
The public plot-truth release is insufficient for profile metric recomputation.

The assembler creates participant-owned schema-v3 files only. It never creates
approval or maintainer-validation records. Optional regional reports are
complete-split, report-only evidence with zero score weight. Local dry-run
success does not open public intake or create a leaderboard entry.

## Retained evidence and support

<details>
<summary>Registered previews, implementation provenance, and maintainer support materialization</summary>

Eleven Transolver and twelve GeoTransolver packages are registered as unapproved,
non-citable preview references. Their unchanged validation receipts are listed
in the [dataset README](../../benchmark-specs/hiliftaeroml/README.md).
The [all-case support validation](../../benchmark-specs/hiliftaeroml/compact-profile-all-case-support-validation-v1.json)
covers all 1,355 unique cases and eight case sets. Its
[rebind receipt](../../benchmark-specs/hiliftaeroml/compact-profile-all-case-support-rebind-v1.json)
records compatibility and independent package checks. Historical commands in
these receipts describe the original runs; use the commands above for new work.

The frozen base evaluator revision does not attest the later compact adapter or
regional-v2 implementation. Historical package provenance remains explicitly
`unbound_worktree_candidate`. New `--dev-intake` packages use the separately
bound dev implementation; this does not rewrite retained historical evidence.

Maintainers can materialize support from authorized native source truth and
validated evaluator outputs, or directly from the frozen prerequisite authority.
The [maintainer guide](../../docs/MAINTAINERS.md#hiliftaeroml-local-support-for-a-coordinated-dry-run) describes the materializer and exact split routing. Keep evaluator support
outside participant packages and use the declared manifest digest unchanged.

</details>
