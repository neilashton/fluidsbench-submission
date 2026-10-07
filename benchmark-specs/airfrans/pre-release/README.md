# AirfRANS pre-release references

These are hash-bound, unranked development references for PRs #44 and #45.
They do not open AirfRANS submissions, publish an official data release, or
record dataset-owner approval. Every normal schema-v3 package, metric,
discretization and profile check still runs against the candidate metadata.
The ordinary contributor and official-feed paths cannot use this registration.

The registry binds every byte of each retained submission and its validation
receipt. A changed package or release snapshot must be verified and registered
again. The feed marks these rows `pre_release_reference` and excludes them
from official ranking.

Each directory retains the original scoring-support manifest, case index and
chunk, the packaged profile-truth manifest, the reproduced profile scores and
a validation receipt. This is a **metadata snapshot**, not a complete evaluator
release. The native NPZ/force tables and CFD profile files remain in the
[contributor's handover](https://drive.google.com/drive/folders/14Tgs28bccp5HP-OXE8LVaIC-9RtFjqWC).
The candidate manifest URLs in the packages deliberately remain unpublished.

The handover's `SHA256SUMS` and per-archive `.files.sha256` files were checked.
All 600 Full and 588 AoA native supports loaded successfully. Profile scores
were reproduced byte for byte from the supplied truth and committed prediction
chunks. The combined profile-truth release contains 355 unique cases: 200 Full
and 196 AoA cases, with 41 shared. Original profiles were preserved byte for
byte, including extraction provenance.

This verification did not rerun model inference or re-extract truth from the
upstream VTK dataset. It preserves the submitted metrics and predictions.

To reproduce the registration after downloading, verifying and extracting the
handover, first run `scripts/export_airfrans_profile_truth.py` with both sources,
both native scoring-support manifests and extractor commit
`5f69ea140b061ec39b6827686a51c88d3ad657cd`. Then run:

```sh
python scripts/register_airfrans_pre_release.py \
  --submission-id transolverpp-full-v1 \
  --handover-root /path/to/handover \
  --profile-truth-release /path/to/airfrans-native-profile-truth-v1-candidate
python scripts/validate_submission.py submissions/airfrans/transolverpp-full-v1
python scripts/manage_leaderboard.py build
```

The handover root contains `downloads/` (including `SHA256SUMS` and
`profile-scores/`) and `extracted/` (the original native support directories).
For #45, repeat registration with `--submission-id transolverpp-aoa-v1`.
