# Launch review before the ownership move

The launch is prepared in the existing `neilashton` repositories. The new
FluidsBench repositories must not be created or populated until Neil has reviewed
this version and approved the move.

## Intended launch behavior

- AirfRANS Full, Scarce and AoA extrapolation, AhmedML, WindsorML, DrivAerML and
  DrivAerNet++ accept submission packages through normal contributor validation.
- AirfRANS Reynolds remains closed. HiLiftAeroML, BlendedNet, Rotor37 and VKI-LS59
  are coming soon.
- Every old trial submission and leaderboard row is absent from this tree.
  Tests generate disposable packages or use clearly identified test fixtures.
- The leaderboard is unreleased and empty. Approval of a package does not publish
  it before an explicit official leaderboard release.
- The submission cutoff and leaderboard release are 5 December 2026, 23:59:59 AoE
  (6 December 2026, 11:59:59 UTC).
- DrivAerML relative diagnostics remain report-only with zero scoring weight;
  Neil waived sensitivity testing as an opening requirement.

## Review checks

The CI checks the complete unit suite, participant packaging in the pinned Linux
runtimes, support metadata and hash chains, and generated feeds. A separate run
checks the exported tree without Git history. The website review checks dataset
availability, the submission links, the deadline, and the empty leaderboard.

Support publication receipts describe their scope explicitly: current metadata,
local artifact bytes and remote payload hash pins. They do not claim a fresh
replay of every remote CFD payload. Existing scientific validation evidence is
retained unchanged, and source snapshots needed by its tests are included as
files rather than old Git history.

## After approval

Export the committed submission source with:

```bash
python scripts/export_launch_snapshot.py --output /path/to/new-local-snapshot
```

Create the new repositories from the reviewed source trees as new initial
commits. Do not transfer the old repositories or push their branches/tags/history.
Set the submission repository links and PR target to the new owner and chosen
branch, update the website configuration and availability snapshot, then repeat
link, support-download, contributor-validation and website checks before public
deployment. Published scientific support remains pinned to immutable bytes;
mirroring it must preserve those bytes and update only its hosting bindings.

This document does not authorize the ownership move or public production deployment.
